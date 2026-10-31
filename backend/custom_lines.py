"""Lignes ajoutées ou corrigées depuis la page d'administration (onglet « Lignes ajoutées »).

Elles sont gardées dans MongoDB (collection custom_lines) et ajoutées au réseau importé : une ligne
de même id remplace celle du fichier, et une ligne « masquée » en est retirée. Elles survivent donc
aux réimports de tunismapper.com.

- GET    /api/admin/custom-lines        : lignes ajoutées ou modifiées, et lignes du fichier qui ne
                                          viennent pas de tunismapper (modifiables aussi).
- POST   /api/admin/custom-lines        : crée une ligne (arrêts dans l'ordre du sens aller).
- PUT    /api/admin/custom-lines/{id}   : la modifie.
- DELETE /api/admin/custom-lines/{id}   : la supprime (une ligne du fichier est masquée).

Le tracé suit les routes (OSRM, comme les itinéraires en voiture) ou relie les arrêts en ligne
droite (métro, train, ou si OSRM ne répond pas).
"""
import asyncio
import logging
import re
import time
from datetime import datetime, timezone
from typing import List, Literal, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

import network
import roads
from admin import require_admin
from database import db
from geo import Shape

logger = logging.getLogger("tuntransport.custom_lines")
admin = APIRouter(prefix="/api/admin", dependencies=[Depends(require_admin)])

Mode = Literal["bus", "metro", "train", "rfr"]
ShapeMode = Literal["road", "straight"]
HHMM = r"^([01]\d|2[0-3]):[0-5]\d$"


class StopIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    lat: float = Field(ge=30, le=38)  # la Tunisie
    lon: float = Field(ge=7, le=12)


class CustomLineIn(BaseModel):
    mode: Mode = "bus"
    short_name: str = Field(min_length=1, max_length=12)
    long_name: str = Field(min_length=1, max_length=120)
    color: str = Field(default="#0E7490", pattern=r"^#[0-9A-Fa-f]{6}$")
    operator: str = Field(default="Bus TRANSTU", max_length=60)
    headsigns: List[str] = Field(default_factory=list, max_length=2)  # [aller, retour] ; terminus par défaut
    stops: List[StopIn] = Field(min_length=2, max_length=120)
    shape_mode: ShapeMode = "road"
    # Horaires facultatifs : premier et dernier départ du terminus, fréquence.
    first_departure: Optional[str] = Field(default=None, pattern=HHMM)
    last_departure: Optional[str] = Field(default=None, pattern=HHMM)
    headway_min: Optional[int] = Field(default=None, ge=3, le=240)


# ------------------------ Construction ------------------------
async def _osrm(client: httpx.AsyncClient, path: str) -> dict:
    """Appel OSRM voiture, espacé d'une seconde sur les serveurs publics (même verrou que roads.py)."""
    base = roads.OSRM_URLS["car"]
    if roads._public(base):
        async with roads._lock:
            wait = roads.MIN_INTERVAL_S - (time.monotonic() - roads._last_call)
            if wait > 0:
                await asyncio.sleep(wait)
            try:
                response = await client.get(f"{base}/{path}")
            finally:
                roads._last_call = time.monotonic()
    else:
        response = await client.get(f"{base}/{path}")
    response.raise_for_status()
    data = response.json()
    if data.get("code") != "Ok":
        raise RuntimeError(data.get("code"))
    return data


async def _road_shapes(stops: list) -> list:
    """Arrêts calés sur la route, puis un tracé routier par sens."""
    async with httpx.AsyncClient(timeout=20.0, headers={"User-Agent": roads.USER_AGENT}) as client:
        for s in stops:
            lon, lat = (await _osrm(client, f"nearest/v1/driving/{s['lon']:.6f},{s['lat']:.6f}?number=1"))["waypoints"][0]["location"]
            s["lat"], s["lon"] = round(lat, 6), round(lon, 6)
        shapes = []
        for ordered in (stops, stops[::-1]):
            coords = ";".join(f"{s['lon']:.6f},{s['lat']:.6f}" for s in ordered)
            route = (await _osrm(client, f"route/v1/driving/{coords}?overview=full&geometries=geojson"))["routes"][0]
            shapes.append([[round(lat, 6), round(lon, 6)] for lon, lat in route["geometry"]["coordinates"]])
    return shapes


def _timetable(spec: CustomLineIn, stops: list, headsigns: list) -> dict:
    """Départs des deux terminus, de first_departure à last_departure, tous les headway_min."""
    if not (spec.first_departure and spec.last_departure and spec.headway_min):
        return {}
    h1, m1 = map(int, spec.first_departure.split(":"))
    h2, m2 = map(int, spec.last_departure.split(":"))
    times = [f"{t // 60:02d}:{t % 60:02d}" for t in range(h1 * 60 + m1, h2 * 60 + m2 + 1, spec.headway_min)]
    return {stops[0]["id"]: {headsigns[0]: times}, stops[-1]["id"]: {headsigns[1]: times}}


async def build(line_id: str, spec: CustomLineIn) -> dict:
    stops = [{"id": f"{line_id}-{i}", "name": s.name.strip(), "lat": s.lat, "lon": s.lon} for i, s in enumerate(spec.stops)]
    headsigns = [h.strip() for h in spec.headsigns if h.strip()]
    if len(headsigns) < 2:
        headsigns = [stops[-1]["name"], stops[0]["name"]]
    shape_source = "manual"
    shapes = None
    if spec.shape_mode == "road":
        try:
            shapes = await _road_shapes(stops)
            shape_source = "osrm"
        except Exception:
            logger.exception("OSRM failed for custom line %s: straight shape", line_id)
    if shapes is None:
        straight = [[s["lat"], s["lon"]] for s in stops]
        shapes = [straight, straight[::-1]]
    directions = []
    for d, ordered in enumerate((stops, stops[::-1])):
        shape = Shape([tuple(p) for p in shapes[d]])
        directions.append({
            "headsign": headsigns[d],
            "shape": shapes[d],
            "stops": [{"id": s["id"], "along_m": round(shape.project(s["lat"], s["lon"]).along_m)} for s in ordered],
        })
    return {
        "id": line_id, "mode": spec.mode, "short_name": spec.short_name.strip(), "long_name": spec.long_name.strip(),
        "color": spec.color, "operator": spec.operator.strip(), "shape_source": shape_source,
        "stops": stops, "directions": directions, "timetable": _timetable(spec, stops, headsigns),
    }


# ------------------------ Réseau ------------------------
async def apply() -> None:
    """Recharge les lignes de l'admin dans le réseau servi."""
    docs = await db.custom_lines.find({}, {"_id": 0}).to_list(1000)
    network.set_custom([d["line"] for d in docs if not d.get("hidden")], {d["id"] for d in docs if d.get("hidden")})


async def setup() -> None:
    await db.custom_lines.create_index("id", unique=True)
    await apply()


def _spec_from_line(line: dict) -> dict:
    """Formulaire pré-rempli pour une ligne du fichier (ex. le 347 de tools/extra_lines.json)."""
    by_id = {s["id"]: s for s in line["stops"]}
    order = [by_id[s["id"]] for s in line["directions"][0]["stops"] if s["id"] in by_id]
    return {
        "mode": line["mode"], "short_name": line["short_name"], "long_name": line["long_name"],
        "color": line.get("color") or "#0E7490", "operator": line.get("operator") or "",
        "headsigns": [d["headsign"] for d in line["directions"][:2]],
        "stops": [{"name": s["name"], "lat": s["lat"], "lon": s["lon"]} for s in order],
        "shape_mode": "road" if line.get("shape_source") == "osrm" else "straight",
    }


def _row(line_id: str, spec: dict, line: Optional[dict], origin: str, hidden: bool = False, updated_at=None) -> dict:
    return {"id": line_id, "origin": origin, "hidden": hidden, "spec": spec, "line": line,
            "updated_at": updated_at.isoformat() if isinstance(updated_at, datetime) else updated_at}


@admin.get("/custom-lines")
async def list_custom_lines():
    docs = {d["id"]: d for d in await db.custom_lines.find({}, {"_id": 0}).to_list(1000)}
    rows = []
    for line in network.file_lines():  # lignes du fichier hors tunismapper (ajoutées à la main)
        if line.get("shape_source") in ("osrm", "manual") and line["id"] not in docs:
            rows.append(_row(line["id"], _spec_from_line(line), line, "file"))
    file_ids = {line["id"] for line in network.file_lines()}
    for d in docs.values():
        rows.append(_row(d["id"], d["spec"], d.get("line"), "file+admin" if d["id"] in file_ids else "admin",
                         d.get("hidden", False), d.get("updated_at")))
    rows.sort(key=lambda r: (r["spec"]["mode"], r["spec"]["short_name"]))
    return rows


def _new_id(short_name: str) -> str:
    base = "x" + (re.sub(r"[^A-Za-z0-9]+", "", short_name).lower() or "ligne")
    line_id, n = base, 2
    while line_id in network.current().lines or line_id in {line["id"] for line in network.file_lines()}:
        line_id, n = f"{base}-{n}", n + 1
    return line_id


async def _save(line_id: str, spec: CustomLineIn) -> dict:
    line = await build(line_id, spec)
    await db.custom_lines.update_one(
        {"id": line_id},
        {"$set": {"id": line_id, "spec": spec.model_dump(), "line": line, "hidden": False,
                  "updated_at": datetime.now(timezone.utc)}},
        upsert=True,
    )
    await apply()
    return line


@admin.post("/custom-lines")
async def create_custom_line(spec: CustomLineIn):
    line_id = _new_id(spec.short_name)
    return await _save(line_id, spec)


@admin.put("/custom-lines/{line_id}")
async def update_custom_line(line_id: str, spec: CustomLineIn):
    in_file = next((line for line in network.file_lines() if line["id"] == line_id), None)
    if not await db.custom_lines.find_one({"id": line_id}):
        if in_file is None:
            raise HTTPException(404, "Unknown line")
        if in_file.get("shape_source") not in ("osrm", "manual"):
            raise HTTPException(400, "Les lignes importées de tunismapper ne se modifient pas ici")
    return await _save(line_id, spec)


@admin.delete("/custom-lines/{line_id}")
async def delete_custom_line(line_id: str):
    in_file = next((line for line in network.file_lines() if line["id"] == line_id), None)
    doc = await db.custom_lines.find_one({"id": line_id})
    if not doc and not in_file:
        raise HTTPException(404, "Unknown line")
    if in_file:
        # Une ligne du fichier reviendrait au prochain chargement : on la masque.
        await db.custom_lines.update_one(
            {"id": line_id},
            {"$set": {"id": line_id, "spec": (doc or {}).get("spec") or _spec_from_line(in_file), "line": None,
                      "hidden": True, "updated_at": datetime.now(timezone.utc)}},
            upsert=True,
        )
    else:
        await db.custom_lines.delete_one({"id": line_id})
    await apply()
    return {"ok": True}


@admin.post("/custom-lines/{line_id}/restore")
async def restore_custom_line(line_id: str):
    """Annule les modifications de l'admin : la ligne du fichier revient telle quelle."""
    await db.custom_lines.delete_one({"id": line_id})
    await apply()
    return {"ok": True}

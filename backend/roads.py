"""Itinéraires en voiture et à pied (OSRM, données OpenStreetMap).

- POST /api/routes/road : trajet routier d'un point (ou arrêt) à un autre, mode `car` ou `foot`,
  avec la durée, la distance, le tracé et les instructions en français.

Par défaut, les serveurs OSRM publics de FOSSGIS (routing.openstreetmap.de) : une requête par seconde
au plus, User-Agent identifiant l'application, réponses en cache. Pour un trafic plus important,
installez OSRM sur le VPS (deploy/setup-osrm.sh) et réglez OSRM_CAR_URL / OSRM_FOOT_URL.
La durée en voiture ne tient pas compte du trafic.
"""
import asyncio
import logging
import math
import os
import time
from collections import OrderedDict
from typing import List, Literal, Optional

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

import routing
import trips

logger = logging.getLogger("tuntransport.roads")

OSRM_URLS = {
    "car": os.environ.get("OSRM_CAR_URL", "https://routing.openstreetmap.de/routed-car"),
    "foot": os.environ.get("OSRM_FOOT_URL", "https://routing.openstreetmap.de/routed-foot"),
}
USER_AGENT = "TransTunisLive/1.0 (+https://tuntransport.academy)"
MIN_INTERVAL_S = 1.0
CACHE_SIZE = 1000
CACHE_TTL_S = 86400
SIMPLIFY_M = 4.0

_cache: "OrderedDict[str, tuple]" = OrderedDict()
_lock = asyncio.Lock()
_last_call = 0.0


def _public(url: str) -> bool:
    return url.startswith("https://routing.openstreetmap.de")


async def _fetch(mode: str, a: tuple, b: tuple) -> dict:
    """Appel OSRM ; les serveurs publics sont espacés d'au moins une seconde."""
    global _last_call
    base = OSRM_URLS[mode]
    url = f"{base}/route/v1/driving/{a[1]:.6f},{a[0]:.6f};{b[1]:.6f},{b[0]:.6f}"
    params = {"overview": "full", "geometries": "geojson", "steps": "true"}
    async with httpx.AsyncClient(timeout=10.0, headers={"User-Agent": USER_AGENT}) as client:
        if _public(base):
            async with _lock:
                wait = MIN_INTERVAL_S - (time.monotonic() - _last_call)
                if wait > 0:
                    await asyncio.sleep(wait)
                try:
                    response = await client.get(url, params=params)
                finally:
                    _last_call = time.monotonic()
        else:
            response = await client.get(url, params=params)
    response.raise_for_status()
    return response.json()


# ------------------------ Instructions en français ------------------------
DIRECTIONS = {
    "left": "à gauche", "right": "à droite", "slight left": "légèrement à gauche", "slight right": "légèrement à droite",
    "sharp left": "franchement à gauche", "sharp right": "franchement à droite", "straight": "tout droit", "uturn": "demi-tour",
}
ORDINAL = {1: "1re", 2: "2e", 3: "3e", 4: "4e", 5: "5e", 6: "6e"}


def instruction(step: dict) -> str:
    m = step.get("maneuver", {})
    kind, modifier = m.get("type", ""), m.get("modifier", "")
    name = step.get("name") or step.get("ref") or ""
    # Nom isolé (U+2068…U+2069) : un nom de rue en arabe ne doit pas réordonner la phrase française.
    on = f" sur \u2068{name}\u2069" if name else ""
    direction = DIRECTIONS.get(modifier, "")
    if kind == "depart":
        return f"Partez{on}"
    if kind == "arrive":
        return "Vous êtes arrivé"
    if kind in ("roundabout", "rotary", "roundabout turn"):
        exit_no = m.get("exit")
        return f"Au rond-point, prenez la {ORDINAL.get(exit_no, f'{exit_no}e')} sortie{on}" if exit_no else f"Au rond-point, continuez{on}"
    if modifier == "uturn":
        return f"Faites demi-tour{on}"
    if kind in ("new name", "continue") or modifier == "straight":
        return f"Continuez tout droit{on}" if kind != "new name" else f"Continuez{on}"
    if kind in ("fork", "off ramp", "on ramp", "merge"):
        side = "à gauche" if "left" in modifier else "à droite" if "right" in modifier else ""
        verb = {"fork": "À l’embranchement, restez", "off ramp": "Prenez la sortie", "on ramp": "Prenez la bretelle",
                "merge": "Insérez-vous"}[kind]
        return f"{verb} {side}{on}".replace("  ", " ").strip()
    if kind == "end of road":
        return f"Au bout de la route, tournez {direction}{on}"
    return f"Tournez {direction}{on}" if direction else f"Continuez{on}"


def _simplify(points: List[List[float]], tolerance_m: float) -> List[List[float]]:
    """Douglas-Peucker (projection locale), pour alléger le tracé envoyé à l'app."""
    if len(points) < 3:
        return points
    lat0 = math.radians(points[0][0])
    xy = [(math.radians(lon) * math.cos(lat0) * 6_371_000, math.radians(lat) * 6_371_000) for lat, lon in points]
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        s, e = stack.pop()
        (ax, ay), (bx, by) = xy[s], xy[e]
        dx, dy = bx - ax, by - ay
        length = math.hypot(dx, dy)
        best_i, best_d = None, tolerance_m
        for i in range(s + 1, e):
            px, py = xy[i]
            d = abs(dx * (ay - py) - dy * (ax - px)) / length if length else math.hypot(px - ax, py - ay)
            if d > best_d:
                best_i, best_d = i, d
        if best_i is not None:
            keep[best_i] = True
            stack += [(s, best_i), (best_i, e)]
    return [p for p, k in zip(points, keep) if k]


# ------------------------ API ------------------------
class RoadRequest(BaseModel):
    origin: routing.Place
    destination: routing.Place
    mode: Literal["car", "foot"]
    depart_at: Optional[float] = Field(default=None, description="heure de départ (secondes epoch) ; maintenant si absent")


class RoadStep(BaseModel):
    instruction: str
    distance_m: int
    duration_s: int


class RoadRoute(BaseModel):
    mode: Literal["car", "foot"]
    distance_m: int
    duration_s: int
    depart: str
    arrive: str
    date: str
    path: List[List[float]]
    steps: List[RoadStep]


router = APIRouter(prefix="/api")


@router.post("/routes/road", response_model=RoadRoute)
async def road_route(payload: RoadRequest):
    g = routing.graph()
    origin = routing._resolve(g, payload.origin, "Départ")
    dest = routing._resolve(g, payload.destination, "Arrivée")
    now = trips.now()
    t0 = now if payload.depart_at is None else payload.depart_at
    if not now - 600 <= t0 <= now + routing.MAX_DEPART_AHEAD_S:
        raise HTTPException(422, "depart_at must be between now and 3 days ahead")

    a, b = (round(origin["lat"], 5), round(origin["lon"], 5)), (round(dest["lat"], 5), round(dest["lon"], 5))
    key = f"{payload.mode}:{a}:{b}"
    cached = _cache.get(key)
    if cached and time.time() - cached[0] < CACHE_TTL_S:
        _cache.move_to_end(key)
        data = cached[1]
    else:
        try:
            data = await _fetch(payload.mode, a, b)
        except Exception:
            logger.exception("OSRM %s request failed", payload.mode)
            raise HTTPException(502, "Road routing unavailable")
        if data.get("code") != "Ok" or not data.get("routes"):
            raise HTTPException(404, "No road route")
        _cache[key] = (time.time(), data)
        while len(_cache) > CACHE_SIZE:
            _cache.popitem(last=False)

    route = data["routes"][0]
    steps = [s for leg in route.get("legs", []) for s in leg.get("steps", [])]
    path = [[round(lat, 6), round(lon, 6)] for lon, lat in route["geometry"]["coordinates"]]
    duration = route["duration"]
    return RoadRoute(
        mode=payload.mode,
        distance_m=round(route["distance"]),
        duration_s=round(duration),
        depart=routing._hhmm(t0),
        arrive=routing._hhmm(t0 + duration),
        date=routing.datetime.fromtimestamp(t0, routing.TUNIS_TZ).date().isoformat(),
        path=_simplify(path, SIMPLIFY_M),
        steps=[RoadStep(instruction=instruction(s), distance_m=round(s.get("distance", 0)), duration_s=round(s.get("duration", 0)))
               for s in steps if s.get("distance", 0) > 0 or s.get("maneuver", {}).get("type") == "arrive"],
    )

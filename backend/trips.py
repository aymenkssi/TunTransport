"""Trajets partagés par les passagers et véhicules en direct.

- POST /api/trips                       : le passager déclare sa ligne et son sens (un seul trajet actif).
- POST /api/trips/{id}/positions        : dernières positions GPS (fenêtre de ~60 s) ; le serveur vérifie
                                          la trace et ne publie que la position le long du tracé.
- POST /api/trips/{id}/end              : fin du trajet, la position disparaît immédiatement.
- GET  /api/lines/{id}/vehicles         : véhicules de la ligne (position, fiabilité, ETA à un arrêt).
- GET  /api/vehicles/live               : tous les véhicules en direct du réseau (carte d'accueil).
- GET  /api/live                        : nombre de véhicules en direct par ligne.

Confidentialité : les coordonnées brutes ne sont jamais enregistrées. Seule la position le long du
tracé est gardée, dans `contributions`, et expire quelques minutes après la dernière mise à jour.
"""
import time
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

import network
import vehicles as vh
from auth import current_user
from database import db
from matching import REASONS, match_trace

MAX_TRIP_S = 2 * 3600
MAX_TRIPS_PER_DAY = 40
MAX_CLOCK_SKEW_S = 120.0  # fixes plus vieux ou dans le futur : ignorés
POSITION_COOLDOWN_S = 2.0

router = APIRouter(prefix="/api")


def now() -> float:
    return time.time()


def iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).isoformat()


# ------------------------ Models ------------------------
class TripStart(BaseModel):
    line_id: str = Field(..., max_length=32)
    direction: int = Field(..., ge=0, le=1)


class TripStarted(BaseModel):
    id: str
    line_id: str
    direction: int
    headsign: str


class PositionResult(BaseModel):
    # "checking" : pas encore assez de points ; "on_route" : position publiée ;
    # "rejected" : trace incompatible, rien n'est publié.
    status: Literal["checking", "on_route", "rejected"]
    reason: Optional[str] = None
    along_m: Optional[float] = None
    speed_mps: Optional[float] = None


class VehicleOut(BaseModel):
    direction: int
    headsign: str
    lat: float
    lon: float
    along_m: float
    speed_mps: float
    confirmations: int
    age_s: int
    reliability: float
    status: Literal["fiable", "probable", "obsolète"]
    eta_s: Optional[int] = None


class LiveVehicle(VehicleOut):
    line_id: str
    line_label: str
    long_name: str
    mode: str
    color: Optional[str] = None


# ------------------------ Helpers ------------------------
async def _active_trip(trip_id: str, user: dict) -> dict:
    trip = await db.trips.find_one({"id": trip_id, "user_id": user["id"]})
    if not trip:
        raise HTTPException(404, "Unknown trip")
    if trip.get("ended_at") is not None:
        raise HTTPException(410, "Trip ended")
    if now() - trip["started_ts"] > MAX_TRIP_S:
        await _end(trip, "timeout")
        raise HTTPException(410, "Trip ended")
    return trip


async def _end(trip: dict, reason: str) -> None:
    await db.contributions.delete_one({"trip_id": trip["id"]})
    await db.trips.update_one(
        {"id": trip["id"], "ended_at": None}, {"$set": {"ended_at": iso(now()), "end_reason": reason}}
    )


async def _fresh_contributions(line_id: Optional[str] = None) -> List[vh.Contribution]:
    query: dict = {"t": {"$gte": now() - vh.EXPIRED_AGE_S}}
    if line_id:
        query["line_id"] = line_id
    docs = await db.contributions.find(query, {"_id": 0}).to_list(5000)
    return [vh.Contribution(d["trip_id"], d["line_id"], d["direction"], d["along_m"], d["speed_mps"], d["t"]) for d in docs]


# ------------------------ Routes ------------------------
@router.post("/trips", response_model=TripStarted)
async def start_trip(payload: TripStart, user: dict = Depends(current_user)):
    line = network.current().line(payload.line_id)
    t = now()
    day_start = t - t % 86400
    if await db.trips.count_documents({"user_id": user["id"], "started_ts": {"$gte": day_start}}) >= MAX_TRIPS_PER_DAY:
        raise HTTPException(429, "Too many trips today")
    async for previous in db.trips.find({"user_id": user["id"], "ended_at": None}):
        await _end(previous, "replaced")

    trip = {
        "id": str(uuid.uuid4()),
        "user_id": user["id"],
        "line_id": line.id,
        "direction": payload.direction,
        "started_ts": t,
        "started_at": iso(t),
        "ended_at": None,
        "last_position_ts": 0.0,
        "on_route_count": 0,
    }
    await db.trips.insert_one(trip)
    headsign = line.data["directions"][payload.direction]["headsign"]
    return TripStarted(id=trip["id"], line_id=line.id, direction=payload.direction, headsign=headsign)


@router.post("/trips/{trip_id}/positions", response_model=PositionResult)
async def post_positions(trip_id: str, trace: network.Trace, user: dict = Depends(current_user)):
    trip = await _active_trip(trip_id, user)
    t = now()
    if t - trip["last_position_ts"] < POSITION_COOLDOWN_S:
        raise HTTPException(429, "Too many updates")
    await db.trips.update_one({"id": trip_id}, {"$set": {"last_position_ts": t}})

    line = network.current().line(trip["line_id"])
    fixes = [f.to_fix() for f in trace.fixes if abs(f.t - t) <= MAX_CLOCK_SKEW_S]
    result = match_trace(fixes, line.shapes[trip["direction"]], line.max_offset_m)

    if not result.ok:
        # Plus rien n'est publié dès que la trace n'est plus validée.
        await db.contributions.delete_one({"trip_id": trip_id})
        if result.reason == "too_short":
            return PositionResult(status="checking")
        return PositionResult(status="rejected", reason=REASONS[result.reason])

    await db.contributions.update_one(
        {"trip_id": trip_id},
        {"$set": {
            "trip_id": trip_id,
            "line_id": trip["line_id"],
            "direction": trip["direction"],
            "along_m": result.along_m,
            "speed_mps": result.speed_mps,
            "t": t,  # heure du serveur : l'horloge du téléphone peut être fausse
            "expires_at": datetime.fromtimestamp(t + vh.EXPIRED_AGE_S, timezone.utc),
        }},
        upsert=True,
    )
    await db.trips.update_one({"id": trip_id}, {"$inc": {"on_route_count": 1}})
    return PositionResult(status="on_route", along_m=round(result.along_m), speed_mps=round(result.speed_mps, 1))


@router.post("/trips/{trip_id}/end")
async def end_trip(trip_id: str, user: dict = Depends(current_user)):
    trip = await db.trips.find_one({"id": trip_id, "user_id": user["id"]})
    if not trip:
        raise HTTPException(404, "Unknown trip")
    await _end(trip, "user")
    return {"ok": True}


def _vehicle_out(line: "network.LoadedLine", vehicle: vh.Vehicle, t: float, stop_id: Optional[str] = None) -> Optional[dict]:
    """Véhicule prêt à afficher (position sur la carte, fiabilité, ETA), ou None s'il a expiré."""
    score, status = vh.reliability(vehicle, t)
    if status == "expiré":
        return None
    direction = line.data["directions"][vehicle.direction]
    shape = line.shapes[vehicle.direction]
    along = min(vehicle.estimated_along(t), shape.length_m)
    lat, lon = shape.point_at(along)
    eta = None
    if stop_id:
        stop = next((s for s in direction["stops"] if s["id"] == stop_id), None)
        seconds = vh.eta_seconds(vehicle, stop["along_m"], t) if stop else None
        eta = None if seconds is None else round(seconds)
    return {
        "direction": vehicle.direction,
        "headsign": direction["headsign"],
        "lat": round(lat, 6),
        "lon": round(lon, 6),
        "along_m": round(along),
        "speed_mps": round(vehicle.speed_mps, 1),
        "confirmations": len(vehicle.contributors),
        "age_s": round(t - vehicle.last_update),
        "reliability": round(score, 2),
        "status": status,
        "eta_s": eta,
    }


@router.get("/lines/{line_id}/vehicles", response_model=List[VehicleOut])
async def line_vehicles(line_id: str, stop_id: Optional[str] = None):
    line = network.current().line(line_id)
    t = now()
    out = [VehicleOut(**v) for vehicle in vh.cluster_vehicles(await _fresh_contributions(line_id), t)
           if (v := _vehicle_out(line, vehicle, t, stop_id))]
    if stop_id:
        out.sort(key=lambda v: (v.eta_s is None, v.eta_s or 0))
    return out


@router.get("/vehicles/live", response_model=List[LiveVehicle])
async def network_vehicles():
    """Tous les véhicules en direct du réseau, pour la carte d'accueil."""
    t = now()
    net = network.current()
    out = []
    for vehicle in vh.cluster_vehicles(await _fresh_contributions(), t):
        line = net.lines.get(vehicle.line_id)
        v = _vehicle_out(line, vehicle, t) if line else None
        if v:
            out.append(LiveVehicle(**v, line_id=line.id, line_label=line.data["short_name"] or line.data["long_name"],
                                   long_name=line.data["long_name"], mode=line.data["mode"], color=line.data.get("color")))
    return out


@router.get("/live", response_model=Dict[str, int])
async def live_counts():
    """Nombre de véhicules visibles par ligne, pour les badges de la liste des lignes."""
    t = now()
    counts: Dict[str, int] = {}
    for vehicle in vh.cluster_vehicles(await _fresh_contributions(), t):
        if vh.reliability(vehicle, t)[1] != "expiré":
            counts[vehicle.line_id] = counts.get(vehicle.line_id, 0) + 1
    return counts


async def setup() -> None:
    await db.trips.create_index("id", unique=True)
    await db.trips.create_index([("user_id", 1), ("started_ts", -1)])
    await db.contributions.create_index("trip_id", unique=True)
    await db.contributions.create_index("line_id")
    # MongoDB supprime lui-même les positions expirées.
    await db.contributions.create_index("expires_at", expireAfterSeconds=0)

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

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

import network
import trust
import vehicles as vh
from auth import current_user
from database import db
from matching import REASONS, match_trace

MAX_TRIP_S = 2 * 3600
MAX_TRIPS_PER_DAY = 40
MAX_CLOCK_SKEW_S = 120.0  # fixes plus vieux ou dans le futur : ignorés
POSITION_COOLDOWN_S = 2.0
DETOUR_MAX_S = 15 * 60  # déviation tolérée au plus 15 min après la dernière position sur le tracé
DETOUR_REASON = "déviation"

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
    # "rejected" : trace incompatible, rien n'est publié. Une déviation tolérée renvoie "on_route"
    # avec reason="déviation" (les anciennes versions de l'application continuent de partager).
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


# ------------------------ Journal des trajets ------------------------
# Un événement à chaque changement d'état (pas à chaque position) : onglet « Trajets » de l'admin.
MAX_EVENTS = 60
END_REASONS = {
    "user": "arrêté par le voyageur (ou automatiquement, hors de la ligne)",
    "timeout": "durée maximale atteinte",
    "replaced": "remplacé par un nouveau partage",
    "mocked": "position simulée (faux GPS)",
}


async def _log(trip: dict, kind: str, reason: Optional[str] = None, **data) -> None:
    """Ajoute un événement ; le même état répété n'est compté qu'une fois (champ n)."""
    events = trip.get("events") or []
    key = f"{kind}|{reason or ''}"
    t = now()
    if events and kind not in ("started", "ended") and f"{events[-1]['kind']}|{events[-1].get('reason') or ''}" == key:
        i = len(events) - 1
        await db.trips.update_one({"id": trip["id"]}, {"$inc": {f"events.{i}.n": 1}, "$set": {f"events.{i}.last": iso(t)}})
        return
    event = {"at": iso(t), "kind": kind, "n": 1, **({"reason": reason} if reason else {}),
             **{k: (round(v, 1) if isinstance(v, float) else v) for k, v in data.items() if v is not None}}
    update: dict = {"$push": {"events": {"$each": [event], "$slice": -MAX_EVENTS}}}
    if kind == "rejected":
        update["$set"] = {"last_reject_reason": reason}
    await db.trips.update_one({"id": trip["id"]}, update)
    trip["events"] = (events + [event])[-MAX_EVENTS:]


def _trace_info(received: int, fixes: list, result=None) -> dict:
    """Mesures utiles pour comprendre un refus : nombre de points, précision GPS, écart à la ligne."""
    precise = [f for f in fixes if f.accuracy_m <= 50]
    info = {"fixes": received, "precise": len(precise)}
    if fixes:
        info["accuracy_m"] = float(sorted(f.accuracy_m for f in fixes)[len(fixes) // 2])
    if result is not None:
        if result.mean_offset_m:
            info["offset_m"] = float(result.mean_offset_m)
        if result.speed_mps:
            info["speed_kmh"] = float(result.speed_mps * 3.6)
        if result.along_m:
            info["along_m"] = round(result.along_m)
    return info


async def _end(trip: dict, reason: str) -> None:
    await db.contributions.delete_one({"trip_id": trip["id"]})
    invalidate_live()
    res = await db.trips.update_one(
        {"id": trip["id"], "ended_at": None}, {"$set": {"ended_at": iso(now()), "end_reason": reason}}
    )
    if res.modified_count:
        fresh = await db.trips.find_one({"id": trip["id"]}, {"_id": 0, "events": 1, "on_route_count": 1, "rejected_count": 1}) or {}
        await _log({"id": trip["id"], "events": fresh.get("events")}, "ended", END_REASONS.get(reason, reason),
                   validated=fresh.get("on_route_count", 0), refused=fresh.get("rejected_count", 0))
    await trust.settle_trip(trip["id"])


async def _fresh_contributions(line_id: Optional[str] = None) -> List[vh.Contribution]:
    """Positions récentes, sans celles masquées après signalement."""
    query: dict = {"t": {"$gte": now() - vh.EXPIRED_AGE_S}, "hidden": {"$ne": True}}
    if line_id:
        query["line_id"] = line_id
    docs = await db.contributions.find(query, {"_id": 0}).to_list(5000)
    return [vh.Contribution(d["trip_id"], d["line_id"], d["direction"], d["along_m"], d["speed_mps"], d["t"],
                            d.get("trusted", True)) for d in docs]


def visible(vehicles: List[vh.Vehicle]) -> List[vh.Vehicle]:
    """Un véhicule n'est montré que si au moins un de ses passagers est de confiance."""
    return [v for v in vehicles if v.trusted > 0]


# Les véhicules visibles de tout le réseau sont recalculés au plus toutes les LIVE_CACHE_S et
# partagés par tous les écrans qui les demandent (carte, lignes, compteur, itinéraires).
# Toute écriture de position dans ce processus vide le cache ; les autres le voient en 2 s au plus.
LIVE_CACHE_S = 2.0
_live_cache: dict = {"at": 0.0, "t": None, "vehicles": None}


def invalidate_live() -> None:
    _live_cache["vehicles"] = None


async def live_vehicles(t: float, line_id: Optional[str] = None) -> List[vh.Vehicle]:
    """Véhicules visibles (non expirés) à l'instant t, éventuellement d'une seule ligne."""
    c = _live_cache
    fresh = (c["vehicles"] is not None and time.monotonic() - c["at"] < LIVE_CACHE_S
             and abs(t - c["t"]) < LIVE_CACHE_S)
    if not fresh:
        vehicles = [v for v in visible(vh.cluster_vehicles(await _fresh_contributions(), t))
                    if vh.reliability(v, t)[1] != "expiré"]
        c.update(at=time.monotonic(), t=t, vehicles=vehicles)
    return [v for v in c["vehicles"] if line_id is None or v.line_id == line_id]


async def _reject(trip: dict, reason: str, info: Optional[dict] = None) -> "PositionResult":
    await _log(trip, "rejected", reason, **(info or {}))
    await db.contributions.delete_one({"trip_id": trip["id"]})
    invalidate_live()
    await db.trips.update_one({"id": trip["id"]}, {"$inc": {"rejected_count": 1}})
    return PositionResult(status="rejected", reason=reason)


# ------------------------ Routes ------------------------
@router.post("/trips", response_model=TripStarted)
async def start_trip(payload: TripStart, user: dict = Depends(current_user),
                     x_app_version: Optional[str] = Header(default=None)):
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
        "rejected_count": 0,
        "confirmed": False,
        "track": [],
    }
    await db.trips.insert_one(trip)
    await _log(trip, "started", None, line=line.data["short_name"] or line.data["long_name"],
               headsign=line.data["directions"][payload.direction]["headsign"],
               reputation=round(trust.reputation(user), 2), app=(x_app_version or "")[:20] or None)
    import notify  # ici : notify dépend du module admin, qui importe celui-ci

    notify.trip_started(line, payload.direction, await db.trips.count_documents({"started_ts": {"$gte": day_start}}))
    headsign = line.data["directions"][payload.direction]["headsign"]
    return TripStarted(id=trip["id"], line_id=line.id, direction=payload.direction, headsign=headsign)


@router.post("/trips/{trip_id}/positions", response_model=PositionResult)
async def post_positions(trip_id: str, trace: network.Trace, user: dict = Depends(current_user)):
    trip = await _active_trip(trip_id, user)
    t = now()
    if t - trip["last_position_ts"] < POSITION_COOLDOWN_S:
        raise HTTPException(429, "Too many updates")
    await db.trips.update_one({"id": trip_id}, {"$set": {"last_position_ts": t}})

    if any(f.mocked for f in trace.fixes):
        # Faux GPS : le trajet s'arrête et la réputation de l'utilisateur chute.
        await trust.penalize_mocked(user["id"])
        await _log(trip, "rejected", trust.REASONS["mocked"], fixes=len(trace.fixes))
        await _end(trip, "mocked")
        return PositionResult(status="rejected", reason=trust.REASONS["mocked"])

    line = network.current().line(trip["line_id"])
    shape = line.shapes[trip["direction"]]
    fixes = [f.to_fix() for f in trace.fixes if abs(f.t - t) <= MAX_CLOCK_SKEW_S]
    last_on_line = trip.get("last_on_line_ts")
    result = match_trace(fixes, shape, line.max_offset_m,
                         allow_detour=last_on_line is not None and t - last_on_line <= DETOUR_MAX_S)
    detour = result.reason == "detour"

    if not result.ok:
        # Plus rien n'est publié dès que la trace n'est plus validée.
        if result.reason == "too_short":
            await _log(trip, "checking", "pas encore assez de points GPS précis", **_trace_info(len(trace.fixes), fixes))
            await db.contributions.delete_one({"trip_id": trip_id})
            invalidate_live()
            return PositionResult(status="checking")
        return await _reject(trip, REASONS[result.reason], _trace_info(len(trace.fixes), fixes, result))

    if not detour:  # en déviation, la position sur la ligne est approximative : pas de contrôle de mouvement
        track = trust.update_track(trip.get("track", []), t, result.along_m)
        await db.trips.update_one({"id": trip_id}, {"$set": {"track": track, "last_on_line_ts": t}})
        problem = trust.motion_problem(track, t, shape.length_m)
        if problem:
            return await _reject(trip, trust.REASONS[problem], _trace_info(len(trace.fixes), fixes, result))

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
            "trusted": trust.is_trusted(user),
        }},
        upsert=True,
    )
    invalidate_live()
    await db.trips.update_one({"id": trip_id}, {"$inc": {"on_route_count": 1}})
    await _log(trip, "detour" if detour else "on_route", DETOUR_REASON if detour else None,
               **_trace_info(len(trace.fixes), fixes, result), trusted=trust.is_trusted(user))
    if not trip.get("on_route_count"):  # première position validée de ce trajet
        import notify

        notify.trip_validated(line, trip["direction"], await db.contributions.count_documents({}))
    # Un autre passager est dans le même véhicule : les trajets se confirment mutuellement.
    for vehicle in vh.cluster_vehicles(await _fresh_contributions(trip["line_id"]), t):
        if trip_id in vehicle.contributors and len(vehicle.contributors) >= 2:
            await db.trips.update_many({"id": {"$in": list(vehicle.contributors)}}, {"$set": {"confirmed": True}})
    return PositionResult(status="on_route", reason=DETOUR_REASON if detour else None,
                          along_m=round(result.along_m), speed_mps=round(result.speed_mps, 1))


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
        alongs = [s["along_m"] for s in direction["stops"]]
        seconds = vh.eta_seconds(vehicle, stop["along_m"], t, vh.typical_speed(line.data), alongs) if stop else None
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
    out = [VehicleOut(**v) for vehicle in await live_vehicles(t, line_id)
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
    for vehicle in await live_vehicles(t):
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
    for vehicle in await live_vehicles(t):
        counts[vehicle.line_id] = counts.get(vehicle.line_id, 0) + 1
    return counts


class LiveSummary(BaseModel):
    sharers: int   # voyageurs qui partagent en ce moment (positions visibles)
    vehicles: int  # véhicules qu'ils font apparaître


@router.get("/live/summary", response_model=LiveSummary)
async def live_summary():
    """Compteur affiché en haut de chaque écran de l'application."""
    t = now()
    shown = await live_vehicles(t)
    return LiveSummary(sharers=sum(len(v.contributors) for v in shown), vehicles=len(shown))


async def setup() -> None:
    await db.trips.create_index("id", unique=True)
    await db.trips.create_index([("user_id", 1), ("started_ts", -1)])
    await db.contributions.create_index("trip_id", unique=True)
    await db.contributions.create_index("line_id")
    # MongoDB supprime lui-même les positions expirées.
    await db.contributions.create_index("expires_at", expireAfterSeconds=0)

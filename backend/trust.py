"""Lutte contre les fausses déclarations (« je suis dans ce bus » alors que non).

Le contrôle de base (matching.py) vérifie que la trace suit la ligne, dans le bon sens, à une vitesse
plausible. Ce module ajoute ce qu'il ne voit pas :
1. mouvement réel : sans au moins 100 m de progression en 4 min, hors terminus, rien n'est publié
   (quelqu'un d'assis près d'une ligne ne crée pas de faux bus arrêté) ;
2. marche : vitesse moyenne de 3 à 7 km/h pendant 3 min sans jamais dépasser 10 km/h = un piéton ;
3. position simulée (application de faux GPS) : trajet arrêté, réputation fortement dégradée ;
4. réputation invisible de chaque utilisateur : confirmée par d'autres passagers, elle monte ; trajets
   refusés, signalés ou simulés, elle baisse. Sous le seuil, ses véhicules ne sont affichés que si un
   utilisateur de confiance les confirme. L'utilisateur n'en sait rien : il n'a pas de raison de recréer
   un identifiant ;
5. signalement « ce véhicule n'existe pas » par les voyageurs : à partir de 2 signalements (3 si le
   véhicule est confirmé par plusieurs passagers), le véhicule est masqué et ses auteurs pénalisés.

- POST /api/vehicles/report : signaler un véhicule affiché qui n'existe pas.
"""
import uuid
from typing import List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from auth import current_user
from database import db

TRACK_KEEP_S = 300
STATIONARY_WINDOW_S = 240
STATIONARY_MIN_PROGRESS_M = 100.0
TERMINUS_MARGIN_M = 300.0      # au terminus, un véhicule attend réellement son départ
WALK_WINDOW_S = 180
WALK_MIN_MPS = 0.8             # ~3 km/h
WALK_MAX_AVG_MPS = 2.0         # ~7 km/h
WALK_MAX_PEAK_MPS = 2.8        # ~10 km/h : un bus le dépasse, même dans les embouteillages
PEAK_CHUNK_S = 25.0

REPUTATION_THRESHOLD = 0.4
# Trajet jamais confirmé : très léger doute, plafonné (on est souvent seul à partager dans son bus),
# donc voyager seul ne fait jamais perdre la confiance.
SOLO_WEIGHT = 0.1
SOLO_MAX_PENALTY = 1.0
REJECTED_WEIGHT = 1.0
REPORTED_WEIGHT = 2.0
MOCKED_WEIGHT = 5.0
REJECTED_TRIP_MIN = 3          # un trajet compte comme « refusé » s'il a eu plus de refus que de validations

REPORT_WINDOW_S = 1800
REPORT_RADIUS_M = 400.0
REPORTS_TO_HIDE = 2
REPORTS_TO_HIDE_CONFIRMED = 3
MAX_REPORTS_PER_DAY = 10

REASONS = {
    "stationary": "le véhicule ne se déplace pas depuis plusieurs minutes",
    "walking": "le déplacement ressemble à de la marche",
    "mocked": "position simulée détectée",
}


# ------------------------ Mouvement ------------------------
def update_track(track: List[List[float]], t: float, along: float) -> List[List[float]]:
    """Historique (heure, position le long du tracé) des 5 dernières minutes d'un trajet."""
    return [p for p in track if t - p[0] <= TRACK_KEEP_S] + [[t, along]]


def _window(track: List[List[float]], t: float, seconds: float) -> Optional[List[List[float]]]:
    """Points des `seconds` dernières secondes, ou None si l'historique ne couvre pas cette durée."""
    if not track or t - track[0][0] < seconds:
        return None
    return [p for p in track if t - p[0] <= seconds]


def motion_problem(track: List[List[float]], t: float, shape_length_m: float) -> Optional[str]:
    """'stationary', 'walking' ou None."""
    window = _window(track, t, STATIONARY_WINDOW_S)
    if window:
        alongs = [a for _, a in window]
        last = alongs[-1]
        at_terminus = last <= TERMINUS_MARGIN_M or last >= shape_length_m - TERMINUS_MARGIN_M
        if max(alongs) - min(alongs) < STATIONARY_MIN_PROGRESS_M and not at_terminus:
            return "stationary"
    window = _window(track, t, WALK_WINDOW_S)
    if window and len(window) >= 3:
        (t0, a0), (t1, a1) = window[0], window[-1]
        average = (a1 - a0) / max(t1 - t0, 1.0)
        peak = 0.0
        for i, (ti, ai) in enumerate(window):
            later = next(((tj, aj) for tj, aj in window[i + 1:] if tj - ti >= PEAK_CHUNK_S), None)
            if later:
                peak = max(peak, (later[1] - ai) / (later[0] - ti))
        if WALK_MIN_MPS <= average <= WALK_MAX_AVG_MPS and peak < WALK_MAX_PEAK_MPS:
            return "walking"
    return None


# ------------------------ Réputation ------------------------
def reputation(user: dict) -> float:
    good = 1.0 + user.get("rep_confirmed", 0)
    bad = (min(SOLO_WEIGHT * user.get("rep_solo", 0), SOLO_MAX_PENALTY) + REJECTED_WEIGHT * user.get("rep_rejected", 0)
           + REPORTED_WEIGHT * user.get("rep_reported", 0) + MOCKED_WEIGHT * user.get("rep_mocked", 0))
    return good / (good + bad)


def is_trusted(user: dict) -> bool:
    return reputation(user) >= REPUTATION_THRESHOLD


async def settle_trip(trip_id: str) -> None:
    """À la fin d'un trajet, une seule fois : met à jour la réputation de son auteur."""
    trip = await db.trips.find_one({"id": trip_id})
    if not trip or trip.get("settled"):
        return
    await db.trips.update_one({"id": trip_id}, {"$set": {"settled": True}})
    inc = {}
    if trip.get("confirmed"):
        inc["rep_confirmed"] = 1
    elif trip.get("on_route_count", 0) > 0:
        inc["rep_solo"] = 1
    rejected = trip.get("rejected_count", 0)
    if rejected >= REJECTED_TRIP_MIN and rejected > trip.get("on_route_count", 0):
        inc["rep_rejected"] = 1
    if inc:
        await db.users.update_one({"id": trip["user_id"]}, {"$inc": inc})


async def penalize_mocked(user_id: str) -> None:
    await db.users.update_one({"id": user_id}, {"$inc": {"rep_mocked": 1}})


# ------------------------ Signalements ------------------------
class ReportIn(BaseModel):
    line_id: str = Field(..., max_length=32)
    direction: int = Field(..., ge=0, le=1)
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)


router = APIRouter(prefix="/api")


def _nearest_vehicle(line, vehicles, direction: int, lat: float, lon: float, t: float) -> Optional[Tuple[float, object]]:
    from geo import haversine_m

    best = None
    for v in vehicles:
        if v.direction != direction:
            continue
        shape = line.shapes[direction]
        vlat, vlon = shape.point_at(min(v.estimated_along(t), shape.length_m))
        dist = haversine_m((lat, lon), (vlat, vlon))
        if dist <= REPORT_RADIUS_M and (best is None or dist < best[0]):
            best = (dist, v)
    return best


@router.post("/vehicles/report")
async def report_vehicle(payload: ReportIn, user: dict = Depends(current_user)):
    import network
    import trips
    import vehicles as vh

    t = trips.now()
    if await db.reports.count_documents({"reporter_id": user["id"], "t": {"$gte": t - 86400}}) >= MAX_REPORTS_PER_DAY:
        raise HTTPException(429, "Too many reports today")
    line = network.current().line(payload.line_id)
    found = _nearest_vehicle(line, trips.visible(vh.cluster_vehicles(await trips._fresh_contributions(line.id), t)),
                             payload.direction, payload.lat, payload.lon, t)
    if not found:
        raise HTTPException(404, "No vehicle here")
    vehicle = found[1]
    trip_ids = list(vehicle.contributors)
    if await db.trips.count_documents({"id": {"$in": trip_ids}, "user_id": user["id"]}):
        raise HTTPException(409, "You are sharing this vehicle")

    already = await db.reports.count_documents(
        {"reporter_id": user["id"], "trip_ids": {"$in": trip_ids}, "t": {"$gte": t - REPORT_WINDOW_S}})
    # Signalement d'un utilisateur peu fiable : accepté sans effet (il ne doit pas le savoir).
    if not already and is_trusted(user):
        await db.reports.insert_one({"id": str(uuid.uuid4()), "reporter_id": user["id"], "line_id": line.id,
                                     "direction": payload.direction, "trip_ids": trip_ids, "t": t})
    reporters = {r["reporter_id"] async for r in db.reports.find(
        {"trip_ids": {"$in": trip_ids}, "t": {"$gte": t - REPORT_WINDOW_S}}, {"reporter_id": 1})}
    needed = REPORTS_TO_HIDE_CONFIRMED if len(trip_ids) >= 2 else REPORTS_TO_HIDE
    if len(reporters) >= needed:
        await hide_trips(trip_ids)
    return {"ok": True}


async def hide_trips(trip_ids: List[str]) -> None:
    """Masque les positions de ces trajets et pénalise leurs auteurs (une fois par trajet)."""
    await db.contributions.update_many({"trip_id": {"$in": trip_ids}}, {"$set": {"hidden": True}})
    async for trip in db.trips.find({"id": {"$in": trip_ids}, "reported": {"$ne": True}}):
        await db.trips.update_one({"id": trip["id"]}, {"$set": {"reported": True}})
        await db.users.update_one({"id": trip["user_id"]}, {"$inc": {"rep_reported": 1}})


async def setup() -> None:
    await db.reports.create_index([("trip_ids", 1), ("t", -1)])
    await db.reports.create_index([("reporter_id", 1), ("t", -1)])

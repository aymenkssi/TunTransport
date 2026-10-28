"""Recherche d'adresses et de lieux (OpenStreetMap / Nominatim) pour l'itinéraire.

- GET /api/places/search?q=  : adresses et lieux en Tunisie correspondant à q.

Règles d'usage de Nominatim respectées : une requête par seconde au plus pour tout le serveur, un
User-Agent qui identifie l'application, pas d'auto-complétion (l'app ne cherche qu'à la validation),
et un cache des réponses. Données © contributeurs OpenStreetMap (ODbL).
"""
import asyncio
import logging
import os
import time
from collections import OrderedDict
from typing import List, Optional

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import routing
from geo import haversine_m

logger = logging.getLogger("tuntransport.places")

NOMINATIM_URL = os.environ.get("NOMINATIM_URL", "https://nominatim.openstreetmap.org/search")
USER_AGENT = "TransTunisLive/1.0 (+https://tuntransport.academy)"
MIN_INTERVAL_S = 1.0
CACHE_SIZE = 2000
CACHE_TTL_S = 7 * 86400
MAX_RESULTS = 6
FETCH_RESULTS = 12
# Le Grand Tunis, où se trouve l'essentiel du réseau : Nominatim y privilégie ses résultats.
VIEWBOX = "9.85,37.10,10.45,36.55"

_cache: "OrderedDict[str, tuple]" = OrderedDict()
_lock = asyncio.Lock()
_last_call = 0.0


class PlaceHit(BaseModel):
    name: str
    detail: str
    lat: float
    lon: float
    kind: Optional[str] = None
    stop_distance_m: Optional[int] = None  # distance au plus proche arrêt du réseau


async def _fetch(q: str) -> list:
    """Appel à Nominatim, espacé d'au moins une seconde du précédent."""
    global _last_call
    async with _lock:
        wait = MIN_INTERVAL_S - (time.monotonic() - _last_call)
        if wait > 0:
            await asyncio.sleep(wait)
        try:
            async with httpx.AsyncClient(timeout=8.0, headers={"User-Agent": USER_AGENT}) as client:
                response = await client.get(NOMINATIM_URL, params={
                    "q": q, "format": "jsonv2", "countrycodes": "tn", "limit": FETCH_RESULTS, "accept-language": "fr",
                    "viewbox": VIEWBOX, "bounded": 0,
                })
        finally:
            _last_call = time.monotonic()
    response.raise_for_status()
    return response.json()


def _to_hit(item: dict) -> Optional[PlaceHit]:
    try:
        lat, lon = float(item["lat"]), float(item["lon"])
    except (KeyError, TypeError, ValueError):
        return None
    parts = [p.strip() for p in item.get("display_name", "").split(",") if p.strip()]
    name = item.get("name") or (parts[0] if parts else "")
    if not name:
        return None
    rest = [p for p in parts if p != name and p != "Tunisie"]
    return PlaceHit(name=name, detail=", ".join(rest[:3]), lat=lat, lon=lon, kind=item.get("type"))


router = APIRouter(prefix="/api")


def _rank(hits: List[PlaceHit]) -> List[PlaceHit]:
    """D'abord les lieux à distance de marche d'un arrêt (dans l'ordre de Nominatim), puis les autres
    du plus proche au plus loin du réseau : un lieu sans arrêt à proximité ne donne pas d'itinéraire."""
    stops = [(s["lat"], s["lon"]) for s in routing.graph().stops.values()]
    ranked = []
    for h in hits:
        nearest = min((haversine_m((h.lat, h.lon), s) for s in stops), default=None)
        ranked.append(h.model_copy(update={"stop_distance_m": None if nearest is None else round(nearest)}))
    reach = routing.MAX_ACCESS_WALK_M
    order = sorted(range(len(ranked)), key=lambda i: (
        (ranked[i].stop_distance_m or 0) > reach, ranked[i].stop_distance_m or 0 if (ranked[i].stop_distance_m or 0) > reach else i))
    return [ranked[i] for i in order][:MAX_RESULTS]


@router.get("/places/search", response_model=List[PlaceHit])
async def search_places(q: str):
    query = " ".join(q.split())[:100]
    if len(query) < 3:
        return []
    key = query.lower()
    cached = _cache.get(key)
    if cached and time.time() - cached[0] < CACHE_TTL_S:
        _cache.move_to_end(key)
        return _rank(cached[1])
    try:
        items = await _fetch(query)
    except Exception:
        logger.exception("Nominatim search failed")
        raise HTTPException(502, "Address search unavailable")
    hits = [h for h in (_to_hit(i) for i in items) if h]
    _cache[key] = (time.time(), hits)
    while len(_cache) > CACHE_SIZE:
        _cache.popitem(last=False)
    return _rank(hits)

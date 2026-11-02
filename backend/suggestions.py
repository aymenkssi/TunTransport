"""Suggestions et signalements envoyés depuis l'application, lus dans la page d'administration
(onglet « Suggestions »).

- POST   /api/suggestions               : un utilisateur envoie une idée, un bug, une erreur de données…
- GET    /api/admin/suggestions         : liste (plus récentes d'abord), filtre ?status=, compteurs.
- PUT    /api/admin/suggestions/{id}    : change le statut (new -> read -> done).
- DELETE /api/admin/suggestions/{id}

Chaque message garde l'adresse IP d'envoi et son pays (api.country.is), pour repérer les abus :
au plus MAX_PER_DAY messages par utilisateur et MAX_PER_IP_PER_DAY par adresse IP.
"""
import ipaddress
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Literal, Optional

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field

import network
from admin import require_admin
from auth import current_user
from database import db

public = APIRouter(prefix="/api")
admin = APIRouter(prefix="/api/admin", dependencies=[Depends(require_admin)])

logger = logging.getLogger("tuntransport.suggestions")
MAX_PER_DAY = 5
MAX_PER_IP_PER_DAY = 10  # plusieurs utilisateurs anonymes peuvent partager une adresse (même Wi-Fi)
COUNTRY_URL = "https://api.country.is/{ip}"
_countries: dict = {}
# idea : idée ; bug : problème dans l'app ; data : erreur de ligne, d'arrêt ou d'horaire ; other : autre
Category = Literal["idea", "bug", "data", "other"]
Status = Literal["new", "read", "done"]


class SuggestionIn(BaseModel):
    category: Category = "idea"
    message: str = Field(..., min_length=5, max_length=1000)
    line_id: Optional[str] = Field(default=None, max_length=32)
    contact: Optional[str] = Field(default=None, max_length=120)  # e-mail ou téléphone, pour répondre


class Suggestion(BaseModel):
    id: str
    category: Category
    message: str
    status: Status
    created_at: str
    line_id: Optional[str] = None
    line_label: Optional[str] = None
    contact: Optional[str] = None
    app_version: Optional[str] = None
    platform: Optional[str] = None
    ip: Optional[str] = None
    country: Optional[str] = None  # code ISO à deux lettres, ex. TN
    same_ip: int = 0               # messages envoyés depuis cette adresse IP (tous)


class SuggestionList(BaseModel):
    items: List[Suggestion]
    counts: dict


class StatusIn(BaseModel):
    status: Status


def _clean(text: Optional[str]) -> Optional[str]:
    if text is None:
        return None
    text = "".join(ch for ch in text if ch.isprintable() or ch == "\n").strip()
    return text or None


async def country_of(ip: Optional[str]) -> Optional[str]:
    """Pays de l'adresse IP, ou None (adresse privée, service injoignable)."""
    try:
        if not ip or not ipaddress.ip_address(ip).is_global:
            return None
    except ValueError:
        return None
    if ip in _countries:
        return _countries[ip]
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.get(COUNTRY_URL.format(ip=ip))
        country = response.json().get("country") if response.status_code == 200 else None
    except Exception:
        logger.warning("Country lookup failed for a suggestion")
        return None
    if len(_countries) > 5000:
        _countries.clear()
    _countries[ip] = country
    return country


@public.post("/suggestions")
async def send_suggestion(
    payload: SuggestionIn,
    request: Request,
    user: dict = Depends(current_user),
    x_app_version: Optional[str] = Header(default=None),
    x_platform: Optional[str] = Header(default=None),
):
    message = _clean(payload.message) or ""
    if len(message) < 5:
        raise HTTPException(422, "Message too short")
    line = network.current().lines.get(payload.line_id) if payload.line_id else None
    if payload.line_id and not line:
        raise HTTPException(404, "Unknown line")
    since = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    if await db.suggestions.count_documents({"user_id": user["id"], "created_at": {"$gte": since}}) >= MAX_PER_DAY:
        raise HTTPException(429, "Too many suggestions today")
    # Adresse du client : le proxy (Caddy ou Traefik) la transmet, uvicorn la lit (--proxy-headers).
    ip = request.client.host if request.client else None
    if ip and await db.suggestions.count_documents({"ip": ip, "created_at": {"$gte": since}}) >= MAX_PER_IP_PER_DAY:
        raise HTTPException(429, "Too many suggestions today")
    await db.suggestions.insert_one({
        "id": str(uuid.uuid4()),
        "user_id": user["id"],
        "category": payload.category,
        "message": message,
        "status": "new",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "line_id": line.id if line else None,
        "line_label": f"{line.data['short_name'] or line.data['long_name']} ({line.data['mode']})" if line else None,
        "contact": _clean(payload.contact),
        "app_version": (x_app_version or "")[:20] or None,
        "platform": (x_platform or "")[:20] or None,
        "ip": ip,
        "country": await country_of(ip),
    })
    return {"ok": True}


@admin.get("/suggestions", response_model=SuggestionList)
async def list_suggestions(status: Optional[Status] = None, limit: int = 200):
    query = {"status": status} if status else {}
    items = await db.suggestions.find(query, {"_id": 0, "user_id": 0}).sort("created_at", -1).to_list(min(limit, 500))
    counts = {s: await db.suggestions.count_documents({"status": s}) for s in ("new", "read", "done")}
    per_ip = {ip: await db.suggestions.count_documents({"ip": ip}) for ip in {i.get("ip") for i in items} if ip}
    return SuggestionList(items=[Suggestion(**i, same_ip=per_ip.get(i.get("ip"), 0)) for i in items], counts=counts)


@admin.put("/suggestions/{suggestion_id}", response_model=Suggestion)
async def set_status(suggestion_id: str, payload: StatusIn):
    res = await db.suggestions.update_one({"id": suggestion_id}, {"$set": {"status": payload.status}})
    if res.matched_count == 0:
        raise HTTPException(404, "Unknown suggestion")
    return Suggestion(**await db.suggestions.find_one({"id": suggestion_id}, {"_id": 0, "user_id": 0}))


@admin.delete("/suggestions/{suggestion_id}")
async def delete_suggestion(suggestion_id: str):
    res = await db.suggestions.delete_one({"id": suggestion_id})
    if res.deleted_count == 0:
        raise HTTPException(404, "Unknown suggestion")
    return {"deleted": suggestion_id}


async def setup():
    await db.suggestions.create_index("id", unique=True)
    await db.suggestions.create_index([("user_id", 1), ("created_at", -1)])
    await db.suggestions.create_index([("status", 1), ("created_at", -1)])
    await db.suggestions.create_index([("ip", 1), ("created_at", -1)])

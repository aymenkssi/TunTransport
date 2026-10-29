"""Suggestions et signalements envoyés depuis l'application, lus dans la page d'administration
(onglet « Suggestions »).

- POST   /api/suggestions               : un utilisateur envoie une idée, un bug, une erreur de données…
- GET    /api/admin/suggestions         : liste (plus récentes d'abord), filtre ?status=, compteurs.
- PUT    /api/admin/suggestions/{id}    : change le statut (new -> read -> done).
- DELETE /api/admin/suggestions/{id}
"""
import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

import network
from admin import require_admin
from auth import current_user
from database import db

public = APIRouter(prefix="/api")
admin = APIRouter(prefix="/api/admin", dependencies=[Depends(require_admin)])

MAX_PER_DAY = 5
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


@public.post("/suggestions")
async def send_suggestion(
    payload: SuggestionIn,
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
    })
    return {"ok": True}


@admin.get("/suggestions", response_model=SuggestionList)
async def list_suggestions(status: Optional[Status] = None, limit: int = 200):
    query = {"status": status} if status else {}
    items = await db.suggestions.find(query, {"_id": 0, "user_id": 0}).sort("created_at", -1).to_list(min(limit, 500))
    counts = {s: await db.suggestions.count_documents({"status": s}) for s in ("new", "read", "done")}
    return SuggestionList(items=[Suggestion(**i) for i in items], counts=counts)


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

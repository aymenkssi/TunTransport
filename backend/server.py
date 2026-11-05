"""TunTransport API : utilisateurs anonymes, réseau de lignes, trajets partagés et véhicules en direct."""
import asyncio
import logging
import os
import secrets
import time
import uuid

from fastapi import APIRouter, Depends, FastAPI
from typing import Optional

from pydantic import BaseModel, Field
from starlette.middleware.cors import CORSMiddleware

import admin
import custom_lines
import geocoder
import network
import notify
import places
import roads
import suggestions
import routing
import trips
import trust
from auth import current_user, hash_token
from database import client, db

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("tuntransport")

app = FastAPI(title="TunTransport API")
api = APIRouter(prefix="/api")


class UserCreated(BaseModel):
    id: str
    token: str


@api.get("/")
async def root():
    return {"message": "TunTransport API online", "lines": len(network.current().lines)}


VERSION_RE = r"^\d{1,3}\.\d{1,3}\.\d{1,3}$"


class AppVersion(BaseModel):
    latest: Optional[str] = Field(default=None, pattern=VERSION_RE)   # dernière version sur Google Play
    minimum: Optional[str] = Field(default=None, pattern=VERSION_RE)  # en dessous : mise à jour obligatoire


@api.get("/app/version", response_model=AppVersion)
async def app_version():
    """Version publiée, réglée dans l'admin : l'application propose la mise à jour si elle est plus ancienne."""
    doc = await db.settings.find_one({"id": "app_version"}, {"_id": 0, "id": 0}) or {}
    return AppVersion(**doc)


@admin.admin.put("/app-version", response_model=AppVersion)
async def set_app_version(payload: AppVersion):
    await db.settings.update_one({"id": "app_version"}, {"$set": {"id": "app_version", **payload.model_dump()}}, upsert=True)
    return payload


@api.post("/users", response_model=UserCreated)
async def create_user():
    """Utilisateur anonyme : aucun nom, aucun e-mail. Le jeton reste sur le téléphone."""
    token = secrets.token_urlsafe(32)
    user = {"id": str(uuid.uuid4()), "token_hash": hash_token(token), "created_ts": time.time()}
    await db.users.insert_one(user)
    return UserCreated(id=user["id"], token=token)


@api.post("/users/me/delete")
async def delete_me(user: dict = Depends(current_user)):
    """Supprime l'utilisateur, ses trajets et sa position en cours (bouton « Supprimer mes données »)."""
    trip_ids = [t["id"] async for t in db.trips.find({"user_id": user["id"]}, {"id": 1})]
    await db.contributions.delete_many({"trip_id": {"$in": trip_ids}})
    trips.invalidate_live()
    await db.trips.delete_many({"user_id": user["id"]})
    await db.suggestions.delete_many({"user_id": user["id"]})
    await db.users.delete_one({"id": user["id"]})
    return {"ok": True}


app.include_router(api)
app.include_router(network.router)
app.include_router(trips.router)
app.include_router(routing.router)
app.include_router(places.router)
app.include_router(roads.router)
app.include_router(suggestions.public)
app.include_router(suggestions.admin)
app.include_router(custom_lines.admin)
app.include_router(notify.admin)
app.include_router(trust.router)
app.include_router(admin.admin)
app.include_router(admin.admin_page)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-App-Version", "X-Platform"],
)


# L'API tourne avec plusieurs processus (API_WORKERS) : chacun garde le réseau en mémoire. Toutes
# les SYNC_EVERY_S secondes, il recharge ce qu'un autre processus ou un réimport a changé.
SYNC_EVERY_S = 15
_sync_task: Optional[asyncio.Task] = None


def _mtime(var: str, default) -> float:
    try:
        return os.stat(os.environ.get(var) or default).st_mtime
    except OSError:
        return 0.0


async def _sync_loop() -> None:
    seen = {"network": _mtime("NETWORK_FILE", network.DEFAULT_FILE), "places": _mtime("PLACES_FILE", geocoder.DEFAULT_FILE)}
    while True:
        await asyncio.sleep(SYNC_EVERY_S)
        try:
            current = _mtime("NETWORK_FILE", network.DEFAULT_FILE)
            if current != seen["network"]:
                seen["network"] = current
                network.load()
                await custom_lines.apply()
            current = _mtime("PLACES_FILE", geocoder.DEFAULT_FILE)
            if current != seen["places"]:
                seen["places"] = current
                geocoder.load()
            await custom_lines.sync()
            await trips.close_silent_trips()
        except Exception:
            logger.exception("Worker sync failed")


@app.on_event("startup")
async def startup():
    global _sync_task
    network.load()
    geocoder.load()
    await db.users.create_index("id", unique=True)
    await db.users.create_index("token_hash", unique=True)
    await trips.setup()
    await trust.setup()
    await suggestions.setup()
    await custom_lines.setup()
    _sync_task = asyncio.create_task(_sync_loop())


@app.on_event("shutdown")
async def shutdown_db_client():
    if _sync_task:
        _sync_task.cancel()
    client.close()

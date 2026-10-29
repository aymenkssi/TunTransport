"""TunTransport API : utilisateurs anonymes, réseau de lignes, trajets partagés et véhicules en direct."""
import logging
import os
import secrets
import time
import uuid

from fastapi import APIRouter, Depends, FastAPI
from pydantic import BaseModel
from starlette.middleware.cors import CORSMiddleware

import admin
import geocoder
import network
import places
import roads
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
    await db.trips.delete_many({"user_id": user["id"]})
    await db.users.delete_one({"id": user["id"]})
    return {"ok": True}


app.include_router(api)
app.include_router(network.router)
app.include_router(trips.router)
app.include_router(routing.router)
app.include_router(places.router)
app.include_router(roads.router)
app.include_router(trust.router)
app.include_router(admin.admin)
app.include_router(admin.admin_page)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.on_event("startup")
async def startup():
    network.load()
    geocoder.load()
    await db.users.create_index("id", unique=True)
    await db.users.create_index("token_hash", unique=True)
    await trips.setup()
    await trust.setup()


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()

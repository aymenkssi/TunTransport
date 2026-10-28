"""Utilisateurs anonymes : un jeton secret par appareil, seul son SHA-256 est stocké."""
import hashlib
from typing import Optional

from fastapi import Header, HTTPException

from database import db


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def current_user(authorization: Optional[str] = Header(default=None)) -> dict:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Missing user token")
    user = await db.users.find_one({"token_hash": hash_token(authorization[7:].strip())})
    if not user:
        raise HTTPException(401, "Unknown user token")
    return user

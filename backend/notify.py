"""Notifications Telegram pour l'administrateur (onglet « Notifications » de la page d'admin).

Un bot Telegram (créé avec @BotFather) envoie un message quand un voyageur commence à partager un
trajet et, au choix, quand ce trajet est validé sur la ligne. Les réglages sont dans MongoDB
(collection settings, id « telegram ») ; le jeton du bot n'est jamais renvoyé en entier.

- GET  /api/admin/telegram        : réglages (jeton masqué).
- PUT  /api/admin/telegram        : enregistre (jeton vide = garder l'actuel).
- POST /api/admin/telegram/test   : envoie un message d'essai.
- GET  /api/admin/telegram/chats  : conversations récentes du bot, pour trouver le « chat ID ».
"""
import asyncio
import html
import logging
import time
from collections import deque
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from admin import require_admin
from database import db

logger = logging.getLogger("tuntransport.notify")
admin = APIRouter(prefix="/api/admin", dependencies=[Depends(require_admin)])

API = "https://api.telegram.org/bot{token}/{method}"
TUNIS = ZoneInfo("Africa/Tunis")
MAX_PER_HOUR = 60  # au-delà, les messages sont sautés (Telegram limite aussi les envois)
_sent: deque = deque()
_tasks: set = set()

MODE_ICONS = {"bus": "🚌", "metro": "🚋", "train": "🚆", "rfr": "🚆"}


class TelegramSettings(BaseModel):
    enabled: bool = False
    bot_token: Optional[str] = Field(default=None, max_length=100)  # vide : garder le jeton enregistré
    chat_id: Optional[str] = Field(default=None, max_length=40)
    on_trip_start: bool = True      # un voyageur commence à partager
    on_trip_validated: bool = False  # sa position est validée sur la ligne


async def _settings() -> dict:
    return await db.settings.find_one({"id": "telegram"}, {"_id": 0}) or {}


def _mask(token: Optional[str]) -> Optional[str]:
    return f"{token[:6]}…{token[-4:]}" if token and len(token) > 12 else None


async def _call(token: str, method: str, **params) -> dict:
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(API.format(token=token, method=method), json=params)
    data = response.json()
    if not data.get("ok"):
        raise RuntimeError(data.get("description") or f"HTTP {response.status_code}")
    return data["result"]


async def _send(text: str, settings: dict) -> None:
    now = time.monotonic()
    while _sent and now - _sent[0] > 3600:
        _sent.popleft()
    if len(_sent) >= MAX_PER_HOUR:
        logger.warning("Telegram: more than %d messages this hour, skipped", MAX_PER_HOUR)
        return
    _sent.append(now)
    try:
        await _call(settings["bot_token"], "sendMessage", chat_id=settings["chat_id"], text=text,
                    parse_mode="HTML", disable_web_page_preview=True)
    except Exception as e:
        logger.warning("Telegram notification failed: %s", e)


async def _notify(event: str, text: str) -> None:
    settings = await _settings()
    if settings.get("enabled") and settings.get("bot_token") and settings.get("chat_id") and settings.get(event):
        await _send(text, settings)


def _background(coro) -> None:
    """Envoi sans faire attendre le voyageur."""
    task = asyncio.create_task(coro)
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


def _line_text(line, direction: int) -> str:
    d = line.data
    label = html.escape(d["short_name"] or d["long_name"])
    headsign = html.escape(d["directions"][direction]["headsign"])
    return f"{MODE_ICONS.get(d['mode'], '🚌')} <b>{label}</b> ({html.escape(d['mode'])}) → {headsign}"


def trip_started(line, direction: int, trips_today: int) -> None:
    at = datetime.now(TUNIS).strftime("%H:%M")
    text = f"📍 Nouveau partage à {at}\n{_line_text(line, direction)}\n{html.escape(line.data['long_name'])}\nPartages aujourd'hui : {trips_today}"
    _background(_notify("on_trip_start", text))


def trip_validated(line, direction: int, sharers: int) -> None:
    text = f"✅ Trajet validé sur la ligne\n{_line_text(line, direction)}\nVoyageurs en direct : {sharers}"
    _background(_notify("on_trip_validated", text))


# ------------------------ Admin ------------------------
@admin.get("/telegram")
async def get_telegram():
    s = await _settings()
    return {
        "enabled": s.get("enabled", False), "chat_id": s.get("chat_id"), "token_hint": _mask(s.get("bot_token")),
        "on_trip_start": s.get("on_trip_start", True), "on_trip_validated": s.get("on_trip_validated", False),
    }


@admin.put("/telegram")
async def set_telegram(payload: TelegramSettings):
    current = await _settings()
    values = payload.model_dump()
    values["bot_token"] = (payload.bot_token or "").strip() or current.get("bot_token")
    values["chat_id"] = (payload.chat_id or "").strip() or None
    if values["enabled"] and not (values["bot_token"] and values["chat_id"]):
        raise HTTPException(422, "Renseignez le jeton du bot et le chat ID pour activer les notifications")
    await db.settings.update_one({"id": "telegram"}, {"$set": {"id": "telegram", **values}}, upsert=True)
    return await get_telegram()


@admin.post("/telegram/test")
async def test_telegram():
    s = await _settings()
    if not (s.get("bot_token") and s.get("chat_id")):
        raise HTTPException(422, "Enregistrez d'abord le jeton du bot et le chat ID")
    try:
        await _call(s["bot_token"], "sendMessage", chat_id=s["chat_id"],
                    text="✅ TransTunisLive : les notifications Telegram fonctionnent.")
    except Exception as e:
        raise HTTPException(502, f"Telegram : {e}")
    return {"ok": True}


@admin.get("/telegram/chats")
async def telegram_chats(bot_token: Optional[str] = None):
    """Conversations où le bot a reçu un message (envoyez-lui /start d'abord)."""
    token = (bot_token or "").strip() or (await _settings()).get("bot_token")
    if not token:
        raise HTTPException(422, "Indiquez le jeton du bot")
    try:
        updates = await _call(token, "getUpdates", limit=100)
    except Exception as e:
        raise HTTPException(502, f"Telegram : {e}")
    chats = {}
    for u in updates:
        chat = (u.get("message") or u.get("channel_post") or u.get("my_chat_member") or {}).get("chat")
        if chat:
            name = chat.get("title") or " ".join(x for x in (chat.get("first_name"), chat.get("last_name")) if x) or chat.get("username")
            chats[str(chat["id"])] = {"id": str(chat["id"]), "name": name, "type": chat.get("type")}
    return list(chats.values())

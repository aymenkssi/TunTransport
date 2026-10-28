"""Page d'administration (/admin) et ses API, protégées par le jeton ADMIN_TOKEN.

- GET  /api/admin/stats            : utilisateurs, trajets, lignes les plus partagées, trajets par jour.
- GET  /api/admin/live             : véhicules en direct sur tout le réseau.
- GET  /api/admin/network          : source, date d'import et nombre de lignes par mode.
- POST /api/admin/network/reload   : recharge NETWORK_FILE après un nouvel import, sans redémarrer.
"""
import os
import secrets
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import HTMLResponse

import network
import trips
import trust
import vehicles as vh
from database import db


async def require_admin(authorization: Optional[str] = Header(default=None)) -> None:
    expected = os.environ.get("ADMIN_TOKEN", "")
    if len(expected) < 16:
        raise HTTPException(503, "Admin disabled: set ADMIN_TOKEN (16+ characters)")
    given = authorization[7:].strip() if authorization and authorization.lower().startswith("bearer ") else ""
    if not secrets.compare_digest(given.encode(), expected.encode()):
        raise HTTPException(401, "Invalid admin token")


admin = APIRouter(prefix="/api/admin", dependencies=[Depends(require_admin)])
admin_page = APIRouter()
ADMIN_HTML = Path(__file__).parent / "admin.html"
STATS_DAYS = 14


@admin_page.get("/admin", response_class=HTMLResponse, include_in_schema=False)
async def page():
    return HTMLResponse(ADMIN_HTML.read_text(encoding="utf-8"), headers={"Cache-Control": "no-store"})


def _line_label(line_id: str) -> str:
    line = network.current().lines.get(line_id)
    if not line:
        return line_id
    return f"{line.data['short_name'] or line.data['long_name']} ({line.data['mode']})"


@admin.get("/stats")
async def stats():
    t = trips.now()
    since = t - STATS_DAYS * 86400
    recent = await db.trips.find({"started_ts": {"$gte": since}}, {"_id": 0, "user_id": 1, "line_id": 1, "started_ts": 1,
                                                                   "on_route_count": 1, "rejected_count": 1}).to_list(200_000)
    today = datetime.fromtimestamp(t, timezone.utc).date()
    days = [(today - timedelta(days=i)).isoformat() for i in range(STATS_DAYS - 1, -1, -1)]
    per_day = Counter(datetime.fromtimestamp(r["started_ts"], timezone.utc).date().isoformat() for r in recent)
    week = [r for r in recent if r["started_ts"] >= t - 7 * 86400]
    validated = [r for r in week if r.get("on_route_count", 0) > 0]
    top = Counter(r["line_id"] for r in validated).most_common(10)
    return {
        "users": await db.users.count_documents({}),
        "active_trips": await db.trips.count_documents({"ended_at": None, "started_ts": {"$gte": t - trips.MAX_TRIP_S}}),
        "trips_today": per_day.get(today.isoformat(), 0),
        "trips_7d": len(week),
        "validated_7d": len(validated),
        "contributors_7d": len({r["user_id"] for r in validated}),
        "per_day": [{"day": d, "trips": per_day.get(d, 0)} for d in days],
        "top_lines": [{"line_id": lid, "label": _line_label(lid), "trips": n} for lid, n in top],
        "reports_7d": await db.reports.count_documents({"t": {"$gte": t - 7 * 86400}}),
        "hidden_trips_7d": await db.trips.count_documents({"reported": True, "started_ts": {"$gte": t - 7 * 86400}}),
        "rejected_trips_7d": sum(1 for r in week if r.get("rejected_count", 0) > r.get("on_route_count", 0)),
        "low_reputation_users": sum([1 async for u in db.users.find(
            {"$or": [{f"rep_{k}": {"$gt": 0}} for k in ("solo", "rejected", "reported", "mocked")]}) if not trust.is_trusted(u)]),
    }


@admin.get("/live")
async def live():
    t = trips.now()
    rows = []
    for vehicle in vh.cluster_vehicles(await trips._fresh_contributions(), t):
        score, status = vh.reliability(vehicle, t)
        line = network.current().lines.get(vehicle.line_id)
        rows.append({
            "line_id": vehicle.line_id,
            "label": _line_label(vehicle.line_id),
            "headsign": line.data["directions"][vehicle.direction]["headsign"] if line else "",
            "along_m": round(vehicle.estimated_along(t)),
            "speed_kmh": round(vehicle.speed_mps * 3.6),
            "confirmations": len(vehicle.contributors),
            "age_s": round(t - vehicle.last_update),
            "reliability": round(score, 2),
            "status": status,
            "visible": vehicle.trusted > 0,  # masqué : aucun passager de confiance
        })
    rows.sort(key=lambda r: (r["label"], r["along_m"]))
    return rows


@admin.get("/network")
async def network_info():
    net = network.current()
    return {
        "source": net.source,
        "generated": net.generated,
        "lines": len(net.lines),
        "by_mode": dict(Counter(line.data["mode"] for line in net.lines.values())),
        "stops_only_shapes": sum(1 for line in net.lines.values() if line.data.get("shape_source") != "tunismapper"),
    }


@admin.post("/network/reload")
async def reload_network():
    network.load()
    return await network_info()

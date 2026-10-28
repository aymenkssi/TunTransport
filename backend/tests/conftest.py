import json
import os
import sys
from pathlib import Path

import mongomock_motor
import motor.motor_asyncio
import pytest

# MongoDB en mémoire ; doit être en place avant l'import de server.py.
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "tuntransport_test")
motor.motor_asyncio.AsyncIOMotorClient = mongomock_motor.AsyncMongoMockClient
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import server  # noqa: E402
import trips  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ADMIN_TOKEN = "test-admin-token-0123456789"
ADMIN = {"Authorization": f"Bearer {ADMIN_TOKEN}"}

LAT = 36.80                 # Tunis
M_PER_DEG_LON = 89_150.0    # à cette latitude, approximativement
EAST = [[LAT, 10.15], [LAT, 10.17], [LAT, 10.20]]
T0 = 1_800_000_000.0


def _direction(headsign, shape, stops):
    return {"headsign": headsign, "shape": shape, "stops": stops}


# L1 : tracé relevé est-ouest (~4,5 km), arrêts tous les ~1,8 km.
# L2 : arrêts seulement, parallèle à ~550 m au nord.
NETWORK = {
    "source": "test",
    "generated": "2026-10-28",
    "lines": [
        {
            "id": "L1", "mode": "bus", "short_name": "1", "long_name": "Ouest - Est", "color": "#E30613",
            "operator": "Bus TRANSTU", "shape_source": "tunismapper",
            "stops": [
                {"id": "s1", "name": "Ouest", "lat": LAT, "lon": 10.15},
                {"id": "s2", "name": "Centre", "lat": LAT, "lon": 10.17},
                {"id": "s3", "name": "Est", "lat": LAT, "lon": 10.20},
            ],
            "directions": [
                _direction("Est", EAST, [{"id": "s1", "along_m": 0}, {"id": "s2", "along_m": 1783}, {"id": "s3", "along_m": 4458}]),
                _direction("Ouest", EAST[::-1], [{"id": "s3", "along_m": 0}, {"id": "s2", "along_m": 2675}, {"id": "s1", "along_m": 4458}]),
            ],
            "timetable": {"s1": {"Est": ["06:00", "06:30"]}},
        },
        {
            "id": "L2", "mode": "metro", "short_name": "2", "long_name": "Nord", "color": "#0071E3",
            "operator": "Métro TRANSTU", "shape_source": "stops",
            "stops": [{"id": "n1", "name": "N1", "lat": LAT + 0.005, "lon": 10.15}, {"id": "n2", "name": "N2", "lat": LAT + 0.005, "lon": 10.20}],
            "directions": [
                _direction("N2", [[LAT + 0.005, 10.15], [LAT + 0.005, 10.20]], [{"id": "n1", "along_m": 0}, {"id": "n2", "along_m": 4458}]),
                _direction("N1", [[LAT + 0.005, 10.20], [LAT + 0.005, 10.15]], [{"id": "n2", "along_m": 0}, {"id": "n1", "along_m": 4458}]),
            ],
        },
    ],
}


class Clock:
    def __init__(self):
        self.t = T0

    def advance(self, seconds):
        self.t += seconds


@pytest.fixture
def clock(monkeypatch):
    c = Clock()
    monkeypatch.setattr(trips, "now", lambda: c.t)
    return c


@pytest.fixture
def api(monkeypatch, tmp_path, clock):
    path = tmp_path / "network.json"
    path.write_text(json.dumps(NETWORK), encoding="utf-8")
    monkeypatch.setenv("NETWORK_FILE", str(path))
    monkeypatch.setenv("ADMIN_TOKEN", ADMIN_TOKEN)
    monkeypatch.setattr(trips, "POSITION_COOLDOWN_S", 0)
    with TestClient(server.app) as c:
        for name in ("users", "trips", "contributions"):
            c.portal.call(server.db[name].delete_many, {})
        yield c


@pytest.fixture
def user(api):
    def make():
        r = api.post("/api/users")
        assert r.status_code == 200, r.text
        return {"Authorization": f"Bearer {r.json()['token']}"}

    return make


def trace(clock, start_lon=10.16, speed_mps=8.0, lat=LAT, n=6, step_s=10, accuracy=10.0):
    """Trace GPS se terminant à l'instant courant, d'ouest en est si speed_mps > 0."""
    t_end = clock.t
    return [
        {"t": t_end - (n - 1 - i) * step_s, "lat": lat,
         "lon": start_lon + speed_mps * i * step_s / M_PER_DEG_LON, "accuracy": accuracy}
        for i in range(n)
    ]


def ride(api, clock, headers, line_id="L1", direction=0, **trace_kwargs):
    """Démarre un trajet et envoie une trace ; renvoie (id du trajet, réponse positions)."""
    trip = api.post("/api/trips", json={"line_id": line_id, "direction": direction}, headers=headers)
    assert trip.status_code == 200, trip.text
    trip_id = trip.json()["id"]
    r = api.post(f"/api/trips/{trip_id}/positions", json={"fixes": trace(clock, **trace_kwargs)}, headers=headers)
    return trip_id, r

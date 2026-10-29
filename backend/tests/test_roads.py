"""Itinéraires en voiture et à pied (OSRM simulé)."""
from conftest import LAT

import roads

OSRM_ROUTE = {
    "code": "Ok",
    "routes": [{
        "distance": 2450.4, "duration": 312.6,
        "geometry": {"type": "LineString", "coordinates": [[10.15, LAT], [10.16, LAT], [10.17, LAT], [10.17, LAT + 0.01]]},
        "legs": [{"steps": [
            {"distance": 900, "duration": 110, "name": "Avenue Habib Bourguiba", "maneuver": {"type": "depart"}},
            {"distance": 1000, "duration": 120, "name": "Rue de Marseille", "maneuver": {"type": "turn", "modifier": "left"}},
            {"distance": 550, "duration": 82, "name": "", "maneuver": {"type": "roundabout", "modifier": "right", "exit": 2}},
            {"distance": 0, "duration": 0, "name": "", "maneuver": {"type": "arrive"}},
        ]}],
    }],
}


def fake_osrm(monkeypatch, response=OSRM_ROUTE):
    calls = []

    async def fetch(mode, a, b):
        calls.append((mode, a, b))
        if isinstance(response, Exception):
            raise response
        return response

    monkeypatch.setattr(roads, "_fetch", fetch)
    roads._cache.clear()
    return calls


def road(api, mode, **extra):
    return api.post("/api/routes/road", json={"origin": {"stop_id": "s1"}, "destination": {"lat": LAT + 0.01, "lon": 10.17, "name": "Bureau"},
                                              "mode": mode, **extra})


def test_car_route_with_french_instructions(api, monkeypatch, clock):
    calls = fake_osrm(monkeypatch)
    r = road(api, "car").json()
    assert (r["mode"], r["distance_m"], r["duration_s"]) == ("car", 2450, 313)
    assert [s["instruction"] for s in r["steps"]] == [
        "Partez sur \u2068Avenue Habib Bourguiba\u2069", "Tournez à gauche sur \u2068Rue de Marseille\u2069",
        "Au rond-point, prenez la 2e sortie", "Vous êtes arrivé"]
    assert r["path"][0] == [LAT, 10.15] and r["path"][-1] == [round(LAT + 0.01, 6), 10.17]
    assert len(r["path"]) == 3  # le point intermédiaire aligné est retiré par la simplification
    assert calls == [("car", (LAT, 10.15), (round(LAT + 0.01, 5), 10.17))]


def test_foot_route_is_cached(api, monkeypatch):
    calls = fake_osrm(monkeypatch)
    assert road(api, "foot").json()["mode"] == "foot"
    road(api, "foot")
    assert len(calls) == 1


def test_errors(api, monkeypatch):
    fake_osrm(monkeypatch, RuntimeError("down"))
    assert road(api, "car").status_code == 502
    fake_osrm(monkeypatch, {"code": "NoRoute", "routes": []})
    assert road(api, "car").status_code == 404
    assert road(api, "bike").status_code == 422


def test_departure_time(api, monkeypatch, clock):
    fake_osrm(monkeypatch)
    r = road(api, "car", depart_at=clock.t + 3600).json()
    assert r["depart"] != road(api, "car").json()["depart"]

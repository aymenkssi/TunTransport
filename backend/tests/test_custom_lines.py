import custom_lines
from conftest import ADMIN

STOPS = [
    {"name": "Départ", "lat": 36.800, "lon": 10.150},
    {"name": "Milieu", "lat": 36.800, "lon": 10.170},
    {"name": "Arrivée", "lat": 36.800, "lon": 10.200},
]


def spec(**over):
    return {"mode": "bus", "short_name": "999", "long_name": "Départ - Arrivée", "stops": STOPS, **over}


async def no_osrm(stops):
    raise RuntimeError("offline")


def test_admin_adds_a_line_served_to_the_app(api, monkeypatch):
    monkeypatch.setattr(custom_lines, "_road_shapes", no_osrm)  # pas d'internet : tracé en ligne droite
    assert api.post("/api/admin/custom-lines", json=spec()).status_code == 401
    line = api.post("/api/admin/custom-lines", json=spec(first_departure="06:00", last_departure="07:00", headway_min=20), headers=ADMIN).json()
    assert line["id"] == "x999" and line["shape_source"] == "manual"
    assert [d["headsign"] for d in line["directions"]] == ["Arrivée", "Départ"]
    assert line["timetable"]["x999-0"]["Arrivée"] == ["06:00", "06:20", "06:40", "07:00"]
    served = api.get("/api/lines/x999").json()
    assert [s["name"] for s in served["stops"]] == ["Départ", "Milieu", "Arrivée"]
    assert any(l["id"] == "x999" for l in api.get("/api/lines").json())

    updated = api.put("/api/admin/custom-lines/x999", json=spec(long_name="Nouveau nom"), headers=ADMIN).json()
    assert updated["long_name"] == "Nouveau nom" and api.get("/api/lines/x999").json()["long_name"] == "Nouveau nom"
    rows = api.get("/api/admin/custom-lines", headers=ADMIN).json()
    assert [r["id"] for r in rows] == ["x999"] and rows[0]["origin"] == "admin"

    assert api.delete("/api/admin/custom-lines/x999", headers=ADMIN).json() == {"ok": True}
    assert api.get("/api/lines/x999").status_code == 404


def test_imported_lines_cannot_be_edited_but_survive_a_reload(api, monkeypatch):
    monkeypatch.setattr(custom_lines, "_road_shapes", no_osrm)
    assert api.put("/api/admin/custom-lines/L1", json=spec(), headers=ADMIN).status_code == 400
    api.post("/api/admin/custom-lines", json=spec(), headers=ADMIN)
    api.post("/api/admin/network/reload", headers=ADMIN)
    assert api.get("/api/lines/x999").status_code == 200


def test_invalid_line_is_refused(api):
    assert api.post("/api/admin/custom-lines", json=spec(stops=STOPS[:1]), headers=ADMIN).status_code == 422
    assert api.post("/api/admin/custom-lines", json=spec(color="red"), headers=ADMIN).status_code == 422


def test_other_workers_pick_up_changes(api, monkeypatch):
    """Un autre processus de l'API a ajouté une ligne : sync() la charge ici."""
    import server

    monkeypatch.setattr(custom_lines, "_road_shapes", no_osrm)
    api.post("/api/admin/custom-lines", json=spec(), headers=ADMIN)
    custom_lines.network.set_custom([], set())  # ce processus ne la voit plus…
    assert api.get("/api/lines/x999").status_code == 404
    api.portal.call(custom_lines.sync)  # …même version : rien à faire
    assert api.get("/api/lines/x999").status_code == 404
    api.portal.call(server.db.settings.update_one, {"id": "custom_lines"}, {"$inc": {"version": 1}})
    api.portal.call(custom_lines.sync)  # un autre processus a modifié les lignes
    assert api.get("/api/lines/x999").status_code == 200

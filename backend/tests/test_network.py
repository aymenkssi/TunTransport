from conftest import trace


def test_root_reports_lines(api):
    assert api.get("/api/").json() == {"message": "TunTransport API online", "lines": 2}


def test_list_lines_without_heavy_fields(api):
    lines = api.get("/api/lines").json()
    assert [line["id"] for line in lines] == ["L1", "L2"]
    assert lines[0] == {"id": "L1", "mode": "bus", "short_name": "1", "long_name": "Ouest - Est",
                        "color": "#E30613", "operator": "Bus TRANSTU"}


def test_line_detail(api):
    line = api.get("/api/lines/L1").json()
    assert [d["headsign"] for d in line["directions"]] == ["Est", "Ouest"]
    assert line["timetable"]["s1"]["Est"] == ["06:00", "06:30"]
    assert api.get("/api/lines/nope").status_code == 404


def test_suggest_matches_line_and_direction(api, clock):
    assert api.post("/api/lines/suggest", json={"fixes": trace(clock)}).json() == [
        {"line_id": "L1", "direction": 0, "mean_offset_m": 0.0}]
    westward = api.post("/api/lines/suggest", json={"fixes": trace(clock, start_lon=10.18, speed_mps=-8)}).json()
    assert [(s["line_id"], s["direction"]) for s in westward] == [("L1", 1)]


def test_suggest_stops_only_line_has_wider_tolerance(api, clock):
    # ~110 m au sud de L2 (tracé reconstruit à partir des arrêts) et ~440 m au nord de L1.
    r = api.post("/api/lines/suggest", json={"fixes": trace(clock, lat=36.804)}).json()
    assert [(s["line_id"], s["direction"]) for s in r] == [("L2", 0)]


def test_missing_network_keeps_api_online(api, monkeypatch, tmp_path):
    import network
    monkeypatch.setenv("NETWORK_FILE", str(tmp_path / "absent.json"))
    network.load()
    assert api.get("/api/lines").json() == []
    assert api.get("/api/").status_code == 200

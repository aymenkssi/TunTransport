from conftest import LAT, ride, trace

import server


def vehicles(api, line_id="L1", **params):
    r = api.get(f"/api/lines/{line_id}/vehicles", params=params)
    assert r.status_code == 200, r.text
    return r.json()


def test_trip_requires_user_and_valid_line(api, user):
    assert api.post("/api/trips", json={"line_id": "L1", "direction": 0}).status_code == 401
    h = user()
    assert api.post("/api/trips", json={"line_id": "nope", "direction": 0}, headers=h).status_code == 404
    assert api.post("/api/trips", json={"line_id": "L1", "direction": 2}, headers=h).status_code == 422
    r = api.post("/api/trips", json={"line_id": "L1", "direction": 1}, headers=h).json()
    assert (r["line_id"], r["direction"], r["headsign"]) == ("L1", 1, "Ouest")


def test_short_trace_is_checking_and_not_published(api, clock, user):
    _, r = ride(api, clock, user(), n=2)
    assert r.json() == {"status": "checking", "reason": None, "along_m": None, "speed_mps": None}
    assert vehicles(api) == []


def test_validated_passenger_publishes_vehicle(api, clock, user):
    _, r = ride(api, clock, user())
    body = r.json()
    assert body["status"] == "on_route" and abs(body["speed_mps"] - 8.0) < 0.3
    [v] = vehicles(api)
    assert (v["direction"], v["headsign"], v["confirmations"], v["status"]) == (0, "Est", 1, "probable")
    assert abs(v["lat"] - LAT) < 1e-4 and abs(v["along_m"] - body["along_m"]) <= 1
    assert api.get("/api/live").json() == {"L1": 1}


def test_eta_to_stop_ahead_only(api, clock, user):
    ride(api, clock, user())  # ~1,3 km du terminus, 8 m/s
    [v] = vehicles(api, stop_id="s3")
    assert abs(v["eta_s"] - (4458 - v["along_m"]) / 8.0) < 10
    assert vehicles(api, stop_id="s1")[0]["eta_s"] is None   # déjà passé


def test_wrong_direction_is_rejected_and_unpublished(api, clock, user):
    h = user()
    trip_id, r = ride(api, clock, h)
    assert r.json()["status"] == "on_route"
    clock.advance(10)
    r = api.post(f"/api/trips/{trip_id}/positions", json={"fixes": trace(clock, start_lon=10.17, speed_mps=-8)}, headers=h)
    assert r.json()["status"] == "rejected" and r.json()["reason"] == "mauvais sens de circulation"
    assert vehicles(api) == []


def test_off_route_is_rejected(api, clock, user):
    _, r = ride(api, clock, user(), lat=LAT + 0.002)
    assert r.json() == {"status": "rejected", "reason": "hors du tracé de la ligne", "along_m": None, "speed_mps": None}


def test_two_passengers_in_same_bus_confirm_it(api, clock, user):
    ride(api, clock, user())
    ride(api, clock, user(), start_lon=10.1603)
    ride(api, clock, user(), start_lon=10.185)      # bus suivant, ~2 km plus loin
    found = sorted(vehicles(api), key=lambda v: v["along_m"])
    assert [v["confirmations"] for v in found] == [2, 1]
    assert [v["status"] for v in found] == ["fiable", "probable"]


def test_end_trip_removes_vehicle_immediately(api, clock, user):
    h = user()
    trip_id, _ = ride(api, clock, h)
    assert api.post(f"/api/trips/{trip_id}/end", headers=h).json() == {"ok": True}
    assert vehicles(api) == []
    assert api.post(f"/api/trips/{trip_id}/positions", json={"fixes": trace(clock)}, headers=h).status_code == 410


def test_new_trip_ends_previous_one(api, clock, user):
    h = user()
    first, _ = ride(api, clock, h)
    ride(api, clock, h, line_id="L1", direction=0, start_lon=10.18)
    assert len(vehicles(api)) == 1
    assert api.post(f"/api/trips/{first}/positions", json={"fixes": trace(clock)}, headers=h).status_code == 410


def test_cannot_use_someone_elses_trip(api, clock, user):
    trip_id, _ = ride(api, clock, user())
    other = user()
    assert api.post(f"/api/trips/{trip_id}/positions", json={"fixes": trace(clock)}, headers=other).status_code == 404
    assert api.post(f"/api/trips/{trip_id}/end", headers=other).status_code == 404


def test_vehicle_becomes_stale_then_disappears(api, clock, user):
    ride(api, clock, user())
    clock.advance(150)
    [v] = vehicles(api)
    assert v["status"] == "obsolète" and v["age_s"] == 150
    clock.advance(200)
    assert vehicles(api) == [] and api.get("/api/live").json() == {}


def test_trip_times_out_after_two_hours(api, clock, user):
    h = user()
    trip_id, _ = ride(api, clock, h)
    clock.advance(2 * 3600 + 1)
    assert api.post(f"/api/trips/{trip_id}/positions", json={"fixes": trace(clock)}, headers=h).status_code == 410


def test_fixes_with_wrong_clock_are_ignored(api, clock, user):
    old = [{**f, "t": f["t"] - 3600} for f in trace(clock)]
    h = user()
    trip_id = api.post("/api/trips", json={"line_id": "L1", "direction": 0}, headers=h).json()["id"]
    assert api.post(f"/api/trips/{trip_id}/positions", json={"fixes": old}, headers=h).json()["status"] == "checking"


def test_position_cooldown(api, clock, user, monkeypatch):
    import trips
    monkeypatch.setattr(trips, "POSITION_COOLDOWN_S", 2)
    h = user()
    trip_id, r = ride(api, clock, h)
    assert r.status_code == 200
    assert api.post(f"/api/trips/{trip_id}/positions", json={"fixes": trace(clock)}, headers=h).status_code == 429


def test_raw_coordinates_are_never_stored(api, clock, user):
    ride(api, clock, user())
    for name in ("trips", "contributions", "users"):
        for doc in api.portal.call(server.db[name].find({}).to_list, 100):
            assert not {"lat", "lon", "fixes"} & set(doc), (name, doc)


def test_user_can_delete_all_their_data(api, clock, user):
    h = user()
    ride(api, clock, h)
    other = user()
    ride(api, clock, other, start_lon=10.185)
    assert api.post("/api/users/me/delete", headers=h).json() == {"ok": True}
    assert [v["confirmations"] for v in vehicles(api)] == [1]
    assert api.post("/api/users/me/delete", headers=h).status_code == 401
    counts = {name: api.portal.call(server.db[name].count_documents, {}) for name in ("users", "trips", "contributions")}
    assert counts == {"users": 1, "trips": 1, "contributions": 1}

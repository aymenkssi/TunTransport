from conftest import ADMIN, LAT, ride, trace


def test_trip_log_explains_refusals(api, clock, user):
    h = user()
    trip_id, r = ride(api, clock, h, lat=LAT + 0.01)  # 1,1 km au nord de la ligne
    assert r.json()["status"] == "rejected"
    clock.advance(10)
    api.post(f"/api/trips/{trip_id}/positions", json={"fixes": trace(clock, lat=LAT + 0.01)}, headers=h)  # même refus : compté
    api.post(f"/api/trips/{trip_id}/end", headers=h)
    ok_id, _ = ride(api, clock, user())

    assert api.get("/api/admin/trips").status_code == 401
    log = api.get("/api/admin/trips", headers=ADMIN).json()
    assert log["reasons"] == [{"reason": "hors du tracé de la ligne", "count": 1}]
    bad = next(x for x in log["trips"] if x["id"] == trip_id)
    kinds = [(e["kind"], e.get("reason"), e["n"]) for e in bad["events"]]
    assert kinds[0][0] == "started" and kinds[1] == ("rejected", "hors du tracé de la ligne", 2) and kinds[-1][0] == "ended"
    assert bad["events"][1]["offset_m"] > 1000 and bad["last_reject_reason"] == "hors du tracé de la ligne"
    assert [x["id"] for x in api.get("/api/admin/trips?status=rejected", headers=ADMIN).json()["trips"]] == [trip_id]
    assert ok_id in [x["id"] for x in api.get("/api/admin/trips?status=validated&line=1", headers=ADMIN).json()["trips"]]


def test_trip_states_and_silent_trips_are_closed(api, clock, user):
    import trips

    live_id, _ = ride(api, clock, user())                    # position affichée
    h = user()
    refused_id, _ = ride(api, clock, h, lat=LAT + 0.01)      # le téléphone envoie, rien n'est affiché
    states = {x["id"]: x["state"] for x in api.get("/api/admin/trips", headers=ADMIN).json()["trips"]}
    assert (states[live_id], states[refused_id]) == ("live", "active")

    clock.advance(6 * 60)                                     # plus de nouvelles
    states = {x["id"]: x["state"] for x in api.get("/api/admin/trips", headers=ADMIN).json()["trips"]}
    assert states[live_id] == states[refused_id] == "silent"
    assert api.get("/api/admin/trips?status=active", headers=ADMIN).json()["trips"] == []

    clock.advance(5 * 60)                                     # 11 min : trajets clos
    assert api.portal.call(trips.close_silent_trips) == 2
    rows = {x["id"]: x for x in api.get("/api/admin/trips", headers=ADMIN).json()["trips"]}
    assert rows[live_id]["state"] == "ended" and rows[live_id]["end_reason"].startswith("plus de nouvelles")
    assert rows[live_id]["events"][-1]["kind"] == "ended"

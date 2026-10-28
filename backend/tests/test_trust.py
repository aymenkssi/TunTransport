"""Fausses déclarations : immobilité, marche, faux GPS, réputation et signalements."""
from conftest import ADMIN, LAT, M_PER_DEG_LON, ride

import server
import trust


def start(api, h, line_id="L1", direction=0):
    r = api.post("/api/trips", json={"line_id": line_id, "direction": direction}, headers=h)
    assert r.status_code == 200, r.text
    return r.json()["id"]


def drive(api, clock, h, trip_id, lon_at, seconds, step=10, mocked=False):
    """Envoie une position toutes les `step` s pendant `seconds` s ; lon_at(t relatif) donne la longitude.
    Renvoie la dernière réponse."""
    t0 = clock.t
    last = None
    for _ in range(int(seconds // step)):
        clock.advance(step)
        fixes = [{"t": clock.t - k * 10, "lat": LAT, "lon": lon_at(clock.t - k * 10 - t0), "accuracy": 8, "mocked": mocked}
                 for k in range(5, -1, -1)]
        last = api.post(f"/api/trips/{trip_id}/positions", json={"fixes": fixes}, headers=h)
    return last


def at_speed(start_lon, speed):
    return lambda s: start_lon + speed * s / M_PER_DEG_LON


def vehicles(api, line_id="L1"):
    return api.get(f"/api/lines/{line_id}/vehicles").json()


def user_doc(api, headers):
    token = headers["Authorization"][7:]
    from auth import hash_token
    return api.portal.call(server.db.users.find_one, {"token_hash": hash_token(token)})


# ------------------------ Mouvement ------------------------
def test_stationary_passenger_is_not_a_vehicle(api, clock, user):
    h = user()
    trip = start(api, h)
    assert drive(api, clock, h, trip, lambda s: 10.17, 200).json()["status"] == "on_route"  # arrêt court : normal
    r = drive(api, clock, h, trip, lambda s: 10.17, 60).json()
    assert r == {"status": "rejected", "reason": trust.REASONS["stationary"], "along_m": None, "speed_mps": None}
    assert vehicles(api) == []
    # Le bus repart : la position est de nouveau publiée.
    assert drive(api, clock, h, trip, at_speed(10.17, 8), 30).json()["status"] == "on_route"


def test_waiting_at_terminus_is_allowed(api, clock, user):
    h = user()
    trip = start(api, h)
    assert drive(api, clock, h, trip, lambda s: 10.1503, 300).json()["status"] == "on_route"


def test_pedestrian_walking_along_the_line_is_rejected(api, clock, user):
    h = user()
    trip = start(api, h)
    r = drive(api, clock, h, trip, at_speed(10.16, 1.4), 240).json()
    assert r["status"] == "rejected" and r["reason"] == trust.REASONS["walking"]


def test_bus_in_traffic_jam_is_not_taken_for_a_pedestrian(api, clock, user):
    h = user()
    trip = start(api, h)
    # 1,5 m/s de moyenne, mais avec des accélérations à 6 m/s : un véhicule, pas un piéton.
    def jam(s):
        cycle, phase = divmod(s, 60)
        return 10.16 + (cycle * 90 + (0 if phase < 45 else (phase - 45) * 6)) / M_PER_DEG_LON
    assert drive(api, clock, h, trip, jam, 300).json()["status"] == "on_route"


def test_bus_running_normally_passes(api, clock, user):
    h = user()
    trip = start(api, h)
    assert drive(api, clock, h, trip, at_speed(10.155, 8), 300).json()["status"] == "on_route"


# ------------------------ Faux GPS et réputation ------------------------
def test_mocked_location_ends_trip_and_hides_future_trips(api, clock, user):
    cheater = user()
    trip = start(api, cheater)
    r = drive(api, clock, cheater, trip, at_speed(10.16, 8), 10, mocked=True).json()
    assert r["status"] == "rejected" and r["reason"] == trust.REASONS["mocked"]
    assert drive(api, clock, cheater, trip, at_speed(10.16, 8), 10).status_code == 410
    assert user_doc(api, cheater)["rep_mocked"] == 1

    # Nouveau trajet : le tricheur voit « position partagée », mais personne ne voit son véhicule.
    trip = start(api, cheater)
    assert drive(api, clock, cheater, trip, at_speed(10.16, 8), 60).json()["status"] == "on_route"
    assert vehicles(api) == [] and api.get("/api/vehicles/live").json() == [] and api.get("/api/live").json() == {}

    # Un passager de confiance dans le même bus le rend visible.
    honest = user()
    # Sa trace se termine là où est le tricheur (480 m parcourus) : même bus.
    ride(api, clock, honest, start_lon=10.16 + (8 * 60 - 8 * 50) / M_PER_DEG_LON)
    [v] = vehicles(api)
    assert v["confirmations"] == 2


def test_trips_settle_reputation(api, clock, user):
    a, b, solo = user(), user(), user()
    ta, _ = ride(api, clock, a)
    tb, _ = ride(api, clock, b, start_lon=10.1603)
    ts, _ = ride(api, clock, solo, line_id="L2", lat=LAT + 0.005)
    for h, t in ((a, ta), (b, tb), (solo, ts)):
        api.post(f"/api/trips/{t}/end", headers=h)
    assert user_doc(api, a).get("rep_confirmed") == 1 and user_doc(api, b).get("rep_confirmed") == 1
    assert user_doc(api, solo).get("rep_confirmed") is None and user_doc(api, solo)["rep_solo"] == 1


def test_reputation_score():
    assert trust.reputation({}) == 1.0
    assert trust.is_trusted({"rep_solo": 500})                     # toujours seul dans son bus : reste crédible
    assert not trust.is_trusted({"rep_mocked": 1})
    assert not trust.is_trusted({"rep_reported": 2})
    assert trust.is_trusted({"rep_reported": 2, "rep_confirmed": 5})


# ------------------------ Signalements ------------------------
def report(api, h, v, line_id="L1"):
    return api.post("/api/vehicles/report", json={"line_id": line_id, "direction": v["direction"], "lat": v["lat"], "lon": v["lon"]}, headers=h)


def test_two_reports_hide_a_solo_vehicle(api, clock, user):
    sharer = user()
    trip_id, r = ride(api, clock, sharer)
    [v] = vehicles(api)
    assert report(api, sharer, v).status_code == 409             # on ne signale pas son propre véhicule
    r1, r2 = user(), user()
    assert report(api, r1, v).json() == {"ok": True}
    assert report(api, r1, v).json() == {"ok": True}             # doublon : ne compte qu'une fois
    assert len(vehicles(api)) == 1
    assert report(api, r2, v).json() == {"ok": True}
    assert vehicles(api) == []
    assert user_doc(api, sharer)["rep_reported"] == 1
    # Le partageur n'en sait rien : ses positions sont toujours « publiées » de son point de vue.
    clock.advance(10)
    from conftest import trace
    assert api.post(f"/api/trips/{trip_id}/positions", json={"fixes": trace(clock)}, headers=sharer).json()["status"] == "on_route"
    assert vehicles(api) == []
    assert api.get("/api/admin/stats", headers=ADMIN).json()["reports_7d"] == 2


def test_confirmed_vehicle_needs_three_reports(api, clock, user):
    ride(api, clock, user())
    ride(api, clock, user(), start_lon=10.1603)
    [v] = vehicles(api)
    for k in range(2):
        report(api, user(), v)
    assert len(vehicles(api)) == 1
    report(api, user(), v)
    assert vehicles(api) == []


def test_untrusted_reporter_has_no_effect(api, clock, user, monkeypatch):
    ride(api, clock, user())
    [v] = vehicles(api)
    liars = [user(), user()]
    for h in liars:
        api.portal.call(server.db.users.update_one, {"id": user_doc(api, h)["id"]}, {"$set": {"rep_mocked": 1}})
        assert report(api, h, v).json() == {"ok": True}
    assert len(vehicles(api)) == 1


def test_report_errors_and_daily_limit(api, clock, user, monkeypatch):
    ride(api, clock, user())
    [v] = vehicles(api)
    h = user()
    assert report(api, h, {**v, "lat": v["lat"] + 0.02}).status_code == 404   # rien à 2 km de là
    assert api.post("/api/vehicles/report", json={"line_id": "L1", "direction": 0, "lat": LAT, "lon": 10.16}).status_code == 401
    monkeypatch.setattr(trust, "MAX_REPORTS_PER_DAY", 1)
    assert report(api, h, v).status_code == 200
    assert report(api, h, v).status_code == 429


def test_admin_live_shows_hidden_untrusted_vehicles(api, clock, user):
    cheater = user()
    api.portal.call(server.db.users.update_one, {"id": user_doc(api, cheater)["id"]}, {"$set": {"rep_mocked": 1}})
    ride(api, clock, cheater)
    [row] = api.get("/api/admin/live", headers=ADMIN).json()
    assert row["visible"] is False
    assert api.get("/api/admin/stats", headers=ADMIN).json()["low_reputation_users"] == 1

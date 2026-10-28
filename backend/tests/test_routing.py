from datetime import datetime

from conftest import LAT, ride

import routing


def at(clock, hour, minute):
    clock.t = datetime(2027, 1, 15, hour, minute, tzinfo=routing.TUNIS_TZ).timestamp()


def plan(api, origin, destination):
    r = api.post("/api/routes/plan", json={"origin": origin, "destination": destination})
    assert r.status_code == 200, r.text
    return r.json()


def test_search_stops(api):
    found = api.get("/api/stops/search", params={"q": "cent"}).json()
    assert [(s["id"], s["name"]) for s in found] == [("s2", "Centre")]
    assert found[0]["lines"][0]["short_name"] == "1"
    assert api.get("/api/stops/search", params={"q": "x"}).json() == []


def test_direct_ride_between_stops(api, clock):
    at(clock, 6, 10)
    [best] = [i for i in plan(api, {"stop_id": "s1"}, {"stop_id": "s3"}) if i["transfers"] == 0 and len(i["legs"]) == 1]
    leg = best["legs"][0]
    assert (leg["kind"], leg["line"]["id"], leg["headsign"], leg["from"]["name"], leg["to"]["name"], leg["stops"]) == (
        "ride", "L1", "Est", "Ouest", "Est", 2)
    assert leg["wait_source"] == "estimé" and leg["wait_s"] == 600
    assert best["depart"] == "06:10" and best["live"] is False
    assert len(leg["path"]) >= 2 and leg["path"][0] == [LAT, 10.15]


def test_walk_to_another_line_then_ride(api, clock):
    at(clock, 6, 10)
    # Départ sur L1 à l'ouest, arrivée au bout est de L2 (~550 m au nord du terminus de L1).
    itineraries = plan(api, {"lat": LAT, "lon": 10.15, "name": "Maison"}, {"lat": LAT + 0.005, "lon": 10.20, "name": "Travail"})
    best = itineraries[0]
    kinds = [(l["kind"], l["line"]["id"] if l["line"] else None) for l in best["legs"]]
    assert ("ride", "L1") in kinds or ("ride", "L2") in kinds
    assert best["legs"][0]["from"]["name"] == "Maison" and best["legs"][-1]["to"]["name"] == "Travail"


def test_live_vehicle_sets_the_wait(api, clock, user):
    at(clock, 6, 10)
    ride(api, clock, user(), start_lon=10.155)   # passager dans un bus L1 qui approche de « Centre »
    leg = next(i for i in plan(api, {"stop_id": "s2"}, {"stop_id": "s3"}) if i["legs"][0]["kind"] == "ride")["legs"][0]
    assert leg["wait_source"] == "en direct" and leg["wait_s"] < 600


def test_no_service_at_night_with_a_far_origin(api, clock):
    at(clock, 23, 30)
    # Aucun arrêt à moins de 1,2 km : ni trajet maintenant, ni premier trajet du lendemain.
    assert plan(api, {"lat": LAT + 0.05, "lon": 10.15, "name": "Loin"}, {"stop_id": "s3"}) == []


def test_scheduled_mode_uses_timetable(api, clock, monkeypatch):
    monkeypatch.setitem(routing.SPEED_MPS, "bus", 4.2)
    monkeypatch.setattr(routing, "SCHEDULED_MODES", {"bus"})
    at(clock, 6, 20)
    leg = next(i for i in plan(api, {"stop_id": "s1"}, {"stop_id": "s3"}) if i["legs"][0]["kind"] == "ride")["legs"][0]
    assert (leg["wait_source"], leg["wait_s"], leg["depart"]) == ("horaire", 600, "06:30")


def test_place_validation(api):
    assert api.post("/api/routes/plan", json={"origin": {}, "destination": {"stop_id": "s1"}}).status_code == 422
    assert api.post("/api/routes/plan", json={"origin": {"stop_id": "nope"}, "destination": {"stop_id": "s1"}}).status_code == 404


def test_night_proposes_first_trip_tomorrow(api, clock):
    at(clock, 23, 30)
    rides = [i for i in plan(api, {"stop_id": "s1"}, {"stop_id": "s3"}) if i["legs"][0]["kind"] == "ride"]
    assert rides, "le premier trajet du lendemain doit être proposé"
    first = rides[0]
    assert first["later"] is True and first["date"] == "2027-01-16"
    assert first["legs"][0]["depart"] == "06:00" and first["depart"] == "06:00" and first["legs"][0]["wait_s"] == 0


def test_choose_departure_time(api, clock):
    at(clock, 23, 30)
    morning = datetime(2027, 1, 16, 6, 10, tzinfo=routing.TUNIS_TZ).timestamp()
    r = api.post("/api/routes/plan", json={"origin": {"stop_id": "s1"}, "destination": {"stop_id": "s3"}, "depart_at": morning}).json()
    first = next(i for i in r if i["legs"][0]["kind"] == "ride")
    assert (first["later"], first["date"], first["depart"]) == (False, "2027-01-16", "06:10")
    too_far = clock.t + 4 * 86400
    assert api.post("/api/routes/plan", json={"origin": {"stop_id": "s1"}, "destination": {"stop_id": "s3"}, "depart_at": too_far}).status_code == 422

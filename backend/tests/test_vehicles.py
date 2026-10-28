"""Algorithmes purs : géométrie, validation de trace, regroupement en véhicules, fiabilité, ETA."""
from conftest import EAST, LAT, M_PER_DEG_LON

from geo import Shape
from matching import GpsFix, match_trace
from vehicles import Contribution, cluster_vehicles, eta_seconds, reliability

SHAPE = Shape([tuple(p) for p in EAST])
NOW = 2000.0


def fixes(start_lon=10.16, speed=8.0, lat=LAT, accuracy=10.0):
    return [GpsFix(1000 + i * 10, lat, start_lon + speed * i * 10 / M_PER_DEG_LON, accuracy) for i in range(6)]


def c(trip, along, speed=8.0, age=0.0, direction=0):
    return Contribution(trip, "L1", direction, along, speed, NOW - age)


def test_point_at_and_bounds():
    lat, lon = SHAPE.point_at(SHAPE.length_m / 2)
    assert abs(lat - LAT) < 1e-9 and abs(SHAPE.project(lat, lon).along_m - SHAPE.length_m / 2) < 1
    assert SHAPE.point_at(-5) == (LAT, 10.15) and SHAPE.point_at(1e9) == (LAT, 10.20)
    lat_min, lon_min, lat_max, lon_max = SHAPE.bounds(100)
    assert lat_min < LAT < lat_max and lon_min < 10.15 and lon_max > 10.20


def test_match_trace():
    assert match_trace(fixes(), SHAPE).ok
    assert match_trace(fixes(speed=-8), SHAPE).reason == "wrong_direction"
    assert match_trace(fixes(lat=LAT + 0.002), SHAPE).reason == "off_route"
    assert match_trace(fixes(accuracy=200), SHAPE).reason == "too_short"
    assert match_trace(fixes(speed=60), SHAPE).reason == "implausible_speed"


def test_clustering():
    found = cluster_vehicles([c("a", 1000, age=5), c("b", 1030, age=2), c("c", 2500), c("d", 1000, direction=1)], NOW)
    assert sorted(len(v.contributors) for v in found) == [1, 1, 2]
    # Un bus à l'arrêt et un autre qui le double au même endroit : deux véhicules.
    assert len(cluster_vehicles([c("a", 1000, speed=0), c("b", 1050, speed=10)], NOW)) == 2


def test_reliability_and_eta():
    alone = cluster_vehicles([c("a", 1000)], NOW)[0]
    confirmed = cluster_vehicles([c(t, 1000) for t in "abc"], NOW)[0]
    assert reliability(alone, NOW)[1] == "probable"
    assert reliability(confirmed, NOW)[1] == "fiable"
    assert reliability(confirmed, NOW + 200)[1] == "obsolète"
    assert reliability(confirmed, NOW + 400)[1] == "expiré"
    fast = cluster_vehicles([c("a", 1000, speed=10)], NOW)[0]
    assert eta_seconds(fast, 2000, NOW) == 100.0 and eta_seconds(fast, 500, NOW) is None
    stopped = cluster_vehicles([c("a", 1000, speed=0)], NOW)[0]
    assert eta_seconds(stopped, 2000, NOW) == 200.0  # vitesse par défaut

from conftest import ADMIN, ride


def test_admin_requires_token(api, monkeypatch):
    assert api.get("/api/admin/stats").status_code == 401
    assert api.get("/api/admin/stats", headers={"Authorization": "Bearer wrong"}).status_code == 401
    monkeypatch.setenv("ADMIN_TOKEN", "short")
    assert api.get("/api/admin/stats", headers=ADMIN).status_code == 503


def test_admin_page_is_served(api):
    r = api.get("/admin")
    assert r.status_code == 200 and "TunTransport" in r.text


def test_stats_and_live(api, clock, user):
    ride(api, clock, user())
    ride(api, clock, user(), lat=36.802)  # hors tracé : trajet non validé
    stats = api.get("/api/admin/stats", headers=ADMIN).json()
    assert (stats["users"], stats["active_trips"], stats["trips_today"], stats["validated_7d"], stats["contributors_7d"]) == (2, 2, 2, 1, 1)
    assert stats["top_lines"] == [{"line_id": "L1", "label": "1 (bus)", "trips": 1}]
    assert len(stats["per_day"]) == 14 and stats["per_day"][-1]["trips"] == 2
    [row] = api.get("/api/admin/live", headers=ADMIN).json()
    assert (row["label"], row["headsign"], row["confirmations"], row["speed_kmh"]) == ("1 (bus)", "Est", 1, 29)


def test_network_info_and_reload(api):
    info = api.get("/api/admin/network", headers=ADMIN).json()
    assert info == {"source": "test", "generated": "2026-10-28", "lines": 2, "by_mode": {"bus": 1, "metro": 1}, "stops_only_shapes": 1}
    assert api.post("/api/admin/network/reload", headers=ADMIN).json()["lines"] == 2

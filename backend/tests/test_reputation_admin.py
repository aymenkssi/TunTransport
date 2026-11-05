import server
from conftest import ADMIN, ride


def test_admin_restores_a_user_reputation(api, clock):
    created = api.post("/api/users").json()
    h = {"Authorization": f"Bearer {created['token']}"}
    api.portal.call(server.db.users.update_one, {"id": created["id"]}, {"$set": {"rep_mocked": 1, "rep_rejected": 2}})
    ride(api, clock, h)

    assert api.get("/api/admin/users").status_code == 401
    [row] = api.get("/api/admin/users", headers=ADMIN).json()
    assert (row["id"], row["trusted"], row["mocked"], row["rejected"], row["trips_7d"], row["last_line"]) == (
        created["id"], False, 1, 2, 1, "1 (bus)")
    [vehicle] = api.get("/api/admin/live", headers=ADMIN).json()
    assert not vehicle["visible"] and vehicle["users"] == [{"id": created["id"], "short": created["id"][:8], "trusted": False}]
    assert [r["id"] for r in api.get(f"/api/admin/users?q={created['id'][:6]}", headers=ADMIN).json()] == [created["id"]]

    assert api.post(f"/api/admin/users/{created['id']}/reputation/reset", headers=ADMIN).json() == {"ok": True}
    assert api.get("/api/admin/users", headers=ADMIN).json() == []  # plus aucun utilisateur non fiable
    [row] = api.get(f"/api/admin/users?q={created['id'][:6]}", headers=ADMIN).json()
    assert row["trusted"] and row["reset_at"]
    assert api.post("/api/admin/users/nope/reputation/reset", headers=ADMIN).status_code == 404

from conftest import ADMIN

import server


def send(api, h, message="Ajouter les horaires du TGM le dimanche", category="idea", **extra):
    return api.post("/api/suggestions", json={"category": category, "message": message, **extra},
                    headers={**h, "X-App-Version": "1.0.0", "X-Platform": "android"})


def test_user_sends_and_admin_reads(api, user):
    h = user()
    assert send(api, h, category="data", message="L'arrêt Centre est mal placé", line_id="L1", contact="  a@b.tn ").json() == {"ok": True}
    r = api.get("/api/admin/suggestions", headers=ADMIN).json()
    assert r["counts"] == {"new": 1, "read": 0, "done": 0}
    s = r["items"][0]
    assert (s["category"], s["message"], s["line_id"], s["line_label"], s["contact"], s["app_version"], s["platform"], s["status"]) == (
        "data", "L'arrêt Centre est mal placé", "L1", "1 (bus)", "a@b.tn", "1.0.0", "android", "new")
    assert "user_id" not in s


def test_validation_and_auth(api, user):
    h = user()
    assert send(api, {}).status_code == 401
    assert send(api, h, message="   ok   ").status_code == 422
    assert send(api, h, message="x" * 1001).status_code == 422
    assert send(api, h, category="spam").status_code == 422
    assert send(api, h, line_id="nope").status_code == 404


def test_daily_limit(api, user):
    h = user()
    for i in range(5):
        assert send(api, h, message=f"Suggestion numéro {i}").status_code == 200
    assert send(api, h, message="Une de trop").status_code == 429
    assert send(api, user(), message="Un autre utilisateur").status_code == 200


def test_status_filter_and_delete(api, user):
    h = user()
    send(api, h, message="Premier message")
    send(api, h, message="Deuxième message", category="bug")
    items = api.get("/api/admin/suggestions", headers=ADMIN).json()["items"]
    bug = next(i for i in items if i["category"] == "bug")
    assert api.put(f"/api/admin/suggestions/{bug['id']}", json={"status": "done"}, headers=ADMIN).json()["status"] == "done"
    r = api.get("/api/admin/suggestions?status=done", headers=ADMIN).json()
    assert [i["id"] for i in r["items"]] == [bug["id"]] and r["counts"] == {"new": 1, "read": 0, "done": 1}
    assert api.put("/api/admin/suggestions/nope", json={"status": "read"}, headers=ADMIN).status_code == 404
    assert api.put(f"/api/admin/suggestions/{bug['id']}", json={"status": "archived"}, headers=ADMIN).status_code == 422
    assert api.delete(f"/api/admin/suggestions/{bug['id']}", headers=ADMIN).status_code == 200
    assert api.get("/api/admin/suggestions", headers=ADMIN).json()["counts"]["done"] == 0
    assert api.get("/api/admin/suggestions").status_code == 401


def test_deleting_my_data_removes_my_suggestions(api, user):
    h = user()
    send(api, h)
    send(api, user(), message="Celle d'un autre utilisateur")
    api.post("/api/users/me/delete", headers=h)
    assert api.portal.call(server.db.suggestions.count_documents, {}) == 1

from conftest import ADMIN


def test_admin_sets_the_published_version(api):
    assert api.get("/api/app/version").json() == {"latest": None, "minimum": None}
    assert api.put("/api/admin/app-version", json={"latest": "1.0.2"}).status_code == 401
    assert api.put("/api/admin/app-version", json={"latest": "1.0.2", "minimum": "1.0.0"}, headers=ADMIN).status_code == 200
    assert api.get("/api/app/version").json() == {"latest": "1.0.2", "minimum": "1.0.0"}
    assert api.put("/api/admin/app-version", json={"latest": "v2"}, headers=ADMIN).status_code == 422

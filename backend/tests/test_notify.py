import notify
from conftest import ADMIN, ride

TOKEN = "123456:ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def fake_telegram(monkeypatch):
    calls = []

    async def call(token, method, **params):
        calls.append((token, method, params))
        if method == "getUpdates":
            return [{"message": {"chat": {"id": 42, "first_name": "Aymen", "type": "private"}}}]
        return {}

    monkeypatch.setattr(notify, "_call", call)
    notify._sent.clear()
    return calls


def test_settings_keep_the_token_secret(api, monkeypatch):
    fake_telegram(monkeypatch)
    assert api.put("/api/admin/telegram", json={"enabled": True}).status_code == 401
    assert api.put("/api/admin/telegram", json={"enabled": True}, headers=ADMIN).status_code == 422
    r = api.put("/api/admin/telegram", json={"enabled": True, "bot_token": TOKEN, "chat_id": "42"}, headers=ADMIN).json()
    assert r["token_hint"] == "123456…WXYZ" and "bot_token" not in r
    # Jeton vide : l'ancien est gardé.
    api.put("/api/admin/telegram", json={"enabled": True, "chat_id": "43"}, headers=ADMIN)
    assert api.get("/api/admin/telegram", headers=ADMIN).json()["token_hint"] == "123456…WXYZ"
    assert api.get("/api/admin/telegram/chats", headers=ADMIN).json() == [{"id": "42", "name": "Aymen", "type": "private"}]
    assert api.post("/api/admin/telegram/test", headers=ADMIN).json() == {"ok": True}


def test_new_trip_sends_a_message(api, clock, user, monkeypatch):
    calls = fake_telegram(monkeypatch)
    ride(api, clock, user())  # notifications désactivées : rien
    assert [c for c in calls if c[1] == "sendMessage"] == []
    api.put("/api/admin/telegram", json={"enabled": True, "bot_token": TOKEN, "chat_id": "42", "on_trip_validated": True}, headers=ADMIN)
    ride(api, clock, user())
    sent = [c[2]["text"] for c in calls if c[1] == "sendMessage"]
    assert len(sent) == 2 and "Nouveau partage" in sent[0] and "<b>1</b>" in sent[0] and "Trajet validé" in sent[1]

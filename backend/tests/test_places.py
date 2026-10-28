import places

NOMINATIM_ITEMS = [
    {"lat": "36.8423", "lon": "10.1960", "name": "Avenue Habib Bourguiba",
     "display_name": "Avenue Habib Bourguiba, Ariana Ville, Ariana, 2080, Tunisie", "type": "secondary"},
    {"lat": "x", "lon": "10", "display_name": "Coordonnées invalides"},
    {"lat": "36.80", "lon": "10.18", "name": "", "display_name": "", "type": "house"},
]


def fake_nominatim(monkeypatch, items=NOMINATIM_ITEMS):
    calls = []

    async def fetch(q):
        calls.append(q)
        if isinstance(items, Exception):
            raise items
        return items

    monkeypatch.setattr(places, "_fetch", fetch)
    places._cache.clear()
    return calls


def test_search_maps_and_caches(api, monkeypatch):
    calls = fake_nominatim(monkeypatch)
    expected = [{"name": "Avenue Habib Bourguiba", "detail": "Ariana Ville, Ariana, 2080", "lat": 36.8423, "lon": 10.196,
                 "kind": "secondary"}]
    first = api.get("/api/places/search", params={"q": "  avenue   bourguiba ariana "}).json()
    assert [{k: v for k, v in h.items() if k != "stop_distance_m"} for h in first] == expected
    assert first[0]["stop_distance_m"] > 4000  # à ~5 km du réseau de test
    assert api.get("/api/places/search", params={"q": "Avenue Bourguiba Ariana"}).json() == first
    assert calls == ["avenue bourguiba ariana"]  # deuxième recherche servie par le cache


def test_places_near_a_stop_come_first(api, monkeypatch):
    far = {"lat": "36.40", "lon": "10.60", "name": "Plage lointaine", "display_name": "Plage lointaine, Nabeul", "type": "beach"}
    farther = {"lat": "35.80", "lon": "10.60", "name": "Plage très lointaine", "display_name": "Plage très lointaine, Sousse", "type": "beach"}
    near = {"lat": "36.8005", "lon": "10.171", "name": "Plage du centre", "display_name": "Plage du centre, Tunis", "type": "beach"}
    fake_nominatim(monkeypatch, [farther, far, near])
    found = api.get("/api/places/search", params={"q": "plage"}).json()
    assert [h["name"] for h in found] == ["Plage du centre", "Plage lointaine", "Plage très lointaine"]
    assert found[0]["stop_distance_m"] < 200


def test_local_index_first_and_no_nominatim_while_typing(api, monkeypatch):
    calls = fake_nominatim(monkeypatch)
    found = api.get("/api/places/search", params={"q": "62 rue hyppocrate cite avicenne", "autocomplete": "true"}).json()
    assert found[0]["name"] == "62 Rue Hippocrate" and found[0]["stop_distance_m"] > 0
    assert api.get("/api/places/search", params={"q": "hippo", "autocomplete": "true"}).json()[0]["name"] == "Rue Hippocrate"
    assert calls == []  # pendant la frappe : jamais Nominatim


def test_nominatim_completes_few_local_results(api, monkeypatch):
    calls = fake_nominatim(monkeypatch, [
        {"lat": "36.7571", "lon": "10.1807", "name": "Rue Hippocrate", "display_name": "Rue Hippocrate, Ibn Sina 1", "type": "tertiary"},
        {"lat": "36.80", "lon": "10.19", "name": "Clinique Hippocrate", "display_name": "Clinique Hippocrate, Tunis", "type": "clinic"},
    ])
    found = api.get("/api/places/search", params={"q": "rue hippocrate"}).json()
    assert [h["name"] for h in found] == ["Rue Hippocrate", "Clinique Hippocrate"]  # doublon de Nominatim écarté
    assert calls == ["rue hippocrate"]


def test_nominatim_down_returns_local_results(api, monkeypatch):
    fake_nominatim(monkeypatch, RuntimeError("down"))
    assert api.get("/api/places/search", params={"q": "rue hippocrate"}).json()[0]["name"] == "Rue Hippocrate"


def test_short_query_does_not_call_nominatim(api, monkeypatch):
    calls = fake_nominatim(monkeypatch)
    assert api.get("/api/places/search", params={"q": "ab"}).json() == []
    assert calls == []


def test_nominatim_failure_is_a_502(api, monkeypatch):
    fake_nominatim(monkeypatch, RuntimeError("down"))
    assert api.get("/api/places/search", params={"q": "La Marsa"}).status_code == 502


def test_requests_are_spaced_by_one_second(monkeypatch):
    import asyncio

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return []

    class Client:
        def __init__(self, **kwargs):
            assert "TransTunisLive" in kwargs["headers"]["User-Agent"]

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def get(self, url, params):
            assert params["countrycodes"] == "tn"
            stamps.append(asyncio.get_running_loop().time())
            return Response()

    stamps = []
    monkeypatch.setattr(places.httpx, "AsyncClient", Client)
    monkeypatch.setattr(places, "MIN_INTERVAL_S", 0.2)
    monkeypatch.setattr(places, "_lock", asyncio.Lock())  # verrou propre à cette boucle d'événements

    async def run():
        places._last_call = 0.0
        await asyncio.gather(places._fetch("a"), places._fetch("b"))

    asyncio.run(run())
    assert stamps[1] - stamps[0] >= 0.19

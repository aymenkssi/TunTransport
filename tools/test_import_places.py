import unittest

from import_places import build


def way(i, name, lat, lon, **tags):
    return {"type": "way", "id": i, "center": {"lat": lat, "lon": lon}, "tags": {"highway": "residential", "name": name, **tags}}


class BuildTest(unittest.TestCase):
    def test_merges_street_segments_and_attaches_quartier(self):
        elements = [
            {"type": "node", "id": 1, "lat": 36.7564, "lon": 10.1851, "tags": {"place": "suburb", "name": "Ibn Sina 1"}},
            way(2, "Rue Hippocrate", 36.7570, 10.1805, **{"name:ar": "نهج أبقراط"}),
            way(3, "Rue Hippocrate", 36.7575, 10.1812),            # tronçon voisin : même rue
            way(4, "Rue Hippocrate", 36.8600, 10.3000),            # même nom à 15 km : autre rue
            {"type": "node", "id": 5, "lat": 36.80, "lon": 10.16, "tags": {"amenity": "hospital", "name": "Hôpital X"}},
            {"type": "node", "id": 6, "lat": 36.80, "lon": 10.16, "tags": {"amenity": "bench"}},   # sans nom : ignoré
        ]
        entries = build(elements)
        streets = [e for e in entries if e["k"] == "street"]
        self.assertEqual(len(streets), 2)
        near = next(e for e in streets if e["lat"] < 36.8)
        self.assertEqual((near["area"], near["a"]), ("Ibn Sina 1", ["نهج أبقراط"]))
        self.assertNotIn("area", next(e for e in streets if e["lat"] > 36.8))  # aucun quartier à moins de 3 km
        self.assertEqual([(e["n"], e["t"]) for e in entries if e["k"] == "poi"], [("Hôpital X", "hospital")])

    def test_prefers_french_name(self):
        [entry] = build([way(1, "نهج مرسيليا", 36.8, 10.18, **{"name:fr": "Rue de Marseille"})])
        self.assertEqual((entry["n"], entry["a"]), ("Rue de Marseille", ["نهج مرسيليا"]))


if __name__ == "__main__":
    unittest.main()

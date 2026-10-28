"""Petit index d'adresses pour les tests, au format de tools/import_places.py."""
from conftest import LAT

PLACES = {
    "generated": "2026-10-28",
    "places": [
        {"n": "Ibn Sina 1", "a": ["ابن سيناء 1"], "k": "area", "t": "suburb", "lat": 36.7564, "lon": 10.1851},
        {"n": "Les Berges du Lac II", "a": [], "k": "area", "t": "suburb", "lat": 36.8455, "lon": 10.2709},
        {"n": "El Menzah 6", "a": ["المنزه 6"], "k": "area", "t": "suburb", "lat": 36.8495, "lon": 10.1626},
        {"n": "El Menzah 5", "a": [], "k": "area", "t": "suburb", "lat": 36.8420, "lon": 10.1700},
        {"n": "Rue Hippocrate", "a": ["نهج أبقراط"], "k": "street", "t": "tertiary", "lat": 36.7571745, "lon": 10.1807693,
         "area": "Ibn Sina 1", "area_alts": ["ابن سيناء 1"]},
        {"n": "Rue du Lac", "a": [], "k": "street", "t": "residential", "lat": 36.83, "lon": 10.24, "area": "El Menzah 5"},
        {"n": "Rue de Marseille", "a": ["نهج مارسيليا"], "k": "street", "t": "residential", "lat": 36.8037, "lon": 10.1822,
         "area": "Bab El Khadhra"},
        {"n": "Hôpital Charles Nicolle", "a": [], "k": "poi", "t": "hospital", "lat": 36.8028, "lon": 10.1636, "area": "Bab Souika"},
        {"n": "Gare du Centre", "a": [], "k": "poi", "t": "station", "lat": LAT, "lon": 10.17, "area": "Centre"},
    ],
}

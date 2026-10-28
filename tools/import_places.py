#!/usr/bin/env python3
"""Importe les rues, quartiers et lieux du Grand Tunis depuis OpenStreetMap (Overpass) et produit
places.json, l'index d'adresses de l'itinéraire (recherche tolérante aux fautes, suggestions pendant
la frappe, sans dépendre d'un service externe).

Données © contributeurs OpenStreetMap (ODbL).

Usage : python3 tools/import_places.py [--out chemin]
"""
import argparse
import json
import math
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
USER_AGENT = "TransTunisLive-importer/1.0 (+https://tuntransport.academy)"
OVERPASS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
]
BBOX = (36.55, 9.85, 37.10, 10.45)  # Grand Tunis : Tunis, Ariana, Ben Arous, Manouba, La Marsa, Hammam-Lif…
POI_KEYS = ("amenity", "healthcare", "shop", "tourism", "office", "leisure", "building")
AREA_PLACES = {"city", "town", "village", "suburb", "quarter", "neighbourhood", "hamlet", "locality", "city_block"}
STREET_MERGE_M = 600   # tronçons d'une même rue (même nom) à moins de 600 m : une seule entrée
AREA_MAX_M = 3000      # quartier rattaché à une rue ou un lieu s'il est à moins de 3 km


def _queries():
    s, w, n, e = BBOX
    mid = round((s + n) / 2, 3)
    box = f"{s},{w},{n},{e}"
    yield f'nwr["place"]["name"]({box});'
    yield f'way["highway"]["name"]({s},{w},{mid},{e});'
    yield f'way["highway"]["name"]({mid},{w},{n},{e});'
    yield "".join(f'nwr["{k}"]["name"]({box});' for k in POI_KEYS[:2])
    yield "".join(f'nwr["{k}"]["name"]({box});' for k in POI_KEYS[2:])


def fetch(query):
    body = urllib.parse.urlencode({"data": f"[out:json][timeout:240];({query});out center tags;"}).encode()
    last = None
    for attempt in range(3):
        for url in OVERPASS:
            try:
                req = urllib.request.Request(url, data=body, headers={"User-Agent": USER_AGENT})
                with urllib.request.urlopen(req, timeout=300) as r:
                    data = json.load(r)
                if data.get("remark") and "error" in data["remark"].lower():
                    raise RuntimeError(data["remark"])
                return data["elements"]
            except Exception as e:  # serveur surchargé : on essaie le suivant
                last = e
                print(f"  {url} : {e}", file=sys.stderr)
                time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"Overpass injoignable : {last}")


def _dist(a, b):
    lat = math.radians((a[0] + b[0]) / 2)
    return math.hypot((a[0] - b[0]) * 111_000, (a[1] - b[1]) * 111_000 * math.cos(lat))


def _point(el):
    if "center" in el:
        return el["center"]["lat"], el["center"]["lon"]
    if "lat" in el:
        return el["lat"], el["lon"]
    return None


def _names(tags):
    """Nom affiché (français de préférence) et autres noms cherchables (arabe, ancien nom…)."""
    main = tags.get("name:fr") or tags.get("name")
    others = [tags.get(k) for k in ("name", "name:ar", "name:en", "alt_name", "alt_name:fr", "old_name", "short_name", "official_name")]
    alts = []
    for n in others:
        for part in (n or "").split(";"):
            part = part.strip()
            if part and part != main and part not in alts:
                alts.append(part)
    return main, alts


def build(elements):
    areas, streets, pois = [], {}, []
    for el in elements:
        tags = el.get("tags", {})
        pt = _point(el)
        main, alts = _names(tags)
        if not pt or not main:
            continue
        if tags.get("place") in AREA_PLACES:
            areas.append({"n": main, "a": alts, "k": "area", "t": tags["place"], "lat": pt[0], "lon": pt[1]})
        elif "highway" in tags and el["type"] == "way":
            if tags["highway"] in ("bus_stop", "platform", "elevator", "street_lamp"):
                continue
            streets.setdefault(main, []).append((pt, alts, tags["highway"]))
        else:
            kind = next((tags[k] for k in POI_KEYS if k in tags), "lieu")
            pois.append({"n": main, "a": alts, "k": "poi", "t": kind if kind != "yes" else "lieu", "lat": pt[0], "lon": pt[1]})

    merged = []
    for name, parts in streets.items():
        groups = []  # regroupe les tronçons proches portant le même nom
        for pt, alts, hw in parts:
            for g in groups:
                if any(_dist(pt, q) <= STREET_MERGE_M for q in g["pts"]):
                    g["pts"].append(pt)
                    g["alts"].update(alts)
                    break
            else:
                groups.append({"pts": [pt], "alts": set(alts), "hw": hw})
        for g in groups:
            lat = sorted(p[0] for p in g["pts"])[len(g["pts"]) // 2]
            lon = sorted(p[1] for p in g["pts"])[len(g["pts"]) // 2]
            merged.append({"n": name, "a": sorted(g["alts"]), "k": "street", "t": g["hw"], "lat": lat, "lon": lon})

    # Quartier le plus proche, pour l'affichage et pour chercher « rue X cité Y ».
    small = [a for a in areas if a["t"] not in ("city", "town")] or areas
    for entry in merged + pois + areas:
        best = min(((_dist((entry["lat"], entry["lon"]), (a["lat"], a["lon"])), a) for a in small if a is not entry),
                   key=lambda x: x[0], default=None)
        if best and best[0] <= AREA_MAX_M:
            entry["area"] = best[1]["n"]
            entry["area_alts"] = best[1]["a"]
    for entry in merged + pois + areas:
        entry["lat"], entry["lon"] = round(entry["lat"], 6), round(entry["lon"], 6)
    return areas + merged + pois


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=ROOT / "backend/data/places.json")
    args = parser.parse_args()
    elements = []
    for q in _queries():
        part = fetch(q)
        print(f"{len(part)} objets", file=sys.stderr)
        elements += part
        time.sleep(2)
    entries = build(elements)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    payload = {"source": "OpenStreetMap (ODbL)", "generated": time.strftime("%Y-%m-%d"), "bbox": BBOX, "places": entries}
    args.out.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    kinds = {}
    for e in entries:
        kinds[e["k"]] = kinds.get(e["k"], 0) + 1
    print(f"{len(entries)} adresses et lieux {kinds} → {args.out}")


if __name__ == "__main__":
    main()

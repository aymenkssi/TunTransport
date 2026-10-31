#!/usr/bin/env python3
"""Construit les lignes ajoutées à la main (tools/extra_lines.json) au format de network.json.

Chaque arrêt est calé sur la route la plus proche, puis le tracé de chaque sens est calculé
sur les routes (OSRM public de FOSSGIS). Le résultat, tools/extra_lines.built.json, est
versionné : import_tunismapper.py l'ajoute au réseau sans avoir besoin du réseau internet.

Usage :
  python3 tools/build_extra_lines.py                 # recalcule extra_lines.built.json
  python3 tools/build_extra_lines.py --merge FICHIER # ajoute/remplace ces lignes dans un network.json
"""
import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
from geo import Shape  # noqa: E402

SOURCE = ROOT / "tools/extra_lines.json"
BUILT = ROOT / "tools/extra_lines.built.json"
OSRM = "https://routing.openstreetmap.de/routed-car"
USER_AGENT = "TunTransport-importer/0.1 (+https://github.com/aymenkssi/TunTransport)"


def osrm(path):
    req = urllib.request.Request(f"{OSRM}/{path}", headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.load(r)
    time.sleep(1.0)  # serveur public : une requête par seconde
    if data.get("code") != "Ok":
        raise RuntimeError(f"OSRM: {data.get('code')} {data.get('message', '')}")
    return data


def snap(lat, lon):
    lon2, lat2 = osrm(f"nearest/v1/driving/{lon},{lat}?number=1")["waypoints"][0]["location"]
    return round(lat2, 6), round(lon2, 6)


def road_shape(points):
    coords = ";".join(f"{lon},{lat}" for lat, lon in points)
    route = osrm(f"route/v1/driving/{coords}?overview=full&geometries=geojson")["routes"][0]
    return [[round(lat, 6), round(lon, 6)] for lon, lat in route["geometry"]["coordinates"]]


def build(spec):
    stops = []
    for i, s in enumerate(spec["stops"]):
        lat, lon = snap(s["lat"], s["lon"])
        stops.append({"id": f"{spec['id']}-{i}", "name": s["name"], "lat": lat, "lon": lon})
    directions = []
    for d, ordered in enumerate((stops, stops[::-1])):
        shape_pts = road_shape([(s["lat"], s["lon"]) for s in ordered])
        shape = Shape([tuple(p) for p in shape_pts])
        directions.append({
            "headsign": spec["headsigns"][d],
            "shape": shape_pts,
            "stops": [{"id": s["id"], "along_m": round(shape.project(s["lat"], s["lon"]).along_m)} for s in ordered],
        })
    return {
        "id": spec["id"], "mode": spec["mode"], "short_name": spec["short_name"], "long_name": spec["long_name"],
        "color": spec["color"], "operator": spec["operator"], "shape_source": "osrm",
        "stops": stops, "directions": directions, "timetable": {},
    }


def merge(network_file):
    built = json.loads(BUILT.read_text(encoding="utf-8"))["lines"]
    network = json.loads(Path(network_file).read_text(encoding="utf-8"))
    ids = {line["id"] for line in built}
    network["lines"] = [line for line in network["lines"] if line["id"] not in ids] + built
    Path(network_file).write_text(json.dumps(network, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{len(built)} ligne(s) ajoutée(s) à {network_file}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--merge", metavar="NETWORK_JSON")
    args = parser.parse_args()
    if args.merge:
        merge(args.merge)
        return
    spec = json.loads(SOURCE.read_text(encoding="utf-8"))
    lines = [build(line) for line in spec["lines"]]
    BUILT.write_text(json.dumps({"lines": lines}, ensure_ascii=False, indent=1), encoding="utf-8")
    for line in lines:
        km = [round(Shape([tuple(p) for p in d["shape"]]).length_m / 1000, 1) for d in line["directions"]]
        print(f"{line['short_name']} : {len(line['stops'])} arrêts, {km} km", file=sys.stderr)


if __name__ == "__main__":
    main()

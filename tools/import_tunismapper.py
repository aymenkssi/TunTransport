#!/usr/bin/env python3
"""Importe les lignes (métro, RFR, train, bus) publiées sur tunismapper.com
et produit network.json, le réseau servi par l'API (backend/data/network.json).

Source : les pages publiques ligne_details.php (autorisées par robots.txt),
listées dans sitemap-lignes.xml. L'API /backend/ est exclue par robots.txt et
n'est pas utilisée. Les pages sont mises en cache et téléchargées lentement.

Usage : python3 tools/import_tunismapper.py [--out chemin] [--cache dossier]
"""
import argparse
import difflib
import html
import json
import math
import re
import sys
import time
import unicodedata
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
from geo import EARTH_RADIUS_M, Shape, haversine_m  # noqa: E402

BASE = "https://www.tunismapper.com"
USER_AGENT = "TunTransport-importer/0.1 (+https://github.com/aymenkssi/TunTransport)"
DELAY_S = 1.0
SIMPLIFY_TOLERANCE_M = 5.0
MAX_STOP_OFFSET_M = 300.0  # un arrêt plus loin du tracé n'est pas desservi dans ce sens
MIN_MOVE_GAIN_M = 200.0
OUTLIER_DETOUR_M = 2000.0  # détour minimal imposé par un arrêt pour le juger mal géolocalisé
MODES = {"métro": "metro", "rfr": "rfr", "train": "train", "bus": "bus"}


def fetch(url, cache_dir):
    cached = cache_dir / re.sub(r"[^A-Za-z0-9]+", "_", url.removeprefix(BASE))
    if cached.exists():
        return cached.read_text(encoding="utf-8")
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                final_url = response.geturl()
                text = response.read().decode("utf-8")
            break
        except OSError:
            if attempt == 3:
                raise
            time.sleep(2 ** (attempt + 1))
    time.sleep(DELAY_S)
    if "ligne_details.php" in url and "ligne_details.php" not in final_url:
        text = ""  # ligne inexistante : le site redirige vers lignes.php
    cached.write_text(text, encoding="utf-8")
    return text


def route_ids(cache_dir):
    sitemap = fetch(f"{BASE}/sitemap-lignes.xml", cache_dir)
    return sorted({int(i) for i in re.findall(r"info_trafic_details\.php\?id=(\d+)", sitemap)})


def _js_var(page, name):
    match = re.search(rf"^var {name}\s*=\s*(.*?);\s*$", page, re.M)
    return json.loads(match.group(1)) if match else None


def normalize(name):
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()


def similarity(a, b):
    return difflib.SequenceMatcher(None, normalize(a), normalize(b)).ratio()


def simplify(points, tolerance_m):
    """Douglas-Peucker en projection équirectangulaire locale."""
    if len(points) < 3:
        return points
    lat0 = math.radians(points[0][0])
    xy = [(math.radians(lon) * math.cos(lat0) * EARTH_RADIUS_M, math.radians(lat) * EARTH_RADIUS_M)
          for lat, lon in points]
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        start, end = stack.pop()
        (ax, ay), (bx, by) = xy[start], xy[end]
        dx, dy = bx - ax, by - ay
        length = math.hypot(dx, dy)
        best_i, best_d = None, tolerance_m
        for i in range(start + 1, end):
            px, py = xy[i]
            d = (abs(dx * (ay - py) - dy * (ax - px)) / length) if length else math.hypot(px - ax, py - ay)
            if d > best_d:
                best_i, best_d = i, d
        if best_i is not None:
            keep[best_i] = True
            stack += [(start, best_i), (best_i, end)]
    return [p for p, k in zip(points, keep) if k]


def order_stops(points):
    """Remet en ordre une suite d'arrêts (lat, lon) pour en faire un tracé.

    La source liste parfois des arrêts d'embranchement à la fin, ou des arrêts
    aux coordonnées fausses. On déplace un arrêt tant que le placer ailleurs
    raccourcit nettement le parcours, puis on écarte ceux qui imposent encore un
    détour énorme. Retourne (indices dans l'ordre, indices écartés)."""
    def d(i, j):
        return haversine_m(points[i], points[j])

    def detour(seq, k):
        """Gain obtenu en retirant seq[k] du parcours."""
        if len(seq) < 3:
            return 0.0
        if k == 0:
            return d(seq[0], seq[1])
        if k == len(seq) - 1:
            return d(seq[-2], seq[-1])
        return d(seq[k - 1], seq[k]) + d(seq[k], seq[k + 1]) - d(seq[k - 1], seq[k + 1])

    def best_insertion(seq, i):
        """(coût, position) de la meilleure insertion de i dans seq."""
        options = [(d(i, seq[0]), 0), (d(seq[-1], i), len(seq))]
        options += [(d(a, i) + d(i, b) - d(a, b), k + 1) for k, (a, b) in enumerate(zip(seq, seq[1:]))]
        return min(options)

    seq = list(range(len(points)))
    for _ in range(len(points) ** 2):
        moved = False
        for k in sorted(range(len(seq)), key=lambda k: -detour(seq, k)):
            rest = seq[:k] + seq[k + 1:]
            cost, position = best_insertion(rest, seq[k])
            if cost < detour(seq, k) - MIN_MOVE_GAIN_M:
                seq = rest[:position] + [seq[k]] + rest[position:]
                moved = True
                break
        if not moved:
            break

    excluded = []
    while len(seq) > 2:
        k = max(range(len(seq)), key=lambda k: detour(seq, k))
        spacing = sorted(d(a, b) for a, b in zip(seq, seq[1:]))[len(seq) // 2]
        if detour(seq, k) < max(OUTLIER_DETOUR_M, 4 * spacing):
            break
        excluded.append(seq.pop(k))
    return seq, sorted(excluded)


def parse_line(route_id, page):
    """Retourne un dict ligne, ou None si la page n'en décrit pas une utilisable."""
    title = re.search(r"<title>Ligne de (\S+)", page)
    graph = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', page, re.S).group(1))
    route = next((g for g in graph["@graph"] if g.get("@type", "").endswith("Route")), None)
    raw_stops = _js_var(page, "stops") or []
    raw_shapes = _js_var(page, "shapes") or []
    if not title or route is None or len(raw_stops) < 2:
        return None

    name = html.unescape(route["name"])
    short_name, _, long_name = name.partition(" — ") if " — " in name else ("", "", name)
    stops = [{"id": str(s["stop_id"]), "name": html.unescape(s["name"]).strip(),
              "lat": round(float(s["lat"]), 6), "lon": round(float(s["lon"]), 6)} for s in raw_stops]
    headsigns = []
    for s in raw_stops:
        for h in s["horaires"]:
            headsign = h["direction"].strip()
            if headsign not in headsigns:
                headsigns.append(headsign)

    points = []
    if raw_shapes and len(raw_shapes[0]) >= 2:
        points = [(float(p["shape_pt_lat"]), float(p["shape_pt_lon"]))
                  for p in sorted(raw_shapes[0], key=lambda p: p["shape_pt_sequence"])]
        shape = Shape(points)
        near = sum(shape.project(s["lat"], s["lon"]).offset_m <= MAX_STOP_OFFSET_M for s in stops)
        if near < len(stops) / 2:
            points = []  # tracé publié incohérent avec les arrêts : on l'ignore
    if points:
        shape_source = "tunismapper"
    else:
        # À défaut : arrêts reliés en ligne droite, dans l'ordre le plus plausible.
        order, _ = order_stops([(s["lat"], s["lon"]) for s in stops])
        points = [(stops[i]["lat"], stops[i]["lon"]) for i in order]
        shape_source = "stops"
    points = simplify(points, SIMPLIFY_TOLERANCE_M)

    directions = []
    for pts in (points, points[::-1]):
        shape = Shape(pts)
        projected = [(shape.project(s["lat"], s["lon"]), s) for s in stops]
        served = sorted(((p.along_m, s) for p, s in projected if p.offset_m <= MAX_STOP_OFFSET_M),
                        key=lambda item: item[0])
        directions.append({
            "shape": [[round(lat, 6), round(lon, 6)] for lat, lon in pts],
            "stops": [{"id": s["id"], "along_m": round(along)} for along, s in served],
        })

    # Le sens « aller » est celui dont la girouette ressemble le plus au terminus d'arrivée.
    def terminus_name(direction):
        last = direction["stops"][-1]["id"] if direction["stops"] else stops[-1]["id"]
        return next(s["name"] for s in stops if s["id"] == last)

    forward_end, backward_end = terminus_name(directions[0]), terminus_name(directions[1])
    if len(headsigns) >= 2:
        h = max(headsigns, key=lambda x: similarity(x, forward_end) - similarity(x, backward_end))
        other = max((x for x in headsigns if x != h), key=lambda x: similarity(x, backward_end))
        directions[0]["headsign"], directions[1]["headsign"] = h, other
    else:
        directions[0]["headsign"], directions[1]["headsign"] = forward_end, backward_end

    timetable = {}
    for s in raw_stops:
        for h in s["horaires"]:
            timetable.setdefault(str(s["stop_id"]), {}).setdefault(h["direction"].strip(), []).append(h["time"])

    return {
        "id": str(route_id),
        "mode": MODES.get(title.group(1).lower(), "bus"),
        "short_name": short_name.strip(),
        "long_name": long_name.strip(),
        "color": (re.search(r'^var RC\s*=\s*"(#[0-9A-Fa-f]{6})"', page, re.M) or [None, None])[1],
        "operator": (route.get("provider") or {}).get("name", ""),
        "shape_source": shape_source,
        "stops": stops,
        "directions": directions,
        "timetable": {stop: {k: sorted(v) for k, v in by_dir.items()} for stop, by_dir in timetable.items()},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=ROOT / "backend/data/network.json")
    parser.add_argument("--cache", type=Path, default=ROOT / "tools/.cache")
    args = parser.parse_args()
    args.cache.mkdir(parents=True, exist_ok=True)

    lines, skipped = [], []
    ids = route_ids(args.cache)
    for n, route_id in enumerate(ids, 1):
        page = fetch(f"{BASE}/ligne_details.php?route_id={route_id}", args.cache)
        line = parse_line(route_id, page) if page else None
        (lines.append(line) if line else skipped.append(route_id))
        print(f"\r{n}/{len(ids)}", end="", file=sys.stderr)
    print(file=sys.stderr)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    network = {"source": f"{BASE}/lignes.php", "generated": time.strftime("%Y-%m-%d"), "lines": lines}
    args.out.write_text(json.dumps(network, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    by_mode = {}
    for line in lines:
        by_mode[line["mode"]] = by_mode.get(line["mode"], 0) + 1
    print(f"{len(lines)} lignes {by_mode} → {args.out}")
    print(f"ignorées (sans arrêts ou inexistantes) : {skipped}")


if __name__ == "__main__":
    main()

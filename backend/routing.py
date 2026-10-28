"""Calcul d'itinéraire : marche + métro, bus, RFR et train, avec correspondances.

- GET  /api/stops/search?q=      : arrêts dont le nom contient q (pour choisir départ et arrivée).
- POST /api/routes/plan          : itinéraires d'un point (ou arrêt) à un autre, au départ de maintenant.

Modèle d'attente à un arrêt, du plus fiable au moins fiable :
1. « en direct » : un véhicule partagé par des passagers approche de l'arrêt ;
2. « horaire »   : prochain passage de l'horaire (trains et RFR, dont les horaires sont réels) ;
3. « estimé »    : métro et bus, dont la source ne donne qu'un passage par heure : l'horaire sert à savoir
                   si la ligne circule encore, l'attente est estimée par la fréquence habituelle du mode.
Recherche : Dijkstra sur les arrêts, dépendant de l'heure, avec une pénalité par correspondance.
"""
import heapq
import math
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Literal, Optional, Tuple

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

import network
import trips
import vehicles as vh
from geo import haversine_m

TUNIS_TZ = timezone(timedelta(hours=1))  # pas d'heure d'été en Tunisie

WALK_SPEED_MPS = 1.2
WALK_DETOUR = 1.3            # les rues ne vont pas en ligne droite
MAX_ACCESS_WALK_M = 1200.0   # marche maximale vers le premier arrêt ou depuis le dernier
MAX_TRANSFER_WALK_M = 400.0  # marche maximale entre deux arrêts lors d'une correspondance
DIRECT_WALK_MAX_M = 2500.0
TRANSFER_PENALTY_S = 240     # une correspondance « coûte » 4 min de plus que le temps réel
MAX_BOARDINGS = 3
DWELL_S = 20                 # arrêt à chaque station
MAX_RESULTS = 3
SPEED_MPS = {"metro": 5.5, "bus": 4.2, "rfr": 11.0, "train": 13.0}
# Le TGM est classé « métro » par la source, mais c'est un train de banlieue (arrêts espacés, ~32 km/h).
SPEED_BY_LINE = {"TGM": 9.0}
# Tracé reconstruit en ligne droite entre arrêts : la distance réelle est plus longue (rues pour le bus).
STOPS_ONLY_DISTANCE_FACTOR = {"bus": 1.3}
STOPS_ONLY_DISTANCE_FACTOR_DEFAULT = 1.1
MAX_EXTRA_MIN = 45           # une alternative qui arrive plus de 45 min après la meilleure est écartée
TYPICAL_WAIT_S = {"metro": 300, "bus": 600}  # attente moyenne : la moitié d'une fréquence habituelle
SCHEDULED_MODES = {"rfr", "train"}
LAST_SERVICE_GRACE_MIN = 30
MAX_SCHEDULED_WAIT_MIN = 180
MAX_LIVE_HORIZON_S = 1800


# ------------------------ Graphe ------------------------
@dataclass
class Pattern:
    line: "network.LoadedLine"
    direction: int
    stops: List[Tuple[str, float]]  # (id d'arrêt, abscisse)
    headsign: str

    @property
    def mode(self) -> str:
        return self.line.data["mode"]


@dataclass
class Graph:
    stops: Dict[str, dict] = field(default_factory=dict)
    patterns: List[Pattern] = field(default_factory=list)
    at_stop: Dict[str, List[Tuple[int, int]]] = field(default_factory=lambda: defaultdict(list))
    transfers: Dict[str, List[Tuple[str, float]]] = field(default_factory=lambda: defaultdict(list))


_graph_cache: Dict[int, Graph] = {}


def _cell(lat: float, lon: float, size: float = 0.01) -> Tuple[int, int]:
    return int(lat // size), int(lon // size)


def graph() -> Graph:
    net = network.current()
    if id(net) in _graph_cache:
        return _graph_cache[id(net)]
    g = Graph()
    for line in net.lines.values():
        for s in line.data["stops"]:
            g.stops.setdefault(s["id"], {**s, "lines": []})["lines"].append(line.id)
        for d, direction in enumerate(line.data["directions"]):
            stops = [(s["id"], s["along_m"]) for s in direction["stops"]]
            if len(stops) < 2:
                continue
            g.patterns.append(Pattern(line, d, stops, direction["headsign"]))
            for pos, (stop_id, _) in enumerate(stops):
                g.at_stop[stop_id].append((len(g.patterns) - 1, pos))
    grid = defaultdict(list)
    for sid, s in g.stops.items():
        grid[_cell(s["lat"], s["lon"])].append(sid)
    for sid, s in g.stops.items():
        ci, cj = _cell(s["lat"], s["lon"])
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                for other in grid.get((ci + di, cj + dj), []):
                    if other == sid:
                        continue
                    o = g.stops[other]
                    dist = haversine_m((s["lat"], s["lon"]), (o["lat"], o["lon"]))
                    if dist <= MAX_TRANSFER_WALK_M:
                        g.transfers[sid].append((other, dist))
    _graph_cache.clear()
    _graph_cache[id(net)] = g
    return g


def stops_near(g: Graph, lat: float, lon: float, radius_m: float) -> List[Tuple[str, float]]:
    out = []
    span = radius_m / 111_000 + 0.01
    for sid, s in g.stops.items():
        if abs(s["lat"] - lat) > span or abs(s["lon"] - lon) > span * 1.3:
            continue
        dist = haversine_m((lat, lon), (s["lat"], s["lon"]))
        if dist <= radius_m:
            out.append((sid, dist))
    return out


def walk_s(dist_m: float) -> float:
    return dist_m * WALK_DETOUR / WALK_SPEED_MPS


# ------------------------ Attente ------------------------
def _minutes(hhmm: str) -> Optional[int]:
    try:
        h, m = hhmm.split(":")
        return int(h) * 60 + int(m)
    except ValueError:
        return None


def scheduled_wait(p: Pattern, stop_id: str, t: float) -> Tuple[Optional[float], str]:
    """(attente en secondes, origine) d'après l'horaire ; (None, …) si la ligne ne circule pas."""
    times = p.line.data.get("timetable", {}).get(stop_id, {}).get(p.headsign)
    if not times:
        times = [x for by_dir in p.line.data.get("timetable", {}).values() for x in by_dir.get(p.headsign, [])]
    minutes = sorted(m for m in (_minutes(x) for x in times) if m is not None)
    local = datetime.fromtimestamp(t, TUNIS_TZ)
    now_min = local.hour * 60 + local.minute + local.second / 60
    if not minutes:
        return float(TYPICAL_WAIT_S.get(p.mode, 900)), "estimé"
    if p.mode in SCHEDULED_MODES:
        nxt = next((m for m in minutes if m >= now_min), None)
        if nxt is None or nxt - now_min > MAX_SCHEDULED_WAIT_MIN:
            return None, "horaire"
        return (nxt - now_min) * 60, "horaire"
    # Métro et bus : service entre le premier et le dernier passage, attente habituelle.
    if now_min < minutes[0] - 15 or now_min > minutes[-1] + LAST_SERVICE_GRACE_MIN:
        return None, "estimé"
    first = max(0.0, (minutes[0] - now_min) * 60)
    return max(first, float(TYPICAL_WAIT_S.get(p.mode, 600))), "estimé"


def live_wait(p: Pattern, stop_along: float, t: float, now: float, live: List[vh.Vehicle]) -> Optional[float]:
    """Attente d'après un véhicule en direct qui n'a pas encore passé l'arrêt."""
    best = None
    for v in live:
        if v.line_id != p.line.id or v.direction != p.direction:
            continue
        eta = vh.eta_seconds(v, stop_along, now)
        if eta is None:
            continue
        arrival = now + eta
        if t <= arrival <= now + MAX_LIVE_HORIZON_S:
            wait = arrival - t
            best = wait if best is None else min(best, wait)
    return best


def wait_at(p: Pattern, pos: int, t: float, now: float, live: List[vh.Vehicle]) -> Tuple[Optional[float], str]:
    stop_id, along = p.stops[pos]
    lw = live_wait(p, along, t, now, live)
    sw, source = scheduled_wait(p, stop_id, t)
    if lw is not None and (sw is None or lw <= sw + 120):
        return lw, "en direct"
    return sw, source


def ride_s(p: Pattern, i: int, j: int) -> float:
    dist = p.stops[j][1] - p.stops[i][1]
    if p.line.data.get("shape_source") != "tunismapper":
        dist *= STOPS_ONLY_DISTANCE_FACTOR.get(p.mode, STOPS_ONLY_DISTANCE_FACTOR_DEFAULT)
    speed = SPEED_BY_LINE.get(p.line.data["short_name"], SPEED_MPS.get(p.mode, 5.0))
    return max(dist, 0.0) / speed + DWELL_S * (j - i)


# ------------------------ Recherche ------------------------
@dataclass(order=True)
class _Label:
    priority: float
    arrival: float = field(compare=False)
    node: str = field(compare=False)
    boardings: int = field(compare=False)
    prev: Optional["_Label"] = field(compare=False, default=None)
    leg: Optional[dict] = field(compare=False, default=None)


def _search(g: Graph, origin: dict, dest: dict, t0: float, now: float, live: List[vh.Vehicle],
            banned_lines: frozenset) -> Optional[_Label]:
    heap: List[_Label] = []
    best: Dict[str, float] = {}

    def push(label: _Label):
        if label.priority < best.get(label.node, math.inf):
            best[label.node] = label.priority
            heapq.heappush(heap, label)

    start = _Label(0.0, t0, "O", 0)
    for sid, dist in origin["stops"]:
        dur = walk_s(dist)
        push(_Label(dur, t0 + dur, sid, 0, start, {"kind": "walk", "from": "O", "to": sid, "distance_m": dist}))
    dest_access = dict(dest["stops"])

    while heap:
        label = heapq.heappop(heap)
        if label.priority > best.get(label.node, math.inf):
            continue
        if label.node == "D":
            return label
        u, t = label.node, label.arrival
        if u in dest_access:
            dur = walk_s(dest_access[u])
            push(_Label(label.priority + dur, t + dur, "D", label.boardings, label,
                        {"kind": "walk", "from": u, "to": "D", "distance_m": dest_access[u]}))
        if label.leg and label.leg["kind"] == "ride":
            for other, dist in g.transfers.get(u, []):
                dur = walk_s(dist)
                push(_Label(label.priority + dur, t + dur, other, label.boardings, label,
                            {"kind": "walk", "from": u, "to": other, "distance_m": dist}))
        if label.boardings >= MAX_BOARDINGS:
            continue
        came_by = label.leg.get("pattern") if label.leg else None
        for pi, pos in g.at_stop.get(u, []):
            p = g.patterns[pi]
            if pi == came_by or pos == len(p.stops) - 1 or p.line.id in banned_lines:
                continue
            wait, source = wait_at(p, pos, t, now, live)
            if wait is None:
                continue
            board = t + wait
            penalty = TRANSFER_PENALTY_S if label.boardings else 0
            for j in range(pos + 1, len(p.stops)):
                arrival = board + ride_s(p, pos, j)
                push(_Label(label.priority + (arrival - t) + penalty, arrival, p.stops[j][0], label.boardings + 1, label,
                            {"kind": "ride", "pattern": pi, "from_pos": pos, "to_pos": j, "wait": wait,
                             "source": source, "board": board}))
    return None


def _legs(g: Graph, end: _Label, origin: dict, dest: dict) -> List[dict]:
    chain = []
    label = end
    while label.prev is not None:
        chain.append(label)
        label = label.prev
    chain.reverse()

    def place(node: str) -> dict:
        if node == "O":
            return {"name": origin["name"], "lat": origin["lat"], "lon": origin["lon"]}
        if node == "D":
            return {"name": dest["name"], "lat": dest["lat"], "lon": dest["lon"]}
        s = g.stops[node]
        return {"name": s["name"], "lat": s["lat"], "lon": s["lon"], "stop_id": node}

    legs = []
    prev_arrival = chain[0].prev.arrival if chain else 0.0
    for label in chain:
        leg = label.leg
        if leg["kind"] == "walk":
            a, b = place(leg["from"]), place(leg["to"])
            if legs and legs[-1]["kind"] == "walk":  # fusionne les marches successives
                legs[-1].update(to=b, distance_m=legs[-1]["distance_m"] + leg["distance_m"], arrive=label.arrival)
                legs[-1]["path"].append([b["lat"], b["lon"]])
            elif leg["distance_m"] >= 1 or ("O" in (leg["from"], leg["to"]) and not origin["is_stop"]) \
                    or ("D" in (leg["from"], leg["to"]) and not dest["is_stop"]):
                legs.append({"kind": "walk", "from": a, "to": b, "distance_m": leg["distance_m"],
                             "depart": prev_arrival, "arrive": label.arrival,
                             "path": [[a["lat"], a["lon"]], [b["lat"], b["lon"]]]})
        else:
            p = g.patterns[leg["pattern"]]
            i, j = leg["from_pos"], leg["to_pos"]
            shape = p.line.shapes[p.direction]
            legs.append({
                "kind": "ride",
                "line": p.line.summary(),
                "direction": p.direction,
                "headsign": p.headsign,
                "from": place(p.stops[i][0]),
                "to": place(p.stops[j][0]),
                "stops": j - i,
                "wait_s": round(leg["wait"]),
                "wait_source": leg["source"],
                "depart": leg["board"],
                "arrive": label.arrival,
                "path": [[round(a, 6), round(b, 6)] for a, b in shape.slice(p.stops[i][1], p.stops[j][1])],
                "dashed": p.line.data.get("shape_source") != "tunismapper",
            })
        prev_arrival = label.arrival
    for leg in legs:
        leg["distance_m"] = round(leg.get("distance_m", 0)) if leg["kind"] == "walk" else None
        leg["duration_s"] = round(leg["arrive"] - leg["depart"])
    return legs


# ------------------------ API ------------------------
class Place(BaseModel):
    stop_id: Optional[str] = Field(default=None, max_length=32)
    lat: Optional[float] = Field(default=None, ge=-90, le=90)
    lon: Optional[float] = Field(default=None, ge=-180, le=180)
    name: Optional[str] = Field(default=None, max_length=120)


class PlanRequest(BaseModel):
    origin: Place
    destination: Place


class LegPlace(BaseModel):
    name: str
    lat: float
    lon: float
    stop_id: Optional[str] = None


class Leg(BaseModel):
    kind: Literal["walk", "ride"]
    from_: LegPlace = Field(alias="from")
    to: LegPlace
    depart: str
    arrive: str
    duration_s: int
    path: List[List[float]]
    distance_m: Optional[int] = None
    line: Optional[network.LineSummary] = None
    direction: Optional[int] = None
    headsign: Optional[str] = None
    stops: Optional[int] = None
    wait_s: Optional[int] = None
    wait_source: Optional[Literal["en direct", "horaire", "estimé"]] = None
    dashed: Optional[bool] = None

    model_config = {"populate_by_name": True}


class Itinerary(BaseModel):
    depart: str
    arrive: str
    duration_s: int
    walk_m: int
    transfers: int
    live: bool
    legs: List[Leg]


def _hhmm(ts: float) -> str:
    return datetime.fromtimestamp(ts, TUNIS_TZ).strftime("%H:%M")


def _resolve(g: Graph, place: Place, default_name: str) -> dict:
    if place.stop_id:
        s = g.stops.get(place.stop_id)
        if not s:
            raise HTTPException(404, "Unknown stop")
        stops = [(place.stop_id, 0.0)] + [(sid, d) for sid, d in stops_near(g, s["lat"], s["lon"], MAX_TRANSFER_WALK_M) if sid != place.stop_id]
        return {"name": s["name"], "lat": s["lat"], "lon": s["lon"], "stops": stops, "is_stop": True}
    if place.lat is None or place.lon is None:
        raise HTTPException(422, "A stop_id or lat/lon is required")
    return {"name": place.name or default_name, "lat": place.lat, "lon": place.lon,
            "stops": stops_near(g, place.lat, place.lon, MAX_ACCESS_WALK_M), "is_stop": False}


def _itinerary(legs: List[dict], depart: float) -> Itinerary:
    """`depart` : heure à laquelle on part (maintenant), attente au premier arrêt comprise dans la durée."""
    rides = [l for l in legs if l["kind"] == "ride"]
    arrive = legs[-1]["arrive"]
    out = []
    for leg in legs:
        leg = {**leg, "depart": _hhmm(leg["depart"]), "arrive": _hhmm(leg["arrive"])}
        out.append(Leg(**leg))
    return Itinerary(
        depart=_hhmm(depart), arrive=_hhmm(arrive), duration_s=round(arrive - depart),
        walk_m=round(sum(l["distance_m"] or 0 for l in legs if l["kind"] == "walk")),
        transfers=max(0, len(rides) - 1), live=any(r["wait_source"] == "en direct" for r in rides), legs=out,
    )


router = APIRouter(prefix="/api")


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return " ".join(text.replace("-", " ").split())


@router.get("/stops/search")
async def search_stops(q: str, limit: int = 12):
    g = graph()
    query = _normalize(q)
    if len(query) < 2:
        return []
    net = network.current()
    hits = []
    for sid, s in g.stops.items():
        name = _normalize(s["name"])
        if query in name:
            hits.append((not name.startswith(query), len(name), sid, s))
    hits.sort(key=lambda h: h[:2])
    out = []
    for _, _, sid, s in hits[: max(1, min(limit, 30))]:
        lines = [net.lines[l] for l in dict.fromkeys(s["lines"]) if l in net.lines]
        out.append({"id": sid, "name": s["name"], "lat": s["lat"], "lon": s["lon"],
                    "lines": [l.summary() for l in lines][:8]})
    return out


@router.post("/routes/plan", response_model=List[Itinerary], response_model_by_alias=True)
async def plan(payload: PlanRequest):
    g = graph()
    origin = _resolve(g, payload.origin, "Départ")
    dest = _resolve(g, payload.destination, "Arrivée")
    now = trips.now()
    live = [v for v in vh.cluster_vehicles(await trips._fresh_contributions(), now) if vh.reliability(v, now)[1] != "expiré"]

    results: List[Itinerary] = []
    seen = set()
    banned: frozenset = frozenset()
    for _ in range(MAX_RESULTS + 2):
        end = _search(g, origin, dest, now, now, live, banned)
        if end is None:
            break
        legs = _legs(g, end, origin, dest)
        rides = tuple(l["line"]["id"] for l in legs if l["kind"] == "ride")
        if rides and rides not in seen:
            seen.add(rides)
            results.append(_itinerary(legs, now))
        if not rides or len(results) >= MAX_RESULTS:
            break
        # Alternative suivante : sans la ligne la plus longue de cet itinéraire.
        longest = max((l for l in legs if l["kind"] == "ride"), key=lambda l: l["arrive"] - l["depart"])
        banned = banned | {longest["line"]["id"]}

    direct = haversine_m((origin["lat"], origin["lon"]), (dest["lat"], dest["lon"]))
    if direct <= DIRECT_WALK_MAX_M:
        dur = walk_s(direct)
        results.append(_itinerary([{
            "kind": "walk", "from": {k: origin[k] for k in ("name", "lat", "lon")}, "to": {k: dest[k] for k in ("name", "lat", "lon")},
            "distance_m": round(direct), "depart": now, "arrive": now + dur, "duration_s": round(dur),
            "path": [[origin["lat"], origin["lon"]], [dest["lat"], dest["lon"]]],
        }], now))
    results.sort(key=lambda r: (r.duration_s + TRANSFER_PENALTY_S * r.transfers))
    if results:
        fastest = min(r.duration_s for r in results)
        results = [r for r in results if r.duration_s <= fastest + MAX_EXTRA_MIN * 60]
    return results[:MAX_RESULTS + 1]

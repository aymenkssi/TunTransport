"""Vérifie qu'une trace GPS de passager est compatible avec la ligne et le sens
déclarés, et propose des lignes candidates quand le passager n'a rien déclaré."""
import statistics
from dataclasses import dataclass, field

MAX_ACCURACY_M = 50.0        # fixes moins précis ignorés
MAX_OFFSET_M = 40.0          # écart toléré au tracé (au-delà de la précision GPS)
MIN_ON_ROUTE_RATIO = 0.8     # part minimale de fixes proches du tracé
MIN_FIXES = 3
MIN_DURATION_S = 20.0
BACKWARD_TOLERANCE_M = 30.0  # recul toléré (bruit GPS) avant de conclure au mauvais sens
MAX_SPEED_MPS = 33.0         # ~120 km/h : au-delà, données aberrantes


@dataclass(frozen=True)
class GpsFix:
    t: float           # secondes (epoch)
    lat: float
    lon: float
    accuracy_m: float = 10.0


@dataclass
class Line:
    id: str
    mode: str                                    # bus, tram, metro, train, louage...
    shapes: dict = field(default_factory=dict)   # sens -> Shape


@dataclass(frozen=True)
class MatchResult:
    ok: bool
    reason: str
    along_m: float = 0.0
    speed_mps: float = 0.0
    mean_offset_m: float = 0.0


def match_trace(fixes, line, direction):
    shape = line.shapes.get(direction)
    if shape is None:
        return MatchResult(False, "sens inconnu pour cette ligne")

    fixes = sorted((f for f in fixes if f.accuracy_m <= MAX_ACCURACY_M), key=lambda f: f.t)
    if len(fixes) < MIN_FIXES or fixes[-1].t - fixes[0].t < MIN_DURATION_S:
        return MatchResult(False, "trace trop courte")

    projections = [shape.project(f.lat, f.lon) for f in fixes]
    on_route = [p.offset_m <= max(MAX_OFFSET_M, f.accuracy_m) for p, f in zip(projections, fixes)]
    mean_offset = statistics.fmean(p.offset_m for p in projections)
    if sum(on_route) / len(on_route) < MIN_ON_ROUTE_RATIO:
        return MatchResult(False, "hors du tracé de la ligne", mean_offset_m=mean_offset)

    progress = projections[-1].along_m - projections[0].along_m
    if progress < -BACKWARD_TOLERANCE_M:
        return MatchResult(False, "mauvais sens de circulation", mean_offset_m=mean_offset)

    speed = max(progress, 0.0) / (fixes[-1].t - fixes[0].t)
    if speed > MAX_SPEED_MPS:
        return MatchResult(False, "vitesse incohérente", mean_offset_m=mean_offset)

    return MatchResult(True, "ok", projections[-1].along_m, speed, mean_offset)


def suggest_lines(fixes, lines, limit=3):
    """Classe les couples (ligne, sens) compatibles avec la trace, du plus proche
    au moins proche : sert à pré-remplir le choix du passager."""
    candidates = []
    for line in lines:
        for direction in line.shapes:
            result = match_trace(fixes, line, direction)
            if result.ok:
                candidates.append((result.mean_offset_m, line.id, direction))
    candidates.sort()
    return [(line_id, direction) for _, line_id, direction in candidates[:limit]]

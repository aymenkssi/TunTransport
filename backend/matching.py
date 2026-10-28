"""Vérifie qu'une trace GPS de passager est compatible avec la ligne et le sens déclarés.

Le serveur est l'autorité : une position n'est publiée que si ce contrôle réussit.
"""
import statistics
from dataclasses import dataclass

MAX_ACCURACY_M = 50.0           # fixes moins précis ignorés
MAX_OFFSET_MEASURED_M = 40.0    # écart toléré à un tracé relevé sur le terrain
MAX_OFFSET_STOPS_ONLY_M = 150.0  # écart toléré quand le tracé relie seulement les arrêts
MIN_ON_ROUTE_RATIO = 0.8
MIN_FIXES = 3
MIN_DURATION_S = 20.0
BACKWARD_TOLERANCE_M = 30.0     # recul toléré (bruit GPS) avant de conclure au mauvais sens
MAX_SPEED_MPS = 33.0            # ~120 km/h : au-delà, données aberrantes

REASONS = {
    "too_short": "trace trop courte",
    "off_route": "hors du tracé de la ligne",
    "wrong_direction": "mauvais sens de circulation",
    "implausible_speed": "vitesse incohérente",
}


@dataclass(frozen=True)
class GpsFix:
    t: float
    lat: float
    lon: float
    accuracy_m: float = 10.0


@dataclass(frozen=True)
class MatchResult:
    ok: bool
    reason: str  # "ok" ou une clé de REASONS
    along_m: float = 0.0
    speed_mps: float = 0.0
    mean_offset_m: float = 0.0


def max_offset_for(shape_source):
    return MAX_OFFSET_MEASURED_M if shape_source == "tunismapper" else MAX_OFFSET_STOPS_ONLY_M


def match_trace(fixes, shape, max_offset_m=MAX_OFFSET_MEASURED_M):
    fixes = sorted((f for f in fixes if f.accuracy_m <= MAX_ACCURACY_M), key=lambda f: f.t)
    if len(fixes) < MIN_FIXES or fixes[-1].t - fixes[0].t < MIN_DURATION_S:
        return MatchResult(False, "too_short")

    projections = [shape.project(f.lat, f.lon) for f in fixes]
    on_route = [p.offset_m <= max(max_offset_m, f.accuracy_m) for p, f in zip(projections, fixes)]
    mean_offset = statistics.fmean(p.offset_m for p in projections)
    if sum(on_route) / len(on_route) < MIN_ON_ROUTE_RATIO:
        return MatchResult(False, "off_route", mean_offset_m=mean_offset)

    progress = projections[-1].along_m - projections[0].along_m
    if progress < -BACKWARD_TOLERANCE_M:
        return MatchResult(False, "wrong_direction", mean_offset_m=mean_offset)

    speed = max(progress, 0.0) / (fixes[-1].t - fixes[0].t)
    if speed > MAX_SPEED_MPS:
        return MatchResult(False, "implausible_speed", mean_offset_m=mean_offset)

    return MatchResult(True, "ok", projections[-1].along_m, speed, mean_offset)

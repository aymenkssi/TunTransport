"""Regroupe les contributions des passagers d'une même ligne en véhicules,
note leur fiabilité et estime les temps d'arrivée aux arrêts."""
import statistics
from dataclasses import dataclass

SAME_VEHICLE_GAP_M = 120.0       # deux passagers plus éloignés = deux véhicules
SAME_VEHICLE_SPEED_DIFF = 4.0    # m/s ; au-delà, l'un roule et l'autre non
FRESH_AGE_S = 30.0
STALE_AGE_S = 120.0              # au-delà : « position obsolète »
EXPIRED_AGE_S = 300.0            # au-delà : le véhicule n'est plus affiché
MAX_EXTRAPOLATION_S = 60.0
DEFAULT_SPEED_MPS = 5.0          # ~18 km/h, vitesse commerciale urbaine typique
MIN_SPEED_MPS = 2.0
MAX_SPEED_MPS = 20.0


@dataclass(frozen=True)
class Contribution:
    user_id: str
    line_id: str
    direction: str
    along_m: float
    speed_mps: float
    t: float


@dataclass
class Vehicle:
    line_id: str
    direction: str
    along_m: float
    speed_mps: float
    last_update: float
    contributors: tuple
    spread_m: float

    def estimated_along(self, now):
        """Position extrapolée à l'instant `now` (bornée pour ne pas inventer)."""
        age = min(max(now - self.last_update, 0.0), MAX_EXTRAPOLATION_S)
        return self.along_m + self.speed_mps * age


def cluster_vehicles(contributions, now):
    """Une contribution = dernier état connu d'un passager. On ramène toutes les
    positions à l'instant `now`, puis on découpe le long du tracé là où l'écart
    de position ou de vitesse est trop grand."""
    groups = {}
    for c in contributions:
        if now - c.t <= EXPIRED_AGE_S:
            groups.setdefault((c.line_id, c.direction), []).append(c)

    vehicles = []
    for (line_id, direction), items in groups.items():
        def aligned(c):
            return c.along_m + c.speed_mps * min(now - c.t, MAX_EXTRAPOLATION_S)

        items.sort(key=aligned)
        current = [items[0]]
        for prev, c in zip(items, items[1:]):
            if (aligned(c) - aligned(prev) > SAME_VEHICLE_GAP_M
                    or abs(c.speed_mps - prev.speed_mps) > SAME_VEHICLE_SPEED_DIFF):
                vehicles.append(_build(line_id, direction, current))
                current = []
            current.append(c)
        vehicles.append(_build(line_id, direction, current))
    return vehicles


def _build(line_id, direction, items):
    last = max(c.t for c in items)
    # Toutes les positions ramenées à l'instant de la contribution la plus récente.
    positions = [c.along_m + c.speed_mps * (last - c.t) for c in items]
    return Vehicle(
        line_id=line_id,
        direction=direction,
        along_m=statistics.median(positions),
        speed_mps=statistics.median(c.speed_mps for c in items),
        last_update=last,
        contributors=tuple(sorted({c.user_id for c in items})),
        spread_m=max(positions) - min(positions),
    )


def reliability(vehicle, now):
    """Retourne (score entre 0 et 1, statut affichable)."""
    age = now - vehicle.last_update
    if age > EXPIRED_AGE_S:
        return 0.0, "expiré"
    freshness = 1.0 if age <= FRESH_AGE_S else max(0.0, 1 - (age - FRESH_AGE_S) / (STALE_AGE_S - FRESH_AGE_S))
    confirmation = 1 - 0.5 ** len(vehicle.contributors)    # 1 → 0,5 ; 2 → 0,75 ; 3 → 0,875
    agreement = 1.0 - 0.5 * min(vehicle.spread_m / SAME_VEHICLE_GAP_M, 1.0)
    score = freshness * confirmation * agreement
    if age > STALE_AGE_S:
        return score, "obsolète"
    if score >= 0.6:
        return score, "fiable"
    return score, "probable"


def eta_seconds(vehicle, stop_along_m, now):
    """Temps estimé avant l'arrivée du véhicule à l'arrêt, ou None s'il l'a dépassé.
    La vitesse instantanée est bornée : un bus à l'arrêt n'a pas un ETA infini."""
    remaining = stop_along_m - vehicle.estimated_along(now)
    if remaining < 0:
        return None
    speed = vehicle.speed_mps if vehicle.speed_mps > 0 else DEFAULT_SPEED_MPS
    speed = min(max(speed, MIN_SPEED_MPS), MAX_SPEED_MPS)
    return remaining / speed

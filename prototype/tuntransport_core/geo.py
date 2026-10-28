import math
from dataclasses import dataclass

EARTH_RADIUS_M = 6_371_000.0


def haversine_m(a, b):
    """Distance en mètres entre deux points (lat, lon)."""
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    h = (math.sin((lat2 - lat1) / 2) ** 2
         + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2)
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(h))


@dataclass(frozen=True)
class Projection:
    along_m: float   # abscisse curviligne depuis le terminus de départ
    offset_m: float  # distance latérale entre le point et le tracé


class Shape:
    """Tracé d'une ligne dans un sens (polyligne ordonnée de points (lat, lon))."""

    def __init__(self, points):
        if len(points) < 2:
            raise ValueError("un tracé doit contenir au moins deux points")
        self.points = list(points)
        self.cumulative_m = [0.0]
        for a, b in zip(self.points, self.points[1:]):
            self.cumulative_m.append(self.cumulative_m[-1] + haversine_m(a, b))

    @property
    def length_m(self):
        return self.cumulative_m[-1]

    def project(self, lat, lon):
        """Projette un point sur le tracé (projection équirectangulaire locale,
        suffisante à l'échelle d'une ville)."""
        cos_lat = math.cos(math.radians(lat))

        def to_xy(p):
            return (math.radians(p[1] - lon) * cos_lat * EARTH_RADIUS_M,
                    math.radians(p[0] - lat) * EARTH_RADIUS_M)

        best = None
        for i, (a, b) in enumerate(zip(self.points, self.points[1:])):
            ax, ay = to_xy(a)
            bx, by = to_xy(b)
            dx, dy = bx - ax, by - ay
            seg2 = dx * dx + dy * dy
            t = 0.0 if seg2 == 0 else max(0.0, min(1.0, -(ax * dx + ay * dy) / seg2))
            offset = math.hypot(ax + t * dx, ay + t * dy)
            if best is None or offset < best.offset_m:
                seg_len = self.cumulative_m[i + 1] - self.cumulative_m[i]
                best = Projection(self.cumulative_m[i] + t * seg_len, offset)
        return best

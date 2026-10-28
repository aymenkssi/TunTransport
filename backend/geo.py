"""Géométrie le long du tracé d'une ligne (abscisse curviligne)."""
import bisect
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

    def point_at(self, along_m):
        """Point (lat, lon) situé à `along_m` mètres du début du tracé."""
        along_m = max(0.0, min(along_m, self.length_m))
        i = max(1, bisect.bisect_left(self.cumulative_m, along_m))
        start, end = self.cumulative_m[i - 1], self.cumulative_m[i]
        t = 0.0 if end == start else (along_m - start) / (end - start)
        (lat1, lon1), (lat2, lon2) = self.points[i - 1], self.points[i]
        return lat1 + t * (lat2 - lat1), lon1 + t * (lon2 - lon1)

    def bounds(self, margin_m=0.0):
        """(lat_min, lon_min, lat_max, lon_max) élargi de `margin_m` mètres."""
        lats = [p[0] for p in self.points]
        lons = [p[1] for p in self.points]
        dlat = math.degrees(margin_m / EARTH_RADIUS_M)
        dlon = dlat / max(math.cos(math.radians(sum(lats) / len(lats))), 0.01)
        return min(lats) - dlat, min(lons) - dlon, max(lats) + dlat, max(lons) + dlon

    def slice(self, start_m, end_m):
        """Points du tracé entre deux abscisses (inclus), pour dessiner un trajet."""
        start_m, end_m = sorted((max(0.0, start_m), min(end_m, self.length_m)))
        inner = [p for p, c in zip(self.points, self.cumulative_m) if start_m < c < end_m]
        return [self.point_at(start_m), *inner, self.point_at(end_m)]

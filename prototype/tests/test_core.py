import unittest

from tuntransport_core.geo import Shape
from tuntransport_core.line_matching import GpsFix, Line, match_trace, suggest_lines
from tuntransport_core.vehicles import (Contribution, cluster_vehicles, eta_seconds,
                                        reliability)

LAT = 36.80                       # Tunis
M_PER_DEG_LON = 89_150.0          # à cette latitude, approximativement

# Ligne fictive est-ouest, et une ligne parallèle à ~550 m au nord.
EAST = [(LAT, 10.15), (LAT, 10.17), (LAT, 10.20)]
LINE_1 = Line("L1", "bus", {"aller": Shape(EAST), "retour": Shape(EAST[::-1])})
LINE_2 = Line("L2", "bus", {"aller": Shape([(LAT + 0.005, lon) for _, lon in EAST])})


def trace(start_lon, speed_mps, n=6, step_s=10, lat=LAT, t0=1000.0):
    return [GpsFix(t0 + i * step_s, lat, start_lon + speed_mps * i * step_s / M_PER_DEG_LON)
            for i in range(n)]


class LineMatchingTest(unittest.TestCase):
    def test_accepts_passenger_on_declared_line(self):
        result = match_trace(trace(10.16, 8.0), LINE_1, "aller")
        self.assertTrue(result.ok, result.reason)
        self.assertAlmostEqual(result.speed_mps, 8.0, delta=0.3)

    def test_rejects_wrong_direction(self):
        result = match_trace(trace(10.16, 8.0), LINE_1, "retour")
        self.assertFalse(result.ok)
        self.assertEqual(result.reason, "mauvais sens de circulation")

    def test_rejects_passenger_off_route(self):
        result = match_trace(trace(10.16, 8.0, lat=LAT + 0.002), LINE_1, "aller")
        self.assertEqual(result.reason, "hors du tracé de la ligne")

    def test_ignores_imprecise_fixes(self):
        fixes = [GpsFix(f.t, f.lat, f.lon, accuracy_m=200) for f in trace(10.16, 8.0)]
        self.assertEqual(match_trace(fixes, LINE_1, "aller").reason, "trace trop courte")

    def test_suggests_nearest_compatible_line(self):
        self.assertEqual(suggest_lines(trace(10.16, 8.0), [LINE_1, LINE_2]), [("L1", "aller")])


class VehicleTest(unittest.TestCase):
    def test_passengers_close_together_form_one_vehicle(self):
        now = 2000.0
        vehicles = cluster_vehicles([
            Contribution("a", "L1", "aller", 1000, 8, now - 5),
            Contribution("b", "L1", "aller", 1030, 8, now - 2),
            Contribution("c", "L1", "aller", 2500, 8, now - 1),   # bus suivant
            Contribution("d", "L1", "retour", 1000, 8, now - 1),  # autre sens
        ], now)
        by_size = sorted(len(v.contributors) for v in vehicles)
        self.assertEqual(by_size, [1, 1, 2])

    def test_stopped_and_moving_passengers_are_split(self):
        now = 2000.0
        vehicles = cluster_vehicles([
            Contribution("a", "L1", "aller", 1000, 0.0, now),     # bus à l'arrêt
            Contribution("b", "L1", "aller", 1050, 10.0, now),    # bus qui le double
        ], now)
        self.assertEqual(len(vehicles), 2)

    def test_reliability_grows_with_confirmations_and_decays_with_age(self):
        now = 2000.0
        alone = cluster_vehicles([Contribution("a", "L1", "aller", 1000, 8, now)], now)[0]
        confirmed = cluster_vehicles([Contribution(u, "L1", "aller", 1000, 8, now)
                                      for u in "abc"], now)[0]
        self.assertEqual(reliability(alone, now)[1], "probable")
        self.assertEqual(reliability(confirmed, now)[1], "fiable")
        self.assertEqual(reliability(confirmed, now + 200)[1], "obsolète")
        self.assertEqual(reliability(confirmed, now + 400)[1], "expiré")
        self.assertEqual(cluster_vehicles([Contribution("a", "L1", "aller", 0, 8, now)],
                                          now + 400), [])

    def test_eta(self):
        now = 2000.0
        v = cluster_vehicles([Contribution("a", "L1", "aller", 1000, 10, now)], now)[0]
        self.assertAlmostEqual(eta_seconds(v, 2000, now), 100.0)
        self.assertIsNone(eta_seconds(v, 500, now))
        stopped = cluster_vehicles([Contribution("a", "L1", "aller", 1000, 0, now)], now)[0]
        self.assertAlmostEqual(eta_seconds(stopped, 2000, now), 200.0)  # vitesse par défaut


if __name__ == "__main__":
    unittest.main()

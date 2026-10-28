import unittest

from import_tunismapper import order_stops

# Arrêts le long d'une droite est-ouest, ~890 m entre chaque.
LINE = [(36.80, 10.10 + 0.01 * i) for i in range(8)]


class OrderStopsTest(unittest.TestCase):
    def test_keeps_ordered_stops(self):
        self.assertEqual(order_stops(LINE), (list(range(8)), []))

    def test_moves_branch_stop_listed_at_the_end(self):
        points = LINE[:3] + LINE[4:] + [LINE[3]]
        order, excluded = order_stops(points)
        self.assertEqual([points[i] for i in order], LINE)
        self.assertEqual(excluded, [])

    def test_excludes_stop_with_wrong_coordinates(self):
        points = LINE[:4] + [(36.70, 10.13)] + LINE[4:]   # ~11 km au sud
        order, excluded = order_stops(points)
        self.assertEqual(excluded, [4])
        self.assertEqual([points[i] for i in order], LINE)


if __name__ == "__main__":
    unittest.main()

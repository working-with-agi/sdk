"""Where to add capacity, and to whom: the welfare score adds the passengers' surplus and both
margins and takes off the airport's annual cost; the no-one-loses best is chosen among plans
where both margins hold."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import route_optimize as ro  # noqa: E402


def row(a, b, value, cost, pax, capital):
    eng = {"utilisation_multiplier": 0.0, "spend_oku": 0.0}
    air = {"aircraft_used_avg": {}, "engines": {"767": eng}, "co2_kt": 0.0}
    return {"plan": {"jal": {}, "ana": {}}, "market_round_trips": {}, "capital_oku": capital, "annual_cost_oku": cost, "new_pax_k": pax,
            "fare_value_oku": value, "margin_change_oku": {"jal": a, "ana": b}, "aircraft": {"jal": air, "ana": air}}


class RouteOptimizeTest(unittest.TestCase):
    def test_welfare(self):
        sc = ro.score(row(10, -4, 100, 20, 50, 400), 0.45)
        self.assertAlmostEqual(sc["welfare"], 0.45 * 100 + 10 - 4 - 20)
        self.assertAlmostEqual(sc["joint"], 6)
        self.assertAlmostEqual(sc["pax_per_cost"], 50 / 400)

    def test_nothing_scores_zero(self):
        sc = ro.score(row(0, 0, 0, 0, 0, 0), 0.45)
        self.assertEqual(sc["welfare"], 0)
        self.assertEqual(sc["pax_per_cost"], 0.0)

    def test_grid_size(self):
        self.assertEqual(len(ro.LEVELS) ** (2 * len(ro.rg.GROW)), 729)


if __name__ == "__main__":
    unittest.main()

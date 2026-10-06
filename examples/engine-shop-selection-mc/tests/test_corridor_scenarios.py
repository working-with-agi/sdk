"""Ground transport and airport capacity: the corridor change reaches the fleet assignment (a
smaller Haneda-Itami market carries fewer passengers), a rail-reached airport keeps fewer of the
spilled passengers the costlier its access, and the Itami screening gives a probability."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import capacity_scenarios as cs  # noqa: E402
import corridor_scenarios as cor  # noqa: E402


class CorridorTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.C = cor.load()
        cls.s = cs.setup("jal")
        cls.base = cs.run(cls.s, 3, dest=True, windows=False)
        cls.small = cs.run(cls.s, 3, dest=True, windows=False, corridor={"market_scale": {"HND-ITM": 0.5}, "bounds": {"HND-ITM": (0, 16)}, "use_min": 0.0})

    def test_market_scale_reaches_the_assignment(self):
        self.assertLess(self.small["demand_pax_k"], self.base["demand_pax_k"])
        self.assertLess(self.small["carried_pax_k"], self.base["carried_pax_k"])

    def test_rail_airports_order_by_access_cost(self):
        base = {**self.base, "spill_by_route_pax_k": {"HND-CTS": 100.0, "HND-FUK": 100.0, "HND-OKA": 100.0}}
        r = cor.rail_airports(self.s, self.C, base)["airports"]
        by = sorted(r, key=lambda a: a["extra_cost_one_way_yen"])
        caps = [a["captured_pax_k"] for a in by]
        self.assertEqual(caps, sorted(caps, reverse=True))

    def test_itami_probability(self):
        m = cor.itami_monte_carlo(self.C, n=2000)
        self.assertTrue(0.0 <= m["p_land_exceeds_loss"] <= 1.0)
        lo, mid, hi = m["net_oku_p10_p50_p90"]
        self.assertLessEqual(lo, mid)
        self.assertLessEqual(mid, hi)
        self.assertEqual(self.C["status"], "checked")


if __name__ == "__main__":
    unittest.main()

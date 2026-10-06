"""Carbon as emissions trading: the allowance price lands on each type's cost per block hour, the
CO2 follows the block hours, the free allocation moves the margin's level but not the choice, and
a binding cap leaves the country's total unchanged."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import capacity_scenarios as cs  # noqa: E402
import carbon_scenarios as cb  # noqa: E402
import corridor_scenarios as cor  # noqa: E402
import route_fleet as rf  # noqa: E402


class CarbonTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.K = cb.load()
        cls.s = cs.setup("jal")
        cls.W = cb.worlds(cls.s, cor.load(), cls.K, 3, prices=(0, 10000))

    def test_price_on_cost(self):
        ov = cb.overrides("jal", self.K, 10000)
        base = {t["type"]: t["cost_per_block_h_k"] for t in rf.types_of(rf.load(), "jal")}
        for t, v in ov.items():
            add = 10000 * 3.16 * self.K["fuel_t_per_block_h"][t] / rf.USD_JPY / 1e3
            self.assertAlmostEqual(v["cost_per_block_h_k"], base[t] + add, places=3)
        self.assertIsNone(cb.overrides("jal", self.K, 0))

    def test_co2_from_block_hours(self):
        w = self.W[(0, "before")]
        e = sum(h * self.K["fuel_t_per_block_h"][t] * 3.16 for t, h in w["block_h_by_type"].items())
        self.assertAlmostEqual(w["co2_kt"], e / 1e3, delta=0.1)
        self.assertTrue(80 < w["co2_g_per_pkm"] < 130)                 # near MLIT's 98 g per passenger-km

    def test_price_costs_margin(self):
        for name, *_ in cb.WORLDS:
            a, b = self.W[(0, name)], self.W[(10000, name)]
            self.assertLess(b["margin_oku"], a["margin_oku"])
            self.assertGreater(b["carbon_cost_oku"], 0)

    def test_binding_cap_holds_total(self):
        for r in cb.system(self.W, self.K, 514):
            self.assertEqual(r["binding"]["country_change_kt"], 0.0)
            self.assertAlmostEqual(r["binding"]["allowances_freed_kt"], -r["air_change_kt"], places=1)
            self.assertEqual(r["linear_kt_by_grid_scale"]["0.0"], 0.0)


if __name__ == "__main__":
    unittest.main()

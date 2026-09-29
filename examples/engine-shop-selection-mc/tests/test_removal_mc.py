"""Run: python -m unittest tests.test_removal_mc"""

import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import lifecycle as lc  # noqa: E402
import removal_mc as rm  # noqa: E402


class RemovalMcTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _v, _s, _sh, cls.state, cls.T = lc.simulate(7)
        cls.sim = rm.simulate(cls.state, cls.T, horizon=36, paths=400, seed=1)
        cls.rows = rm.plan_rows(cls.sim, 24)

    def test_engines_in_the_shop_are_skipped(self):
        in_shop = ~self.sim["active"]
        self.assertTrue(np.all(self.sim["limit"][:, in_shop] == rm.NEVER))
        self.assertTrue(np.all(self.sim["heavy"][:, in_shop] == rm.NEVER))

    def test_rows_are_valid_plan_input(self):
        self.assertGreater(len(self.rows), 20)
        for r in self.rows:
            e, l = r["window"]
            self.assertTrue(0 <= e <= l <= 23, r)
            self.assertTrue(0 < r["hazard"] <= 1, r)
            self.assertGreaterEqual(r["p_in_horizon"], 0.5)
            self.assertAlmostEqual(sum(r["driver_share"].values()), 1.0, places=2)

    def test_latest_is_before_the_median_removal(self):
        # the plan inducts before the limit with probability 1 - late_risk
        for r in self.rows:
            p10, p50, _ = r["removal_p10_p50_p90"]
            self.assertLessEqual(r["window"][1], p50)

    def test_close_to_the_mean_path_without_noise(self):
        sim = rm.simulate(self.state, self.T, horizon=36, paths=200, seed=2, rate_sigma=0.0, util_sigma=0.0)
        mc = {r["esn"]: r for r in rm.plan_rows(sim, 24, late_risk=0.5)}
        det = {r["esn"]: r for r in lc.window(self.state, self.T)}
        both = set(mc) & set(det)
        self.assertGreater(len(both), 0.8 * len(det))
        # only tail assignment and seasonality move the median: within two months of the mean path
        near = [abs(mc[e]["window"][1] - det[e]["window"][1]) <= 2 for e in both]
        self.assertGreater(np.mean(near), 0.8)

    def test_fleet_forecast_quantiles_are_ordered(self):
        fc = rm.fleet_forecast(self.sim, 24)
        lo, mid, hi = fc["shop_visits_in_window_p10_p50_p90"]
        self.assertTrue(lo <= mid <= hi)
        self.assertEqual(len(fc["removals_by_month_p10_p50_p90"]), 24)


if __name__ == "__main__":
    unittest.main()

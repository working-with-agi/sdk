"""Backtest: the demand-rule backtest never uses data from the year it predicts, its
error columns are consistent, and the engine backtest's coverage is a share."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import backtest  # noqa: E402
import demand  # noqa: E402


class BacktestTest(unittest.TestCase):
    def test_demand_rule_uses_only_prior_years(self):
        D = demand.load()
        out = backtest.demand_backtest(D)
        rpk = {f["fy"]: f["rpk"] for f in D["market"]["fiscal_years"]}
        for r in out["rows"]:
            y = int(r["fy"][2:])
            short = (rpk[f"FY{y - 1}"] / rpk[f"FY{y - 3}"]) ** 0.5 - 1
            self.assertAlmostEqual(r["short"], short, places=3)
            self.assertAlmostEqual(r["realised"], rpk[f"FY{y}"] / rpk[f"FY{y - 1}"] - 1, places=3)
            self.assertAlmostEqual(r["err_short"], r["realised"] - r["short"], places=3)

    def test_split_learns_only_on_learn_versions(self):
        rng = __import__("numpy").random.default_rng(1)
        vs = []
        for back in (14, 10, 6, 5, 3, 1):
            vs.append({"back": back, "version": f"{2026 - back}-10", "realised_months": 24,
                       "timing": [{"actual": 5 + (2 if back > 5 else 0), "forecast": 4, "unscheduled": False}],
                       "fiscal_years": [{"months": 12, "planned": 10, "actual": 9, "unsched_expected": 1.0, "unsched_actual": 2 if back > 5 else 1}]})
        out = backtest.split_backtest({"versions": vs}, rng)
        self.assertEqual(out["learn_backs"], [14, 10, 6]); self.assertEqual(out["test_backs"], [5, 3, 1])
        self.assertEqual(out["corrections"]["timing_shift"], 3)          # learned from the learn versions only (error 3 there, 1 in test)
        self.assertAlmostEqual(out["corrections"]["unsched_ratio"], 2.0)
        self.assertAlmostEqual(out["test_corrected"]["timing_mean"], 1 - 3)

    def test_engine_backtest_shape(self):
        e = backtest.engine_backtest("jal", years=2, scenarios=10)
        self.assertGreaterEqual(e["n_versions"], 1)
        self.assertTrue(0.0 <= e["coverage"] <= 1.0)
        self.assertEqual(len(e["timing"]["hist"]), len(e["timing"]["hist_bins"]) - 1)


if __name__ == "__main__":
    unittest.main()

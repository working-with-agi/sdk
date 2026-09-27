"""Run-out chain (退役までの入場列): the frozen plan is kept inside the window, every engine
leaves by the last exit, the run-out workscope never exceeds the stub rule's cost, and the
totals are consistent with the per-engine rows."""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import runout  # noqa: E402


class RunoutTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg, cls.b, cls.fleet, cls.shops = runout.load_inputs("jal")
        cls.out = runout.build("jal")

    def test_window_visits_follow_the_frozen_plan(self):
        plan = {r["esn"]: r for r in self.b["plan"]}
        rows = {e["esn"]: e for e in self.out["engines"]}
        W = self.out["window_months"]
        for esn, r in plan.items():
            chain = [c for c in rows[esn]["chain"] if not c.get("gap") and c["t"] < W]
            self.assertEqual([(c["t"], c["ws"]) for c in chain], [(r["t"], r["workscope"])], esn)

    def test_every_engine_leaves_by_the_last_exit(self):
        n_ac = self.cfg["aircraft"]["total"]
        retired = [e for e in self.out["engines"] if e["retire_t"] is not None]
        self.assertGreaterEqual(len(retired), 2 * n_ac)
        self.assertTrue(all(e["retire_t"] < self.out["end_t"] for e in retired))

    def test_totals_match_rows(self):
        T = self.out["totals"]
        self.assertEqual(T["visits"], sum(e["visits"] for e in self.out["engines"]))
        self.assertAlmostEqual(T["spend_k"], sum(e["spend_k"] for e in self.out["engines"]))
        self.assertEqual(sum(y["visits"] for y in self.out["by_year"]), T["visits"])

    def test_runout_sizing_never_costs_more_than_the_stub_rule(self):
        self.assertLessEqual(self.out["policies"]["next_due"]["spend_k"], self.out["without_runout"]["spend_k"] + 1e-6)

    def test_lightest_workscope_that_reaches_the_exit(self):
        ph = runout.Physics(self.cfg, self.fleet)
        s = {"margin": 2.0, "since": 9000.0, "core": 15000.0, "lp": 20000.0, "fan": 25000.0}
        ws, lasts = ph.runout_workscope(s, 12.0, ["PR", "CORE", "FULL"])
        self.assertEqual(ws, "PR"); self.assertGreaterEqual(lasts, 12.0)
        s2 = {"margin": 2.0, "since": 9000.0, "core": 1600.0, "lp": 20000.0, "fan": 25000.0}
        ws2, _ = ph.runout_workscope(s2, 12.0, ["PR", "CORE", "FULL"])
        self.assertEqual(ws2, "CORE")


if __name__ == "__main__":
    unittest.main()

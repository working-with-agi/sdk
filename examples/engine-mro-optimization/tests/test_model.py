"""Sanity tests on small instances that solve to proven optimality in seconds.

Run: python -m unittest discover -s tests
"""

import dataclasses
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine_mro import load, solve  # noqa: E402

SAMPLE = ROOT / "data" / "sample_fleet.json"


def small(**overrides):
    d = load(SAMPLE)
    engines = [e for e in d.engines if e.esn in ("E-801", "E-807", "E-811")]
    base = dict(horizon=18, installed_positions=2, engines=engines, shop_slots=1)
    return dataclasses.replace(d, **{**base, **overrides})


class EngineMroTest(unittest.TestCase):
    def check_plan(self, d, sol):
        self.assertTrue(sol.has_solution)
        for e in d.engines:
            dg = d.egt_loss_per_month(e)
            for t in range(d.horizon):
                if sol.operating[e.esn][t]:
                    # never fly below the EGT margin floor or past LLP life
                    self.assertGreaterEqual(sol.egt[e.esn][t] - dg, -1e-6)
                    for m in d.modules:
                        self.assertGreaterEqual(sol.llp[e.esn][m.name][t] - d.cycles(e), -1e-6)
        # no engine flies while in the shop, capacity respected
        busy = {(v.esn, t) for v in sol.visits for t in range(v.start, v.start + v.tat)}
        for e in d.engines:
            for t in range(min(e.in_shop_until, d.horizon)):
                busy.add((e.esn, t))
        for esn, t in busy:
            if t < d.horizon:
                self.assertEqual(sol.operating[esn][t], 0)
        for t in range(d.horizon):
            self.assertLessEqual(sum(1 for (_, tt) in busy if tt == t), d.shop_slots)

    def test_small_instance_optimal_and_feasible(self):
        d = small()
        sol = solve(d, time_limit=60, gap=0.0)
        self.assertEqual(sol.status, "Optimal")
        self.check_plan(d, sol)
        # E-801 starts with 6 degC margin at 0.52 degC/month: 11 months of flying
        # at most unless a restoring workscope is performed.
        restored = any(
            v.esn == "E-801"
            and next(w for w in d.workscopes if w.code == v.workscope).egt_restore_to
            for v in sol.visits
        )
        self.assertTrue(restored or sum(sol.operating["E-801"]) <= 11)

    def test_llp_limit_forces_replacement(self):
        d = small(horizon=24)
        sol = solve(d, time_limit=60, gap=0.0)
        self.check_plan(d, sol)
        flown = sum(sol.operating["E-807"])
        replaced_hpt = any(
            v.esn == "E-807" and "HPT" in next(w for w in d.workscopes if w.code == v.workscope).llp_replace
            for v in sol.visits
        )
        # 2600 cycles / 130 per month = 20 months of flying at most without new HPT LLPs
        self.assertTrue(replaced_hpt or flown <= 20)

    def test_more_shop_capacity_never_hurts(self):
        tight = solve(small(shop_slots=1), time_limit=60, gap=0.0)
        loose = solve(small(shop_slots=3), time_limit=60, gap=0.0)
        self.assertLessEqual(loose.objective, tight.objective + 1e-6)

    def test_cbc_matches_highs(self):
        d = small(horizon=12)
        a = solve(d, solver="highs", time_limit=60, gap=0.0)
        b = solve(d, solver="cbc", time_limit=60, gap=0.0)
        self.assertAlmostEqual(a.objective, b.objective, delta=1.0)


if __name__ == "__main__":
    unittest.main()

"""Run: python -m unittest discover -s tests"""

import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from shop_mc import evaluate, load, mean_value, sample, solve_saa  # noqa: E402

P = load(ROOT / "data" / "fleet_visits.json", ROOT / "data" / "shop_quotes.json")


class ShopMcTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sc = sample(P, 20, seed=1)
        cls.plan = solve_saa(P, cls.sc, gap=1e-4)

    def test_one_option_per_visit_within_window(self):
        chosen = [self.sc.options[i] for i in self.plan.chosen]
        self.assertEqual(sorted(v.esn for v, *_ in chosen), sorted(v.esn for v in P.visits))
        for v, k, w, t, _rush in chosen:
            self.assertTrue(v.earliest <= t <= v.latest)
            self.assertIn(w, v.allowed_workscopes)
            self.assertIn(w, k.quotes)

    def test_planned_capacity(self):
        chosen = [self.sc.options[i] for i in self.plan.chosen]
        for k in P.shops:
            for t in range(P.horizon):
                busy = sum(1 for o in chosen if o.shop is k and o.month <= t < o.month + o.tat())
                self.assertLessEqual(busy, k.slots)

    def test_closed_form_recourse_matches_saa_objective(self):
        # evaluating the SAA plan on its own scenarios must reproduce the MILP objective
        ev = evaluate(P, self.plan, self.sc)
        self.assertAlmostEqual(ev.mean, self.plan.objective, delta=1e-3 * abs(self.plan.objective))

    def test_saa_not_worse_in_sample_than_ev_plan(self):
        ev_plan = solve_saa(P, mean_value(P, n=2000, seed=3), gap=1e-4)
        # up to the MIP gap tolerance
        self.assertLessEqual(
            evaluate(P, self.plan, self.sc).mean, evaluate(P, ev_plan, self.sc).mean * (1 + 1e-3)
        )

    def test_fixed_price_shop_never_bills_overrun(self):
        # OEM-NET is fixed price in USD: its cost varies only with FX, which is common to
        # all its quotes in a scenario, so the price ratio is identical across engines
        sc = self.sc
        fixed = next(k for k in P.shops if k.overrun_share == 0.0)     # the fixed-price shop in the tender data
        ws = next(w for w in ("PR", "CORE", "FULL") if w in fixed.quotes)
        def ratio(esn):
            i = next(i for i, o in enumerate(sc.options)
                     if o.shop is fixed and o.visit.esn == esn and o.workscope == ws and not o.rush)
            k = sc.options[i].shop
            return (sc.cost[:, i] - k.transport_cost) / k.quotes[ws].price
        a, b = [v.esn for v in P.visits if ws in v.allowed_workscopes][:2]
        self.assertTrue(np.allclose(ratio(a), ratio(b)))

    def test_llp_kits_and_budget(self):
        chosen = [self.sc.options[i] for i in self.plan.chosen]
        early_kits = sum(1 for o in chosen if o.workscope in P.llp_workscopes and o.month < P.llp_kit_lead_months)
        self.assertLessEqual(early_kits, P.llp_kits_on_hand)
        exp = self.sc.cost.mean(axis=0)
        for fy, budget in P.budget_by_fy.items():
            spend = sum(exp[i] for i in self.plan.chosen if P.fiscal_year(self.sc.options[i].month) == fy)
            self.assertLessEqual(spend, budget + 1e-6)



class NormalStateTest(unittest.TestCase):
    """The plan keeps 'what the schedule needs + shelf buffer' on its quoted schedule."""

    def test_buffer_rule(self):
        sc = sample(P, 10, seed=5)
        plan = solve_saa(P, sc, gap=1e-3)
        chosen = [sc.options[i] for i in plan.chosen]
        for t in range(P.horizon):
            off = sum(1 for o in chosen if o.month <= t < o.month + o.shop.transport_months + o.tat())
            self.assertGreaterEqual(P.owned_engines - off + plan.long_spares, P.required_positions[t] + P.buffer[t])

    def test_failure_moves_start_earlier(self):
        sc = sample(P, 200, seed=9)
        for i, o in enumerate(sc.options[:200]):
            self.assertTrue((sc.start[:, i] <= o.month).all())
            self.assertTrue((sc.start[:, i] >= o.visit.earliest).all())


if __name__ == "__main__":
    unittest.main()

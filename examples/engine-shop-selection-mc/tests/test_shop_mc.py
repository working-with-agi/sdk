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
        cls.sc = sample(P, 30, seed=1)
        cls.plan = solve_saa(P, cls.sc, gap=0.0)

    def test_one_option_per_visit_within_window(self):
        chosen = [self.sc.options[i] for i in self.plan.chosen]
        self.assertEqual(sorted(v.esn for v, *_ in chosen), sorted(v.esn for v in P.visits))
        for v, k, w, t in chosen:
            self.assertTrue(v.earliest <= t <= v.latest)
            self.assertIn(w, v.allowed_workscopes)
            self.assertIn(w, k.quotes)

    def test_planned_capacity(self):
        chosen = [self.sc.options[i] for i in self.plan.chosen]
        for k in P.shops:
            for t in range(P.horizon):
                busy = sum(1 for _, kk, w, t0 in chosen if kk is k and t0 <= t < t0 + k.quotes[w].tat)
                self.assertLessEqual(busy, k.slots)

    def test_closed_form_recourse_matches_saa_objective(self):
        # evaluating the SAA plan on its own scenarios must reproduce the MILP objective
        ev = evaluate(P, self.plan, self.sc)
        self.assertAlmostEqual(ev.mean, self.plan.objective, delta=1e-3 * abs(self.plan.objective))

    def test_saa_not_worse_in_sample_than_ev_plan(self):
        ev_plan = solve_saa(P, mean_value(P, n=2000, seed=3), gap=0.0)
        self.assertLessEqual(
            evaluate(P, self.plan, self.sc).mean, evaluate(P, ev_plan, self.sc).mean + 1e-6
        )

    def test_common_random_numbers_for_findings(self):
        # the same engine gets the same findings draw at every shop: a fixed-price shop
        # (share 0) never bills an overrun, a T&M shop bills it in the same scenarios
        sc = self.sc
        inhouse = [i for i, (v, k, w, t) in enumerate(sc.options) if k.id == "IN-HOUSE" and v.esn == "E-903" and w == "PR" and t == 2]
        oem = [i for i, (v, k, w, t) in enumerate(sc.options) if k.id == "OEM-NET" and v.esn == "E-903" and w == "PR" and t == 2]
        k_oem = next(k for k in P.shops if k.id == "OEM-NET")
        self.assertTrue(np.allclose(sc.cost[:, oem[0]], k_oem.quotes["PR"].price + k_oem.transport_cost))
        self.assertTrue((sc.cost[:, inhouse[0]] >= 2500).all())


if __name__ == "__main__":
    unittest.main()

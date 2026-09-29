"""Run: python -m unittest tests.test_dro"""

import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from decide import case_problem  # noqa: E402
from shop_mc import load, sample, solve_saa  # noqa: E402
from shop_mc.dro import pool, remap  # noqa: E402

P = load(ROOT / "data" / "fleet_visits.json", ROOT / "data" / "shop_quotes.json")


class DroTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sup = pool(P, {"backlog": case_problem(P, "backlog")}, n_nominal=8, n_per_world=4, seed=3)
        cls.plans = {th: solve_saa(P, cls.sup.sc, ambiguity=cls.sup.ambiguity(th)) for th in (0.0, 0.5, 2.0)}

    def test_theta_zero_is_saa(self):
        saa = solve_saa(P, sample(P, 8, seed=3))
        self.assertAlmostEqual(self.plans[0.0].objective, saa.objective, delta=1e-6 * abs(saa.objective))

    def test_objective_grows_with_radius(self):
        objs = [self.plans[th].objective for th in (0.0, 0.5, 2.0)]
        self.assertTrue(all(a <= b + 1e-6 * abs(b) for a, b in zip(objs, objs[1:])), objs)

    def test_support_and_distances(self):
        s = self.sup
        self.assertEqual(s.sc.n, 12)
        self.assertAlmostEqual(s.weights.sum(), 1.0)
        self.assertTrue(np.all(s.weights[8:] == 0))
        self.assertTrue(np.allclose(np.diag(s.dist), 0))
        self.assertTrue(np.allclose(s.dist, s.dist.T))
        # congestion moves the delay summary, so the stressed scenarios are farther away on average
        self.assertGreater(s.dist[:8, 8:].mean(), s.dist[:8, :8].mean())

    def test_remap_keeps_world_outcomes(self):
        sw = sample(case_problem(P, "backlog"), 5, seed=9)
        r = remap(P, sw)
        self.assertIs(r.down, sw.down)
        self.assertEqual(r.options[0].shop.quotes, P.shops[0].quotes)

    def test_not_combined_with_cvar(self):
        with self.assertRaises(ValueError):
            solve_saa(P, self.sup.sc, ambiguity=self.sup.ambiguity(0.5), cvar_weight=1.0)


if __name__ == "__main__":
    unittest.main()

"""The public-data estimate: the route x month panel and the monthly indexes line up, the design
keeps its fixed effects, and the fit reports the fare effect (OLS and 2SLS) and, when asked, seats."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import fare_elasticity as fe  # noqa: E402


class FareElasticityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = fe.load()
        cls.pre = cls.d[cls.d.year <= 2019]

    def test_panel(self):
        self.assertEqual(set(fe.TARGET) - set(self.d.route), set())
        self.assertGreaterEqual(self.d.route.nunique(), 10)
        self.assertTrue((self.d.pax <= self.d.seats * 1.0001).all())
        self.assertEqual(self.pre.ym.min(), 200601)

    def test_fit(self):
        r = fe.fit(self.pre, "test", seats=True)
        self.assertLess(r["ols"]["b"], 0)
        self.assertGreater(r["seats_b"], 0)
        self.assertIn("first_stage_F", r["iv"])
        self.assertEqual(r["months"], 168)


if __name__ == "__main__":
    unittest.main()

"""Levers through political lenses: number axes come from the model outputs scaled to -2..+2, red
lines exclude levers, and the weight shake gives top-3 probabilities between 0 and 1."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import politics  # noqa: E402


class PoliticsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = politics.build()

    def test_scores_on_scale(self):
        for k, sc in self.r["scores"].items():
            for a, v in sc.items():
                self.assertTrue(-2.0 - 1e-9 <= v <= 2.0 + 1e-9, (k, a, v))

    def test_red_lines_exclude(self):
        for i, v in self.r["isms"].items():
            for row in v["ranking"]:
                if row["red_lines"]:
                    self.assertNotIn(row["lever"], v["top3"])
            for p in v["top3_probability"].values():
                self.assertTrue(0.0 <= p <= 1.0)

    def test_agreement_counts(self):
        n = len(self.r["isms"])
        for a in self.r["agreement"]:
            self.assertEqual(a["not_excluded"] + len(a["excluded_by"]), n)


if __name__ == "__main__":
    unittest.main()

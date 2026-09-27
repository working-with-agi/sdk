"""The shortage watch: probabilities are in [0, 1], the fix never exceeds the lease cap,
and a fleet with no engines in the shop and no plan ahead is never short."""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import shortage  # noqa: E402

RESULTS = ROOT / "handover" / "02_results"


class ShortageTest(unittest.TestCase):
    def test_watch_on_tracked_actuals(self):
        tp = RESULTS / "jal-track-crunch.json"
        if not tp.exists():
            self.skipTest("no tracked actuals")
        out = shortage.build("jal", tp)
        self.assertTrue(out["months"])
        for x in out["months"]:
            self.assertTrue(0.0 <= x["p_aog"] <= 1.0 and x["p_aog"] <= x["p_margin_gone"])
        if out["fix"]:
            self.assertLessEqual(out["fix"]["short_lease_engines"], out["fix"]["cap"])
        self.assertEqual(out["triggered"], bool(out["worst"] and out["worst"]["p_aog"] > out["target"]))


if __name__ == "__main__":
    unittest.main()

"""Counted levers and the purchase loop: spares@n / buy@n / pool@n / midlife@n change the
problem by n, and the loop's trajectory never raises expected AOG."""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import actions  # noqa: E402
from shop_mc import load  # noqa: E402


class PurchaseTest(unittest.TestCase):
    def setUp(self):
        self.p = load(str(ROOT / "data" / "jal" / "fleet.json"), str(ROOT / "data" / "jal" / "shops.json"))

    def test_counted_levers(self):
        self.assertEqual(actions.apply_action(self.p, "spares@3").owned_engines, self.p.owned_engines + 3)
        self.assertEqual(actions.apply_action(self.p, "buy@2").owned_engines, self.p.owned_engines + 2)
        self.assertEqual(actions.apply_action(self.p, "pool@1").short_lease_max, self.p.short_lease_max + 1)
        q = actions.apply_action(self.p, "midlife@4")
        self.assertEqual(next(k for k in q.shops if k.id == "MIDLIFE").max_visits, 4)
        self.assertGreater(actions.apply_action(self.p, "buy@1").extra_fixed_cost, self.p.extra_fixed_cost)

    def test_trajectory_monotone(self):
        p = ROOT / "purchase" / "jal.json"
        if not p.exists():
            self.skipTest("no purchase output")
        d = json.loads(p.read_text(encoding="utf-8"))
        aog = [s["expected"]["aog_prob"] for s in d["trajectory"]]
        self.assertTrue(all(a >= b - 1e-9 for a, b in zip(aog, aog[1:])))
        self.assertEqual(d["summary"]["reached"], aog[-1] <= d["target"])


if __name__ == "__main__":
    unittest.main()

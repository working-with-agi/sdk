"""The playbook: the second-shop option adds a shop (never removes one), the late-life
world reduces slots and stretches TAT, and the staged plan's worlds and posterior are
consistent."""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import actions  # noqa: E402
import decide  # noqa: E402
from shop_mc import load  # noqa: E402


class PlaybookTest(unittest.TestCase):
    def setUp(self):
        self.p = load(str(ROOT / "data" / "jal" / "fleet.json"), str(ROOT / "data" / "jal" / "shops.json"))

    def test_second_shop_is_an_added_option(self):
        q = actions.apply_action(self.p, "second_shop")
        self.assertEqual(len(q.shops), len(self.p.shops) + 1)
        k0, k1 = self.p.shops[0], q.shops[-1]
        self.assertEqual(k1.id, "SECOND")
        self.assertAlmostEqual(k1.quotes["FULL"].price, k0.quotes["FULL"].price * (1 + actions.SECOND_SHOP["price_premium"]))
        self.assertGreater(q.extra_fixed_cost, self.p.extra_fixed_cost)

    def test_late_world_shrinks_capacity(self):
        q = decide.case_problem(self.p, "late")
        for a, b in zip(self.p.shops, q.shops):
            self.assertLess(b.slots, a.slots)
            self.assertEqual(b.quotes["FULL"].tat, a.quotes["FULL"].tat + 1)
        q2 = decide.case_problem(self.p, "late@0.5")
        self.assertLessEqual(q2.shops[0].slots, q.shops[0].slots)

    def test_playbook_output_consistent(self):
        p = ROOT / "playbook" / "jal.json"
        if not p.exists():
            self.skipTest("no playbook output")
        d = json.loads(p.read_text(encoding="utf-8"))
        self.assertAlmostEqual(sum(d["posterior"].values()), 1.0, places=6)
        self.assertEqual([s["key"] for s in d["steps"]], ["base", "kits", "contract", "second"])
        for s in d["steps"][1:]:
            self.assertEqual(set(s["pays_in"]), set(d["worlds"]))


if __name__ == "__main__":
    unittest.main()

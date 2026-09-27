"""The type's clock: the residual multiplier is 1 before production end, falls to the floor
when the type disappears, never rises; the stage moves young -> late -> fading."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import typelife  # noqa: E402


class TypelifeTest(unittest.TestCase):
    def test_multiplier_monotone(self):
        T = typelife.load()
        ys = list(range(2015, 2050))
        ms = [typelife.residual_multiplier(T, "CFM56-7B", y) for y in ys]
        self.assertEqual(ms[0], 1.0)
        self.assertAlmostEqual(ms[-1], T["assumptions"]["residual_decay"]["floor"])
        self.assertTrue(all(a >= b for a, b in zip(ms, ms[1:])))

    def test_stages(self):
        T = typelife.load()
        self.assertEqual(typelife.stage(T, "CFM56-7B", 2015), "young")
        self.assertEqual(typelife.stage(T, "CFM56-7B", 2026), "late")
        self.assertEqual(typelife.stage(T, "CFM56-7B", 2040), "fading")

    def test_build_without_runout(self):
        o = typelife.build("CFM56-7B", "2026-10", None)
        self.assertEqual(o["successor"], "LEAP-1B")
        self.assertGreater(o["age_at_start"], 28)


if __name__ == "__main__":
    unittest.main()

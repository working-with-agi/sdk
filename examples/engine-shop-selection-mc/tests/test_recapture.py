"""Recapture: of the passengers a full flight turns away, a share rebooks on the same route into the
empty seats. Expost keeps the plan and only restates the lost revenue; the recaptured stay within the
share of the turned-away and within the seats."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import capacity_scenarios as cs  # noqa: E402
import route_fleet as rf  # noqa: E402


class RecaptureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s = cs.setup("jal")
        old = (rf.RECAPTURE, rf.RECAPTURE_MODE)
        try:
            rf.RECAPTURE_MODE = "expost"
            rf.RECAPTURE = 0.0; cls.r0 = cs.run(cls.s, 0, windows=False)
            rf.RECAPTURE = 0.5; cls.r5 = cs.run(cls.s, 0, windows=False)
        finally:
            rf.RECAPTURE, rf.RECAPTURE_MODE = old

    def test_plan_unchanged_expost(self):
        self.assertEqual(self.r0["version_round_trips"], self.r5["version_round_trips"])
        self.assertEqual(self.r0["aircraft_used_avg"], self.r5["aircraft_used_avg"])

    def test_lost_revenue_falls(self):
        self.assertLess(self.r5["lost_revenue_oku"], self.r0["lost_revenue_oku"])
        self.assertAlmostEqual(self.r5["carried_pax_k"] - self.r0["carried_pax_k"], self.r5["recaptured_pax_k"], delta=2.0)

    def test_recaptured_bounded(self):
        self.assertLessEqual(self.r5["recaptured_pax_k"], 0.5 * self.r0["spill_pax_k"] + 1.0)
        for m in self.r5["by_month"]:
            for r, lf in m["lf"].items():
                if lf is not None:
                    self.assertLessEqual(lf, rf.RECAPTURE_LF_MAX + 1e-3, (m["label"], r))

    def test_default_is_zero(self):
        self.assertEqual(rf.RECAPTURE, 0.0)


if __name__ == "__main__":
    unittest.main()

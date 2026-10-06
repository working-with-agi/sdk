"""The hub's capacity cap and what lies past it: the destination airports' caps clip the per-route
bounds and leave the hub slots above their sum unusable; widebody overrides raise what the trunk can
use; under the cap a later year carries more only through fuller aircraft (frequencies stay), and the
engine rows keep the cycles the trunk flies when the planning cap is off."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import airport_slots as ap  # noqa: E402
import capacity_scenarios as cs  # noqa: E402


class CapacityScenariosTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.S = ap.load()
        cls.s = cs.setup("jal")
        cls.base = cs.run(cls.s, 0)
        cls.later = cs.run(cls.s, 3)
        cls.lift = cs.run(cls.s, 0, delta=20, windows=False)
        cls.lift_dest = cs.run(cls.s, 0, delta=20, dest=True, windows=False)
        cls.wide = cs.run(cls.s, 3, overrides={"A350": {"trunk_aircraft": 17}}, windows=False)

    def test_destination_caps_clip_the_bounds(self):
        caps = ap.destination_caps(self.S, "jal")
        cur = ap.current_freq(self.S, "jal")
        dest = ap.load_destinations()["airports"]
        self.assertEqual(caps["HND-ITM"], cur["HND-ITM"] + dest["ITM"]["headroom_round_trips"])
        b = ap.bounds(self.S, "jal", 45, caps)
        for r in ap.HUB_ROUTES:
            self.assertLessEqual(b[r][1], caps[r])
            self.assertLessEqual(b[r][0], b[r][1])

    def test_slots_past_the_destinations_are_unusable(self):
        self.assertEqual(self.lift["unusable_round_trips"], 0)
        self.assertGreater(self.lift_dest["unusable_round_trips"], 0)
        caps = ap.destination_caps(self.S, "jal")
        self.assertAlmostEqual(self.lift_dest["flyable_budget"], sum(caps[r] for r in ap.HUB_ROUTES))
        for r in ap.HUB_ROUTES:
            self.assertLessEqual(self.lift_dest["version_round_trips"][r], caps[r] + 1e-6)
        self.assertTrue(self.lift_dest["destination_at_cap"])
        self.assertLess(self.lift_dest["margin_oku"], self.lift["margin_oku"])

    def test_under_the_cap_later_years_fill_the_aircraft(self):
        hub = lambda x: sum(x["version_round_trips"][r] for r in ap.HUB_ROUTES)
        self.assertAlmostEqual(hub(self.later), hub(self.base), delta=1)
        self.assertGreater(self.later["spill_pax_k"], self.base["spill_pax_k"])
        self.assertGreater(self.later["carried_pax_k"], self.base["carried_pax_k"])
        self.assertEqual(cs.fy_after(self.s["fy"], 3), f"FY{int(self.s['fy'][2:]) + 3}")

    def test_widebody_override_is_used_and_carries_more(self):
        self.assertGreater(self.wide["aircraft_used_avg"]["A350"], self.later["aircraft_used_avg"]["A350"])
        self.assertLessEqual(self.wide["spill_pax_k"], self.later["spill_pax_k"])

    def test_engine_rows_keep_the_trunk_cycles(self):
        for e in self.base["engines"]:
            if e["utilisation_multiplier"] is not None:
                self.assertAlmostEqual(e["utilisation_multiplier"], e["utilisation_uncapped"], places=2)


if __name__ == "__main__":
    unittest.main()

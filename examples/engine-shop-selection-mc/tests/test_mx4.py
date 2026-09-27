import json
import unittest
from pathlib import Path

import lease
import mx4

HERE = Path(__file__).resolve().parent.parent


class Mx4Test(unittest.TestCase):
    def setUp(self):
        self.b = json.loads((HERE / "baselines" / "jal-2026-10.json").read_text(encoding="utf-8"))
        self.f = json.loads((HERE / "data" / "jal" / "fleet.json").read_text(encoding="utf-8"))

    def test_engine_value_half_life_convention(self):
        P = mx4.load_params()
        e = {"llp_remaining": {"core": P["llp_life_cycles"] // 2}, "window": [0, 0]}
        v = mx4.engine_value(e, 36.0, P, 165.0, 72.0)   # half LLP, half run -> half-life value exactly
        self.assertAlmostEqual(v["value_k"], P["half_life_value_k"], places=6)

    def test_reserve_balance_never_negative_and_claims_bounded(self):
        L = lease.evaluate(self.b, self.f, loss=4.0)
        M = mx4.build(self.b, self.f, L)
        self.assertTrue(all(x >= -1e-9 for x in M["reserves"]["balance"]))
        self.assertLessEqual(M["reserves"]["total_claims_k"], M["reserves"]["total_inflow_k"] + M["reserves"]["n_leased"] * M["params"]["reserve_opening_balance_k"] + 1e-6)

    def test_value_created_matches_end_minus_now(self):
        M = mx4.build(self.b, self.f, None)
        V = M["value"]
        self.assertAlmostEqual(V["value_created_k"], V["end_k"] - V["now_k"], places=6)


if __name__ == "__main__":
    unittest.main()

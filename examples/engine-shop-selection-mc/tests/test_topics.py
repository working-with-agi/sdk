"""Topic threads: every item lands in exactly one topic, framework keys route by key
before words, and the status is the worst of the thread's findings."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import topics  # noqa: E402


class TopicsTest(unittest.TestCase):
    def test_route_by_key_then_words(self):
        d = topics.load_defs()
        self.assertEqual(topics.route("何でも", d, "kit_lead"), "supply")
        self.assertEqual(topics.route("需要の伸びの仮定から外れた", d), "demand")
        self.assertEqual(topics.route("契約形態を所見折半へ", d, "contract"), "contract")
        self.assertEqual(topics.route("特に語のない文", d), "method")

    def test_every_item_in_one_thread(self):
        review = {"framework": {"table": [{"key": "kit_lead", "name": "LLP キットの納期", "cadence_months": 12, "trigger": "x", "last_derived": "2027-10", "status": "fired", "owner": "調達"}],
                                "fired": [{"key": "kit_lead", "name": "LLP キットの納期", "evidence": "変化点"}]},
                  "symptoms": [{"loop": "PDCA", "stage": "Plan", "severity": "warn", "finding": "立て直し費が全体の 17%", "evidence": "", "ask": "契約形態で買うか"}]}
        out = topics.build("x", review, None, None)
        total = sum(t["counts"]["findings"] + t["counts"]["assumptions"] + t["counts"]["triggers"] for t in out["threads"])
        self.assertEqual(total, 3)
        sup = next(t for t in out["threads"] if t["id"] == "supply")
        self.assertEqual(sup["counts"]["assumptions"], 1); self.assertEqual(sup["status"], "warn")


if __name__ == "__main__":
    unittest.main()

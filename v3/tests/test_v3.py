import copy
import json
from pathlib import Path
import tempfile
import time
import unittest

from v3.app import LiveStore, validate_payload
from v3.explainer import GraniteExplainer, validate_generated, factual_template, evidence_key
from v3.mock_feed import fixture


class TestLiveIntegration(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = LiveStore(Path(self.tmp.name) / "approvals.jsonl",
                               GraniteExplainer(generator=lambda _: (
                                   "Account A_MOCK_TARGET is recommended for review based on "
                                   "4 historical transfers, 5 counterparties and 4 cross-bank transfers. "
                                   "These observations do not prove money laundering. "
                                   "Any simulated hold requires human approval.", "stop")))

    def tearDown(self):
        self.store.pool.shutdown(wait=True)
        self.tmp.cleanup()

    def test_initial_watchlist_independent_of_hold_budget(self):
        payload = fixture(0)
        self.assertEqual(validate_payload(payload)["recommendations"], [])
        self.store.publish(payload)
        state = self.store.state()
        self.assertEqual(state["watch_count"], 0)  # 0.58 and 0.7 under 0.8 threshold
        self.assertEqual(len(state["recommendations"]), 0)

    def test_detect_propose_and_human_review(self):
        self.store.publish(fixture(3))
        state = self.store.state()
        self.assertEqual(state["watch_count"], 1)
        self.assertEqual(len(state["recommendations"]), 1)
        rec = state["recommendations"][0]
        self.assertEqual(rec["review_status"], "awaiting_human_review")
        self.assertEqual(self.store.request_explanation(rec["acct"],rec["decision_id"])["status"], "queued")
        self.store.pool.shutdown(wait=True)
        after = self.store.state()["recommendations"][0]
        self.assertEqual(after["explanation"]["status"], "ready")
        event = self.store.decide(rec["acct"],rec["decision_id"],"approve")
        self.assertEqual(event["event"],"simulated_investigator_decision")
        self.assertIn("No real",event["note"])
        with self.assertRaises(ValueError):
            self.store.decide(rec["acct"],rec["decision_id"],"approve")
        self.assertEqual(len(Path(self.tmp.name,"approvals.jsonl").read_text().splitlines()),1)

    def test_reject_future_and_ground_truth(self):
        bad = fixture(3)
        bad["snapshot"]["recent_transactions"][0]["is_laundering"] = 1
        with self.assertRaisesRegex(ValueError,"evaluation-only"):
            validate_payload(bad)
        bad = fixture(3)
        bad["snapshot"]["recent_transactions"][0]["timestamp"]="2022-09-20T00:00:00+00:00"
        with self.assertRaisesRegex(ValueError,"future"):
            validate_payload(bad)

    def test_no_backwards_checkpoint(self):
        self.store.publish(fixture(4))
        with self.assertRaisesRegex(ValueError,"older"):
            self.store.publish(fixture(3))

    def test_scores_and_recommendation_are_same_point_in_time(self):
        bad = fixture(3)
        bad["scores"][0]["as_of"]="2022-09-01T10:00:00+00:00"
        with self.assertRaisesRegex(ValueError,"timestamp"):
            validate_payload(bad)
        bad = fixture(3)
        bad["recommendations"][0]["risk_score"] = 0.05
        with self.assertRaisesRegex(ValueError,"does not match"):
            validate_payload(bad)

    def test_stale_decision_rejected(self):
        self.store.publish(fixture(3))
        rec = self.store.state()["recommendations"][0]
        self.store.publish(fixture(4))
        with self.assertRaisesRegex(ValueError,"stale"):
            self.store.decide(rec["acct"],rec["decision_id"],"approve")

    def test_budget_enforced(self):
        bad = fixture(3)
        bad["recommendations"] = [bad["recommendations"][0]] * 11
        with self.assertRaisesRegex(ValueError,">10"):
            validate_payload(bad)


class TestGranite(unittest.TestCase):
    def setUp(self):
        self.rec={"acct":"A_DEMO1", "as_of":"2022-09-01T11:00:00+00:00",
                  "risk_score":.997,"reason_facts":"18 historical transfers; 4 counterparties; 16 cross-bank transfers"}

    def test_reject_wrong_count_even_if_other_number_is_present(self):
        wrong=("Account A_DEMO1 has 18 historical transfers, 4 counterparties and "
               "4 cross-bank transfers. These observations do not prove money laundering. "
               "Any simulated hold requires human approval.")
        self.assertFalse(validate_generated(self.rec,wrong)[0])

    def test_safe_fallback_and_cache(self):
        calls=[]
        def bad(_):
            calls.append(1)
            return ("Account A_DEMO1 has 4 cross-bank transfers. These observations do not prove "
                    "money laundering. Any simulated hold requires human approval.","stop")
        service=GraniteExplainer(generator=bad)
        first=service.explain(self.rec)
        second=service.explain(self.rec)
        self.assertEqual(first.source,"template_fallback")
        self.assertIn("16 cross-bank transfers",first.text)
        self.assertEqual(first.key,second.key)
        self.assertEqual(len(calls),1)

    def test_cache_depends_on_time_and_evidence(self):
        changed=dict(self.rec,as_of="2022-09-01T12:00:00+00:00")
        self.assertNotEqual(evidence_key(self.rec),evidence_key(changed))
        changed=dict(self.rec,reason_facts="3 historical transfers")
        self.assertNotEqual(evidence_key(self.rec),evidence_key(changed))

    def test_no_fake_numbers_on_fallback(self):
        text=factual_template(self.rec)
        self.assertIn("18 observed historical transfers",text)
        self.assertIn("human approval",text)
        self.assertNotIn("criminal proceeds",text)


if __name__=="__main__":unittest.main()

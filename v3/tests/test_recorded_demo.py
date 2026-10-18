"""Contract regression tests for the recorded Guardian dashboard adapter."""
import csv
import io
import json
import unittest
import zipfile
from pathlib import Path

from v3.recorded_demo import compose, load_checkpoint, read_explanations, RecordedStore

HERE = Path(__file__).resolve().parents[3]
# Real evidence fixtures are not shipped with this patch. If present, use them;
# otherwise the tests create a minimal Guardian fixture below.


def fixture():
    stamp = "2022-09-06T14:00:00Z"
    acct = "A_FAKE1"
    facts = "Risk score 0.700; 2 historical transfers; 1 counterparties; 1 cross-bank transfers; HUMAN REVIEW ONLY."
    rec = {"acct": acct, "rank": 1, "risk_score": .7, "reason_facts": facts,
           "decision_time": stamp, "execution_status": "NOT_EXECUTED",
           "action": "ACCOUNT_REVIEW_RECOMMENDATION", "requires_human_approval": True}
    guardian_sha = "a" * 64
    d = {"decision_time": stamp, "feature_cutoff": "2022-09-06T13:59:00Z",
         "score_available_at": stamp, "visible_tx_count": 123,
         "computed_risk_only_top_k": [{"acct": acct, "risk_score": .7}],
         "recommendations": [rec],
         "guardian_decision": {"decision_sha256": guardian_sha, "recommendations": [rec]}}
    row = {"acct": acct, "rank": "1", "risk_score": ".7", "reason_facts": facts,
           "decision_time": stamp, "decision_sha256": guardian_sha,
           "feature_cutoff": "2022-09-06T13:59:00Z", "score_available_at": stamp,
           "requires_human_approval": "True", "execution_status": "NOT_EXECUTED",
           "action": "ACCOUNT_REVIEW_RECOMMENDATION",
           "investigator_explanation": "Account A_FAKE1 is recommended for human review. No hold executed.",
           "granite_draft": "", "explanation_source": "structured_template_no_llm",
           "granite_seconds": "", "granite_validation_note": "Structured explanation"}
    return d, row


class TestRecordedDemo(unittest.TestCase):
    def test_can_publish_trusted_checkpoint_without_inference(self):
        import tempfile
        d, row = fixture()
        with tempfile.TemporaryDirectory() as tmp:
            store = RecordedStore(Path(tmp)/"audit.jsonl")
            result = store.seed_recorded(d, [row])
            s = store.state()
            self.assertTrue(s["ready"])
            self.assertEqual(result["recommendations"], 1)
            self.assertEqual(s["mode"], "RECORDED_GUARDIAN_V3_NOT_LIVE")
            self.assertEqual(s["recent_transactions"], [])
            self.assertEqual(s["bank_links"], [])
            r = s["recommendations"][0]
            self.assertEqual(r["explanation"]["status"], "ready")
            self.assertEqual(r["execution_status"], "NOT_EXECUTED")
            self.assertEqual(s["guardian_decision_sha256"], "a"*64)
            self.assertEqual(store.request_explanation(r["acct"], r["decision_id"])["status"], "ready")

    def test_reject_wrong_decision(self):
        d, row = fixture()
        row["decision_sha256"] = "b"*64
        with self.assertRaisesRegex(ValueError, "decision SHA"):
            compose(d, [row])

    def test_reject_future_feature(self):
        d, row = fixture()
        future = "2022-09-06T15:00:00Z"
        d["feature_cutoff"] = row["feature_cutoff"] = future
        with self.assertRaisesRegex(ValueError, "Future-scored"):
            compose(d, [row])

    def test_reject_duplicate_account(self):
        d, row = fixture()
        with self.assertRaisesRegex(ValueError, "accounts must match"):
            compose(d, [row, dict(row)])

    def test_reject_executed_hold(self):
        d, row = fixture()
        row["execution_status"] = "EXECUTED"
        with self.assertRaisesRegex(ValueError, "Executed action"):
            compose(d, [row])


if __name__ == "__main__":
    unittest.main()

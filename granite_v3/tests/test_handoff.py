import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from granite_v3_from_guardian import (
    load_archive, structured_explanation, validate_decision, verify_rows,
    build_rows,
)

ZIP = Path('/home/ibm-user/shared/Guardian_V3_40_Checkpoint_Results_For_Abdel.zip')
LOCAL_ZIP = Path(__file__).resolve().parents[1] / 'Guardian_V3_40_Checkpoint_Results_For_Abdel.zip'
if not ZIP.is_file() and LOCAL_ZIP.is_file():
    ZIP = LOCAL_ZIP
RELEASE_ZIP = Path(__file__).resolve().parents[2] / 'guardian_v3_outputs' / 'Guardian_V3_40_Checkpoint_Results_For_Abdel.zip'
if not ZIP.is_file() and RELEASE_ZIP.is_file():
    ZIP = RELEASE_ZIP


@unittest.skipUnless(ZIP.is_file(), 'Guardian source archive not located at shared path or package root')
class HandoffTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.docs, cls.status = load_archive(ZIP)

    def test_archive_count(self):
        self.assertEqual(len(self.docs), 40)
        self.assertEqual(sum(len(d['recommendations']) for d in self.docs), 63)
        self.assertEqual(len({r['acct'] for d in self.docs for r in d['recommendations']}), 21)

    def test_best_demo_checkpoint(self):
        d = next(d for d in self.docs if d['decision_time']=='2022-09-06T14:00:00Z')
        self.assertEqual(len(d['recommendations']), 10)
        self.assertIn('no account hold was executed', structured_explanation(d['recommendations'][0], d['decision_time']))

    def test_reject_future_feature(self):
        d=copy.deepcopy(self.docs[0]); d['feature_cutoff']='2023-01-01T00:00:00Z'
        with self.assertRaisesRegex(ValueError,'future feature cutoff'):
            validate_decision(d, 'expanded_guardian/decisions/20220906T000000Z.json')

    def test_reject_executed_action(self):
        d=copy.deepcopy(self.docs[0]);d['recommendations'][0]['execution_status']='EXECUTED'
        d['guardian_decision']['recommendations'][0]['execution_status']='EXECUTED'
        with self.assertRaisesRegex(ValueError,'unexpected executed action'):
            validate_decision(d, 'expanded_guardian/decisions/20220906T000000Z.json')

    def test_reject_wrong_count_score(self):
        d=copy.deepcopy(self.docs[0]); d['recommendations'][0]['risk_score']=.01
        d['guardian_decision']['recommendations'][0]['risk_score']=.01
        with self.assertRaisesRegex(ValueError,'risk score/reason_facts mismatch'):
            validate_decision(d, 'expanded_guardian/decisions/20220906T000000Z.json')

    def test_63_deterministic_records_verified(self):
        rows=build_rows(self.docs, use_granite=False, explainer_path=Path('/does-not-matter'),
                        model_path=None, limit=None)
        report=verify_rows(rows, self.docs, expected=63, granite_requested=False)
        self.assertEqual(report['status'], 'PASS')
        self.assertEqual(report['granite_validated_drafts'], 0)
        self.assertEqual(report['explanation_source_counts'], {'structured_template_no_llm': 63})

if __name__=='__main__': unittest.main()

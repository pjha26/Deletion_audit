"""Authored regressions for submission safety and missing proof."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from main import atomic_write, validate_requests, input_fingerprint
from audit import validate
from evidence import observed_state, Evidence


class IntegrityTests(unittest.TestCase):
    def test_fingerprint_tracks_source_bytes_and_ignores_sample_labels(self):
        root = Path(__file__).resolve().parents[2]/'work'
        root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=root) as directory:
            data = Path(directory)
            for name in ('user_identities.csv','user_audit_log.csv','system_activity.csv','deletion_rules.csv','deletion_requests.csv'):
                (data/name).write_text('header\nvalue\n',encoding='utf-8')
            (data/'evidence_files.csv').write_text('file_id,file_path\nsource,source.txt\n',encoding='utf-8')
            (data/'source.txt').write_text('record present',encoding='utf-8')
            fingerprint = input_fingerprint(data,data/'deletion_requests.csv')
            (data/'sample_expected_output.csv').write_text('not an input',encoding='utf-8')
            self.assertEqual(input_fingerprint(data,data/'deletion_requests.csv'),fingerprint)
            (data/'source.txt').write_text('record changed',encoding='utf-8')
            self.assertNotEqual(input_fingerprint(data,data/'deletion_requests.csv'),fingerprint)
            (data/'evidence_files.csv').write_text('file_id,file_path\nsource,../outside.txt\n',encoding='utf-8')
            with self.assertRaises(ValueError):
                input_fingerprint(data,data/'deletion_requests.csv')

    def test_invalid_requests_fail_before_export(self):
        valid = dict(case_id='fictional',email='owner@example.test',requested_at='2026-01-01T00:00:00Z',
                     reported_status='COMPLETE',reported_at='2026-01-02T00:00:00Z',
                     audit_at='2026-01-03T00:00:00Z',request_text='Delete my account')
        validate_requests([valid])
        for requests in ([],[valid,valid],[dict(valid,email='')],
                         [dict(valid,audit_at='2025-01-01T00:00:00Z')],
                         [dict(valid,audit_at='2026-01-03T00:00:00')]):
            with self.assertRaises(ValueError):
                validate_requests(requests)

    def test_failed_atomic_replace_preserves_previous_export(self):
        root = Path(__file__).resolve().parents[2]/'work'
        root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=root) as directory:
            target = Path(directory)/'output.csv'
            target.write_text('previous',encoding='utf-8')
            with patch.object(Path,'replace',side_effect=OSError('disk error')):
                with self.assertRaises(OSError):
                    atomic_write(target,'new')
            self.assertEqual(target.read_text(),'previous')
            self.assertEqual(list(Path(directory).iterdir()),[target])

    def test_http_errors_are_not_absence_proof(self):
        for code in (401,403,429,500,503):
            self.assertEqual(observed_state('USER_PROFILE',{'status_code':code,'rows':0}),'UNKNOWN')
        for field in ('http_status','status_code'):
            e = Evidence(Path('.'),Path('.'))
            e.read_text(f'2026-01-01T00:00:00Z service=account_service event=profile_lookup_completed resource_id=account_719 {field}=503 rows=0',
                        {'file_id':'synthetic','captured_at':'2026-01-01T00:00:01Z'})
            self.assertEqual(e.observations[0].state,'UNKNOWN')

    def test_complete_requires_matching_subject_resource_proof(self):
        row = {'case_id':'fictional','deletion_status':'COMPLETE','steps_json':'[]'}
        with self.assertRaises(ValueError):
            validate([row],[{'case_id':'fictional'}],{'source'})
        step = dict(step_no=1,phase='VERIFICATION',system_id='account_service',resource_id='account_719',
                    operation='VERIFY_RECORD_ABSENT',state='ABSENT',evidence_id='source')
        row['steps_json'] = json.dumps([step])
        wrong = [{'case_id':'fictional','resources':[{'system':'account_service','resource':'other_account','evidence':'source'}]}]
        with self.assertRaises(ValueError):
            validate([row],[{'case_id':'fictional'}],{'source'},wrong)
        right = [{'case_id':'fictional','resources':[{'system':'account_service','resource':'account_719','evidence':'source'}]}]
        validate([row],[{'case_id':'fictional'}],{'source'},right)
        row['steps_json'] = json.dumps([step,dict(step,step_no=2)])
        with self.assertRaises(ValueError):
            validate([row],[{'case_id':'fictional'}],{'source'},right)

import sys
import json
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evidence import Evidence, observed_state


class ReaderTests(unittest.TestCase):
    def test_record_system_overrides_exporting_collector(self):
        work = Path(__file__).resolve().parents[2]/'work'
        work.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=work) as temp:
            path = Path(temp)/'snapshot.json'
            path.write_text(json.dumps({'snapshots':[{'data_store':'generic_history_collector',
                'captured_at':'2026-01-01T00:00:00Z','records':[{'resource_id':'account_719',
                    'system':'account_service','record_type':'USER_PROFILE','result':'NOT_FOUND',
                    'lookup_value':'owner@fiction.test'}]}]}),encoding='utf-8')
            e = Evidence(Path(temp),Path(temp))
            e.read_json(path,{'file_id':'synthetic','captured_at':'2026-01-01T00:00:00Z'})
            self.assertEqual(e.observations[0].system,'account_service')
            self.assertEqual(e.observations[0].state,'ABSENT')

    def test_trace_keeps_subject_when_completion_has_only_resource(self):
        e = Evidence(Path('.'), Path('.'))
        e.read_text('2026-01-01T00:00:00Z service=account_service trace_id=x event=profile_lookup_started lookup_key=old@example.com\n'
                    '2026-01-01T00:00:01Z service=account_service trace_id=x event=profile_lookup_completed resource_id=account_777 rows=1',
                    {'file_id': 'source', 'captured_at': '2026-01-01T00:00:02Z'})
        self.assertEqual(len(e.observations), 1)
        self.assertIn('old@example.com', e.observations[0].identifiers)
        self.assertEqual(e.observations[0].state, 'PRESENT')

    def test_multiple_log_encodings(self):
        lines = [
            '2026-01-01T00:00:00Z {"event":"profile_lookup_completed","resource_id":"account_7","rows":"0"}',
            '2026-01-01T00:00:00Z [INFO] [account_service] [tr-a] profile_lookup_completed: resource_id="account_7" rows="0"',
            '2026-01-01T00:00:00Z | INFO | account_service | tr-a | profile_lookup_completed | resource_id="account_7" rows="0"',
            '2026-01-01T00:00:00Z requestId=tr-a function=account_service message="event=\\"profile_lookup_completed\\" resource_id=\\"account_7\\" rows=\\"0\\""',
        ]
        for line in lines:
            self.assertEqual(Evidence.log_payload(line)['rows'], '0')

    def test_anonymized_requires_all_identifiers_removed(self):
        self.assertEqual(observed_state('ANALYTICS_PROFILE', {'email': None, 'email_hash': 'x'}), 'EXPOSED')
        self.assertEqual(observed_state('ANALYTICS_PROFILE', {'email': None, 'user_id': None}), 'ANONYMIZED')

    def test_tombstone_stable_reference_is_permitted(self):
        self.assertEqual(observed_state('ACCOUNT_TOMBSTONE', {'subject_reference': 'user_7', 'email': None}), 'REDACTED')
        self.assertEqual(observed_state('ACCOUNT_TOMBSTONE', {'subject_reference': 'user_7', 'email_hash': 'x'}), 'EXPOSED')


if __name__ == '__main__':
    unittest.main()

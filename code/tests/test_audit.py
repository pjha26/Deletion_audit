"""Authored scenarios: no participant case IDs or canonical answers are used here."""
import csv
import json
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'code'))
from audit import Auditor, make_steps, validate
from evidence import Observation, tokens
from intent import IntentModel

TIME = '2026-01-10T12:00:00Z'


def observation(resource, category, state, system='account_service', **changes):
    return replace(Observation(resource, system, category, state, TIME, TIME, 'proof', 'test', {}), **changes)


class PlanningTests(unittest.TestCase):
    def test_flow_disabled_before_deleting_profile_and_retained_record_preserved(self):
        records = [observation('account_731', 'USER_PROFILE', 'PRESENT'),
                   observation('data_flow_892', 'DATA_FLOW', 'ACTIVE', 'integration_service'),
                   observation('audit_record_505', 'SECURITY_AUDIT_LOG', 'PRESENT', 'security_service')]
        actions = {'USER_PROFILE': 'DELETE', 'DATA_FLOW': 'DISABLE', 'SECURITY_AUDIT_LOG': 'RETAIN'}
        status, steps = make_steps(records, lambda o: actions[o.category])
        self.assertEqual(status, 'INCOMPLETE')
        remedies = [s['operation'] for s in steps if s['phase'] == 'REMEDIATION']
        self.assertEqual(remedies, ['DISABLE_DATA_FLOW', 'DELETE_RECORD'])
        self.assertTrue(any(s['operation'] == 'VERIFY_RECORD_PRESENT' for s in steps))
        self.assertFalse(any(s['resource_id'] == 'audit_record_505' and s['phase'] == 'REMEDIATION' for s in steps))
        self.assertTrue(all(s['evidence_id'] == '' for s in steps if s['phase'] != 'FINDING'))

    def test_tombstone_hash_requires_redaction_preserving_reference(self):
        obs = observation('tombstone_382', 'ACCOUNT_TOMBSTONE', 'EXPOSED', 'identity_service')
        status, steps = make_steps([obs], lambda o: 'REDACT')
        self.assertEqual(status, 'INCOMPLETE')
        self.assertEqual([s['operation'] for s in steps], ['REPORT_EXPOSED_PII', 'REDACT_RECORD', 'VERIFY_RECORD_REDACTED'])

    def test_complete_has_only_evidenced_verification(self):
        status, steps = make_steps([observation('account_221', 'USER_PROFILE', 'ABSENT')], lambda o: 'DELETE')
        self.assertEqual(status, 'COMPLETE')
        self.assertEqual(steps[0]['operation'], 'VERIFY_RECORD_ABSENT')
        self.assertEqual(steps[0]['evidence_id'], 'proof')

    def test_missing_retained_record_cannot_be_called_complete(self):
        with self.assertRaisesRegex(ValueError, 'retained resource missing'):
            make_steps([observation('audit_record_921', 'SECURITY_AUDIT_LOG', 'ABSENT')], lambda o: 'RETAIN')

    def test_unknown_state_cannot_be_called_complete(self):
        with self.assertRaisesRegex(ValueError, 'Unproven resource state'):
            make_steps([observation('audit_record_921', 'SECURITY_AUDIT_LOG', 'UNKNOWN')], lambda o: 'RETAIN')

    def test_planner_invariant_to_input_order(self):
        records = [observation('account_9', 'USER_PROFILE', 'PRESENT'), observation('account_2', 'USER_PROFILE', 'ABSENT')]
        self.assertEqual(make_steps(records, lambda o: 'DELETE'), make_steps(list(reversed(records)), lambda o: 'DELETE'))

    def test_validator_rejects_evidence_on_future_work(self):
        request = {'case_id': 'synthetic'}
        status, steps = make_steps([observation('account_33', 'USER_PROFILE', 'PRESENT')], lambda o: 'DELETE')
        steps[1]['evidence_id'] = 'proof'
        with self.assertRaisesRegex(ValueError, 'Future'):
            validate([dict(case_id='synthetic', deletion_status=status, steps_json=json.dumps(steps))], [request], {'proof'})


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        work = ROOT / 'work'
        work.mkdir(exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=work)
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'evidence').mkdir()
        self.write_csv('user_identities.csv', [dict(user_id='user_731', name='Synthetic Customer', email='new@fiction.test',
            phone='+1 555 987 6521', email_hash='', updated_at='2026-01-02T00:00:00Z')])
        self.write_csv('user_audit_log.csv', [dict(audit_id='change', user_id='user_731', event_time='2026-01-02T00:00:00Z',
            field_name='email', old_value='old@fiction.test', new_value='new@fiction.test')])
        self.write_csv('system_activity.csv', [], ['activity_id','event_time','event_type','source_system','target_system','resource_id','reported_result','details'])
        self.write_csv('deletion_rules.csv', [dict(rule_id='delete', data_category='USER_PROFILE', condition='Always', required_action='DELETE'),
            dict(rule_id='search', data_category='SEARCH_INDEX_ENTRY', condition='Always', required_action='DELETE'),
            dict(rule_id='cache', data_category='CACHE_ENTRY', condition='Always', required_action='DELETE'),
            dict(rule_id='analytics', data_category='ANALYTICS_PROFILE', condition='Attributable', required_action='ANONYMIZE'),
            dict(rule_id='support', data_category='SUPPORT_MESSAGE', condition='Shared context retained', required_action='REDACT'),
            dict(rule_id='backup', data_category='BACKUP_ARCHIVE', condition='Restore can be blocked', required_action='RETAIN')])
        self.request = dict(case_id='synthetic', email='new@fiction.test', requested_at='2026-01-05T00:00:00Z',
            reported_status='COMPLETE', reported_at='2026-01-06T00:00:00Z', audit_at=TIME,
            request_text='Please erase this customer account and its personal information.')

    def write_csv(self, name, records, fields=None):
        with (self.root / name).open('w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fields or list(records[0]))
            writer.writeheader()
            writer.writerows(records)

    def auditor(self, entries):
        manifest = []
        for no, (time, payload) in enumerate(entries):
            file_id = f'synthetic_evidence_{no}'
            filename = f'evidence/{no}.json'
            (self.root / filename).write_text(json.dumps(payload), encoding='utf-8')
            manifest.append(dict(file_id=file_id, file_path=filename, origin='test', captured_at=time))
        self.write_csv('evidence_files.csv', manifest)
        return Auditor(self.root, self.root / 'cache')

    def test_historic_identifier_and_reported_status_is_only_claim(self):
        a = self.auditor([(TIME, {'records': [{'resource_id':'account_440', 'email':'old@fiction.test'}]})])
        prediction, trace = a.audit(self.request)
        self.assertEqual(prediction['deletion_status'], 'INCOMPLETE')
        self.assertIn('old@fiction.test', trace['identifiers'])
        changed = dict(self.request, reported_status='NOT_STARTED', case_id='renamed')
        other, _ = a.audit(changed)
        self.assertEqual(prediction['steps_json'], other['steps_json'])

    def test_after_cutoff_deletion_does_not_hide_existing_record(self):
        before = {'records': [{'resource_id':'account_440', 'email':'old@fiction.test'}]}
        after = {'records': [{'resource_id':'account_440', 'result':'NOT_FOUND', 'subject_reference':'user_731'}]}
        a = self.auditor([(TIME, before), ('2026-01-11T12:00:00Z', after)])
        prediction, _ = a.audit(self.request)
        self.assertEqual(prediction['deletion_status'], 'INCOMPLETE')
        self.assertEqual(json.loads(prediction['steps_json'])[0]['evidence_id'], 'synthetic_evidence_0')

    def test_non_deletion_does_not_create_actions(self):
        a = self.auditor([(TIME, {'records': [{'resource_id':'account_440', 'email':'old@fiction.test'}]})])
        prediction, _ = a.audit(dict(self.request, request_text='Send me an export. Do not delete my account.'))
        self.assertEqual(prediction['deletion_status'], 'NOT_APPLICABLE')
        self.assertEqual(prediction['steps_json'], '[]')

    def test_similar_email_is_not_same_subject(self):
        a = self.auditor([(TIME, {'records': [{'resource_id':'account_440', 'email':'old@fiction.test', 'result':'NOT_FOUND'},
                                            {'resource_id':'account_441', 'email':'old.jr@fiction.test'}]})])
        prediction, _ = a.audit(self.request)
        self.assertEqual(prediction['deletion_status'], 'COMPLETE')
        self.assertNotIn('account_441', prediction['steps_json'])

    def test_new_primary_absence_does_not_prove_replica_clean(self):
        a = self.auditor([(TIME, {'records': [{'resource_id':'account_440', 'email':'old@fiction.test', 'result':'NOT_FOUND'}]})])
        replica = observation('account_440', 'USER_PROFILE', 'PRESENT', time='2026-01-09T12:00:00Z',
                              available_at='2026-01-09T12:00:00Z', store='customer_profiles_failover_replica',
                              payload={'email':'old@fiction.test'})
        a.by_resource['account_440'].append(len(a.evidence.observations))
        a.evidence.observations.append(replica)
        prediction, trace = a.audit(self.request)
        self.assertEqual(prediction['deletion_status'], 'INCOMPLETE')
        self.assertTrue(any('replica' in warning for warning in trace['warnings']))

    def test_trace_exposes_basis_and_excluded_observations(self):
        a = self.auditor([(TIME, {'records': [{'resource_id':'account_440', 'email':'old@fiction.test'}]}),
            ('2026-01-11T00:00:00Z', {'records': [{'resource_id':'account_440', 'result':'NOT_FOUND'}]})])
        _, trace = a.audit(self.request)
        self.assertEqual(trace['linkage'][0]['basis'], 'exact_identifier')
        self.assertEqual(trace['review']['excluded_observations'], 1)
        self.assertFalse(trace['review']['required'])
        self.assertFalse(trace['timeline'][-1]['included'])

    def test_catalog_display_fields_do_not_merge_another_person(self):
        item = observation('account_440', 'USER_PROFILE', 'PRESENT', payload={
            'catalog_link':'resource belongs to owner@fiction.test', 'business_fields':'displayed other@fiction.test'})
        self.assertIn('owner@fiction.test', item.identifiers)
        self.assertNotIn('other@fiction.test', item.identifiers)

    def test_strict_review_does_not_overwrite_existing_export(self):
        self.auditor([(TIME, {'records':[{'resource_id':'search_992','email':'old@fiction.test'}]})])
        self.write_csv('deletion_requests.csv',[self.request])
        output = self.root/'output.csv'
        output.write_text('existing export',encoding='utf-8')
        from main import run
        with self.assertRaisesRegex(ValueError,'require review'):
            run(self.root,self.root/'deletion_requests.csv',output,self.root/'cache',self.root/'trace.json',strict_review=True)
        self.assertEqual(output.read_text(encoding='utf-8'),'existing export')

    def test_reverse_and_multiple_reference_hops_recover_cleaned_records(self):
        records = [
            {'resource_id':'account_440','email':'old@fiction.test','result':'NOT_FOUND'},
            {'resource_id':'analytics_8120','email':None,'user_id':None,'source_resource_id':'account_440'},
            {'resource_id':'cache_9231','source_resource_id':'analytics_8120','result':'NOT_FOUND'}]
        a = self.auditor([(TIME,{'records':records})])
        prediction, trace = a.audit(self.request)
        self.assertEqual(prediction['deletion_status'],'COMPLETE')
        self.assertEqual({o['resource'] for o in trace['resources']},{'account_440','analytics_8120','cache_9231'})
        self.assertEqual(sum(l['basis']=='explicit_resource_reference' for l in trace['linkage']),2)
        self.assertEqual(len(json.loads(prediction['steps_json'])),3)

    def test_future_reference_does_not_link_a_record_before_cutoff(self):
        a = self.auditor([(TIME,{'records':[{'resource_id':'account_440','email':'old@fiction.test','result':'NOT_FOUND'}]}),
            ('2026-01-11T00:00:00Z',{'records':[{'resource_id':'analytics_8120','email':None,'source_resource_id':'account_440'}]})])
        prediction, trace = a.audit(self.request)
        self.assertNotIn('analytics_8120',prediction['steps_json'])
        self.assertFalse(trace['review']['required'])

    def test_related_record_with_different_owner_requires_review(self):
        a = self.auditor([(TIME,{'records':[
            {'resource_id':'account_440','email':'old@fiction.test','result':'NOT_FOUND'},
            {'resource_id':'analytics_8120','user_id':'user_9999','email':'other@fiction.test','source_resource_id':'account_440'}]})])
        prediction, trace = a.audit(self.request)
        self.assertNotIn('analytics_8120',prediction['steps_json'])
        self.assertTrue(trace['review']['required'])
        self.assertTrue(any('conflicting subject ownership' in reason for reason in trace['review']['reasons']))

    def test_workflow_time_never_overrides_a_different_explicit_owner(self):
        self.write_csv('system_activity.csv',[dict(activity_id='worker',event_time=self.request['reported_at'],
            event_type='DELETE_RECORD',source_system='deletion_worker',target_system='account_service',
            resource_id='account_999',reported_result='SUCCESS',details='Primary deletion operation submitted.')])
        a = self.auditor([(TIME,{'records':[
            {'resource_id':'search_992','email':'old@fiction.test'},
            {'resource_id':'account_999','user_id':'user_9999','email':'other@fiction.test'}]})])
        prediction, trace = a.audit(self.request)
        self.assertNotIn('account_999',prediction['steps_json'])
        self.assertTrue(any('different explicit owner' in reason for reason in trace['warnings']))

    def test_shared_support_keeps_other_subject_contact_information(self):
        a = self.auditor([(TIME,{'records':[
            {'resource_id':'account_440','email':'old@fiction.test','result':'NOT_FOUND'},
            {'resource_id':'support_991','subject_reference':'user_731','requester_email':None,
             'message_text':'The other customer is other@fiction.test. Requested subject details are [REDACTED].'}]})])
        prediction, trace = a.audit(self.request)
        self.assertEqual(prediction['deletion_status'],'COMPLETE')
        support = next(r for r in trace['resources'] if r['resource']=='support_991')
        self.assertEqual(support['state'],'REDACTED')
        self.assertIn('other@fiction.test',support['payload']['message_text'])

    def test_shared_support_still_finds_historical_subject_email(self):
        a = self.auditor([(TIME,{'records':[
            {'resource_id':'support_991','subject_reference':'user_731',
             'message_text':'Contact old@fiction.test and other@fiction.test for this shared delivery.'}]})])
        prediction, _ = a.audit(self.request)
        self.assertEqual(prediction['deletion_status'],'INCOMPLETE')
        self.assertIn('REDACT_RECORD',prediction['steps_json'])
        self.assertNotIn('DELETE_RECORD',prediction['steps_json'])

    def test_restore_link_discovers_copy_but_does_not_assume_its_state(self):
        self.write_csv('system_activity.csv',[dict(activity_id='restore',event_time='2026-01-09T00:00:00Z',
            event_type='RESTORE_BACKUP',source_system='backup_service',target_system='search_service',
            resource_id='backup_230',reported_result='SUCCESS',details='Restore job repopulated downstream resource search_983.')])
        a = self.auditor([(TIME,{'records':[{'resource_id':'backup_230','customer_email':'old@fiction.test','restore_allowed':False}]})])
        prediction, trace = a.audit(self.request)
        self.assertEqual(trace['review']['unproven_resources'],['search_983'])
        self.assertNotIn('REPORT_REMAINING_RECORD',prediction['steps_json'])
        self.assertTrue(trace['review']['required'])


class IntentTests(unittest.TestCase):
    def test_multilingual_and_negation(self):
        model = IntentModel()
        for text in ['Delete the profile I no longer use.', '개인정보 영구 삭제를 신청합니다.', 'Je souhaite effacer mon compte.',
                     'このアカウントを削除してください。']:
            self.assertTrue(model.predict(text)['authorized'], text)
        for text in ['Do not delete anything; I only need an export.', 'Update my phone number.', 'Please remove only marketing subscriptions.']:
            self.assertFalse(model.predict(text)['authorized'], text)

    def test_multiline_and_phone_identifiers(self):
        self.assertIn('person@fiction.test', tokens({'body': 'Customer\nperson@fiction.test\nEnd'}))
        self.assertIn('phone:15559876521', tokens({'phone': '+1 (555) 987-6521'}))


if __name__ == '__main__':
    unittest.main()

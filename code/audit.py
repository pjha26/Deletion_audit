"""Identity resolution, temporal evidence reconciliation, policy and deterministic planning."""
from collections import defaultdict, deque
from dataclasses import asdict, replace
from datetime import datetime
from pathlib import Path
import json
import re

from evidence import Evidence, Observation, RESOURCE, CATEGORIES, prefix, rows, tokens, scalar_items, resource_references
from intent import IntentModel

OPERATIONS = {
    'FINDING': ['REPORT_REMAINING_RECORD', 'REPORT_EXPOSED_PII', 'REPORT_ACTIVE_DATA_FLOW', 'REPORT_RESTORE_RISK'],
    'REMEDIATION': ['DISABLE_DATA_FLOW', 'BLOCK_RESTORE', 'DELETE_RECORD', 'REDACT_RECORD', 'ANONYMIZE_RECORD'],
    'VERIFICATION': ['VERIFY_RECORD_ABSENT', 'VERIFY_RECORD_PRESENT', 'VERIFY_RECORD_REDACTED',
                     'VERIFY_RECORD_ANONYMIZED', 'VERIFY_DATA_FLOW_DISABLED', 'VERIFY_RESTORE_BLOCKED'],
}
STATES = {
    'REPORT_REMAINING_RECORD': 'PRESENT', 'REPORT_EXPOSED_PII': 'PRESENT',
    'REPORT_ACTIVE_DATA_FLOW': 'ACTIVE', 'REPORT_RESTORE_RISK': 'ACTIVE',
    'DISABLE_DATA_FLOW': 'DISABLED', 'BLOCK_RESTORE': 'BLOCKED', 'DELETE_RECORD': 'ABSENT',
    'REDACT_RECORD': 'REDACTED', 'ANONYMIZE_RECORD': 'ANONYMIZED',
    'VERIFY_RECORD_ABSENT': 'ABSENT', 'VERIFY_RECORD_PRESENT': 'PRESENT',
    'VERIFY_RECORD_REDACTED': 'REDACTED', 'VERIFY_RECORD_ANONYMIZED': 'ANONYMIZED',
    'VERIFY_DATA_FLOW_DISABLED': 'DISABLED', 'VERIFY_RESTORE_BLOCKED': 'BLOCKED',
}
TARGETS = {'DELETE': ('ABSENT', 'DELETE_RECORD', 'VERIFY_RECORD_ABSENT'),
           'REDACT': ('REDACTED', 'REDACT_RECORD', 'VERIFY_RECORD_REDACTED'),
           'ANONYMIZE': ('ANONYMIZED', 'ANONYMIZE_RECORD', 'VERIFY_RECORD_ANONYMIZED'),
           'RETAIN': ('PRESENT', '', 'VERIFY_RECORD_PRESENT'),
           'DISABLE': ('DISABLED', 'DISABLE_DATA_FLOW', 'VERIFY_DATA_FLOW_DISABLED'),
           'BLOCK': ('BLOCKED', 'BLOCK_RESTORE', 'VERIFY_RESTORE_BLOCKED')}


def subject_support_state(payload, identifiers, name):
    """Shared support context may keep another person's contact details."""
    fields = {'email', 'phone', 'email_hash', 'name', 'full_name', 'requester_name',
              'requester_email', 'requester_phone', 'message_text', 'message_excerpt'}
    direct = [(key, value) for key, value in scalar_items(payload) if key in fields]
    if not direct:
        return None
    subject_pii = {value for value in identifiers if '@' in value or value.startswith('phone:') or re.fullmatch(r'[a-f0-9]{64}', value)}
    for key, value in direct:
        if value in (None, '', 'null', '[REDACTED]'):
            continue
        if tokens({key: value}) & subject_pii:
            return 'EXPOSED'
        if name and re.search(r'(?<!\w)' + re.escape(name.casefold()) + r'(?!\w)', str(value).casefold()):
            return 'EXPOSED'
    return 'REDACTED'


def step_key(step):
    phase = step['phase']
    return (list(OPERATIONS).index(phase), OPERATIONS[phase].index(step['operation']), step['system_id'], step['resource_id'])


def make_steps(resources, policy):
    """Pure planner: generate findings only for violations; verify the entire relevant final state."""
    result, incomplete = [], False
    decisions = []
    for obs in resources:
        if obs.state not in {'ABSENT', 'PRESENT', 'EXPOSED', 'REDACTED', 'ANONYMIZED', 'ACTIVE', 'DISABLED', 'BLOCKED'}:
            raise ValueError(f'Unproven resource state: {obs.resource}/{obs.state}')
        action = policy(obs)
        target, remediation, verification = TARGETS[action]
        compliant = obs.state == target or (action == 'RETAIN' and obs.state != 'ABSENT')
        decisions.append((obs, target, remediation, verification, compliant))
        incomplete |= not compliant
    def emit(phase, operation, obs, evidence=''):
        result.append(dict(step_no=0, phase=phase, system_id=obs.system, resource_id=obs.resource,
                           operation=operation, state=STATES[operation], evidence_id=evidence))
    for obs, target, remediation, verification, compliant in decisions:
        if not compliant:
            if not remediation:
                raise ValueError(f'Required retained resource missing: {obs.system}/{obs.resource}; contract has no restore-record operation')
            finding = ('REPORT_ACTIVE_DATA_FLOW' if target == 'DISABLED' else
                       'REPORT_RESTORE_RISK' if target == 'BLOCKED' else
                       'REPORT_REMAINING_RECORD' if target == 'ABSENT' else 'REPORT_EXPOSED_PII')
            emit('FINDING', finding, obs, obs.evidence)
            emit('REMEDIATION', remediation, obs)
        emit('VERIFICATION', verification, obs, '' if incomplete else obs.evidence)
    result.sort(key=step_key)
    for no, step in enumerate(result, 1):
        step['step_no'] = no
    return ('INCOMPLETE' if incomplete else 'COMPLETE'), result


class Auditor:
    def __init__(self, dataset: Path, cache: Path):
        self.dataset = dataset
        self.evidence = Evidence(dataset, cache).load()
        self.users = rows(dataset / 'user_identities.csv')
        self.history = rows(dataset / 'user_audit_log.csv')
        self.activity = rows(dataset / 'system_activity.csv')
        self.rules = rows(dataset / 'deletion_rules.csv')
        self.actions = {r['data_category']: r['required_action'] for r in self.rules}
        self.intent = IntentModel()
        self.identity_index = defaultdict(set)
        self.histories = defaultdict(list)
        for user in self.users:
            for token in tokens(user):
                self.identity_index[token].add(user['user_id'])
        for row in self.history:
            self.histories[row['user_id']].append(row)
            for token in tokens([row['old_value'], row['new_value']]):
                self.identity_index[token].add(row['user_id'])
        self.user_by_id = {u['user_id']: u for u in self.users}
        self.link_documents()
        self.by_token = defaultdict(set)
        self.by_resource = defaultdict(list)
        for no, obs in enumerate(self.evidence.observations):
            for token in obs.identifiers:
                self.by_token[token].add(no)
            self.by_resource[obs.resource].append(no)
        self.activity_tokens = [(r, tokens(r['details'])) for r in self.activity]
        self.resource_links = defaultdict(list)
        for obs in self.evidence.observations:
            for reference, field in resource_references(obs.payload):
                self.add_resource_link(obs.resource, reference, obs.time, obs.available_at, obs.evidence,
                                       f'{obs.location} / {field}')
        for activity in self.activity:
            if activity['event_type'] == 'RESTORE_BACKUP':
                for target in re.findall(r'\bdownstream resource\s+(' + RESOURCE + r')\b', activity['details']):
                    self.add_resource_link(activity['resource_id'], target, activity['event_time'],
                        activity['event_time'], activity['activity_id'], 'Explicit restore source-to-destination resource link')

    def add_resource_link(self, source, target, time, available_at, evidence, location):
        if source == target:
            return
        for left, right in ((source, target), (target, source)):
            self.resource_links[left].append({'target': right, 'time': time, 'available_at': available_at,
                                               'evidence_id': evidence, 'location': location})

    def resource_owners(self, resource, cutoff):
        by_time = defaultdict(set)
        for index in self.by_resource.get(resource, ()):
            obs = self.evidence.observations[index]
            if obs.time > cutoff or obs.available_at > cutoff:
                continue
            for key, value in scalar_items(obs.payload):
                if key in {'user_id', 'subject_reference', 'customer_reference'} and isinstance(value, str) and re.fullmatch(r'user_\d+', value):
                    by_time[obs.time].add(value)
        return by_time[max(by_time)] if by_time else set()

    def expand_resource_links(self, resources, uid, cutoff, linkage, warnings):
        queue = deque(sorted(resources))
        while queue:
            source = queue.popleft()
            for edge in self.resource_links.get(source, ()):
                target = edge['target']
                if target in resources or edge['time'] > cutoff or edge['available_at'] > cutoff:
                    continue
                owners = self.resource_owners(target, cutoff)
                if owners and uid not in owners:
                    warnings.append(f'Resource link {source} → {target} has conflicting subject ownership; automatic treatment excluded')
                    continue
                resources.add(target)
                queue.append(target)
                linkage.append({'resource_id': target, 'source_resource_id': source, 'basis': 'explicit_resource_reference',
                                'identifiers': [], 'evidence_id': edge['evidence_id'], 'location': edge['location']})

    def link_documents(self):
        """Explicit catalog aliases connect business documents without filename-based verdicts."""
        for activity in self.activity:
            if activity['event_type'] != 'LINK_RESOURCE_IDENTITY':
                continue
            alias = re.search(r'\(([^)]+)\)', activity['details'])
            if not alias:
                continue
            resource = activity['resource_id']
            for document in self.evidence.documents:
                text = document['text']
                if alias.group(1) not in text:
                    continue
                system = activity['target_system']
                category = CATEGORIES.get(prefix(resource), '')
                if 'belongs only' in activity['details']:
                    category = 'SUPPORT_ATTACHMENT'
                if category == 'DATA_FLOW':
                    if not re.search(r'continuous|events delivered|enabled', text, re.I):
                        continue
                    state = 'DISABLED' if re.search(r'\bdisabled\b', text, re.I) else 'ACTIVE'
                elif category == 'BACKUP_ARCHIVE':
                    state = 'BLOCKED' if re.search(r'restore.{0,20}(?:blocked|denied)', text, re.I) else 'ACTIVE'
                elif category in {'ANALYTICS_PROFILE', 'SUPPORT_MESSAGE'}:
                    state = 'EXPOSED'
                elif category == 'ACCOUNT_TOMBSTONE':
                    if not re.search(r'retained reference|customer reference registry', text, re.I):
                        continue
                    state = 'EXPOSED' if re.search(r'[\w.+%-]+@[\w.-]+\.[A-Za-z]{2,}', text) else 'REDACTED'
                else:
                    state = 'PRESENT'
                matching_lines = [line for line in text.splitlines() if alias.group(1) in line]
                direct_emails = tokens('\n'.join(matching_lines))
                direct_emails = {t for t in direct_emails if '@' in t}
                catalog_emails = {t for t in tokens(activity['details']) if '@' in t}
                payload = {'catalog_link': activity['details'], 'business_fields': '\n'.join(matching_lines)}
                if direct_emails and catalog_emails and not direct_emails & catalog_emails:
                    payload['identity_conflict'] = 'Explicit catalog resource link differs from displayed contact fields'
                self.evidence.add(resource, payload, document, 'catalog alias / document',
                    time=document['captured_at'], system=system, category=category, state=state, rank=3)
                self.evidence.observations[-1].available_at = max(document['captured_at'], activity['event_time'])

    def identities(self, request):
        email = request['email'].strip().casefold()
        users = self.identity_index[email]
        if len(users) != 1:
            raise ValueError(f"Identity unresolved or ambiguous for {request['case_id']}: {len(users)} matches")
        uid = next(iter(users))
        identity = dict(self.user_by_id[uid])
        cutoff = request['audit_at']
        # Roll current fields back before gathering historical identifiers available by cutoff.
        history = sorted(self.histories[uid], key=lambda r: (r['event_time'], r['audit_id']), reverse=True)
        for row in history:
            if row['event_time'] > cutoff:
                identity[row['field_name']] = row['old_value']
        values = tokens(identity) | {email, uid}
        for row in history:
            if row['event_time'] <= cutoff:
                values |= tokens([row['old_value'], row['new_value']])
        return uid, values

    def policy(self, obs, at=None):
        at = at or obs.time
        if obs.category in {'SECURITY_AUDIT_LOG', 'LEGAL_HOLD_RECORD'}:
            until = obs.payload.get('retention_until') or obs.payload.get('retained_until')
            if until and until <= at:
                raise ValueError(f'Retention condition expired for {obs.resource}; no fallback policy supplied')
            if obs.category == 'LEGAL_HOLD_RECORD' and obs.payload.get('hold_active') is False:
                raise ValueError(f'Legal hold inactive for {obs.resource}; no fallback policy supplied')
        if obs.category == 'DATA_FLOW':
            return 'DISABLE'
        if obs.category == 'BACKUP_ARCHIVE':
            if self.actions.get(obs.category) != 'RETAIN':
                raise ValueError('Unsupported backup policy')
            if str(obs.payload.get('archive_present', 'true')).lower() in {'false', '0'}:
                raise ValueError('Required retained archive is missing; restore-access denial alone cannot prove retention')
            return 'BLOCK'
        if obs.category not in self.actions:
            raise ValueError(f'No supplied policy for {obs.category}')
        return self.actions[obs.category]

    def audit(self, request):
        intent = self.intent.predict(request['request_text'])
        trace = {'case_id': request['case_id'], 'intent': intent, 'warnings': []}
        if not intent['authorized']:
            trace.update(review={'required': False, 'reasons': [], 'scope': 'No deletion authorized'}, linkage=[], timeline=[])
            return {'case_id': request['case_id'], 'deletion_status': 'NOT_APPLICABLE', 'steps_json': '[]'}, trace
        uid, identifiers = self.identities(request)
        cutoff = request['audit_at']
        eligible = lambda o: o.time <= cutoff and o.available_at <= cutoff
        selected = set()
        for token in identifiers:
            selected |= {i for i in self.by_token.get(token, ()) if eligible(self.evidence.observations[i])}
        resources = {self.evidence.observations[i].resource for i in selected}
        linkage = []
        for i in sorted(selected):
            observation = self.evidence.observations[i]
            matched = sorted(identifiers & observation.identifiers)
            linkage.append({'resource_id': observation.resource, 'basis': 'catalog' if 'catalog_link' in observation.payload else 'exact_identifier',
                            'identifiers': matched, 'evidence_id': observation.evidence, 'location': observation.location})
        # Historical readback/resource linkage remains valid after fields are anonymized.
        for activity, linked_tokens in self.activity_tokens:
            if activity['event_time'] <= cutoff and identifiers & linked_tokens:
                resources.add(activity['resource_id'])
                linkage.append({'resource_id': activity['resource_id'], 'basis': 'activity_identity',
                                'identifiers': sorted(identifiers & linked_tokens), 'evidence_id': activity['activity_id'], 'location': activity['details']})
        self.expand_resource_links(resources, uid, cutoff, linkage, trace['warnings'])
        if not any(prefix(r) in {'account', 'tombstone'} for r in resources):
            # shortcut: time correlation is weaker than a request ID, replace when explicit workflow correlation IDs are available.
            # Legacy workflow events lack subject fields. A unique nearby primary operation
            # supplies a candidate resource; readback evidence must still establish its state.
            reported = datetime.fromisoformat(request['reported_at'].replace('Z', '+00:00'))
            candidates = {a['resource_id'] for a in self.activity
                          if a['event_type'] == 'DELETE_RECORD' and a['target_system'] == 'account_service'
                          and a['event_time'] <= cutoff
                          and abs((datetime.fromisoformat(a['event_time'].replace('Z', '+00:00')) - reported).total_seconds()) <= 600}
            if len(candidates) == 1:
                candidate = next(iter(candidates))
                owners = self.resource_owners(candidate, cutoff)
                if owners and uid not in owners:
                    trace['warnings'].append(f'Workflow-time candidate {candidate} has a different explicit owner; automatic treatment excluded')
                else:
                    resources |= candidates
                    linkage.extend({'resource_id': resource, 'basis': 'workflow_time', 'identifiers': [], 'evidence_id': '',
                                    'location': 'Unique primary operation within ten minutes of workflow report; candidate link only'} for resource in sorted(candidates))
                    trace['warnings'].append('Primary resource linked by unique workflow-time correlation; no explicit subject key in legacy event')
                    self.expand_resource_links(resources, uid, cutoff, linkage, trace['warnings'])
        for resource in list(resources):
            selected |= {i for i in self.by_resource.get(resource, ()) if eligible(self.evidence.observations[i])}
        observations = [self.evidence.observations[i] for i in selected]
        observations = [replace(o, state=scoped) if o.category == 'SUPPORT_MESSAGE' and o.state == 'EXPOSED'
                        and (scoped := subject_support_state(o.payload, identifiers, self.user_by_id[uid]['name'])) else o
                        for o in observations]
        relevant_files = {o.evidence for o in observations}
        for resource in resources:
            if prefix(resource) != 'account':
                continue
            for scope in self.evidence.scopes:
                if scope['table'] == 'customer_profiles' and scope['evidence'] not in relevant_files:
                    continue
                if scope['system'] == 'account_service' and scope['time'] <= cutoff and scope['available_at'] <= cutoff and resource not in scope['present']:
                    observations.append(Observation(resource, 'account_service', 'USER_PROFILE', 'ABSENT',
                        scope['time'], scope['available_at'], scope['evidence'], scope['table'] + ': missing row',
                        {}, scope['table'], 2))
        grouped = defaultdict(list)
        for obs in observations:
            grouped[(obs.system, obs.resource)].append(obs)
        latest = []
        for key, group in sorted(grouped.items()):
            newest = max(o.time for o in group)
            current = [o for o in group if o.time == newest]
            # At one snapshot, a surviving copy outweighs absence in a different replica.
            severity = {'ABSENT': 0, 'REDACTED': 1, 'ANONYMIZED': 1, 'DISABLED': 1, 'BLOCKED': 1,
                        'PRESENT': 2, 'EXPOSED': 3, 'ACTIVE': 3}
            obs = max(current, key=lambda o: (severity.get(o.state, 0), o.rank, o.evidence))
            replicas = defaultdict(list)
            for item in group:
                if 'replica' in item.store:
                    replicas[item.store].append(item)
            for physical in replicas.values():
                replica = max(physical, key=lambda o: (o.time, severity.get(o.state, 0)))
                # A newer primary read cannot establish that an older independent replica was cleaned.
                if replica.state in {'PRESENT', 'EXPOSED', 'ACTIVE'} and obs.state in {'ABSENT', 'REDACTED', 'ANONYMIZED', 'DISABLED', 'BLOCKED'}:
                    obs = replica
                    trace['warnings'].append(replica.resource + ': surviving replica has no subsequent cleanup proof')
            consistent = [o for o in group if o.state == obs.state and o.time[:10] == newest[:10]]
            if consistent:
                obs = max(consistent, key=lambda o: (o.rank, o.time, o.evidence))
            latest.append(obs)
        unproven = sorted(resources - {o.resource for o in observations})
        trace['warnings'].extend(f'Explicitly linked resource {resource} has no state proof at the audit cutoff' for resource in unproven)
        if not latest:
            raise ValueError(f"No auditable resources for {request['case_id']}")
        status, steps = make_steps(latest, lambda obs: self.policy(obs, cutoff))
        if not any(o.category in {'USER_PROFILE', 'ACCOUNT_TOMBSTONE'} for o in latest):
            trace['warnings'].append('No primary account/tombstone resource could be explicitly linked; verification scope is limited to discovered resources')
        if intent['supported_fraction'] < 0.2:
            trace['warnings'].append('Low training-vocabulary coverage; intent score is not calibrated confidence')
        for obs in latest:
            if 'identity_conflict' in obs.payload:
                trace['warnings'].append(obs.resource + ': ' + obs.payload['identity_conflict'])
        trace['warnings'] = list(dict.fromkeys(trace['warnings']))
        timeline = [{'resource_id': o.resource, 'system_id': o.system, 'state': o.state, 'time': o.time,
                     'container_captured_at': o.container_captured_at, 'evidence_id': o.evidence, 'location': o.location,
                     'included': eligible(o)} for resource in sorted(resources) for i in self.by_resource.get(resource, ())
                    for o in [self.evidence.observations[i]]]
        timeline.sort(key=lambda event: (event['time'], event['system_id'], event['resource_id'], event['evidence_id']))
        trace.update(user_id=uid, identifiers=sorted(identifiers), resources=[asdict(o) for o in latest],
                     linkage=linkage, timeline=timeline,
                     review={'required': bool(trace['warnings']), 'reasons': trace['warnings'],
                             'scope': 'Discovered participant-corpus resources',
                             'primary_linked': any(o.category in {'USER_PROFILE', 'ACCOUNT_TOMBSTONE'} for o in latest),
                             'unproven_resources': unproven,
                             'excluded_observations': sum(not event['included'] for event in timeline)})
        return {'case_id': request['case_id'], 'deletion_status': status,
                'steps_json': json.dumps(steps, ensure_ascii=False, separators=(',', ':'))}, trace


def validate(predictions, requests, evidence_ids):
    expected = sorted(r['case_id'] for r in requests)
    actual = [r['case_id'] for r in predictions]
    if actual != expected or len(set(actual)) != len(actual):
        raise ValueError('Prediction case coverage/order mismatch')
    for row in predictions:
        status = row['deletion_status']
        if status not in {'COMPLETE', 'INCOMPLETE', 'NOT_APPLICABLE'}:
            raise ValueError('Invalid status')
        steps = json.loads(row['steps_json'])
        if not isinstance(steps, list) or (status == 'NOT_APPLICABLE' and steps):
            raise ValueError('Invalid steps array')
        if steps != sorted(steps, key=step_key):
            raise ValueError('Step ordering violation')
        for no, step in enumerate(steps, 1):
            if set(step) != {'step_no', 'phase', 'system_id', 'resource_id', 'operation', 'state', 'evidence_id'}:
                raise ValueError('Step fields mismatch')
            if step['step_no'] != no or step['state'] != STATES[step['operation']]:
                raise ValueError('Step number/state mismatch')
            must_cite = step['phase'] == 'FINDING' or status == 'COMPLETE'
            if must_cite and step['evidence_id'] not in evidence_ids:
                raise ValueError('Missing or invalid evidence')
            if not must_cite and step['evidence_id'] != '':
                raise ValueError('Future step must not cite completed evidence')
            if status == 'COMPLETE' and step['phase'] != 'VERIFICATION':
                raise ValueError('Complete case contains non-verification step')

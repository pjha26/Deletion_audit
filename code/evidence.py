"""Participant evidence readers. Every observation keeps its actual source and time."""
from __future__ import annotations

import csv
import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

EMAIL = r"[\w.+%-]+@[\w.-]+\.[A-Za-z]{2,}"
RESOURCE = r"(?:account|search|analytics|support|backup|data_flow|audit_record|export|marketing|object|tombstone|cache|email_delivery|legal_hold|telemetry)_[0-9]+"
TOKEN = re.compile(rf"{EMAIL}|\buser_\d+\b|\b[a-fA-F0-9]{{64}}\b|\b{RESOURCE}\b", re.I)
SYSTEMS = {
    'account': 'account_service', 'search': 'search_service',
    'analytics': 'analytics_platform', 'support': 'support_platform',
    'backup': 'backup_service', 'data_flow': 'integration_service',
    'audit_record': 'security_service', 'export': 'export_service',
    'marketing': 'marketing_platform', 'object': 'object_storage',
    'tombstone': 'identity_service', 'cache': 'cache_service',
    'email_delivery': 'email_delivery_service', 'legal_hold': 'legal_service',
    'telemetry': 'telemetry_service',
}
CATEGORIES = {
    'account': 'USER_PROFILE', 'search': 'SEARCH_INDEX_ENTRY',
    'analytics': 'ANALYTICS_PROFILE', 'support': 'SUPPORT_MESSAGE',
    'backup': 'BACKUP_ARCHIVE', 'data_flow': 'DATA_FLOW',
    'audit_record': 'SECURITY_AUDIT_LOG', 'export': 'USER_EXPORT',
    'marketing': 'MARKETING_PROFILE', 'object': 'SUPPORT_ATTACHMENT',
    'tombstone': 'ACCOUNT_TOMBSTONE', 'cache': 'CACHE_ENTRY',
    'email_delivery': 'EMAIL_DELIVERY_LOG', 'legal_hold': 'LEGAL_HOLD_RECORD',
    'telemetry': 'PRODUCT_TELEMETRY',
}
STATE_MAP = {'FOUND': 'PRESENT', 'NOT_FOUND': 'ABSENT', 'IDENTIFIABLE': 'EXPOSED',
             'ACTIVE': 'ACTIVE', 'BLOCKED': 'BLOCKED', 'DISABLED': 'DISABLED',
             'REDACTED': 'REDACTED', 'ANONYMIZED': 'ANONYMIZED'}


def rows(path: Path) -> list[dict]:
    with path.open(encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(stream))


def prefix(resource: str) -> str:
    return resource.rsplit('_', 1)[0]


def tokens(value: Any) -> set[str]:
    if isinstance(value, dict):
        result = set().union(*(tokens(v) for v in value.values())) if value else set()
        for key, item in value.items():
            if 'phone' in key.lower() and item:
                digits = re.sub(r'\D', '', str(item))
                if 7 <= len(digits) <= 15:
                    result.add('phone:' + digits)
        return result
    if isinstance(value, (list, tuple)):
        return set().union(*(tokens(v) for v in value)) if value else set()
    text = str(value)
    result = {m.group().casefold() for m in TOKEN.finditer(text)}
    for phone in re.findall(r'\+[0-9][0-9 ()-]{5,}[0-9]', text):
        digits = re.sub(r'\D', '', phone)
        if 7 <= len(digits) <= 15:
            result.add('phone:' + digits)
    return result


def is_true(value: Any) -> bool:
    return str(value).lower() in {'true', '1', 'yes', 'enabled', 'active'}


def scalar_items(value: Any):
    if isinstance(value, dict):
        for key, item in value.items():
            if isinstance(item, (dict, list)):
                yield from scalar_items(item)
            else:
                yield key, item
    elif isinstance(value, list):
        for item in value:
            yield from scalar_items(item)


def classify(resource: str, payload: dict, collection: str = '') -> tuple[str, str]:
    kind = prefix(resource)
    system = payload.get('system') or payload.get('origin_system') or SYSTEMS.get(kind, '')
    category = payload.get('record_type') or payload.get('data_category') or CATEGORIES.get(kind, '')
    if kind == 'support' and ('file_name' in payload or 'attachment' in collection.lower()):
        category = 'SUPPORT_ATTACHMENT'
    if str(payload.get('account_status', '')).upper() in {'DELETED', 'TOMBSTONE'}:
        category = 'ACCOUNT_TOMBSTONE'
    return system, category


def observed_state(category: str, payload: dict) -> str:
    result = str(payload.get('result', '')).upper()
    if result in STATE_MAP:
        return STATE_MAP[result]
    if 'status_code' in payload and int(payload['status_code']) == 404:
        return 'ABSENT'
    if category == 'DATA_FLOW':
        return 'ACTIVE' if is_true(payload.get('enabled', False)) else 'DISABLED'
    if category == 'BACKUP_ARCHIVE':
        return 'ACTIVE' if is_true(payload.get('restore_allowed', False)) else 'BLOCKED'
    if category == 'ANALYTICS_PROFILE' or category == 'PRODUCT_TELEMETRY':
        identifying = [(k, v) for k, v in scalar_items(payload)
                       if k in {'user_id', 'customer_reference', 'subject_reference', 'email', 'phone', 'email_hash'}]
        return 'EXPOSED' if any(v not in (None, '', 'null', '[REDACTED]') for _, v in identifying) else 'ANONYMIZED'
    if category in {'SUPPORT_MESSAGE', 'ACCOUNT_TOMBSTONE', 'EMAIL_DELIVERY_LOG'}:
        direct = [(k, v) for k, v in scalar_items(payload)
                  if k in {'email', 'phone', 'email_hash', 'name', 'full_name', 'requester_name',
                           'requester_email', 'requester_phone', 'message_text', 'message_excerpt'}]
        exposed = any(v not in (None, '', 'null', '[REDACTED]') and
                      (k not in {'message_text', 'message_excerpt'} or bool(re.search(EMAIL, str(v))))
                      for k, v in direct)
        return 'EXPOSED' if exposed else 'REDACTED'
    return 'PRESENT'


@dataclass
class Observation:
    resource: str
    system: str
    category: str
    state: str
    time: str
    available_at: str
    evidence: str
    location: str
    payload: dict = field(default_factory=dict)
    store: str = ''
    rank: int = 2
    container_captured_at: str = ''

    @property
    def identifiers(self) -> set[str]:
        if 'catalog_link' in self.payload:
            return tokens(self.payload['catalog_link'])
        return tokens(self.payload)


class Evidence:
    def __init__(self, dataset: Path, cache: Path):
        self.dataset, self.cache = dataset, cache
        self.observations: list[Observation] = []
        self.scopes: list[dict] = []
        self.coverage: list[dict] = []
        self.documents: list[dict] = []
        self.ocr_calls = 0
        self.cache_hits = 0
        self.ocr = None
        self.ocr_quality = {}

    def add(self, resource, payload, entry, location, *, time='', system='', category='', state='', store='', rank=2):
        sys, cat = classify(resource, payload, store)
        if not (system or sys) or not (category or cat):
            raise ValueError(f'Unclassified resource {resource} at {location}')
        cat = category or cat
        self.observations.append(Observation(resource, system or sys, cat,
            state or observed_state(cat, payload), time or entry['captured_at'],
            time or entry['captured_at'], entry['file_id'], location, payload, store, rank, entry['captured_at']))

    def load(self):
        root = self.dataset.resolve()
        for entry in rows(self.dataset / 'evidence_files.csv'):
            path = (self.dataset / entry['file_path']).resolve()
            if not path.is_relative_to(root):
                raise ValueError('Evidence path escapes dataset')
            before = len(self.observations)
            if path.suffix == '.json':
                self.read_json(path, entry)
            elif path.suffix == '.sql':
                self.read_sql(path, entry)
            elif path.suffix in {'.log', '.txt'}:
                self.read_text(path.read_text(encoding='utf-8'), entry)
            elif path.suffix == '.pdf':
                from pypdf import PdfReader
                pages = [p.extract_text() or '' for p in PdfReader(path).pages]
                if not all(p.strip() for p in pages):
                    raise ValueError(f'Scanned PDF requires OCR: {path.name}')
                text = '\n'.join(pages)
                self.documents.append(dict(entry, text=text, location='PDF pages'))
                self.read_document(text, entry)
            elif path.suffix == '.png':
                text = self.read_image(path)
                self.documents.append(dict(entry, text=text, location='OCR lines'))
                self.read_document(text, entry)
            else:
                raise ValueError(f'Unsupported evidence: {path}')
            self.coverage.append({'file_id': entry['file_id'], 'path': entry['file_path'],
                                  'observations': len(self.observations) - before, 'read': True,
                                  **self.ocr_quality.get(str(path), {})})
        return self

    def read_image(self, path):
        digest = hashlib.sha256(path.read_bytes() + b'rapidocr-v1-layout2').hexdigest()
        dest = self.cache / 'ocr' / f'{digest}.json'
        if dest.exists():
            result = json.loads(dest.read_text(encoding='utf-8'))
            self.cache_hits += 1
        else:
            if self.ocr is None:
                from rapidocr_onnxruntime import RapidOCR
                self.ocr = RapidOCR(intra_op_num_threads=2, inter_op_num_threads=2)
            result, _ = self.ocr(str(path))
            if not result:
                raise ValueError(f'No OCR text: {path.name}')
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(json.dumps(result, ensure_ascii=False), encoding='utf-8')
            self.ocr_calls += 1
        confidences = [float(row[2]) for row in result]
        self.ocr_quality[str(path)] = {'ocr_lines': len(result),
            'minimum_ocr_confidence': round(min(confidences), 4),
            'low_confidence_lines': sum(c < 0.85 for c in confidences)}
        # Preserve reading order, joining boxes on a common baseline for console tables.
        bands = []
        for box, text, confidence in sorted(result, key=lambda r: (sum(p[1] for p in r[0])/4, r[0][0][0])):
            y = sum(p[1] for p in box) / 4
            if bands and abs(bands[-1][0] - y) < 12:
                bands[-1][1].append((box[0][0], text))
            else:
                bands.append((y, [(box[0][0], text)]))
        return '\n'.join(' | '.join(text for _, text in sorted(band)) for _, band in bands)

    def read_json(self, path, entry):
        data = json.loads(path.read_text(encoding='utf-8'))

        def walk(obj, context=None, location='$'):
            context = dict(context or {})
            if isinstance(obj, dict):
                for key in ('data_store', 'collection', 'captured_at', 'observed_at'):
                    if key in obj:
                        context[key] = obj[key]
                if 'resource_id' in obj:
                    resource = obj['resource_id']
                    payload = dict(obj)
                    if isinstance(payload.get('profile'), dict):
                        payload.update(payload['profile'])
                    if isinstance(payload.get('hits'), dict):
                        if payload['hits'].get('total') == 0:
                            payload['result'] = 'NOT_FOUND'
                        elif payload['hits'].get('documents'):
                            payload.update(payload['hits']['documents'][0])
                    self.add(resource, payload, entry, location,
                             system=obj.get('system') or obj.get('origin_system') or context.get('data_store', ''),
                             time=obj.get('recorded_at') or obj.get('observed_at') or context.get('captured_at', ''),
                             store=context.get('collection', ''), rank=4 if 'service_exports' in data else 2)
                    return
                for key, value in obj.items():
                    child = dict(context)
                    if key in SYSTEMS.values():
                        child['data_store'] = key
                    walk(value, child, f'{location}.{key}')
            elif isinstance(obj, list):
                for i, value in enumerate(obj):
                    walk(value, context, f'{location}[{i}]')
        walk(data)

    def read_sql(self, path, entry):
        conn = sqlite3.connect(':memory:')
        # Snapshot SQL is data: disallow file attachment, extension loading and writes outside memory.
        forbidden = {sqlite3.SQLITE_ATTACH, sqlite3.SQLITE_DETACH}
        def authorize(action, arg1, arg2, db, source):
            if action in forbidden or (action == sqlite3.SQLITE_FUNCTION and str(arg2).lower() in {'load_extension', 'writefile', 'readfile'}):
                return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK
        conn.set_authorizer(authorize)
        try:
            conn.executescript(path.read_text(encoding='utf-8'))
            conn.row_factory = sqlite3.Row
            tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
            for table in tables:
                safe = '"' + table.replace('"', '""') + '"'
                records = [dict(r) for r in conn.execute(f'SELECT * FROM {safe}')]
                if table == 'snapshot_scope':
                    for r in records:
                        self.scopes.append(dict(system=r['origin_system'], category='USER_PROFILE',
                            time=r['captured_at'], available_at=entry['captured_at'], evidence=entry['file_id'],
                            table='customer_profiles', present={x['resource_id'] for x in conn.execute('SELECT resource_id FROM customer_profiles')}))
                    continue
                for index, record in enumerate(records):
                    if 'resource_id' not in record:
                        continue
                    payload = json.loads(record['record_json']) if 'record_json' in record else record
                    self.add(record['resource_id'], payload, entry, f'{table}[{index}]',
                             system=record.get('origin_system', ''), time=entry['captured_at'], store=table, rank=4)
                if table.startswith('customer_profiles'):
                    self.scopes.append(dict(system='account_service', category='USER_PROFILE',
                        time=entry['captured_at'], available_at=entry['captured_at'], evidence=entry['file_id'],
                        table=table, present={r['resource_id'] for r in records}))
        finally:
            conn.close()

    @staticmethod
    def key_values(text):
        return {key: (quoted or plain) for key, quoted, plain in
                re.findall(r'(\w+)=(?:"([^"]*)"|([^\s]+))', text)}

    @classmethod
    def log_payload(cls, line):
        if line[21:].lstrip().startswith('{'):
            return json.loads(line[21:])
        if 'message="' in line and '\\"' in line:
            outer = cls.key_values(line.split('message=', 1)[0])
            inner = line.split('message="', 1)[1][:-1].replace('\\"', '"')
            return dict(cls.key_values(inner), trace_id=outer.get('requestId', ''), service=outer.get('function', ''))
        payload = cls.key_values(line)
        bracket = re.match(r'\S+ \[\w+\] \[(\w+)\] \[([^]]+)\] (\w+):', line)
        pipe = re.match(r'\S+ \| \w+ \| (\w+) \| ([^|]+) \| (\w+) \|', line)
        syslog = re.match(r'\S+ <\d+>\d+ \S+ (\w+) (\S+) - - ', line)
        if bracket or pipe:
            service, trace, event = (bracket or pipe).groups()
            payload.update(service=service, trace_id=trace.strip(), event=event)
        elif syslog:
            service, trace = syslog.groups()
            payload.update(service=service, trace_id=trace)
        return payload

    def read_text(self, text, entry):
        traces = {}
        for no, line in enumerate(text.splitlines(), 1):
            # A handover is a table with an explicit record state.
            match = re.match(r'- (\S+) \| (\w+) \| (\w+) \| (\w+) \| (\w+) \| (.*)', line)
            if match:
                time, system, resource, category, result, subject = match.groups()
                self.add(resource, {'subject_reference': subject, 'result': result}, entry,
                         f'line {no}', time=time, system=system, category=category)
                continue
            p = self.log_payload(line)
            if not p:
                continue
            trace = p.get('trace_id') or p.get('request_id')
            if trace:
                history = traces.setdefault(trace, {})
                context_keys = {'lookup_key', 'match_key', 'subject_key', 'scan_key', 'owner_key',
                                'subject_ref', 'subject_reference', 'correlation_key', 'service', 'resource_id'}
                previous = dict(history)
                history.update({k: v for k, v in p.items() if k in context_keys})
                p = dict(previous, **p)
            resource = p.get('resource_id')
            if not resource or not re.fullmatch(RESOURCE, resource):
                continue
            event = p.get('event', '')
            if event.endswith('_started') or event in {'connection_acquired', 'dependency_retry', 'dependency_recovered', 'deletion_marker_check', 'thumbnail_failed'}:
                continue
            time = line[:20] if re.match(r'\d{4}-\d{2}-\d{2}T', line) else entry['captured_at']
            system, category = classify(resource, p)
            state = ''
            if p.get('result', '').upper() in STATE_MAP:
                state = STATE_MAP[p['result'].upper()]
            elif 'rows' in p:
                state = 'PRESENT' if int(p['rows']) else 'ABSENT'
            elif p.get('result') in {'hit', 'miss'}:
                state = 'PRESENT' if p['result'] == 'hit' else 'ABSENT'
            elif category == 'DATA_FLOW' and 'enabled' in p:
                state = 'ACTIVE' if is_true(p['enabled']) else 'DISABLED'
            elif category == 'BACKUP_ARCHIVE' and 'restore_allowed' in p:
                state = 'ACTIVE' if is_true(p['restore_allowed']) else 'BLOCKED'
            elif category == 'BACKUP_ARCHIVE' and 'eligible' in p:
                state = 'ACTIVE' if is_true(p['eligible']) and not is_true(p.get('deletion_block')) else 'BLOCKED'
            elif category == 'BACKUP_ARCHIVE' and p.get('decision') == 'deny':
                state = 'BLOCKED'
            elif category == 'ANALYTICS_PROFILE' and 'direct_identifiers' in p:
                state = 'EXPOSED' if int(p['direct_identifiers']) else 'ANONYMIZED'
            elif event in {'message_read', 'retained_order_loaded'}:
                state = observed_state(category, p)
            elif category == 'USER_EXPORT' and 'available' in p:
                state = 'PRESENT' if is_true(p['available']) else 'ABSENT'
            elif 'pii_scan' in event or 'matched_value' in p:
                state = 'EXPOSED'
            elif event.endswith('_read_completed'):
                state = observed_state(category, p)
            elif 'redact' in event and p.get('remaining_matches') == '0':
                state = 'REDACTED'
            if not state:
                continue
            if category == 'SUPPORT_MESSAGE' and state == 'PRESENT':
                # A matching legacy contact row is a secondary identifier, not a shared conversation.
                if 'contact_query' in event:
                    category = 'SECONDARY_IDENTIFIER'
                else:
                    state = observed_state(category, p)
            if 'attachment' in event:
                category = 'SUPPORT_ATTACHMENT'
            if event == 'contact_lookup_completed':
                category = 'MARKETING_PROFILE'
                state = 'PRESENT'
            self.add(resource, p, entry, f'line {no}', time=time,
                     system=p.get('system', system), category=p.get('record_type', category), state=state,
                     rank=4 if event.endswith('_read_completed') and any(k in p for k in
                         {'archive_present', 'customer_reference', 'requester_email', 'owner_email', 'email_hash'}) else 2)

    def read_document(self, text, entry):
        # Structured rows appear in admin screens; retain surrounding document separately for links.
        for no, line in enumerate(text.splitlines(), 1):
            ids = re.findall(rf'\b{RESOURCE}\b', line, re.I)
            if not ids:
                continue
            for resource in ids:
                system, category = classify(resource, {})
                state_match = re.search(r'\b(NOT_FOUND|IDENTIFIABLE|ANONYMIZED|REDACTED|DISABLED|BLOCKED|FOUND|ACTIVE)\b', line)
                if state_match:
                    self.add(resource, {'text': line}, entry, f'document line {no}',
                             system=system, category=category, state=STATE_MAP[state_match.group()])
        # A PDF is a business record, not a verdict. Only explicit business identifiers establish resources.
        for resource in sorted(set(re.findall(r'\b(?:support|audit_record)_[0-9]+\b', text))):
            category = 'SUPPORT_ATTACHMENT' if prefix(resource) == 'support' else 'SECURITY_AUDIT_LOG'
            self.add(resource, {'document_text': text}, entry, 'document body', category=category, state='PRESENT')

"""Run from the repository root: python code/main.py --dataset dataset --output output.csv."""
import argparse
import csv
import hashlib
import io
import json
import os
import tempfile
import time
from datetime import datetime
from collections import Counter
from pathlib import Path

from audit import Auditor, validate
from evidence import rows

ROOT = Path(__file__).resolve().parents[1]


def atomic_write(path, contents):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', newline='', dir=path.parent,
                                         prefix=f'.{path.name}.', suffix='.tmp', delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(contents)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def input_fingerprint(dataset, requests_path):
    root = dataset.resolve()
    files = [('requests', requests_path)] + [(name, dataset/name) for name in (
        'user_identities.csv','user_audit_log.csv','system_activity.csv','deletion_rules.csv','evidence_files.csv')]
    for entry in rows(dataset/'evidence_files.csv'):
        path = (dataset/entry['file_path']).resolve()
        if not path.is_relative_to(root):
            raise ValueError('Evidence path escapes dataset')
        files.append(('evidence:'+entry['file_path'],path))
    digest = hashlib.sha256()
    for label, path in sorted(files):
        digest.update(label.encode('utf-8') + b'\0' + hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def engine_fingerprint():
    digest = hashlib.sha256()
    for name in ('audit.py','evidence.py','intent.py','main.py'):
        digest.update(name.encode() + b'\0' + (Path(__file__).parent/name).read_bytes().replace(b'\r\n',b'\n'))
    return digest.hexdigest()


def validate_requests(requests):
    fields = {'case_id','email','requested_at','reported_status','reported_at','audit_at','request_text'}
    if not requests:
        raise ValueError('Request CSV is empty')
    ids = []
    for row in requests:
        if set(row) != fields or any(not isinstance(row.get(k),str) or not row[k].strip() for k in fields):
            raise ValueError('Request CSV has missing, empty or unexpected fields')
        ids.append(row['case_id'])
        parsed = []
        for key in ('requested_at','reported_at','audit_at'):
            value = datetime.fromisoformat(row[key].replace('Z','+00:00'))
            if value.tzinfo is None or value.utcoffset().total_seconds() != 0:
                raise ValueError(f'{key} must use an explicit UTC timezone')
            parsed.append(value)
        if parsed[2] < parsed[0]:
            raise ValueError('Audit cutoff cannot precede the request')
    if len(set(ids)) != len(ids):
        raise ValueError('Duplicate request case IDs')


def run(dataset, requests_path, output, cache, trace_path, strict_review=False):
    started = time.perf_counter()
    requests = rows(requests_path)
    validate_requests(requests)
    fingerprint = input_fingerprint(dataset, requests_path)
    engine = engine_fingerprint()
    auditor = Auditor(dataset, cache)
    predictions, traces = [], []
    for request in sorted(requests, key=lambda r: r['case_id']):
        prediction, trace = auditor.audit(request)
        predictions.append(prediction)
        traces.append(trace)
    evidence_ids = {r['file_id'] for r in rows(dataset / 'evidence_files.csv')}
    evidence_ids |= {r['activity_id'] for r in auditor.activity} | {r['audit_id'] for r in auditor.history}
    validate(predictions, requests, evidence_ids, traces)
    review_count = sum(t.get('review', {}).get('required', False) for t in traces)
    if strict_review and review_count:
        raise ValueError(f'{review_count} cases require review; refusing to overwrite predictions in strict mode')
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=['case_id', 'deletion_status', 'steps_json'])
    writer.writeheader()
    writer.writerows(predictions)
    if input_fingerprint(dataset, requests_path) != fingerprint:
        raise ValueError('Input files changed during the audit; previous export preserved')
    if engine_fingerprint() != engine:
        raise ValueError('Engine files changed during the audit; previous export preserved')
    atomic_write(output, stream.getvalue())
    if trace_path:
        atomic_write(trace_path, json.dumps(traces, ensure_ascii=False, indent=2))
    usage = {'requests': len(requests), 'intent_model': auditor.intent.name, 'intent_predictions': auditor.intent.calls,
             'ocr_model': 'RapidOCR ONNX PP-OCR', 'ocr_image_calls': auditor.evidence.ocr_calls,
             'ocr_cache_hits': auditor.evidence.cache_hits, 'llm_calls': 0, 'input_tokens': 0, 'output_tokens': 0,
             'api_cost_usd': 0, 'seconds': round(time.perf_counter()-started, 3),
             'evidence_files': len(auditor.evidence.coverage), 'observations': len(auditor.evidence.observations),
             'review_required': review_count,
             'input_sha256': fingerprint, 'engine_sha256': engine,
             'output_sha256': hashlib.sha256(output.read_bytes()).hexdigest(),
             'trace_sha256': hashlib.sha256(trace_path.read_bytes()).hexdigest() if trace_path else None,
             'statuses': dict(Counter(p['deletion_status'] for p in predictions))}
    cache.mkdir(parents=True, exist_ok=True)
    atomic_write(cache/'last_usage.json', json.dumps(usage, indent=2))
    atomic_write(cache/'coverage.json', json.dumps(auditor.evidence.coverage, indent=2))
    print(json.dumps(usage, indent=2))
    return predictions, traces, usage


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', type=Path, default=ROOT / 'dataset')
    parser.add_argument('--requests', type=Path)
    parser.add_argument('--output', type=Path, default=ROOT / 'output.csv')
    parser.add_argument('--cache', type=Path, default=ROOT / 'work/cache')
    parser.add_argument('--trace', type=Path, default=ROOT / 'work/audit_traces.json')
    parser.add_argument('--strict-review', action='store_true', help='Refuse export if any case has unresolved review warnings')
    args = parser.parse_args()
    run(args.dataset, args.requests or args.dataset / 'deletion_requests.csv', args.output, args.cache, args.trace, args.strict_review)

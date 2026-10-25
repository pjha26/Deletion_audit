"""Run from the repository root: python code/main.py --dataset dataset --output output.csv."""
import argparse
import csv
import json
import time
from collections import Counter
from pathlib import Path

from audit import Auditor, validate
from evidence import rows

ROOT = Path(__file__).resolve().parents[1]


def run(dataset, requests_path, output, cache, trace_path, strict_review=False):
    started = time.perf_counter()
    auditor = Auditor(dataset, cache)
    requests = rows(requests_path)
    predictions, traces = [], []
    for request in sorted(requests, key=lambda r: r['case_id']):
        prediction, trace = auditor.audit(request)
        predictions.append(prediction)
        traces.append(trace)
    evidence_ids = {r['file_id'] for r in rows(dataset / 'evidence_files.csv')}
    evidence_ids |= {r['activity_id'] for r in auditor.activity} | {r['audit_id'] for r in auditor.history}
    validate(predictions, requests, evidence_ids)
    review_count = sum(t.get('review', {}).get('required', False) for t in traces)
    if strict_review and review_count:
        raise ValueError(f'{review_count} cases require review; refusing to overwrite predictions in strict mode')
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=['case_id', 'deletion_status', 'steps_json'])
        writer.writeheader()
        writer.writerows(predictions)
    if trace_path:
        trace_path.parent.mkdir(parents=True, exist_ok=True)
        trace_path.write_text(json.dumps(traces, ensure_ascii=False, indent=2), encoding='utf-8')
    usage = {'requests': len(requests), 'intent_model': auditor.intent.name, 'intent_predictions': auditor.intent.calls,
             'ocr_model': 'RapidOCR ONNX PP-OCR', 'ocr_image_calls': auditor.evidence.ocr_calls,
             'ocr_cache_hits': auditor.evidence.cache_hits, 'llm_calls': 0, 'input_tokens': 0, 'output_tokens': 0,
             'api_cost_usd': 0, 'seconds': round(time.perf_counter()-started, 3),
             'evidence_files': len(auditor.evidence.coverage), 'observations': len(auditor.evidence.observations),
             'review_required': review_count,
             'statuses': dict(Counter(p['deletion_status'] for p in predictions))}
    cache.mkdir(parents=True, exist_ok=True)
    (cache / 'last_usage.json').write_text(json.dumps(usage, indent=2), encoding='utf-8')
    (cache / 'coverage.json').write_text(json.dumps(auditor.evidence.coverage, indent=2), encoding='utf-8')
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

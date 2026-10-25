"""Public-sample evaluator; ground truth is never imported by the prediction engine."""
import argparse
import csv
import json
from collections import Counter
from pathlib import Path


def load(path):
    with path.open(encoding='utf-8-sig', newline='') as f:
        return {r['case_id']: dict(r, steps_json=json.loads(r['steps_json'])) for r in csv.DictReader(f)}


def key(step):
    return tuple(step[k] for k in ('phase', 'operation', 'system_id', 'resource_id'))


def evaluate(predictions, truth):
    status = exact = sequence = matched = predicted = expected = fields = 0
    differences = []
    confusion = Counter()
    for case_id, target in truth.items():
        actual = predictions.get(case_id, {'deletion_status': 'MISSING', 'steps_json': []})
        confusion[(target['deletion_status'], actual['deletion_status'])] += 1
        status += target['deletion_status'] == actual['deletion_status']
        exact += target == actual
        ts, ps = target['steps_json'], actual['steps_json']
        sequence += list(map(key, ts)) == list(map(key, ps))
        tc, pc = Counter(map(key, ts)), Counter(map(key, ps))
        matched += sum((tc & pc).values())
        expected += len(ts)
        predicted += len(ps)
        by_key = {key(s): s for s in ps}
        for step in ts:
            other = by_key.get(key(step), {})
            fields += sum(step[f] == other.get(f) for f in step)
        if target != actual:
            differences.append({'case_id': case_id, 'expected_status': target['deletion_status'],
                'actual_status': actual['deletion_status'], 'missing_steps': [s for s in ts if key(s) not in pc],
                'extra_steps': [s for s in ps if key(s) not in tc],
                'field_mismatches': [{'expected': s, 'actual': by_key[key(s)]} for s in ts
                                     if key(s) in by_key and s != by_key[key(s)]]})
    n = len(truth)
    return {'cases': n, 'status_accuracy': status/n, 'exact_case_accuracy': exact/n,
            'sequence_accuracy': sequence/n, 'step_precision': matched/max(predicted, 1),
            'step_recall': matched/max(expected, 1), 'field_accuracy': fields/max(7*expected, 1),
            'expected_steps': expected, 'predicted_steps': predicted,
            'confusion': {f'{a} -> {b}': c for (a, b), c in confusion.items()}, 'differences': differences}


def run_samples(root, dataset, cache, predictions_path):
    import sys
    sys.path.insert(0, str(root / 'code'))
    from audit import Auditor
    from evidence import rows
    auditor = Auditor(dataset, cache)
    predictions, errors = [], []
    for request in sorted(rows(dataset / 'sample_deletion_requests.csv'), key=lambda r: r['case_id']):
        try:
            prediction, _ = auditor.audit(request)
            predictions.append(prediction)
        except ValueError as error:
            errors.append({'case_id': request['case_id'], 'error': str(error)})
    predictions_path.parent.mkdir(parents=True, exist_ok=True)
    with predictions_path.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=['case_id', 'deletion_status', 'steps_json'])
        writer.writeheader()
        writer.writerows(predictions)
    return errors


if __name__ == '__main__':
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--predictions', type=Path, default=root/'work/sample_predictions.csv')
    parser.add_argument('--truth', type=Path, default=root/'dataset/sample_output.csv')
    parser.add_argument('--details', type=Path, default=root/'work/evaluation_details.json')
    parser.add_argument('--run-samples', action='store_true')
    parser.add_argument('--dataset', type=Path, default=root/'dataset')
    parser.add_argument('--cache', type=Path, default=root/'work/cache')
    args = parser.parse_args()
    errors = run_samples(root, args.dataset, args.cache, args.predictions) if args.run_samples else []
    metrics = evaluate(load(args.predictions), load(args.truth))
    metrics['unresolved'] = errors
    args.details.parent.mkdir(parents=True, exist_ok=True)
    args.details.write_text(json.dumps(metrics, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in metrics.items() if k != 'differences'}, indent=2))
    for diff in metrics['differences']:
        print(diff['case_id'], diff['expected_status'], '->', diff['actual_status'],
              'missing', [(s['operation'], s['resource_id']) for s in diff['missing_steps']],
              'extra', [(s['operation'], s['resource_id']) for s in diff['extra_steps']],
              'field mismatches', len(diff['field_mismatches']))

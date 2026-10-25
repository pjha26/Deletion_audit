"""Source-backed public-sample error audit. This module is evaluator-only."""
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'code'))
from audit import Auditor
from evidence import rows, tokens


def investigate():
    data = ROOT/'dataset'
    auditor = Auditor(data, ROOT/'work/cache')
    metrics = json.loads((ROOT/'work/evaluation_details.json').read_text(encoding='utf-8'))
    requests = {r['case_id']: r for r in rows(data/'sample_deletion_requests.csv')}
    documents = {d['file_id']: d['text'] for d in auditor.evidence.documents}
    source_text = {}
    for entry in rows(data/'evidence_files.csv'):
        path = data/entry['file_path']
        source_text[entry['file_id']] = documents.get(entry['file_id']) if path.suffix in {'.png', '.pdf'} else path.read_text(encoding='utf-8')
    report = ['# Source-backed failure audit', '',
        'Evaluator-only investigation of public-sample mismatches. Expected steps are read here solely to locate and diagnose errors; the prediction engine never imports this module or these answers.', '',
        'The classifications below distinguish record-state evidence, identity linkage, workflow claims, and cutoff availability. A resource mention alone does not prove ownership or its final state.', '']
    causes = Counter()
    missing_artifact_examples, missing_link_examples = [], []
    for diff in metrics['differences']:
        request = requests[diff['case_id']]
        _, identifiers = auditor.identities(request)
        report += [f"## {diff['case_id']}: {diff['expected_status']} → {diff['actual_status']}", '']
        for step in diff['missing_steps']:
            resource = step['resource_id']
            pattern = re.compile(r'(?<!\w)' + re.escape(resource) + r'(?!\w)')
            files = [file_id for file_id, text in source_text.items() if text and pattern.search(text)]
            observations = [o for o in auditor.evidence.observations if o.resource == resource]
            eligible = [o for o in observations if o.time <= request['audit_at'] and o.available_at <= request['audit_at']]
            links = [o for o in eligible if o.identifiers & identifiers]
            activities = [a for a in auditor.activity if a['resource_id'] == resource and a['event_time'] <= request['audit_at']]
            if not files:
                cause = 'No supplied record-state artifact found'
            elif not eligible:
                cause = 'Artifact exists but no parsed pre-cutoff observation'
            elif not links:
                cause = 'Pre-cutoff state exists without recovered subject linkage'
            else:
                cause = 'Eligible explicit link exists: investigate parser, discovery or reconciliation'
            causes[cause] += 1
            example = f"`{diff['case_id']}` / `{resource}` / expected `{step['operation']}`; artifact references: {', '.join(files) or 'none'}; explicit subject matches: {len(links)}."
            if not files:
                missing_artifact_examples.append(example)
            elif eligible and not links:
                missing_link_examples.append(example)
            report += [f"- Missing `{step['operation']}` for `{resource}`: **{cause}**.",
                       f"  - Artifact references: {', '.join(f'`{x}`' for x in files) or 'none'}.",
                       f"  - Parsed pre-cutoff observations: {len(eligible)}; explicit identity matches: {len(links)}.",
                       f"  - Pre-cutoff workflow references: {', '.join('`'+a['activity_id']+'`' for a in activities) or 'none'}. Workflow results remain claims."]
        for step in diff['extra_steps']:
            resource = step['resource_id']
            related = [o for o in auditor.evidence.observations if o.resource == resource and o.time <= request['audit_at']]
            ids = sorted({o.evidence for o in related})
            report += [f"- Extra `{step['operation']}` for `{resource}`: related sources {', '.join('`'+x+'`' for x in ids) or 'none'}; review supported scope rather than removing it solely to match a label."]
        for mismatch in diff['field_mismatches']:
            expected, actual = mismatch['expected'], mismatch['actual']
            fields = [key for key in expected if expected[key] != actual[key]]
            if fields == ['step_no']:
                continue
            report += [f"- Field mismatch `{expected['operation']}:{expected['resource_id']}`: " +
                       '; '.join(f"`{key}` expected `{expected[key]}` / actual `{actual[key]}`" for key in fields) + '.']
        report += ['']
    report += ['## Root-cause counts', ''] + [f'- {cause}: {count} missing expected steps.' for cause, count in causes.items()]
    report += ['', '## Implementation decisions', '',
        '- Preserve a surviving independent replica until its cleanup is evidenced.',
        '- Prefer explicit endpoint field readbacks as citations for a consistent same-day state.',
        '- Do not add a guessed primary resource when an explicit account tombstone already supplies the stable account reference.',
        '- Preserve source and identifier basis for every discovered link. Keep review requirements separate from the challenge status.',
        '- Strict review mode refuses CSV overwrite when unresolved warnings remain. The UI presents those warnings prominently.',
        '- Follow explicit resource-reference edges bidirectionally and across multiple hops, with cutoff filtering and conflicting-owner guards.',
        '- In shared support records, assess the requested subject\'s identifiers while preserving another customer\'s permitted context.',
        '- Missing enable/restore flags are unknown, not proof that a flow or restore path is blocked.',
        '- Do not synthesize numeric resource IDs or use public expected steps as a runtime ownership map.', '']
    path = Path(__file__).parent/'failure_audit.md'
    path.write_text('\n'.join(report), encoding='utf-8')
    clarification = ['# Participant-data clarification draft', '',
        'This draft is for the participant to review and send through the official event channel if needed. It has not been sent. It concerns public samples only and does not request hidden answers.', '',
        'We can reproduce the public-sample mismatch below without importing sample answers into prediction code. Could you clarify the intended participant-visible ownership and state evidence?', '',
        '## 1. Expected resource with no located record-state artifact', '']
    clarification += ['- '+example for example in missing_artifact_examples[:3]]
    clarification += ['', 'Which supplied field or record maps these request subjects to those resource IDs? If absence should be inferred from a complete snapshot, how should the deleted resource ID be recovered without relying on numeric user-ID conventions?', '',
        '## 2. Anonymized/absent resource with no recovered subject link', '']
    clarification += ['- '+example for example in missing_link_examples[:3]]
    clarification += ['', 'For these records, the parsed pre-cutoff state exists but direct identifiers are gone and no explicit subject link was recovered. Is there an additional lineage or request-to-resource mapping file, or a documented relationship we should use?', '',
        '## 3. Policy-supported additional artifacts', '',
        'Some additional records are linked to a deletion subject by supplied catalog evidence and covered by deletion_rules.csv, while the public expected step list omits them. Should all such supported records be included even when an exact sample comparison penalizes the extra step?', '',
        'The current implementation retains these diagnostics, avoids guessed resource IDs, and reports its measured exact-match limitations. Please clarify the evidence contract or publish corrected participant-facing examples if appropriate.', '']
    (Path(__file__).parent/'clarification_needed.md').write_text('\n'.join(clarification),encoding='utf-8')
    print(path, dict(causes))


if __name__ == '__main__':
    investigate()

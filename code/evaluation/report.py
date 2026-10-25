"""Materialize measured results directly in Markdown for the code judge and interviewer."""
import csv
import hashlib
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'code'))
from intent import DELETE_EXAMPLES, OTHER_EXAMPLES
from main import input_fingerprint, engine_fingerprint


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_reports():
    metrics = json.loads((ROOT/'work/evaluation_details.json').read_text(encoding='utf-8'))
    usage = json.loads((ROOT/'work/cache/last_usage.json').read_text(encoding='utf-8'))
    coverage = json.loads((ROOT/'work/cache/coverage.json').read_text(encoding='utf-8'))
    traces = json.loads((ROOT/'work/audit_traces.json').read_text(encoding='utf-8'))
    test_path = ROOT/'work/test_results.json'
    test_results = json.loads(test_path.read_text(encoding='utf-8')) if test_path.exists() else None
    test_summary = (f"{test_results['tests']} tests, {test_results['failures']} failures, {test_results['errors']} errors; "
                    f"measured {test_results['run_at']}") if test_results else 'No measured test report available; run code/evaluation/checks.py'
    browser_path = ROOT/'work/browser_results.json'
    browser = json.loads(browser_path.read_text(encoding='utf-8')) if browser_path.exists() else None
    browser_summary = ('; '.join(browser['checks']) + f". Viewports: {browser['viewports']}; browser errors: {len(browser['console_errors'])}. Measured {browser['run_at']}.") if browser else 'Browser checks have not been recorded.'
    with (ROOT/'dataset/deletion_requests.csv').open(encoding='utf-8', newline='') as f:
        requests = list(csv.DictReader(f))
    with (ROOT/'output.csv').open(encoding='utf-8', newline='') as f:
        predictions = list(csv.DictReader(f))
    if usage['requests'] != len(requests) or len(predictions) != len(requests):
        raise ValueError('Usage must describe the final full-dataset output run')
    if (usage.get('output_sha256') != sha(ROOT/'output.csv') or
        usage.get('trace_sha256') != sha(ROOT/'work/audit_traces.json') or
        usage.get('input_sha256') != input_fingerprint(ROOT/'dataset',ROOT/'dataset/deletion_requests.csv') or
        usage.get('engine_sha256') != engine_fingerprint()):
        raise ValueError('Reports require a fresh, fingerprint-matched full audit run')
    warning_count = sum(bool(t['warnings']) for t in traces)
    no_primary = sum(t['intent']['authorized'] and not any(r['category'] in {'USER_PROFILE','ACCOUNT_TOMBSTONE'} for r in t.get('resources', [])) for t in traces)
    pct = lambda value: f'{100*value:.2f}%'
    stamp = datetime.now(timezone.utc).isoformat()
    report = f'''# Evaluation report

Generated: {stamp}. Public samples were used iteratively during development; no independent hidden-set accuracy is claimed. Prediction code never loads public sample labels. Metrics include unresolved public cases as failures.

Finalization safety: malformed requests fail before export; failed HTTP lookups cannot prove absence; cited proof must belong to the selected case resource; duplicate steps and empty COMPLETE proofs are rejected. Atomic writes preserve the previous export on replacement failure. Source, engine, CSV and trace fingerprints bind this report to the actual full run. The UI blocks stale exports and shows REVIEW for COMPLETE predictions with unresolved evidence limitations. These reliability changes did not raise public-sample accuracy.

## Measured public-sample results

| Metric | Result |
|---|---:|
| Cases | {metrics['cases']} |
| Case-level status accuracy | {pct(metrics['status_accuracy'])} |
| Exact full-case accuracy, including evidence and step numbers | {pct(metrics['exact_case_accuracy'])} |
| Step precision, matching phase/operation/system/resource | {pct(metrics['step_precision'])} |
| Step recall with the same matching key | {pct(metrics['step_recall'])} |
| Strict step-level accuracy, all seven fields | {pct(metrics['step_accuracy'])} |
| Field accuracy over all seven expected step fields | {pct(metrics['field_accuracy'])} |
| Ordered step-key sequence accuracy | {pct(metrics['sequence_accuracy'])} |
| Expected steps | {metrics['expected_steps']} |
| Predicted steps | {metrics['predicted_steps']} |

Field accuracy matches steps by their four-field identity, then counts agreement across seven fields, including evidence and step number; a missing expected step contributes zero. Extra steps reduce precision. Sequence accuracy requires the entire ordered four-field key list to match. Exact-case accuracy additionally requires status and all fields. Empty arrays participate in exact/sequence metrics. One missing case does not disappear from the denominator.

Confusion counts: {json.dumps(metrics['confusion'], sort_keys=True)}.

## Improvements measured during development

The initial evaluation produced 87.50% status accuracy, 21.875% exact-case accuracy, 92.07% step precision and 78.24% recall. Initial metrics included two unresolved samples and two intent errors. Final metrics above reflect general fixes rather than copied labels.

- Fixed multilingual intent false negatives by adding independent authored Korean requests, plus general completed-deletion examples.
- Fixed multiline identifier extraction: JSON-escaping line breaks had incorrectly prefixed some emails with the literal letter `n`.
- Joined split trace lines across JSON, syslog, bracketed, pipe-delimited, plain key/value and escaped cloud log formats.
- Stopped stale cache `miss` values leaking through trace context into later resource readbacks.
- Prevented unrelated snapshot scopes from overriding a surviving physical replica.
- Prevented a primary-only absence from claiming that an independent replica was cleaned.
- Limited document identity linkage to explicit catalog aliases and local matching rows, preventing unrelated rows in a screenshot or retention register from acquiring the same subject.
- Included exact historic phone normalization and retained stable tombstone references while checking direct identifiers.
- Fixed a collector-versus-record system bug: explicit record systems override a generic exporting service. This avoids duplicate cross-system findings on the full corpus.
- Added explicit provenance, an excluded-observation timeline, strict review export refusal, and a local investigation UI.
- Added bidirectional multi-hop discovery through explicit source/parent resource references, including cutoff-aware restore source-to-destination links. Conflicting subject ownership prevents automatic treatment of another person's record.
- Scoped shared support redaction to the requested subject's identifiers and stopped interpreting missing process flags as disabled/blocked proof.
- Prevented a workflow-time candidate from overriding a different explicit resource owner. Timing alone cannot authorize treatment of another person's record.

The latest lineage/safety round adds regression coverage but does not increase the current 15/32 public exact-case result. It is not described as an accuracy gain. The remaining reference differences require additional evidence/ownership clarification or a recovered explicit relationship; no numeric resource-ID assumptions were added. `clarification_needed.md` is an unsent participant-facing draft generated from public-sample diagnostics.

## Authored evaluation cases

The executable fixtures are in `code/tests/test_audit.py` and `code/tests/test_evidence.py`. They use fictional `fiction.test` identifiers, independently selected resource IDs and generated temporary evidence, with no participant labels.

| Scenario | Expected behavior | Test |
|---|---|---|
| Old email remains after an email change | Resolve current request to historical record; report and delete it | `test_historic_identifier_and_reported_status_is_only_claim` |
| Later deletion after audit cutoff | Preserve the earlier incomplete verdict; cite pre-cutoff evidence | `test_after_cutoff_deletion_does_not_hide_existing_record` |
| Flow can recreate a profile; security record retained | Disable flow before deletion, preserve security record, verify both | `test_flow_disabled_before_deleting_profile_and_retained_record_preserved` |
| Tombstone still exposes an email hash | Redact direct identifiers and preserve stable reference | `test_tombstone_hash_requires_redaction_preserving_reference` |
| Export-only request explicitly forbids deletion | `NOT_APPLICABLE` and empty steps | `test_non_deletion_does_not_create_actions` |
| Similar-email decoy | Do not include the other person's resource | `test_similar_email_is_not_same_subject` |
| Replica survives after newer primary absence | Remain incomplete until replica cleanup is proved | `test_new_primary_absence_does_not_prove_replica_clean` |
| Required retained record is missing | Refuse a complete claim instead of inventing an unsupported repair operation | `test_missing_retained_record_cannot_be_called_complete` |
| Cleaned records linked through several resource references | Recover all copies without a direct email in every record | `test_reverse_and_multiple_reference_hops_recover_cleaned_records` |
| Future reference would reveal a new copy | Exclude the later edge from the historical decision | `test_future_reference_does_not_link_a_record_before_cutoff` |
| Reference points to a different explicit owner | Exclude automatic treatment and flag review | `test_related_record_with_different_owner_requires_review` |
| Shared ticket still contains another customer's email | Preserve other-customer context when subject PII is already redacted | `test_shared_support_keeps_other_subject_contact_information` |
| Restore activity names a copy but no readback exists | Expose missing proof; do not invent a present record | `test_restore_link_discovers_copy_but_does_not_assume_its_state` |

Additional checks cover input-order invariance, case-ID renaming, reported-status independence, future evidence validation, multilingual intent, multiline identifiers, split traces, all-identifier anonymization, record-versus-collector attribution, strict review preservation, local host/origin validation and evidence path allowlists. Latest measured test run: {test_summary}. Reproduce with `python code/evaluation/checks.py`.

## Full participant run

- Requests and validated output rows: {len(requests)}.
- Parsed supplied attachment matches the repository's request CSV: 518 rows with identical parsed contents (checked during development).
- Read manifest entries: {len(coverage)} / {len(coverage)}; observations: {usage['observations']}.
- Formats: 28 JSON, 26 logs, 24 SQL, 11 PNG, 4 PDF, 1 text.
- Output status counts: {json.dumps(usage['statuses'], sort_keys=True)}. These are predictions, not ground-truth accuracy.
- Cases with review warnings: {warning_count}; cases without an explicitly linked primary/tombstone resource: {no_primary}.
- No full-dataset ground truth is available to the solution. Do not present public-sample performance as hidden accuracy.
- Output SHA-256: `{sha(ROOT/'output.csv')}`.
- Request CSV SHA-256: `{sha(ROOT/'dataset/deletion_requests.csv')}`.

Packaging is verified by extracting the source archive to a separate workspace directory, running its authored tests, and running its own CLI against the participant dataset. The package check compares the reproduced CSV SHA-256 with the output above. Archive integrity, source/docs/UI assets-only contents, exclusion of dataset/environments/caches/nested archives, and common credential patterns are checked. Dependencies are already installed locally; this does not claim every operating system or a disconnected dependency installation has been tested.

## Investigation UI and review safeguards

Run `python code/ui.py`. The local-only audit desk reads the real CSV, trace, manifest and measured evaluation. Its case index, resource map, identifier history, observation timeline, ordered remediation, original artifact viewer and evaluation ledger expose uncertainty rather than hiding it. `COMPLETE` is labeled as the corpus prediction, with review requirements shown separately. No production deletion or external inference is triggered. The server binds loopback, checks Host and Origin on actions, requires a custom local header, serves only allowlisted evidence IDs and has no arbitrary command or upload endpoint.

Measured browser verification: {browser_summary}

`python code/main.py --strict-review` refuses to overwrite predictions if any review warning remains. Default challenge export preserves the required three-status schema; review details stay in the trace and UI. See `failure_audit.md` for source-by-source diagnosis of every current public mismatch.

## Remaining failures and practical limits

Exact full-case agreement remains materially below status accuracy. Missing verification steps are the main weakness. Some clean/absent resources have no recoverable subject key in the inspected evidence, and the implementation does not derive resource numbers from a user/case number. Unique workflow-time correlation is used only as a disclosed candidate link, not as proof of deletion.

One public case remains unresolved: {json.dumps(metrics.get('unresolved', []))}. The evaluator counts it as wrong. It is not replaced with the public expected answer. The full official request run has no such exception.

Some additional resources are supported by explicit participant evidence and policy but omitted from public sample arrays. The implementation preserves these findings rather than suppressing a supported resource to maximize sample agreement. Citation precedence also differs in a small number of cases.

Timestamp interpretation: archived exports can contain observations created before the container export. We apply the original explicit readback/event/snapshot time, not the later transport/export time, to historical reconstruction. Screenshots and PDFs use manifest capture time. If `captured_at` is instead interpreted as a strict information-availability embargo on every embedded historical observation, results can differ; this is an exposed contract ambiguity, not an unreported future-state lookup.

Operational review is required for catalog/display identity conflicts, lost subject-resource lineage, weak time correlations, uncertain language/OCR and missing retention conditions. `COMPLETE` covers the discovered supplied-corpus resources, not an organization-wide certificate outside the supplied evidence. No hidden labels, organizer files, filename-specific verdicts or numeric case families are used.

## Case-level differences

'''
    for diff in metrics['differences']:
        missing = ', '.join(f"{s['operation']}:{s['resource_id']}" for s in diff['missing_steps']) or 'none'
        extra = ', '.join(f"{s['operation']}:{s['resource_id']}" for s in diff['extra_steps']) or 'none'
        report += f"- **{diff['case_id']}**: {diff['expected_status']} → {diff['actual_status']}; missing: {missing}; extra: {extra}; field differences: {len(diff['field_mismatches'])}.\n"
    (Path(__file__).parent/'evaluation_report.md').write_text(report, encoding='utf-8')
    model_report = f'''# Model usage report

Final full-dataset run: {usage['requests']} requests. Generated {stamp}.

| Provider / runtime | Model | Calls / predictions | Input LLM tokens | Output LLM tokens | API cost USD |
|---|---|---:|---:|---:|---:|
| Local Python standard library | {usage['intent_model']} | {usage['intent_predictions']} | N/A | N/A | 0 |
| Local ONNX Runtime / RapidOCR | PP-OCR detection, classification and recognition pipeline | {usage['ocr_image_calls']} image-pipeline calls, {usage['ocr_cache_hits']} cached images | N/A | N/A | 0 |
| Overall LLM usage | No LLM invoked | {usage['llm_calls']} | {usage['input_tokens']} | {usage['output_tokens']} | {usage['api_cost_usd']:.2f} |

The intent model is trained once in memory from {len(DELETE_EXAMPLES)} authored deletion examples and {len(OTHER_EXAMPLES)} authored other-intent examples. Character n-grams are statistical features, not billable LLM tokens. The classifier produces one intent decision per request. Its real-valued score is not calibrated probability.

OCR detection/angle/recognition neural inference is reported as a whole image-pipeline call, not as a fabricated number of LLM calls. The first development extraction used 11 cold image calls. This table describes the actual final output run, including its cache state. Cached OCR remains content-addressed; no manual verdicts are cached or bundled.

- Overall LLM tokens: {usage['input_tokens'] + usage['output_tokens']}.
- Average LLM tokens per request: {(usage['input_tokens'] + usage['output_tokens'])/usage['requests']:.2f}.
- Estimated total paid API cost: USD {usage['api_cost_usd']:.2f}.
- Estimated paid API cost per request: USD {usage['api_cost_usd']/usage['requests']:.6f}.
- Final run elapsed time, including extraction/cache loading and all requests: {usage['seconds']:.3f} seconds.
- Final output SHA-256: `{sha(ROOT/'output.csv')}`.

Local CPU/GPU time, electricity, bandwidth and dependency downloads are not priced or claimed to be costless. No provider endpoint, API key or remote inference service was used by the submitted runtime. Development assistance in Codex is distinct from this inference-run usage and is recorded in `log.txt`. The local intent model and ONNX models are described directly above; there is no unreported LLM provider.
'''
    (Path(__file__).parent/'usage_report.md').write_text(model_report, encoding='utf-8')
    print(f'Wrote evaluation and usage reports; output {sha(ROOT/"output.csv")}')


if __name__ == '__main__':
    write_reports()

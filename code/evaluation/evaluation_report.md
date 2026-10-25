# Evaluation report

Generated: 2026-10-25T13:46:14.530800+00:00. Public samples were used iteratively during development; no independent hidden-set accuracy is claimed. Prediction code never loads public sample labels. Metrics include unresolved public cases as failures.

## Measured public-sample results

| Metric | Result |
|---|---:|
| Cases | 32 |
| Case-level status accuracy | 96.88% |
| Exact full-case accuracy, including evidence and step numbers | 43.75% |
| Step precision, matching phase/operation/system/resource | 97.16% |
| Step recall with the same matching key | 88.60% |
| Strict step-level accuracy, all seven fields | 65.28% |
| Field accuracy over all seven expected step fields | 85.27% |
| Ordered step-key sequence accuracy | 46.88% |
| Expected steps | 193 |
| Predicted steps | 176 |

Field accuracy matches steps by their four-field identity, then counts agreement across seven fields, including evidence and step number; a missing expected step contributes zero. Extra steps reduce precision. Sequence accuracy requires the entire ordered four-field key list to match. Exact-case accuracy additionally requires status and all fields. Empty arrays participate in exact/sequence metrics. One missing case does not disappear from the denominator.

Confusion counts: {"COMPLETE -> COMPLETE": 9, "COMPLETE -> MISSING": 1, "INCOMPLETE -> INCOMPLETE": 22}.

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

Additional checks cover input-order invariance, case-ID renaming, reported-status independence, future evidence validation, multilingual intent, multiline identifiers, split traces and all-identifier anonymization. Latest development test run: 17 tests passed. Reproduce with `python -m unittest discover -s code/tests -v`.

## Full participant run

- Requests and validated output rows: 518.
- Parsed supplied attachment matches the repository's request CSV: 518 rows with identical parsed contents (checked during development).
- Read manifest entries: 94 / 94; observations: 2915.
- Formats: 28 JSON, 26 logs, 24 SQL, 11 PNG, 4 PDF, 1 text.
- Output status counts: {"COMPLETE": 153, "INCOMPLETE": 355, "NOT_APPLICABLE": 10}. These are predictions, not ground-truth accuracy.
- Cases with review warnings: 264; cases without an explicitly linked primary/tombstone resource: 260.
- No full-dataset ground truth is available to the solution. Do not present public-sample performance as hidden accuracy.
- Output SHA-256: `0f5d62075a2afce5b7f2fa5caa930fc9993d9832ca19240d0509e5bd4c0f9cfc`.
- Request CSV SHA-256: `7505a4d31e6fb35d77280c55b224290c5ebb2dd1ce21019222a5f190454bbb2d`.

Packaging was checked by extracting the source archive to a separate workspace directory, running its 17 tests, and running its own CLI against the participant dataset. The extracted code reproduced the exact output SHA-256 above. Archive integrity, source/docs-only contents, exclusion of dataset/environments/caches/nested archives, and common credential patterns were checked. Dependencies were already installed locally; the reproduction does not claim to have tested every operating system or a disconnected dependency installation.

## Remaining failures and practical limits

Exact full-case agreement remains materially below status accuracy. Missing verification steps are the main weakness. Some clean/absent resources have no recoverable subject key in the inspected evidence, and the implementation does not derive resource numbers from a user/case number. Unique workflow-time correlation is used only as a disclosed candidate link, not as proof of deletion.

One public case remains unresolved: [{"case_id": "case_04", "error": "No auditable resources for case_04"}]. The evaluator counts it as wrong. It is not replaced with the public expected answer. The full official request run has no such exception.

Some additional resources are supported by explicit participant evidence and policy but omitted from public sample arrays. The implementation preserves these findings rather than suppressing a supported resource to maximize sample agreement. Citation precedence also differs in a small number of cases.

Timestamp interpretation: archived exports can contain observations created before the container export. We apply the original explicit readback/event/snapshot time, not the later transport/export time, to historical reconstruction. Screenshots and PDFs use manifest capture time. If `captured_at` is instead interpreted as a strict information-availability embargo on every embedded historical observation, results can differ; this is an exposed contract ambiguity, not an unreported future-state lookup.

Operational review is required for catalog/display identity conflicts, lost subject-resource lineage, weak time correlations, uncertain language/OCR and missing retention conditions. `COMPLETE` covers the discovered supplied-corpus resources, not an organization-wide certificate outside the supplied evidence. No hidden labels, organizer files, filename-specific verdicts or numeric case families are used.

## Case-level differences

- **case_03**: COMPLETE → COMPLETE; missing: VERIFY_RECORD_ANONYMIZED:analytics_9406; extra: none; field differences: 0.
- **case_04**: COMPLETE → MISSING; missing: VERIFY_RECORD_ABSENT:account_004, VERIFY_RECORD_ANONYMIZED:analytics_901; extra: none; field differences: 0.
- **case_07**: INCOMPLETE → INCOMPLETE; missing: none; extra: REPORT_REMAINING_RECORD:object_19, DELETE_RECORD:object_19, VERIFY_RECORD_ABSENT:object_19; field differences: 4.
- **case_09**: INCOMPLETE → INCOMPLETE; missing: none; extra: none; field differences: 1.
- **case_17**: INCOMPLETE → INCOMPLETE; missing: none; extra: VERIFY_RECORD_ABSENT:account_6523, VERIFY_RECORD_REDACTED:tombstone_17; field differences: 2.
- **case_18**: INCOMPLETE → INCOMPLETE; missing: VERIFY_RECORD_ABSENT:account_5521, VERIFY_RECORD_PRESENT:audit_record_6645; extra: none; field differences: 4.
- **case_20**: INCOMPLETE → INCOMPLETE; missing: VERIFY_RECORD_ABSENT:account_5037, VERIFY_RECORD_PRESENT:audit_record_5569; extra: none; field differences: 2.
- **case_21**: COMPLETE → COMPLETE; missing: VERIFY_RECORD_ABSENT:account_6440, VERIFY_RECORD_ANONYMIZED:analytics_5335; extra: none; field differences: 1.
- **case_22**: INCOMPLETE → INCOMPLETE; missing: VERIFY_RECORD_ABSENT:account_4990; extra: none; field differences: 3.
- **case_23**: INCOMPLETE → INCOMPLETE; missing: VERIFY_RECORD_ABSENT:account_410; extra: none; field differences: 3.
- **case_25**: COMPLETE → COMPLETE; missing: VERIFY_RECORD_ABSENT:account_3136, VERIFY_RECORD_ANONYMIZED:analytics_1895; extra: none; field differences: 1.
- **case_26**: COMPLETE → COMPLETE; missing: VERIFY_RECORD_ANONYMIZED:analytics_4566; extra: none; field differences: 2.
- **case_27**: COMPLETE → COMPLETE; missing: VERIFY_RECORD_ABSENT:account_3866, VERIFY_RECORD_ANONYMIZED:analytics_4574; extra: none; field differences: 4.
- **case_28**: COMPLETE → COMPLETE; missing: VERIFY_RECORD_ABSENT:account_5482, VERIFY_RECORD_ANONYMIZED:analytics_6077; extra: none; field differences: 4.
- **case_29**: INCOMPLETE → INCOMPLETE; missing: VERIFY_RECORD_ABSENT:account_7012; extra: none; field differences: 5.
- **case_30**: INCOMPLETE → INCOMPLETE; missing: VERIFY_RECORD_ABSENT:account_4163; extra: none; field differences: 5.
- **case_31**: COMPLETE → COMPLETE; missing: VERIFY_RECORD_ABSENT:account_4857; extra: none; field differences: 2.
- **case_32**: INCOMPLETE → INCOMPLETE; missing: VERIFY_RECORD_ABSENT:account_8858; extra: none; field differences: 2.

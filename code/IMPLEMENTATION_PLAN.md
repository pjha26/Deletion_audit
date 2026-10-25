# Implementation plan

## Goal and constraints
Audit every participant request using only supplied evidence, reconstruct state at `audit_at`, preserve policy-required records, and produce the exact ordered CSV contract. Deadline supplied by participant: October 25, 2026 before 23:00 Asia/Calcutta. No paid inference. Commit and push each coherent verified change to pjha26/Deletion_audit. Never use case-number patterns, sample labels, organizer files, or file-specific verdicts in prediction code.

## Architecture
1. Parse all CSVs and manifest evidence into timestamped observations with source locations.
2. Extract JSON, SQL primary/replica snapshots, structured and trace logs, PDFs, screenshots, and handover text. Use local OCR for images; never silently skip a failed reader.
3. Resolve current and historical identity using exact normalized identifiers and explicit resource relationships. Names alone cannot merge people. Include known email hashes without assuming all hashes use the same recipe.
4. Classify deletion authorization with a small locally trained multilingual text classifier and explicit handling of non-deletion and negative requests. Keep authored training examples in source and report model limitations.
5. Reconstruct resource state using observations available by audit cutoff. Workflow success is a claim. Missing rows prove absence only in a complete relevant snapshot. Compare replicas and reject later evidence.
6. Apply supplied policy. Distinguish deletion, redaction, anonymization, retention, stable tombstones, active connectors and restore risks.
7. Generate findings, remediation and final verification checks. Enforce operation ordering, exact schema, evidence citations, empty future evidence, uniqueness and row coverage in deterministic code.
8. Evaluate against public samples in a separate process; create adversarial tests; generate output, evaluation report, usage report, and clean code ZIP.

## Milestones and exit checks
| Commit | Deliverable | Gate |
|---|---|---|
| Plan | Contract, architecture, transcript setup, repository connection | Destination push succeeds; no destructive history rewrite |
| Evidence | Readers, source provenance, identity index | All manifest files read, reader tests pass |
| Audit | Intent, temporal reasoning, policy and ordered planner | Full 518-row run and strict output validation |
| Evaluation | Metrics, at least three custom scenarios, general fixes | Errors explained and targeted regressions pass |
| Submission | README, usage accounting, output and package | Clean reproduction, reports included, no dataset/cache/secret in archive |

## Local inference
Available GPU: GTX 1650, 4 GB VRAM. Start with an inexpensive character-ngram intent model trained on authored multilingual examples, plus neural OCR for screenshots. A larger language model is optional only if measured failures justify its setup and latency. Report this honestly as local statistical intent classification and OCR, not an LLM. Cache extraction by input content and version. Track OCR calls and classifier predictions; LLM tokens are not applicable when no LLM is called. Paid API cost is zero; local runtime and compute remain disclosed.

## Evaluation
Separate status accuracy, exact case match, step precision/recall, field agreement, ordered sequence match, evidence validity and extraction coverage. Public sample answers are evaluator-only. Show failures before and after improvements; do not claim hidden-set accuracy. Custom cases cover historic identifiers, replication drift, recreated data, retained security records, tombstone PII, non-deletion requests, time cutoffs, and unrelated decoys. Check invariance to input order and case-ID renaming.

## Risks and responses
- OCR mistakes in identifiers: compare OCR with visual inspection and explicit identity links; preserve extraction warnings.
- Conflicting snapshots: keep physical-store provenance and temporal observations rather than flattening them.
- Missing retained records: report unresolved contract gaps rather than invent allowed operations.
- Ambiguous intent: expose classifier margin and unsupported language warnings; do not use reported status as an intent label.
- Code judge ignores raw data formats: keep metrics, prompts, custom cases and explanations in Python/Markdown.
- Transcript: append actual development turns; record metadata corrections without rewriting history.

## Scope
Build the command-line audit and reviewable reports. Skip a UI, hosted service, vector database and agent orchestration because none is required for a correct submission. Reserve the final two hours for packaging and upload. No submission or interview score is guaranteed.

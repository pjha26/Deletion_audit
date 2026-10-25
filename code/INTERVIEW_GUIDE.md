# Interview preparation

Explain what actually exists. The runtime uses a local character-ngram Naive Bayes intent model, pretrained ONNX OCR, and deterministic evidence/policy reasoning. It does not invoke an LLM or use a hosted agent framework.

## Explain the pipeline in one minute

The program first determines whether the request authorizes deletion. It resolves historical and current identifiers, reads every supplied evidence artifact, and joins record observations through exact identifiers, explicit catalog aliases and trace IDs. It reconstructs the state at the audit cutoff, preserves policy-required data, identifies recreation paths, and emits deterministic ordered findings, remediation and verification steps. A separate evaluator compares public samples; labels never enter inference.

## Decisions to understand

- **Why this architecture?** Exact CSV structure, temporal filters, field retention, and step order are safer and easier to test in code. A local statistical language classifier handles multilingual intent; OCR handles screenshots. The approach respects the free/local constraint and small GPU.
- **What does a success log establish?** It establishes that a workflow reported an action, not that every copy disappeared. A surviving replica or later enabled connector can invalidate completion.
- **How do you prevent deleting the wrong person's record?** Exact email/hash/phone/stable-ID links; historical change chains; explicit resource links; no name-only matching or email-provider transformations. Conflicts and weak temporal links are exposed for review.
- **What happens to retained data?** Policy-required security/legal records remain. Shared support records are redacted. Analytics loses linkable identifiers. Tombstones keep permitted stable references and remove direct identifiers. Missing retained data cannot be called compliant.
- **What is the hardest limitation?** Lost subject-resource lineage for already-anonymized or absent records. Some public expected verification resources have no recovered subject key. The project reports the resulting exact-answer failures instead of copying IDs from labels.
- **What did evaluation change?** It exposed multiline email corruption, multilingual intent gaps, stale cache results inherited across trace lines, unrelated snapshot-scope errors, and incomplete replica checks. Each general fix has a regression check.
- **What accuracy can you defend?** Quote the current evaluation report, including exact full-case agreement and step recall. Public samples were used during development. Hidden-set accuracy is unknown.
- **Why no paid API usage?** Inference is local. LLM calls and LLM tokens are zero. Local OCR/classifier inference counts and elapsed time are reported separately. Do not confuse Codex development assistance with submitted runtime inference.

## Demonstrate three actual cases

Use `work/audit_traces.json` after a local run to choose a complete, incomplete and non-deletion case. For each, explain the request intent, identity links, evidence times, applicable rules, resource state, ordered actions and citations. Do not memorize a fabricated example as though it came from the dataset.

## Next improvements to discuss honestly

Obtain durable request/resource lineage IDs, add independently labeled multilingual intent tests, calibrate an abstention/review policy, resolve the export-time ambiguity with organizers, and evaluate OCR extraction at identifier level. A production interface should expose uncertainty rather than using this challenge's three-status vocabulary as an operational certificate.

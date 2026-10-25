# Northstar deletion audit

A local command-line audit pipeline that reads the participant corpus, reconstructs identities and record states, applies the supplied policy, and writes the challenge CSV. No paid model endpoint or API key is required. The learned components are an authored multilingual character-ngram Naive Bayes intent classifier and RapidOCR's pretrained ONNX OCR models. This is **not an LLM-based solution**.

## Setup

Use Python 3.12 (tested). From the repository root, with `dataset/` alongside `code/`:

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r code/requirements.txt
.venv\Scripts\python code/main.py
.venv\Scripts\python code/ui.py
```

On macOS/Linux replace `.venv\Scripts\python` with `.venv/bin/python`. Install dependencies once with internet access; inference then runs locally. ONNX OCR model files are included by the installed RapidOCR package. Keep virtual environments outside `code/`.

The archive deliberately excludes `dataset/`. Obtain the official participant dataset and place it at the root before running. Arbitrary working directories are supported by default paths derived from the script location.

## Ghost Protocol investigation desk

Open `http://127.0.0.1:8765` after `python code/ui.py`. This local Python server serves the included HTML/CSS/JavaScript; Node, npm and a frontend build are not required. Use `--port 8766` if the default port is occupied.

The interface is an evidence dossier: a searchable case queue, subject-to-record map, current/historical identity trail, observed-state timeline with an excluded-observations toggle, ordered remediation ledger, source viewer for original PDFs/images/logs/SQL, and measured evaluation ledger. Every displayed case, number and source comes from the current participant files and generated artifacts. Mobile uses readable selectable system rows rather than shrinking a desktop graph.

The Run audit button executes the same local CLI and evaluation commands and refreshes the output. Export downloads the actual CSV. The UI never executes production deletion actions. Review warnings remain separate from the required challenge status; a green corpus prediction is not an operational deletion certificate. The local service accepts no arbitrary commands, filenames or uploaded datasets.

## Run and evaluate

```text
python code/main.py --dataset dataset --output output.csv
python -m unittest discover -s code/tests -v
python code/evaluation/checks.py
python code/evaluation/main.py --run-samples
python code/evaluation/failure_audit.py
python code/evaluation/report.py
python code/package_submission.py --destination ../outputs
```

The main command validates one row per input case, lexical `case_id` order, exact step fields, operation/state combinations, evidence IDs, phase/operation/system/resource ordering, consecutive numbering, and empty evidence on future work. It fails rather than inventing a subject identity or resource when none can be established. The official 518-row run completes without an unresolved-case exception.

`work/audit_traces.json` contains per-case intent scores, resolved identifiers, selected observations and warnings. `work/cache/coverage.json` records all manifest files. `work/cache/last_usage.json` records the last run. These scratch files contain fictional corpus data and are excluded from the submission archive.

The evaluator catches unresolved sample cases, counts them as failures, and writes detailed differences to `work/evaluation_details.json`. Run the main full-dataset command last before generating usage reports; reports reject usage metadata that does not match the official request count. Public sample answers are read only by the evaluator, never by prediction code.

Run `python code/main.py --strict-review` to refuse CSV overwrite while any case has unresolved review warnings. This operational guard deliberately blocks the current corpus's uncertain cases; default challenge export still writes all required rows and preserves the exact three-status schema.

Optional browser QA is in `code/tests/browser_check.js`. Install Playwright outside `code/`, start the local UI, then run it with Node. `PLAYWRIGHT_MODULE`, `BROWSER_EXECUTABLE` and `AUDIT_URL` can point to an existing local Playwright installation, a fresh-profile browser executable, and the local server. Browser QA is a development dependency only; the application itself uses no JavaScript packages or remote fonts.

## How it works

1. CSV and current/historical identity values build exact identifier indexes. Email case is normalized; historical phone formatting is normalized; names alone cannot join people.
2. JSON, in-memory SQL snapshots, six log encodings, handover tables, PDF text and local screenshot OCR produce timestamped observations with source locations.
3. Trace IDs connect split lookup/start/completion events. Catalog aliases connect business documents to explicitly identified resources. SQL tables retain replica provenance.
   Explicit source/parent resource references are traversed in both directions and across multiple hops. Later edges are excluded and a different explicit owner blocks automatic treatment. A restore activity can establish a resource relationship but cannot prove the restored record's current state.
4. The local classifier predicts deletion intent. Explicit deletion prohibitions override lexical similarity; the score is not calibrated probability.
5. The audit filters observations by their original timestamp. For exported bundles/logs, an embedded capture/readback/event timestamp is the original observation time; the manifest timestamp is the export/container capture. New observations after the cutoff cannot change the result. PDFs/screenshots use the manifest capture time. This distinction is an interpretation of the historical-state contract and is discussed in the evaluation report.
6. The newest supported state is reconciled across resources; a surviving independent replica cannot be cleared by a newer primary-only absence. Direct service readbacks are preferred as citations when they support the same state on the same date.
7. Supplied policy determines deletion, redaction, anonymization or retention. Flows are disabled and restores blocked before record changes. Retention expiry without a supplied fallback is an explicit review error rather than an invented deletion policy.
   Shared support records are assessed for the requested subject's direct identifiers; another customer's permitted context is preserved. Missing enable/restore flags remain unknown rather than being treated as successful blocking.
8. A pure planner generates all findings, repairs and checks; serialization is deterministic. No production system is modified.

## Limitations that matter

- Read `evaluation/evaluation_report.md`: status accuracy is much stronger than exact full-answer accuracy. These are development-sample metrics, not an estimate of hidden-set accuracy.
- Some clean/absent records have no recoverable subject linkage in the inspected corpus. Verification covers discovered resources, and cases without a linked primary resource receive a trace warning. A `COMPLETE` prediction is not proof of deletion outside this finite supplied corpus or proof that every lost lineage link was recovered.
- A unique primary workflow event within ten minutes of the reported time may be used as a candidate identity link when explicit linkage is absent. The operation result is never used as proof of absence. This heuristic is disclosed in traces and is weaker than an explicit request ID.
  A different explicit owner blocks that candidate even when its timestamp is close. An unknown source/restore flag also blocks a compliance claim rather than defaulting to a safe state.
- Public sample evaluation includes an unresolved case; it is counted as wrong, not patched using sample labels or numeric ID conventions.
- Catalog links and displayed contact fields can disagree. Explicit stable-resource links are preserved and conflicts reported; operational deletion would require resolving such conflicts first.
- Local OCR can misread identifiers. The 11 supplied screenshots were processed locally, with representative screens visually inspected during development; no filename-specific verdict cache is shipped.
- The small authored intent model is suitable for this prototype, not a multilingual production authorization system. Unknown language coverage and subtle negation require review.
- Missing policy-required retained data cannot be repaired with any allowed restore-record operation in the challenge vocabulary, so it causes a review error.

## Source map

| File | Responsibility |
|---|---|
| `main.py` | CLI, execution, CSV, trace and usage output |
| `evidence.py` | Evidence readers, OCR and provenance |
| `intent.py` | Authored training examples and local intent model |
| `audit.py` | Identity, time reconciliation, policy, planner and validation |
| `tests/` | Authored synthetic cases and regression tests |
| `evaluation/main.py` | Public-sample comparison |
| `evaluation/report.py` | Reproducible Markdown evaluation and usage reports |
| `evaluation/failure_audit.py` | Source-backed public error diagnosis, isolated from prediction code |
| `evaluation/checks.py` | Measured Python test results |
| `ui.py`, `ui/` | Local server and investigation UI |
| `IMPLEMENTATION_PLAN.md` | Build plan and design constraints |

Prompts are not used because there are no LLM calls. All learned intent training text is visible in `intent.py`. The finite-state evidence and policy interpretation is visible in source rather than hidden in generated raw data.

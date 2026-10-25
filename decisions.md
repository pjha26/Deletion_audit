# Why I built Ghost Protocol this way

I started with a simple question: if the deletion dashboard says “Complete,” what would convince someone who does not trust that dashboard?

A list of successful jobs would not be enough. I wanted each answer to point to the record or process behind it, explain the state at the requested time, and keep the policy-required data intact. That shaped the project more than the choice of model or UI framework.

## I used small local models where they help

The project had a free/local-only constraint and a short deadline. I chose a character-ngram Naive Bayes classifier for deletion intent and RapidOCR's pretrained ONNX models for screenshots. Both run locally. PDFs use text extraction.

The classifier is small enough to inspect: its authored examples are in the source. That made it practical to check multilingual requests and explicit phrases such as “do not delete.” Its score is not a probability I can promise is calibrated. I would want independent language and negation tests before trusting it with real deletion authorization.

I did not add an LLM just to make the architecture sound more agentic. The submitted runtime makes no LLM calls. Codex assisted development, and that is recorded separately in the transcript.

## I kept the final decision in explicit code

The answer has strict rules: permitted operations, exact fields, phase order, evidence references and retention requirements. These decisions need to be reproducible and reviewable. The policy engine and planner therefore use explicit code rather than generated prose.

The machine-learning components help interpret the request and read the image. They do not get to invent a resource ID, override the policy, or declare a retained record safe without an observation.

## I treated a successful job as a claim

A delete job can succeed while a replica, search index or support attachment still contains the data. A connector can also recreate it later. I separated activity records from observed state so that a success message does not automatically become proof of deletion.

This also explains a recent safeguard: a failed HTTP read with zero returned rows is unknown, not absence. At the same timestamp, that failed check must not be hidden by another apparently clean observation. If the state cannot be established, the code stops rather than quietly manufacturing a complete proof.

## I preferred identity evidence over clever guessing

Current and historical emails, phones, hashes and stable IDs are useful links. Names by themselves are not. Explicit source and parent resource references can connect a cleaned record even after direct identifiers have disappeared, so the index follows those links in both directions and over multiple hops.

Some records still lose their subject linkage. I left that uncertainty visible. There is a weaker workflow-time candidate for a unique nearby primary event, but it is disclosed in the trace, blocked by conflicting ownership, and never turns the job's reported result into absence proof.

The uncomfortable trade-off is lower exact-answer agreement on some public cases. I chose that over copying IDs from sample answers or using numeric naming patterns as ownership evidence. Either shortcut would make the score look better without making the audit more trustworthy.

## I made the time interpretation visible

Historical bundles can be exported after the events they contain. For logs and structured exports, I use an explicit embedded readback/event time as the original observation time. For PDFs and screenshots, I use the manifest capture time.

There is a real ambiguity here: if the manifest timestamp is intended as a strict availability embargo, some embedded older observations should be unavailable to an earlier audit. I documented the interpretation instead of presenting it as settled. With more time, I would ask the organizers to clarify it and test both interpretations against independently labeled examples.

## I protected records that are meant to remain

Deletion is not the same as removing everything connected to a person. Security records, legal records, shared support context and tombstones have different requirements.

The planner applies the supplied rules to each resource. Shared support content is checked for this subject's identifiers without erasing another person's permitted context. A tombstone can keep an allowed stable reference while direct identifiers are removed. A missing required retained record is a failure, not a successful deletion.

The challenge has no restore-record operation for repairing that last situation. I chose an explicit error rather than inventing an unsupported action or calling the missing record compliant.

## I stopped recreation paths before proposing record changes

Deleting a record while its import or restore process remains active can recreate the original problem. The plan disables flows and blocks unsafe restores before record changes, then produces the required verification steps. The final array also follows the challenge's canonical operation and identifier ordering.

These are proposed steps. The application does not have production deletion credentials or execute the plan.

## I built a desk for investigation, not just a score screen

I wanted a reviewer to move from a verdict to the actual source. That is why the interface has a case queue, identity trail, trace map, timestamped observations and clickable evidence next to the remediation ledger.

I chose an investigation-dossier visual style because it fits the task and keeps the evidence central. Plain HTML, CSS and JavaScript were enough. A Python loopback server meant no frontend build pipeline or extra deployment dependency under the deadline.

A COMPLETE CSV prediction can still have evidence limitations. The UI shows REVIEW in that situation and keeps the CSV verdict visible. Strict review mode can refuse export altogether. This is more honest than making an attractive green stamp look like an organization-wide certificate.

## I put effort into the handoff

A correct-looking screen is not enough if the ZIP cannot run. I added one finalization command, atomic exports, citation validation and fingerprints binding the inputs, engine, CSV and traces. Stale UI exports and mismatched packages are blocked.

The final checks included the authored test suite, all official requests, a fresh OCR extraction, real browser actions and a separate extraction of the ZIP that reproduced the same CSV. The packaging excludes the dataset, caches and installed environments.

## What I would submit, and what I would improve later

I would submit this verified version rather than replace the core model in the last hour. The current public results are 31/32 correct statuses and 15/32 exact answers. Those samples were used during development; hidden accuracy is unknown. The failures and unsupported links are documented rather than hidden.

The next worthwhile work is better lineage evidence, independent multilingual tests, OCR accuracy measured on identifiers, and a clearer historical-availability contract. Those improvements need new evidence or careful evaluation. The last-minute work that was safe to finish was clearer documentation, stronger validation and a reproducible package.

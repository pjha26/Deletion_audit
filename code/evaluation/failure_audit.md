# Source-backed failure audit

Evaluator-only investigation of public-sample mismatches. Expected steps are read here solely to locate and diagnose errors; the prediction engine never imports this module or these answers.

The classifications below distinguish record-state evidence, identity linkage, workflow claims, and cutoff availability. A resource mention alone does not prove ownership or its final state.

## case_03: COMPLETE → COMPLETE

- Missing `VERIFY_RECORD_ANONYMIZED` for `analytics_9406`: **Pre-cutoff state exists without recovered subject linkage**.
  - Artifact references: `evidence_94`.
  - Parsed pre-cutoff observations: 1; explicit identity matches: 0.
  - Pre-cutoff workflow references: `activity_3852`. Workflow results remain claims.

## case_04: COMPLETE → MISSING

- Missing `VERIFY_RECORD_ABSENT` for `account_004`: **No supplied record-state artifact found**.
  - Artifact references: none.
  - Parsed pre-cutoff observations: 0; explicit identity matches: 0.
  - Pre-cutoff workflow references: none. Workflow results remain claims.
- Missing `VERIFY_RECORD_ANONYMIZED` for `analytics_901`: **Pre-cutoff state exists without recovered subject linkage**.
  - Artifact references: `evidence_56`.
  - Parsed pre-cutoff observations: 1; explicit identity matches: 0.
  - Pre-cutoff workflow references: `activity_3463`. Workflow results remain claims.

## case_07: INCOMPLETE → INCOMPLETE

- Extra `REPORT_REMAINING_RECORD` for `object_19`: related sources `evidence_46`; review supported scope rather than removing it solely to match a label.
- Extra `DELETE_RECORD` for `object_19`: related sources `evidence_46`; review supported scope rather than removing it solely to match a label.
- Extra `VERIFY_RECORD_ABSENT` for `object_19`: related sources `evidence_46`; review supported scope rather than removing it solely to match a label.

## case_17: INCOMPLETE → INCOMPLETE

- Extra `VERIFY_RECORD_ABSENT` for `account_6523`: related sources `evidence_67`; review supported scope rather than removing it solely to match a label.
- Extra `VERIFY_RECORD_REDACTED` for `tombstone_17`: related sources `evidence_42`; review supported scope rather than removing it solely to match a label.

## case_18: INCOMPLETE → INCOMPLETE

- Missing `VERIFY_RECORD_ABSENT` for `account_5521`: **No supplied record-state artifact found**.
  - Artifact references: none.
  - Parsed pre-cutoff observations: 0; explicit identity matches: 0.
  - Pre-cutoff workflow references: `activity_3732`. Workflow results remain claims.
- Missing `VERIFY_RECORD_PRESENT` for `audit_record_6645`: **No supplied record-state artifact found**.
  - Artifact references: none.
  - Parsed pre-cutoff observations: 0; explicit identity matches: 0.
  - Pre-cutoff workflow references: none. Workflow results remain claims.

## case_20: INCOMPLETE → INCOMPLETE

- Missing `VERIFY_RECORD_ABSENT` for `account_5037`: **No supplied record-state artifact found**.
  - Artifact references: none.
  - Parsed pre-cutoff observations: 0; explicit identity matches: 0.
  - Pre-cutoff workflow references: `activity_3734`. Workflow results remain claims.
- Missing `VERIFY_RECORD_PRESENT` for `audit_record_5569`: **No supplied record-state artifact found**.
  - Artifact references: none.
  - Parsed pre-cutoff observations: 0; explicit identity matches: 0.
  - Pre-cutoff workflow references: none. Workflow results remain claims.

## case_21: COMPLETE → COMPLETE

- Missing `VERIFY_RECORD_ABSENT` for `account_6440`: **Pre-cutoff state exists without recovered subject linkage**.
  - Artifact references: `evidence_92`.
  - Parsed pre-cutoff observations: 1; explicit identity matches: 0.
  - Pre-cutoff workflow references: `activity_3661`. Workflow results remain claims.
- Missing `VERIFY_RECORD_ANONYMIZED` for `analytics_5335`: **Pre-cutoff state exists without recovered subject linkage**.
  - Artifact references: `evidence_02`, `evidence_92`.
  - Parsed pre-cutoff observations: 2; explicit identity matches: 0.
  - Pre-cutoff workflow references: `activity_3665`. Workflow results remain claims.

## case_22: INCOMPLETE → INCOMPLETE

- Missing `VERIFY_RECORD_ABSENT` for `account_4990`: **No supplied record-state artifact found**.
  - Artifact references: none.
  - Parsed pre-cutoff observations: 0; explicit identity matches: 0.
  - Pre-cutoff workflow references: `activity_3573`. Workflow results remain claims.

## case_23: INCOMPLETE → INCOMPLETE

- Missing `VERIFY_RECORD_ABSENT` for `account_410`: **No supplied record-state artifact found**.
  - Artifact references: none.
  - Parsed pre-cutoff observations: 0; explicit identity matches: 0.
  - Pre-cutoff workflow references: `activity_3662`. Workflow results remain claims.

## case_25: COMPLETE → COMPLETE

- Missing `VERIFY_RECORD_ABSENT` for `account_3136`: **Pre-cutoff state exists without recovered subject linkage**.
  - Artifact references: `evidence_92`.
  - Parsed pre-cutoff observations: 1; explicit identity matches: 0.
  - Pre-cutoff workflow references: `activity_3597`. Workflow results remain claims.
- Missing `VERIFY_RECORD_ANONYMIZED` for `analytics_1895`: **Pre-cutoff state exists without recovered subject linkage**.
  - Artifact references: `evidence_02`, `evidence_92`.
  - Parsed pre-cutoff observations: 2; explicit identity matches: 0.
  - Pre-cutoff workflow references: `activity_3602`. Workflow results remain claims.

## case_26: COMPLETE → COMPLETE

- Missing `VERIFY_RECORD_ANONYMIZED` for `analytics_4566`: **Pre-cutoff state exists without recovered subject linkage**.
  - Artifact references: `evidence_02`, `evidence_92`.
  - Parsed pre-cutoff observations: 2; explicit identity matches: 0.
  - Pre-cutoff workflow references: `activity_3603`. Workflow results remain claims.

## case_27: COMPLETE → COMPLETE

- Missing `VERIFY_RECORD_ABSENT` for `account_3866`: **Pre-cutoff state exists without recovered subject linkage**.
  - Artifact references: `evidence_02`, `evidence_92`.
  - Parsed pre-cutoff observations: 1; explicit identity matches: 0.
  - Pre-cutoff workflow references: `activity_3530`. Workflow results remain claims.
- Missing `VERIFY_RECORD_ANONYMIZED` for `analytics_4574`: **Pre-cutoff state exists without recovered subject linkage**.
  - Artifact references: `evidence_02`, `evidence_92`.
  - Parsed pre-cutoff observations: 2; explicit identity matches: 0.
  - Pre-cutoff workflow references: `activity_3533`. Workflow results remain claims.

## case_28: COMPLETE → COMPLETE

- Missing `VERIFY_RECORD_ABSENT` for `account_5482`: **Pre-cutoff state exists without recovered subject linkage**.
  - Artifact references: `evidence_92`.
  - Parsed pre-cutoff observations: 1; explicit identity matches: 0.
  - Pre-cutoff workflow references: `activity_3529`. Workflow results remain claims.
- Missing `VERIFY_RECORD_ANONYMIZED` for `analytics_6077`: **Pre-cutoff state exists without recovered subject linkage**.
  - Artifact references: `evidence_02`, `evidence_92`.
  - Parsed pre-cutoff observations: 2; explicit identity matches: 0.
  - Pre-cutoff workflow references: `activity_3534`. Workflow results remain claims.

## case_29: INCOMPLETE → INCOMPLETE

- Missing `VERIFY_RECORD_ABSENT` for `account_7012`: **No supplied record-state artifact found**.
  - Artifact references: none.
  - Parsed pre-cutoff observations: 0; explicit identity matches: 0.
  - Pre-cutoff workflow references: `activity_3532`. Workflow results remain claims.

## case_30: INCOMPLETE → INCOMPLETE

- Missing `VERIFY_RECORD_ABSENT` for `account_4163`: **No supplied record-state artifact found**.
  - Artifact references: none.
  - Parsed pre-cutoff observations: 0; explicit identity matches: 0.
  - Pre-cutoff workflow references: `activity_3465`. Workflow results remain claims.

## case_31: COMPLETE → COMPLETE

- Missing `VERIFY_RECORD_ABSENT` for `account_4857`: **No supplied record-state artifact found**.
  - Artifact references: none.
  - Parsed pre-cutoff observations: 0; explicit identity matches: 0.
  - Pre-cutoff workflow references: `activity_3682`. Workflow results remain claims.

## case_32: INCOMPLETE → INCOMPLETE

- Missing `VERIFY_RECORD_ABSENT` for `account_8858`: **No supplied record-state artifact found**.
  - Artifact references: none.
  - Parsed pre-cutoff observations: 0; explicit identity matches: 0.
  - Pre-cutoff workflow references: `activity_3685`. Workflow results remain claims.

## Root-cause counts

- Pre-cutoff state exists without recovered subject linkage: 11 missing expected steps.
- No supplied record-state artifact found: 11 missing expected steps.

## Implementation decisions

- Preserve a surviving independent replica until its cleanup is evidenced.
- Prefer explicit endpoint field readbacks as citations for a consistent same-day state.
- Do not add a guessed primary resource when an explicit account tombstone already supplies the stable account reference.
- Preserve source and identifier basis for every discovered link. Keep review requirements separate from the challenge status.
- Strict review mode refuses CSV overwrite when unresolved warnings remain. The UI presents those warnings prominently.
- Follow explicit resource-reference edges bidirectionally and across multiple hops, with cutoff filtering and conflicting-owner guards.
- In shared support records, assess the requested subject's identifiers while preserving another customer's permitted context.
- Missing enable/restore flags are unknown, not proof that a flow or restore path is blocked.
- Do not synthesize numeric resource IDs or use public expected steps as a runtime ownership map.

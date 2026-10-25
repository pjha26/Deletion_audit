# Participant-data clarification draft

This draft is for the participant to review and send through the official event channel if needed. It has not been sent. It concerns public samples only and does not request hidden answers.

We can reproduce the public-sample mismatch below without importing sample answers into prediction code. Could you clarify the intended participant-visible ownership and state evidence?

## 1. Expected resource with no located record-state artifact

- `case_04` / `account_004` / expected `VERIFY_RECORD_ABSENT`; artifact references: none; explicit subject matches: 0.
- `case_18` / `account_5521` / expected `VERIFY_RECORD_ABSENT`; artifact references: none; explicit subject matches: 0.
- `case_18` / `audit_record_6645` / expected `VERIFY_RECORD_PRESENT`; artifact references: none; explicit subject matches: 0.

Which supplied field or record maps these request subjects to those resource IDs? If absence should be inferred from a complete snapshot, how should the deleted resource ID be recovered without relying on numeric user-ID conventions?

## 2. Anonymized/absent resource with no recovered subject link

- `case_03` / `analytics_9406` / expected `VERIFY_RECORD_ANONYMIZED`; artifact references: evidence_94; explicit subject matches: 0.
- `case_04` / `analytics_901` / expected `VERIFY_RECORD_ANONYMIZED`; artifact references: evidence_56; explicit subject matches: 0.
- `case_21` / `account_6440` / expected `VERIFY_RECORD_ABSENT`; artifact references: evidence_92; explicit subject matches: 0.

For these records, the parsed pre-cutoff state exists but direct identifiers are gone and no explicit subject link was recovered. Is there an additional lineage or request-to-resource mapping file, or a documented relationship we should use?

## 3. Policy-supported additional artifacts

Some additional records are linked to a deletion subject by supplied catalog evidence and covered by deletion_rules.csv, while the public expected step list omits them. Should all such supported records be included even when an exact sample comparison penalizes the extra step?

The current implementation retains these diagnostics, avoids guessed resource IDs, and reports its measured exact-match limitations. Please clarify the evidence contract or publish corrected participant-facing examples if appropriate.

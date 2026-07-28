# Interval and metric contract

This document defines `evalfence.case.v1`. The independent cross-record
identity contract is defined in [MANIFEST_CONTRACT.md](MANIFEST_CONTRACT.md).
Neither contract changes the other's strict schema or semantics.

## Evidence model

An audit case declares two sets of inclusive line intervals:

- `prediction`: evidence attributed to the evaluated system;
- `gold`: reference evidence used for comparison.

Each interval is `(file, start, end)`. File identifiers are normalized from
backslashes to forward slashes. Same-file intervals are sorted and merged when
they overlap or are adjacent.

For normalized sets `P` and `G`:

- `pred_size = |P|`
- `gold_size = |G|`
- `intersection = |P intersection G|`
- `precision = |P intersection G| / |P|`
- `recall = |P intersection G| / |G|`
- `f1 = 2 * precision * recall / (precision + recall)`

Sizes count inclusive coordinates after merging. Cardinality arithmetic is
checked and fails if a result cannot fit in an unsigned 64-bit report field.
When a denominator is zero, the corresponding metric is `null`. F1 is `null`
unless both precision and recall are defined.

## Required declarations

`policy`, `prediction.input_present`, and `gold.input_present` must be present in
JSON. A missing required field is an input error and exits `1`.

Prediction evidence is always required. A missing `prediction`, or
`prediction.input_present: false`, registers
`EF001_MISSING_PREDICTION_INPUT`. Gold evidence is structurally required, and
`gold.input_present: false` registers `EF008_MISSING_GOLD_INPUT`.

Prediction and gold source labels must be nonempty. Prediction labels are
trimmed before comparison. `allowed_prediction_sources` is a required exact
allowlist; an empty list approves no source. Labels that identify the declared
gold source or visibly contain `gold` fail closed as gold-derived declarations.
This string check audits an adapter declaration, not the upstream data flow.

If `reported.prediction_source` is supplied, it is checked independently and
must equal `prediction.source` after trimming.

## Reported fields

`reported` is optional. Every field inside it is also optional or nullable.
EvalFence always recomputes calculated metrics from the interval declarations,
but compares only supplied non-null report fields. Therefore:

- a mismatch in a supplied field registers its stable code;
- a missing or `null` field is not asserted to be correct; and
- `passed: true` does not validate any metric absent from the input.

Supplying a `reported` object without prediction evidence registers
`EF007_REPORTED_WITHOUT_PREDICTION` because its values cannot be audited.

## Stable violation codes

| Code | Meaning |
| --- | --- |
| `EF000_SCHEMA_VERSION` | The case schema is not `evalfence.case.v1`. |
| `EF001_MISSING_PREDICTION_INPUT` | Required prediction evidence is absent. |
| `EF002_GOLD_AS_PREDICTION` | A prediction source declaration is gold-derived. |
| `EF003_EMPTY_CASE_ID` | `case_id` is empty. |
| `EF004_INVALID_TOLERANCE` | Tolerance is negative or non-finite. |
| `EF005_UNAPPROVED_PREDICTION_SOURCE` | Source is outside the exact allowlist. |
| `EF006_PREDICTION_SOURCE_MISMATCH` | Reported and evidence source labels differ. |
| `EF007_REPORTED_WITHOUT_PREDICTION` | Reported metrics have no prediction evidence. |
| `EF008_MISSING_GOLD_INPUT` | The declared gold input is absent. |
| `EF009_EMPTY_SOURCE` | A required source label or allowlist label is empty. |
| `EF010_INVALID_INTERVAL` | Bounds are zero or reversed. |
| `EF011_UNSAFE_FILE_KEY` | File key is absolute, drive-qualified, empty, or traversing. |
| `EF012_CARDINALITY_OVERFLOW` | A normalized set cannot fit the report count type. |
| `EF101_PRED_SIZE_MISMATCH` | Reported prediction size disagrees. |
| `EF102_GOLD_SIZE_MISMATCH` | Reported gold size disagrees. |
| `EF103_INTERSECTION_MISMATCH` | Reported intersection disagrees. |
| `EF104_PRECISION_FORMULA_MISMATCH` | Reported precision disagrees. |
| `EF105_RECALL_FORMULA_MISMATCH` | Reported recall disagrees. |
| `EF106_F1_FORMULA_MISMATCH` | Reported F1 disagrees. |

Codes are additive. Reports sort and deduplicate identical findings for
deterministic output.

## Exit codes

| Exit | Meaning |
| ---: | --- |
| `0` | Parsed successfully and no registered finding remains. |
| `1` | Input, parsing, size, serialization, empty-batch, or runtime error. |
| `2` | Parsed successfully and at least one finding was registered. |

A JSONL batch must contain at least one case and exits `2` if any case fails.
The report retains exact counts for every violation code and a bounded number of
failing examples.

## Trust boundary

EvalFence checks its normalized declared contract. It does not establish that an
adapter extracted the correct semantic artifact from arbitrary upstream data.
An adapter therefore needs:

1. an exact upstream revision;
2. input-file hashes and a clean import boundary;
3. an explicit mapping from upstream fields to prediction and gold;
4. positive and negative controls; and
5. a statement of what the observations cannot prove.

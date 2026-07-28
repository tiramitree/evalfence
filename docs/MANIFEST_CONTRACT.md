# Keyed-manifest contract

`evalfence.keyed-manifest.v1` is independent from the interval and metric
contract in `evalfence.case.v1`. It audits cross-record identity, coverage, and
collision behavior before an evaluation consumer reduces a sequence into a
keyed map.

The contract does not parse patches, run a benchmark, or score a model. An
adapter supplies one SHA-256 digest for each payload. EvalFence checks the
manifest relationships and emits `evalfence.manifest-report.v1`.

## Input

```json
{
  "schema_version": "evalfence.keyed-manifest.v1",
  "case_id": "example",
  "records": [
    {
      "id": "example__repo-1",
      "payload_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    }
  ],
  "reported": {
    "record_count": 1,
    "unique_id_count": 1
  },
  "policy": {
    "allowed_ids": ["example__repo-1"],
    "required_ids": [],
    "consumer_collision_policy": "last_write_wins"
  }
}
```

All objects reject unknown fields.

- `id` is compared byte-for-byte. EvalFence does not trim or normalize it.
- `payload_sha256` must be exactly 64 lowercase hexadecimal characters.
- `allowed_ids` and `required_ids` must contain unique, non-empty strings.
- Every required ID must also be allowed.
- An empty `required_ids` list explicitly permits a partial or empty manifest.
- `reported` is optional. When present, either count can be `null` to leave
  that count undeclared.
- v1 registers only `last_write_wins`, matching consumers that build a keyed
  dictionary from records in input order.

The adapter decides what bytes a payload digest covers. That choice must be
documented and source-bound; the core cannot authenticate an adapter's digest
claim.

## Calculation

EvalFence:

1. validates schema, case, policy, IDs, and payload digests;
2. groups non-empty IDs by exact value;
3. counts raw records and unique non-empty IDs;
4. detects repeated IDs;
5. distinguishes repeated identical payloads from conflicting payloads;
6. under `last_write_wins`, records the first and last valid payload digest for
   every conflicting group;
7. checks allowlist, required coverage, and declared counts.

A repeated ID is a finding even when all payload digests match. It is not
order-dependent unless at least two valid payload digests differ.

## Stable findings

| Code | Meaning |
|---|---|
| `EF000_SCHEMA_VERSION` | Input uses a different schema version. |
| `EF003_EMPTY_CASE_ID` | `case_id` is empty after trimming. |
| `EF201_EMPTY_RECORD_ID` | A record ID is empty after trimming. |
| `EF202_DUPLICATE_RECORD_ID` | One exact record ID occurs more than once. |
| `EF203_CONFLICTING_DUPLICATE_PAYLOAD` | A duplicate group has multiple valid payload digests. |
| `EF204_UNAPPROVED_RECORD_ID` | A non-empty record ID is outside `allowed_ids`. |
| `EF205_MISSING_REQUIRED_RECORD` | No valid-payload record satisfies a required ID. |
| `EF206_REPORTED_RECORD_COUNT_MISMATCH` | Declared raw record count differs. |
| `EF207_REPORTED_UNIQUE_COUNT_MISMATCH` | Declared unique non-empty ID count differs. |
| `EF208_ORDER_DEPENDENT_COLLAPSE` | A conflicting group has a different possible survivor when input order changes under last-write-wins. |
| `EF209_INVALID_PAYLOAD_DIGEST` | A payload digest is not lowercase SHA-256 syntax. |
| `EF210_INVALID_ID_POLICY` | ID policy contains blanks, duplicates, or a required ID that is not allowed. |

Exit status remains consistent with the interval lane:

- `0`: parsed and no findings;
- `2`: parsed and one or more findings;
- `1`: I/O, size, syntax, or strict deserialization error.

## Report privacy boundary

Reports do not serialize IDs from `records`, `allowed_ids`, or `required_ids`.
Distinct record groups receive deterministic one-based ordinals for that case.
Collapse witnesses contain only group ordinal, zero-based positions of records
with valid payload digests, registered valid payload digests, and the
first/last valid record payload digests.

The caller-controlled `case_id` is copied to the report, so it must not contain
a record ID or sensitive value. This prevents generated findings and witnesses
from becoming an identity list; input cases and `case_id` still require their
own publication privacy review. Unsupported schema values are rejected without
copying the caller-supplied value into a finding.

## SWE-bench source-bound control

The bundled adapter binds the exact public MIT revision
`SWE-bench/SWE-bench@f7bbbb2ccdf479001d6467c9e34af59e44a840f9`.
At that revision:

- the documentation labels `instance_id` as a unique task instance ID and
  allows partial prediction sets;
- the registered constants bind `KEY_INSTANCE_ID`, `KEY_MODEL`, and
  `KEY_PREDICTION` to their documented prediction-field names;
- the loader accepts JSON or JSONL and checks that each record contains
  `instance_id`;
- the evaluation entry point then constructs a Python dictionary keyed by
  `instance_id`.

The adapter verifies exact Git blob SHA-256 values and the registered syntax,
then supplies two synthetic records with the same ID and different payload
digests. Reversing those records changes the simulated last-write-wins
survivor. EvalFence must produce the same three finding codes in both orders
while binding the different surviving digest.

This observation is intentionally narrow. It does not establish that any real
prediction file contains duplicates, that any leaderboard score changed, or
that SWE-bench is defective or nonconforming. The adapter does not import or
execute SWE-bench, Docker, a dataset, a model, an API, or a paid service.

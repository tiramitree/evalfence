# Agent-boundary contract

`evalfence.agent-boundary.v1` is independent from the interval/metric and
keyed-manifest contracts. It audits an adapter's declaration of what reaches a
custom agent, which callable capabilities are exposed, and when the benchmark
captures its baseline.

The contract is generic. It does not name a benchmark, framework, model, or
provider.

## Input

```json
{
  "schema_version": "evalfence.agent-boundary.v1",
  "case_id": "example-boundary",
  "inputs": [
    {
      "name": "task_id",
      "classification": "runtime_metadata",
      "present": true,
      "item_count": 1,
      "payload_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      "mutable_source_alias": false
    }
  ],
  "capabilities": [
    {
      "name": "domain.write_handlers",
      "kind": "write_handler",
      "exposed_to_agent": false,
      "total_count": 4,
      "callable_count": 0,
      "mediated_count": 0
    }
  ],
  "construction_order": {
    "baseline_snapshot_before_agent_constructor": true,
    "baseline_snapshot_before_first_agent_turn": true
  },
  "reported": {
    "input_count": 1,
    "oracle_input_count": 0,
    "capability_group_count": 1,
    "unmediated_write_callable_count": 0
  },
  "policy": {
    "allowed_agent_inputs": ["task_id"],
    "forbid_oracle_inputs": true,
    "forbid_mutable_source_aliases": true,
    "require_write_capability_mediation": true,
    "require_baseline_before_agent_constructor": true
  }
}
```

Unknown JSON fields are rejected. Names must start with a lowercase ASCII
letter, contain only lowercase letters, digits, `.`, `_`, or `-`, and be at
most 128 bytes. Input and capability names must be unique.

## Input classifications

- `runtime_metadata`: harness metadata such as a task key, domain, or clock.
- `user_visible`: content already available through the declared user-facing
  interaction.
- `task_oracle`: task-definition content that the adapter declares unavailable
  to the evaluated policy.
- `scoring_oracle`: expected-state or scoring content that the adapter declares
  unavailable to the evaluated policy.

The Rust core does not infer classifications. The adapter owns that
benchmark-specific mapping and must bind it to reproducible evidence.

`present` controls the exposure counts. `item_count` and `payload_sha256` are
optional evidence fields; when a digest is supplied, it must be lowercase
SHA-256 syntax. A mutable alias means the agent receives the same mutable
source object, rather than a detached representation.

## Capabilities and counts

A capability group declares read or write handlers and four independent facts:

- how many handlers belong to the group;
- whether the group reaches the agent;
- how many exposed handlers are callable; and
- how many callable handlers are mediated by the declared harness boundary.

The core requires:

```text
mediated_count <= callable_count <= total_count
```

`callable_count` must be zero when `exposed_to_agent` is false. For an exposed
write group, `callable_count - mediated_count` is the unmediated write-callable
count. Aggregate callable counts that exceed `u64` fail closed rather than
wrapping.

## Policy semantics

An empty `allowed_agent_inputs` list approves no non-oracle input. Invalid or
duplicate policy names fail closed. Oracle fields are checked by their
classification; they are not silently converted into ordinary allowlisted
metadata.

The constructor-order policy is deliberately stricter than a first-turn-only
check. Arbitrary custom constructor code is agent code, so a baseline captured
after construction cannot establish what state existed before that code ran.

## Stable findings

| Code | Meaning |
| --- | --- |
| `EF301_ORACLE_INPUT_EXPOSED` | A present task/scoring oracle violates the policy. |
| `EF302_UNAPPROVED_AGENT_INPUT` | A present non-oracle input is not allowlisted. |
| `EF303_UNMEDIATED_WRITE_CAPABILITY` | An exposed write group contains unmediated callables. |
| `EF304_AGENT_CODE_BEFORE_BASELINE` | The custom agent is constructed before the baseline snapshot. |
| `EF305_MUTABLE_SOURCE_ALIAS` | A present input aliases a mutable source object. |
| `EF306`–`EF308` | Adapter-reported input/oracle/capability counts disagree. |
| `EF309_INVALID_BOUNDARY_DIGEST` | A supplied payload digest is not lowercase SHA-256. |
| `EF310_INVALID_AGENT_INPUT_POLICY` | The allowlist is invalid or contains duplicates. |
| `EF311_INVALID_BOUNDARY_NAME` | An input or capability name is unsafe. |
| `EF312_DUPLICATE_BOUNDARY_NAME` | An input or capability name is repeated. |
| `EF313_INVALID_CAPABILITY_COUNTS` | Capability totals, callability, mediation, or exposure conflict. |
| `EF314_REPORTED_UNMEDIATED_COUNT_MISMATCH` | The reported unmediated count disagrees. |
| `EF315_INVALID_CONSTRUCTION_ORDER` | Constructor and first-turn ordering declarations contradict each other. |
| `EF316_CAPABILITY_COUNT_OVERFLOW` | Aggregate callable capability counts exceed `u64`. |
| `EF317_INVALID_AGENT_INPUT_DECLARATION` | An absent input is declared as a mutable source alias. |

The shared `EF000_SCHEMA_VERSION` and `EF003_EMPTY_CASE_ID` checks also apply.
Findings exit `2`; malformed input or runtime errors exit `1`; a clean report
exits `0`.

## Boundary

This is a declared-contract checker, not a Python sandbox, capability-secure
runtime, whole-program taint analyzer, or proof of physical/process isolation.
It cannot establish that an adapter observed the real runtime merely because
the JSON is well formed. Source-bound adapters, causal controls, and CI evidence
must support that claim separately.

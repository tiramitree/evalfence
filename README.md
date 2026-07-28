# EvalFence

[![CI](https://github.com/tiramitree/evalfence/actions/workflows/ci.yml/badge.svg)](https://github.com/tiramitree/evalfence/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)

EvalFence is a Rust CLI that audits declared metric, evidence-provenance,
keyed-manifest, and custom-agent boundary contracts for agent benchmarks.

It asks three independent bounded questions:

> Were prediction and gold evidence supplied under distinct declarations, and
> do the supplied metric fields use the denominator their names promise?

> Before records are collapsed into a keyed map, are task identities unique,
> payload digests valid, coverage declared, and collision semantics explicit?

> Which declared inputs and callable capabilities reach custom agent code, and
> is the environment baseline captured before that code can run?

The Rust core validates adapter-supplied labels, intervals, identities, digests,
counts, classifications, capability totals, and formulas. It does not observe
or prove the upstream data flow that produced those adapter declarations.

## Why this exists

Agent evaluations combine model output, trajectories, patches, gold annotations,
repository state, and several metric layers. A score can look plausible even
when an absent prediction is represented by a gold-derived artifact, a field
named `recall` divides by prediction size, interval overlap is double-counted,
duplicate task IDs are silently collapsed, or a batch hides failed cases behind
a successful process.

EvalFence makes a declared contract executable. Findings exit `2`, input or
runtime errors exit `1`, and a clean audit exits `0`.

## Current scope

The interval contract `evalfence.case.v1` checks:

- explicit prediction and gold input-presence declarations;
- a nonempty, exact prediction-source allowlist;
- rejection of empty, gold-derived, or inconsistent source declarations;
- positive inclusive intervals and relative traversal-free file keys;
- deterministic interval merging and overflow-checked cardinalities;
- prediction size, gold size, and intersection;
- standard precision (`intersection / prediction_size`);
- standard recall (`intersection / gold_size`);
- F1 derived from those two metrics;
- bounded single-case and JSONL batch input; and
- stable per-case and aggregate JSON reports.

`policy`, `prediction.input_present`, and `gold.input_present` are required.
An empty source allowlist approves no prediction source. Zero denominators
produce `null`, not an implicit perfect or zero score.

`reported` and each of its metric fields are optional. EvalFence recomputes all
calculated metrics but compares only non-null reported fields. A passing report
does not validate a metric that the input did not supply.

The independent keyed-manifest contract `evalfence.keyed-manifest.v1` checks:

- exact, non-empty record identities;
- lowercase SHA-256 payload-digest syntax;
- duplicate identities and conflicting duplicate payloads;
- allowlisted and required identity coverage;
- declared raw-record and unique-ID counts;
- last-write-wins order-dependent collapse; and
- generated findings and witnesses that replace record IDs with per-case group
  ordinals.

An empty `required_ids` list explicitly permits partial submissions. The core
does not decide which payload bytes an adapter hashes.

The independent agent-boundary contract `evalfence.agent-boundary.v1` checks:

- allowlisted custom-agent inputs;
- explicit runtime, user-visible, task-oracle, and scoring-oracle classes;
- mutable aliases to adapter-declared source objects;
- exposed read/write capability groups;
- callable, mediated, and total capability-count consistency; and
- custom-agent construction versus baseline-snapshot order.

Input classifications remain benchmark-specific adapter declarations. An empty
input allowlist approves no non-oracle field, and invalid or duplicate safe-name
entries fail closed. The core does not infer whether a field is an oracle or
prove that an adapter observed the real runtime.

See [the agent-boundary contract](docs/AGENT_BOUNDARY_CONTRACT.md) for exact
schema and stable-code semantics.

## Quick start

The repository pins Rust 1.97.1 and commits `Cargo.lock`.

```bash
cargo run --locked -- audit --input fixtures/good.json --pretty
cargo run --locked -- audit --input fixtures/gold-fallback.json --pretty
```

The first interval fixture exits `0`. The second exits `2` with:

- `EF001_MISSING_PREDICTION_INPUT`
- `EF002_GOLD_AS_PREDICTION`
- `EF005_UNAPPROVED_PREDICTION_SOURCE`
- `EF105_RECALL_FORMULA_MISMATCH`

Batch input is newline-delimited JSON. An empty or all-whitespace batch is an
input error.

```bash
cargo run --locked -- audit-batch \
  --input cases.jsonl \
  --output report.json \
  --max-examples 10 \
  --pretty
```

Use `-` as the input path to read from stdin.

Audit one keyed manifest:

```bash
cargo run --locked -- audit-manifest   --input fixtures/manifest-good.json   --pretty
cargo run --locked -- audit-manifest   --input fixtures/manifest-conflict.json   --pretty
```

The conflict fixture exits `2` with `EF202`, `EF203`, and `EF208`. Its report
contains payload digests and record positions but does not serialize the record
ID from the manifest.


Audit a declared custom-agent boundary:

```bash
cargo run --locked -- audit-agent-boundary --input fixtures/agent-boundary-good.json --pretty
cargo run --locked -- audit-agent-boundary --input fixtures/agent-boundary-exposed.json --pretty
```

The first fixture exits `0`. The second exits `2` with registered oracle,
unmediated-write, pre-baseline-constructor, and mutable-alias findings.
## Case contract

```json
{
  "schema_version": "evalfence.case.v1",
  "case_id": "example",
  "prediction": {
    "source": "prediction.model_patch",
    "input_present": true,
    "intervals": [{"file": "src/lib.rs", "start": 1, "end": 10}]
  },
  "gold": {
    "source": "gold.init_ctx",
    "input_present": true,
    "intervals": [{"file": "src/lib.rs", "start": 1, "end": 100}]
  },
  "reported": {
    "prediction_source": "prediction.model_patch",
    "pred_size": 10,
    "gold_size": 100,
    "intersection": 10,
    "precision": 1.0,
    "recall": 0.1,
    "f1": 0.18181818181818182
  },
  "policy": {
    "allowed_prediction_sources": ["prediction.model_patch"],
    "tolerance": 1e-9
  }
}
```

See [the interval contract reference](docs/CONTRACT.md),
[keyed-manifest contract](docs/MANIFEST_CONTRACT.md), and
[agent-boundary contract](docs/AGENT_BOUNDARY_CONTRACT.md) for exact fields
and stable-code semantics.

## ContextBench case study

The first adapter is pinned to
[`EuniAI/ContextBench@1436c28`](https://github.com/EuniAI/ContextBench/tree/1436c28a8eb95496da4ea69ad458b9f8a8eb7d61),
an Apache-2.0 coding-agent context benchmark.

At that exact revision, the per-instance EditLoc path:

1. falls back from an absent `model_patch` to the gold `patch`; and
2. writes both per-instance EditLoc precision and recall as
   `intersection / prediction_size`.

The separate upstream aggregation path accumulates intersection, gold size,
and prediction size, then recomputes standard micro recall and precision. This
project does not claim that the aggregate or any leaderboard recall is affected
by the per-instance field formula.

The adapter simulates the absent-`model_patch` path over 500 public rows. Of the
421 rows whose gold patch contains deleted lines:

| Per-instance observation | Count |
| --- | ---: |
| Cases materialized from the gold-patch fallback | 421 |
| Record recall differs from standard set recall | 410 |
| Record recall is `1.0` while standard set recall is below `1.0` | 380 |

Across those same 421 cases, the mean per-instance record field is `0.941993`;
mean standard set recall is `0.082896`. These are per-instance means under the
simulated fallback, not aggregate or leaderboard metrics.

The case study does not establish whether any submitted prediction omitted
`model_patch`. If the intended per-instance measure is only "what fraction of
predicted edits fall inside context," that is a precision/containment measure;
EvalFence does not choose the upstream authors' intended replacement.

Reproduce from a fresh exact clone. The adapter rejects any tracked
modification, untracked file, or ignored residue in the upstream worktree.

The hash-pinned Python dependency lane targets CPython 3.12 on Linux x86_64,
matching the public CI case-study job.

```bash
python -m pip install --require-hashes -r requirements-audit.txt
git clone https://github.com/EuniAI/ContextBench.git contextbench
git -C contextbench checkout 1436c28a8eb95496da4ea69ad458b9f8a8eb7d61
python scripts/contextbench_audit.py \
  --contextbench-root contextbench \
  --cases-out build/contextbench-cases.jsonl \
  --summary-out build/contextbench-summary.json
cargo run --locked -- audit-batch \
  --input build/contextbench-cases.jsonl \
  --output build/contextbench-report.json \
  --pretty
```

The final command is expected to exit `2`. CI is configured to verify exact
source, parser, metric-helper, dataset, dependency, observation, and violation
hashes or counts. See
[the bounded case-study note](docs/CONTEXTBENCH_CASE_STUDY.md).

## SWE-bench keyed-manifest case study

The second adapter is pinned to
[`SWE-bench/SWE-bench@f7bbbb2`](https://github.com/SWE-bench/SWE-bench/tree/f7bbbb2ccdf479001d6467c9e34af59e44a840f9),
an MIT-licensed coding-agent benchmark.

At that exact revision, the official evaluation note labels `instance_id` as
a unique task instance ID and permits partial prediction sets. The loader
accepts JSON or JSONL records and checks that each contains `instance_id`.
The evaluation entry point then constructs a Python dictionary keyed by that
field.

The source-bound adapter verifies exact Git blob hashes, registered
prediction-key constants, and the registered AST shape. It supplies two synthetic records with the same ID and different
payload digests. Reversing their order changes the simulated last-write-wins
survivor. EvalFence emits the same duplicate, conflict, and order-dependence
findings for both orders while binding the different survivor digest.

The control does not import or execute SWE-bench and needs no Docker, dataset,
model, GPU, API, or paid service. It does not establish that any real
prediction file contains duplicates, that a published score changed, or that
SWE-bench is defective or nonconforming.

```bash
git clone https://github.com/SWE-bench/SWE-bench.git swebench
git -C swebench checkout f7bbbb2ccdf479001d6467c9e34af59e44a840f9
cargo build --locked
python scripts/swebench_manifest_audit.py   --swebench-root swebench   --evalfence-bin target/debug/evalfence   --output-dir build/swebench-manifest
python scripts/verify_manifest_case_study.py   --summary build/swebench-manifest/summary.json   --forward-report build/swebench-manifest/forward-report.json   --reverse-report build/swebench-manifest/reverse-report.json
```

The upstream worktree must contain only exact tracked files. CI regenerates
the bounded summary and both reports from a fresh detached checkout.


## STATE-Bench custom-agent boundary case study

The third adapter is pinned to
[`microsoft/STATE-Bench@4efcbf2`](https://github.com/microsoft/STATE-Bench/tree/4efcbf2d4fe60df04878859b692d9391f3d5b33a),
an MIT-licensed stateful-agent benchmark.

At that exact revision, source and AST checks bind the custom-agent context
construction, live handler argument, and baseline-snapshot order. A no-API
runtime probe uses one public test task in each of the three registered domains.
It observes 14 state-requirement items, nine task-requirement items, and 20
callable write handlers reaching the declared custom-agent boundary.

A separate registered shopping control derives two normal harness-executed
tool calls only from the supplied runtime context. Its deterministic state
score is `1`; removing only `state_requirements` from the same context makes no
calls and scores `0`. This is not a protocol-compliant or official score.

The generated boundary case produces three oracle-input, three
unmediated-write, one pre-baseline-constructor, and two mutable-alias findings.
It does not show that any submitted agent used those fields or callables, or
that a leaderboard result was affected. See
[the bounded STATE-Bench case study](docs/STATE_BENCH_CASE_STUDY.md).

```bash
python scripts/statebench_boundary_audit.py \
  --statebench-root statebench \
  --case-out build/statebench-boundary/case.json \
  --summary-out build/statebench-boundary/summary.json
cargo run --locked -- audit-agent-boundary \
  --input build/statebench-boundary/case.json \
  --output build/statebench-boundary/report.json
python scripts/verify_statebench_case_study.py \
  --expected-summary evidence/statebench-4efcbf2-agent-boundary-summary.json \
  --summary build/statebench-boundary/summary.json \
  --case build/statebench-boundary/case.json \
  --report build/statebench-boundary/report.json
```
## Security and privacy boundary

The Rust core performs no network or subprocess operation and reads only the
named JSON or JSONL input. The interval lane rejects host and traversal paths.
All three single-case commands are bounded to 8 MiB; interval batch input is
bounded to 64 MiB, 1 MiB per row, and 100,000 cases. The core never needs
source contents, prompts, trajectories, credentials, or model responses.
Manifest findings do not serialize record IDs. Boundary findings expose only
declared safe field/group names and counts, while payloads remain optional
hashes. The caller-controlled `case_id` is copied to reports and requires
publication review.

The separate Python adapters read clean exact public clones and hash-bound
files. The ContextBench lane emits public instance identifiers, coordinates,
counts, and metrics; the SWE-bench lane emits one synthetic identifier and
digests; the STATE-Bench lane emits field names, counts, hashes, and bounded
result relationships. Checked evidence copies no task text, requirement
payload, environment payload, prompt, trajectory, patch, or repository source.

CI includes a generic text-only privacy gate for common contact data, host
paths, credential filenames, key markers, and token prefixes. It is a backstop,
not a universal PII or secret detector. Do not place private prompts,
proprietary code, secrets, personal data, or unpublished research in public
fixtures, artifacts, or issues.

## What this does not prove

EvalFence v0.3 is not:

- proof of actual data-flow provenance beyond adapter declarations;
- a complete static taint analyzer for arbitrary evaluator source;
- proof that omitted or null reported fields are correct;
- a model-quality, harness-quality, or coding-success benchmark;
- evidence that a public aggregate or leaderboard was affected;
- a sandbox, capability-secure runtime, whole-program taint analyzer,
  statistical significance framework, or production deployment;
- evidence of external adoption, independent review, or endorsement.

Generalization beyond the exact ContextBench, SWE-bench, and STATE-Bench
controls needs a separately declared adapter contract and evidence.

## Development provenance

This repository was built with substantial AI assistance under the
`tiramitree` account. Public claims are limited to committed tests, frozen
upstream hashes, generated evidence, and CI results. AI assistance is not an
independent review, endorsement, or external adoption signal.

## Development

```bash
cargo fmt --all -- --check
cargo clippy --all-targets --locked -- -D warnings
cargo test --all-targets --locked
python -m py_compile \
  scripts/contextbench_audit.py scripts/swebench_manifest_audit.py \
  scripts/statebench_boundary_audit.py scripts/privacy_gate.py \
  scripts/verify_case_study.py scripts/verify_manifest_case_study.py scripts/verify_statebench_case_study.py
python -m unittest discover -s tests -p 'test_*.py'
python scripts/privacy_gate.py --root .
```

CI is configured to run the Rust suite on Linux, Windows, and macOS and all
three pinned case studies on Linux. See [CONTRIBUTING.md](CONTRIBUTING.md) and
[SECURITY.md](SECURITY.md).

## License

Original EvalFence code is Apache-2.0. ContextBench, SWE-bench, and STATE-Bench
remain copyright their authors and are referenced under their Apache-2.0, MIT,
and MIT licenses respectively. EvalFence does not vendor upstream source,
datasets, task definitions, environments, prompts, or trajectories.

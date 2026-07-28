# EvalFence

[![CI](https://github.com/tiramitree/evalfence/actions/workflows/ci.yml/badge.svg)](https://github.com/tiramitree/evalfence/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)

EvalFence is a Rust CLI that audits declared metric and evidence-provenance
contracts for agent benchmarks.

> Were prediction and gold evidence supplied under distinct declarations, and
> do the supplied metric fields use the denominator their names promise?

The Rust core validates adapter-supplied labels, intervals, counts, and formulas.
It does not observe or prove the upstream data flow that produced those
adapter declarations.

## Why this exists

Agent evaluations combine model output, trajectories, patches, gold annotations,
repository state, and several metric layers. A score can look plausible even
when an absent prediction is represented by a gold-derived artifact, a field
named `recall` divides by prediction size, interval overlap is double-counted,
or a batch hides failed cases behind a successful process.

EvalFence makes a declared contract executable. Findings exit `2`, input or
runtime errors exit `1`, and a clean audit exits `0`.

## Current scope

The v0.1 contract checks:

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

## Quick start

The repository pins Rust 1.97.1 and commits `Cargo.lock`.

```bash
cargo run --locked -- audit --input fixtures/good.json --pretty
cargo run --locked -- audit --input fixtures/gold-fallback.json --pretty
```

The first fixture exits `0`. The second exits `2` with:

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

See [the contract reference](docs/CONTRACT.md) for exact field and stable-code
semantics.

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

## Security and privacy boundary

The Rust core performs no network or subprocess operation, reads only the named
JSON or JSONL input, rejects host and traversal paths, and bounds a case to 8
MiB, a batch to 64 MiB, a row to 1 MiB, and a batch to 100,000 cases. It never
needs source contents, prompts, trajectories, credentials, or model responses.

The separate Python adapter reads a clean exact public clone and hash-bound
files. It emits only public instance identifiers, relative interval coordinates,
counts, and metric values; it does not copy issue text, patches, prompts, or
repository source into checked evidence.

CI includes a generic text-only privacy gate for common contact data, host
paths, credential filenames, key markers, and token prefixes. It is a backstop,
not a universal PII or secret detector. Do not place private prompts,
proprietary code, secrets, personal data, or unpublished research in public
fixtures, artifacts, or issues.

## What this does not prove

EvalFence v0.1 is not:

- proof of actual data-flow provenance beyond adapter declarations;
- a complete static taint analyzer for arbitrary evaluator source;
- proof that omitted or null reported fields are correct;
- a model-quality, harness-quality, or coding-success benchmark;
- evidence that a public aggregate or leaderboard was affected;
- a sandbox, statistical significance framework, or production deployment;
- evidence of external adoption, independent review, or endorsement.

Generalization beyond the exact ContextBench case study needs a separately
declared adapter contract and evidence.

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
python -m py_compile scripts/contextbench_audit.py scripts/privacy_gate.py scripts/verify_case_study.py
python -m unittest discover -s tests -p 'test_*.py'
python scripts/privacy_gate.py --root .
```

CI is configured to run the Rust suite on Linux, Windows, and macOS and the
pinned case study on Linux. See [CONTRIBUTING.md](CONTRIBUTING.md) and
[SECURITY.md](SECURITY.md).

## License

Original EvalFence code is Apache-2.0. ContextBench remains copyright its
authors and is referenced under its Apache-2.0 license. EvalFence does not
vendor ContextBench source or dataset files.

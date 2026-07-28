# Changelog

## 0.3.0 - 2026-07-29

- Add the generic `evalfence.agent-boundary.v1` declared contract for custom
  agent inputs, oracle classifications, mutable aliases, callable write
  capabilities, mediation, and baseline-snapshot order.
- Fail closed on contradictory construction order, absent mutable aliases, and
  aggregate capability-count overflow.
- Add a standard-library-only, source-bound STATE-Bench adapter with exact
  source/AST checks, three-domain offline runtime observations, and one
  deterministic no-API causal control.
- Register the bounded
  `microsoft/STATE-Bench@4efcbf2d4fe60df04878859b692d9391f3d5b33a`
  case study without claiming an official score, submission effect, or defect.
- Preserve all v0.1 interval/metric and v0.2 keyed-manifest semantics.

## 0.2.0 - 2026-07-28

- Add the independent `evalfence.keyed-manifest.v1` contract.
- Detect duplicate IDs, conflicting payload digests, coverage mismatches, and
  order-dependent last-write-wins collapse without serializing manifest record
  IDs in generated findings or witnesses.
- Add a source-bound synthetic control for
  `SWE-bench/SWE-bench@f7bbbb2ccdf479001d6467c9e34af59e44a840f9`.
- Preserve the v0.1 interval, metric, batch, finding, and exit-code semantics.

## 0.1.0 - 2026-07-28

- Add strict interval and metric contract auditing.
- Add the bounded ContextBench source and formula case study.

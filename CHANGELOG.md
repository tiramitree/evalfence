# Changelog

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

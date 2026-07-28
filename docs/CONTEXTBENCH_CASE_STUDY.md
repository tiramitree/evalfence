# Bounded ContextBench case study

## Question

At one exact public ContextBench revision, does the per-instance EditLoc path
preserve a declared prediction/gold boundary, and do its fields named precision
and recall use standard set denominators?

This is a source-and-data contract audit. It is not a model, aggregate, or
leaderboard reproduction.

## Frozen source

- upstream: `EuniAI/ContextBench`
- revision: `1436c28a8eb95496da4ea69ad458b9f8a8eb7d61`
- license: Apache-2.0
- dataset: `data/contextbench_verified.parquet`
- rows: 500
- dataset SHA-256:
  `e9dcfd504cbfb849ac815a79040c793d0d92f94eecc9b5a4ee3e1445a2f8a791`
- evaluator SHA-256:
  `059b7f51cc09cf858c02b630e1eb5f78df7e105eb08da2950619dadf97dc1594`
- metric helper SHA-256:
  `457dd5b03ef5b89b93f892fd4b45658cc9795600f7e13271c65e39657f2df358`

The adapter also binds the exact gold parser, diff parser, and license hashes.
It refuses a source worktree containing any tracked modification, untracked
file, or ignored residue before importing the package.

## Registered checks

### C1: declared prediction provenance

The exact per-instance path reads `prediction.model_patch`; when that value is
absent, it falls back to `gold.patch`. The adapter simulates that missing-input
branch and labels the materialized intervals `gold.patch_fallback` with
`input_present: false`.

EvalFence registers missing-input, gold-derived-source, and source-allowlist
findings. These findings validate the adapter declaration. They do not prove
that a published submission used the fallback.

### C2: per-instance metric denominator

For nonempty deletion interval sets, EvalFence calculates:

```text
standard precision = intersection / prediction_size
standard recall    = intersection / gold_size
```

The exact per-instance EditLoc record writes both fields using
`intersection / prediction_size`. `EF105_RECALL_FORMULA_MISMATCH` is registered
only when the supplied record field differs from standard set recall by more
than `1e-9`.

### Separate aggregate path

The same upstream file has a separate aggregation path. It sums intersection,
gold size, and prediction size across instances and calls the hash-bound metric
helper, which computes micro recall from total intersection divided by total
gold size and precision from total intersection divided by total prediction
size.

The per-instance formula observation therefore does not establish an aggregate
or leaderboard recall error.

### Controls

- `fixtures/good.json` has present, allowlisted evidence and correct formulas.
- `fixtures/gold-fallback.json` isolates the declared fallback and denominator
  mismatch on a 10-line prediction and 100-line gold set.
- Rust tests cover merging, cross-file intersection, path rejection,
  overflow, missing declarations, source consistency, empty denominators,
  optional reported fields, and the metamorphic law that adding unmatched gold
  leaves precision unchanged while reducing recall.

## Observations

| Per-instance observation | Value |
| --- | ---: |
| Dataset rows inspected | 500 |
| Rows without deleted patch lines | 79 |
| Nonempty simulated fallback cases | 421 |
| Standard recall formula mismatches | 410 |
| Record recall greater than standard recall | 410 |
| Record recall `1.0`, standard recall below `1.0` | 380 |
| Mean per-instance record recall | 0.941993 |
| Mean standard set recall over the same cases | 0.082896 |
| Median positive gap | 0.946818 |
| Maximum positive gap | 0.999408 |

The 11 nonempty cases without a mismatch have zero intersection, so both
ratios are zero. The two means above are not micro-aggregate or leaderboard
metrics.

## Interpretation boundary

The provenance finding is a potential per-instance evaluator branch: it applies
when a prediction record reaches EditLoc without `model_patch`. The audit does
not show how often, if ever, that happened in a published submission.

A per-instance field named recall does not implement standard set recall at this
revision. The upstream comment may instead describe a containment question--are
predicted edits inside context?--for which `intersection / prediction_size` is a
precision-like measure. EvalFence does not choose the authors' intended
replacement; it requires supplied names, formulas, and declared evidence to
agree.

No model accuracy, agent quality, aggregate or leaderboard impact, benchmark
validity as a whole, external review, adoption, or production conclusion
follows.

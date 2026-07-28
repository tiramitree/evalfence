# Bounded STATE-Bench custom-agent case study

## Question

At one exact public STATE-Bench revision, what task/scoring fields and write
callables reach the custom-agent construction path, and is the environment
baseline captured before arbitrary custom constructor code runs?

This is a source-bound harness-integrity control. It is not an official
benchmark run, model evaluation, security assessment, or leaderboard
reproduction.

## Frozen source

- upstream: `microsoft/STATE-Bench`
- revision: `4efcbf2d4fe60df04878859b692d9391f3d5b33a`
- package version: `0.8.1`
- evaluation protocol: `state_bench_v0.8.1_gpt54`
- license: MIT
- registered files: 10

The adapter binds canonical Git blob IDs and SHA-256 values for the agent base,
orchestrator, task schema, batch entry point, two custom-agent documents, one
registered shopping task and environment, license, and package metadata. It
also recognizes exact CRLF checkout hashes while requiring those bytes to be
only a line-ending translation of the registered Git blob.

The source worktree must be at the exact detached revision and contain no
tracked modification, untracked file, or ignored residue.

## Registered source shape

The adapter checks the Python syntax tree rather than searching for isolated
tokens:

1. `AgentRuntimeContext` declares task summary, state requirements, and task
   requirements.
2. `run_task` maps the corresponding `TaskDefinition` fields into that
   context.
3. The context and the environment's handler mapping are arguments to the
   resolved custom-agent constructor.
4. The constructor call occurs before the first environment snapshot.
5. The first snapshot occurs before the first agent turn.

The Agent Learning Track documentation separately says held-out test task
definitions and environments must not be oracle inputs for learning
extraction. The custom-client documentation describes runtime context as task
metadata and instructs harness-executed custom agents to ignore the handler
argument. This case study records that instruction as a convention; it does
not treat documentation as an enforced isolation mechanism.

## Offline runtime observations

The standard-library-only adapter installs a client stub that raises on any
model or simulator call. It then uses the official task loader, domain
environments, protocol split, and `run_task` path for one test task in each
domain.

| Domain | State-requirement items | Task-requirement items | Callable write handlers |
| --- | ---: | ---: | ---: |
| travel | 4 | 2 | 7 |
| customer support | 6 | 1 | 5 |
| shopping assistant | 4 | 6 | 8 |
| **Total** | **14** | **9** | **20** |

For all three tasks:

- the task summary reaching the custom agent equals the loaded task summary;
- requirement payload hashes match;
- both requirement lists are the same mutable objects held by the loaded task;
- every registered write handler reaching the constructor is callable; and
- observed event order is constructor, baseline snapshot, first agent turn,
  final snapshot.

Model-client, simulator-client, and judge calls are all zero.

## Registered causal control

The shopping task `4-brand_bundle_missed` supplies a bounded no-API control.
The unsafe arm derives two normal harness-executed tool requests from the state
requirements supplied through runtime context. The control arm gives the same
policy a context with only the state-requirements list removed.

| Arm | Deterministic state score | Tool calls | Tool errors | Empty state diff |
| --- | ---: | ---: | ---: | --- |
| context-only oracle arm | 1 | 2 | 0 | no |
| state-requirements-removed control | 0 | 0 | 0 | yes |

Only the official deterministic state checker is used. No task-requirements
judge runs. The score is an integrity-control outcome, not a protocol-compliant
or official STATE-Bench score.

## EvalFence result

The generated `evalfence.agent-boundary.v1` case declares:

- four allowed runtime-metadata fields;
- three exposed task/scoring-oracle fields;
- two mutable source aliases;
- three exposed write-handler groups containing 20 callable, unmediated
  handlers in total; and
- custom-agent construction before the baseline snapshot.

EvalFence emits nine findings: three `EF301`, three `EF303`, one `EF304`, and
two `EF305`. These findings validate the adapter's registered declaration. They
do not establish that any submitted agent used the fields or callables.

## Reproduction

No Python package installation, model, dataset download, GPU, API key, or paid
service is required after the exact public source revision is available.

```bash
git clone https://github.com/microsoft/STATE-Bench.git statebench
git -C statebench checkout 4efcbf2d4fe60df04878859b692d9391f3d5b33a
cargo build --locked
python scripts/statebench_boundary_audit.py \
  --statebench-root statebench \
  --case-out build/statebench-boundary/case.json \
  --summary-out build/statebench-boundary/summary.json
target/debug/evalfence audit-agent-boundary \
  --input build/statebench-boundary/case.json \
  --output build/statebench-boundary/report.json \
  --pretty
python scripts/verify_statebench_case_study.py \
  --summary build/statebench-boundary/summary.json \
  --case build/statebench-boundary/case.json \
  --report build/statebench-boundary/report.json
```

The EvalFence command is expected to exit `2`. CI verifies the exact committed
summary, generated case/report relationships, finding counts, and privacy
boundary.

## Interpretation boundary

This case study does not claim:

- that STATE-Bench is defective, insecure, compromised, or invalid;
- that any official submission or leaderboard entry used the exposed data;
- that any agent cheated;
- that removing one context field isolates arbitrary untrusted Python code;
- complete isolation from filesystem access, task-ID-based lookup, or other
  same-process custom-agent hooks;
- that a conventionally ignored argument is necessarily harmful;
- model quality, benchmark pass rate, production impact, external adoption,
  independent review, or endorsement; or
- applicability to a revision other than the registered commit.

The narrow result is that the pinned source and deterministic runtime controls
support one declared custom-agent boundary case, and EvalFence fails closed on
that declaration.

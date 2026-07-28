# Threat model

## Assets

- correctness of normalized interval counts and formulas;
- separation of adapter-declared prediction and gold evidence;
- deterministic reports and stable findings;
- keyed-manifest identity, digest, coverage, and collision declarations;
- non-serialization of manifest record IDs in generated findings and witnesses;
- caller control over local input and output paths; and
- absence of private contents in committed or uploaded evidence.

## In scope

- malformed, empty, or oversized JSON and JSONL;
- missing explicit input-presence and policy declarations;
- zero, reversed, overlapping, adjacent, or cardinality-overflowing intervals;
- absolute, UNC, drive-qualified, or traversing file identifiers;
- missing prediction or gold inputs;
- empty, gold-derived, unapproved, or inconsistent source labels;
- supplied count and formula disagreement;
- empty, duplicate, unapproved, or missing keyed-manifest identities;
- invalid payload digests and order-dependent last-write-wins collapse;
- duplicate findings;
- a failing case hidden inside a larger batch;
- a dirty upstream worktree contaminating the public adapter import; and
- common contact, host-path, credential-file, and secret-prefix patterns in
  tracked or uploaded text evidence.

## Out of scope

- proving actual upstream data flow from source-label strings alone;
- executing untrusted evaluator code in the Rust core;
- proving adapter semantics or payload-digest coverage without its frozen-source
  contract;
- proving that a synthetic manifest control occurs in a real submission;
- arbitrary static source-code taint analysis;
- malicious local users who can replace the binary or inputs;
- filesystem durability after power loss;
- cryptographic signing or remote attestation;
- secrets deliberately placed in `case_id` or source strings outside the public
  privacy gate;
- universal PII or secret detection; and
- model, harness, task, aggregate, or leaderboard correctness beyond registered
  checks.

## Design choices

- The Rust core performs no network or subprocess operation.
- Inputs and cardinality arithmetic are bounded before trust.
- File keys are identifiers only and are never opened.
- Empty metric denominators are explicit `null`.
- Keyed-manifest findings and witnesses expose group ordinals, positions, and
  payload digests, but do not serialize IDs from records or policy.
  Caller-controlled `case_id` is copied to the report.
- Findings use exit `2`; input and runtime errors use exit `1`.
- Public adapters reject any tracked, untracked, or ignored upstream residue
  and verify canonical Git blob hashes before import or source inspection.
  Checked-out text may differ only by Git's LF-to-CRLF translation; binary
  inputs must be byte-exact.
- Adapters remain separate so their wider dependency and execution boundary is
  visible.
- CI scans tracked text and named generated artifacts before upload, but that
  generic gate is not treated as proof of complete privacy.

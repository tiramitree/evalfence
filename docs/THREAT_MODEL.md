# Threat model

## Assets

- correctness of normalized interval counts and formulas;
- separation of adapter-declared prediction and gold evidence;
- deterministic reports and stable findings;
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
- duplicate findings;
- a failing case hidden inside a larger batch;
- a dirty upstream worktree contaminating the public adapter import; and
- common contact, host-path, credential-file, and secret-prefix patterns in
  tracked or uploaded text evidence.

## Out of scope

- proving actual upstream data flow from source-label strings alone;
- executing untrusted evaluator code in the Rust core;
- proving adapter semantics without its frozen-source contract;
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
- Findings use exit `2`; input and runtime errors use exit `1`.
- The public adapter rejects any tracked, untracked, or ignored upstream residue
  and verifies canonical Git blob hashes before import. Checked-out text may
  differ only by Git's LF-to-CRLF translation; the dataset must be byte-exact.
- Adapters remain separate so their wider dependency and execution boundary is
  visible.
- CI scans tracked text and named generated artifacts before upload, but that
  generic gate is not treated as proof of complete privacy.

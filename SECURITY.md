# Security policy

Please use GitHub's private vulnerability-reporting interface when it is
available for this repository. Do not place credentials, private data, or
unpublished exploit details in a public issue.

EvalFence's Rust core does not execute evaluator commands or read source files
named by interval keys. Keyed-manifest findings and witnesses do not serialize
IDs from records or policy, but `case_id` is copied to reports and input
manifests still require a publication privacy review. A
report that depends on a third-party adapter inherits that adapter's separate
execution, source-inspection, digest-coverage, and dependency boundary.

Security reports are assessed against the latest tagged version when one exists.
No long-term-support, response-time, deployment, or production guarantee is offered.

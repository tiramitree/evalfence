#!/usr/bin/env python3
"""Offline relationship checks for the bounded SWE-bench manifest control."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

EXPECTED_CODES = [
    "EF202_DUPLICATE_RECORD_ID",
    "EF203_CONFLICTING_DUPLICATE_PAYLOAD",
    "EF208_ORDER_DEPENDENT_COLLAPSE",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--forward-report", type=Path, required=True)
    parser.add_argument("--reverse-report", type=Path, required=True)
    return parser.parse_args()


def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load(path: Path) -> dict[str, Any]:
    value = json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=reject_duplicate_keys,
    )
    if not isinstance(value, dict):
        raise SystemExit(f"{path} is not one JSON object")
    return value


def verify_report(
    report: dict[str, Any], expected_first: str, expected_last: str
) -> None:
    if report.get("schema_version") != "evalfence.manifest-report.v1":
        raise SystemExit("unexpected manifest report schema")
    if report.get("passed") is not False:
        raise SystemExit("registered conflict report must fail")
    calculated = report.get("calculated")
    if calculated != {
        "record_count": 2,
        "unique_id_count": 1,
        "duplicate_id_count": 1,
        "conflicting_duplicate_id_count": 1,
        "order_dependent_collapse_count": 1,
        "unapproved_id_count": 0,
        "missing_required_id_count": 0,
        "invalid_payload_count": 0,
    }:
        raise SystemExit("unexpected manifest report counts")
    violations = report.get("violations")
    if not isinstance(violations, list):
        raise SystemExit("manifest report violations are unavailable")
    if [violation.get("code") for violation in violations] != EXPECTED_CODES:
        raise SystemExit("unexpected manifest report finding codes")
    witnesses = report.get("collapse_witnesses")
    if not isinstance(witnesses, list) or len(witnesses) != 1:
        raise SystemExit("manifest report must contain one collapse witness")
    witness = witnesses[0]
    if (
        witness.get("record_group") != 1
        or witness.get("positions") != [0, 1]
        or witness.get("first_record_payload_sha256") != expected_first
        or witness.get("last_record_payload_sha256") != expected_last
    ):
        raise SystemExit("manifest collapse witness is inconsistent")


def main() -> int:
    args = parse_args()
    summary = load(args.summary)
    forward = load(args.forward_report)
    reverse = load(args.reverse_report)
    if summary.get("schema_version") != (
        "evalfence.swebench-manifest-case-study.v1"
    ):
        raise SystemExit("unexpected case-study schema")
    observations = summary.get("observations")
    if not isinstance(observations, dict):
        raise SystemExit("case-study observations are unavailable")
    if observations.get("survivor_changes_when_input_order_reverses") is not True:
        raise SystemExit("registered order-reversal observation is absent")
    if observations.get("reports_expose_record_ids") is not False:
        raise SystemExit("case-study report redaction boundary changed")
    forward_survivor = observations.get("forward_survivor_sha256")
    reverse_survivor = observations.get("reverse_survivor_sha256")
    if (
        not isinstance(forward_survivor, str)
        or not isinstance(reverse_survivor, str)
        or len(forward_survivor) != 64
        or len(reverse_survivor) != 64
        or forward_survivor == reverse_survivor
    ):
        raise SystemExit("case-study survivor digests are invalid")
    verify_report(forward, reverse_survivor, forward_survivor)
    verify_report(reverse, forward_survivor, reverse_survivor)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

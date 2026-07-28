#!/usr/bin/env python3
"""Verify the bounded ContextBench case-study outputs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--batch-report", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    summary = json.loads(args.summary.read_text(encoding="utf-8"))
    report = json.loads(args.batch_report.read_text(encoding="utf-8"))

    if summary.get("schema_version") != "evalfence.contextbench-case-study.v1":
        raise SystemExit("unexpected ContextBench case-study summary schema")

    expected_observations = {
        "dataset_rows": 500,
        "rows_without_deleted_patch_lines": 79,
        "gold_fallback_cases_with_deleted_lines": 421,
        "per_instance_standard_recall_formula_mismatches": 410,
        "per_instance_record_recall_greater_than_standard": 410,
        "per_instance_record_recall_one_standard_below_one": 380,
        "mean_per_instance_record_recall": 0.941993,
        "mean_standard_set_recall_same_cases": 0.082896,
        "median_positive_gap": 0.946818,
        "max_positive_gap": 0.999408,
    }
    if summary.get("observations") != expected_observations:
        raise SystemExit(
            "unexpected ContextBench observations:\n"
            + json.dumps(summary.get("observations"), indent=2, sort_keys=True)
        )

    if report.get("schema_version") != "evalfence.batch-report.v1":
        raise SystemExit("unexpected batch report schema")
    if (report.get("total"), report.get("passed"), report.get("failed")) != (421, 0, 421):
        raise SystemExit("unexpected batch verdict counts")
    expected_violations = {
        "EF001_MISSING_PREDICTION_INPUT": 421,
        "EF002_GOLD_AS_PREDICTION": 421,
        "EF005_UNAPPROVED_PREDICTION_SOURCE": 421,
        "EF105_RECALL_FORMULA_MISMATCH": 410,
    }
    if report.get("violation_counts") != expected_violations:
        raise SystemExit(
            "unexpected violation counts:\n"
            + json.dumps(report.get("violation_counts"), indent=2, sort_keys=True)
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

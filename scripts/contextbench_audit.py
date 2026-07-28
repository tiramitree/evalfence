#!/usr/bin/env python3
"""Build bounded EvalFence cases from an exact public ContextBench revision.

The adapter emits only public instance identifiers, interval coordinates, counts,
and metric values. It does not copy repository contents, issue text, patches, or
gold-context text into EvalFence evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import statistics
import subprocess
import sys
from pathlib import Path
from typing import Any

EXPECTED_COMMIT = "1436c28a8eb95496da4ea69ad458b9f8a8eb7d61"
TOLERANCE = 1.0e-9
EXPECTED_FILES = {
    "contextbench/evaluate.py": "059b7f51cc09cf858c02b630e1eb5f78df7e105eb08da2950619dadf97dc1594",
    "contextbench/parsers/gold.py": "f3cb58c4ec443f78e68d4831a41e023091642c93279483195a707bae63c9842f",
    "contextbench/parsers/diff.py": "d3028286a3e96c4142eb81cdf934ba3ea6345975c8261b64fa7289011b31a162",
    "data/contextbench_verified.parquet": "e9dcfd504cbfb849ac815a79040c793d0d92f94eecc9b5a4ee3e1445a2f8a791",
    "LICENSE": "1eb85fc97224598dad1852b5d6483bbcf0aa8608790dcc657a5a2a761ae9c8c6",
    "contextbench/metrics/compute.py": "457dd5b03ef5b89b93f892fd4b45658cc9795600f7e13271c65e39657f2df358",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contextbench-root", type=Path, required=True)
    parser.add_argument("--cases-out", type=Path, required=True)
    parser.add_argument("--summary-out", type=Path, required=True)
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_source(root: Path) -> None:
    root = root.resolve()
    if not (root / ".git").is_dir():
        raise SystemExit(f"not a Git worktree: {root}")
    commit = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if commit != EXPECTED_COMMIT:
        raise SystemExit(f"unexpected ContextBench commit: {commit}")
    status = subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
            "--ignored=matching",
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    if status.strip():
        raise SystemExit("ContextBench worktree must contain only exact tracked files")
    for relative, expected in EXPECTED_FILES.items():
        path = root / relative
        actual = sha256(path)
        if actual != expected:
            raise SystemExit(f"sha256 mismatch for {relative}: {actual}")


def interval_size(values: dict[str, list[tuple[int, int]]]) -> int:
    return sum(end - start + 1 for ranges in values.values() for start, end in ranges)


def hit_size(
    prediction: dict[str, list[tuple[int, int]]],
    gold: dict[str, list[tuple[int, int]]],
) -> int:
    total = 0
    for file_path, ranges in prediction.items():
        targets = gold.get(file_path, [])
        for start, end in ranges:
            for line in range(start, end + 1):
                if any(gold_start <= line <= gold_end for gold_start, gold_end in targets):
                    total += 1
    return total


def flatten(values: dict[str, list[tuple[int, int]]]) -> list[dict[str, Any]]:
    return [
        {"file": file_path, "start": start, "end": end}
        for file_path in sorted(values)
        for start, end in values[file_path]
    ]


def main() -> int:
    args = parse_args()
    root = args.contextbench_root.resolve()
    verify_source(root)

    try:
        import pyarrow.parquet as parquet
    except ImportError as error:
        raise SystemExit("pyarrow is required; install the pinned project audit dependency") from error

    sys.path.insert(0, str(root))
    from contextbench.parsers.diff import parse_diff_lines
    from contextbench.parsers.gold import GoldLoader

    dataset_path = root / "data" / "contextbench_verified.parquet"
    rows = parquet.read_table(dataset_path).to_pylist()
    loader = GoldLoader(str(dataset_path))

    cases: list[dict[str, Any]] = []
    current_recalls: list[float] = []
    standard_recalls: list[float] = []
    mismatch_count = 0
    inflated_count = 0
    reported_one_standard_below_one = 0
    rows_without_deleted_lines = 0

    for row in rows:
        instance_id = row["instance_id"]
        gold = loader.get(instance_id)
        if gold is None:
            raise SystemExit(f"gold loader could not resolve {instance_id}")
        fallback_prediction = parse_diff_lines(row.get("patch") or "", deletions_only=True)
        prediction_size = interval_size(fallback_prediction)
        if prediction_size == 0:
            rows_without_deleted_lines += 1
            continue
        gold_intervals = gold.line_spans_init()
        gold_size = interval_size(gold_intervals)
        intersection = hit_size(fallback_prediction, gold_intervals)
        current_recall = intersection / prediction_size
        standard_recall = intersection / gold_size if gold_size else 1.0
        current_recalls.append(current_recall)
        standard_recalls.append(standard_recall)
        if abs(current_recall - standard_recall) > TOLERANCE:
            mismatch_count += 1
        if current_recall > standard_recall + TOLERANCE:
            inflated_count += 1
        if abs(current_recall - 1.0) <= TOLERANCE and standard_recall < 1.0 - TOLERANCE:
            reported_one_standard_below_one += 1

        cases.append(
            {
                "schema_version": "evalfence.case.v1",
                "case_id": instance_id,
                "prediction": {
                    "source": "gold.patch_fallback",
                    "input_present": False,
                    "intervals": flatten(fallback_prediction),
                },
                "gold": {
                    "source": "gold.init_ctx",
                    "input_present": True,
                    "intervals": flatten(gold_intervals),
                },
                "reported": {
                    "prediction_source": "gold.patch_fallback",
                    "pred_size": prediction_size,
                    "gold_size": gold_size,
                    "intersection": intersection,
                    "precision": current_recall,
                    "recall": current_recall,
                    "f1": None,
                },
                "policy": {
                    "allowed_prediction_sources": ["prediction.model_patch"],
                    "tolerance": TOLERANCE,
                },
            }
        )

    args.cases_out.parent.mkdir(parents=True, exist_ok=True)
    with args.cases_out.open("w", encoding="utf-8", newline="\n") as handle:
        for case in cases:
            handle.write(json.dumps(case, sort_keys=True, separators=(",", ":")) + "\n")

    summary = {
        "schema_version": "evalfence.contextbench-case-study.v1",
        "scope": {
            "upstream": "EuniAI/ContextBench",
            "commit": EXPECTED_COMMIT,
            "dataset": "data/contextbench_verified.parquet",
            "dataset_sha256": EXPECTED_FILES["data/contextbench_verified.parquet"],
            "evaluate_py_sha256": EXPECTED_FILES["contextbench/evaluate.py"],
            "gold_parser_sha256": EXPECTED_FILES["contextbench/parsers/gold.py"],
            "diff_parser_sha256": EXPECTED_FILES["contextbench/parsers/diff.py"],
            "metrics_compute_sha256": EXPECTED_FILES["contextbench/metrics/compute.py"],
            "license": "Apache-2.0",
            "pyarrow": importlib.metadata.version("pyarrow"),
            "tolerance": TOLERANCE,
        },
        "observations": {
            "dataset_rows": len(rows),
            "rows_without_deleted_patch_lines": rows_without_deleted_lines,
            "gold_fallback_cases_with_deleted_lines": len(cases),
            "per_instance_standard_recall_formula_mismatches": mismatch_count,
            "per_instance_record_recall_greater_than_standard": inflated_count,
            "per_instance_record_recall_one_standard_below_one": reported_one_standard_below_one,
            "mean_per_instance_record_recall": round(statistics.mean(current_recalls), 6),
            "mean_standard_set_recall_same_cases": round(statistics.mean(standard_recalls), 6),
            "median_positive_gap": round(
                statistics.median(
                    current - standard
                    for current, standard in zip(current_recalls, standard_recalls, strict=True)
                    if current > standard
                ),
                6,
            ),
            "max_positive_gap": round(
                max(
                    current - standard
                    for current, standard in zip(current_recalls, standard_recalls, strict=True)
                ),
                6,
            ),
        },
        "boundaries": [
            "This measures the exact public fallback and formula code paths against one public 500-row dataset.",
            "It does not establish whether any published leaderboard submission omitted model_patch.",
            "Standard set recall is intersection divided by gold size; it is not asserted to be the upstream authors' intended containment metric.",
            "The separate upstream aggregate path recomputes micro recall from total intersection and gold size; this audit does not claim aggregate or leaderboard impact.",
            "No model, harness, product, adoption, review, or production-quality claim follows from these observations.",
        ],
    }
    args.summary_out.parent.mkdir(parents=True, exist_ok=True)
    args.summary_out.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

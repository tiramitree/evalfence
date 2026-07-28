#!/usr/bin/env python3
"""Build a bounded keyed-manifest control from one exact SWE-bench revision.

The adapter inspects source syntax but does not import or execute SWE-bench,
Docker, a dataset, a model, or a network client. Generated cases contain one
synthetic public identifier and payload digests; no patch text is published.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

EXPECTED_COMMIT = "f7bbbb2ccdf479001d6467c9e34af59e44a840f9"
EXPECTED_FILES = {
    "swebench/harness/utils.py": "c21797d88ab640db8dea67838e2f1bd16d45ce3ddf3aedc5ac1965068bff3cae",
    "swebench/harness/run_evaluation.py": "6959f0b4e4eaf979771f529b88e3e9df1daa7fe86bc4291feec2e7d320bf7f2e",
    "swebench/harness/constants/__init__.py": "c12fe2671fd8b7d8af8f5c711fceb2ca684254e2c1b4cde448422a44b8d04e35",
    "docs/assets/evaluation.md": "1932e475a4ee2129664a9107ea162bdb15dfd65a40781068b382dbfdf2debda9",
    "LICENSE": "2bd2e08df7147f67a69b42c10efae09bd4bf119df397371036187d5dd1b02f57",
}
EXPECTED_EVALUATION_KEYS = {
    "KEY_INSTANCE_ID": "instance_id",
    "KEY_MODEL": "model_name_or_path",
    "KEY_PREDICTION": "model_patch",
}
SYNTHETIC_ID = "example__repo-1"
EXPECTED_CODES = [
    "EF202_DUPLICATE_RECORD_ID",
    "EF203_CONFLICTING_DUPLICATE_PAYLOAD",
    "EF208_ORDER_DEPENDENT_COLLAPSE",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--swebench-root", type=Path, required=True)
    parser.add_argument("--evalfence-bin", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def write_canonical(path: Path, value: Any) -> None:
    path.write_bytes(canonical_bytes(value) + b"\n")


def verify_checked_out_file(root: Path, relative: str, expected: str) -> bytes:
    blob = subprocess.run(
        ["git", "-C", str(root), "cat-file", "blob", f"HEAD:{relative}"],
        check=True,
        capture_output=True,
    ).stdout
    actual = sha256_bytes(blob)
    if actual != expected:
        raise SystemExit(f"sha256 mismatch for Git blob {relative}: {actual}")
    path = root / relative
    if not path.is_file() or path.is_symlink():
        raise SystemExit(f"expected a regular checked-out file: {relative}")
    worktree = path.read_bytes()
    if worktree not in (blob, blob.replace(b"\n", b"\r\n")):
        raise SystemExit(
            f"checked-out bytes for {relative} differ beyond line-ending translation"
        )
    return blob


def verify_source(root: Path) -> dict[str, bytes]:
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
        raise SystemExit(f"unexpected SWE-bench commit: {commit}")
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
        raise SystemExit("SWE-bench worktree must contain only exact tracked files")
    return {
        relative: verify_checked_out_file(root, relative, expected)
        for relative, expected in EXPECTED_FILES.items()
    }


def named_function(module: ast.Module, name: str) -> ast.FunctionDef:
    matches = [
        node
        for node in module.body
        if isinstance(node, ast.FunctionDef) and node.name == name
    ]
    if len(matches) != 1:
        raise SystemExit(f"expected one function named {name}")
    return matches[0]


def verify_evaluation_keys(source: bytes) -> dict[str, str]:
    module = ast.parse(source.decode("utf-8"))
    observed: dict[str, str] = {}
    for node in module.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name) or target.id not in EXPECTED_EVALUATION_KEYS:
            continue
        if target.id in observed:
            raise SystemExit(f"duplicate registered evaluation key: {target.id}")
        if not isinstance(node.value, ast.Constant) or not isinstance(
            node.value.value, str
        ):
            raise SystemExit(f"registered evaluation key is not a string: {target.id}")
        observed[target.id] = node.value.value
    if observed != EXPECTED_EVALUATION_KEYS:
        raise SystemExit("registered SWE-bench evaluation-key constants changed")
    return observed


def verify_loader_shape(source: bytes) -> dict[str, int]:
    module = ast.parse(source.decode("utf-8"))
    function = named_function(module, "get_predictions_from_file")
    id_presence_checks = [
        node
        for node in ast.walk(function)
        if isinstance(node, ast.Compare)
        and len(node.ops) == 1
        and isinstance(node.ops[0], ast.NotIn)
        and isinstance(node.left, ast.Name)
        and node.left.id == "KEY_INSTANCE_ID"
        and len(node.comparators) == 1
        and isinstance(node.comparators[0], ast.Name)
        and node.comparators[0].id == "pred"
    ]
    suffixes = {
        constant.value
        for constant in ast.walk(function)
        if isinstance(constant, ast.Constant)
        and constant.value in {".json", ".jsonl"}
    }
    if len(id_presence_checks) != 1 or suffixes != {".json", ".jsonl"}:
        raise SystemExit("registered SWE-bench prediction-loader syntax changed")
    return {
        "instance_id_presence_checks": len(id_presence_checks),
        "accepted_file_suffixes": len(suffixes),
    }


def is_registered_dict_collapse(node: ast.AST) -> bool:
    if not isinstance(node, ast.DictComp) or len(node.generators) != 1:
        return False
    generator = node.generators[0]
    return (
        not generator.ifs
        and generator.is_async == 0
        and isinstance(generator.target, ast.Name)
        and generator.target.id == "pred"
        and isinstance(generator.iter, ast.Name)
        and generator.iter.id == "predictions"
        and isinstance(node.key, ast.Subscript)
        and isinstance(node.key.value, ast.Name)
        and node.key.value.id == "pred"
        and isinstance(node.key.slice, ast.Name)
        and node.key.slice.id == "KEY_INSTANCE_ID"
        and isinstance(node.value, ast.Name)
        and node.value.id == "pred"
    )


def verify_consumer_shape(source: bytes) -> dict[str, int]:
    module = ast.parse(source.decode("utf-8"))
    function = named_function(module, "main")
    loader_assignments = 0
    collapse_assignments = 0
    for node in ast.walk(function):
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == "predictions"
        ):
            if (
                isinstance(node.value, ast.Call)
                and isinstance(node.value.func, ast.Name)
                and node.value.func.id == "get_predictions_from_file"
            ):
                loader_assignments += 1
            if is_registered_dict_collapse(node.value):
                collapse_assignments += 1
    if loader_assignments != 1 or collapse_assignments != 1:
        raise SystemExit("registered SWE-bench prediction-consumer syntax changed")
    return {
        "loader_assignments": loader_assignments,
        "last_write_wins_dict_comprehensions": collapse_assignments,
    }


def verify_documented_boundary(source: bytes) -> dict[str, bool]:
    text = source.decode("utf-8")
    result = {
        "documents_unique_task_instance_id": '"instance_id": "<Unique task instance ID>"'
        in text,
        "documents_partial_predictions_allowed": (
            "It is not necessary to generate predictions for every task instance."
            in text
        ),
    }
    if not all(result.values()):
        raise SystemExit("registered SWE-bench prediction documentation changed")
    return result


def payload_digest(prediction: dict[str, str], instance_id_key: str) -> str:
    payload = {
        key: value for key, value in prediction.items() if key != instance_id_key
    }
    return sha256_bytes(canonical_bytes(payload))


def build_case(
    case_id: str, records: list[dict[str, str]], instance_id_key: str
) -> dict[str, Any]:
    return {
        "schema_version": "evalfence.keyed-manifest.v1",
        "case_id": case_id,
        "records": [
            {
                "id": prediction[instance_id_key],
                "payload_sha256": payload_digest(prediction, instance_id_key),
            }
            for prediction in records
        ],
        "reported": {
            "record_count": len(records),
            "unique_id_count": len(
                {prediction[instance_id_key] for prediction in records}
            ),
        },
        "policy": {
            "allowed_ids": [SYNTHETIC_ID],
            "required_ids": [],
            "consumer_collision_policy": "last_write_wins",
        },
    }


def run_evalfence(binary: Path, case_path: Path, report_path: Path) -> dict[str, Any]:
    completed = subprocess.run(
        [
            str(binary),
            "audit-manifest",
            "--input",
            str(case_path),
            "--output",
            str(report_path),
        ],
        check=False,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if completed.returncode != 2:
        raise SystemExit(
            f"EvalFence returned {completed.returncode}, expected registered findings"
        )
    if completed.stdout or completed.stderr:
        raise SystemExit("EvalFence emitted unexpected process output")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    codes = [violation["code"] for violation in report["violations"]]
    if codes != EXPECTED_CODES:
        raise SystemExit(f"unexpected EvalFence finding codes: {codes}")
    if SYNTHETIC_ID in report_path.read_text(encoding="utf-8"):
        raise SystemExit("EvalFence report exposed the synthetic record identifier")
    return report


def survivor_digest(
    records: list[dict[str, str]], instance_id_key: str
) -> str:
    collapsed = {prediction[instance_id_key]: prediction for prediction in records}
    if set(collapsed) != {SYNTHETIC_ID}:
        raise SystemExit("synthetic last-write-wins control did not collapse to one id")
    return payload_digest(collapsed[SYNTHETIC_ID], instance_id_key)


def main() -> int:
    args = parse_args()
    root = args.swebench_root.resolve()
    binary = args.evalfence_bin.resolve()
    output = args.output_dir.resolve()
    if not binary.is_file() or binary.is_symlink():
        raise SystemExit("evalfence binary is not one regular file")
    if os.path.lexists(output):
        raise SystemExit("output directory must start absent")
    output.parent.mkdir(parents=True, exist_ok=True)

    blobs = verify_source(root)
    evaluation_keys = verify_evaluation_keys(
        blobs["swebench/harness/constants/__init__.py"]
    )
    loader_shape = verify_loader_shape(blobs["swebench/harness/utils.py"])
    consumer_shape = verify_consumer_shape(
        blobs["swebench/harness/run_evaluation.py"]
    )
    documentation = verify_documented_boundary(blobs["docs/assets/evaluation.md"])

    instance_id_key = evaluation_keys["KEY_INSTANCE_ID"]
    model_key = evaluation_keys["KEY_MODEL"]
    prediction_key = evaluation_keys["KEY_PREDICTION"]
    first = {
        instance_id_key: SYNTHETIC_ID,
        model_key: "synthetic-control",
        prediction_key: "first-payload",
    }
    second = {
        instance_id_key: SYNTHETIC_ID,
        model_key: "synthetic-control",
        prediction_key: "second-payload",
    }
    forward = [first, second]
    reverse = [second, first]

    with tempfile.TemporaryDirectory(
        prefix=".swebench-manifest-", dir=output.parent
    ) as temporary:
        staging = Path(temporary) / output.name
        staging.mkdir()
        forward_case = staging / "forward-case.json"
        reverse_case = staging / "reverse-case.json"
        forward_report = staging / "forward-report.json"
        reverse_report = staging / "reverse-report.json"
        write_canonical(
            forward_case,
            build_case("swebench-order-control-forward", forward, instance_id_key),
        )
        write_canonical(
            reverse_case,
            build_case("swebench-order-control-reverse", reverse, instance_id_key),
        )
        forward_result = run_evalfence(binary, forward_case, forward_report)
        reverse_result = run_evalfence(binary, reverse_case, reverse_report)

        forward_survivor = survivor_digest(forward, instance_id_key)
        reverse_survivor = survivor_digest(reverse, instance_id_key)
        if forward_survivor == reverse_survivor:
            raise SystemExit("reversing the synthetic records did not change survivor")
        if (
            forward_result["collapse_witnesses"][0][
                "last_record_payload_sha256"
            ]
            != forward_survivor
            or reverse_result["collapse_witnesses"][0][
                "last_record_payload_sha256"
            ]
            != reverse_survivor
        ):
            raise SystemExit("EvalFence survivor evidence differs from source semantics")

        summary = {
            "schema_version": "evalfence.swebench-manifest-case-study.v1",
            "scope": {
                "upstream": "SWE-bench/SWE-bench",
                "commit": EXPECTED_COMMIT,
                "license": "MIT",
                "files_sha256": EXPECTED_FILES,
                "evaluation_keys": evaluation_keys,
                "loader_shape": loader_shape,
                "consumer_shape": consumer_shape,
                "documentation": documentation,
            },
            "observations": {
                "synthetic_record_count": 2,
                "synthetic_unique_id_count": 1,
                "synthetic_distinct_payload_count": 2,
                "forward_survivor_sha256": forward_survivor,
                "reverse_survivor_sha256": reverse_survivor,
                "survivor_changes_when_input_order_reverses": True,
                "forward_finding_codes": EXPECTED_CODES,
                "reverse_finding_codes": EXPECTED_CODES,
                "reports_expose_record_ids": False,
            },
            "boundaries": [
                "The source-bound observation covers one exact public SWE-bench revision and two synthetic records.",
                "The adapter inspects source syntax and simulates the exact keyed-dictionary collapse; it does not import or execute SWE-bench.",
                "The control does not run Docker, a dataset, a model, an API, a leaderboard submission, or a paid service.",
                "It does not establish that any real prediction file contains duplicates or that any published score changed.",
                "It does not claim a SWE-bench defect, nonconformance, endorsement, adoption, or external review.",
            ],
        }
        write_canonical(staging / "summary.json", summary)
        staging.rename(output)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

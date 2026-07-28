#!/usr/bin/env python3
"""Verify the bounded STATE-Bench custom-agent boundary case study."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from statebench_boundary_audit import (
    EXPECTED_COMMIT,
    EXPECTED_CONTEXT_COUNTS,
    EXPECTED_DOMAINS,
    EXPECTED_EVENTS,
    EXPECTED_FILES,
    EXPECTED_PACKAGE_VERSION,
    EXPECTED_PROTOCOL_ID,
    EXPECTED_WRITE_COUNTS,
    REGISTERED_TASK_ID,
    canonical_bytes,
)

EXPECTED_INPUTS = {
    "task_id": ("runtime_metadata", 3, False),
    "user_id": ("runtime_metadata", 3, False),
    "domain": ("runtime_metadata", 3, False),
    "now": ("runtime_metadata", 3, False),
    "task_summary": ("task_oracle", 3, False),
    "state_requirements": ("scoring_oracle", 14, True),
    "task_requirements": ("scoring_oracle", 9, True),
}
EXPECTED_CALCULATED = {
    "input_count": 7,
    "present_input_count": 7,
    "oracle_input_count": 3,
    "unapproved_input_count": 0,
    "mutable_source_alias_count": 2,
    "capability_group_count": 3,
    "live_write_callable_count": 20,
    "unmediated_write_callable_count": 20,
    "prebaseline_constructor_count": 1,
}
EXPECTED_CODE_COUNTS = {
    "EF301_ORACLE_INPUT_EXPOSED": 3,
    "EF303_UNMEDIATED_WRITE_CAPABILITY": 3,
    "EF304_AGENT_CODE_BEFORE_BASELINE": 1,
    "EF305_MUTABLE_SOURCE_ALIAS": 2,
}
DENIED_KEYS = {
    "assistant_messages",
    "conversation",
    "environment_data",
    "opening_message",
    "prompt_text",
    "reasoning",
    "source_content",
    "state_diff",
    "task_requirements_payload",
    "task_summary_text",
    "trajectory",
}
DENIED_VALUE_PATTERNS = [
    re.compile(r"(?<![A-Za-z])[A-Za-z]:[\\/]"),
    re.compile(r"/(?:home|Users)/[^\s\"']+"),
    re.compile(
        r"(?<![A-Za-z0-9._%+-])[A-Za-z0-9._%+-]+"
        r"@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"
    ),
    re.compile(r"\b(?:10(?:\.\d{1,3}){3}|192\.168(?:\.\d{1,3}){2})\b"),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--case", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    return parser.parse_args()


def load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"{path.name} must contain one JSON object")
    return value


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"statebench-case-study verification failed: {message}")


def is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def audit_public_shape(value: Any, location: str = "$") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            require(isinstance(key, str), f"non-string key at {location}")
            require(key not in DENIED_KEYS, f"raw-content key {key!r} at {location}")
            audit_public_shape(item, f"{location}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            audit_public_shape(item, f"{location}[{index}]")
    elif isinstance(value, str):
        require(len(value) <= 256, f"oversized string at {location}")
        require("\r" not in value and "\n" not in value, f"multiline string at {location}")
        for pattern in DENIED_VALUE_PATTERNS:
            require(not pattern.search(value), f"private-data pattern at {location}")


def verify_case(case: dict[str, Any]) -> None:
    require(
        case.get("schema_version") == "evalfence.agent-boundary.v1",
        "boundary case schema changed",
    )
    require(
        case.get("case_id") == "statebench-4efcbf2d-agent-boundary",
        "boundary case ID changed",
    )
    inputs = case.get("inputs")
    require(isinstance(inputs, list) and len(inputs) == 7, "input set changed")
    by_name = {
        item.get("name"): item
        for item in inputs
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    }
    require(set(by_name) == set(EXPECTED_INPUTS), "input names changed")
    for name, (classification, item_count, mutable_alias) in EXPECTED_INPUTS.items():
        item = by_name[name]
        require(item.get("classification") == classification, f"classification changed: {name}")
        require(item.get("present") is True, f"input absent: {name}")
        require(item.get("item_count") == item_count, f"item count changed: {name}")
        require(
            item.get("mutable_source_alias") is mutable_alias,
            f"alias declaration changed: {name}",
        )
        require(is_sha256(item.get("payload_sha256")), f"invalid payload hash: {name}")

    capabilities = case.get("capabilities")
    require(
        isinstance(capabilities, list) and len(capabilities) == 3,
        "capability set changed",
    )
    by_domain = {
        item.get("name", "").removesuffix(".write_handlers"): item
        for item in capabilities
        if isinstance(item, dict)
    }
    require(set(by_domain) == set(EXPECTED_DOMAINS), "capability domains changed")
    for domain, count in EXPECTED_WRITE_COUNTS.items():
        item = by_domain[domain]
        require(item.get("kind") == "write_handler", f"capability kind changed: {domain}")
        require(item.get("exposed_to_agent") is True, f"exposure changed: {domain}")
        require(item.get("total_count") == count, f"total count changed: {domain}")
        require(item.get("callable_count") == count, f"callable count changed: {domain}")
        require(item.get("mediated_count") == 0, f"mediation count changed: {domain}")

    require(
        case.get("construction_order")
        == {
            "baseline_snapshot_before_agent_constructor": False,
            "baseline_snapshot_before_first_agent_turn": True,
        },
        "construction order changed",
    )
    require(
        case.get("reported")
        == {
            "input_count": 7,
            "oracle_input_count": 3,
            "capability_group_count": 3,
            "unmediated_write_callable_count": 20,
        },
        "reported counts changed",
    )
    require(
        case.get("policy")
        == {
            "allowed_agent_inputs": ["task_id", "user_id", "domain", "now"],
            "forbid_oracle_inputs": True,
            "forbid_mutable_source_aliases": True,
            "require_write_capability_mediation": True,
            "require_baseline_before_agent_constructor": True,
        },
        "registered policy changed",
    )


def verify_summary(summary: dict[str, Any], case: dict[str, Any]) -> None:
    require(
        summary.get("schema_version")
        == "evalfence.statebench-case-study-summary.v1",
        "summary schema changed",
    )
    upstream = summary.get("upstream")
    require(isinstance(upstream, dict), "upstream registration missing")
    require(upstream.get("repository") == "microsoft/STATE-Bench", "repository changed")
    require(upstream.get("commit") == EXPECTED_COMMIT, "commit changed")
    require(upstream.get("package_version") == EXPECTED_PACKAGE_VERSION, "version changed")
    require(upstream.get("protocol_id") == EXPECTED_PROTOCOL_ID, "protocol changed")
    require(upstream.get("registered_file_count") == len(EXPECTED_FILES), "file count changed")
    require(upstream.get("registered_files") == EXPECTED_FILES, "source registry changed")

    require(
        summary.get("source_shape")
        == {
            "agent_runtime_required_field_count": 7,
            "base_agent_context_assignment_count": 1,
            "task_to_context_mapping_count": 3,
            "live_handler_constructor_argument_count": 1,
            "constructor_before_baseline_snapshot": True,
            "baseline_snapshot_before_first_agent_turn": True,
            "learning_track_oracle_statement_count": 2,
            "custom_client_ignore_handler_instruction_count": 1,
            "custom_client_context_metadata_description_count": 1,
        },
        "source-shape registration changed",
    )

    probe = summary.get("runtime_context_probe")
    require(isinstance(probe, dict), "runtime probe missing")
    require(probe.get("domain_count") == 3, "domain count changed")
    require(probe.get("state_requirement_item_count") == 14, "state count changed")
    require(probe.get("task_requirement_item_count") == 9, "task count changed")
    require(probe.get("write_handler_count") == 20, "write count changed")
    require(
        probe.get("constructor_before_baseline_in_all_domains") is True,
        "constructor/baseline relation changed",
    )
    require(
        probe.get("baseline_before_first_turn_in_all_domains") is True,
        "baseline/turn relation changed",
    )
    domains = probe.get("domains")
    require(
        isinstance(domains, list)
        and [item.get("domain") for item in domains] == EXPECTED_DOMAINS,
        "runtime domain observations changed",
    )
    for observation in domains:
        domain = observation["domain"]
        expected_counts = EXPECTED_CONTEXT_COUNTS[domain]
        require(observation.get("events") == EXPECTED_EVENTS, f"event order changed: {domain}")
        require(observation.get("task_summary_equal") is True, f"summary mapping changed: {domain}")
        require(
            observation.get("write_handler_count") == EXPECTED_WRITE_COUNTS[domain],
            f"write count changed: {domain}",
        )
        require(
            observation.get("callable_write_handler_count") == EXPECTED_WRITE_COUNTS[domain],
            f"callable write count changed: {domain}",
        )
        require(is_sha256(observation.get("task_key_sha256")), f"task hash invalid: {domain}")
        require(
            is_sha256(observation.get("write_handler_names_sha256")),
            f"handler hash invalid: {domain}",
        )
        for lane, expected in (
            ("state_requirements", expected_counts["state"]),
            ("task_requirements", expected_counts["task"]),
        ):
            boundary = observation.get(lane)
            require(isinstance(boundary, dict), f"{lane} missing: {domain}")
            require(boundary.get("item_count") == expected, f"{lane} count changed: {domain}")
            require(boundary.get("payload_equal") is True, f"{lane} payload changed: {domain}")
            require(
                boundary.get("mutable_source_alias") is True,
                f"{lane} alias changed: {domain}",
            )
            require(is_sha256(boundary.get("payload_sha256")), f"{lane} hash invalid: {domain}")

    causal = summary.get("causal_control")
    require(isinstance(causal, dict), "causal control missing")
    require(causal.get("registered_task_id") == REGISTERED_TASK_ID, "causal task changed")
    require(
        causal.get("unsafe_context_arm")
        == {
            "deterministic_state_score": 1,
            "tool_calls": 2,
            "tool_errors": 0,
            "state_diff_empty": False,
        },
        "unsafe causal arm changed",
    )
    require(
        causal.get("state_requirements_removed_control")
        == {
            "deterministic_state_score": 0,
            "tool_calls": 0,
            "tool_errors": 0,
            "state_diff_empty": True,
        },
        "state-requirements control changed",
    )
    require(causal.get("deterministic_state_score_delta") == 1, "causal delta changed")
    require(causal.get("protocol_compliant_run") is False, "protocol claim changed")
    require(causal.get("official_score_claimed") is False, "score claim changed")
    require(
        summary.get("api_boundary")
        == {
            "agent_client_calls": 0,
            "simulator_client_calls": 0,
            "judge_calls": 0,
        },
        "API boundary changed",
    )
    publication = summary.get("publication_boundary")
    require(
        isinstance(publication, dict)
        and publication
        and all(value is False for value in publication.values()),
        "publication boundary changed",
    )
    require(
        summary.get("boundary_case_sha256")
        == hashlib.sha256(canonical_bytes(case)).hexdigest(),
        "boundary case digest mismatch",
    )


def verify_report(report: dict[str, Any]) -> None:
    require(
        report.get("schema_version") == "evalfence.agent-boundary-report.v1",
        "report schema changed",
    )
    require(report.get("case_id") == "statebench-4efcbf2d-agent-boundary", "report case changed")
    require(report.get("passed") is False, "registered findings disappeared")
    require(report.get("calculated") == EXPECTED_CALCULATED, "calculated counts changed")
    violations = report.get("violations")
    require(isinstance(violations, list), "violations missing")
    code_counts: dict[str, int] = {}
    for violation in violations:
        require(isinstance(violation, dict), "invalid violation object")
        code = violation.get("code")
        require(isinstance(code, str), "violation code missing")
        code_counts[code] = code_counts.get(code, 0) + 1
    require(code_counts == EXPECTED_CODE_COUNTS, "registered finding counts changed")


def main() -> int:
    args = parse_args()
    summary = load_object(args.summary)
    case = load_object(args.case)
    report = load_object(args.report)
    for value in (summary, case, report):
        audit_public_shape(value)
    verify_case(case)
    verify_summary(summary, case)
    verify_report(report)
    print(
        "statebench-case-study: verified 3 domains, "
        "20 exposed write handlers, 9 registered findings"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Generate a bounded custom-agent boundary case from one exact STATE-Bench revision.

The adapter uses only the Python standard library. It imports the pinned public
benchmark behind an offline client stub, executes deterministic harness paths,
and emits no task text, requirement payload, environment payload, trajectory,
or source content.
"""

from __future__ import annotations

import argparse
import ast
import dataclasses
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import types
from pathlib import Path
from typing import Any

EXPECTED_COMMIT = "4efcbf2d4fe60df04878859b692d9391f3d5b33a"
EXPECTED_PACKAGE_VERSION = "0.8.1"
EXPECTED_PROTOCOL_ID = "state_bench_v0.8.1_gpt54"
EXPECTED_DOMAINS = ["travel", "customer_support", "shopping_assistant"]
REGISTERED_TASK_ID = "4-brand_bundle_missed"
REGISTERED_TASK_PATH = (
    "state_bench/domains/shopping_assistant/tasks/4-brand_bundle_missed.json"
)
REGISTERED_ENV_PATH = (
    "state_bench/domains/shopping_assistant/task_envs/"
    "4-brand_bundle_missed.json"
)

EXPECTED_FILES = {
    "state_bench/agents/base.py": {
        "git_blob_sha256": "da6465ac1bf381cfb3b315bd18589dd5b8247658f2c773499fc2d84be21ea153",
        "crlf_checkout_sha256": "20a87153b902c37966d270ea1b14b2ce829097f65e0791058a9dedfb05973cbb",
        "git_blob_id": "5fd22338a6e847ba25c1fa0cb3c553b703570f49",
    },
    "state_bench/orchestrator.py": {
        "git_blob_sha256": "50795142687841e9b470d4454e7f22b79c4d2b93a18786e87a61a88fe3d6c9a8",
        "crlf_checkout_sha256": "edac1a15e62b9b6c5accee905198ab3ebe994d31dc9a9c686131b1570c835d96",
        "git_blob_id": "5f0437cc536352f2408336ae86be56acf8c5b192",
    },
    "state_bench/scripts/run_batch.py": {
        "git_blob_sha256": "c062c775a9444b4a60c4ba82b1a024a5bc33f5f468061205147dba9f96d6a560",
        "crlf_checkout_sha256": "1836e7396107d4ef4b00a34f844f2297b9bb5a0932392bd086b98c3c74c4d14e",
        "git_blob_id": "cd58b538d6394211c959cc790d7c1388f65f9c43",
    },
    "state_bench/schemas.py": {
        "git_blob_sha256": "5fbadcfeba076542920aa6cb2e5e1295b20f75d905a196a1f62b61789c894f29",
        "crlf_checkout_sha256": "42527e548bd4b1e509cfedfc081d76f0f28e23de3a5dee1be26d33075ebf876b",
        "git_blob_id": "add69637ffa67b8d000124fc403dd08f02295dcf",
    },
    "docs/AGENT_LEARNING_TRACK.md": {
        "git_blob_sha256": "f111b5159d8842c4db210c7bbec1201880aace964dc69909d1fb38bd30ce8a0f",
        "crlf_checkout_sha256": "cb338d79489326f7eb6a7dd42dbdbf1f4ffac85297bf9de8f08e2ce2a8349251",
        "git_blob_id": "22148fe3f4e7d2275c28e502bdd5a17516d853ea",
    },
    "docs/USE_CUSTOM_CLIENT.md": {
        "git_blob_sha256": "92a1e09c1a55d9a9058c996cf3e30fde67a4c63096c92a0ce1a4e196ebd77d45",
        "crlf_checkout_sha256": "6f639f955a97d183f3a6fb9cc9b031bffd98e7732e9aa8defd85b6fbafb45585",
        "git_blob_id": "97bd45c53d5abaf5ba8cd964a6188bed55ab2255",
    },
    REGISTERED_TASK_PATH: {
        "git_blob_sha256": "ebb02885230511fb45e3450d4027604ad6acbd128fbfc936a593a39c2db01aeb",
        "crlf_checkout_sha256": "905c7b8c34daf72f38f8213ef898dac4a00e8366f5c40be7696f2e7e039ce267",
        "git_blob_id": "9d036d10cfeb0baf195e6202d65eacabe88d8164",
    },
    REGISTERED_ENV_PATH: {
        "git_blob_sha256": "82596ee03f2500bb38d35d23f0f302b77b5ccc6ee0364aaa703d78fca60db556",
        "crlf_checkout_sha256": "9ec500cbd4e1cb1d58fe6c2127bd79c5d7d93bf60c48f40974f7cf671f572778",
        "git_blob_id": "70ca2f91acdb970a50748280bc6af0c5da7d6ffd",
    },
    "LICENSE": {
        "git_blob_sha256": "2e969379b1a7eaeeefe741c576aa64e29099b9629b645e0e938bf2c88e7b5f0b",
        "crlf_checkout_sha256": "a6e337407113665041a928064a479586bb385443e313efb69ab410e46ace3ab6",
        "git_blob_id": "75c58b5c7f47bd4b0f9f64fec44379de9ad4a2bf",
    },
    "pyproject.toml": {
        "git_blob_sha256": "25813450621e1fec548b01932ae06870246131fd652c7d85bfa7507b440e7f8a",
        "crlf_checkout_sha256": "c65ee146cbff574950d225ce2fcfe498bcea0e578958a17a60cbc74578d5c5b5",
        "git_blob_id": "58d05ee222be8e516fa6ebb4bbd995354cffd305",
    },
}

EXPECTED_WRITE_COUNTS = {
    "travel": 7,
    "customer_support": 5,
    "shopping_assistant": 8,
}
EXPECTED_CONTEXT_COUNTS = {
    "travel": {"state": 4, "task": 2},
    "customer_support": {"state": 6, "task": 1},
    "shopping_assistant": {"state": 4, "task": 6},
}
EXPECTED_EVENTS = [
    "agent_constructor",
    "baseline_snapshot",
    "first_agent_turn",
    "final_snapshot",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--statebench-root", type=Path, required=True)
    parser.add_argument("--case-out", type=Path, required=True)
    parser.add_argument("--summary-out", type=Path, required=True)
    return parser.parse_args()


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def run_git(root: Path, *arguments: str, text: bool = True) -> str | bytes:
    result = subprocess.run(
        ["git", "-C", str(root), *arguments],
        check=True,
        capture_output=True,
        text=text,
    )
    return result.stdout


def verify_checked_out_file(
    root: Path,
    relative: str,
    expected_git_blob_sha256: str,
    expected_crlf_checkout_sha256: str,
    expected_git_blob_id: str,
) -> bytes:
    observed_blob = str(run_git(root, "rev-parse", f"HEAD:{relative}")).strip()
    if observed_blob != expected_git_blob_id:
        raise SystemExit(f"unexpected Git blob for registered file: {relative}")
    blob = run_git(root, "cat-file", "blob", f"HEAD:{relative}", text=False)
    if not isinstance(blob, bytes) or sha256_bytes(blob) != expected_git_blob_sha256:
        raise SystemExit(f"unexpected SHA-256 for registered file: {relative}")
    path = root / relative
    if not path.is_file() or path.is_symlink():
        raise SystemExit(f"expected a regular checked-out file: {relative}")
    worktree = path.read_bytes()
    if worktree not in (blob, blob.replace(b"\n", b"\r\n")):
        raise SystemExit(
            f"checked-out bytes differ beyond line-ending translation: {relative}"
        )
    if worktree != blob and sha256_bytes(worktree) != expected_crlf_checkout_sha256:
        raise SystemExit(
            f"unexpected CRLF checkout SHA-256 for registered file: {relative}"
        )
    return blob


def verify_source(root: Path) -> dict[str, bytes]:
    root = root.resolve()
    if not (root / ".git").is_dir():
        raise SystemExit("STATE-Bench root is not a Git worktree")
    commit = str(run_git(root, "rev-parse", "HEAD")).strip()
    if commit != EXPECTED_COMMIT:
        raise SystemExit(f"unexpected STATE-Bench commit: {commit}")
    status = str(
        run_git(
            root,
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
            "--ignored=matching",
        )
    )
    if status.strip():
        raise SystemExit(
            "STATE-Bench worktree must contain only exact tracked files"
        )
    return {
        relative: verify_checked_out_file(
            root,
            relative,
            registration["git_blob_sha256"],
            registration["crlf_checkout_sha256"],
            registration["git_blob_id"],
        )
        for relative, registration in EXPECTED_FILES.items()
    }


def named_class(module: ast.Module, name: str) -> ast.ClassDef:
    matches = [
        node
        for node in module.body
        if isinstance(node, ast.ClassDef) and node.name == name
    ]
    if len(matches) != 1:
        raise SystemExit(f"expected one class named {name}")
    return matches[0]


def named_method(node: ast.ClassDef, name: str) -> ast.FunctionDef:
    matches = [
        item
        for item in node.body
        if isinstance(item, ast.FunctionDef) and item.name == name
    ]
    if len(matches) != 1:
        raise SystemExit(f"expected one method named {node.name}.{name}")
    return matches[0]


def named_function(module: ast.Module, name: str) -> ast.FunctionDef:
    matches = [
        node
        for node in module.body
        if isinstance(node, ast.FunctionDef) and node.name == name
    ]
    if len(matches) != 1:
        raise SystemExit(f"expected one function named {name}")
    return matches[0]


def class_fields(node: ast.ClassDef) -> set[str]:
    return {
        item.target.id
        for item in node.body
        if isinstance(item, ast.AnnAssign)
        and isinstance(item.target, ast.Name)
    }


def is_attribute(node: ast.AST, owner: str, field: str) -> bool:
    return (
        isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == owner
        and node.attr == field
    )


def verify_source_shape(files: dict[str, bytes]) -> dict[str, Any]:
    base_module = ast.parse(
        files["state_bench/agents/base.py"].decode("utf-8")
    )
    context_class = named_class(base_module, "AgentRuntimeContext")
    required_context_fields = {
        "task_id",
        "user_id",
        "domain",
        "now",
        "task_summary",
        "state_requirements",
        "task_requirements",
    }
    if not required_context_fields.issubset(class_fields(context_class)):
        raise SystemExit("registered AgentRuntimeContext fields changed")

    base_agent = named_class(base_module, "BaseAgent")
    base_init = named_method(base_agent, "__init__")
    context_assignments = [
        node
        for node in ast.walk(base_init)
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and is_attribute(node.targets[0], "self", "runtime_context")
        and isinstance(node.value, ast.Name)
        and node.value.id == "runtime_context"
    ]
    if len(context_assignments) != 1:
        raise SystemExit("registered BaseAgent runtime-context storage changed")

    schemas_module = ast.parse(files["state_bench/schemas.py"].decode("utf-8"))
    task_definition = named_class(schemas_module, "TaskDefinition")
    task_fields = class_fields(task_definition)
    required_task_fields = {
        "task_summary",
        "state_requirements",
        "task_requirements",
    }
    if not required_task_fields.issubset(task_fields):
        raise SystemExit("registered TaskDefinition fields changed")

    orchestrator_module = ast.parse(
        files["state_bench/orchestrator.py"].decode("utf-8")
    )
    run_task = named_function(orchestrator_module, "run_task")
    context_calls = [
        node
        for node in ast.walk(run_task)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "AgentRuntimeContext"
    ]
    if len(context_calls) != 1:
        raise SystemExit("registered AgentRuntimeContext construction changed")
    context_call = context_calls[0]
    keyword_values = {
        keyword.arg: keyword.value
        for keyword in context_call.keywords
        if keyword.arg is not None
    }
    for field in ("task_summary", "state_requirements", "task_requirements"):
        if not is_attribute(keyword_values.get(field), "task", field):
            raise SystemExit(f"registered task-to-context mapping changed: {field}")

    kwargs_bindings = [
        node
        for node in ast.walk(run_task)
        if isinstance(node, ast.AnnAssign)
        and isinstance(node.target, ast.Name)
        and node.target.id == "agent_kwargs"
        and isinstance(node.value, ast.Dict)
    ]
    if len(kwargs_bindings) != 1:
        raise SystemExit("registered custom-agent kwargs construction changed")
    kwargs_dict = kwargs_bindings[0].value
    kwargs_pairs = {
        key.value: value
        for key, value in zip(kwargs_dict.keys, kwargs_dict.values, strict=True)
        if isinstance(key, ast.Constant) and isinstance(key.value, str)
    }
    runtime_value = kwargs_pairs.get("runtime_context")
    if not isinstance(runtime_value, ast.Name) or runtime_value.id != "runtime_context":
        raise SystemExit("registered runtime_context forwarding changed")

    constructor_assignments = [
        node
        for node in ast.walk(run_task)
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id == "agent"
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Name)
        and node.value.func.id == "resolved_agent_class"
    ]
    if len(constructor_assignments) != 1:
        raise SystemExit("registered custom-agent constructor changed")
    constructor = constructor_assignments[0]
    constructor_call = constructor.value
    if len(constructor_call.args) < 4 or not is_attribute(
        constructor_call.args[3], "env", "tool_handlers"
    ):
        raise SystemExit("registered live handler forwarding changed")
    unpacked_kwargs = [
        keyword.value
        for keyword in constructor_call.keywords
        if keyword.arg is None
        and isinstance(keyword.value, ast.Name)
        and keyword.value.id == "agent_kwargs"
    ]
    if len(unpacked_kwargs) != 1:
        raise SystemExit("registered agent_kwargs forwarding changed")

    snapshot_calls = sorted(
        (
            node
            for node in ast.walk(run_task)
            if isinstance(node, ast.Call)
            and is_attribute(node.func, "env", "get_full_snapshot")
        ),
        key=lambda node: node.lineno,
    )
    if len(snapshot_calls) != 2:
        raise SystemExit("registered environment snapshot calls changed")
    first_agent_turn_calls = sorted(
        (
            node
            for node in ast.walk(run_task)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "agent"
            and node.func.attr in {"uses_harness_tool_execution", "act"}
        ),
        key=lambda node: node.lineno,
    )
    if not first_agent_turn_calls:
        raise SystemExit("registered agent-turn path changed")
    if not (
        constructor.lineno
        < snapshot_calls[0].lineno
        < first_agent_turn_calls[0].lineno
        < snapshot_calls[1].lineno
    ):
        raise SystemExit("registered constructor/snapshot/turn order changed")

    learning_doc = files["docs/AGENT_LEARNING_TRACK.md"].decode("utf-8")
    custom_doc = files["docs/USE_CUSTOM_CLIENT.md"].decode("utf-8")
    learning_oracle_statements = learning_doc.count(
        "oracle inputs"
    )
    ignore_handler_instructions = custom_doc.count(
        "should ignore this argument"
    )
    context_metadata_descriptions = custom_doc.count(
        "carrying task metadata"
    )
    if (
        learning_oracle_statements != 2
        or ignore_handler_instructions != 1
        or context_metadata_descriptions != 1
    ):
        raise SystemExit("registered custom-agent documentation shape changed")

    return {
        "agent_runtime_required_field_count": len(required_context_fields),
        "base_agent_context_assignment_count": len(context_assignments),
        "task_to_context_mapping_count": 3,
        "live_handler_constructor_argument_count": 1,
        "constructor_before_baseline_snapshot": True,
        "baseline_snapshot_before_first_agent_turn": True,
        "learning_track_oracle_statement_count": learning_oracle_statements,
        "custom_client_ignore_handler_instruction_count": (
            ignore_handler_instructions
        ),
        "custom_client_context_metadata_description_count": (
            context_metadata_descriptions
        ),
    }


def install_offline_client_stub(
    upstream_root: Path,
) -> tuple[type[Any], dict[str, int]]:
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(upstream_root))
    counters = {
        "agent_client_calls": 0,
        "simulator_client_calls": 0,
        "judge_calls": 0,
    }
    client_module = types.ModuleType("state_bench.client")

    class BaseLLMClient:
        def __init__(self, lane: str = "agent") -> None:
            self.lane = lane

        def complete_chat(self, *_args: Any, **_kwargs: Any) -> str:
            key = (
                "simulator_client_calls"
                if self.lane == "simulator"
                else "agent_client_calls"
            )
            counters[key] += 1
            raise RuntimeError("network-backed client calls are disabled")

        def respond(self, *_args: Any, **_kwargs: Any) -> Any:
            key = (
                "simulator_client_calls"
                if self.lane == "simulator"
                else "agent_client_calls"
            )
            counters[key] += 1
            raise RuntimeError("network-backed client calls are disabled")

    class LLMClient(BaseLLMClient):
        pass

    class PooledLLMClient(BaseLLMClient):
        pass

    client_module.BaseLLMClient = BaseLLMClient
    client_module.LLMClient = LLMClient
    client_module.PooledLLMClient = PooledLLMClient
    sys.modules["state_bench.client"] = client_module
    return BaseLLMClient, counters


class OfflineSimulator:
    def __init__(self, _client: Any, _system_prompt: str) -> None:
        pass

    def respond(self, _conversation: list[dict[str, Any]]) -> str:
        return "[TASK_DONE]"


class SnapshotLoggingEnvironment:
    def __init__(self, inner: Any, events: list[str]) -> None:
        self.inner = inner
        self.events = events
        self.snapshot_count = 0

    @property
    def tool_handlers(self) -> dict[str, Any]:
        return self.inner.tool_handlers

    def get_full_snapshot(self) -> dict[str, Any]:
        self.snapshot_count += 1
        self.events.append(
            "baseline_snapshot"
            if self.snapshot_count == 1
            else "final_snapshot"
        )
        return self.inner.get_full_snapshot()


def hashed_sequence(values: list[Any]) -> str:
    return canonical_sha256([canonical_sha256(value) for value in values])


def run_context_probe(
    upstream_root: Path,
    offline_client_class: type[Any],
    counters: dict[str, int],
) -> tuple[list[dict[str, Any]], dict[str, list[Any]]]:
    from state_bench.agents.base import AgentTurnResponse, BaseAgent
    from state_bench.domain import get_domain_config
    from state_bench.env_loader import load_task_environment
    from state_bench.orchestrator import run_task
    from state_bench.paths import domain_tasks_dir
    from state_bench.protocol import load_default_protocol, load_split_task_ids
    from state_bench.schemas import TaskDefinition
    from state_bench.version import get_package_version
    import state_bench.orchestrator as orchestrator_module

    orchestrator_module.UserSimulator = OfflineSimulator
    protocol = load_default_protocol()
    if get_package_version() != EXPECTED_PACKAGE_VERSION:
        raise SystemExit("unexpected imported STATE-Bench package version")
    if protocol.protocol_id != EXPECTED_PROTOCOL_ID:
        raise SystemExit("unexpected STATE-Bench evaluation protocol")
    if protocol.domains != EXPECTED_DOMAINS:
        raise SystemExit("unexpected STATE-Bench protocol domain order")

    materials: dict[str, list[Any]] = {
        "task_id": [],
        "user_id": [],
        "domain": [],
        "now": [],
        "task_summary": [],
        "state_requirements": [],
        "task_requirements": [],
    }
    observations: list[dict[str, Any]] = []

    for domain_name in protocol.domains:
        domain = get_domain_config(domain_name)
        task_id = load_split_task_ids(
            domain_name,
            protocol.split,
            protocol.split_version,
        )[0]
        task = TaskDefinition.load(
            domain_tasks_dir(domain_name) / f"{task_id}.json"
        )
        env_data, _ = load_task_environment(domain, task)
        events: list[str] = []
        capture: dict[str, Any] = {}

        class ContextCaptureAgent(BaseAgent):
            def __init__(
                self,
                client: Any,
                system_prompt: str,
                tools: list[dict[str, Any]],
                tool_handlers: dict[str, Any],
                runtime_context: Any = None,
                **_kwargs: Any,
            ) -> None:
                del client, system_prompt, tools
                events.append("agent_constructor")
                super().__init__(runtime_context=runtime_context)
                capture["context"] = runtime_context
                capture["handler_names"] = sorted(tool_handlers)
                capture["callable_handler_names"] = sorted(
                    name
                    for name, handler in tool_handlers.items()
                    if callable(handler)
                )

            def generate_next_turn(
                self,
                *,
                system_prompt: str,
                conversation: list[dict[str, Any]],
                tools: list[dict[str, Any]],
            ) -> Any:
                del system_prompt, conversation, tools
                if "first_agent_turn" not in events:
                    events.append("first_agent_turn")
                return AgentTurnResponse(text="offline boundary observation")

        inner_env = domain.environment_class(
            env_data.deep_copy(),
            now=task.now,
        )
        logging_env = SnapshotLoggingEnvironment(inner_env, events)
        run_task(
            task=task,
            env_data=env_data,
            user_id=task.user_id,
            client=offline_client_class("agent"),
            domain=domain,
            simulator_client=offline_client_class("simulator"),
            agent_class=ContextCaptureAgent,
            env=logging_env,
        )
        context = capture["context"]
        write_names = sorted(domain.write_tool_names)
        handler_names = capture["handler_names"]
        callable_handler_names = capture["callable_handler_names"]
        callable_write_names = sorted(set(write_names) & set(callable_handler_names))

        expected_counts = EXPECTED_CONTEXT_COUNTS[domain_name]
        conditions = {
            "task_summary_equal": context.task_summary == task.task_summary,
            "state_payload_equal": (
                canonical_sha256(context.state_requirements)
                == canonical_sha256(task.state_requirements)
            ),
            "task_payload_equal": (
                canonical_sha256(context.task_requirements)
                == canonical_sha256(task.task_requirements)
            ),
            "state_mutable_alias": (
                context.state_requirements is task.state_requirements
            ),
            "task_mutable_alias": (
                context.task_requirements is task.task_requirements
            ),
            "all_handlers_received": set(handler_names)
            == set(inner_env.tool_handlers),
            "all_write_handlers_callable": callable_write_names == write_names,
            "registered_event_order": events == EXPECTED_EVENTS,
        }
        if not all(conditions.values()):
            raise SystemExit(
                f"runtime boundary observation changed for {domain_name}"
            )
        if (
            len(task.state_requirements) != expected_counts["state"]
            or len(task.task_requirements) != expected_counts["task"]
            or len(write_names) != EXPECTED_WRITE_COUNTS[domain_name]
        ):
            raise SystemExit(
                f"registered runtime counts changed for {domain_name}"
            )

        observations.append(
            {
                "domain": domain_name,
                "task_key_sha256": sha256_bytes(task.task_id.encode("utf-8")),
                "task_summary_equal": conditions["task_summary_equal"],
                "state_requirements": {
                    "item_count": len(task.state_requirements),
                    "payload_equal": conditions["state_payload_equal"],
                    "mutable_source_alias": conditions["state_mutable_alias"],
                    "payload_sha256": canonical_sha256(
                        task.state_requirements
                    ),
                },
                "task_requirements": {
                    "item_count": len(task.task_requirements),
                    "payload_equal": conditions["task_payload_equal"],
                    "mutable_source_alias": conditions["task_mutable_alias"],
                    "payload_sha256": canonical_sha256(
                        task.task_requirements
                    ),
                },
                "constructor_handler_count": len(handler_names),
                "write_handler_count": len(write_names),
                "callable_write_handler_count": len(callable_write_names),
                "write_handler_names_sha256": canonical_sha256(write_names),
                "events": events,
            }
        )
        materials["task_id"].append(task.task_id)
        materials["user_id"].append(task.user_id)
        materials["domain"].append(domain_name)
        materials["now"].append(task.now)
        materials["task_summary"].append(task.task_summary)
        materials["state_requirements"].append(task.state_requirements)
        materials["task_requirements"].append(task.task_requirements)

    if counters != {
        "agent_client_calls": 0,
        "simulator_client_calls": 0,
        "judge_calls": 0,
    }:
        raise SystemExit("offline context probe attempted an API-backed call")
    return observations, materials


def run_causal_control(
    offline_client_class: type[Any],
    counters: dict[str, int],
) -> dict[str, Any]:
    from state_bench.agents.base import AgentTurnResponse, BaseAgent
    from state_bench.domain import get_domain_config
    from state_bench.env_loader import load_task_environment
    from state_bench.orchestrator import run_task
    from state_bench.paths import domain_tasks_dir
    from state_bench.schemas import TaskDefinition
    from state_bench.scoring import evaluate_state_requirements
    import state_bench.orchestrator as orchestrator_module

    orchestrator_module.UserSimulator = OfflineSimulator

    def tool_round_seen(conversation: list[dict[str, Any]]) -> bool:
        return any(message.get("role") == "tool" for message in conversation)

    class ContextOnlyOracleAgent(BaseAgent):
        def __init__(
            self,
            client: Any,
            system_prompt: str,
            tools: list[dict[str, Any]],
            tool_handlers: dict[str, Any],
            runtime_context: Any = None,
            **_kwargs: Any,
        ) -> None:
            del client, system_prompt, tools, tool_handlers
            super().__init__(runtime_context=runtime_context)

        def generate_next_turn(
            self,
            *,
            system_prompt: str,
            conversation: list[dict[str, Any]],
            tools: list[dict[str, Any]],
        ) -> Any:
            del system_prompt, tools
            if not tool_round_seen(conversation):
                requests = []
                for requirement in self.runtime_context.state_requirements:
                    if requirement.get("entity_type") != "cart_items":
                        continue
                    fields = requirement.get("match_fields") or {}
                    requests.append(
                        {
                            "name": "add_to_cart",
                            "arguments": {
                                "customer_id": fields["customer_id"],
                                "product_id": fields["product_id"],
                                "quantity": fields["quantity"],
                                "gift_wrap": fields["gift_wrap"],
                            },
                        }
                    )
                return AgentTurnResponse(
                    text="applying context-bound state requirements",
                    tool_calls=requests,
                )
            response_key = canonical_sha256(
                self.runtime_context.task_requirements
            )[:16]
            return AgentTurnResponse(
                text=f"context-bound completion {response_key}"
            )

    class StateRequirementsRemovedAgent(ContextOnlyOracleAgent):
        def __init__(
            self,
            client: Any,
            system_prompt: str,
            tools: list[dict[str, Any]],
            tool_handlers: dict[str, Any],
            runtime_context: Any = None,
            **_kwargs: Any,
        ) -> None:
            del client, system_prompt, tools, tool_handlers
            clean_context = dataclasses.replace(
                runtime_context,
                state_requirements=[],
            )
            BaseAgent.__init__(self, runtime_context=clean_context)

    def run_arm(agent_class: type[Any]) -> dict[str, Any]:
        domain = get_domain_config("shopping_assistant")
        task = TaskDefinition.load(
            domain_tasks_dir("shopping_assistant")
            / f"{REGISTERED_TASK_ID}.json"
        )
        env_data, _ = load_task_environment(domain, task)
        trajectory = run_task(
            task=task,
            env_data=env_data,
            user_id=task.user_id,
            client=offline_client_class("agent"),
            domain=domain,
            simulator_client=offline_client_class("simulator"),
            agent_class=agent_class,
        )
        state_score = evaluate_state_requirements(
            task,
            trajectory.state_diff,
        )
        if state_score is None:
            raise SystemExit("registered deterministic state score is absent")
        return {
            "deterministic_state_score": int(state_score.score),
            "tool_calls": int(trajectory.efficiency.tool_calls),
            "tool_errors": int(trajectory.efficiency.tool_errors),
            "state_diff_empty": bool(trajectory.state_diff.is_empty()),
        }

    unsafe = run_arm(ContextOnlyOracleAgent)
    state_requirements_removed = run_arm(StateRequirementsRemovedAgent)
    if unsafe != {
        "deterministic_state_score": 1,
        "tool_calls": 2,
        "tool_errors": 0,
        "state_diff_empty": False,
    }:
        raise SystemExit("registered context-only causal arm changed")
    if state_requirements_removed != {
        "deterministic_state_score": 0,
        "tool_calls": 0,
        "tool_errors": 0,
        "state_diff_empty": True,
    }:
        raise SystemExit("registered state-requirements control changed")
    if counters != {
        "agent_client_calls": 0,
        "simulator_client_calls": 0,
        "judge_calls": 0,
    }:
        raise SystemExit("offline causal control attempted an API-backed call")
    return {
        "registered_task_id": REGISTERED_TASK_ID,
        "unsafe_context_arm": unsafe,
        "state_requirements_removed_control": state_requirements_removed,
        "deterministic_state_score_delta": 1,
        "protocol_compliant_run": False,
        "official_score_claimed": False,
    }


def build_boundary_case(
    observations: list[dict[str, Any]],
    materials: dict[str, list[Any]],
) -> dict[str, Any]:
    state_item_count = sum(
        observation["state_requirements"]["item_count"]
        for observation in observations
    )
    task_item_count = sum(
        observation["task_requirements"]["item_count"]
        for observation in observations
    )
    inputs = [
        {
            "name": "task_id",
            "classification": "runtime_metadata",
            "present": True,
            "item_count": len(materials["task_id"]),
            "payload_sha256": hashed_sequence(materials["task_id"]),
            "mutable_source_alias": False,
        },
        {
            "name": "user_id",
            "classification": "runtime_metadata",
            "present": True,
            "item_count": len(materials["user_id"]),
            "payload_sha256": hashed_sequence(materials["user_id"]),
            "mutable_source_alias": False,
        },
        {
            "name": "domain",
            "classification": "runtime_metadata",
            "present": True,
            "item_count": len(materials["domain"]),
            "payload_sha256": hashed_sequence(materials["domain"]),
            "mutable_source_alias": False,
        },
        {
            "name": "now",
            "classification": "runtime_metadata",
            "present": True,
            "item_count": len(materials["now"]),
            "payload_sha256": hashed_sequence(materials["now"]),
            "mutable_source_alias": False,
        },
        {
            "name": "task_summary",
            "classification": "task_oracle",
            "present": True,
            "item_count": len(materials["task_summary"]),
            "payload_sha256": hashed_sequence(materials["task_summary"]),
            "mutable_source_alias": False,
        },
        {
            "name": "state_requirements",
            "classification": "scoring_oracle",
            "present": True,
            "item_count": state_item_count,
            "payload_sha256": hashed_sequence(
                materials["state_requirements"]
            ),
            "mutable_source_alias": True,
        },
        {
            "name": "task_requirements",
            "classification": "scoring_oracle",
            "present": True,
            "item_count": task_item_count,
            "payload_sha256": hashed_sequence(
                materials["task_requirements"]
            ),
            "mutable_source_alias": True,
        },
    ]
    capabilities = [
        {
            "name": f"{observation['domain']}.write_handlers",
            "kind": "write_handler",
            "exposed_to_agent": True,
            "total_count": observation["write_handler_count"],
            "callable_count": observation["callable_write_handler_count"],
            "mediated_count": 0,
        }
        for observation in observations
    ]
    return {
        "schema_version": "evalfence.agent-boundary.v1",
        "case_id": "statebench-4efcbf2d-agent-boundary",
        "inputs": inputs,
        "capabilities": capabilities,
        "construction_order": {
            "baseline_snapshot_before_agent_constructor": False,
            "baseline_snapshot_before_first_agent_turn": True,
        },
        "reported": {
            "input_count": len(inputs),
            "oracle_input_count": 3,
            "capability_group_count": len(capabilities),
            "unmediated_write_callable_count": sum(
                item["callable_count"] for item in capabilities
            ),
        },
        "policy": {
            "allowed_agent_inputs": [
                "task_id",
                "user_id",
                "domain",
                "now",
            ],
            "forbid_oracle_inputs": True,
            "forbid_mutable_source_aliases": True,
            "require_write_capability_mediation": True,
            "require_baseline_before_agent_constructor": True,
        },
    }


def build_summary(
    source_shape: dict[str, Any],
    observations: list[dict[str, Any]],
    causal_control: dict[str, Any],
    boundary_case: dict[str, Any],
    counters: dict[str, int],
) -> dict[str, Any]:
    return {
        "schema_version": "evalfence.statebench-case-study-summary.v1",
        "upstream": {
            "repository": "microsoft/STATE-Bench",
            "commit": EXPECTED_COMMIT,
            "package_version": EXPECTED_PACKAGE_VERSION,
            "protocol_id": EXPECTED_PROTOCOL_ID,
            "registered_file_count": len(EXPECTED_FILES),
            "registered_files": EXPECTED_FILES,
        },
        "source_shape": source_shape,
        "runtime_context_probe": {
            "domain_count": len(observations),
            "domains": observations,
            "state_requirement_item_count": sum(
                item["state_requirements"]["item_count"]
                for item in observations
            ),
            "task_requirement_item_count": sum(
                item["task_requirements"]["item_count"]
                for item in observations
            ),
            "write_handler_count": sum(
                item["write_handler_count"] for item in observations
            ),
            "constructor_before_baseline_in_all_domains": True,
            "baseline_before_first_turn_in_all_domains": True,
        },
        "causal_control": causal_control,
        "api_boundary": counters,
        "boundary_case_sha256": canonical_sha256(boundary_case),
        "publication_boundary": {
            "raw_task_content_emitted": False,
            "raw_requirement_content_emitted": False,
            "raw_environment_content_emitted": False,
            "raw_trajectory_content_emitted": False,
            "model_result_claimed": False,
            "leaderboard_effect_claimed": False,
            "external_adoption_claimed": False,
        },
    }


def ensure_output_targets(
    upstream_root: Path,
    case_out: Path,
    summary_out: Path,
) -> None:
    upstream = upstream_root.resolve()
    case = case_out.resolve()
    summary = summary_out.resolve()
    if case == summary:
        raise SystemExit("case and summary output paths must differ")
    for output in (case, summary):
        if output == upstream or output.is_relative_to(upstream):
            raise SystemExit("generated evidence must not modify the upstream clone")
        if output.exists() and (output.is_symlink() or not output.is_file()):
            raise SystemExit("output target must be a regular file or absent")


def write_canonical(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = canonical_bytes(value) + b"\n"
    with tempfile.NamedTemporaryFile(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        temp_path = Path(handle.name)
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    try:
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def main() -> int:
    args = parse_args()
    upstream_root = args.statebench_root.resolve()
    ensure_output_targets(upstream_root, args.case_out, args.summary_out)
    files = verify_source(upstream_root)
    source_shape = verify_source_shape(files)
    offline_client_class, counters = install_offline_client_stub(upstream_root)
    observations, materials = run_context_probe(
        upstream_root,
        offline_client_class,
        counters,
    )
    causal_control = run_causal_control(offline_client_class, counters)
    boundary_case = build_boundary_case(observations, materials)
    summary = build_summary(
        source_shape,
        observations,
        causal_control,
        boundary_case,
        counters,
    )
    write_canonical(args.case_out, boundary_case)
    write_canonical(args.summary_out, summary)
    print(
        "statebench-boundary-audit: generated "
        f"{len(observations)} domains, "
        f"{summary['runtime_context_probe']['write_handler_count']} write handlers"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

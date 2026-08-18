from __future__ import annotations

import json
import math
import hashlib
import platform
import statistics
import subprocess
import sys
import time
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from datetime import datetime, timezone
from typing import Any

from pydantic import Field

from .agent import HousingAgent, VAGUE_QUERIES
from .cache import InMemoryTTLCache
from .corpus import DATA_VERSION, fixture_documents
from .observability import Metrics
from .retrieval import LocalHybridSearchBackend
from .schemas import AgentQueryRequest, StrictModel, ToolResult
from .tools import ToolRegistry
from .traces import TraceStore


class EvalTask(StrictModel):
    task_id: str
    category: str
    question: str
    expected_tools: list[str] = Field(default_factory=list)
    expected_status: str = "completed"
    fault_mode: str | None = None
    reviewed: bool = False


def generate_tasks() -> list[EvalTask]:
    regions = [("Victoria", "rental stress"), ("New South Wales", "vacancy"), ("Queensland", "housing supply"), ("Western Australia", "first-home buyers"), ("South Australia", "tenancy")]
    tasks: list[EvalTask] = []
    for i in range(30):
        region, topic = regions[i % len(regions)]
        tasks.append(EvalTask(task_id=f"direct-{i+1:03d}", category="direct_retrieval", question=f"What does discussion and official evidence say about {topic} in {region}?", expected_tools=["search_discussion", "search_official_evidence"], reviewed=i < 5))
    pairs = [("Victoria", "New South Wales"), ("Queensland", "Western Australia"), ("South Australia", "Victoria")]
    for i in range(25):
        left, right = pairs[i % len(pairs)]
        tasks.append(EvalTask(task_id=f"multihop-{i+1:03d}", category="multi_hop", question=f"Compare rental stress evidence in {left} versus {right}.", expected_tools=["compare_region_period"], reviewed=i < 4))
    cities = ["Melbourne", "Sydney", "Brisbane", "Perth", "Adelaide"]
    for i in range(15):
        tasks.append(EvalTask(task_id=f"normalise-{i+1:03d}", category="normalization", question=f"Show rental stress evidence for {cities[i % len(cities)]}.", expected_tools=["search_discussion", "search_official_evidence"], reviewed=i < 2))
    vague = sorted(VAGUE_QUERIES)
    for i in range(15):
        tasks.append(EvalTask(task_id=f"clarify-{i+1:03d}", category="clarification", question=vague[i % len(vague)], expected_status="clarification_required", reviewed=i < 2))
    faults = ["error", "empty", "timeout"]
    for i in range(15):
        tasks.append(EvalTask(task_id=f"fault-{i+1:03d}", category="failure_recovery", question="What does official evidence say about rental stress in Victoria?", expected_tools=["search_discussion", "search_official_evidence"], fault_mode=faults[i % len(faults)], reviewed=i < 2))
    assert len(tasks) == 100
    return tasks


class FaultRegistry(ToolRegistry):
    def __init__(self, backend: LocalHybridSearchBackend, mode: str | None) -> None:
        super().__init__(backend)
        self.mode = mode
        self.injected = False

    def execute(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        if self.mode and not self.injected:
            self.injected = True
            if self.mode == "error":
                raise RuntimeError("injected transient backend error")
            if self.mode == "timeout":
                time.sleep(0.08)
            if self.mode == "empty":
                return ToolResult(tool_name=name, data={"injected": "empty"})
        return super().execute(name, arguments)


@dataclass(slots=True)
class Outcome:
    task_id: str
    variant: str
    status: str
    tools: list[str]
    argument_valid: bool
    citations: int
    tool_success: int
    tool_total: int
    logical_tool_success: bool
    recovered: bool
    latency_ms: float


def _run_agent(task: EvalTask, variant: str) -> Outcome:
    backend = LocalHybridSearchBackend(fixture_documents(), data_version=DATA_VERSION)
    registry = FaultRegistry(backend, task.fault_mode)
    max_calls = 1 if variant == "single_tool" else 4
    timeout = 0.02 if task.fault_mode == "timeout" else 1.0
    agent = HousingAgent(registry, TraceStore(), InMemoryTTLCache(), Metrics(), max_tool_calls=max_calls, tool_timeout_seconds=timeout)
    started = time.perf_counter()
    response = agent.run(AgentQueryRequest(question=task.question, max_tool_calls=max_calls))
    latency = (time.perf_counter() - started) * 1000
    valid = True
    for record in response.tool_calls:
        try:
            registry.validate(record.tool_name, record.arguments)
        except Exception:
            valid = False
    unique_tools = set(record.tool_name for record in response.tool_calls)
    logical_success = bool(unique_tools) and all(
        any(record.tool_name == name and record.status == "ok" for record in response.tool_calls)
        for name in unique_tools
    )
    return Outcome(
        task_id=task.task_id, variant=variant, status=response.status,
        tools=[record.tool_name for record in response.tool_calls], argument_valid=valid,
        citations=len(response.citations), tool_success=sum(record.status == "ok" for record in response.tool_calls),
        tool_total=len(response.tool_calls), logical_tool_success=logical_success,
        recovered=any(record.recovered and record.status == "ok" for record in response.tool_calls),
        latency_ms=latency,
    )


def _run_direct(task: EvalTask) -> Outcome:
    normalized = task.question.lower().strip(" ?.! ")
    status = "clarification_required" if normalized in VAGUE_QUERIES else "completed"
    return Outcome(task.task_id, "direct_no_tools", status, [], True, 0, 0, 0, False, False, 0.01)


def evaluate(tasks: list[EvalTask]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    summaries: dict[str, Any] = {}
    for variant in ("direct_no_tools", "single_tool", "state_machine"):
        outcomes = [_run_direct(task) if variant == "direct_no_tools" else _run_agent(task, variant) for task in tasks]
        successes = []
        for task, outcome in zip(tasks, outcomes, strict=True):
            expected_tools_ok = all(tool in outcome.tools for tool in task.expected_tools)
            if not task.expected_tools:
                expected_tools_ok = True
            success = outcome.status == task.expected_status and expected_tools_ok
            successes.append(success)
            rows.append({**asdict(outcome), "category": task.category, "expected_status": task.expected_status, "expected_tools": task.expected_tools, "task_success": success})
        latencies = sorted(item.latency_ms for item in outcomes)
        tool_total = sum(item.tool_total for item in outcomes)
        completed = [item for item in outcomes if item.status == "completed"]
        with_tools = [item for item in outcomes if item.tool_total]
        faulted = [item for task, item in zip(tasks, outcomes, strict=True) if task.fault_mode]
        summaries[variant] = {
            "task_count": len(tasks),
            "task_success": sum(successes) / len(successes),
            "argument_validity": sum(item.argument_valid for item in outcomes) / len(outcomes),
            "tool_execution_success": (sum(item.logical_tool_success for item in with_tools) / len(with_tools)) if with_tools else None,
            "tool_attempt_success": (sum(item.tool_success for item in outcomes) / tool_total) if tool_total else None,
            "citation_completeness": (sum(item.citations > 0 for item in completed) / len(completed)) if completed else None,
            "failure_recovery": (sum(item.recovered for item in faulted) / len(faulted)) if faulted else None,
            "average_tool_calls": tool_total / len(outcomes),
            "p50_latency_ms": statistics.median(latencies),
            "p95_latency_ms": latencies[math.ceil(0.95 * len(latencies)) - 1],
            "provider_cost_usd": 0.0,
        }
    return {
        "scope": "synthetic/deidentified contract evaluation; not real-corpus answer quality",
        "data_version": DATA_VERSION,
        "task_distribution": dict(Counter(task.category for task in tasks)),
        "metric_definitions": {
            "task_success": "expected status and all expected tool names observed",
            "tool_execution_success": "per logical tool, at least one attempt succeeded after bounded recovery",
            "tool_attempt_success": "successful physical attempts divided by all physical attempts",
            "citation_completeness": "completed responses containing at least one citation",
            "failure_recovery": "injected-failure tasks with a successful call marked recovered",
        },
        "variants": summaries,
    }, rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False, default=str) + "\n" for row in rows), encoding="utf-8")


def run_evaluation(output_dir: Path) -> dict[str, Any]:
    tasks = generate_tasks()
    metrics, rows = evaluate(tasks)
    output_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(output_dir / "tasks.jsonl", [task.model_dump(mode="json") for task in tasks])
    write_jsonl(output_dir / "predictions.jsonl", rows)
    write_jsonl(output_dir / "error_cases.jsonl", [row for row in rows if not row["task_success"]])
    (output_dir / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    task_hash = hashlib.sha256((output_dir / "tasks.jsonl").read_bytes()).hexdigest()
    try:
        git_sha = subprocess.run(["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        git_sha = "uncommitted"
    try:
        dirty = bool(subprocess.run(["git", "status", "--porcelain"], check=True, capture_output=True, text=True).stdout.strip())
    except (subprocess.CalledProcessError, FileNotFoundError):
        dirty = True
    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "git_sha": git_sha,
        "git_dirty": dirty,
        "python": sys.version,
        "platform": platform.platform(),
        "data_version": DATA_VERSION,
        "task_sha256": task_hash,
        "provider": "local deterministic",
        "provider_cost_usd": 0.0,
    }
    (output_dir / "run_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# Deterministic evaluation report",
        "",
        "> Synthetic/deidentified contract evaluation only; not real-corpus answer quality.",
        "",
        "| Variant | Task success | Argument validity | Logical tool success | Attempt success | Citation completeness | Failure recovery | P95 ms |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name, values in metrics["variants"].items():
        percent = lambda value: "n/a" if value is None else f"{100 * value:.1f}%"
        lines.append(
            f"| {name} | {percent(values['task_success'])} | {percent(values['argument_validity'])} | "
            f"{percent(values['tool_execution_success'])} | {percent(values['tool_attempt_success'])} | "
            f"{percent(values['citation_completeness'])} | {percent(values['failure_recovery'])} | {values['p95_latency_ms']:.3f} |"
        )
    lines.extend((
        "", "## Interpretation", "",
        "The full state machine succeeds on the generated fixture contract because the generator and deterministic corpus are deliberately controlled. "
        "The attempt-level success rate includes injected first-attempt failures; logical success reflects bounded recovery. "
        "Do not transfer these percentages to a resume until a human-labeled, real-corpus evaluation is completed.",
    ))
    (output_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return metrics

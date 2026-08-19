from __future__ import annotations

import hashlib
import json
import math
import platform
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .api import create_container
from .config import Settings
from .evaluation import EvalTask, generate_tasks, write_jsonl
from .schemas import AgentQueryRequest


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[math.ceil(percentile * len(ordered)) - 1]


def _load_curated_tasks(path: Path) -> list[EvalTask]:
    annotations = {
        row["task_id"]: row
        for row in (json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
    }
    tasks = []
    for task in generate_tasks():
        annotation = annotations.get(task.task_id)
        if annotation is None or task.fault_mode is not None:
            continue
        tasks.append(task.model_copy(update={
            "reviewed": bool(annotation.get("reviewed")),
            "expected_tools": annotation.get("expected_tools", task.expected_tools),
            "expected_status": annotation.get("expected_status", task.expected_status),
        }))
    if not tasks:
        raise ValueError("no non-fault curated tasks found")
    return tasks


def _run_pass(container: Any, tasks: list[EvalTask], pass_name: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for task in tasks:
        started = time.perf_counter()
        response = container.agent.run(AgentQueryRequest(question=task.question, use_model=True))
        latency_ms = (time.perf_counter() - started) * 1000
        trace = container.traces.get(response.trace_id)
        planned_tools = [row["name"] for row in trace.planned_tools] if trace else []
        expected = set(task.expected_tools)
        observed = set(planned_tools)
        exact_match = expected == observed if expected else not observed
        true_positive = len(expected & observed)
        precision = true_positive / len(observed) if observed else (1.0 if not expected else 0.0)
        recall = true_positive / len(expected) if expected else 1.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        provider_task = task.expected_status != "clarification_required"
        provider_schema_valid = None if not provider_task else not response.cost.fallback_used
        task_success = response.status == task.expected_status and exact_match
        rows.append({
            "task_id": task.task_id,
            "category": task.category,
            "pass": pass_name,
            "expected_status": task.expected_status,
            "observed_status": response.status,
            "expected_tools": task.expected_tools,
            "planned_tools": planned_tools,
            "tool_exact_match": exact_match,
            "tool_precision": precision,
            "tool_recall": recall,
            "tool_f1": f1,
            "provider_schema_valid": provider_schema_valid,
            "fallback_used": response.cost.fallback_used,
            "cache_hit": response.cost.cache_hit,
            "model_calls": response.cost.model_calls,
            "prompt_tokens": response.cost.prompt_tokens,
            "completion_tokens": response.cost.completion_tokens,
            "total_tokens": response.cost.prompt_tokens + response.cost.completion_tokens,
            "planner_latency_ms": response.cost.planner_latency_ms,
            "end_to_end_latency_ms": latency_ms,
            "citation_complete": bool(response.citations) if response.status == "completed" else None,
            "task_success": task_success,
        })
    return rows


def _summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    provider_rows = [row for row in rows if row["provider_schema_valid"] is not None]
    completed_rows = [row for row in rows if row["observed_status"] == "completed"]
    successful_rows = [row for row in rows if row["task_success"]]
    total_tokens = sum(row["total_tokens"] for row in rows)
    return {
        "task_count": len(rows),
        "provider_task_count": len(provider_rows),
        "task_success_rate": sum(row["task_success"] for row in rows) / len(rows),
        "tool_exact_match_rate": sum(row["tool_exact_match"] for row in rows) / len(rows),
        "mean_tool_f1": statistics.fmean(row["tool_f1"] for row in rows),
        "provider_schema_valid_rate": (
            sum(bool(row["provider_schema_valid"]) for row in provider_rows) / len(provider_rows)
            if provider_rows else None
        ),
        "fallback_rate": sum(row["fallback_used"] for row in provider_rows) / len(provider_rows) if provider_rows else None,
        "citation_completeness": (
            sum(bool(row["citation_complete"]) for row in completed_rows) / len(completed_rows)
            if completed_rows else None
        ),
        "provider_calls": sum(row["model_calls"] for row in rows),
        "prompt_tokens": sum(row["prompt_tokens"] for row in rows),
        "completion_tokens": sum(row["completion_tokens"] for row in rows),
        "total_tokens": total_tokens,
        "tokens_per_successful_task": total_tokens / len(successful_rows) if successful_rows else None,
        "planner_p50_ms": statistics.median(row["planner_latency_ms"] for row in provider_rows) if provider_rows else None,
        "planner_p95_ms": _percentile([row["planner_latency_ms"] for row in provider_rows], 0.95),
        "end_to_end_p50_ms": statistics.median(row["end_to_end_latency_ms"] for row in rows),
        "end_to_end_p95_ms": _percentile([row["end_to_end_latency_ms"] for row in rows], 0.95),
    }


def run_live_evaluation(output_dir: Path, tasks_path: Path) -> dict[str, Any]:
    settings = Settings.from_env()
    if not settings.model_configured:
        raise RuntimeError("MODEL_STUDIO_BASE_URL and MODEL_STUDIO_API_KEY are required")
    tasks = _load_curated_tasks(tasks_path)
    container = create_container(settings)
    if container.agent.model_planner is None:
        raise RuntimeError("Model Studio planner is not configured")

    cold_rows = _run_pass(container, tasks, "cold")
    warm_rows = _run_pass(container, tasks, "warm")
    cold = _summarize(cold_rows)
    warm = _summarize(warm_rows)
    call_avoidance = 1 - warm["provider_calls"] / cold["provider_calls"] if cold["provider_calls"] else None
    token_reduction = 1 - warm["total_tokens"] / cold["total_tokens"] if cold["total_tokens"] else None
    latency_reduction = (
        1 - warm["end_to_end_p50_ms"] / cold["end_to_end_p50_ms"]
        if cold["end_to_end_p50_ms"] else None
    )
    metrics = {
        "scope": "live Model Studio tool-planning contract evaluation over a local deidentified fixture; not real-corpus answer quality",
        "task_source": "curated project contract annotations; fault-injection tasks excluded",
        "model": settings.chat_model,
        "pricing_status": (
            "configured_rates" if settings.model_input_usd_per_million is not None and settings.model_output_usd_per_million is not None
            else "provider_usage_not_priced"
        ),
        "cold": cold,
        "warm": warm,
        "cache_effect": {
            "provider_call_avoidance": call_avoidance,
            "token_reduction": token_reduction,
            "p50_end_to_end_latency_reduction": latency_reduction,
        },
    }

    try:
        git_sha = subprocess.run(["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        git_sha = "uncommitted"
    try:
        dirty = bool(subprocess.run(["git", "status", "--porcelain"], check=True, capture_output=True, text=True).stdout.strip())
    except (subprocess.CalledProcessError, FileNotFoundError):
        dirty = True

    output_dir.mkdir(parents=True, exist_ok=True)
    task_rows = [task.model_dump(mode="json") for task in tasks]
    write_jsonl(output_dir / "tasks.jsonl", task_rows)
    write_jsonl(output_dir / "predictions.jsonl", cold_rows + warm_rows)
    write_jsonl(output_dir / "error_cases.jsonl", [row for row in cold_rows if not row["task_success"]])
    (output_dir / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "git_sha": git_sha,
        "git_dirty": dirty,
        "python": sys.version,
        "platform": platform.platform(),
        "data_version": container.registry.backend.data_version,
        "task_sha256": hashlib.sha256((output_dir / "tasks.jsonl").read_bytes()).hexdigest(),
        "provider": "Alibaba Cloud Model Studio",
        "model": settings.chat_model,
        "credentials_persisted": False,
        "real_corpus_used": False,
    }
    (output_dir / "run_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return metrics

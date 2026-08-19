"""Black-box API benchmark for an already running Housing Agent service."""

from __future__ import annotations

import json
import math
import os
import platform
import statistics
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .evaluation import generate_tasks


def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    return ordered[math.ceil(percentile * len(ordered)) - 1]


def _request(url: str, question: str, timeout_seconds: float) -> dict[str, Any]:
    payload = json.dumps({"question": question, "use_model": False}).encode("utf-8")
    request = urllib.request.Request(
        url.rstrip("/") + "/api/agent/query",
        data=payload,
        headers={"content-type": "application/json"},
        method="POST",
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            body = json.loads(response.read().decode("utf-8"))
            status_code = int(response.status)
        error = None
    except Exception as exc:
        body = {}
        status_code = 0
        error = type(exc).__name__
    latency_ms = (time.perf_counter() - started) * 1000
    return {
        "status_code": status_code,
        "agent_status": body.get("status"),
        "question": question,
        "clarification": body.get("clarification"),
        "latency_ms": latency_ms,
        "citation_count": len(body.get("citations") or []),
        "tool_duration_ms": sum(float(row.get("duration_ms") or 0) for row in body.get("tool_calls") or []),
        "error": error,
    }


def _summarize(rows: list[dict[str, Any]], wall_seconds: float) -> dict[str, Any]:
    latencies = [row["latency_ms"] for row in rows]
    tool_latencies = [row["tool_duration_ms"] for row in rows]
    transport_successes = [row for row in rows if row["status_code"] == 200]
    agent_successes = [row for row in transport_successes if row["agent_status"] != "failed"]
    status_counts = {
        status: sum(row["agent_status"] == status for row in rows)
        for status in sorted({row["agent_status"] for row in rows if row["agent_status"]})
    }
    return {
        "requests": len(rows),
        "transport_successful_requests": len(transport_successes),
        "transport_success_rate": len(transport_successes) / len(rows),
        "agent_nonfailed_requests": len(agent_successes),
        "agent_nonfailed_rate": len(agent_successes) / len(rows),
        "agent_status_counts": status_counts,
        "wall_seconds": wall_seconds,
        "throughput_qps": len(rows) / wall_seconds,
        "http_latency_p50_ms": statistics.median(latencies),
        "http_latency_p95_ms": _percentile(latencies, 0.95),
        "http_latency_p99_ms": _percentile(latencies, 0.99),
        "tool_duration_p50_ms": statistics.median(tool_latencies),
        "tool_duration_p95_ms": _percentile(tool_latencies, 0.95),
        "citation_complete_rate": sum(row["citation_count"] > 0 for row in agent_successes) / len(agent_successes) if agent_successes else None,
        "agent_failures": [
            {"question": row["question"], "clarification": row["clarification"]}
            for row in rows if row["agent_status"] == "failed"
        ],
        "error_counts": {
            error: sum(row["error"] == error for row in rows)
            for error in sorted({row["error"] for row in rows if row["error"]})
        },
    }


def run_api_benchmark(
    url: str,
    *,
    output: Path | None = None,
    requests: int = 100,
    concurrency: int = 10,
    timeout_seconds: float = 10.0,
) -> dict[str, Any]:
    if requests < 1 or concurrency < 1:
        raise ValueError("requests and concurrency must be positive")
    candidate_questions = [
        task.question for task in generate_tasks()
        if task.fault_mode is None and task.expected_status == "completed"
    ]
    task_questions = list(dict.fromkeys(candidate_questions))[:20]

    passes: dict[str, Any] = {}
    for name in ("cold", "warm"):
        started = time.perf_counter()
        rows = [_request(url, question, timeout_seconds) for question in task_questions]
        passes[name] = _summarize(rows, time.perf_counter() - started)

    expanded = [task_questions[index % len(task_questions)] for index in range(requests)]
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        concurrent_rows = list(pool.map(lambda question: _request(url, question, timeout_seconds), expanded))
    concurrent = _summarize(concurrent_rows, time.perf_counter() - started)
    cold_p50 = passes["cold"]["http_latency_p50_ms"]
    warm_p50 = passes["warm"]["http_latency_p50_ms"]
    cold_tool = passes["cold"]["tool_duration_p50_ms"]
    warm_tool = passes["warm"]["tool_duration_p50_ms"]
    try:
        with urllib.request.urlopen(url.rstrip("/") + "/healthz", timeout=timeout_seconds) as response:
            health = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        health = {"status": "unavailable", "error": type(exc).__name__}
    result = {
        "scope": "black-box online benchmark over deidentified fixture queries; not real-corpus relevance or production SLA",
        "run_manifest": {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "source_git_sha": os.getenv("SOURCE_GIT_SHA", "unknown"),
            "python": platform.python_version(),
            "platform": platform.platform(),
            "hostname": platform.node(),
            "health": health,
        },
        "url": url,
        "query_count_per_cache_pass": len(task_questions),
        "concurrency": concurrency,
        "passes": passes,
        "cache_effect": {
            "http_p50_latency_reduction": 1 - warm_p50 / cold_p50 if cold_p50 else None,
            "tool_p50_duration_reduction": 1 - warm_tool / cold_tool if cold_tool else None,
        },
        "concurrent": concurrent,
    }
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result

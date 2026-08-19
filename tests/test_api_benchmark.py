from housing_agent.api_benchmark import _summarize


def test_benchmark_summary_separates_throughput_and_latency() -> None:
    rows = [
        {"status_code": 200, "agent_status": "completed", "latency_ms": 10.0, "citation_count": 2, "tool_duration_ms": 4.0, "error": None},
        {"status_code": 200, "agent_status": "completed", "latency_ms": 20.0, "citation_count": 1, "tool_duration_ms": 8.0, "error": None},
    ]
    summary = _summarize(rows, wall_seconds=0.5)
    assert summary["throughput_qps"] == 4.0
    assert summary["http_latency_p50_ms"] == 15.0
    assert summary["http_latency_p95_ms"] == 20.0
    assert summary["citation_complete_rate"] == 1.0
    assert summary["transport_success_rate"] == 1.0
    assert summary["agent_nonfailed_rate"] == 1.0

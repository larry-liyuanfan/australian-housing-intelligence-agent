from __future__ import annotations

from fastapi.testclient import TestClient

from housing_agent.api import create_app, create_container
from housing_agent.config import Settings


def client() -> TestClient:
    return TestClient(create_app(create_container(Settings())))


def test_query_trace_and_metrics_endpoints() -> None:
    api = client()
    response = api.post("/api/agent/query", json={"question": "Show discussion and official evidence for rental stress in Victoria."})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    trace = api.get(f"/api/agent/traces/{body['trace_id']}")
    assert trace.status_code == 200
    assert trace.json()["citation_ids"]
    metrics = api.get("/metrics")
    assert metrics.status_code == 200
    assert "housing_agent_queries_total" in metrics.text


def test_unknown_trace_returns_404() -> None:
    assert client().get("/api/agent/traces/not-found").status_code == 404


def test_api_rejects_raw_dsl_and_extra_fields() -> None:
    response = client().post("/api/agent/query", json={"question": "rent in Victoria", "dsl": {"match_all": {}}})
    assert response.status_code == 422

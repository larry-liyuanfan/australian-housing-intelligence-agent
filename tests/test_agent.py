from __future__ import annotations

from housing_agent.agent import HousingAgent
from housing_agent.cache import InMemoryTTLCache
from housing_agent.corpus import DATA_VERSION, fixture_documents
from housing_agent.evaluation import FaultRegistry
from housing_agent.observability import Metrics
from housing_agent.retrieval import LocalHybridSearchBackend
from housing_agent.schemas import AgentQueryRequest
from housing_agent.tools import ToolRegistry
from housing_agent.traces import TraceStore


def build_agent(registry: ToolRegistry | None = None, timeout: float = 1.0) -> tuple[HousingAgent, TraceStore]:
    backend = LocalHybridSearchBackend(fixture_documents(), data_version=DATA_VERSION)
    registry = registry or ToolRegistry(backend)
    traces = TraceStore()
    return HousingAgent(registry, traces, InMemoryTTLCache(), Metrics(), tool_timeout_seconds=timeout), traces


def test_state_machine_returns_cited_discussion_and_official_evidence() -> None:
    agent, traces = build_agent()
    result = agent.run(AgentQueryRequest(question="What does discussion and official evidence say about rental stress in Victoria?"))
    assert result.status == "completed"
    assert {call.tool_name for call in result.tool_calls} == {"search_discussion", "search_official_evidence"}
    assert {item.corpus for item in result.citations} == {"discussion", "official"}
    assert all(f"[{item.doc_id}]" in result.answer for item in result.citations[:4])
    trace = traces.get(result.trace_id)
    assert trace is not None
    assert trace.states == ["receive", "normalize", "plan", "execute", "verify", "synthesize", "done"]


def test_vague_question_requests_clarification_without_tool_call() -> None:
    agent, traces = build_agent()
    result = agent.run(AgentQueryRequest(question="Tell me about it"))
    assert result.status == "clarification_required"
    assert result.tool_calls == []
    assert traces.get(result.trace_id).states[-1] == "clarify"


def test_transient_tool_error_is_retried_and_recorded() -> None:
    backend = LocalHybridSearchBackend(fixture_documents(), data_version=DATA_VERSION)
    registry = FaultRegistry(backend, "error")
    agent, _ = build_agent(registry)
    result = agent.run(AgentQueryRequest(question="What does official evidence say about rental stress in Victoria?"))
    assert result.status == "completed"
    assert any(call.status == "error" for call in result.tool_calls)
    assert any(call.recovered and call.status == "ok" for call in result.tool_calls)


def test_timeout_is_retried_without_unbounded_loop() -> None:
    backend = LocalHybridSearchBackend(fixture_documents(), data_version=DATA_VERSION)
    registry = FaultRegistry(backend, "timeout")
    agent, _ = build_agent(registry, timeout=0.01)
    result = agent.run(AgentQueryRequest(question="What does official evidence say about rental stress in Victoria?"))
    assert result.status == "completed"
    assert len(result.tool_calls) <= 4
    assert any(call.status == "timeout" for call in result.tool_calls)


def test_retry_never_exceeds_request_call_budget() -> None:
    backend = LocalHybridSearchBackend(fixture_documents(), data_version=DATA_VERSION)
    registry = FaultRegistry(backend, "error")
    agent, _ = build_agent(registry)
    result = agent.run(AgentQueryRequest(
        question="What does discussion and official evidence say about rental stress in Victoria?",
        max_tool_calls=2,
    ))
    assert len(result.tool_calls) == 2

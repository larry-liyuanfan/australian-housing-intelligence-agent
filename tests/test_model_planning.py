from __future__ import annotations

from housing_agent.agent import HousingAgent
from housing_agent.cache import InMemoryTTLCache
from housing_agent.corpus import DATA_VERSION, fixture_documents
from housing_agent.observability import Metrics
from housing_agent.planning import ModelStudioPlanner
from housing_agent.retrieval import LocalHybridSearchBackend
from housing_agent.schemas import AgentQueryRequest
from housing_agent.tools import ToolRegistry
from housing_agent.traces import TraceStore


class FakeModelStudioClient:
    chat_model = "qwen-test"

    def __init__(self, invalid: bool = False) -> None:
        self.calls = 0
        self.invalid = invalid

    def chat_with_tools(self, messages: list[dict], tools: list[dict]) -> dict:
        self.calls += 1
        name = "not_a_tool" if self.invalid else "search_discussion"
        return {
            "choices": [{
                "message": {
                    "tool_calls": [{
                        "function": {
                            "name": name,
                            "arguments": '{"query":"rental stress Victoria","region":"VIC","top_k":5}',
                        }
                    }]
                }
            }],
            "usage": {"prompt_tokens": 120, "completion_tokens": 18},
        }


def _agent(client: FakeModelStudioClient) -> HousingAgent:
    registry = ToolRegistry(LocalHybridSearchBackend(fixture_documents(), data_version=DATA_VERSION))
    return HousingAgent(
        registry,
        TraceStore(),
        InMemoryTTLCache(),
        Metrics(),
        model_planner=ModelStudioPlanner(client),
    )


def test_model_usage_is_recorded_and_valid_plan_is_cached() -> None:
    client = FakeModelStudioClient()
    agent = _agent(client)
    request = AgentQueryRequest(question="Show rental stress in Victoria", use_model=True)

    cold = agent.run(request)
    warm = agent.run(request)

    assert client.calls == 1
    assert cold.cost.model_calls == 1
    assert cold.cost.prompt_tokens == 120
    assert cold.cost.completion_tokens == 18
    assert cold.cost.fallback_used is False
    assert warm.cost.model_calls == 0
    assert warm.cost.cache_hit is True
    assert warm.cost.measurement_status == "cache_avoided_provider_call"


def test_invalid_provider_tool_falls_back_without_caching_failure() -> None:
    client = FakeModelStudioClient(invalid=True)
    agent = _agent(client)
    request = AgentQueryRequest(question="Show rental stress in Victoria", use_model=True)

    first = agent.run(request)
    second = agent.run(request)

    assert client.calls == 2
    assert first.status == "completed"
    assert first.cost.fallback_used is True
    assert second.cost.cache_hit is False

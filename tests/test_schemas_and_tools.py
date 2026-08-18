from __future__ import annotations

import pytest
from pydantic import ValidationError

from housing_agent.corpus import DATA_VERSION, fixture_documents
from housing_agent.retrieval import LocalHybridSearchBackend
from housing_agent.schemas import SearchDiscussionInput
from housing_agent.tools import ToolRegistry, ToolValidationError


def registry() -> ToolRegistry:
    return ToolRegistry(LocalHybridSearchBackend(fixture_documents(), data_version=DATA_VERSION))


def test_tool_schema_rejects_unknown_fields_and_oversized_top_k() -> None:
    with pytest.raises(ValidationError):
        SearchDiscussionInput(query="rental stress", top_k=21)
    with pytest.raises(ValidationError):
        SearchDiscussionInput.model_validate({"query": "rent", "elasticsearch_dsl": {"match_all": {}}})


def test_registry_rejects_unknown_tool_and_arbitrary_dsl() -> None:
    tools = registry()
    with pytest.raises(ToolValidationError):
        tools.execute("delete_index", {})
    with pytest.raises(ToolValidationError):
        tools.execute("search_discussion", {"query": "rent", "dsl": {"match_all": {}}})


def test_all_six_tool_specs_are_exposed() -> None:
    tools = registry()
    assert set(tools.names) == {
        "search_discussion", "search_official_evidence", "aggregate_topic",
        "compare_region_period", "get_sentiment_trend", "explain_data_coverage",
    }
    assert all(item["type"] == "function" for item in tools.model_studio_specs())

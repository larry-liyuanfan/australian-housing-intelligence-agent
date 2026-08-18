from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Protocol

from .modelstudio import ModelStudioClient, ModelStudioError
from .schemas import AgentQueryRequest, AustralianRegion
from .tools import ToolRegistry, ToolValidationError


REGION_ALIASES = {
    "victoria": "VIC", "melbourne": "VIC", "vic": "VIC",
    "new south wales": "NSW", "sydney": "NSW", "nsw": "NSW",
    "queensland": "QLD", "brisbane": "QLD", "qld": "QLD",
    "south australia": "SA", "adelaide": "SA", "sa": "SA",
    "western australia": "WA", "perth": "WA", "wa": "WA",
    "tasmania": "TAS", "hobart": "TAS", "tas": "TAS",
    "australian capital territory": "ACT", "canberra": "ACT", "act": "ACT",
    "northern territory": "NT", "darwin": "NT", "nt": "NT",
}


@dataclass(frozen=True, slots=True)
class ProposedToolCall:
    name: str
    arguments: dict[str, Any]


class Planner(Protocol):
    provider: str
    def plan(self, request: AgentQueryRequest, registry: ToolRegistry) -> list[ProposedToolCall]: ...


def regions_in_text(text: str) -> list[AustralianRegion]:
    lowered = text.lower()
    found: list[AustralianRegion] = []
    for alias, code in sorted(REGION_ALIASES.items(), key=lambda item: -len(item[0])):
        if re.search(rf"(?<![a-z]){re.escape(alias)}(?![a-z])", lowered):
            region = AustralianRegion(code)
            if region not in found:
                found.append(region)
    return found


class DeterministicPlanner:
    provider = "local"

    def plan(self, request: AgentQueryRequest, registry: ToolRegistry) -> list[ProposedToolCall]:
        text = request.question.lower()
        regions = regions_in_text(text)
        region = request.region or (regions[0] if len(regions) == 1 else None)
        window = {"start_date": request.start_date, "end_date": request.end_date}
        common = {"query": request.question, "region": region, **window, "top_k": 5}
        calls: list[ProposedToolCall] = []

        if any(term in text for term in ("coverage", "covered", "data available", "data range", "数据覆盖", "数据范围")):
            calls.append(ProposedToolCall("explain_data_coverage", {"corpus": "both", "region": region}))
        elif len(regions) >= 2 or any(term in text for term in ("compare", "versus", " vs ", "对比", "比较")):
            compare_regions = regions[:4]
            if len(compare_regions) < 2 and region:
                compare_regions = [region, AustralianRegion.NATIONAL]
            if len(compare_regions) >= 2:
                calls.append(ProposedToolCall("compare_region_period", {"query": request.question, "regions": compare_regions, **window}))
        elif any(term in text for term in ("sentiment", "tone", "情绪", "舆情")):
            calls.append(ProposedToolCall("get_sentiment_trend", {"topic": request.question, "region": region, **window}))
        elif any(term in text for term in ("how many", "count", "volume", "topic", "数量", "主题", "多少")):
            calls.append(ProposedToolCall("aggregate_topic", {"topic": request.question, "region": region, "platform": None}))
        else:
            calls.append(ProposedToolCall("search_discussion", {**common, "platform": None}))

        needs_official = any(term in text for term in ("official", "evidence", "indicator", "statistics", "context", "官方", "指标", "证据"))
        if needs_official and calls[0].name not in {"compare_region_period", "explain_data_coverage"}:
            calls.append(ProposedToolCall("search_official_evidence", {**common, "source_group": None}))
        elif calls[0].name == "search_discussion" and len(calls) < request.max_tool_calls:
            calls.append(ProposedToolCall("search_official_evidence", {**common, "source_group": None}))
        return calls[: request.max_tool_calls]


class ModelStudioPlanner:
    provider = "model_studio"

    def __init__(self, client: ModelStudioClient, fallback: Planner | None = None) -> None:
        self.client = client
        self.fallback = fallback or DeterministicPlanner()

    def plan(self, request: AgentQueryRequest, registry: ToolRegistry) -> list[ProposedToolCall]:
        system = (
            "Select only the supplied housing evidence tools. Never create Elasticsearch DSL. "
            "Use at most four calls. Keep online discussion separate from official evidence."
        )
        try:
            response = self.client.chat_with_tools(
                [{"role": "system", "content": system}, {"role": "user", "content": request.question}],
                registry.model_studio_specs(),
            )
            message = response["choices"][0]["message"]
            raw_calls = message.get("tool_calls") or []
            calls = []
            for raw in raw_calls[: request.max_tool_calls]:
                name = raw["function"]["name"]
                arguments = json.loads(raw["function"].get("arguments") or "{}")
                parsed = registry.validate(name, arguments)
                calls.append(ProposedToolCall(name, parsed.model_dump(mode="json")))
            return calls or self.fallback.plan(request, registry)
        except (ModelStudioError, KeyError, IndexError, TypeError, ValueError, ToolValidationError, json.JSONDecodeError):
            return self.fallback.plan(request, registry)

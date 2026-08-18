from __future__ import annotations

from collections import Counter
from datetime import date
from typing import Any, Callable

from pydantic import BaseModel, ValidationError

from .retrieval import SearchBackend
from .schemas import (
    AggregateTopicInput,
    AustralianRegion,
    CompareRegionPeriodInput,
    DataCoverageInput,
    SearchDiscussionInput,
    SearchOfficialEvidenceInput,
    SentimentTrendInput,
    ToolResult,
)


class ToolValidationError(ValueError):
    pass


class ToolRegistry:
    """Allowlisted tool dispatcher. No tool accepts raw Elasticsearch DSL."""

    def __init__(self, backend: SearchBackend) -> None:
        self.backend = backend
        self._tools: dict[str, tuple[type[BaseModel], Callable[[BaseModel], ToolResult]]] = {
            "search_discussion": (SearchDiscussionInput, self._search_discussion),
            "search_official_evidence": (SearchOfficialEvidenceInput, self._search_official),
            "aggregate_topic": (AggregateTopicInput, self._aggregate_topic),
            "compare_region_period": (CompareRegionPeriodInput, self._compare_region_period),
            "get_sentiment_trend": (SentimentTrendInput, self._sentiment_trend),
            "explain_data_coverage": (DataCoverageInput, self._coverage),
        }

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(self._tools)

    def model_studio_specs(self) -> list[dict[str, Any]]:
        descriptions = {
            "search_discussion": "Search deidentified public-discussion signals with controlled filters.",
            "search_official_evidence": "Search official housing context kept separate from discussion signals.",
            "aggregate_topic": "Aggregate indexed discussion records for a topic.",
            "compare_region_period": "Compare discussion and official evidence across two to four regions.",
            "get_sentiment_trend": "Return an approximate indexed sentiment trend for a topic.",
            "explain_data_coverage": "Explain index coverage, data version and limitations.",
        }
        return [
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": descriptions[name],
                    "parameters": model.model_json_schema(),
                },
            }
            for name, (model, _) in self._tools.items()
        ]

    def validate(self, name: str, arguments: dict[str, Any]) -> BaseModel:
        if name not in self._tools:
            raise ToolValidationError(f"unknown tool: {name}")
        model, _ = self._tools[name]
        try:
            return model.model_validate(arguments)
        except ValidationError as exc:
            raise ToolValidationError(str(exc)) from exc

    def execute(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        parsed = self.validate(name, arguments)
        return self._tools[name][1](parsed)

    def _search_discussion(self, raw: BaseModel) -> ToolResult:
        args = SearchDiscussionInput.model_validate(raw)
        evidence = self.backend.search(
            "discussion", args.query, region=args.region, start_date=args.start_date,
            end_date=args.end_date, top_k=args.top_k, platform=args.platform, source_group=None,
        )
        return ToolResult(tool_name="search_discussion", data={"query": args.query, "result_count": len(evidence)}, evidence=evidence)

    def _search_official(self, raw: BaseModel) -> ToolResult:
        args = SearchOfficialEvidenceInput.model_validate(raw)
        evidence = self.backend.search(
            "official", args.query, region=args.region, start_date=args.start_date,
            end_date=args.end_date, top_k=args.top_k, platform=None, source_group=args.source_group,
        )
        return ToolResult(tool_name="search_official_evidence", data={"query": args.query, "result_count": len(evidence)}, evidence=evidence)

    def _aggregate_topic(self, raw: BaseModel) -> ToolResult:
        args = AggregateTopicInput.model_validate(raw)
        data = self.backend.aggregate_topic(args.topic, region=args.region, platform=args.platform)
        evidence = self.backend.search("discussion", args.topic, region=args.region, top_k=3, platform=args.platform)
        return ToolResult(tool_name="aggregate_topic", data=data, evidence=evidence, warnings=["Counts describe indexed records, not population prevalence."])

    def _compare_region_period(self, raw: BaseModel) -> ToolResult:
        args = CompareRegionPeriodInput.model_validate(raw)
        rows = []
        evidence = []
        for region in args.regions:
            discussion = self.backend.search("discussion", args.query, region=region, start_date=args.start_date, end_date=args.end_date, top_k=2)
            official = self.backend.search("official", args.query, region=region, start_date=args.start_date, end_date=args.end_date, top_k=2)
            evidence.extend(discussion + official)
            rows.append({"region": region.value, "discussion_hits": len(discussion), "official_hits": len(official)})
        return ToolResult(
            tool_name="compare_region_period",
            data={"query": args.query, "regions": rows},
            evidence=evidence,
            warnings=["Hit counts are retrieval diagnostics, not estimates of real-world incidence."],
        )

    def _sentiment_trend(self, raw: BaseModel) -> ToolResult:
        args = SentimentTrendInput.model_validate(raw)
        data = self.backend.sentiment_trend(args.topic, region=args.region, start_date=args.start_date, end_date=args.end_date)
        evidence = self.backend.search("discussion", args.topic, region=args.region, start_date=args.start_date, end_date=args.end_date, top_k=3)
        return ToolResult(tool_name="get_sentiment_trend", data=data, evidence=evidence, warnings=["Sentiment is an approximate text signal."])

    def _coverage(self, raw: BaseModel) -> ToolResult:
        args = DataCoverageInput.model_validate(raw)
        data = self.backend.coverage(args.corpus, region=args.region)
        evidence = []
        corpora = ("discussion", "official") if args.corpus == "both" else (args.corpus,)
        for corpus in corpora:
            evidence.extend(self.backend.search(corpus, "housing", region=args.region, top_k=1))
        return ToolResult(tool_name="explain_data_coverage", data=data, evidence=evidence, warnings=[str(data.get("warning", ""))])

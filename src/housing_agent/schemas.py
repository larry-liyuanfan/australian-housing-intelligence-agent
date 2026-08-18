from __future__ import annotations

from datetime import date, datetime, timezone
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class AustralianRegion(StrEnum):
    NATIONAL = "AU"
    ACT = "ACT"
    NSW = "NSW"
    NT = "NT"
    QLD = "QLD"
    SA = "SA"
    TAS = "TAS"
    VIC = "VIC"
    WA = "WA"


class DateWindow(StrictModel):
    start: date | None = None
    end: date | None = None

    @model_validator(mode="after")
    def validate_order(self) -> "DateWindow":
        if self.start and self.end and self.start > self.end:
            raise ValueError("start must not be after end")
        return self


class SearchFilters(StrictModel):
    region: AustralianRegion | None = None
    date_window: DateWindow = Field(default_factory=DateWindow)


class HousingDocument(StrictModel):
    doc_id: str
    corpus: Literal["discussion", "official"]
    title: str
    text: str
    source: str
    region: AustralianRegion = AustralianRegion.NATIONAL
    period: date | None = None
    topic: str
    sentiment: float | None = Field(default=None, ge=-1.0, le=1.0)
    url: str | None = None
    platform: Literal["bluesky", "mastodon", "youtube", "gdelt", "official"]
    metrics: dict[str, float] = Field(default_factory=dict)


class Evidence(StrictModel):
    doc_id: str
    corpus: Literal["discussion", "official"]
    title: str
    snippet: str
    source: str
    region: AustralianRegion
    period: date | None = None
    url: str | None = None
    score: float
    rank: int


class SearchInput(StrictModel):
    query: str = Field(min_length=2, max_length=500)
    region: AustralianRegion | None = None
    start_date: date | None = None
    end_date: date | None = None
    top_k: int = Field(default=5, ge=1, le=20)

    @model_validator(mode="after")
    def validate_dates(self) -> "SearchInput":
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError("start_date must not be after end_date")
        return self


class SearchDiscussionInput(SearchInput):
    platform: Literal["bluesky", "mastodon", "youtube", "gdelt"] | None = None


class SearchOfficialEvidenceInput(SearchInput):
    source_group: str | None = Field(default=None, max_length=100)


class AggregateTopicInput(StrictModel):
    topic: str = Field(min_length=2, max_length=100)
    region: AustralianRegion | None = None
    platform: Literal["bluesky", "mastodon", "youtube", "gdelt"] | None = None


class CompareRegionPeriodInput(StrictModel):
    query: str = Field(min_length=2, max_length=500)
    regions: list[AustralianRegion] = Field(min_length=2, max_length=4)
    start_date: date | None = None
    end_date: date | None = None


class SentimentTrendInput(StrictModel):
    topic: str = Field(min_length=2, max_length=100)
    region: AustralianRegion | None = None
    start_date: date | None = None
    end_date: date | None = None


class DataCoverageInput(StrictModel):
    corpus: Literal["discussion", "official", "both"] = "both"
    region: AustralianRegion | None = None


class ToolResult(StrictModel):
    tool_name: str
    data: dict[str, Any] = Field(default_factory=dict)
    evidence: list[Evidence] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ToolCallRecord(StrictModel):
    tool_name: str
    arguments: dict[str, Any]
    status: Literal["ok", "error", "timeout", "skipped"]
    duration_ms: float
    evidence_count: int = 0
    error: str | None = None
    recovered: bool = False


class CostRecord(StrictModel):
    provider: Literal["local", "model_studio"] = "local"
    prompt_tokens: int = 0
    completion_tokens: int = 0
    model_calls: int = 0
    estimated_cost_usd: float | None = 0.0
    measurement_status: Literal["local_no_provider_cost", "provider_usage_not_priced"] = "local_no_provider_cost"


class AgentQueryRequest(StrictModel):
    question: str = Field(min_length=3, max_length=1000)
    region: AustralianRegion | None = None
    start_date: date | None = None
    end_date: date | None = None
    max_tool_calls: int = Field(default=4, ge=1, le=4)
    use_model: bool = False

    @model_validator(mode="after")
    def validate_dates(self) -> "AgentQueryRequest":
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError("start_date must not be after end_date")
        return self


class AgentQueryResponse(StrictModel):
    trace_id: str
    status: Literal["completed", "clarification_required", "insufficient_evidence", "failed"]
    answer: str
    citations: list[Evidence] = Field(default_factory=list)
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
    cost: CostRecord = Field(default_factory=CostRecord)
    data_version: str
    clarification: str | None = None


class TraceRecord(StrictModel):
    trace_id: str
    question: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None
    states: list[str] = Field(default_factory=list)
    normalized_query: dict[str, Any] = Field(default_factory=dict)
    planned_tools: list[dict[str, Any]] = Field(default_factory=list)
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
    status: str = "running"
    citation_ids: list[str] = Field(default_factory=list)
    cost: CostRecord = Field(default_factory=CostRecord)

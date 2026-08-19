from __future__ import annotations

import hashlib
import json
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from .cache import Cache
from .observability import Metrics
from .planning import DeterministicPlanner, ModelStudioPlanner, Planner, ProposedPlan, ProposedToolCall, regions_in_text
from .schemas import AgentQueryRequest, AgentQueryResponse, CostRecord, Evidence, ToolCallRecord, ToolResult, TraceRecord
from .tools import ToolRegistry, ToolValidationError
from .traces import TraceStore


class AgentState(StrEnum):
    RECEIVE = "receive"
    NORMALIZE = "normalize"
    PLAN = "plan"
    EXECUTE = "execute"
    VERIFY = "verify"
    SYNTHESIZE = "synthesize"
    CLARIFY = "clarify"
    DONE = "done"
    FAILED = "failed"


VAGUE_QUERIES = {"tell me about it", "what about housing", "housing", "help", "分析一下", "说说住房"}


class HousingAgent:
    def __init__(
        self,
        registry: ToolRegistry,
        traces: TraceStore,
        cache: Cache,
        metrics: Metrics,
        *,
        planner: Planner | None = None,
        model_planner: ModelStudioPlanner | None = None,
        max_tool_calls: int = 4,
        tool_timeout_seconds: float = 3.0,
        model_input_usd_per_million: float | None = None,
        model_output_usd_per_million: float | None = None,
    ) -> None:
        self.registry = registry
        self.traces = traces
        self.cache = cache
        self.metrics = metrics
        self.planner = planner or DeterministicPlanner()
        self.model_planner = model_planner
        self.max_tool_calls = min(4, max(1, max_tool_calls))
        self.tool_timeout_seconds = tool_timeout_seconds
        self.model_input_usd_per_million = model_input_usd_per_million
        self.model_output_usd_per_million = model_output_usd_per_million

    @staticmethod
    def _signature(call: ProposedToolCall) -> str:
        payload = json.dumps(call.arguments, sort_keys=True, default=str, separators=(",", ":"))
        return hashlib.sha256(f"{call.name}:{payload}".encode()).hexdigest()

    def _plan_cache_key(self, request: AgentQueryRequest) -> str:
        payload = request.model_dump(mode="json", exclude={"use_model"})
        payload["data_version"] = self.registry.backend.data_version
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return "plan:" + hashlib.sha256(encoded.encode()).hexdigest()

    def _plan(self, request: AgentQueryRequest, planner: Planner) -> ProposedPlan:
        if planner.provider != "model_studio":
            return planner.plan(request, self.registry)
        cache_key = self._plan_cache_key(request)
        cached = self.cache.get(cache_key)
        if cached is not None:
            try:
                calls = []
                for raw in cached["calls"]:
                    parsed = self.registry.validate(raw["name"], raw["arguments"])
                    calls.append(ProposedToolCall(raw["name"], parsed.model_dump(mode="json")))
                self.metrics.increment("plan_cache_hits_total")
                return ProposedPlan(
                    calls=calls,
                    provider="model_studio",
                    model_calls=0,
                    cache_hit=True,
                    model=cached.get("model"),
                )
            except (KeyError, TypeError, ToolValidationError, ValueError):
                pass
        self.metrics.increment("plan_cache_misses_total")
        plan = planner.plan(request, self.registry)
        if plan.provider == "model_studio" and not plan.fallback_used:
            self.cache.set(
                cache_key,
                {
                    "calls": [
                        {"name": call.name, "arguments": json.loads(json.dumps(call.arguments, default=str))}
                        for call in plan.calls
                    ],
                    "model": plan.model,
                },
                ttl_seconds=300,
            )
        return plan

    def _cost_record(self, plan: ProposedPlan) -> CostRecord:
        if plan.provider != "model_studio":
            return CostRecord()
        if plan.cache_hit:
            return CostRecord(
                provider="model_studio",
                model=plan.model,
                cache_hit=True,
                measurement_status="cache_avoided_provider_call",
                estimated_cost_usd=0.0,
            )
        estimated_cost = None
        measurement_status = "provider_usage_not_priced"
        if self.model_input_usd_per_million is not None and self.model_output_usd_per_million is not None:
            estimated_cost = (
                plan.prompt_tokens * self.model_input_usd_per_million
                + plan.completion_tokens * self.model_output_usd_per_million
            ) / 1_000_000
            measurement_status = "provider_usage_priced"
        return CostRecord(
            provider="model_studio",
            model=plan.model,
            prompt_tokens=plan.prompt_tokens,
            completion_tokens=plan.completion_tokens,
            model_calls=plan.model_calls,
            planner_latency_ms=round(plan.latency_ms, 3),
            fallback_used=plan.fallback_used,
            estimated_cost_usd=estimated_cost,
            measurement_status=measurement_status,
        )

    @staticmethod
    def _append_state(trace: TraceRecord, state: AgentState) -> None:
        trace.states.append(state.value)

    def _execute_one(self, call: ProposedToolCall) -> tuple[ToolResult | None, ToolCallRecord]:
        started = time.perf_counter()
        cache_key = f"tool:{self.registry.backend.data_version}:{self._signature(call)}"
        try:
            cached = self.cache.get(cache_key)
            if cached is not None:
                result = ToolResult.model_validate(cached)
                self.metrics.increment("cache_hits_total")
            else:
                pool = ThreadPoolExecutor(max_workers=1)
                future = pool.submit(self.registry.execute, call.name, call.arguments)
                try:
                    result = future.result(timeout=self.tool_timeout_seconds)
                finally:
                    pool.shutdown(wait=False, cancel_futures=True)
                self.cache.set(cache_key, result.model_dump(mode="json"), ttl_seconds=300)
                self.metrics.increment("cache_misses_total")
            status, error = "ok", None
        except FutureTimeout:
            result, status, error = None, "timeout", "tool timeout"
        except (ToolValidationError, RuntimeError, ValueError) as exc:
            result, status, error = None, "error", f"{type(exc).__name__}: {exc}"
        duration = (time.perf_counter() - started) * 1000
        record = ToolCallRecord(
            tool_name=call.name,
            arguments=json.loads(json.dumps(call.arguments, default=str)),
            status=status,
            duration_ms=round(duration, 3),
            evidence_count=len(result.evidence) if result else 0,
            error=error,
        )
        return result, record

    def _recover_empty(self, call: ProposedToolCall) -> tuple[ToolResult | None, ToolCallRecord] | None:
        if call.name not in {"search_discussion", "search_official_evidence"}:
            return None
        args = dict(call.arguments)
        if not any(args.get(field) for field in ("region", "start_date", "end_date", "platform", "source_group")):
            return None
        for field in ("region", "start_date", "end_date", "platform", "source_group"):
            if field in args:
                args[field] = None
        result, record = self._execute_one(ProposedToolCall(call.name, args))
        record.recovered = True
        return result, record

    @staticmethod
    def _deduplicate_evidence(results: list[ToolResult]) -> list[Evidence]:
        best: dict[str, Evidence] = {}
        for result in results:
            for item in result.evidence:
                current = best.get(item.doc_id)
                if current is None or item.score > current.score:
                    best[item.doc_id] = item
        ordered = sorted(best.values(), key=lambda item: (-item.score, item.doc_id))[:8]
        return [item.model_copy(update={"rank": rank}) for rank, item in enumerate(ordered, start=1)]

    @staticmethod
    def _synthesize(question: str, results: list[ToolResult], evidence: list[Evidence]) -> str:
        if not evidence:
            return "The indexed evidence is insufficient to answer this question safely. Narrow the region, period, or housing topic."
        findings = []
        for item in evidence[:4]:
            findings.append(f"- {item.snippet} [{item.doc_id}]")
        structured = []
        for result in results:
            if result.data:
                compact = json.dumps(result.data, ensure_ascii=False, default=str, sort_keys=True)
                if len(compact) > 300:
                    compact = compact[:299] + "…"
                structured.append(f"- `{result.tool_name}`: {compact}")
        sections = [
            "Evidence-grounded result (online discussion is a signal, not a prevalence estimate):",
            *findings,
        ]
        if structured:
            sections.extend(("\nTool outputs:", *structured))
        sections.append("\nUse the cited source records and their data version before making policy or financial decisions.")
        return "\n".join(sections)

    def run(self, request: AgentQueryRequest) -> AgentQueryResponse:
        trace = TraceRecord(trace_id=uuid.uuid4().hex, question=request.question)
        started = time.perf_counter()
        self._append_state(trace, AgentState.RECEIVE)
        self.metrics.increment("queries_total")
        try:
            self._append_state(trace, AgentState.NORMALIZE)
            inferred_regions = [region.value for region in regions_in_text(request.question)]
            trace.normalized_query = {
                "question": " ".join(request.question.split()),
                "explicit_region": request.region.value if request.region else None,
                "inferred_regions": inferred_regions,
                "start_date": request.start_date.isoformat() if request.start_date else None,
                "end_date": request.end_date.isoformat() if request.end_date else None,
            }

            if request.question.lower().strip(" ?.!") in VAGUE_QUERIES:
                self._append_state(trace, AgentState.CLARIFY)
                trace.status = "clarification_required"
                trace.completed_at = datetime.now(timezone.utc)
                self.traces.put(trace)
                self.metrics.increment("clarifications_total")
                return AgentQueryResponse(
                    trace_id=trace.trace_id,
                    status="clarification_required",
                    answer="Please specify a housing topic and, if relevant, an Australian region or time period.",
                    clarification="For example: Compare rental-stress discussion with official context in Victoria during 2026.",
                    data_version=self.registry.backend.data_version,
                )

            self._append_state(trace, AgentState.PLAN)
            selected_planner: Planner = self.model_planner if request.use_model and self.model_planner else self.planner
            plan = self._plan(request, selected_planner)
            budget = min(self.max_tool_calls, request.max_tool_calls)
            unique_calls: list[ProposedToolCall] = []
            signatures = set()
            for call in plan.calls:
                signature = self._signature(call)
                if signature in signatures:
                    continue
                signatures.add(signature)
                self.registry.validate(call.name, call.arguments)
                unique_calls.append(call)
                if len(unique_calls) >= budget:
                    break
            trace.planned_tools = [{"name": call.name, "arguments": json.loads(json.dumps(call.arguments, default=str))} for call in unique_calls]

            self._append_state(trace, AgentState.EXECUTE)
            results: list[ToolResult] = []
            for call in unique_calls:
                if len(trace.tool_calls) >= budget:
                    break
                result, record = self._execute_one(call)
                trace.tool_calls.append(record)
                self.metrics.increment(f"tool_{record.status}_total")
                self.metrics.observe_ms("tool_duration", record.duration_ms)
                if result is None and record.status in {"error", "timeout"} and len(trace.tool_calls) < budget:
                    result, retry_record = self._execute_one(call)
                    retry_record.recovered = True
                    trace.tool_calls.append(retry_record)
                if result and not result.evidence and len(trace.tool_calls) < budget:
                    recovered = self._recover_empty(call)
                    if recovered:
                        retry_result, retry_record = recovered
                        trace.tool_calls.append(retry_record)
                        if retry_result:
                            result = retry_result
                if result:
                    results.append(result)

            self._append_state(trace, AgentState.VERIFY)
            evidence = self._deduplicate_evidence(results)
            status = "completed" if evidence else "insufficient_evidence"
            self._append_state(trace, AgentState.SYNTHESIZE)
            answer = self._synthesize(request.question, results, evidence)
            self._append_state(trace, AgentState.DONE)

            cost = self._cost_record(plan)
            trace.status = status
            trace.citation_ids = [item.doc_id for item in evidence]
            trace.cost = cost
            trace.completed_at = datetime.now(timezone.utc)
            self.traces.put(trace)
            elapsed = (time.perf_counter() - started) * 1000
            self.metrics.observe_ms("query_duration", elapsed)
            self.metrics.increment(f"query_{status}_total")
            return AgentQueryResponse(
                trace_id=trace.trace_id,
                status=status,
                answer=answer,
                citations=evidence,
                tool_calls=trace.tool_calls,
                cost=cost,
                data_version=self.registry.backend.data_version,
            )
        except Exception as exc:
            self._append_state(trace, AgentState.FAILED)
            trace.status = "failed"
            trace.completed_at = datetime.now(timezone.utc)
            self.traces.put(trace)
            self.metrics.increment("query_failed_total")
            return AgentQueryResponse(
                trace_id=trace.trace_id,
                status="failed",
                answer="The request failed safely without executing unrestricted queries.",
                data_version=self.registry.backend.data_version,
                clarification=f"Retry with a narrower question. Error category: {type(exc).__name__}",
            )

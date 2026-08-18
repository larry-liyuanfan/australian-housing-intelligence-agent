from __future__ import annotations

from dataclasses import dataclass

from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse

from .agent import HousingAgent
from .cache import InMemoryTTLCache, RedisCache
from .config import Settings
from .corpus import DATA_VERSION, fixture_documents
from .modelstudio import ModelStudioClient, ModelStudioReranker
from .observability import Metrics
from .planning import ModelStudioPlanner
from .retrieval import ElasticsearchHybridSearchBackend, LocalHybridSearchBackend
from .schemas import AgentQueryRequest, AgentQueryResponse, TraceRecord
from .tools import ToolRegistry
from .traces import TraceStore


@dataclass(slots=True)
class AppContainer:
    settings: Settings
    agent: HousingAgent
    traces: TraceStore
    metrics: Metrics
    registry: ToolRegistry


def create_container(settings: Settings | None = None) -> AppContainer:
    settings = settings or Settings.from_env()
    documents = fixture_documents()
    model_client = None
    if settings.model_configured:
        model_client = ModelStudioClient(
            base_url=settings.model_base_url or "",
            api_key=settings.model_api_key or "",
            chat_model=settings.chat_model,
            embedding_model=settings.embedding_model,
            rerank_model=settings.rerank_model,
            rerank_path=settings.rerank_path,
        )
    backend = LocalHybridSearchBackend(documents, data_version=DATA_VERSION)
    if settings.backend == "elasticsearch":
        try:
            from elasticsearch import Elasticsearch
            client = Elasticsearch(settings.elasticsearch_url, api_key=settings.elasticsearch_api_key) if settings.elasticsearch_api_key else Elasticsearch(settings.elasticsearch_url)
            backend = ElasticsearchHybridSearchBackend(
                client, documents, data_version="elasticsearch-live-with-local-fallback-v1",
                embedder=model_client.embedding if model_client else None,
                reranker=ModelStudioReranker(model_client) if model_client else None,
            )
        except (ImportError, Exception):
            backend = LocalHybridSearchBackend(documents, data_version=DATA_VERSION)

    cache = InMemoryTTLCache()
    if settings.cache == "redis":
        try:
            cache = RedisCache(settings.redis_url)
        except RuntimeError:
            cache = InMemoryTTLCache()

    model_planner = None
    if model_client:
        model_planner = ModelStudioPlanner(model_client)

    traces = TraceStore(settings.trace_limit)
    metrics = Metrics()
    registry = ToolRegistry(backend)
    agent = HousingAgent(
        registry, traces, cache, metrics,
        model_planner=model_planner,
        max_tool_calls=settings.max_tool_calls,
        tool_timeout_seconds=settings.tool_timeout_seconds,
    )
    return AppContainer(settings=settings, agent=agent, traces=traces, metrics=metrics, registry=registry)


def create_app(container: AppContainer | None = None) -> FastAPI:
    container = container or create_container()
    app = FastAPI(
        title="Australian Housing Intelligence Agent",
        version="0.1.0",
        description="Typed, evidence-grounded Agentic Search over discussion signals and official context.",
    )
    app.state.container = container

    @app.get("/healthz")
    def health() -> dict[str, str]:
        return {"status": "ok", "backend": container.settings.backend, "data_version": container.registry.backend.data_version}

    @app.post("/api/agent/query", response_model=AgentQueryResponse)
    def query(request: AgentQueryRequest) -> AgentQueryResponse:
        return container.agent.run(request)

    @app.get("/api/agent/traces/{trace_id}", response_model=TraceRecord)
    def trace(trace_id: str) -> TraceRecord:
        record = container.traces.get(trace_id)
        if record is None:
            raise HTTPException(status_code=404, detail="trace not found")
        return record

    @app.get("/api/tools")
    def tools() -> dict[str, object]:
        return {"tools": container.registry.model_studio_specs(), "arbitrary_dsl_allowed": False}

    @app.get("/metrics", response_class=PlainTextResponse)
    def metrics() -> str:
        return container.metrics.render_prometheus()

    return app


app = create_app()

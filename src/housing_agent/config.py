from __future__ import annotations

import os
from dataclasses import dataclass


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


@dataclass(frozen=True, slots=True)
class Settings:
    backend: str = "local"
    cache: str = "memory"
    max_tool_calls: int = 4
    tool_timeout_seconds: float = 3.0
    trace_limit: int = 1000
    elasticsearch_url: str = "http://localhost:9200"
    elasticsearch_api_key: str | None = None
    redis_url: str = "redis://localhost:6379/0"
    model_base_url: str | None = None
    model_api_key: str | None = None
    chat_model: str = "qwen-plus"
    embedding_model: str = "text-embedding-v4"
    rerank_model: str = "qwen3-rerank"
    rerank_path: str = "/reranks"

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            backend=os.getenv("HOUSING_BACKEND", "local").lower(),
            cache=os.getenv("HOUSING_CACHE", "memory").lower(),
            max_tool_calls=min(4, max(1, _int("HOUSING_MAX_TOOL_CALLS", 4))),
            tool_timeout_seconds=max(0.1, _float("HOUSING_TOOL_TIMEOUT_SECONDS", 3.0)),
            trace_limit=max(10, _int("HOUSING_TRACE_LIMIT", 1000)),
            elasticsearch_url=os.getenv("ELASTICSEARCH_URL", "http://localhost:9200"),
            elasticsearch_api_key=os.getenv("ELASTICSEARCH_API_KEY") or None,
            redis_url=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
            model_base_url=(os.getenv("MODEL_STUDIO_BASE_URL") or None),
            model_api_key=(os.getenv("MODEL_STUDIO_API_KEY") or None),
            chat_model=os.getenv("MODEL_STUDIO_CHAT_MODEL", "qwen-plus"),
            embedding_model=os.getenv("MODEL_STUDIO_EMBEDDING_MODEL", "text-embedding-v4"),
            rerank_model=os.getenv("MODEL_STUDIO_RERANK_MODEL", "qwen3-rerank"),
            rerank_path=os.getenv("MODEL_STUDIO_RERANK_PATH", "/reranks"),
        )

    @property
    def model_configured(self) -> bool:
        return bool(self.model_base_url and self.model_api_key)

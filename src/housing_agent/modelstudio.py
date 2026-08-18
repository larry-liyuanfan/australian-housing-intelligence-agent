from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from .retrieval import LexicalReranker
from .schemas import HousingDocument


class ModelStudioError(RuntimeError):
    pass


@dataclass(slots=True)
class ModelStudioClient:
    """Minimal environment-configured client; credentials are never persisted."""

    base_url: str
    api_key: str
    chat_model: str
    embedding_model: str
    rerank_model: str
    rerank_path: str = "/reranks"
    timeout_seconds: float = 10.0

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = self.base_url.rstrip("/") + "/" + path.lstrip("/")
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise ModelStudioError(f"Model Studio request failed: {type(exc).__name__}") from exc

    def embedding(self, text: str) -> list[float]:
        result = self._post("/embeddings", {"model": self.embedding_model, "input": text})
        try:
            return [float(value) for value in result["data"][0]["embedding"]]
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise ModelStudioError("invalid embedding response") from exc

    def rerank(self, query: str, documents: list[str], top_n: int) -> list[tuple[int, float]]:
        result = self._post(self.rerank_path, {"model": self.rerank_model, "query": query, "documents": documents, "top_n": top_n})
        rows = result.get("results") or result.get("output", {}).get("results") or []
        try:
            return [(int(row["index"]), float(row.get("relevance_score", row.get("score", 0.0)))) for row in rows]
        except (KeyError, TypeError, ValueError) as exc:
            raise ModelStudioError("invalid rerank response") from exc

    def chat_with_tools(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> dict[str, Any]:
        return self._post("/chat/completions", {"model": self.chat_model, "messages": messages, "tools": tools, "tool_choice": "auto", "temperature": 0})


class ModelStudioReranker:
    def __init__(self, client: ModelStudioClient, fallback: LexicalReranker | None = None) -> None:
        self.client = client
        self.fallback = fallback or LexicalReranker()

    def rerank(self, query: str, documents: list[HousingDocument], scores: list[float]) -> list[tuple[HousingDocument, float]]:
        try:
            ranked = self.client.rerank(query, [f"{doc.title}\n{doc.text}" for doc in documents], len(documents))
            return [(documents[index], score) for index, score in ranked if 0 <= index < len(documents)]
        except ModelStudioError:
            return self.fallback.rerank(query, documents, scores)

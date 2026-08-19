from __future__ import annotations

import hashlib
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from typing import Any, Callable, Iterable, Protocol

from .schemas import AustralianRegion, Evidence, HousingDocument


TOKEN_RE = re.compile(r"[a-z0-9]+")
QUERY_STOPWORDS = {
    "a", "an", "and", "are", "about", "for", "from", "how", "in", "is", "of", "on", "the", "to", "what", "with",
    "housing", "australia", "australian", "discussion", "official", "evidence", "please", "show", "tell",
}


def tokenize(text: str) -> list[str]:
    return TOKEN_RE.findall(text.lower())


def _snippet(text: str, limit: int = 240) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


class SearchBackend(Protocol):
    data_version: str

    def search(
        self,
        corpus: str,
        query: str,
        *,
        region: AustralianRegion | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        top_k: int = 5,
        platform: str | None = None,
        source_group: str | None = None,
    ) -> list[Evidence]: ...

    def aggregate_topic(self, topic: str, *, region: AustralianRegion | None = None, platform: str | None = None) -> dict[str, Any]: ...

    def sentiment_trend(self, topic: str, *, region: AustralianRegion | None = None, start_date: date | None = None, end_date: date | None = None) -> dict[str, Any]: ...

    def coverage(self, corpus: str, *, region: AustralianRegion | None = None) -> dict[str, Any]: ...


class Reranker(Protocol):
    def rerank(self, query: str, documents: list[HousingDocument], scores: list[float]) -> list[tuple[HousingDocument, float]]: ...


class LexicalReranker:
    """Deterministic cross-feature fallback used when no model API is configured."""

    def rerank(self, query: str, documents: list[HousingDocument], scores: list[float]) -> list[tuple[HousingDocument, float]]:
        q_tokens = set(tokenize(query))
        ranked: list[tuple[HousingDocument, float]] = []
        for doc, base in zip(documents, scores, strict=True):
            title = set(tokenize(doc.title))
            text = set(tokenize(doc.text))
            title_overlap = len(q_tokens & title) / max(1, len(q_tokens))
            body_overlap = len(q_tokens & text) / max(1, len(q_tokens))
            phrase = 1.0 if query.lower() in (doc.title + " " + doc.text).lower() else 0.0
            ranked.append((doc, base + 0.12 * title_overlap + 0.05 * body_overlap + 0.03 * phrase))
        return sorted(ranked, key=lambda item: (-item[1], item[0].doc_id))


@dataclass(slots=True)
class _Scored:
    doc: HousingDocument
    score: float


class LocalHybridSearchBackend:
    """Small, dependency-free BM25 + hashed-dense + RRF reference backend."""

    def __init__(self, documents: Iterable[HousingDocument], *, data_version: str, reranker: Reranker | None = None) -> None:
        self.documents = list(documents)
        self.data_version = data_version
        self.reranker = reranker or LexicalReranker()
        self._tokens = {doc.doc_id: tokenize(f"{doc.title} {doc.text} {doc.topic}") for doc in self.documents}
        self._df: dict[str, Counter[str]] = {}
        for corpus in ("discussion", "official"):
            counter: Counter[str] = Counter()
            for doc in self.documents:
                if doc.corpus == corpus:
                    counter.update(set(self._tokens[doc.doc_id]))
            self._df[corpus] = counter

    def _filtered(
        self,
        corpus: str,
        region: AustralianRegion | None,
        start_date: date | None,
        end_date: date | None,
        platform: str | None,
        source_group: str | None,
    ) -> list[HousingDocument]:
        result = []
        for doc in self.documents:
            if doc.corpus != corpus:
                continue
            if region and doc.region not in (region, AustralianRegion.NATIONAL):
                continue
            if start_date and doc.period and doc.period < start_date:
                continue
            if end_date and doc.period and doc.period > end_date:
                continue
            if platform and doc.platform != platform:
                continue
            if source_group and source_group.lower() not in doc.source.lower():
                continue
            result.append(doc)
        return result

    def _bm25(self, corpus: str, query: str, docs: list[HousingDocument]) -> list[_Scored]:
        q_tokens = tokenize(query)
        n = max(1, sum(1 for doc in self.documents if doc.corpus == corpus))
        avgdl = sum(len(self._tokens[d.doc_id]) for d in docs) / max(1, len(docs))
        k1, b = 1.5, 0.75
        ranked = []
        for doc in docs:
            tokens = self._tokens[doc.doc_id]
            tf = Counter(tokens)
            score = 0.0
            for term in q_tokens:
                df = self._df[corpus].get(term, 0)
                idf = math.log(1.0 + (n - df + 0.5) / (df + 0.5))
                freq = tf.get(term, 0)
                denom = freq + k1 * (1 - b + b * len(tokens) / max(1.0, avgdl))
                score += idf * (freq * (k1 + 1)) / max(1e-9, denom)
            ranked.append(_Scored(doc, score))
        return sorted(ranked, key=lambda item: (-item.score, item.doc.doc_id))

    @staticmethod
    def _hashed_vector(tokens: list[str], dimensions: int = 128) -> dict[int, float]:
        vector: defaultdict[int, float] = defaultdict(float)
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign
        norm = math.sqrt(sum(value * value for value in vector.values())) or 1.0
        return {key: value / norm for key, value in vector.items()}

    def _dense(self, query: str, docs: list[HousingDocument]) -> list[_Scored]:
        qv = self._hashed_vector(tokenize(query))
        ranked = []
        for doc in docs:
            dv = self._hashed_vector(self._tokens[doc.doc_id])
            score = sum(value * dv.get(index, 0.0) for index, value in qv.items())
            ranked.append(_Scored(doc, score))
        return sorted(ranked, key=lambda item: (-item.score, item.doc.doc_id))

    @staticmethod
    def _rrf(rankings: list[list[_Scored]], k: int = 60) -> list[_Scored]:
        totals: defaultdict[str, float] = defaultdict(float)
        docs: dict[str, HousingDocument] = {}
        for ranking in rankings:
            for rank, item in enumerate(ranking, start=1):
                totals[item.doc.doc_id] += 1.0 / (k + rank)
                docs[item.doc.doc_id] = item.doc
        return sorted((_Scored(docs[key], value) for key, value in totals.items()), key=lambda item: (-item.score, item.doc.doc_id))

    def search(
        self,
        corpus: str,
        query: str,
        *,
        region: AustralianRegion | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        top_k: int = 5,
        platform: str | None = None,
        source_group: str | None = None,
    ) -> list[Evidence]:
        if corpus not in {"discussion", "official"}:
            raise ValueError("corpus must be discussion or official")
        docs = self._filtered(corpus, region, start_date, end_date, platform, source_group)
        if not docs:
            return []
        important = {term for term in tokenize(query) if term not in QUERY_STOPWORDS and len(term) > 2}
        if important:
            relevant = [doc for doc in docs if important & set(self._tokens[doc.doc_id])]
            if relevant:
                docs = relevant
            elif len(important) >= 2:
                return []
        bm25 = self._bm25(corpus, query, docs)[: max(top_k * 4, 20)]
        dense = self._dense(query, docs)[: max(top_k * 4, 20)]
        fused = self._rrf([bm25, dense])[: max(top_k * 2, 10)]
        reranked = self.reranker.rerank(query, [item.doc for item in fused], [item.score for item in fused])[:top_k]
        return [
            Evidence(
                doc_id=doc.doc_id,
                corpus=doc.corpus,
                title=doc.title,
                snippet=_snippet(doc.text),
                source=doc.source,
                region=doc.region,
                period=doc.period,
                url=doc.url,
                score=round(score, 8),
                rank=rank,
            )
            for rank, (doc, score) in enumerate(reranked, start=1)
        ]

    def aggregate_topic(self, topic: str, *, region: AustralianRegion | None = None, platform: str | None = None) -> dict[str, Any]:
        matches = self._filtered("discussion", region, None, None, platform, None)
        query_terms = set(tokenize(topic))
        matches = [doc for doc in matches if query_terms & set(tokenize(f"{doc.topic} {doc.title} {doc.text}"))]
        by_platform = Counter(doc.platform for doc in matches)
        by_region = Counter(doc.region.value for doc in matches)
        return {"topic": topic, "count": len(matches), "by_platform": dict(sorted(by_platform.items())), "by_region": dict(sorted(by_region.items()))}

    def sentiment_trend(self, topic: str, *, region: AustralianRegion | None = None, start_date: date | None = None, end_date: date | None = None) -> dict[str, Any]:
        docs = self._filtered("discussion", region, start_date, end_date, None, None)
        q = set(tokenize(topic))
        docs = [doc for doc in docs if doc.sentiment is not None and q & set(tokenize(f"{doc.topic} {doc.text}"))]
        points = [{"period": doc.period.isoformat() if doc.period else None, "mean_sentiment": doc.sentiment, "count": 1} for doc in sorted(docs, key=lambda d: (d.period or date.min, d.doc_id))]
        return {"topic": topic, "points": points, "interpretation": "Synthetic fixture sentiment is a pipeline check, not a population estimate."}

    def coverage(self, corpus: str, *, region: AustralianRegion | None = None) -> dict[str, Any]:
        corpora = {"discussion", "official"} if corpus == "both" else {corpus}
        docs = [doc for doc in self.documents if doc.corpus in corpora and (not region or doc.region in (region, AustralianRegion.NATIONAL))]
        periods = [doc.period for doc in docs if doc.period]
        return {
            "corpus": corpus,
            "region": region.value if region else None,
            "document_count": len(docs),
            "sources": sorted({doc.source for doc in docs}),
            "date_min": min(periods).isoformat() if periods else None,
            "date_max": max(periods).isoformat() if periods else None,
            "data_version": self.data_version,
            "warning": "Counts describe indexed records, not housing-insecurity prevalence.",
        }


class ElasticsearchHybridSearchBackend(LocalHybridSearchBackend):
    """Allowlisted Elasticsearch adapter with local analytics fallbacks.

    It generates every DSL clause itself. Callers can supply only typed query,
    region/date/platform/source filters; arbitrary Elasticsearch JSON is never accepted.
    Dense retrieval is activated when an embedding provider is supplied.
    """

    DISCUSSION_INDEX = "housing_posts"
    OFFICIAL_INDEX = "official_housing_rows"

    def __init__(
        self,
        client: Any,
        fallback_documents: Iterable[HousingDocument],
        *,
        data_version: str,
        embedder: Callable[[str], list[float]] | None = None,
        reranker: Reranker | None = None,
    ) -> None:
        super().__init__(fallback_documents, data_version=data_version, reranker=reranker)
        self.client = client
        self.embedder = embedder

    @classmethod
    def build_bm25_body(
        cls,
        corpus: str,
        query: str,
        *,
        region: AustralianRegion | None,
        start_date: date | None,
        end_date: date | None,
        top_k: int,
        platform: str | None,
        source_group: str | None,
    ) -> dict[str, Any]:
        if corpus not in {"discussion", "official"}:
            raise ValueError("invalid corpus")
        filters: list[dict[str, Any]] = []
        if region:
            field = "city_context" if corpus == "discussion" else "state"
            filters.append({"terms": {field: [region.value, "AU"]}})
        if start_date or end_date:
            field = "created_at" if corpus == "discussion" else "period"
            bounds: dict[str, str] = {}
            if start_date:
                bounds["gte"] = start_date.isoformat()
            if end_date:
                bounds["lte"] = end_date.isoformat()
            filters.append({"range": {field: bounds}})
        if platform and corpus == "discussion":
            filters.append({"term": {"platform": platform}})
        if source_group and corpus == "official":
            filters.append({"term": {"source_group": source_group}})
        fields = ["title^2", "text", "topic^1.5"] if corpus == "discussion" else ["row_label^2", "text", "source_group"]
        return {
            "size": top_k,
            "_source": ["doc_id", "title", "row_label", "text", "source", "source_group", "city_context", "state", "created_at", "period", "topic", "sentiment", "platform", "url"],
            "query": {"bool": {"must": [{"multi_match": {"query": query, "fields": fields}}], "filter": filters}},
        }

    def search(self, corpus: str, query: str, **kwargs: Any) -> list[Evidence]:
        options = {
            "region": None,
            "start_date": None,
            "end_date": None,
            "top_k": 5,
            "platform": None,
            "source_group": None,
            **kwargs,
        }
        body = self.build_bm25_body(corpus, query, **options)
        try:
            response = self.client.search(index=self.DISCUSSION_INDEX if corpus == "discussion" else self.OFFICIAL_INDEX, body=body)
            rankings = [response.get("hits", {}).get("hits", [])]
            if self.embedder:
                try:
                    vector = self.embedder(query)
                    dense_body: dict[str, Any] = {
                        "size": kwargs["top_k"],
                        "_source": body["_source"],
                        "knn": {
                            "field": "embedding",
                            "query_vector": vector,
                            "k": options["top_k"],
                            "num_candidates": max(50, options["top_k"] * 4),
                        },
                    }
                    filters = body["query"]["bool"]["filter"]
                    if filters:
                        dense_body["knn"]["filter"] = filters
                    dense_response = self.client.search(index=self.DISCUSSION_INDEX if corpus == "discussion" else self.OFFICIAL_INDEX, body=dense_body)
                    rankings.append(dense_response.get("hits", {}).get("hits", []))
                except Exception:
                    pass
            by_id: dict[str, dict[str, Any]] = {}
            rrf_scores: defaultdict[str, float] = defaultdict(float)
            for ranking in rankings:
                for rank, hit in enumerate(ranking, start=1):
                    key = str(hit.get("_id") or hit.get("_source", {}).get("doc_id"))
                    by_id[key] = hit
                    rrf_scores[key] += 1.0 / (60 + rank)
            hits = [by_id[key] for key in sorted(by_id, key=lambda item: (-rrf_scores[item], item))]
            if not hits:
                return super().search(corpus, query, **options)
            docs: list[HousingDocument] = []
            scores: list[float] = []
            for hit in hits:
                src = hit.get("_source", {})
                region = src.get("city_context") or src.get("state") or "AU"
                if region not in AustralianRegion._value2member_map_:
                    region = "AU"
                raw_period = src.get("created_at") or src.get("period")
                period = None
                if isinstance(raw_period, str):
                    try:
                        period = date.fromisoformat(raw_period[:10])
                    except ValueError:
                        period = None
                docs.append(HousingDocument(
                    doc_id=str(src.get("doc_id") or hit.get("_id")),
                    corpus=corpus,
                    title=str(src.get("title") or src.get("row_label") or "Untitled evidence"),
                    text=str(src.get("text") or ""),
                    source=str(src.get("source") or src.get("source_group") or "indexed-source"),
                    region=AustralianRegion(region),
                    period=period,
                    topic=str(src.get("topic") or src.get("row_label") or "housing"),
                    sentiment=src.get("sentiment"),
                    url=src.get("url"),
                    platform=src.get("platform") if src.get("platform") in {"bluesky", "mastodon", "youtube", "gdelt"} else "official",
                ))
                key = str(hit.get("_id") or src.get("doc_id"))
                scores.append(rrf_scores.get(key, float(hit.get("_score") or 0.0)))
            ranked = self.reranker.rerank(query, docs, scores)
            return [Evidence(doc_id=doc.doc_id, corpus=doc.corpus, title=doc.title, snippet=_snippet(doc.text), source=doc.source, region=doc.region, period=doc.period, url=doc.url, score=round(score, 8), rank=rank) for rank, (doc, score) in enumerate(ranked, start=1)]
        except Exception:
            return super().search(corpus, query, **options)

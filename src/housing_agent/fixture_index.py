"""Seed only the public deidentified fixtures for infrastructure smoke tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import Settings
from .corpus import DATA_VERSION, fixture_documents
from .retrieval import ElasticsearchHybridSearchBackend


def seed_fixture_indices(settings: Settings, mapping_dir: Path) -> dict[str, Any]:
    try:
        from elasticsearch import Elasticsearch
    except ImportError as exc:
        raise RuntimeError("install the elasticsearch extra") from exc
    client = (
        Elasticsearch(settings.elasticsearch_url, api_key=settings.elasticsearch_api_key)
        if settings.elasticsearch_api_key
        else Elasticsearch(settings.elasticsearch_url)
    )
    client.info()
    definitions = {
        "discussion": (
            ElasticsearchHybridSearchBackend.DISCUSSION_INDEX,
            mapping_dir / "discussion-mapping.json",
        ),
        "official": (
            ElasticsearchHybridSearchBackend.OFFICIAL_INDEX,
            mapping_dir / "official-mapping.json",
        ),
    }
    for _, (index_name, mapping_path) in definitions.items():
        if not client.indices.exists(index=index_name):
            definition = json.loads(mapping_path.read_text(encoding="utf-8"))
            client.indices.create(index=index_name, **definition)
    written = {"discussion": 0, "official": 0}
    for document in fixture_documents():
        if document.corpus == "discussion":
            index_name = definitions["discussion"][0]
            payload = {
                "doc_id": document.doc_id,
                "platform": document.platform,
                "title": document.title,
                "text": document.text,
                "created_at": document.period.isoformat() if document.period else None,
                "city_context": document.region.value,
                "topic": document.topic,
                "sentiment": document.sentiment,
                "source": document.source,
                "url": document.url,
            }
            written["discussion"] += 1
        else:
            index_name = definitions["official"][0]
            payload = {
                "doc_id": document.doc_id,
                "source_group": document.source,
                "state": document.region.value,
                "period": document.period.isoformat() if document.period else None,
                "row_label": document.title,
                "text": document.text,
                "source": document.source,
                "url": document.url,
            }
            written["official"] += 1
        client.index(index=index_name, id=document.doc_id, document=payload)
    for _, (index_name, _) in definitions.items():
        client.indices.refresh(index=index_name)
    counts = {
        corpus: int(client.count(index=index_name)["count"])
        for corpus, (index_name, _) in definitions.items()
    }
    return {
        "scope": "public deidentified fixture infrastructure smoke test; not a real housing corpus",
        "data_version": DATA_VERSION,
        "written": written,
        "index_counts": counts,
        "indexes": {corpus: values[0] for corpus, values in definitions.items()},
    }

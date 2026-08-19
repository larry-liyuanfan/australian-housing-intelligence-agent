from __future__ import annotations

from housing_agent.corpus import DATA_VERSION, fixture_documents
from housing_agent.retrieval import ElasticsearchHybridSearchBackend, LocalHybridSearchBackend
from housing_agent.schemas import AustralianRegion


def test_local_hybrid_retrieval_respects_corpus_and_region() -> None:
    backend = LocalHybridSearchBackend(fixture_documents(), data_version=DATA_VERSION)
    hits = backend.search("discussion", "rent increase inspection", region=AustralianRegion.VIC, top_k=5)
    assert hits
    assert all(hit.corpus == "discussion" for hit in hits)
    assert hits[0].doc_id == "d01"


def test_unrelated_multi_term_query_returns_no_evidence() -> None:
    backend = LocalHybridSearchBackend(fixture_documents(), data_version=DATA_VERSION)
    assert backend.search("official", "zebrafish quantum lattice", top_k=5) == []


def test_elasticsearch_query_is_generated_from_allowlisted_fields() -> None:
    body = ElasticsearchHybridSearchBackend.build_bm25_body(
        "discussion", "rental stress", region=AustralianRegion.VIC,
        start_date=None, end_date=None, top_k=5, platform="bluesky", source_group=None,
    )
    serialized = str(body)
    assert "rental stress" in serialized
    assert "city_context" in serialized
    assert "script" not in serialized
    assert "delete" not in serialized


def test_elasticsearch_adapter_supplies_optional_filter_defaults() -> None:
    class EmptyClient:
        def search(self, **kwargs):
            return {"hits": {"hits": []}}

    backend = ElasticsearchHybridSearchBackend(
        EmptyClient(), fixture_documents(), data_version="fixture-es",
    )
    hits = backend.search("discussion", "rental stress", region=AustralianRegion.VIC, top_k=2)
    assert hits
    assert all(hit.corpus == "discussion" for hit in hits)

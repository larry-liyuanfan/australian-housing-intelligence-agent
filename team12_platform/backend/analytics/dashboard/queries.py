# COMP90024 Team 12
# Public attribution: COMP90024 Team 12; member identities removed from this portfolio copy.

"""Dashboard-level query helpers that combine social and official summaries."""

from __future__ import annotations

from typing import Any, Dict

from elasticsearch import Elasticsearch

from backend.analytics.core.utils import count_index, terms_distribution
from backend.analytics.sentiment.queries import housing_sentiment_summary


def dashboard_overview(
    es: Elasticsearch,
    housing_index: str,
    official_index: str,
) -> Dict[str, Any]:
    """Return the compact overview shown near the top of the notebook."""
    return {
        "public_discourse": {
            "index": housing_index,
            "document_count": count_index(es, housing_index),
            "platforms": terms_distribution(
                es,
                housing_index,
                field="platform",
                size=20,
                label_name="platform",
            )["buckets"],
            "top_query_keywords": terms_distribution(
                es,
                housing_index,
                field="query_keyword",
                size=20,
                label_name="query_keyword",
            )["buckets"],
            "sentiment": housing_sentiment_summary(es, housing_index),
        },
        "official_evidence": {
            "index": official_index,
            "document_count": count_index(es, official_index),
            "source_groups": terms_distribution(
                es,
                official_index,
                field="source_group",
                size=20,
                label_name="source_group",
            )["buckets"],
            "states": terms_distribution(
                es,
                official_index,
                field="state",
                size=20,
                label_name="state",
            )["buckets"],
            "row_types": terms_distribution(
                es,
                official_index,
                field="row_type",
                size=20,
                label_name="row_type",
            )["buckets"],
        },
    }

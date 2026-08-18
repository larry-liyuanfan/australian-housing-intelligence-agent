# COMP90024 Team 12
# Public attribution: COMP90024 Team 12; member identities removed from this portfolio copy.

"""Topic and keyword query helpers used by the API and notebook."""

from __future__ import annotations

from typing import Any, Dict

from elasticsearch import Elasticsearch

from backend.analytics.core.utils import terms_distribution


def get_top_query_keywords(
    es: Elasticsearch,
    index: str,
    size: int = 50,
) -> Dict[str, Any]:
    """Return the most frequent query keywords in housing records."""
    return terms_distribution(
        es,
        index,
        field="query_keyword",
        size=size,
        label_name="query_keyword",
    )


def get_top_subtopics(
    es: Elasticsearch,
    index: str,
    size: int = 30,
) -> Dict[str, Any]:
    """Return the most frequent inferred housing subtopics."""
    return terms_distribution(
        es,
        index,
        field="subtopic",
        size=size,
        label_name="subtopic",
    )

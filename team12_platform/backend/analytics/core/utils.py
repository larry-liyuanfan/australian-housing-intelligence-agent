# COMP90024 Team 12
# Public attribution: COMP90024 Team 12; member identities removed from this portfolio copy.

"""Small shared helpers for Elasticsearch-backed analytics endpoints."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from elasticsearch import Elasticsearch


def clamp(value: int, minimum: int = 1, maximum: int = 100) -> int:
    """Clamp a numeric value to the accepted API range."""
    return max(minimum, min(value, maximum))


def count_index(es: Elasticsearch, index: str) -> int:
    """Return the current document count for an Elasticsearch index."""
    result = es.count(index=index)
    return int(result.get("count", 0))


def terms_distribution(
    es: Elasticsearch,
    index: str,
    field: str,
    size: int = 20,
    label_name: str = "key",
) -> Dict[str, Any]:
    """Return a common terms-aggregation payload for notebook charts."""
    size = clamp(size, 1, 200)
    body = {
        "size": 0,
        "aggs": {
            "distribution": {
                "terms": {
                    "field": field,
                    "size": size,
                }
            }
        },
    }

    result = es.search(index=index, body=body)
    buckets = result.get("aggregations", {}).get("distribution", {}).get("buckets", [])

    return {
        "index": index,
        "field": field,
        "total": result.get("hits", {}).get("total", {}),
        "buckets": [
            {
                label_name: bucket.get("key"),
                "count": bucket.get("doc_count"),
            }
            for bucket in buckets
        ],
    }


def build_filters(
    platform: Optional[str] = None,
    query_keyword: Optional[str] = None,
    city_context: Optional[str] = None,
    state: Optional[str] = None,
    source_group: Optional[str] = None,
    row_type: Optional[str] = None,
    period: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Build exact-match filters shared by social and official endpoints."""
    filters: List[Dict[str, Any]] = []

    if platform:
        filters.append({"term": {"platform": platform}})
    if query_keyword:
        filters.append({"term": {"query_keyword": query_keyword}})
    if city_context:
        filters.append({"term": {"city_context": city_context}})
    if state:
        filters.append({"term": {"state": state}})
    if source_group:
        filters.append({"term": {"source_group": source_group}})
    if row_type:
        filters.append({"term": {"row_type": row_type}})
    if period:
        filters.append({"term": {"period": period}})

    return filters

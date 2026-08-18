# COMP90024 Team 12
# Public attribution: COMP90024 Team 12; member identities removed from this portfolio copy.

"""Elasticsearch query helpers for official housing comparison data."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from elasticsearch import Elasticsearch

from backend.analytics.core.utils import clamp


OFFICIAL_SOURCE_FIELDS = [
    "doc_id",
    "source_file",
    "source_group",
    "record_index",
    "sheet",
    "state",
    "period",
    "row_type",
    "row_label",
    "text",
    "non_null_count",
    "numeric_count",
    "raw_data",
]


def get_official_count(es: Elasticsearch, index: str) -> int:
    """Return the total number of official-data rows in Elasticsearch."""
    result = es.count(index=index)
    return int(result.get("count", 0))


def terms_distribution(
    es: Elasticsearch,
    index: str,
    aggregation_name: str,
    field: str,
    label_name: str,
    size: int,
    order: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Shared terms aggregation shape used by the official-data endpoints."""
    terms: Dict[str, Any] = {
        "field": field,
        "size": size,
    }

    if order:
        terms["order"] = order

    body = {
        "size": 0,
        "aggs": {
            aggregation_name: {
                "terms": terms,
            }
        },
    }

    result = es.search(index=index, body=body)
    buckets = result.get("aggregations", {}).get(aggregation_name, {}).get("buckets", [])

    return {
        "index": index,
        "total": result.get("hits", {}).get("total", {}),
        "buckets": [
            {
                label_name: bucket.get("key"),
                "count": bucket.get("doc_count"),
            }
            for bucket in buckets
        ],
    }


def get_source_group_distribution(
    es: Elasticsearch,
    index: str,
    size: int = 30,
) -> Dict[str, Any]:
    """Return official-data counts by source group."""
    return terms_distribution(
        es,
        index,
        aggregation_name="by_source_group",
        field="source_group",
        label_name="source_group",
        size=size,
    )


def get_row_type_distribution(
    es: Elasticsearch,
    index: str,
    size: int = 20,
) -> Dict[str, Any]:
    """Return official-data counts by row type."""
    return terms_distribution(
        es,
        index,
        aggregation_name="by_row_type",
        field="row_type",
        label_name="row_type",
        size=size,
    )


def get_state_distribution(
    es: Elasticsearch,
    index: str,
    size: int = 20,
) -> Dict[str, Any]:
    """Return official-data counts by state or territory."""
    return terms_distribution(
        es,
        index,
        aggregation_name="by_state",
        field="state",
        label_name="state",
        size=size,
    )


def get_period_distribution(
    es: Elasticsearch,
    index: str,
    size: int = 50,
) -> Dict[str, Any]:
    """Return official-data counts by reporting period."""
    return terms_distribution(
        es,
        index,
        aggregation_name="by_period",
        field="period",
        label_name="period",
        size=size,
        order={"_key": "asc"},
    )


def build_filter_terms(
    source_group: Optional[str] = None,
    state: Optional[str] = None,
    row_type: Optional[str] = None,
    period: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Build Elasticsearch filter clauses from optional API parameters."""
    filters: List[Dict[str, Any]] = []

    if source_group:
        filters.append({"term": {"source_group": source_group}})
    if state:
        filters.append({"term": {"state": state}})
    if row_type:
        filters.append({"term": {"row_type": row_type}})
    if period:
        filters.append({"term": {"period": period}})

    return filters


def search_official_rows(
    es: Elasticsearch,
    index: str,
    query: str,
    size: int = 10,
    source_group: Optional[str] = None,
    state: Optional[str] = None,
    row_type: Optional[str] = None,
    period: Optional[str] = None,
) -> Dict[str, Any]:
    """Search official-data rows with optional source, state and period filters."""
    size = max(1, min(size, 100))
    filters = build_filter_terms(
        source_group=source_group,
        state=state,
        row_type=row_type,
        period=period,
    )

    if query:
        must_query: Dict[str, Any] = {
            "multi_match": {
                "query": query,
                "fields": ["text", "row_label"],
            }
        }
    else:
        must_query = {"match_all": {}}

    body = {
        "track_total_hits": True,
        "size": size,
        "query": {
            "bool": {
                "must": [must_query],
                "filter": filters,
            }
        },
        "_source": OFFICIAL_SOURCE_FIELDS,
    }

    result = es.search(index=index, body=body)
    hits = result.get("hits", {}).get("hits", [])

    return {
        "index": index,
        "query": query,
        "filters": {
            "source_group": source_group,
            "state": state,
            "row_type": row_type,
            "period": period,
        },
        "total": result.get("hits", {}).get("total", {}),
        "results": [
            {
                "score": hit.get("_score"),
                **hit.get("_source", {}),
            }
            for hit in hits
        ],
    }


def get_official_overview(es: Elasticsearch, index: str) -> Dict[str, Any]:
    """Build the official-data overview payload used by the dashboard."""
    return {
        "index": index,
        "document_count": get_official_count(es, index),
        "source_groups": get_source_group_distribution(es, index, size=20)["buckets"],
        "row_types": get_row_type_distribution(es, index, size=20)["buckets"],
        "states": get_state_distribution(es, index, size=20)["buckets"],
    }


def official_period_by_source_group(
    es: Elasticsearch,
    index: str,
    size: int = 20,
    period_size: int = 20,
) -> Dict[str, Any]:
    """Aggregate official-data coverage by period and source group."""
    size = clamp(size, 1, 100)
    period_size = clamp(period_size, 1, 100)

    body = {
        "size": 0,
        "aggs": {
            "by_source_group": {
                "terms": {
                    "field": "source_group",
                    "size": size,
                },
                "aggs": {
                    "by_period": {
                        "terms": {
                            "field": "period",
                            "size": period_size,
                            "order": {"_key": "asc"},
                        }
                    }
                },
            }
        },
    }

    result = es.search(index=index, body=body)
    buckets = result.get("aggregations", {}).get("by_source_group", {}).get("buckets", [])

    return {
        "index": index,
        "total": result.get("hits", {}).get("total", {}),
        "buckets": [
            {
                "source_group": bucket.get("key"),
                "count": bucket.get("doc_count"),
                "periods": [
                    {
                        "period": item.get("key"),
                        "count": item.get("doc_count"),
                    }
                    for item in bucket.get("by_period", {}).get("buckets", [])
                ],
            }
            for bucket in buckets
        ],
    }

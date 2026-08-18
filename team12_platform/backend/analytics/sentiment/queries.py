# COMP90024 Team 12
# Public attribution: COMP90024 Team 12; member identities removed from this portfolio copy.

"""Elasticsearch query helpers for sentiment analysis outputs."""

from __future__ import annotations

from typing import Any, Dict, Optional

from elasticsearch import Elasticsearch

from backend.analytics.core.utils import build_filters, clamp


def housing_sentiment_summary(es: Elasticsearch, index: str) -> Dict[str, Any]:
    """Aggregate overall sentiment labels for housing records."""
    body = {
        "size": 0,
        "aggs": {
            "by_sentiment_label": {
                "terms": {
                    "field": "sentiment_label",
                    "size": 10,
                }
            },
            "avg_sentiment": {
                "avg": {
                    "field": "sentiment",
                }
            },
            "sentiment_stats": {
                "stats": {
                    "field": "sentiment",
                }
            },
        },
    }

    result = es.search(index=index, body=body)
    buckets = result.get("aggregations", {}).get("by_sentiment_label", {}).get("buckets", [])

    return {
        "index": index,
        "total": result.get("hits", {}).get("total", {}),
        "average_sentiment": result.get("aggregations", {})
        .get("avg_sentiment", {})
        .get("value"),
        "sentiment_stats": result.get("aggregations", {}).get("sentiment_stats", {}),
        "buckets": [
            {
                "sentiment_label": bucket.get("key"),
                "count": bucket.get("doc_count"),
            }
            for bucket in buckets
        ],
    }


def housing_sentiment_by_platform(
    es: Elasticsearch,
    index: str,
    size: int = 20,
) -> Dict[str, Any]:
    """Aggregate average sentiment by platform."""
    size = clamp(size, 1, 100)
    body = {
        "size": 0,
        "aggs": {
            "by_platform": {
                "terms": {
                    "field": "platform",
                    "size": size,
                },
                "aggs": {
                    "avg_sentiment": {
                        "avg": {
                            "field": "sentiment",
                        }
                    },
                    "by_sentiment_label": {
                        "terms": {
                            "field": "sentiment_label",
                            "size": 10,
                        }
                    },
                },
            }
        },
    }

    result = es.search(index=index, body=body)
    platform_buckets = result.get("aggregations", {}).get("by_platform", {}).get("buckets", [])
    output = []

    for bucket in platform_buckets:
        sentiment_buckets = bucket.get("by_sentiment_label", {}).get("buckets", [])
        output.append(
            {
                "platform": bucket.get("key"),
                "count": bucket.get("doc_count"),
                "average_sentiment": bucket.get("avg_sentiment", {}).get("value"),
                "sentiment_labels": [
                    {
                        "sentiment_label": item.get("key"),
                        "count": item.get("doc_count"),
                    }
                    for item in sentiment_buckets
                ],
            }
        )

    return {
        "index": index,
        "total": result.get("hits", {}).get("total", {}),
        "buckets": output,
    }


def housing_sentiment_over_time(
    es: Elasticsearch,
    index: str,
    interval: str = "month",
    platform: Optional[str] = None,
    query_keyword: Optional[str] = None,
    city_context: Optional[str] = None,
) -> Dict[str, Any]:
    """Aggregate average sentiment over calendar intervals."""
    if interval not in {"day", "week", "month"}:
        interval = "month"

    filters = build_filters(
        platform=platform,
        query_keyword=query_keyword,
        city_context=city_context,
    )
    body = {
        "size": 0,
        "query": {
            "bool": {
                "filter": filters,
            }
        },
        "aggs": {
            "over_time": {
                "date_histogram": {
                    "field": "created_at",
                    "calendar_interval": interval,
                    "min_doc_count": 1,
                },
                "aggs": {
                    "avg_sentiment": {
                        "avg": {
                            "field": "sentiment",
                        }
                    },
                    "by_sentiment_label": {
                        "terms": {
                            "field": "sentiment_label",
                            "size": 10,
                        }
                    },
                },
            }
        },
    }

    result = es.search(index=index, body=body)
    time_buckets = result.get("aggregations", {}).get("over_time", {}).get("buckets", [])

    return {
        "index": index,
        "interval": interval,
        "filters": {
            "platform": platform,
            "query_keyword": query_keyword,
            "city_context": city_context,
        },
        "total": result.get("hits", {}).get("total", {}),
        "buckets": [
            {
                "period": bucket.get("key_as_string"),
                "count": bucket.get("doc_count"),
                "average_sentiment": bucket.get("avg_sentiment", {}).get("value"),
                "sentiment_labels": [
                    {
                        "sentiment_label": item.get("key"),
                        "count": item.get("doc_count"),
                    }
                    for item in bucket.get("by_sentiment_label", {}).get("buckets", [])
                ],
            }
            for bucket in time_buckets
        ],
    }

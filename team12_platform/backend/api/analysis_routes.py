# COMP90024 Team 12
# Public attribution: COMP90024 Team 12; member identities removed from this portfolio copy.

"""Analysis endpoints used by the notebook dashboard."""

from __future__ import annotations

import os
import re
from collections import Counter
from typing import Any, Dict, List, Optional

from flask import Blueprint, Flask, jsonify, request

try:
    from backend.analytics.core.es_client import get_es_client
    from backend.analytics.regional.queries import cleaned_city_context_distribution
except ModuleNotFoundError:
    from analytics.core.es_client import get_es_client
    from analytics.regional.queries import cleaned_city_context_distribution


analysis_bp = Blueprint("analysis", __name__, url_prefix="/api/analysis")


def get_housing_index() -> str:
    """Read the housing index name from configuration."""
    return os.getenv("ES_INDEX", "housing_posts")


def get_official_index() -> str:
    """Read the official-data index name from configuration."""
    return os.getenv("OFFICIAL_ES_INDEX", "official_housing_rows")


def clamp(value: int, minimum: int = 1, maximum: int = 100) -> int:
    """Clamp a numeric value to the accepted API range."""
    return max(minimum, min(value, maximum))


def parse_int_arg(
    name: str,
    default: int,
    minimum: int = 1,
    maximum: int = 100,
) -> int:
    """Read and validate an integer query parameter."""
    raw = request.args.get(name)

    if raw is None:
        return default

    try:
        value = int(raw)
    except ValueError:
        return default

    return clamp(value, minimum, maximum)


def optional_arg(name: str) -> Optional[str]:
    """Return a trimmed optional query parameter."""
    value = request.args.get(name)

    if value is None:
        return None

    value = value.strip()

    return value or None


def count_index(es, index: str) -> int:
    """Return the current document count for an Elasticsearch index."""
    result = es.count(index=index)
    return int(result.get("count", 0))


def terms_distribution(
    es,
    index: str,
    field: str,
    size: int = 20,
    label_name: str = "key",
) -> Dict[str, Any]:
    """Run a terms aggregation and return bucket counts."""
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

    buckets = (
        result.get("aggregations", {})
        .get("distribution", {})
        .get("buckets", [])
    )

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
    """Build Elasticsearch filters from common dashboard parameters."""
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


# Stopwords are applied before returning word-cloud tokens to the frontend.
WORD_CLOUD_STOPWORDS = {
    "the", "and", "for", "that", "with", "this", "from", "have", "has",
    "are", "was", "were", "will", "would", "could", "should", "can",
    "you", "your", "their", "they", "them", "our", "out", "about",
    "into", "than", "then", "there", "here", "when", "where", "what",
    "which", "who", "how", "why", "not", "but", "all", "any", "more",
    "most", "some", "such", "also", "just", "over", "under", "after",
    "before", "new", "one", "two", "three", "per", "via", "its",
    "been", "being", "had", "did", "does", "doing", "because",
    "australia", "australian", "housing", "house", "houses", "home",
    "homes", "property", "properties", "news", "said", "says", "say",
    "people", "year", "years", "month", "months", "week", "weeks",
    "time", "today", "report", "reports", "data", "source", "record",
    "records", "http", "https", "www", "com", "amp", "auspol"
}


def normalise_word(token: str) -> str:
    """Clean a token before adding it to the word-cloud vocabulary."""
    token = token.lower().strip("'’`-")

    if token.endswith("'s"):
        token = token[:-2]

    if token.endswith("ies") and len(token) > 4:
        token = token[:-3] + "y"
    elif token.endswith("s") and len(token) > 4:
        token = token[:-1]

    return token


def extract_word_cloud_tokens(text: str) -> List[str]:
    """Extract meaningful housing terms for the word-cloud view."""
    if not text:
        return []

    raw_tokens = re.findall(r"[A-Za-z][A-Za-z'\-]{2,}", text)

    tokens = []

    for raw in raw_tokens:
        token = normalise_word(raw)

        if len(token) < 3:
            continue

        if token in WORD_CLOUD_STOPWORDS:
            continue

        if token.isdigit():
            continue

        tokens.append(token)

    return tokens


def housing_word_cloud(
    es,
    index: str,
    source_size: int = 3000,
    word_size: int = 100,
    platform: Optional[str] = None,
    query_keyword: Optional[str] = None,
    subtopic: Optional[str] = None,
    city_context: Optional[str] = None,
) -> Dict[str, Any]:
    """Build word-cloud terms from recent housing records."""
    source_size = clamp(source_size, 100, 10000)
    word_size = clamp(word_size, 10, 300)

    filters = build_filters(
        platform=platform,
        query_keyword=query_keyword,
        city_context=city_context,
    )

    if subtopic:
        filters.append({"term": {"subtopic": subtopic}})

    body = {
        "size": source_size,
        "_source": [
            "title",
            "text",
            "query_keyword",
            "subtopic",
            "platform",
            "city_context",
        ],
        "query": {
            "bool": {
                "filter": filters,
            }
        },
        "sort": [
            {
                "created_at": {
                    "order": "desc",
                    "unmapped_type": "date",
                }
            }
        ],
    }

    result = es.search(index=index, body=body, request_timeout=60)

    hits = result.get("hits", {}).get("hits", [])
    counter: Counter[str] = Counter()

    for hit in hits:
        source = hit.get("_source", {})

        text_parts = [
            source.get("title", ""),
            source.get("text", ""),
            source.get("query_keyword", ""),
            source.get("subtopic", ""),
        ]

        combined_text = " ".join(
            str(part)
            for part in text_parts
            if part
        )

        counter.update(extract_word_cloud_tokens(combined_text))

    words = [
        {
            "text": word,
            "value": count,
        }
        for word, count in counter.most_common(word_size)
    ]

    return {
        "index": index,
        "source_size": source_size,
        "returned_documents": len(hits),
        "word_size": word_size,
        "filters": {
            "platform": platform,
            "query_keyword": query_keyword,
            "subtopic": subtopic,
            "city_context": city_context,
        },
        "words": words,
    }


def housing_sentiment_summary(es, index: str) -> Dict[str, Any]:
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

    buckets = (
        result.get("aggregations", {})
        .get("by_sentiment_label", {})
        .get("buckets", [])
    )

    return {
        "index": index,
        "total": result.get("hits", {}).get("total", {}),
        "average_sentiment": (
            result.get("aggregations", {})
            .get("avg_sentiment", {})
            .get("value")
        ),
        "sentiment_stats": (
            result.get("aggregations", {})
            .get("sentiment_stats", {})
        ),
        "buckets": [
            {
                "sentiment_label": bucket.get("key"),
                "count": bucket.get("doc_count"),
            }
            for bucket in buckets
        ],
    }


def housing_sentiment_by_platform(
    es,
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

    platform_buckets = (
        result.get("aggregations", {})
        .get("by_platform", {})
        .get("buckets", [])
    )

    output = []

    for bucket in platform_buckets:
        sentiment_buckets = (
            bucket.get("by_sentiment_label", {})
            .get("buckets", [])
        )

        sent_counts = {item.get("key"): item.get("doc_count") for item in sentiment_buckets}
        total_p = sum(sent_counts.values())
        neg_ratio = round(sent_counts.get("negative", 0) / max(1, total_p), 4)
        pos_ratio = round(sent_counts.get("positive", 0) / max(1, total_p), 4)

        output.append(
            {
                "platform": bucket.get("key"),
                "count": bucket.get("doc_count"),
                "average_sentiment": neg_ratio,
                "pos_ratio": pos_ratio,
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
    es,
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

    time_buckets = (
        result.get("aggregations", {})
        .get("over_time", {})
        .get("buckets", [])
    )

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
                "average_sentiment": round(
                    sum(s.get("doc_count", 0) for s in bucket.get("by_sentiment_label", {}).get("buckets", [])
                        if s.get("key") == "negative")
                    / max(1, bucket.get("doc_count", 1)), 4
                ),
                "sentiment_labels": [
                    {
                        "sentiment_label": item.get("key"),
                        "count": item.get("doc_count"),
                    }
                    for item in (
                        bucket.get("by_sentiment_label", {})
                        .get("buckets", [])
                    )
                ],
            }
            for bucket in time_buckets
        ],
    }


def housing_platform_keywords(
    es,
    index: str,
    platform_size: int = 20,
    keyword_size: int = 10,
    keyword_field: str = "query_keyword",
) -> Dict[str, Any]:
    """Return keyword distributions grouped by platform."""
    platform_size = clamp(platform_size, 1, 100)
    keyword_size = clamp(keyword_size, 1, 50)

    body = {
        "size": 0,
        "aggs": {
            "by_platform": {
                "terms": {
                    "field": "platform",
                    "size": platform_size,
                },
                "aggs": {
                    "top_keywords": {
                        "terms": {
                            "field": keyword_field,
                            "size": keyword_size,
                        }
                    }
                },
            }
        },
    }

    result = es.search(index=index, body=body)

    platform_buckets = (
        result.get("aggregations", {})
        .get("by_platform", {})
        .get("buckets", [])
    )

    return {
        "index": index,
        "keyword_field": keyword_field,
        "total": result.get("hits", {}).get("total", {}),
        "buckets": [
            {
                "platform": bucket.get("key"),
                "count": bucket.get("doc_count"),
                "top_keywords": [
                    {
                        "keyword": item.get("key"),
                        "count": item.get("doc_count"),
                    }
                    for item in (
                        bucket.get("top_keywords", {})
                        .get("buckets", [])
                    )
                ],
            }
            for bucket in platform_buckets
        ],
    }


def official_period_by_source_group(
    es,
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
                            "order": {
                                "_key": "asc",
                            },
                        }
                    }
                },
            }
        },
    }

    result = es.search(index=index, body=body)

    source_buckets = (
        result.get("aggregations", {})
        .get("by_source_group", {})
        .get("buckets", [])
    )

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
                    for item in (
                        bucket.get("by_period", {})
                        .get("buckets", [])
                    )
                ],
            }
            for bucket in source_buckets
        ],
    }


def dashboard_overview(
    es,
    housing_index: str,
    official_index: str,
) -> Dict[str, Any]:
    """Build a compact multi-source overview for the dashboard."""
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
            "sentiment": housing_sentiment_summary(
                es,
                housing_index,
            ),
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


# Build the comparison payload used by the official-data notebook panel.
def discourse_vs_official_comparison(
    es,
    housing_index: str,
    official_index: str,
    interval: str = "month",
    topic_size: int = 20,
    region_size: int = 20,
    source_size: int = 20,
    period_size: int = 20,
) -> Dict[str, Any]:
    """Compare online discussion signals with official-data coverage."""
    if interval not in {"day", "week", "month"}:
        interval = "month"

    return {
        "comparison_type": "public_discourse_vs_official_evidence",
        "description": (
            "This response compares public housing discourse with official housing evidence. "
            "Public discourse is based on housing_posts, while official evidence is based on "
            "official_housing_rows."
        ),
        "interval": interval,
        "public_discourse": {
            "index": housing_index,
            "document_count": count_index(es, housing_index),
            "platform_distribution": terms_distribution(
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
                size=topic_size,
                label_name="query_keyword",
            )["buckets"],
            "top_subtopics": terms_distribution(
                es,
                housing_index,
                field="subtopic",
                size=topic_size,
                label_name="subtopic",
            )["buckets"],
            "cleaned_regional_distribution": cleaned_city_context_distribution(
                es=es,
                index=housing_index,
                source_size=500,
                output_size=region_size,
                include_other=False,
            )["buckets"],
            "sentiment_summary": housing_sentiment_summary(
                es=es,
                index=housing_index,
            ),
            "sentiment_over_time": housing_sentiment_over_time(
                es=es,
                index=housing_index,
                interval=interval,
            )["buckets"],
        },
        "official_evidence": {
            "index": official_index,
            "document_count": count_index(es, official_index),
            "source_group_distribution": terms_distribution(
                es,
                official_index,
                field="source_group",
                size=source_size,
                label_name="source_group",
            )["buckets"],
            "state_distribution": terms_distribution(
                es,
                official_index,
                field="state",
                size=20,
                label_name="state",
            )["buckets"],
            "row_type_distribution": terms_distribution(
                es,
                official_index,
                field="row_type",
                size=20,
                label_name="row_type",
            )["buckets"],
            "period_coverage_by_source_group": official_period_by_source_group(
                es=es,
                index=official_index,
                size=source_size,
                period_size=period_size,
            )["buckets"],
        },
    }


@analysis_bp.route("/health", methods=["GET"])
def health():
    """Return a health payload for service checks."""
    es = get_es_client()
    info = es.info()

    housing_index = get_housing_index()
    official_index = get_official_index()

    housing_count = es.count(index=housing_index).get("count", 0)
    official_count = es.count(index=official_index).get("count", 0)

    return jsonify(
        {
            "status": "ok",
            "cluster_name": info.get("cluster_name"),
            "es_version": info.get("version", {}).get("number"),
            "housing_index": housing_index,
            "housing_document_count": housing_count,
            "official_index": official_index,
            "official_document_count": official_count,
        }
    )


@analysis_bp.route("/dashboard/overview", methods=["GET"])
def dashboard():
    """HTTP handler for the combined dashboard overview."""
    es = get_es_client()

    return jsonify(
        dashboard_overview(
            es=es,
            housing_index=get_housing_index(),
            official_index=get_official_index(),
        )
    )


# Compare online discourse aggregates with official housing indicators.
@analysis_bp.route("/compare/discourse-vs-official", methods=["GET"])
def compare_discourse_vs_official():
    """HTTP handler for discussion-versus-official comparison data."""
    es = get_es_client()

    interval = request.args.get("interval", "month").strip()

    topic_size = parse_int_arg(
        "topic_size",
        default=20,
        minimum=1,
        maximum=100,
    )

    region_size = parse_int_arg(
        "region_size",
        default=20,
        minimum=1,
        maximum=100,
    )

    source_size = parse_int_arg(
        "source_size",
        default=20,
        minimum=1,
        maximum=100,
    )

    period_size = parse_int_arg(
        "period_size",
        default=20,
        minimum=1,
        maximum=100,
    )

    return jsonify(
        discourse_vs_official_comparison(
            es=es,
            housing_index=get_housing_index(),
            official_index=get_official_index(),
            interval=interval,
            topic_size=topic_size,
            region_size=region_size,
            source_size=source_size,
            period_size=period_size,
        )
    )


@analysis_bp.route("/housing/sentiment-summary", methods=["GET"])
def sentiment_summary():
    """HTTP handler for overall sentiment data."""
    es = get_es_client()

    return jsonify(
        housing_sentiment_summary(
            es=es,
            index=get_housing_index(),
        )
    )


@analysis_bp.route("/housing/sentiment-by-platform", methods=["GET"])
def sentiment_by_platform():
    """HTTP handler for platform sentiment data."""
    es = get_es_client()
    size = parse_int_arg("size", default=20, minimum=1, maximum=100)

    return jsonify(
        housing_sentiment_by_platform(
            es=es,
            index=get_housing_index(),
            size=size,
        )
    )


@analysis_bp.route("/housing/sentiment-over-time", methods=["GET"])
def sentiment_over_time():
    """HTTP handler for sentiment trend data."""
    es = get_es_client()

    interval = request.args.get("interval", "month").strip()
    platform = optional_arg("platform")
    query_keyword = optional_arg("query_keyword")
    city_context = optional_arg("city_context")

    return jsonify(
        housing_sentiment_over_time(
            es=es,
            index=get_housing_index(),
            interval=interval,
            platform=platform,
            query_keyword=query_keyword,
            city_context=city_context,
        )
    )


@analysis_bp.route("/housing/by-city-context", methods=["GET"])
def by_city_context():
    """HTTP handler for city-context aggregation data."""
    es = get_es_client()
    size = parse_int_arg("size", default=30, minimum=1, maximum=100)

    return jsonify(
        terms_distribution(
            es=es,
            index=get_housing_index(),
            field="city_context",
            size=size,
            label_name="city_context",
        )
    )


@analysis_bp.route("/housing/by-region-cleaned", methods=["GET"])
def by_region_cleaned():
    """HTTP handler for cleaned regional distribution data."""
    es = get_es_client()

    source_size = parse_int_arg(
        "source_size",
        default=500,
        minimum=10,
        maximum=2000,
    )

    output_size = parse_int_arg(
        "output_size",
        default=30,
        minimum=1,
        maximum=100,
    )

    include_other_raw = request.args.get("include_other", "false").lower()
    include_other = include_other_raw in {"1", "true", "yes"}

    return jsonify(
        cleaned_city_context_distribution(
            es=es,
            index=get_housing_index(),
            source_size=source_size,
            output_size=output_size,
            include_other=include_other,
        )
    )


@analysis_bp.route("/housing/by-australia-connection", methods=["GET"])
def by_australia_connection():
    """HTTP handler for Australian-connection distribution data."""
    es = get_es_client()
    size = parse_int_arg("size", default=30, minimum=1, maximum=100)

    return jsonify(
        terms_distribution(
            es=es,
            index=get_housing_index(),
            field="australia_connection",
            size=size,
            label_name="australia_connection",
        )
    )


@analysis_bp.route("/housing/top-query-keywords", methods=["GET"])
def top_query_keywords():
    """HTTP handler for top housing keyword data."""
    es = get_es_client()
    size = parse_int_arg("size", default=30, minimum=1, maximum=100)

    return jsonify(
        terms_distribution(
            es=es,
            index=get_housing_index(),
            field="query_keyword",
            size=size,
            label_name="query_keyword",
        )
    )


@analysis_bp.route("/housing/top-subtopics", methods=["GET"])
def top_subtopics():
    """HTTP handler for inferred housing subtopic counts."""
    es = get_es_client()
    size = parse_int_arg("size", default=30, minimum=1, maximum=100)

    return jsonify(
        terms_distribution(
            es=es,
            index=get_housing_index(),
            field="subtopic",
            size=size,
            label_name="subtopic",
        )
    )


# Return weighted terms for the dashboard word-cloud visualisation.
@analysis_bp.route("/housing/word-cloud", methods=["GET"])
def word_cloud():
    """HTTP handler for word-cloud terms."""
    es = get_es_client()

    source_size = parse_int_arg(
        "source_size",
        default=3000,
        minimum=100,
        maximum=10000,
    )

    word_size = parse_int_arg(
        "word_size",
        default=100,
        minimum=10,
        maximum=300,
    )

    platform = optional_arg("platform")
    query_keyword = optional_arg("query_keyword")
    subtopic = optional_arg("subtopic")
    city_context = optional_arg("city_context")

    return jsonify(
        housing_word_cloud(
            es=es,
            index=get_housing_index(),
            source_size=source_size,
            word_size=word_size,
            platform=platform,
            query_keyword=query_keyword,
            subtopic=subtopic,
            city_context=city_context,
        )
    )


@analysis_bp.route("/housing/platform-keywords", methods=["GET"])
def platform_keywords():
    """HTTP handler for platform keyword comparisons."""
    es = get_es_client()

    platform_size = parse_int_arg(
        "platform_size",
        default=20,
        minimum=1,
        maximum=100,
    )

    keyword_size = parse_int_arg(
        "keyword_size",
        default=10,
        minimum=1,
        maximum=50,
    )

    keyword_field = request.args.get("keyword_field", "query_keyword").strip()

    return jsonify(
        housing_platform_keywords(
            es=es,
            index=get_housing_index(),
            platform_size=platform_size,
            keyword_size=keyword_size,
            keyword_field=keyword_field,
        )
    )


@analysis_bp.route("/official/period-by-source-group", methods=["GET"])
def official_periods_by_source():
    """HTTP handler for official-data period coverage by source."""
    es = get_es_client()

    size = parse_int_arg("size", default=20, minimum=1, maximum=100)
    period_size = parse_int_arg(
        "period_size",
        default=20,
        minimum=1,
        maximum=100,
    )

    return jsonify(
        official_period_by_source_group(
            es=es,
            index=get_official_index(),
            size=size,
            period_size=period_size,
        )
    )


def create_app() -> Flask:
    """Create and configure the Flask application."""
    app = Flask(__name__)
    app.register_blueprint(analysis_bp)

    @app.route("/", methods=["GET"])
    def root():
        """Return a small service description for the root endpoint."""
        return jsonify(
            {
                "service": "analysis API",
                "routes": [
                    "/api/analysis/health",
                    "/api/analysis/dashboard/overview",
                    "/api/analysis/compare/discourse-vs-official",
                    "/api/analysis/housing/sentiment-summary",
                    "/api/analysis/housing/sentiment-by-platform",
                    "/api/analysis/housing/sentiment-over-time",
                    "/api/analysis/housing/by-city-context",
                    "/api/analysis/housing/by-region-cleaned",
                    "/api/analysis/housing/by-australia-connection",
                    "/api/analysis/housing/top-query-keywords",
                    "/api/analysis/housing/top-subtopics",
                    "/api/analysis/housing/word-cloud",
                    "/api/analysis/housing/platform-keywords",
                    "/api/analysis/official/period-by-source-group",
                ],
            }
        )

    return app


if __name__ == "__main__":
    app = create_app()

    host = os.getenv("ANALYSIS_API_HOST", "0.0.0.0")
    port = int(os.getenv("ANALYSIS_API_PORT", os.getenv("PORT", "9092")))

    debug = os.getenv("FLASK_DEBUG", "false").lower() == "true"

    app.run(host=host, port=port, debug=debug)

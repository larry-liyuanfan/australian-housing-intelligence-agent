# COMP90024 Team 12
# Public attribution: COMP90024 Team 12; member identities removed from this portfolio copy.

"""Elasticsearch query helpers for notebook and API analytics."""

from __future__ import annotations

import re
from typing import Any, Dict, Optional

from elasticsearch import Elasticsearch


CITY_TO_STATE = {
    "Sydney": "NSW",
    "Melbourne": "VIC",
    "Brisbane": "QLD",
    "Adelaide": "SA",
    "Perth": "WA",
    "Hobart": "TAS",
    "Darwin": "NT",
    "Canberra": "ACT",
    "Gold Coast": "QLD",
    "Sunshine Coast": "QLD",
    "Geelong": "VIC",
    "Newcastle": "NSW",
    "Wollongong": "NSW",
    "Bendigo": "VIC",
    "Ballarat": "VIC",
    "Toowoomba": "QLD",
    "Cairns": "QLD",
    "Townsville": "QLD",
    "Launceston": "TAS",
    "Albury": "NSW",
    "Wagga Wagga": "NSW",
    "Central Coast": "NSW",
    "Mandurah": "WA",
    "Bunbury": "WA",
    "Rockhampton": "QLD",
    "Mackay": "QLD",
}

CITY_PATTERNS = {
    "Sydney": [r"\bsydney\b"],
    "Melbourne": [r"\bmelbourne\b", r"\bmelb\b"],
    "Brisbane": [r"\bbrisbane\b"],
    "Adelaide": [r"\badelaide\b"],
    "Perth": [r"\bperth\b"],
    "Hobart": [r"\bhobart\b"],
    "Darwin": [r"\bdarwin\b"],
    "Canberra": [r"\bcanberra\b"],
    "Gold Coast": [r"\bgold\s?coast\b"],
    "Sunshine Coast": [r"\bsunshine\s?coast\b"],
    "Geelong": [r"\bgeelong\b"],
    "Newcastle": [r"\bnewcastle\b"],
    "Wollongong": [r"\bwollongong\b"],
    "Bendigo": [r"\bbendigo\b"],
    "Ballarat": [r"\bballarat\b"],
    "Toowoomba": [r"\btoowoomba\b"],
    "Cairns": [r"\bcairns\b"],
    "Townsville": [r"\btownsville\b"],
    "Launceston": [r"\blaunceston\b"],
    "Albury": [r"\balbury\b"],
    "Wagga Wagga": [r"\bwagga\s?wagga\b"],
    "Central Coast": [r"\bcentral\s?coast\b"],
    "Mandurah": [r"\bmandurah\b"],
    "Bunbury": [r"\bbunbury\b"],
    "Rockhampton": [r"\brockhampton\b"],
    "Mackay": [r"\bmackay\b"],
}

STATE_PATTERNS = {
    "NSW": [r"\bnew south wales\b", r"\bnsw\b"],
    "VIC": [r"\bvictoria\b", r"\bvic\b"],
    "QLD": [r"\bqueensland\b", r"\bqld\b"],
    "SA": [r"\bsouth australia\b", r"\bsa\b"],
    "WA": [r"\bwestern australia\b", r"\bwa\b"],
    "TAS": [r"\btasmania\b", r"\btas\b"],
    "NT": [r"\bnorthern territory\b", r"\bnt\b"],
    "ACT": [r"\baustralian capital territory\b", r"\bact\b"],
}


def has_pattern(text: str, patterns: list[str]) -> bool:
    """Check whether a text value matches any compiled location pattern."""
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)


def normalise_city_context(value: str) -> Optional[Dict[str, Any]]:
    """Map noisy city or state strings into a cleaned region label."""
    if not value:
        return None

    raw = str(value).strip()
    text = raw.lower()

    if not text or text in {"unknown", "none", "nan"}:
        return None

    has_australia_signal = bool(
        re.search(r"\baustralia\b|\baussie\b|\baus\b", text)
    )

    for city, patterns in CITY_PATTERNS.items():
        if has_pattern(text, patterns):
            return {
                "region_label": city,
                "region_type": "city",
                "region_city": city,
                "region_state": CITY_TO_STATE.get(city, "unknown"),
                "raw_city_context": raw,
            }

    for state, patterns in STATE_PATTERNS.items():
        if has_pattern(text, patterns):
            return {
                "region_label": state,
                "region_type": "state",
                "region_city": None,
                "region_state": state,
                "raw_city_context": raw,
            }

    if has_australia_signal:
        return {
            "region_label": "Australia",
            "region_type": "country",
            "region_city": None,
            "region_state": "AUS",
            "raw_city_context": raw,
        }

    return {
        "region_label": "Other / non-Australia",
        "region_type": "other",
        "region_city": None,
        "region_state": "unknown",
        "raw_city_context": raw,
    }


def cleaned_city_context_distribution(
    es: Elasticsearch,
    index: str = "housing_posts",
    source_size: int = 500,
    output_size: int = 30,
    include_other: bool = False,
) -> Dict[str, Any]:
    """Aggregate cleaned city and state mentions for the dashboard."""
    body = {
        "size": 0,
        "aggs": {
            "city_contexts": {
                "terms": {
                    "field": "city_context",
                    "size": source_size,
                }
            }
        },
    }

    result = es.search(index=index, body=body)

    buckets = (
        result.get("aggregations", {})
        .get("city_contexts", {})
        .get("buckets", [])
    )

    merged: dict[str, Dict[str, Any]] = {}

    for bucket in buckets:
        raw_value = bucket.get("key")
        count = int(bucket.get("doc_count", 0))

        cleaned = normalise_city_context(raw_value)

        if cleaned is None:
            continue

        if cleaned["region_type"] == "other" and not include_other:
            continue

        label = cleaned["region_label"]

        if label not in merged:
            merged[label] = {
                "region_label": label,
                "region_type": cleaned["region_type"],
                "region_city": cleaned["region_city"],
                "region_state": cleaned["region_state"],
                "count": 0,
                "raw_examples": [],
            }

        merged[label]["count"] += count

        if len(merged[label]["raw_examples"]) < 5:
            merged[label]["raw_examples"].append(raw_value)

    rows = sorted(
        merged.values(),
        key=lambda item: item["count"],
        reverse=True,
    )

    return {
        "index": index,
        "source_field": "city_context",
        "cleaning": "city_context values are normalised into city/state/country labels",
        "source_size": source_size,
        "output_size": output_size,
        "include_other": include_other,
        "buckets": rows[:output_size],
    }

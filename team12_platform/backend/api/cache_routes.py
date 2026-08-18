# COMP90024 Team 12
# Public attribution: COMP90024 Team 12; member identities removed from this portfolio copy.

"""Cache routes — serve pre-computed dashboard_cache with <100ms latency."""
from flask import Blueprint, jsonify
from backend.analytics.core.es_client import get_es_client

cache_bp = Blueprint("cache", __name__)
CACHE_INDEX = "dashboard_cache"


def _get_cache(key: str):
    es = get_es_client()
    try:
        doc = es.get(index=CACHE_INDEX, id=key)
    except Exception:
        return {"error": f"cache key '{key}' not found"}, 404
    return doc["_source"]["data"]


def _jsonify(result):
    if isinstance(result, tuple):
        return jsonify(result[0]), result[1]
    return jsonify(result)


@cache_bp.route("/api/cache/overview")
def cache_overview():
    return _jsonify(_get_cache("overview"))


@cache_bp.route("/api/cache/timeline")
def cache_timeline():
    return _jsonify(_get_cache("timeline"))


@cache_bp.route("/api/cache/cities")
def cache_cities():
    return _jsonify(_get_cache("cities"))


@cache_bp.route("/api/cache/keywords")
def cache_keywords():
    return _jsonify(_get_cache("keywords"))


@cache_bp.route("/api/cache/official")
def cache_official():
    return _jsonify(_get_cache("official"))


@cache_bp.route("/api/cache/youtube")
def cache_youtube():
    return _jsonify(_get_cache("youtube"))


@cache_bp.route("/api/cache/all")
def cache_all():
    es = get_es_client()
    try:
        result = es.search(index=CACHE_INDEX, body={"query": {"match_all": {}}, "size": 10})
        panels = {}
        for hit in result["hits"]["hits"]:
            panels[hit["_id"]] = hit["_source"]["data"]
        return jsonify(panels)
    except Exception as e:
        return jsonify({"error": str(e)})

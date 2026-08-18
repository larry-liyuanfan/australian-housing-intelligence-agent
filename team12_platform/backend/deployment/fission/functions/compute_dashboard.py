# COMP90024 Team 12
# Public attribution: COMP90024 Team 12; member identities removed from this portfolio copy.

# Pre-compute dashboard aggregations to ES cache. Fission Timer @every 30m.
# Reads housing_posts + official_housing_rows, writes dashboard_cache index.
from __future__ import annotations
import json, os, base64, urllib.request, urllib.error, ssl
from datetime import datetime, timezone
from typing import Optional, Dict, Any

ES_HOST = os.getenv("ES_HOST", "https://elasticsearch-es-http.elastic.svc.cluster.local:9200")
ES_USERNAME = os.getenv("ES_USERNAME", "elastic")
ES_PASSWORD = os.getenv("ES_PASSWORD", "")
ES_VERIFY = os.getenv("ES_VERIFY_CERTS", "0").lower() not in ("0", "false", "no")
HOUSING_INDEX = os.getenv("ES_INDEX", "housing_posts")
OFFICIAL_INDEX = os.getenv("OFFICIAL_ES_INDEX", "official_housing_rows")
CACHE_INDEX = "dashboard_cache"

_AUTH = base64.b64encode(f"{ES_USERNAME}:{ES_PASSWORD}".encode()).decode()

_ctx = ssl.create_default_context()
if not ES_VERIFY:
    _ctx.check_hostname = False
    _ctx.verify_mode = ssl.CERT_NONE


def _es(method: str, path: str, body: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    url = f"{ES_HOST}/{path}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Basic {_AUTH}")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30, context=_ctx) as resp:
            raw = resp.read().decode()
            return json.loads(raw) if raw.strip() else {"status_code": resp.status}
    except urllib.error.HTTPError as e:
        body_raw = e.read().decode()
        return {"error": str(e), "body": body_raw[:500]}
    except Exception as e:
        return {"error": str(e)}


def ensure_index(name: str, mapping: Dict[str, Any]) -> None:
    """Create index if it does not exist. Idempotent."""
    r = _es("GET", name)
    if "error" not in r:
        return
    _es("PUT", name, {"mappings": mapping})


def _safe_agg(body: dict) -> dict:
    result = _es("POST", f"{HOUSING_INDEX}/_search", body)
    if "error" in result:
        return {}
    return result


def compute_overview() -> dict:
    result = _safe_agg({
        "size": 0,
        "track_total_hits": True,
        "aggs": {
            "by_platform": {"terms": {"field": "platform", "size": 10}},
            "housing_ratio": {"terms": {"field": "housing_relevant"}},
            "by_sentiment": {"terms": {"field": "sentiment_label"}},
        }
    })
    aggs = result.get("aggregations", {})
    by_platform = {b["key"]: b["doc_count"] for b in aggs.get("by_platform", {}).get("buckets", [])}
    # YouTube: count videos + comments as discussion units for display
    if "youtube" in by_platform:
        yt_comments = _safe_agg({"size": 0, "query": {"term": {"platform": "youtube"}},
            "aggs": {"total_comments": {"sum": {"field": "comment_count"}}}})
        total_comments = int(yt_comments.get("aggregations", {}).get("total_comments", {}).get("value", 0))
        by_platform["youtube"] = by_platform["youtube"] + total_comments
    return {
        "total_docs": result.get("hits", {}).get("total", {}).get("value", 0),
        "by_platform": by_platform,
        "housing_relevant": {b["key_as_string"]: b["doc_count"] for b in aggs.get("housing_ratio", {}).get("buckets", [])},
        "sentiment_distribution": {b["key"]: b["doc_count"] for b in aggs.get("by_sentiment", {}).get("buckets", [])},
    }


def compute_timeline(days: int = 30) -> dict:
    result = _safe_agg({
        "size": 0,
        "query": {"range": {"created_at": {"gte": f"now-{days}d/d"}}},
        "aggs": {
            "daily": {
                "date_histogram": {"field": "created_at", "fixed_interval": "1d"},
                "aggs": {"by_sentiment": {"terms": {"field": "sentiment_label"}}},
            }
        }
    })
    buckets = result.get("aggregations", {}).get("daily", {}).get("buckets", [])
    return {
        "timeline": [
            {
                "date": b["key_as_string"][:10],
                "total": b["doc_count"],
                "sentiment": {s["key"]: s["doc_count"] for s in b.get("by_sentiment", {}).get("buckets", [])},
            }
            for b in buckets
        ]
    }


def compute_cities(top_n: int = 20) -> dict:
    result = _safe_agg({
        "size": 0,
        "query": {"term": {"housing_relevant": True}},
        "aggs": {"cities": {"terms": {"field": "city_context", "size": top_n, "exclude": "[aA]ustralia.*"}}}
    })
    buckets = result.get("aggregations", {}).get("cities", {}).get("buckets", [])
    return {"top_cities": [{"city": b["key"], "count": b["doc_count"]} for b in buckets]}


def compute_keywords(top_n: int = 30) -> dict:
    result = _safe_agg({
        "size": 0,
        "query": {"term": {"housing_relevant": True}},
        "aggs": {"keywords": {"terms": {"field": "query_keyword", "size": top_n}}}
    })
    buckets = result.get("aggregations", {}).get("keywords", {}).get("buckets", [])
    return {"top_keywords": [{"keyword": b["key"], "count": b["doc_count"]} for b in buckets]}


def compute_official() -> dict:
    r = _es("POST", f"{OFFICIAL_INDEX}/_search", {
        "size": 0,
        "track_total_hits": True,
        "aggs": {
            "by_source": {"terms": {"field": "source_group", "size": 20}},
            "by_state": {"terms": {"field": "state", "size": 10}},
            "by_period": {"terms": {"field": "period", "size": 20}},
        }
    })
    if "error" in r:
        return {}
    aggs = r.get("aggregations", {})
    return {
        "total_docs": r.get("hits", {}).get("total", {}).get("value", 0),
        "by_source": {b["key"]: b["doc_count"] for b in aggs.get("by_source", {}).get("buckets", [])},
        "by_state": {b["key"]: b["doc_count"] for b in aggs.get("by_state", {}).get("buckets", [])},
        "by_period": {b["key"]: b["doc_count"] for b in aggs.get("by_period", {}).get("buckets", [])},
    }


def write_cache(key: str, data: dict) -> None:
    doc = {"cache_key": key, "cached_at": datetime.now(timezone.utc).isoformat(), "data": data}
    _es("PUT", f"{CACHE_INDEX}/_doc/{key}", doc)


def check_volume_anomalies() -> list:
    """Compare yesterday vs day-before volume per platform.
    Alert if yesterday < day_before/5 or > day_before*3.
    """
    alerts = []
    r = _es("POST", f"{HOUSING_INDEX}/_search", {
        "size": 0,
        "query": {"range": {"created_at": {"gte": "now-3d/d"}}},
        "aggs": {
            "daily": {
                "date_histogram": {"field": "created_at", "calendar_interval": "day"},
                "aggs": {
                    "by_platform": {"terms": {"field": "platform", "size": 10}}
                }
            }
        }
    })
    buckets = r.get("aggregations", {}).get("daily", {}).get("buckets", [])
    if len(buckets) < 2:
        return alerts

    yesterday = buckets[-1] if len(buckets) > 0 else None
    day_before = buckets[-2] if len(buckets) > 1 else None
    if not yesterday or not day_before:
        return alerts

    y_platforms = {b["key"]: b["doc_count"] for b in yesterday.get("by_platform", {}).get("buckets", [])}
    d_platforms = {b["key"]: b["doc_count"] for b in day_before.get("by_platform", {}).get("buckets", [])}

    for plat in set(list(y_platforms.keys()) + list(d_platforms.keys())):
        y_count = y_platforms.get(plat, 0)
        d_count = d_platforms.get(plat, 0)
        if d_count == 0:
            continue
        # Skip low-volume platforms (< 100 docs/day) — normal fluctuation
        if d_count < 100 and y_count < 100:
            continue
        ratio = y_count / d_count
        if ratio < 0.2:
            alerts.append(f"{plat}: yesterday={y_count} < 1/5 of day_before={d_count} (ratio={ratio:.2f})")
        elif ratio > 3.0:
            alerts.append(f"{plat}: yesterday={y_count} > 3x day_before={d_count} (ratio={ratio:.2f})")

    return alerts


def compute_youtube() -> dict:
    """YouTube-specific aggregations: channels, yearly trend, likes, tags."""
    base_query = {"term": {"platform": "youtube"}}

    # Top channels
    channels_r = _safe_agg({
        "size": 0, "query": base_query,
        "aggs": {"channels": {"terms": {"field": "channel_title", "size": 15, "min_doc_count": 5}}}
    })
    channels = [{"channel": b["key"], "videos": b["doc_count"]}
                for b in channels_r.get("aggregations", {}).get("channels", {}).get("buckets", [])]

    # Yearly trend
    yearly_r = _safe_agg({
        "size": 0, "query": base_query,
        "aggs": {"yearly": {"date_histogram": {"field": "created_at", "calendar_interval": "year", "min_doc_count": 1}}}
    })
    yearly = [{"year": b["key_as_string"][:4], "videos": b["doc_count"]}
              for b in yearly_r.get("aggregations", {}).get("yearly", {}).get("buckets", [])]

    # Like stats
    likes_r = _safe_agg({
        "size": 0, "query": base_query,
        "aggs": {"total_likes": {"sum": {"field": "like_count"}},
                 "avg_likes": {"avg": {"field": "like_count"}},
                 "max_likes": {"max": {"field": "like_count"}}}
    })
    likes_agg = likes_r.get("aggregations", {})

    # Top viewed: fetch top 10 by like_count as proxy
    top_videos_r = _es("POST", f"{HOUSING_INDEX}/_search", {
        "size": 10, "query": base_query,
        "sort": [{"like_count": "desc"}],
        "_source": ["title", "channel_title", "like_count", "url", "created_at"]
    })
    top_videos = []
    for hit in top_videos_r.get("hits", {}).get("hits", []):
        s = hit["_source"]
        top_videos.append({
            "title": s.get("title", ""),
            "channel": s.get("channel_title", ""),
            "likes": s.get("like_count", 0),
            "url": s.get("url", ""),
            "date": (s.get("created_at", "") or "")[:10],
        })

    # Channel sentiment comparison (top 10 channels)
    sentiment_r = _es("POST", f"{HOUSING_INDEX}/_search", {
        "size": 0, "query": {"bool": {"filter": [
            base_query,
            {"terms": {"channel_title": [c["channel"] for c in channels[:10]]}}
        ]}},
        "aggs": {
            "by_channel": {
                "terms": {"field": "channel_title", "size": 10},
                "aggs": {"by_sentiment": {"terms": {"field": "sentiment_label"}}}
            }
        }
    })
    channel_sentiment = {}
    for b in sentiment_r.get("aggregations", {}).get("by_channel", {}).get("buckets", []):
        channel_sentiment[b["key"]] = {s["key"]: s["doc_count"]
                                        for s in b.get("by_sentiment", {}).get("buckets", [])}

    # Comment count
    comments_r = _safe_agg({
        "size": 0, "query": base_query,
        "aggs": {"total_comments": {"sum": {"field": "comment_count"}}}
    })
    total_comments = comments_r.get("aggregations", {}).get("total_comments", {}).get("value", 0)

    return {
        "total_videos": channels_r.get("hits", {}).get("total", {}).get("value", 0),
        "total_comments": int(total_comments),
        "total_discussion_units": int(channels_r.get("hits", {}).get("total", {}).get("value", 0) + total_comments),
        "top_channels": channels,
        "yearly_trend": yearly,
        "like_stats": {
            "total": likes_agg.get("total_likes", {}).get("value", 0),
            "average": likes_agg.get("avg_likes", {}).get("value", 0),
            "max": likes_agg.get("max_likes", {}).get("value", 0),
        },
        "top_videos": top_videos,
        "channel_sentiment": channel_sentiment,
    }


def main():
    ensure_index(CACHE_INDEX, {
        "dynamic": False,
        "properties": {
            "cache_key": {"type": "keyword"},
            "cached_at": {"type": "date"},
            "data": {"type": "object", "enabled": False},
        }
    })

    now = datetime.now(timezone.utc).isoformat()
    results = {"cached_at": now, "panels": {}}

    overview = compute_overview()
    write_cache("overview", overview)
    results["panels"]["overview"] = overview.get("total_docs", 0)

    timeline = compute_timeline()
    write_cache("timeline", timeline)
    results["panels"]["timeline"] = "ok"

    cities = compute_cities()
    write_cache("cities", cities)
    results["panels"]["cities"] = "ok"

    keywords = compute_keywords()
    write_cache("keywords", keywords)
    results["panels"]["keywords"] = "ok"

    official = compute_official()
    write_cache("official", official)
    results["panels"]["official"] = official.get("total_docs", 0)

    youtube = compute_youtube()
    write_cache("youtube", youtube)
    results["panels"]["youtube"] = youtube.get("total_discussion_units", 0)

    # Anomaly detection: check platform volume vs previous day
    anomalies = check_volume_anomalies()
    for alert in anomalies:
        _es("POST", "harvester_errors/_doc", {
            "harvester": "compute-dashboard",
            "time": datetime.now(timezone.utc).isoformat(),
            "error_type": "volume_anomaly",
            "message": alert,
            "raw_error": "",
        })
    results["panels"]["anomalies"] = anomalies if anomalies else "none"

    return json.dumps(results)


if __name__ == "__main__":
    print(main())

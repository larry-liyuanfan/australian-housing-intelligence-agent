# COMP90024 Team 12
# Public attribution: COMP90024 Team 12; member identities removed from this portfolio copy.

from __future__ import annotations
from typing import Any, Dict, List, Optional
from elasticsearch import Elasticsearch
from backend.analytics.core.utils import clamp

def _date_filter(start: Optional[str]=None, end: Optional[str]=None) -> Dict[str, Any]:
    if not start and (not end):
        return {'match_all': {}}
    range_body: Dict[str, Any] = {}
    if start:
        range_body['gte'] = start
    if end:
        range_body['lte'] = end
    return {'range': {'created_at': range_body}}

def get_volume_by_platform(es: Elasticsearch, index: str='housing_posts') -> Dict[str, Any]:
    body = {'size': 0, 'aggs': {'by_platform': {'terms': {'field': 'platform', 'size': 10}, 'aggs': {'unique_sources': {'cardinality': {'field': 'source'}}}}}}
    res = es.search(index=index, body=body)
    rows = []
    yt_comments = 0
    for bucket in res.get('aggregations', {}).get('by_platform', {}).get('buckets', []):
        platform = bucket.get('key')
        count = bucket.get('doc_count')
        if platform == 'youtube':
            if yt_comments == 0:
                yt = es.search(index=index, body={'size': 0, 'query': {'term': {'platform': 'youtube'}},
                    'aggs': {'total_comments': {'sum': {'field': 'comment_count'}}}})
                yt_comments = int(yt.get('aggregations', {}).get('total_comments', {}).get('value', 0))
            count = count + yt_comments
        rows.append({'platform': platform, 'post_count': count,
                     'unique_sources': bucket.get('unique_sources', {}).get('value')})
    return {'results': rows}

def get_timeseries_by_platform(es: Elasticsearch, index: str='housing_posts', interval: str='day', start: Optional[str]=None, end: Optional[str]=None) -> Dict[str, Any]:
    body = {'size': 0, 'query': _date_filter(start, end), 'aggs': {'over_time': {'date_histogram': {'field': 'created_at', 'calendar_interval': interval, 'min_doc_count': 1}, 'aggs': {'by_platform': {'terms': {'field': 'platform', 'size': 10}}}}}}
    res = es.search(index=index, body=body)
    rows: List[Dict[str, Any]] = []
    for date_bucket in res.get('aggregations', {}).get('over_time', {}).get('buckets', []):
        date = date_bucket.get('key_as_string', '')[:10]
        for platform_bucket in date_bucket.get('by_platform', {}).get('buckets', []):
            rows.append({'date': date, 'platform': platform_bucket.get('key'), 'post_count': platform_bucket.get('doc_count')})
    return {'results': rows}

def get_top_query_keywords(es: Elasticsearch, index: str='housing_posts', size: int=50) -> Dict[str, Any]:
    body = {'size': 0, 'aggs': {'top_query_keywords': {'terms': {'field': 'query_keyword', 'size': size}, 'aggs': {'by_platform': {'terms': {'field': 'platform', 'size': 10}}}}}}
    res = es.search(index=index, body=body)
    rows = []
    for bucket in res.get('aggregations', {}).get('top_query_keywords', {}).get('buckets', []):
        rows.append({'query_keyword': bucket.get('key'), 'post_count': bucket.get('doc_count'), 'platform_breakdown': [{'platform': b.get('key'), 'post_count': b.get('doc_count')} for b in bucket.get('by_platform', {}).get('buckets', [])]})
    return {'results': rows}

def get_city_context_distribution(es: Elasticsearch, index: str='housing_posts') -> Dict[str, Any]:
    body = {'size': 0, 'aggs': {'by_city_context': {'terms': {'field': 'city_context', 'size': 50, 'missing': 'unknown'}, 'aggs': {'by_platform': {'terms': {'field': 'platform', 'size': 10}}}}}}
    res = es.search(index=index, body=body)
    rows = []
    for bucket in res.get('aggregations', {}).get('by_city_context', {}).get('buckets', []):
        rows.append({'city_context': bucket.get('key'), 'post_count': bucket.get('doc_count'), 'platform_breakdown': [{'platform': b.get('key'), 'post_count': b.get('doc_count')} for b in bucket.get('by_platform', {}).get('buckets', [])]})
    return {'results': rows}

def get_australia_connection_distribution(es: Elasticsearch, index: str='housing_posts') -> Dict[str, Any]:
    body = {'size': 0, 'aggs': {'by_connection': {'terms': {'field': 'australia_connection', 'size': 30, 'missing': 'unknown'}, 'aggs': {'by_platform': {'terms': {'field': 'platform', 'size': 10}}}}}}
    res = es.search(index=index, body=body)
    rows = []
    for bucket in res.get('aggregations', {}).get('by_connection', {}).get('buckets', []):
        rows.append({'australia_connection': bucket.get('key'), 'post_count': bucket.get('doc_count'), 'platform_breakdown': [{'platform': b.get('key'), 'post_count': b.get('doc_count')} for b in bucket.get('by_platform', {}).get('buckets', [])]})
    return {'results': rows}

def search_posts(es: Elasticsearch, index: str='housing_posts', q: str='housing', platform: Optional[str]=None, city_context: Optional[str]=None, size: int=20) -> Dict[str, Any]:
    must: List[Dict[str, Any]] = [{'multi_match': {'query': q, 'fields': ['text', 'title']}}]
    if platform:
        must.append({'term': {'platform': platform}})
    if city_context:
        must.append({'term': {'city_context': city_context}})
    body = {'size': size, 'query': {'bool': {'must': must}}, 'sort': [{'created_at': {'order': 'desc', 'unmapped_type': 'date'}}], '_source': ['doc_id', 'platform', 'source', 'query_keyword', 'title', 'text', 'created_at', 'collected_at', 'url', 'city_context', 'topic', 'australia_connection', 'sentiment', 'sentiment_label', 'subjectivity']}
    res = es.search(index=index, body=body)
    return {'results': [hit.get('_source', {}) for hit in res.get('hits', {}).get('hits', [])]}

def housing_platform_keywords(es: Elasticsearch, index: str, platform_size: int=20, keyword_size: int=10, keyword_field: str='query_keyword') -> Dict[str, Any]:
    platform_size = clamp(platform_size, 1, 100)
    keyword_size = clamp(keyword_size, 1, 50)
    body = {'size': 0, 'aggs': {'by_platform': {'terms': {'field': 'platform', 'size': platform_size}, 'aggs': {'top_keywords': {'terms': {'field': keyword_field, 'size': keyword_size}}}}}}
    result = es.search(index=index, body=body)
    platform_buckets = result.get('aggregations', {}).get('by_platform', {}).get('buckets', [])
    return {'index': index, 'keyword_field': keyword_field, 'total': result.get('hits', {}).get('total', {}), 'buckets': [{'platform': bucket.get('key'), 'count': bucket.get('doc_count'), 'top_keywords': [{'keyword': item.get('key'), 'count': item.get('doc_count')} for item in bucket.get('top_keywords', {}).get('buckets', [])]} for bucket in platform_buckets]}

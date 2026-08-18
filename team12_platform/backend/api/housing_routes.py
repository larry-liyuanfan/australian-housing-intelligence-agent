# COMP90024 Team 12
# Public attribution: COMP90024 Team 12; member identities removed from this portfolio copy.

from __future__ import annotations
import os
from flask import Blueprint, Flask, jsonify, request
from backend.analytics.core.es_client import get_es_client
from backend.analytics.platform.queries import get_australia_connection_distribution, get_city_context_distribution, get_timeseries_by_platform, get_top_query_keywords, get_volume_by_platform, search_posts
housing_bp = Blueprint('housing', __name__)

def get_housing_index() -> str:
    return os.getenv('ES_INDEX', 'housing_posts')

def get_int_arg(name: str, default: int, minimum: int=1, maximum: int=200) -> int:
    raw = request.args.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(minimum, min(value, maximum))

@housing_bp.get('/api/health')
def health():
    es = get_es_client()
    index_name = get_housing_index()
    try:
        info = es.info()
        count = es.count(index=index_name)
        return jsonify({'status': 'ok', 'index': index_name, 'document_count': count.get('count'), 'cluster_name': info.get('cluster_name'), 'es_version': info.get('version', {}).get('number')})
    except Exception as exc:
        return (jsonify({'status': 'error', 'index': index_name, 'message': str(exc)}), 500)

@housing_bp.get('/api/housing/volume-by-platform')
def volume_by_platform():
    es = get_es_client()
    return jsonify(get_volume_by_platform(es, get_housing_index()))

@housing_bp.get('/api/housing/timeseries')
def timeseries():
    es = get_es_client()
    interval = request.args.get('interval', 'day')
    start = request.args.get('start')
    end = request.args.get('end')
    return jsonify(get_timeseries_by_platform(es, get_housing_index(), interval=interval, start=start, end=end))

@housing_bp.get('/api/housing/top-query-keywords')
def top_query_keywords():
    es = get_es_client()
    size = get_int_arg('size', 50, 1, 200)
    return jsonify(get_top_query_keywords(es, get_housing_index(), size=size))

@housing_bp.get('/api/housing/by-city-context')
def by_city_context():
    es = get_es_client()
    return jsonify(get_city_context_distribution(es, get_housing_index()))

@housing_bp.get('/api/housing/australia-connection')
def australia_connection():
    es = get_es_client()
    return jsonify(get_australia_connection_distribution(es, get_housing_index()))

@housing_bp.get('/api/housing/search')
def search():
    es = get_es_client()
    q = request.args.get('q', 'housing')
    platform = request.args.get('platform')
    city_context = request.args.get('city_context')
    size = get_int_arg('size', 20, 1, 100)
    return jsonify(search_posts(es, get_housing_index(), q=q, platform=platform, city_context=city_context, size=size))

def create_app() -> Flask:
    app = Flask(__name__)
    app.register_blueprint(housing_bp)

    @app.get('/')
    def root():
        return jsonify({'service': 'housing public discourse API', 'routes': ['/api/health', '/api/housing/volume-by-platform', '/api/housing/timeseries', '/api/housing/top-query-keywords', '/api/housing/by-city-context', '/api/housing/australia-connection', '/api/housing/search?q=rent&size=5']})
    return app
if __name__ == '__main__':
    app = create_app()
    app.run(host=os.getenv('API_HOST', '0.0.0.0'), port=int(os.getenv('PORT', '9090')), debug=os.getenv('FLASK_DEBUG', 'false').lower() == 'true')

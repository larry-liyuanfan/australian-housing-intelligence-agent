# COMP90024 Team 12
# Public attribution: COMP90024 Team 12; member identities removed from this portfolio copy.

from __future__ import annotations
import os
from typing import Optional
from flask import Blueprint, Flask, jsonify, request
from backend.analytics.core.es_client import get_es_client
from backend.analytics.official.queries import get_official_count, get_official_overview, get_period_distribution, get_row_type_distribution, get_source_group_distribution, get_state_distribution, search_official_rows
official_bp = Blueprint('official', __name__, url_prefix='/api/official')

def get_official_index() -> str:
    return os.getenv('OFFICIAL_ES_INDEX', 'official_housing_rows')

def parse_int_arg(name: str, default: int, minimum: int=1, maximum: int=100) -> int:
    raw_value = request.args.get(name)
    if raw_value is None:
        return default
    try:
        value = int(raw_value)
    except ValueError:
        return default
    return max(minimum, min(value, maximum))

def optional_arg(name: str) -> Optional[str]:
    value = request.args.get(name)
    if value is None:
        return None
    value = value.strip()
    return value or None

@official_bp.route('/health', methods=['GET'])
def official_health():
    es = get_es_client()
    index = get_official_index()
    info = es.info()
    count = get_official_count(es, index)
    return jsonify({'status': 'ok', 'cluster_name': info.get('cluster_name'), 'es_version': info.get('version', {}).get('number'), 'index': index, 'document_count': count})

@official_bp.route('/overview', methods=['GET'])
def official_overview():
    es = get_es_client()
    index = get_official_index()
    return jsonify(get_official_overview(es, index))

@official_bp.route('/source-groups', methods=['GET'])
def official_source_groups():
    es = get_es_client()
    index = get_official_index()
    size = parse_int_arg('size', default=30, minimum=1, maximum=100)
    return jsonify(get_source_group_distribution(es, index, size=size))

@official_bp.route('/row-types', methods=['GET'])
def official_row_types():
    es = get_es_client()
    index = get_official_index()
    size = parse_int_arg('size', default=20, minimum=1, maximum=100)
    return jsonify(get_row_type_distribution(es, index, size=size))

@official_bp.route('/by-state', methods=['GET'])
def official_by_state():
    es = get_es_client()
    index = get_official_index()
    size = parse_int_arg('size', default=20, minimum=1, maximum=100)
    return jsonify(get_state_distribution(es, index, size=size))

@official_bp.route('/by-period', methods=['GET'])
def official_by_period():
    es = get_es_client()
    index = get_official_index()
    size = parse_int_arg('size', default=50, minimum=1, maximum=200)
    return jsonify(get_period_distribution(es, index, size=size))

@official_bp.route('/search', methods=['GET'])
def official_search():
    es = get_es_client()
    index = get_official_index()
    q = request.args.get('q', '').strip()
    size = parse_int_arg('size', default=10, minimum=1, maximum=100)
    source_group = optional_arg('source_group')
    state = optional_arg('state')
    row_type = optional_arg('row_type')
    period = optional_arg('period')
    return jsonify(search_official_rows(es=es, index=index, query=q, size=size, source_group=source_group, state=state, row_type=row_type, period=period))

def create_app() -> Flask:
    app = Flask(__name__)
    app.register_blueprint(official_bp)

    @app.route('/', methods=['GET'])
    def root():
        return jsonify({'service': 'official housing API', 'routes': ['/api/official/health', '/api/official/overview', '/api/official/source-groups', '/api/official/row-types', '/api/official/by-state', '/api/official/by-period', '/api/official/search?q=Aberfoyle Park median rent&size=5']})
    return app
if __name__ == '__main__':
    app = create_app()
    host = os.getenv('OFFICIAL_API_HOST', '0.0.0.0')
    port = int(os.getenv('OFFICIAL_API_PORT', '9091'))
    app.run(host=host, port=port, debug=True)

# COMP90024 Team 12
# Public attribution: COMP90024 Team 12; member identities removed from this portfolio copy.

"""Create Elasticsearch clients from deployment environment variables."""

from __future__ import annotations

import os

from elasticsearch import Elasticsearch


def get_es_client() -> Elasticsearch:
    """Return an Elasticsearch client configured from environment variables."""
    host = os.getenv("ES_HOST", "http://localhost:9200")
    username = os.getenv("ES_USERNAME")
    password = os.getenv("ES_PASSWORD")
    verify = os.getenv("ES_VERIFY_CERTS", "1") not in ("0", "false", "no")

    if username and password:
        return Elasticsearch(host, basic_auth=(username, password), verify_certs=verify)

    return Elasticsearch(host, verify_certs=verify)

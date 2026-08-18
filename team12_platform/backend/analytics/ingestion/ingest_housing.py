# COMP90024 Team 12
# Public attribution: COMP90024 Team 12; member identities removed from this portfolio copy.

"""Ingest normalised records into Elasticsearch."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, Iterable, Iterator

from elasticsearch import Elasticsearch, helpers

try:
    from backend.analytics.core.es_client import get_es_client
except ModuleNotFoundError:
    from analytics.core.es_client import get_es_client


def load_mapping(mapping_path: Path) -> Dict:
    """Load an Elasticsearch mapping document from disk."""
    with mapping_path.open('r', encoding='utf-8') as f:
        return json.load(f)


def ensure_index(
    es: Elasticsearch,
    index_name: str,
    mapping_path: Path,
    recreate: bool = False,
) -> None:
    """Create or recreate the target Elasticsearch index before ingestion."""
    if recreate and es.indices.exists(index=index_name):
        es.indices.delete(index=index_name)
        print(f'Deleted existing index: {index_name}')

    if not es.indices.exists(index=index_name):
        es.indices.create(index=index_name, body=load_mapping(mapping_path))
        print(f'Created index: {index_name}')
    else:
        print(f'Index already exists: {index_name}')


def read_jsonl(path: Path) -> Iterator[Dict]:
    """Yield decoded JSON records from a JSONL file."""
    with path.open('r', encoding='utf-8') as f:
        for line_no, line in enumerate(f, start=1):
            if not line.strip():
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f'Invalid JSON on {path}:{line_no}: {exc}'
                ) from exc


def to_bulk_actions(index_name: str, docs: Iterable[Dict]) -> Iterator[Dict]:
    """Convert documents into Elasticsearch bulk API actions."""
    skipped = 0
    for doc in docs:
        doc_id = doc.get('doc_id')
        if not doc_id:
            skipped += 1
            continue
        yield {'_index': index_name, '_id': doc_id, '_source': doc}
    if skipped:
        print(f'Skipped {skipped} records without doc_id')


def _run_bulk(
    es: Elasticsearch,
    index_name: str,
    actions: Iterable[Dict],
    chunk_size: int,
    label: str,
) -> None:
    """Run helpers.bulk and print a result summary."""
    success, errors = helpers.bulk(
        es,
        actions,
        stats_only=False,
        raise_on_error=False,
        chunk_size=chunk_size,
        request_timeout=120,
    )

    failed = [
        item
        for item in errors
        if 'index' in item and item['index'].get('error')
    ]

    print(f'{label}: indexed={success}, failed={len(failed)}')

    if failed:
        print(f'  First {min(5, len(failed))} failures:')
        for item in failed[:5]:
            error = item['index'].get('error', {})
            print(
                f'    doc_id={item["index"].get("_id")} '
                f'type={error.get("type")} '
                f'reason={error.get("reason", "")[:120]}'
            )


def main() -> None:
    """Run this module as a command-line entry point."""
    parser = argparse.ArgumentParser(
        description='Ingest normalised housing JSONL into ElasticSearch.'
    )

    parser.add_argument(
        '--index',
        default='housing_posts',
        help='ElasticSearch index name (default: housing_posts).',
    )

    parser.add_argument(
        '--input',
        default='data/processed/normalised_housing_posts.jsonl',
        help=(
            'Pre-normalised JSONL file to ingest. '
            'Produced by normalise_housing.py. '
            'Skipped if the file does not exist.'
        ),
    )

    parser.add_argument(
        '--mapping',
        default='backend/mappings/housing_index_mapping.json',
        help='ElasticSearch mapping JSON file.',
    )

    parser.add_argument(
        '--recreate',
        action='store_true',
        help='Delete and recreate the index before ingesting.',
    )

    parser.add_argument(
        '--chunk-size',
        type=int,
        default=500,
        help='Bulk indexing chunk size (default: 500).',
    )

    # Raw source files can be normalised and ingested without regenerating the
    # complete processed dataset, which is useful during the final demo.
    parser.add_argument(
        '--extra-inputs',
        nargs='*',
        default=[],
        metavar='FILE',
        help=(
            'Raw (un-normalised) JSONL files to normalise and ingest directly. '
            'Useful for ingesting bluesky_housing.jsonl or mastodon_housing.jsonl '
            'without re-running the full normalise pipeline. '
            'Example: --extra-inputs data/bluesky_housing.jsonl '
            'data/mastodon_housing.jsonl'
        ),
    )

    args = parser.parse_args()

    input_path = Path(args.input)
    mapping_path = Path(args.mapping)

    if not mapping_path.exists():
        raise FileNotFoundError(f'Missing mapping file: {mapping_path}')

    # ------------------------------------------------------------------
    # Connect to ElasticSearch
    # ------------------------------------------------------------------
    es = get_es_client()

    try:
        info = es.info()
        print(
            f"Connected to ElasticSearch "
            f"{info.get('version', {}).get('number')} "
            f"cluster={info.get('cluster_name')}"
        )
    except Exception as exc:
        raise ConnectionError(
            'Could not connect to ElasticSearch. '
            'Check ES_HOST or ensure local ElasticSearch is running.'
        ) from exc

    ensure_index(
        es=es,
        index_name=args.index,
        mapping_path=mapping_path,
        recreate=args.recreate,
    )

    # ------------------------------------------------------------------
    # 1. Ingest the pre-normalised file (main pipeline output)
    # ------------------------------------------------------------------
    if input_path.exists():
        _run_bulk(
            es=es,
            index_name=args.index,
            actions=to_bulk_actions(args.index, read_jsonl(input_path)),
            chunk_size=args.chunk_size,
            label=str(input_path),
        )
    else:
        print(
            f'Main input not found ({input_path}), skipping. '
            f'Run normalise_housing.py first, or use --extra-inputs.'
        )

    # ------------------------------------------------------------------
    # 2. Normalise and ingest any extra raw JSONL files on the fly.
    # ------------------------------------------------------------------
    if args.extra_inputs:
        # Import normalise_record lazily so this file can run even if the
        # normalisation module is not importable (pure-ingest use case).
        try:
            from backend.analytics.normalisation.normalise_housing import (
                normalise_record,
                read_jsonl as _read_jsonl,
            )
        except ModuleNotFoundError:
            from analytics.normalisation.normalise_housing import (  # type: ignore[no-redef]
                normalise_record,
                read_jsonl as _read_jsonl,
            )

        for raw_path_str in args.extra_inputs:
            raw_path = Path(raw_path_str)

            if not raw_path.exists():
                print(f'WARNING: --extra-inputs file not found, skipping: {raw_path}')
                continue

            print(f'Normalising and ingesting: {raw_path}')

            read_count = 0
            skip_count = 0

            def _generate_actions(path: Path) -> Iterator[Dict]:
                """Generate ingestion actions from normalised input records."""
                nonlocal read_count, skip_count
                seen: set[str] = set()

                for raw in _read_jsonl(path):
                    read_count += 1
                    doc = normalise_record(raw)

                    if doc is None or not doc.get('text') or not doc.get('doc_id'):
                        skip_count += 1
                        continue

                    doc_id: str = doc['doc_id']

                    if doc_id in seen:
                        skip_count += 1
                        continue

                    seen.add(doc_id)

                    yield {
                        '_index': args.index,
                        '_id': doc_id,
                        '_source': doc,
                    }

            _run_bulk(
                es=es,
                index_name=args.index,
                actions=_generate_actions(raw_path),
                chunk_size=args.chunk_size,
                label=str(raw_path),
            )

            print(
                f'  {raw_path.name}: '
                f'read={read_count}, skipped={skip_count}'
            )


if __name__ == '__main__':
    main()

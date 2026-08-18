# COMP90024 Team 12
# Public attribution: COMP90024 Team 12; member identities removed from this portfolio copy.

"""Ingest normalised official housing rows into Elasticsearch."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import time
from typing import Dict, Iterable, Iterator

from elasticsearch import Elasticsearch, helpers

try:
    from backend.analytics.core.es_client import get_es_client
except ModuleNotFoundError:
    from analytics.core.es_client import get_es_client


def load_mapping(mapping_path: Path) -> Dict:
    """Load an Elasticsearch mapping document from disk."""
    with mapping_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def ensure_index(
    es: Elasticsearch,
    index_name: str,
    mapping_path: Path,
    recreate: bool = False,
) -> None:
    """Create or recreate the target Elasticsearch index before ingestion."""
    if recreate and es.indices.exists(index=index_name):
        es.indices.delete(index=index_name)
        print(f"Deleted existing index: {index_name}")

    if not es.indices.exists(index=index_name):
        es.indices.create(index=index_name, body=load_mapping(mapping_path))
        print(f"Created index: {index_name}")
    else:
        print(f"Index already exists: {index_name}")


def read_jsonl(path: Path) -> Iterator[Dict]:
    """Yield decoded JSON records from a JSONL file."""
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            if not line.strip():
                continue

            try:
                yield json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON on {path}:{line_no}: {exc}") from exc


def to_bulk_actions(index_name: str, docs: Iterable[Dict]) -> Iterator[Dict]:
    """Convert documents into Elasticsearch bulk API actions."""
    skipped = 0

    for doc in docs:
        doc_id = doc.get("doc_id")

        if not doc_id:
            skipped += 1
            continue

        yield {
            "_op_type": "index",
            "_index": index_name,
            "_id": doc_id,
            "_source": doc,
        }

    if skipped:
        print(f"Skipped {skipped} records without doc_id")


def set_refresh_interval(es: Elasticsearch, index_name: str, value: str) -> None:
    """Temporarily change the Elasticsearch refresh interval for faster bulk ingestion."""
    try:
        es.indices.put_settings(
            index=index_name,
            settings={
                "index": {
                    "refresh_interval": value,
                }
            },
        )
        print(f"Set {index_name} refresh_interval={value}")
    except Exception as exc:
        print(f"Warning: could not set refresh_interval={value}: {exc}")


def refresh_index(es: Elasticsearch, index_name: str) -> None:
    """Force an Elasticsearch refresh so indexed records are visible to queries."""
    try:
        es.indices.refresh(index=index_name)
        print(f"Refreshed index: {index_name}")
    except Exception as exc:
        print(f"Warning: could not refresh index {index_name}: {exc}")


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for this script."""
    parser = argparse.ArgumentParser(
        description="Parallel bulk ingest official housing rows into Elasticsearch."
    )
    parser.add_argument(
        "--index",
        default="official_housing_rows",
        help="Elasticsearch index name.",
    )
    parser.add_argument(
        "--input",
        default="backend/data/normalised_official_housing_rows.jsonl",
        help="Normalised official JSONL file.",
    )
    parser.add_argument(
        "--mapping",
        default="backend/mappings/official_housing_rows_mapping.json",
        help="Elasticsearch mapping JSON file.",
    )
    parser.add_argument(
        "--recreate",
        action="store_true",
        help="Delete and recreate the index before ingesting.",
    )
    parser.add_argument(
        "--thread-count",
        type=int,
        default=4,
        help="Number of indexing threads used by parallel_bulk.",
    )
    parser.add_argument("--chunk-size", type=int, default=1000, help="Bulk chunk size.")
    parser.add_argument("--queue-size", type=int, default=4, help="parallel_bulk queue size.")
    parser.add_argument(
        "--request-timeout",
        type=int,
        default=180,
        help="Elasticsearch request timeout in seconds.",
    )
    parser.add_argument(
        "--max-errors",
        type=int,
        default=20,
        help="Maximum number of failed indexing examples to print.",
    )
    parser.add_argument(
        "--keep-refresh",
        action="store_true",
        help="Do not disable refresh_interval during ingest.",
    )
    return parser.parse_args()


def print_progress(total: int, success_count: int, failed_count: int, start_time: float) -> None:
    """Print a compact progress line for long-running ingestion jobs."""
    elapsed = time.time() - start_time
    rate = total / elapsed if elapsed > 0 else 0
    print(
        f"Progress: total={total}, success={success_count}, "
        f"failed={failed_count}, rate={round(rate, 2)} docs/sec"
    )


def main() -> None:
    """Run this module as a command-line entry point."""
    args = parse_args()
    input_path = Path(args.input)
    mapping_path = Path(args.mapping)

    if not input_path.exists():
        raise FileNotFoundError(f"Missing input file: {input_path}")
    if not mapping_path.exists():
        raise FileNotFoundError(f"Missing mapping file: {mapping_path}")

    es = get_es_client()

    try:
        info = es.info()
        print(
            "Connected to Elasticsearch "
            f"{info.get('version', {}).get('number')} "
            f"cluster={info.get('cluster_name')}"
        )
    except Exception as exc:
        raise ConnectionError(
            "Could not connect to Elasticsearch. Check ES_HOST or make sure "
            "local Elasticsearch is running."
        ) from exc

    ensure_index(
        es=es,
        index_name=args.index,
        mapping_path=mapping_path,
        recreate=args.recreate,
    )

    # Disable refresh during the large official-data load, then restore it.
    if not args.keep_refresh:
        set_refresh_interval(es, args.index, "-1")

    bulk_client = es.options(request_timeout=args.request_timeout)
    success_count = 0
    failed_count = 0
    error_examples = []
    start_time = time.time()
    actions = to_bulk_actions(index_name=args.index, docs=read_jsonl(input_path))

    for ok, item in helpers.parallel_bulk(
        client=bulk_client,
        actions=actions,
        thread_count=args.thread_count,
        chunk_size=args.chunk_size,
        queue_size=args.queue_size,
        raise_on_error=False,
        raise_on_exception=False,
    ):
        if ok:
            success_count += 1
        else:
            failed_count += 1
            if len(error_examples) < args.max_errors:
                error_examples.append(item)

        total = success_count + failed_count

        if total % 50000 == 0:
            print_progress(total, success_count, failed_count, start_time)

    if not args.keep_refresh:
        set_refresh_interval(es, args.index, "1s")

    refresh_index(es, args.index)

    elapsed = time.time() - start_time
    rate = success_count / elapsed if elapsed > 0 else 0

    print()
    print("Parallel ingest complete")
    print(f"Indexed successfully: {success_count}")
    print(f"Failed: {failed_count}")
    print(f"Elapsed: {round(elapsed, 2)}s")
    print(f"Average rate: {round(rate, 2)} docs/sec")

    if error_examples:
        print()
        print("First error examples:")
        for error in error_examples:
            print(json.dumps(error, ensure_ascii=False, indent=2)[:3000])


if __name__ == "__main__":
    main()

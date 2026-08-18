# COMP90024 Team 12
# Public attribution: COMP90024 Team 12; member identities removed from this portfolio copy.

"""Parallel normalisation for source records that share the housing schema."""

from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import json
import os
from pathlib import Path
import re
import shutil
from typing import Any, Dict, Iterator

try:
    from backend.analytics.normalisation.normalise_housing import (
        discover_input_files,
        normalise_record,
        read_jsonl,
    )
except ModuleNotFoundError:
    from backend.analytics.normalisation.normalise_housing import (
        discover_input_files,
        normalise_record,
        read_jsonl,
    )


def safe_part_name(index: int, path: Path) -> str:
    """Create a safe filename for an intermediate normalisation part."""
    raw = str(path)
    cleaned = re.sub("[^A-Za-z0-9._-]+", "_", raw)
    return f"{index:04d}_{cleaned}.part.jsonl"


def normalise_one_file(args: tuple[int, str, str]) -> Dict[str, Any]:
    """Normalise one input file into a temporary part file."""
    index, source_path_str, tmp_dir_str = args
    source_path = Path(source_path_str)
    tmp_dir = Path(tmp_dir_str)
    part_path = tmp_dir / safe_part_name(index, source_path)

    read_count = 0
    usable_count = 0
    skipped_count = 0
    duplicate_count = 0
    local_seen_doc_ids = set()

    with part_path.open("w", encoding="utf-8") as out:
        for raw in read_jsonl(source_path):
            read_count += 1
            doc = normalise_record(raw)

            if doc is None or not doc.get("text"):
                skipped_count += 1
                continue

            doc_id = doc.get("doc_id")

            if not doc_id:
                skipped_count += 1
                continue

            # Remove duplicates inside this worker before the global merge pass.
            if doc_id in local_seen_doc_ids:
                duplicate_count += 1
                skipped_count += 1
                continue

            local_seen_doc_ids.add(doc_id)
            out.write(json.dumps(doc, ensure_ascii=False) + "\n")
            usable_count += 1

    return {
        "index": index,
        "source_path": str(source_path),
        "part_path": str(part_path),
        "read": read_count,
        "usable": usable_count,
        "skipped": skipped_count,
        "duplicates": duplicate_count,
    }


def read_jsonl_simple(path: Path) -> Iterator[Dict[str, Any]]:
    """Yield decoded JSON records without applying normalisation."""
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            if not line.strip():
                continue

            try:
                yield json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON on {path}:{line_no}: {exc}") from exc


def merge_part_files(
    part_stats: list[Dict[str, Any]],
    output_path: Path,
) -> Dict[str, int]:
    """Merge worker output files into one final JSONL file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    global_seen_doc_ids = set()
    written = 0
    global_duplicates = 0
    missing_doc_id = 0

    ordered_stats = sorted(part_stats, key=lambda item: item["index"])

    with output_path.open("w", encoding="utf-8") as out:
        for stat in ordered_stats:
            part_path = Path(stat["part_path"])

            for doc in read_jsonl_simple(part_path):
                doc_id = doc.get("doc_id")

                if not doc_id:
                    missing_doc_id += 1
                    continue

                if doc_id in global_seen_doc_ids:
                    global_duplicates += 1
                    continue

                global_seen_doc_ids.add(doc_id)
                out.write(json.dumps(doc, ensure_ascii=False) + "\n")
                written += 1

    return {
        "written": written,
        "global_duplicates": global_duplicates,
        "missing_doc_id": missing_doc_id,
    }


def main() -> None:
    """Run this module as a command-line entry point."""
    parser = argparse.ArgumentParser(
        description="Parallel normalisation for housing records."
    )
    parser.add_argument("--data-dir", default="data", help="Project data directory.")
    parser.add_argument(
        "--samples-dir",
        default="backend/harvesting/samples",
        help="Directory containing sample normalised JSONL files.",
    )
    parser.add_argument(
        "--output",
        default="backend/data/normalised_housing_posts.jsonl",
        help="Output normalised JSONL file.",
    )
    parser.add_argument(
        "--tmp-dir",
        default="data/.normalise_parts",
        help="Temporary directory for per-file part outputs.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=max(1, min(6, (os.cpu_count() or 2) - 1)),
        help="Number of parallel worker processes.",
    )
    parser.add_argument(
        "--keep-tmp",
        action="store_true",
        help="Keep temporary part files after merging.",
    )

    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    samples_dir = Path(args.samples_dir)
    output_path = Path(args.output)
    tmp_dir = Path(args.tmp_dir)
    paths = discover_input_files(data_dir, samples_dir)

    if not paths:
        raise FileNotFoundError(
            "No JSONL input files found. Checked: "
            f"{samples_dir} and {data_dir / 'gdelt_yearly_25-26_lt100mb'}"
        )

    print("Discovered input files:")
    for path in paths:
        print(f"- {path}")

    print(f"\nUsing workers={args.workers}")
    print(f"Temporary directory: {tmp_dir}")

    if tmp_dir.exists():
        shutil.rmtree(tmp_dir)

    tmp_dir.mkdir(parents=True, exist_ok=True)

    worker_args = [
        (index, str(path), str(tmp_dir))
        for index, path in enumerate(paths)
    ]
    part_stats: list[Dict[str, Any]] = []

    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        futures = [executor.submit(normalise_one_file, item) for item in worker_args]

        for future in as_completed(futures):
            stat = future.result()
            part_stats.append(stat)
            print(
                f"{stat['source_path']}: "
                f"read={stat['read']}, "
                f"usable={stat['usable']}, "
                f"skipped={stat['skipped']}, "
                f"duplicates={stat['duplicates']}"
            )

    merge_stats = merge_part_files(part_stats, output_path)

    print("\nMerge complete")
    print(f"Wrote {merge_stats['written']} normalised records to {output_path}")
    print(f"Global duplicates removed: {merge_stats['global_duplicates']}")
    print(f"Missing doc_id during merge: {merge_stats['missing_doc_id']}")

    if not args.keep_tmp:
        shutil.rmtree(tmp_dir)
        print(f"Removed temporary directory: {tmp_dir}")


if __name__ == "__main__":
    main()

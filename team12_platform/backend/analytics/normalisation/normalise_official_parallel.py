# COMP90024 Team 12
# Public attribution: COMP90024 Team 12; member identities removed from this portfolio copy.

from __future__ import annotations
import argparse
import json
import os
import re
import shutil
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, Iterator, Optional
try:
    from backend.analytics.normalisation.normalise_official import discover_official_files, normalise_official_record, read_jsonl
except ModuleNotFoundError:
    from backend.analytics.normalisation.normalise_official import discover_official_files, normalise_official_record, read_jsonl

def safe_part_name(index: int, path: Path) -> str:
    cleaned = re.sub('[^A-Za-z0-9._-]+', '_', str(path))
    return f'{index:04d}_{cleaned}.part.jsonl'

def normalise_one_file(args: tuple[int, str, str, Optional[int]]) -> Dict[str, Any]:
    index, source_path_str, tmp_dir_str, limit_per_file = args
    source_path = Path(source_path_str)
    tmp_dir = Path(tmp_dir_str)
    part_path = tmp_dir / safe_part_name(index, source_path)
    read_count = 0
    usable_count = 0
    skipped_count = 0
    start_time = time.time()
    with part_path.open('w', encoding='utf-8') as out:
        for row in read_jsonl(source_path):
            read_count += 1
            doc = normalise_official_record(row)
            if doc is None:
                skipped_count += 1
                continue
            out.write(json.dumps(doc, ensure_ascii=False, allow_nan=False) + '\n')
            usable_count += 1
            if limit_per_file is not None and usable_count >= limit_per_file:
                break
    elapsed = time.time() - start_time
    return {'index': index, 'source_path': str(source_path), 'part_path': str(part_path), 'read': read_count, 'usable': usable_count, 'skipped': skipped_count, 'elapsed_seconds': round(elapsed, 2)}

def read_jsonl_simple(path: Path) -> Iterator[Dict[str, Any]]:
    with path.open('r', encoding='utf-8') as f:
        for line_no, line in enumerate(f, start=1):
            if not line.strip():
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f'Invalid JSON on {path}:{line_no}: {exc}') from exc

def merge_part_files(part_stats: list[Dict[str, Any]], output_path: Path, global_dedupe: bool=False) -> Dict[str, int]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    ordered_stats = sorted(part_stats, key=lambda item: item['index'])
    written = 0
    duplicates = 0
    missing_doc_id = 0
    seen_doc_ids = set() if global_dedupe else None
    with output_path.open('w', encoding='utf-8') as out:
        for stat in ordered_stats:
            part_path = Path(stat['part_path'])
            for doc in read_jsonl_simple(part_path):
                doc_id = doc.get('doc_id')
                if not doc_id:
                    missing_doc_id += 1
                    continue
                if seen_doc_ids is not None:
                    if doc_id in seen_doc_ids:
                        duplicates += 1
                        continue
                    seen_doc_ids.add(doc_id)
                out.write(json.dumps(doc, ensure_ascii=False, allow_nan=False) + '\n')
                written += 1
    return {'written': written, 'duplicates': duplicates, 'missing_doc_id': missing_doc_id}

def main() -> None:
    parser = argparse.ArgumentParser(description='Parallel normalisation for official housing source rows.')
    parser.add_argument('--data-dir', default='data', help='Project data directory.')
    parser.add_argument('--output', default='backend/data/normalised_official_housing_rows.jsonl', help='Output normalised official JSONL file.')
    parser.add_argument('--tmp-dir', default='data/.official_normalise_parts', help='Temporary directory for per-file normalised part files.')
    parser.add_argument('--workers', type=int, default=max(1, min(6, (os.cpu_count() or 2) - 1)), help='Number of worker processes.')
    parser.add_argument('--max-files', type=int, default=None, help='Optional limit on number of official part files for testing.')
    parser.add_argument('--limit-per-file', type=int, default=None, help='Optional usable-row limit per source file for testing.')
    parser.add_argument('--global-dedupe', action='store_true', help='Enable global doc_id de-duplication during merge.')
    parser.add_argument('--keep-tmp', action='store_true', help='Keep temporary part files after merging.')
    args = parser.parse_args()
    data_dir = Path(args.data_dir)
    output_path = Path(args.output)
    tmp_dir = Path(args.tmp_dir)
    paths = discover_official_files(data_dir)
    if args.max_files is not None:
        paths = paths[:args.max_files]
    if not paths:
        raise FileNotFoundError(f"No official source JSONL files found under {data_dir / 'official_sources_json_v2'}")
    print('Discovered official source JSONL files:')
    for path in paths:
        print(f'- {path}')
    print()
    print(f'workers={args.workers}')
    print(f'max_files={args.max_files}')
    print(f'limit_per_file={args.limit_per_file}')
    print(f'global_dedupe={args.global_dedupe}')
    print(f'tmp_dir={tmp_dir}')
    print(f'output={output_path}')
    print()
    if tmp_dir.exists():
        shutil.rmtree(tmp_dir)
    tmp_dir.mkdir(parents=True, exist_ok=True)
    worker_args = [(index, str(path), str(tmp_dir), args.limit_per_file) for index, path in enumerate(paths)]
    start_time = time.time()
    part_stats: list[Dict[str, Any]] = []
    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        futures = [executor.submit(normalise_one_file, item) for item in worker_args]
        for future in as_completed(futures):
            stat = future.result()
            part_stats.append(stat)
            print(f"{stat['source_path']}: read={stat['read']}, usable={stat['usable']}, skipped={stat['skipped']}, elapsed={stat['elapsed_seconds']}s")
    merge_stats = merge_part_files(part_stats=part_stats, output_path=output_path, global_dedupe=args.global_dedupe)
    total_elapsed = time.time() - start_time
    print()
    print('Merge complete')
    print(f"Wrote {merge_stats['written']} official rows to {output_path}")
    print(f"Global duplicates removed: {merge_stats['duplicates']}")
    print(f"Missing doc_id during merge: {merge_stats['missing_doc_id']}")
    print(f'Total elapsed: {round(total_elapsed, 2)}s')
    if not args.keep_tmp:
        shutil.rmtree(tmp_dir)
        print(f'Removed temporary directory: {tmp_dir}')
    else:
        print(f'Kept temporary directory: {tmp_dir}')
if __name__ == '__main__':
    main()

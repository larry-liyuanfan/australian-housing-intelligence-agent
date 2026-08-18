# COMP90024 Team 12
# Public attribution: COMP90024 Team 12; member identities removed from this portfolio copy.

"""Harvesting utility for inspecting or normalising collected source data."""

import json
import sys
from pathlib import Path


def inspect_jsonl(file_path: str, max_preview_chars: int = 2000) -> None:
    """Print a quick structure preview for a JSONL file."""
    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    count = 0
    first_record = None

    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                count += 1
                if first_record is None:
                    first_record = json.loads(line)

    print(f"File: {file_path}")
    print(f"Number of records: {count}")

    if first_record is None:
        print("No records found.")
        return

    print("\nTop-level fields:")
    for key in first_record.keys():
        print(f"- {key}")

    print("\nFirst record preview:")
    print(json.dumps(first_record, indent=2, ensure_ascii=False)[:max_preview_chars])


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python inspect_jsonl.py <path_to_jsonl_file>")
        sys.exit(1)

    inspect_jsonl(sys.argv[1])

# COMP90024 Team 12
# Public attribution: COMP90024 Team 12; member identities removed from this portfolio copy.

"""Normalise official housing rows into the comparison-data schema."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any, Dict, Iterable, Iterator, Optional


MONTHS = {
    "january": "01",
    "february": "02",
    "march": "03",
    "april": "04",
    "may": "05",
    "june": "06",
    "july": "07",
    "august": "08",
    "september": "09",
    "october": "10",
    "november": "11",
    "december": "12",
}

PREFERRED_LABEL_KEYS = [
    "Suburb",
    "suburb",
    "LGA",
    "lga",
    "Region",
    "region",
    "Area",
    "area",
    "Local Government Area",
    "Unnamed: 0",
    "Unnamed: 1",
]


def stable_hash(value: Any) -> str:
    """Create a stable hash for repeatable document identifiers."""
    encoded = json.dumps(value, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha1(encoded).hexdigest()[:16]


def read_jsonl(path: Path) -> Iterator[Dict[str, Any]]:
    """Yield decoded JSON records from a JSONL file."""
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            if not line.strip():
                continue

            try:
                yield json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON on {path}:{line_no}: {exc}") from exc


def discover_official_files(data_dir: Path) -> list[Path]:
    """Find official-data JSONL files under the configured data directory."""
    candidate_roots = [
        data_dir / "official_sources_json_v3",
        data_dir / "official_sources_json_v2",
    ]
    paths: list[Path] = []

    for root in candidate_roots:
        if not root.exists():
            continue

        paths.extend(sorted(root.glob("official_v*_part*.jsonl")))
        paths.extend(sorted(root.glob("official_sources_part*.jsonl")))
        paths.extend(sorted(root.glob("*.jsonl")))

    unique_paths: list[Path] = []
    seen: set[Path] = set()

    for path in paths:
        resolved = path.resolve()

        if resolved in seen:
            continue

        unique_paths.append(path)
        seen.add(resolved)

    if not unique_paths:
        raise FileNotFoundError(
            "No official source JSONL files found. Checked: "
            + ", ".join(str(root) for root in candidate_roots)
        )

    return unique_paths


def infer_source_group(source_file: str) -> str:
    """Infer the official-data source group from a source filename."""
    if not source_file:
        return "unknown"
    if "/" in source_file:
        return source_file.split("/", 1)[0]
    if source_file.startswith("manifest_"):
        return "manifest"
    return "unknown"


def infer_state(source_file: str, source_group: str) -> str:
    """Infer an Australian state or territory from source metadata."""
    text = f"{source_group} {source_file}".lower()

    if "nsw" in text:
        return "NSW"
    if "vic" in text or "victoria" in text:
        return "VIC"
    if "qld" in text or "queensland" in text:
        return "QLD"
    if "sa_" in text or "south-australia" in text or "south australia" in text:
        return "SA"
    if "tas" in text or "tasmania" in text:
        return "TAS"
    if "wa_" in text or "western-australia" in text or "western australia" in text:
        return "WA"
    if "aus" in text or "australia" in text:
        return "AUS"

    return "unknown"


def infer_period(source_file: str) -> str:
    """Infer the reporting period from an official-data filename."""
    name = source_file.lower()

    match = re.search(r"(20\d{2})[-_ ](0[1-9]|1[0-2])", name)
    if match:
        return f"{match.group(1)}-{match.group(2)}"

    for month_name, month_no in MONTHS.items():
        match = re.search(rf"{month_name}[-_ ]*(20\d{{2}})", name)
        if match:
            return f"{match.group(1)}-{month_no}"

    match = re.search(
        r"(january|february|march|april|may|june|july|august|"
        r"september|october|november|december)(\d{2})",
        name,
    )
    if match:
        return f"20{match.group(2)}-{MONTHS[match.group(1)]}"

    match = re.search(r"year[-_ ]*(20\d{2})", name)
    if match:
        return match.group(1)

    match = re.search(r"(20\d{2})", name)
    if match:
        return match.group(1)

    return "unknown"


def clean_value(value: Any) -> Optional[Any]:
    """Clean scalar values while preserving useful numeric and text content."""
    if value is None:
        return None

    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return value

    if isinstance(value, str):
        stripped = value.strip()

        if not stripped:
            return None
        if stripped.lower() in {"nan", "none", "null", "nat"}:
            return None

        return stripped

    return value


def extract_non_null_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """Keep only populated fields from an official-data row."""
    output = {}

    for key, value in data.items():
        cleaned = clean_value(value)
        if cleaned is not None:
            output[key] = cleaned

    return output


def count_numeric_values(data: Dict[str, Any]) -> int:
    """Count numeric fields in an official-data row."""
    count = 0

    for value in data.values():
        if isinstance(value, (int, float)):
            count += 1
            continue

        if isinstance(value, str):
            try:
                float(value.replace(",", ""))
                count += 1
            except ValueError:
                continue

    return count


def infer_row_label(non_null_data: Dict[str, Any]) -> str:
    """Build a readable label for an official-data row."""
    for key in PREFERRED_LABEL_KEYS:
        value = non_null_data.get(key)
        if value is not None:
            return str(value)

    for value in non_null_data.values():
        if isinstance(value, str) and value.strip():
            return value.strip()

    return ""


def infer_row_type(source_file: str, non_null_data: Dict[str, Any]) -> str:
    """Infer a broad official-data row type for filtering and aggregation."""
    if source_file.startswith("manifest_"):
        return "manifest"
    if not non_null_data:
        return "empty"

    values_text = " ".join(str(value).lower() for value in non_null_data.values())
    note_markers = [
        "source:",
        "notes:",
        "note:",
        "excludes",
        "rounded",
        "where there are",
    ]
    header_markers = [
        "row labels",
        "column labels",
        "count",
        "median",
        "total count",
        "total median",
    ]

    if any(marker in values_text for marker in note_markers):
        return "note"
    if any(marker in values_text for marker in header_markers):
        return "header"

    return "data"


def build_text(
    source_file: str,
    source_group: str,
    sheet: str,
    state: str,
    period: str,
    row_label: str,
    non_null_data: Dict[str, Any],
) -> str:
    """Build searchable text from official-data metadata and values."""
    values = [str(value) for value in non_null_data.values() if value is not None]
    parts = [
        f"Source file: {source_file}",
        f"Source group: {source_group}",
        f"Sheet: {sheet}" if sheet else "",
        f"State: {state}" if state else "",
        f"Period: {period}" if period else "",
        f"Row label: {row_label}" if row_label else "",
        "Values: " + " | ".join(values[:80]) if values else "",
    ]

    return "\n".join(part for part in parts if part)


def normalise_official_record(row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Map one extracted official-data row into the official ES schema."""
    source_file = row.get("_source_file", "") or ""
    record_index = row.get("_record_index")
    data = row.get("data", {}) or {}

    if not isinstance(data, dict):
        return None
    if data.get("_binary_skipped"):
        return None
    if source_file == ".DS_Store":
        return None

    non_null_data = extract_non_null_data(data)

    if not non_null_data:
        return None

    source_group = infer_source_group(source_file)
    state = infer_state(source_file, source_group)
    period = infer_period(source_file)
    sheet = str(non_null_data.get("_sheet", "") or "")
    row_label = infer_row_label(non_null_data)
    row_type = infer_row_type(source_file, non_null_data)

    if row_type == "manifest":
        return None

    doc_id_raw = f"{source_file}:{record_index}:{stable_hash(non_null_data)}"
    doc_id = f"official_{stable_hash(doc_id_raw)}"

    return {
        "doc_id": doc_id,
        "source_file": source_file,
        "source_group": source_group,
        "record_index": int(record_index) if isinstance(record_index, int) else None,
        "sheet": sheet,
        "state": state,
        "period": period,
        "row_type": row_type,
        "row_label": row_label,
        "text": build_text(
            source_file=source_file,
            source_group=source_group,
            sheet=sheet,
            state=state,
            period=period,
            row_label=row_label,
            non_null_data=non_null_data,
        ),
        "non_null_count": len(non_null_data),
        "numeric_count": count_numeric_values(non_null_data),
        "raw_data": non_null_data,
    }


def normalise_files(
    paths: Iterable[Path],
    limit: Optional[int] = None,
) -> Iterator[Dict[str, Any]]:
    """Normalise a collection of input files into project documents."""
    written = 0

    for path in paths:
        read_count = 0
        usable_count = 0
        skipped_count = 0

        for row in read_jsonl(path):
            read_count += 1
            doc = normalise_official_record(row)

            if doc is None:
                skipped_count += 1
                continue

            usable_count += 1
            written += 1
            yield doc

            if limit is not None and written >= limit:
                print(
                    f"{path}: read={read_count}, "
                    f"usable={usable_count}, skipped={skipped_count}"
                )
                return

        print(
            f"{path}: read={read_count}, "
            f"usable={usable_count}, skipped={skipped_count}"
        )


def write_jsonl(docs: Iterable[Dict[str, Any]], output_path: Path) -> int:
    """Write normalised records to a JSONL output file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0

    with output_path.open("w", encoding="utf-8") as handle:
        for doc in docs:
            handle.write(json.dumps(doc, ensure_ascii=False, allow_nan=False) + "\n")
            count += 1

    return count


def main() -> None:
    """Run this module as a command-line entry point."""
    parser = argparse.ArgumentParser(
        description="Normalise official housing source rows."
    )
    parser.add_argument("--data-dir", default="data", help="Project data directory.")
    parser.add_argument(
        "--output",
        default="backend/data/normalised_official_housing_rows.jsonl",
        help="Output official normalised JSONL file.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional maximum number of records for testing.",
    )

    args = parser.parse_args()
    data_dir = Path(args.data_dir)
    output_path = Path(args.output)
    paths = discover_official_files(data_dir)

    print("Discovered official source JSONL files:")
    for path in paths:
        print(f"- {path}")

    count = write_jsonl(normalise_files(paths, limit=args.limit), output_path)
    print(f"Wrote {count} official rows to {output_path}")


if __name__ == "__main__":
    main()

# COMP90024 Team 12
# Public attribution: COMP90024 Team 12; member identities removed from this portfolio copy.

"""Lightweight repository smoke tests for the final submission.

These checks avoid live Elasticsearch, Kubernetes, and Fission dependencies.
They verify that core repository assets are readable and that the sample
harvesting data can be normalised into the expected housing-post schema.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
REQUIRED_POST_FIELDS = {
    "doc_id",
    "platform",
    "source",
    "query_keyword",
    "title",
    "text",
    "created_at",
    "collected_at",
    "url",
    "city_context",
    "topic",
    "australia_connection",
    "raw_metadata",
}


def assert_true(condition: bool, message: str) -> None:
    """Raise a readable assertion error for smoke-test checks."""
    if not condition:
        raise AssertionError(message)


def load_json(path: Path):
    """Load a JSON file used by the smoke tests."""
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def test_mapping_files() -> None:
    """Verify that Elasticsearch mapping files are valid JSON objects."""
    mapping_paths = [
        ROOT / "backend/mappings/housing_index_mapping.json",
        ROOT / "backend/mappings/official_housing_rows_mapping.json",
        ROOT / "database/housing_index_mapping.json",
    ]

    for path in mapping_paths:
        data = load_json(path)
        properties = data.get("mappings", {}).get("properties", {})
        assert_true(bool(properties), f"Mapping has no properties: {path}")


def test_sample_normalisation() -> None:
    """Verify that sample source records normalise into required fields."""
    sys.path.insert(0, str(ROOT))

    from backend.harvesting.src.normalise import normalise_record

    sample_path = ROOT / "backend/harvesting/sample_raw_posts.json"
    records = load_json(sample_path)
    docs = []

    for record in records:
        docs.extend(normalise_record(record))

    assert_true(len(docs) >= 4, "Expected at least one normalised document per sample source")

    doc_ids = set()
    platforms = set()

    for doc in docs:
        missing = REQUIRED_POST_FIELDS - set(doc)
        assert_true(not missing, f"Missing fields in {doc.get('doc_id')}: {sorted(missing)}")
        assert_true(bool(doc["doc_id"]), "doc_id must not be empty")
        assert_true(bool(doc["text"]), f"text must not be empty for {doc['doc_id']}")
        assert_true(doc["doc_id"] not in doc_ids, f"Duplicate doc_id: {doc['doc_id']}")

        doc_ids.add(doc["doc_id"])
        platforms.add(doc["platform"])

    assert_true(
        {"bluesky", "mastodon", "gdelt_doc", "youtube"}.issubset(platforms),
        f"Missing expected platforms: {platforms}",
    )


def test_notebook_is_valid_json_and_python() -> None:
    """Verify that the notebook JSON and code cells are syntactically valid."""
    notebook_path = ROOT / "frontend/housing_api_dashboard.ipynb"
    notebook = load_json(notebook_path)

    assert_true(notebook.get("nbformat") == 4, "Notebook should use nbformat 4")

    for index, cell in enumerate(notebook.get("cells", []), start=1):
        if cell.get("cell_type") != "code":
            continue

        source = "".join(cell.get("source", []))
        # Skip shell commands and magic lines
        if source.strip().startswith(("!", "%", "pip", "apt", "npm")):
            continue
        ast.parse(source, filename=f"notebook cell {index}")


def main() -> None:
    """Run this module as a command-line entry point."""
    tests = [
        test_mapping_files,
        test_sample_normalisation,
        test_notebook_is_valid_json_and_python,
    ]

    for test in tests:
        test()
        print(f"PASS {test.__name__}")

    print("All smoke tests passed.")


if __name__ == "__main__":
    main()

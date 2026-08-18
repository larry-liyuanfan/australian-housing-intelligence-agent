from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable


EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
URL = re.compile(r"https?://\S+", re.I)
HANDLE = re.compile(r"(?<!\w)@[A-Za-z0-9_.-]+")
PHONE = re.compile(r"(?<!\d)(?:\+?61|0)[2-478](?:[ -]?\d){8}(?!\d)")


def redact_text(value: str) -> str:
    value = EMAIL.sub("[EMAIL]", value)
    value = PHONE.sub("[PHONE]", value)
    value = HANDLE.sub("[HANDLE]", value)
    return URL.sub("[URL]", value)


def stable_id(source_id: str, salt: str) -> str:
    if not salt:
        raise ValueError("A non-empty job-specific salt is required")
    return hashlib.sha256(f"{salt}:{source_id}".encode("utf-8")).hexdigest()[:24]


def public_record(raw: dict[str, Any], salt: str) -> dict[str, Any]:
    """Create an allowlisted, deidentified record for an offline index job."""
    source_id = str(raw.get("doc_id") or raw.get("id") or raw.get("uri") or "")
    text = redact_text(str(raw.get("text") or raw.get("title") or ""))
    return {
        "doc_id": stable_id(source_id or text, salt),
        "platform": str(raw.get("platform") or raw.get("source") or "unknown")[:64],
        "title": redact_text(str(raw.get("title") or ""))[:500],
        "text": text[:10000],
        "created_at": raw.get("created_at"),
        "city_context": raw.get("city_context"),
        "topic": raw.get("topic") or raw.get("subtopic"),
        "sentiment": raw.get("sentiment"),
    }


def iter_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON on line {line_number}") from exc
            if isinstance(row, dict):
                yield row


def main() -> None:
    parser = argparse.ArgumentParser(description="Deidentify a private JSONL file for controlled offline indexing")
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--salt-env", default="HOUSING_HASH_SALT")
    args = parser.parse_args()
    import os
    salt = os.getenv(args.salt_env, "")
    if not salt:
        raise SystemExit(f"Set {args.salt_env}; do not commit the salt")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        for raw in iter_jsonl(args.input):
            handle.write(json.dumps(public_record(raw, salt), ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()

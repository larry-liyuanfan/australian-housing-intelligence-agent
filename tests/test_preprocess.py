from __future__ import annotations

from housing_agent.preprocess import public_record, redact_text


def test_redaction_removes_common_identifiers() -> None:
    cleaned = redact_text("Email user@example.org or call 0412 345 678; see https://example.org/x and @handle")
    assert "user@example.org" not in cleaned
    assert "0412" not in cleaned
    assert "https://" not in cleaned
    assert "@handle" not in cleaned


def test_public_record_is_allowlisted_and_hashes_id() -> None:
    raw = {"id": "private-id", "text": "hello @person", "platform": "test", "raw_metadata": {"email": "private@example.org"}}
    result = public_record(raw, "test-only-salt")
    assert result["doc_id"] != "private-id"
    assert "raw_metadata" not in result
    assert "@person" not in result["text"]

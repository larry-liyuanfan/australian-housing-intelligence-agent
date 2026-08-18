# COMP90024 Team 12
# Public attribution: COMP90024 Team 12; member identities removed from this portfolio copy.

"""Unit tests for sentiment analysis and normalisation functions."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.analytics.sentiment.sentiment import analyse_sentiment
from backend.analytics.normalisation.normalise_housing import (
    translate_gdelt_code,
    safe_doc_id,
    normalise_date,
)


def test_sentiment_negative():
    assert analyse_sentiment("rental crisis devastating families")["sentiment_label"] == "negative"
    assert analyse_sentiment("homelessness surges evictions skyrocket")["sentiment_label"] == "negative"


def test_sentiment_positive():
    assert analyse_sentiment("affordable housing initiative helps buyers")["sentiment_label"] == "positive"


def test_sentiment_neutral():
    assert analyse_sentiment("")["sentiment_label"] == "neutral"


def test_translate_gdelt_code():
    assert translate_gdelt_code("econ_housing_prices") == "housing prices"
    assert translate_gdelt_code("crisislex_c05_need_of_shelters") == "need for shelter"


def test_safe_doc_id():
    assert safe_doc_id("bluesky", "at://test/post/123") is not None
    assert safe_doc_id("mastodon", "") is not None  # falls back to 'missing'
    assert safe_doc_id("youtube", None) is not None


def test_normalise_date():
    assert normalise_date("2026-01-01T00:00:00Z") is not None
    assert normalise_date("") is None
    assert normalise_date(None) is None


def main():
    tests = [
        test_sentiment_negative,
        test_sentiment_positive,
        test_sentiment_neutral,
        test_translate_gdelt_code,
        test_safe_doc_id,
        test_normalise_date,
    ]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print("All unit tests passed.")


if __name__ == "__main__":
    main()

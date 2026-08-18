from __future__ import annotations

from datetime import date

from .schemas import AustralianRegion, HousingDocument


DATA_VERSION = "deidentified-fixtures-v1"


def fixture_documents() -> list[HousingDocument]:
    """Return synthetic/aggregated records safe for tests and public demos.

    These are not copied social-media posts and do not represent population
    prevalence. They exist to exercise retrieval and tool contracts.
    """

    rows = [
        ("d01", "discussion", "Rent increases in Melbourne", "Public discussion frequently mentions rent increases, inspection pressure and difficulty finding an affordable lease in Melbourne.", "synthetic-discussion-summary", "VIC", "2026-02-01", "rental stress", -0.72, "gdelt"),
        ("d02", "discussion", "Sydney rental competition", "Aggregated discussion describes competitive applications, high weekly rent and limited vacancy across Sydney.", "synthetic-discussion-summary", "NSW", "2026-02-15", "rental stress", -0.66, "bluesky"),
        ("d03", "discussion", "Brisbane housing supply", "Public posts discuss new housing supply, commuting distance and affordability trade-offs in Brisbane.", "synthetic-discussion-summary", "QLD", "2026-03-01", "housing supply", -0.28, "mastodon"),
        ("d04", "discussion", "Perth first-home buyers", "A deidentified aggregate notes mortgage deposit concerns and competition among first-home buyers in Perth.", "synthetic-discussion-summary", "WA", "2026-03-12", "home ownership", -0.33, "youtube"),
        ("d05", "discussion", "Adelaide bond and lease concerns", "Discussion summaries highlight bond return disputes, lease renewals and rent increases in Adelaide.", "synthetic-discussion-summary", "SA", "2026-04-02", "tenancy", -0.61, "bluesky"),
        ("d06", "discussion", "Hobart availability", "Aggregated public discussion reports difficulty locating long-term rentals and concern about seasonal availability in Hobart.", "synthetic-discussion-summary", "TAS", "2026-04-18", "availability", -0.55, "mastodon"),
        ("d07", "discussion", "National homelessness framing", "News-linked discussion uses homelessness, temporary accommodation and social housing as recurring themes.", "synthetic-discussion-summary", "AU", "2026-05-01", "homelessness", -0.79, "gdelt"),
        ("d08", "discussion", "Canberra rental sentiment", "Deidentified comments describe mixed sentiment about rental price growth and proximity to employment in Canberra.", "synthetic-discussion-summary", "ACT", "2026-05-07", "rental stress", -0.24, "youtube"),
        ("o01", "official", "Victoria rental indicator context", "Official housing table summary for Victoria includes median rent and rental affordability indicators. Values must be checked against the source release before policy use.", "public-statistics-synthetic-fixture", "VIC", "2026-01-01", "rental stress", None, "official"),
        ("o02", "official", "New South Wales vacancy context", "Official summary for New South Wales contains vacancy and housing cost indicators, suitable for contextual comparison rather than causal inference.", "public-statistics-synthetic-fixture", "NSW", "2026-01-01", "rental stress", None, "official"),
        ("o03", "official", "Queensland supply context", "Official Queensland tables describe dwelling approvals and housing supply indicators by period.", "public-statistics-synthetic-fixture", "QLD", "2026-01-01", "housing supply", None, "official"),
        ("o04", "official", "National homelessness services context", "An official aggregate describes demand for homelessness services nationally; online discussion volume is not a prevalence estimate.", "public-statistics-synthetic-fixture", "AU", "2026-01-01", "homelessness", None, "official"),
        ("o05", "official", "South Australia tenancy context", "Official tables provide regional rental and tenancy context for South Australia.", "public-statistics-synthetic-fixture", "SA", "2026-01-01", "tenancy", None, "official"),
        ("o06", "official", "Western Australia ownership context", "Official Western Australia aggregates include dwelling values and first-home buyer finance indicators.", "public-statistics-synthetic-fixture", "WA", "2026-01-01", "home ownership", None, "official"),
    ]
    return [
        HousingDocument(
            doc_id=doc_id,
            corpus=corpus,
            title=title,
            text=text,
            source=source,
            region=AustralianRegion(region),
            period=date.fromisoformat(period),
            topic=topic,
            sentiment=sentiment,
            platform=platform,
            metrics={},
        )
        for doc_id, corpus, title, text, source, region, period, topic, sentiment, platform in rows
    ]

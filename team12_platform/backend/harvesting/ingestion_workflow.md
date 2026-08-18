# Harvesting to Ingestion Workflow

This document describes how harvested online housing-discussion data moves from
raw JSONL files into the backend analytics and Elasticsearch pipeline.

## 1. Raw Data Collection

Raw data is collected from multiple online sources:

- BlueSky
- Mastodon
- GDELT
- YouTube

Each source has a different JSON structure. For example, BlueSky text is stored
under `post.text`, Mastodon status content is HTML, GDELT records contain
article metadata and text, and YouTube records contain video metadata plus
comments.

## 2. Inspection

Before normalisation, JSONL files can be inspected with:

```bash
python3 backend/harvesting/src/inspect_jsonl.py <input_jsonl>
```

For YouTube-specific files:

```bash
python3 backend/harvesting/src/inspect_youtube.py <youtube_jsonl>
```

## 3. Normalisation

The normalisation step converts source-specific records into the shared
`housing_posts` schema. This keeps downstream Elasticsearch ingestion and
Notebook analysis consistent across sources.

Expected common fields include:

- `doc_id`
- `source`
- `created_at`
- `text`
- `housing_relevant`
- `sentiment_label`
- `region`
- `source_url`

## 4. Elasticsearch Ingestion

Normalised records are passed into the backend ingestion module and written to
the `housing_posts` index. Official data is written to
`official_housing_rows` and remains a comparative dataset.

## 5. Demo and Reporting

For the final demo, the team should show:

- a small raw-source sample,
- the normalised output schema,
- Elasticsearch index health,
- the Notebook reading the ingested or exported analysis data.

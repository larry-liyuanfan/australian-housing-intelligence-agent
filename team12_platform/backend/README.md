# Backend README

## Purpose

The backend connects processed housing data, Elasticsearch storage, analytical
APIs, Fission functions, and the Jupyter Notebook frontend.

```text
raw / processed data
-> normalisation
-> Elasticsearch ingestion
-> analytics queries
-> Flask REST API / Fission functions
-> Jupyter Notebook frontend
```

Most commands in this document should be run from the project root, not from
inside `backend/`.

## Current Backend Structure

```text
backend/
|-- __init__.py
|-- Dockerfile
|-- README.md
|-- requirements.txt
|-- analytics/
|-- api/
|-- deployment/
|-- harvesting/
`-- mappings/
```

Functional folders:

```text
api/          Flask API entry points and route definitions
analytics/    Elasticsearch client, normalisation, ingestion, and query logic
deployment/   Kubernetes and Fission deployment files
harvesting/   harvesting-side utilities, schemas, and source samples
mappings/     Elasticsearch index mappings
```

## Python Requirements

The canonical dependency file is:

```text
backend/requirements.txt
```

It covers the backend API, Elasticsearch ingestion/query helpers,
normalisation scripts, smoke tests, and the final notebook frontend. The
harvesting utilities currently use Python standard-library modules only, so
there is no separate harvesting requirements file.

Install from the project root with:

```bash
python -m pip install -r backend/requirements.txt
```

`__init__.py` files are intentionally retained. They make these directories
importable Python packages and support imports such as
`backend.analytics.core.es_client`.

## Core Elasticsearch Indexes

```text
housing_posts
  Public-discourse records from BlueSky, Mastodon, GDELT, and YouTube.

official_housing_rows
  Official housing evidence used for comparison and context.
```

The two indexes are intentionally separate because official datasets and online
discussion data have different structures and sampling frames.

## Processed Data Location

The processed JSONL files live at project-root level:

```text
data/processed/
|-- normalised_housing_posts.jsonl
`-- normalised_official_housing_rows.jsonl
```

These files are currently tracked as part of the final submission dataset. New
large local dumps should not be added casually; add them only when they are part
of the documented submission data and the team agrees they are required.

## Normalisation

### Public Discourse

Expected input sources may include:

```text
data/bluesky_au/*.jsonl
data/mastodon_au/*.jsonl
data/gdelt_yearly/**/articles/*.jsonl
data/gdelt_yearly/**/gkg_high.jsonl
data/youtube-demo/youtube_master_part*.jsonl
```

Run from the project root:

```bash
python -m backend.analytics.normalisation.normalise_housing \
  --data-dir data \
  --samples-dir backend/harvesting/samples \
  --output data/processed/normalised_housing_posts.jsonl
```

Normalised public-discourse rows include fields such as:

```text
doc_id
platform
source
query_keyword
subtopic
title
text
created_at
collected_at
url
city_context
sentiment
sentiment_label
subjectivity
raw_metadata
```

### Official Evidence

Official source rows are stored under:

```text
data/official_sources_json_v3/official_v3_part*.jsonl
```

Run from the project root:

```bash
python -m backend.analytics.normalisation.normalise_official \
  --data-dir data \
  --output data/processed/normalised_official_housing_rows.jsonl
```

Normalised official rows include fields such as:

```text
doc_id
source_file
source_group
state
period
row_type
row_label
text
raw_data
```

## Ingestion

### Housing Posts

```bash
python -m backend.analytics.ingestion.ingest_housing \
  --index housing_posts \
  --input data/processed/normalised_housing_posts.jsonl \
  --mapping backend/mappings/housing_index_mapping.json
```

Use `--recreate` only when intentionally deleting and rebuilding the index.

### Official Rows

```bash
python -m backend.analytics.ingestion.ingest_official \
  --index official_housing_rows \
  --input data/processed/normalised_official_housing_rows.jsonl \
  --mapping backend/mappings/official_housing_rows_mapping.json \
  --thread-count 4 \
  --chunk-size 1000
```

## API Layer

Unified Flask entry point:

```text
backend/api/app.py
```

It registers:

```text
housing_routes.py
official_routes.py
analysis_routes.py
```

Run from the project root:

```bash
export ES_HOST=http://localhost:9200
export ES_INDEX=housing_posts
export OFFICIAL_ES_INDEX=official_housing_rows
export PORT=9093

python -m backend.api.app
```

Useful checks:

```bash
export API_BASE=http://localhost:9093

curl "$API_BASE/api/health"
curl "$API_BASE/api/analysis/health"
curl "$API_BASE/api/official/overview"
curl "$API_BASE/api/analysis/housing/sentiment-summary"
curl "$API_BASE/api/analysis/housing/top-query-keywords"
curl "$API_BASE/api/analysis/housing/by-region-cleaned"
```

Expected result: the health routes should return `status = ok`, and both
Elasticsearch indexes should have non-zero document counts after ingestion.

## Analytics Layer

```text
backend/analytics/
|-- core/
|-- dashboard/
|-- ingestion/
|-- normalisation/
|-- official/
|-- platform/
|-- regional/
|-- sentiment/
`-- topic/
```

Main responsibilities:

```text
core/           shared Elasticsearch client and utilities
normalisation/  source-specific data conversion into shared schemas
ingestion/      Elasticsearch index creation and bulk loading
platform/       source/platform distribution queries
regional/       city/state cleaning and aggregation
sentiment/      sentiment scoring and sentiment queries
topic/          keyword and subtopic aggregations
official/       official-data comparison queries
dashboard/      compact overview payloads for the frontend
```

## Mappings

Mapping files:

```text
backend/mappings/housing_index_mapping.json
backend/mappings/official_housing_rows_mapping.json
```

These define field types for the `housing_posts` and `official_housing_rows`
indexes.

## Frontend Connection

The final frontend is the notebook:

```text
frontend/housing_insecurity_dashboard_review_aligned.ipynb
```

The notebook can read exported/processed data and, where configured, backend API
responses. It is the main demo interface for charts, summaries, official-data
comparison, and narrative explanation.

## Deployment

Deployment files live under:

```text
backend/deployment/
|-- k8s/
`-- fission/
```

Typical cloud flow:

```text
Docker image
-> Kubernetes deployment/service
-> Elasticsearch connection through environment variables
-> Fission functions for serverless checks and small events
-> Notebook/API demo
```

Important environment variables:

```text
ES_HOST
ES_INDEX
OFFICIAL_ES_INDEX
PORT
FLASK_DEBUG
```

## Interpretation Notes

```text
Official source count = indexed row coverage, not housing severity.
Regional discussion count = mention count, not actual regional severity.
Sentiment score = approximate NLP signal, not a complete public opinion measure.
Topic/keyword charts = cleaned summaries, not full linguistic analysis.
```

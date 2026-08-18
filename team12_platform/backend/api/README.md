# COMP90024 Team 12
# Public attribution: COMP90024 Team 12; member identities removed from this portfolio copy.

# API README

This folder exposes backend data and analysis results as REST APIs for the frontend dashboard.

```text
backend/api/
├── app.py
├── housing_routes.py
├── official_routes.py
└── analysis_routes.py
```

Set the base URL before testing:

```bash
export API_BASE=http://localhost:9093
```

For cloud or Kubernetes deployment, replace `API_BASE` with the deployed backend URL.

---

## 1. `app.py`

Purpose:

```text
unified Flask entry point
```

It registers:

```text
housing_routes.py
official_routes.py
analysis_routes.py
```

Run locally:

```bash
export ES_HOST=http://localhost:9200
export ES_INDEX=housing_posts
export OFFICIAL_ES_INDEX=official_housing_rows
export PORT=9093

python -m backend.api.app
```

Health checks:

```bash
curl "$API_BASE/api/health"
curl "$API_BASE/api/analysis/health"
curl "$API_BASE/api/official/health"
```

If the frontend is served from a different port, `app.py` should enable CORS.

---

## 2. `housing_routes.py`

Index:

```text
housing_posts
```

Data:

```text
public discourse records
GDELT / YouTube / BlueSky / Mastodon
```

Main routes:

```text
GET /api/health
GET /api/housing/search
GET /api/housing/volume-by-platform
GET /api/housing/timeseries
GET /api/housing/top-query-keywords
```

Examples:

```bash
curl "$API_BASE/api/housing/volume-by-platform"
curl "$API_BASE/api/housing/timeseries?interval=month"
curl "$API_BASE/api/housing/top-query-keywords"
curl "$API_BASE/api/housing/search?q=rental%20crisis&size=5"
```

Frontend use:

```text
cross-platform discussion volume
public discussion trend
keyword ranking
search table
```

Note:

```text
/api/housing/volume-by-platform may return results rather than buckets.
The frontend should support both keys.
```

---

## 3. `official_routes.py`

Index:

```text
official_housing_rows
```

Data:

```text
official housing evidence
rental bond / census / median rent / housing stress / official rows
```

Main routes:

```text
GET /api/official/health
GET /api/official/overview
GET /api/official/source-groups
GET /api/official/by-state
GET /api/official/by-period
GET /api/official/search
```

Examples:

```bash
curl "$API_BASE/api/official/health"
curl "$API_BASE/api/official/overview"
curl "$API_BASE/api/official/source-groups"
curl "$API_BASE/api/official/by-state"
curl "$API_BASE/api/official/by-period"
curl "$API_BASE/api/official/search?q=median%20rent&size=5"
```

Frontend use:

```text
official source coverage
official state distribution
official period coverage
official evidence search
```

Interpretation:

```text
Official source counts are indexed row counts.
They show data coverage, not housing severity.
```

---

## 4. `analysis_routes.py`

Indexes used:

```text
housing_posts
official_housing_rows
```

Purpose:

```text
frontend-ready analytical outputs
```

This file combines:

```text
sentiment analysis
platform analysis
topic / keyword analysis
regional cleaning
official evidence comparison
dashboard overview
```

---

## 4.1 Health

```bash
curl "$API_BASE/api/analysis/health"
```

Expected fields:

```text
status
housing_index
housing_document_count
official_index
official_document_count
```

Successful state:

```text
status = ok
housing_document_count > 0
official_document_count > 0
```

---

## 4.2 Dashboard Overview

```bash
curl "$API_BASE/api/analysis/dashboard/overview"
```

Purpose:

```text
summary of public discourse and official evidence
```

Frontend use:

```text
dashboard summary cards
official evidence overview
public-discourse overview
```

---

## 4.3 Sentiment APIs

### Overall sentiment

```bash
curl "$API_BASE/api/analysis/housing/sentiment-summary"
```

Returns:

```text
average_sentiment
sentiment_stats
buckets by sentiment_label
```

Frontend use:

```text
Overall Sentiment Distribution
```

---

### Sentiment by platform

```bash
curl "$API_BASE/api/analysis/housing/sentiment-by-platform"
```

Returns:

```text
platform
count
average_sentiment
sentiment_labels
```

Frontend use:

```text
Platform Sentiment Comparison
```

Use `average_sentiment` for sentiment comparison, not `count`.

---

### Sentiment over time

```bash
curl "$API_BASE/api/analysis/housing/sentiment-over-time?interval=month"
```

Optional filters:

```text
platform
query_keyword
city_context
```

Frontend use:

```text
Sentiment Trend Over Time
```

Use `average_sentiment` for sentiment trend.

---

## 4.4 Topic and Keyword APIs

### Top query keywords

```bash
curl "$API_BASE/api/analysis/housing/top-query-keywords"
```

Returns:

```text
query_keyword
count
```

Frontend use:

```text
Keyword Distribution
Housing Topic Cloud
```

---

### Top subtopics

```bash
curl "$API_BASE/api/analysis/housing/top-subtopics"
```

Returns:

```text
subtopic
count
```

Frontend use:

```text
topic ranking
topic cloud
```

---

### Platform keywords

```bash
curl "$API_BASE/api/analysis/housing/platform-keywords"
```

Optional parameters:

```text
platform_size
keyword_size
keyword_field
```

---

## 4.5 Regional APIs

### Raw city context

```bash
curl "$API_BASE/api/analysis/housing/by-city-context"
```

Returns raw `city_context` distribution.

---

### Cleaned regional distribution

Recommended call:

```bash
curl "$API_BASE/api/analysis/housing/by-region-cleaned?source_size=2000&output_size=100"
```

Returns:

```text
region_label
region_type
region_city
region_state
count
raw_examples
```

Frontend use:

```text
Top Mentioned Cities
State-level Regional Discussion Distribution
```

Important:

```text
Do not mix city and state labels in one chart.
Split region_type=city from state-level aggregation.
Regional counts are mention counts, not housing severity.
```

---

## 4.6 Official Analysis APIs

### Period coverage by source group

```bash
curl "$API_BASE/api/analysis/official/period-by-source-group"
```

Optional parameters:

```text
size
period_size
```

---

## 4.7 Comparison API

If enabled in `analysis_routes.py`:

```bash
curl "$API_BASE/api/analysis/compare/discourse-vs-official"
```

Optional parameters:

```text
interval
topic_size
region_size
source_size
period_size
```

Returns:

```text
public_discourse
official_evidence
```

Frontend use:

```text
public discourse vs official evidence comparison
integrated dashboard summary
```

---

## 4.8 Word Cloud / Topic Cloud

If backend word-cloud endpoint is enabled:

```bash
curl "$API_BASE/api/analysis/housing/word-cloud?source_size=5000&word_size=120"
```

Optional filters:

```text
platform
query_keyword
subtopic
city_context
```

Current frontend can also build a cleaner topic cloud directly from:

```text
/api/analysis/housing/top-query-keywords
/api/analysis/housing/top-subtopics
```

This is recommended for presentation because raw text word clouds often contain noisy generic words.

---

## 5. Full API Validation Script

```bash
python - <<'PY'
import requests

API_BASE = "http://localhost:9093"

endpoints = [
    "/api/health",
    "/api/analysis/health",
    "/api/housing/volume-by-platform",
    "/api/analysis/housing/sentiment-summary",
    "/api/analysis/housing/sentiment-by-platform",
    "/api/analysis/housing/sentiment-over-time?interval=month",
    "/api/analysis/housing/top-query-keywords",
    "/api/analysis/housing/top-subtopics",
    "/api/analysis/housing/by-region-cleaned",
    "/api/official/overview",
]

for endpoint in endpoints:
    print("
GET", endpoint)
    r = requests.get(API_BASE + endpoint, timeout=60)
    print("status:", r.status_code)

    if r.status_code != 200:
        print(r.text[:500])
        continue

    data = r.json()
    print("keys:", list(data.keys())[:10])

    if endpoint == "/api/analysis/health":
        print("housing:", data.get("housing_document_count"))
        print("official:", data.get("official_document_count"))
PY
```

---

## 6. Response Interpretation Notes

```text
count
= number of indexed records or aggregation bucket count

average_sentiment
= average NLP sentiment score

sentiment_label
= positive / neutral / negative

query_keyword
= collection or analysis keyword

subtopic
= inferred housing topic category

region_label
= cleaned region display label

region_type
= country / state / city / other

source_group
= official data source family
```

Important interpretation:

```text
Official overview shows data coverage, not housing severity.
Regional distribution shows mention volume, not actual regional housing pressure.
Sentiment is a baseline signal, not a full public opinion model.
Topic cloud is a cleaned display of keywords/subtopics, not a full linguistic model.
```

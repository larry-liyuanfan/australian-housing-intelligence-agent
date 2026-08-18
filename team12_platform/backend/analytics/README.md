# COMP90024 Team 12
# Public attribution: COMP90024 Team 12; member identities removed from this portfolio copy.

# API README

This document explains what each API file does and how the frontend should call it after cloud deployment.

Replace `API_BASE` with the deployed backend URL.

If using Kubernetes port-forward:

```bash
kubectl port-forward -n comp90024 svc/housing-backend-api 8080:80
```

then:

```python
API_BASE = "http://localhost:8080"
```

---

## 1. `app.py`

Location:

```text
backend/api/app.py
```

Purpose:

This is the unified backend entry point. It combines:

```text
housing_routes.py
official_routes.py
analysis_routes.py
```

into one Flask service.

Main routes:

```text
/api/health
/api/housing/...
/api/official/...
/api/analysis/...
```

How to call:

```bash
curl "$API_BASE/api/health"
curl "$API_BASE/api/official/health"
curl "$API_BASE/api/analysis/health"
```

---

## 2. `housing_routes.py`

Location:

```text
backend/api/housing_routes.py
```

Index used:

```text
housing_posts
```

Data type:

```text
Public discourse data:
GDELT / YouTube / BlueSky / Mastodon
```

What it supports:

```text
public discussion search
platform volume
time-series trend
housing keyword access
```

Main routes:

```text
GET /api/health
GET /api/housing/search
GET /api/housing/volume-by-platform
GET /api/housing/timeseries
GET /api/housing/top-query-keywords
```

How to call:

```bash
curl "$API_BASE/api/housing/volume-by-platform"
curl "$API_BASE/api/housing/timeseries?interval=month"
curl "$API_BASE/api/housing/search?q=rental%20crisis&size=5"
curl "$API_BASE/api/housing/top-query-keywords"
```

Frontend use:

```text
platform volume chart
public discussion trend chart
keyword ranking chart
public-discourse search table
```

---

## 3. `official_routes.py`

Location:

```text
backend/api/official_routes.py
```

Index used:

```text
official_housing_rows
```

Data type:

```text
Official housing evidence:
rental bond / census / median rent / housing stress / other official rows
```

What it supports:

```text
official source distribution
state coverage
period coverage
official evidence search
```

Main routes:

```text
GET /api/official/health
GET /api/official/overview
GET /api/official/source-groups
GET /api/official/row-types
GET /api/official/by-state
GET /api/official/by-period
GET /api/official/search
```

How to call:

```bash
curl "$API_BASE/api/official/overview"
curl "$API_BASE/api/official/source-groups"
curl "$API_BASE/api/official/by-state"
curl "$API_BASE/api/official/by-period"
curl "$API_BASE/api/official/search?q=Aberfoyle%20Park%20median%20rent&source_group=sa_private_rent_report&state=SA&row_type=data&size=5"
```

Frontend use:

```text
official source chart
state coverage chart
period coverage chart
official evidence table
```

---

## 4. `analysis_routes.py`

Location:

```text
backend/api/analysis_routes.py
```

Indexes used:

```text
housing_posts
official_housing_rows
```

Data type:

```text
Frontend-ready analytical outputs
```

What it supports:

```text
dashboard overview
sentiment analysis
regional analysis
topic analysis
platform-topic comparison
official time coverage
```

Main routes:

```text
GET /api/analysis/health
GET /api/analysis/dashboard/overview
GET /api/analysis/housing/sentiment-summary
GET /api/analysis/housing/sentiment-by-platform
GET /api/analysis/housing/sentiment-over-time
GET /api/analysis/housing/by-city-context
GET /api/analysis/housing/top-query-keywords
GET /api/analysis/housing/platform-keywords
GET /api/analysis/official/period-by-source-group
```

How to call:

```bash
curl "$API_BASE/api/analysis/dashboard/overview"
curl "$API_BASE/api/analysis/housing/sentiment-summary"
curl "$API_BASE/api/analysis/housing/sentiment-by-platform"
curl "$API_BASE/api/analysis/housing/sentiment-over-time?interval=month"
curl "$API_BASE/api/analysis/housing/by-city-context"
curl "$API_BASE/api/analysis/housing/top-query-keywords"
curl "$API_BASE/api/analysis/housing/platform-keywords"
curl "$API_BASE/api/analysis/official/period-by-source-group"
```

Frontend use:

```text
dashboard summary
sentiment chart
platform sentiment comparison
sentiment trend chart
regional discussion chart
topic ranking chart
platform-topic comparison chart
official time coverage chart
```

---

## 5. Quick Mapping

| Analysis | API file | Endpoint |
|---|---|---|
| Backend health | `app.py` / `housing_routes.py` | `/api/health` |
| Official health | `official_routes.py` | `/api/official/health` |
| Full analysis health | `analysis_routes.py` | `/api/analysis/health` |
| Platform volume | `housing_routes.py` | `/api/housing/volume-by-platform` |
| Public time trend | `housing_routes.py` | `/api/housing/timeseries` |
| Public search | `housing_routes.py` | `/api/housing/search` |
| Official sources | `official_routes.py` | `/api/official/source-groups` |
| Official states | `official_routes.py` | `/api/official/by-state` |
| Official periods | `official_routes.py` | `/api/official/by-period` |
| Official search | `official_routes.py` | `/api/official/search` |
| Dashboard overview | `analysis_routes.py` | `/api/analysis/dashboard/overview` |
| Sentiment summary | `analysis_routes.py` | `/api/analysis/housing/sentiment-summary` |
| Sentiment by platform | `analysis_routes.py` | `/api/analysis/housing/sentiment-by-platform` |
| Regional discussion | `analysis_routes.py` | `/api/analysis/housing/by-city-context` |
| Keyword ranking | `analysis_routes.py` | `/api/analysis/housing/top-query-keywords` |
| Official time coverage | `analysis_routes.py` | `/api/analysis/official/period-by-source-group` |

---

## 6. Jupyter Example

```python
import requests
import pandas as pd

API_BASE = "http://localhost:8080"

overview = requests.get(
    f"{API_BASE}/api/analysis/dashboard/overview"
).json()

keywords = requests.get(
    f"{API_BASE}/api/analysis/housing/top-query-keywords"
).json()

keyword_df = pd.DataFrame(keywords["buckets"])
keyword_df.head()
```

Official evidence search:

```python
params = {
    "q": "Aberfoyle Park median rent",
    "source_group": "sa_private_rent_report",
    "state": "SA",
    "row_type": "data",
    "size": 5
}

results = requests.get(
    f"{API_BASE}/api/official/search",
    params=params
).json()

official_df = pd.DataFrame(results["results"])
official_df.head()
```

---

## 7. Recommended Frontend Order

```text
1. /api/analysis/health
2. /api/analysis/dashboard/overview
3. /api/housing/volume-by-platform
4. /api/analysis/housing/top-query-keywords
5. /api/analysis/housing/by-city-context
6. /api/analysis/housing/sentiment-summary
7. /api/official/source-groups
8. /api/official/by-state
9. /api/analysis/official/period-by-source-group
10. /api/housing/search or /api/official/search
```

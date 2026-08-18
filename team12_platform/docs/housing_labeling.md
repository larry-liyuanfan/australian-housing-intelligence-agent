# Housing Relevance Labeling — Cross-Platform Logic

How the `housing_relevant` boolean field is determined for each platform.

---

## 1. The Labeling Function

All platforms share the same function in `normalise_housing.py`:

```python
def is_housing_relevant(query_keyword: str = '', text: str = '', title: str = '') -> bool:
    combined = f'{query_keyword} {title} {text}'.lower()
    for kw in HOUSING_KEYWORDS:
        if ' ' in kw:                    # multi-word phrase → substring match
            if kw in combined:
                return True
        else:                            # single word → \b word boundary regex
            if re.search(r'\b' + re.escape(kw) + r'\b', combined):
                return True
    return False
```

86 housing keywords covering: rent/rental, tenant/landlord, eviction, mortgage, homelessness, affordability, bond, share house, housing supply, VCAT/NCAT, NRAS, negative gearing, stamp duty, NIMBY/YIMBY, etc.

Single words use `\b` word-boundary matching to avoid false positives (e.g. `bond` won't match "Bondi").

---

## 2. Per-Platform Strategy

### 2.1 BlueSky

| Aspect | Detail |
|--------|--------|
| **Data source** | `bluesky_au_v2.jsonl` — 122 broad AU queries (city names, media outlets, generic AU terms) |
| **AU filter** | `_AU_CITY_STATE_PATTERN`, `_AU_JARGON_PATTERN`, `_AU_EMOJI_PATTERN` regex post-filter on post text + author bio + handle |
| **Housing filter** | `is_housing_relevant(query_keyword, text)` at normalisation time |
| **Result** | ~4.7% of 756K records = ~36K housing relevant |
| **Fission harvest** | Always `housing_relevant: True` (uses housing-specific search queries) |

**Why only 4.7%?** The broad AU crawl was designed to maximise volume for big-data demonstration. Queries like "Sydney", "Newcastle", "The Age" capture Australian online discourse broadly. The `housing_relevant` flag allows filtering to housing-specific content at query time.

**ES query to filter:**
```json
{"query": {"bool": {"must": [
  {"term": {"platform": "bluesky"}},
  {"term": {"housing_relevant": true}}
]}}}
```

### 2.2 Mastodon

| Aspect | Detail |
|--------|--------|
| **Data source** | `mastodon_au_all.jsonl` — AU instance public timelines + global instances with AU hashtag filter |
| **AU filter** | AU instances (aus.social, mastodon.au, melb.social) trusted implicitly; global instances filtered by `_contains_region_token()` on post content + tags |
| **Housing filter** | `is_housing_relevant(query_keyword, text)` at normalisation time |
| **Result** | ~9.4% of 238K records = ~22K housing relevant |
| **Fission harvest** | Always `housing_relevant: True` (uses housing hashtags) |

**Why 9.4%?** AU instances' public timelines contain all topics. The housing hashtag timeline on global instances has better precision but Mastodon's hashtag culture means some posts use housing tags tangentially.

### 2.3 GDELT GKG

| Aspect | Detail |
|--------|--------|
| **Data source** | `gdelt_yearly/*/medium/gkg_medium.jsonl` — 5 years of GKG data |
| **Pre-filter** | GDELT GKG themes: `HOUSING`, `HOUSING_PRICES`, `HOUSING_AFFORDABILITY`, `EVICTION`, `HOMELESSNESS`, `RENTAL`, `WB_2671_HOUSING_AND_CONSTRUCTION`, `ENV_NATURALRESOURCES_HOUSING` |
| **Housing filter** | `is_housing_relevant(query_keyword, text)` at normalisation time |
| **Result** | ~100% of 624K records = housing relevant (pre-filtered by GKG themes) |

**Does GDELT need labeling?** The GKG medium tier is already pre-filtered to housing themes. Our `is_housing_relevant()` function confirms this — 100% of medium-tier records pass the housing keyword check. The GKG theme filter is the first line of defense; the `housing_relevant` field provides a second validation layer.

**Key insight:** GDELT themes are broad categories. `HOUSING` includes related infrastructure, `RENTAL` includes commercial leasing. The `is_housing_relevant()` function's 86 keywords catch this nuance better than the GKG theme filter alone — but in practice, the overlap is near-total for Australian data.

### 2.4 YouTube

| Aspect | Detail |
|--------|--------|
| **Data source** | `youtube_master.jsonl` — 196 housing-specific Tier 1/2/3 search queries |
| **Pre-filter** | `regionCode=AU` + `relevanceLanguage=en` + strict snippet filter (`_HOUSING_RE` + `_AU_RE`) which removes musical-RENT and non-housing noise |
| **Housing filter** | `is_housing_relevant(query_keyword, text, title)` at normalisation time |
| **Result** | 99.1% of 3,829 videos = housing relevant |

**YouTube effectively doesn't need labeling** because every search query is housing-specific. The snippet filter catches the few false positives (musical "RENT"). The `housing_relevant` flag on YouTube is present for schema consistency.

---

## 3. Cross-Platform Summary

| Platform | Records | housing_relevant=True | Method |
|----------|---------|----------------------|--------|
| BlueSky | 754,887 | ~4.7% (broad crawl) / 100% (Fission harvest) | Query keyword + text keyword match |
| Mastodon | 232,145 | ~9.4% (broad crawl) / 100% (Fission harvest) | Hashtag + content keyword match |
| GDELT GKG | 623,992 | ~100% | Pre-filtered by GKG themes + keyword validation |
| YouTube | 3,829 | 99.1% | Housing-specific queries + snippet filter |

## 4. Usage in ES Queries

```json
// Get only housing-relevant discourse
GET /housing_posts/_search
{
  "query": {
    "bool": {
      "must": [
        {"term": {"housing_relevant": true}},
        {"term": {"platform": "bluesky"}}
      ]
    }
  }
}

// Dashboard: housing vs non-housing breakdown
GET /housing_posts/_search
{
  "size": 0,
  "aggs": {
    "housing_breakdown": {
      "terms": {"field": "housing_relevant"}
    }
  }
}
```

The `housing_relevant` field is a **normalisation-time flag**, not a query-time filter. This means keyword matching happens once during ingestion, and ES queries use a cheap boolean term filter — no expensive full-text scan needed.

---

## 5. Keyword List

```text
rent, rental, rented, renter, renting, tenant, tenants, tenancy,
landlord, landlords, lease, leasing, bond, bonds,
housing, homeless, homelessness, apartment, apartments, flat, flats,
mortgage, mortgages, property,
eviction, evicted, evict, foreclosure,
affordability, affordable, unaffordable,
accommodation, shelter, lodging, boarding,
negative gearing, stamp duty, first home, public housing,
social housing, community housing, housing crisis, rental crisis,
rent increase, rent freeze, rent cap, rent control,
rental stress, housing stress, mortgage stress, cost of living,
share house, flatmate, roommate, sublet, boarding house,
property manager, real estate, rental bond, bond cleaning,
no grounds, sleeping rough, tent city, couch surfing,
housing supply, housing shortage, housing target,
build to rent, housing insecurity, housing waitlist,
rent arrears, rental application, routine inspection,
vcat, ncat, qcat, sacat,
nras, fhogg, commonwealth rent assistance, rent assistance,
rental reform, tenant rights, renters rights,
nimby, yimby, urban sprawl, zoning,
renoviction, slumlord
```

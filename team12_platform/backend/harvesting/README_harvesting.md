# Data Harvesting and Normalisation Module

This folder contains harvesting-side utilities used to inspect and normalise raw
online housing-discussion data before it is passed into the backend analytics
and Elasticsearch ingestion pipeline.

## Supported Sources

The current harvesting and normalisation utilities cover four online data
sources:

- BlueSky posts
- Mastodon statuses
- GDELT document/article records
- YouTube video metadata and comment material

Official datasets are handled separately by the official-data pipeline and are
stored in the `official_housing_rows` Elasticsearch index. They are used as
comparative context rather than being forced into the same social-post schema.

## Main Scripts

### `src/inspect_jsonl.py`

Inspects a JSONL file and reports the number of records, top-level fields, and a
preview of the first record.

```bash
python3 backend/harvesting/src/inspect_jsonl.py <input_jsonl>
```

### `src/inspect_youtube.py`

Checks the structure of YouTube harvest files before normalisation.

```bash
python3 backend/harvesting/src/inspect_youtube.py <youtube_jsonl>
```

### `src/normalise.py`

Converts supported source files into the shared `housing_posts` schema used by
the analytics and ingestion modules.

```bash
python3 backend/harvesting/src/normalise.py \
  --input <raw_jsonl> \
  --output data/processed/normalised_housing_posts.jsonl
```

## Notes

- Keep raw API keys, tokens, OpenRC files, and kubeconfig files out of Git.
- Keep large local harvesting dumps outside this folder unless they are part of
  the final documented submission dataset.
- Use `sample_raw_posts.json` only as a small schema example for review and
  smoke testing.

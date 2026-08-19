# Evidence and fact boundary

## Source provenance

- Original baseline: private COMP90024 Team 12 GitLab repository referenced by the final course report.
- Local review source: the archived Team 12 repository and course report supplied by the user.
- Public extension: only files in this repository.

The original material was inspected to confirm mappings, Flask endpoints, Kubernetes/Fission configuration, separate `housing_posts`/`official_housing_rows` indexes, and team-level runtime records. A sanitized source snapshot is included under `team12_platform/`; identities, raw/normalized records, notebook outputs, command screenshots, credentials, and report PDF were excluded. The original source has no confirmed open-source license.

## Claim status

| Claim | Status | Evidence |
|---|---|---|
| Six typed tools reject extra fields/raw DSL | implemented | Pydantic schemas, registry tests |
| Explicit plan/execute/verify/synthesize trace | implemented | state-machine and API tests |
| Local BM25 + hashed dense + RRF + rerank | implemented | retrieval code/tests |
| Error/timeout/empty-result recovery | implemented | fault injection tests/eval |
| 100 deterministic eval tasks | implemented | generator plus output artifacts when run |
| Elasticsearch/Redis/Prometheus deployment | verified SG fixture infrastructure | Health, separate index counts, commit `52c6c74` |
| 200-request concurrency-10 run: 470.1 QPS, P95 42.30 ms | verified fixture benchmark | Run artifact SHA-256 `8fc947...c834` |
| Redis warm replay reduced HTTP P50 82.8% and tool P50 96.3% | verified fixture benchmark | 13 unique cold/warm queries; same artifact |
| Model Studio Function Calling | adapter-only until credentialed run | environment-only client/planner |
| Real task-success/latency/cost | unverified until live run | must add run manifest and raw predictions |
| Original data volumes/cloud scale | team project record only | original course report; not personal extension result |

## Required live-run manifest

Before any resume claim based on a live run, record:

- Git commit and dirty/clean state;
- timestamp and runner/host;
- data version, index counts and data hashes;
- model names and endpoint region;
- evaluation task hash and human-review protocol;
- task/tool/citation metrics with raw predictions;
- P50/P95, concurrency, cache state, API token use and cost;
- failure cases and limitations.

Local synthetic evaluation can prove contract correctness; it cannot validate answer relevance on the original corpus.

The SG benchmark proves deployment, controlled Elasticsearch templates, Redis
cache behavior and bounded online latency only. Its 14 documents are explicit
deidentified fixtures. The Model Studio runtime variables are empty, so provider
tool-selection quality, provider token use and API cost remain unverified.

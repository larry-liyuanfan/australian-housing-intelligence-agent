# Australian Housing Intelligence Agent

An evidence-grounded Agentic Search system for questions about Australian housing discussion signals and official context. It demonstrates typed tool calling, controlled hybrid retrieval, explicit orchestration, failure recovery, traceability, evaluation, and a resource-bounded cloud deployment.

> Portfolio status: the FastAPI/Agent/Eval code is a new personal extension. `team12_platform/` is a sanitized snapshot of the 2026 COMP90024 Team 12 baseline. Public fixtures are synthetic/deidentified; they are not evidence of population prevalence or production performance.

## Why this project exists

The original team system collected and normalized public discussion and official housing data, indexed the two evidence types separately in Elasticsearch, exposed REST analytics, and deployed course workloads with Kubernetes/Fission. This extension asks a harder engineering question:

**Can a language-model planner answer housing questions only through typed, auditable tools, preserve the distinction between discussion and official evidence, and recover safely from invalid arguments, empty results, timeouts, and backend errors?**

It supports the broader portfolio focus: **Multimodal Search, RAG and Agentic AI Applications**. Trip remains the flagship multimodal project; this repository supplies the Agentic Search, evaluation, online-serving, and observability evidence.

## Architecture

```text
Question
  -> canonicalize region/time
  -> deterministic planner or Model Studio Function Calling
  -> Pydantic allowlist (no arbitrary Elasticsearch DSL)
  -> typed tools
       search_discussion        search_official_evidence
       aggregate_topic          compare_region_period
       get_sentiment_trend      explain_data_coverage
  -> BM25 + dense adapter + RRF + rerank fallback
  -> evidence verification and citation synthesis
  -> trace, latency, cost and Prometheus metrics
```

The local backend implements dependency-free BM25, hashed dense retrieval, reciprocal-rank fusion and deterministic feature reranking. It makes tests and evaluation reproducible without an external model. Elasticsearch, Redis, and Alibaba Cloud Model Studio are environment-configured adapters; provider failure falls back safely and no credential is stored in the repository.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate              # Windows: .venv\Scripts\activate
python -m pip install -e ".[test]"
pytest
housing-agent serve --port 8080
```

Query and inspect its trace:

```bash
curl -s http://localhost:8080/api/agent/query \
  -H 'content-type: application/json' \
  -d '{"question":"Compare rental stress evidence in Victoria versus New South Wales."}'

curl -s http://localhost:8080/api/agent/traces/TRACE_ID
curl -s http://localhost:8080/metrics
```

Main contracts:

- `POST /api/agent/query` returns status, answer, citations, tool records, data version, trace ID and provider-cost fields.
- `GET /api/agent/traces/{trace_id}` returns state transitions and validated tool arguments.
- `GET /metrics` exposes request/tool counters and P50/P95 process-local latency gauges.
- `GET /api/tools` exposes the exact Function Calling JSON schemas and confirms that raw DSL is disabled.

## Evaluation

The deterministic generator creates exactly 100 tasks:

| Category | Count | Purpose |
|---|---:|---|
| Direct retrieval | 30 | Discussion plus official evidence |
| Multi-hop comparison | 25 | Region comparison |
| Normalization | 15 | City-to-state canonicalization |
| Clarification | 15 | Underspecified questions |
| Failure recovery | 15 | Injected error, empty result, timeout |

Run the three-way comparison:

```bash
housing-agent evaluate --output artifacts/eval
```

It evaluates `direct_no_tools`, `single_tool`, and `state_machine`, and writes `tasks.jsonl`, `predictions.jsonl`, and `metrics.json`. The fixtures validate contracts and orchestration; they do **not** establish real-world answer quality. Real Elasticsearch/Model Studio claims require a separately recorded run manifest and human-labeled evaluation.

Verified local synthetic run (Windows/Python 3.13, 2026-08-18):

| Variant | Task success | Logical tool success | Physical-attempt success | Failure recovery |
|---|---:|---:|---:|---:|
| No tools | 15% | n/a | n/a | 0% |
| Single tool | 40% | 88.2% | 88.2% | 0% |
| Full state machine | 100% | 100% | 94.0% | 100% |

The state-machine score is a contract/golden-fixture result, not a relevance or production-quality claim. Injected first-attempt failures deliberately reduce physical-attempt success; all of them recovered within the configured budget. See `artifacts/eval/run_manifest.json`, raw predictions and the generated report for provenance.

## Model Studio and Elasticsearch

Copy `.env.example` to a private `.env`. Set `MODEL_STUDIO_BASE_URL` to the Singapore OpenAI-compatible endpoint and provide `MODEL_STUDIO_API_KEY` only in the runtime environment. Set `use_model=true` per request to enable Function Calling; local deterministic planning remains the fallback.

For Elasticsearch, use `HOUSING_BACKEND=elasticsearch`. Queries are compiled from typed filters into fixed templates. Discussion and official corpora use separate indexes. The mappings under `deploy/elasticsearch/` reserve a 1,024-dimensional vector field for offline embeddings; bulk embeddings and private data stay outside Git.

## Aliyun SG deployment

`compose.yaml` uses an isolated `housing_agent_sg` project, network and volumes. Default host ports are 8090 (API) and 9091 (Prometheus), avoiding the existing Trip service. Limits are intentionally conservative for a 4-vCPU/7-GB host:

| Service | CPU | Memory |
|---|---:|---:|
| API | 1.00 | 768 MB |
| Elasticsearch | 1.25 | 1,536 MB (768 MB heap) |
| Redis | 0.25 | 256 MB |
| Prometheus | 0.25 | 256 MB |

```bash
docker compose config
docker compose up -d --build
```

Do not expose Elasticsearch or Redis publicly. The Compose file binds only API/Prometheus to loopback; place an authenticated TLS reverse proxy in front of the API if a public demo is required.

## Data, authorship and claims

- **Team baseline:** COMP90024 Team 12, University of Melbourne, Semester 1 2026. The sanitized code snapshot is under `team12_platform/`; the original GitLab repository and course materials remain the source of team-level cloud/data claims.
- **Personal extension:** the typed Agent, controlled retrieval adapters, state machine, evaluation harness, public deployment package, and evidence/decision documentation in this repository.
- **Not included:** team member identities, student IDs, credentials, identifiable raw/normalized social records, notebook outputs, command screenshots, kubeconfigs, the report PDF, or restricted datasets.
- **No causal claim:** online discussion records are public-discourse signals and must not be presented as housing-insecurity prevalence.
- **No production claim:** local fixture metrics and original team-scale records cannot be described as personal production impact.

No open-source license is granted yet because the extension was derived from a team project context. Confirm the publication/licensing boundary before adding one.

## Documentation

- [Architecture and failure modes](docs/architecture.md)
- [Decision record](docs/decisions.md)
- [Evidence and fact boundary](docs/evidence.md)
- [Privacy and publication checklist](docs/privacy.md)
- [Interview defense guide](docs/interview.md)
- [Team/project attribution boundary](TEAM_PROJECT_ATTRIBUTION.md)

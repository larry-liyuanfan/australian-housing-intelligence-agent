# Interview defense guide

## 90-second story

The Team 12 baseline separated Australian online housing discussion from official context in Elasticsearch and exposed cloud analytics. My extension turns that data layer into an auditable Agentic Search system. Instead of allowing a model to emit Elasticsearch JSON, I defined six strict Pydantic tools and an explicit state machine with call budgets, duplicate detection, timeout/error retry, empty-result recovery and evidence verification. Retrieval has a credential-free BM25/dense-surrogate/RRF/rerank baseline plus environment-only adapters for Elasticsearch and Model Studio. A deterministic 100-task harness compares no-tools, single-call and full-state-machine variants, while every API response exposes citations, data version, trace and cost fields. The public repository uses synthetic/deidentified fixtures, so I distinguish contract metrics from live relevance claims.

## Deep-dive questions

1. Why are online discussion and official records separate corpora?
2. Why is a typed state machine safer than free-form ReAct?
3. How does Pydantic prevent arbitrary Elasticsearch DSL?
4. What does reciprocal-rank fusion solve?
5. Why is the local hash vector not called a semantic embedding?
6. How would `text-embedding-v4` be indexed and versioned?
7. How do you avoid comparing incompatible BM25 and dense scores?
8. Why rerank only a small fused candidate set?
9. How are duplicate tool loops detected?
10. What counts against the four-call budget?
11. How does timeout retry avoid duplicate side effects?
12. Why are these tools read-only and idempotent?
13. What happens when filtered retrieval is empty?
14. What is citation completeness, and what does it miss?
15. How were the 100 tasks generated and stratified?
16. Why can synthetic task success not enter the resume as production accuracy?
17. How would you create a human-reviewed gold set?
18. What traces are process-local today, and what would production require?
19. How do Redis keys include data/index version?
20. How does Compose avoid affecting the Trip deployment?

## Code evidence map

| Question area | Code or artifact to open |
|---|---|
| Tool schemas and argument rejection | `src/housing_agent/schemas.py`, `src/housing_agent/tools.py` |
| Explicit states, budgets, retries and loop detection | `src/housing_agent/agent.py`, `src/housing_agent/planning.py` |
| BM25, hash-vector surrogate, RRF and rerank | `src/housing_agent/retrieval.py` |
| Elasticsearch allowlisted query construction | `src/housing_agent/corpus.py` |
| Model Studio adapters and deterministic fallback | `src/housing_agent/modelstudio.py` |
| Citation verification and insufficient-evidence behavior | `src/housing_agent/agent.py` |
| Trace, metrics and cache versioning | `src/housing_agent/traces.py`, `src/housing_agent/observability.py`, `src/housing_agent/cache.py` |
| Query/trace/metrics HTTP contracts | `src/housing_agent/api.py` |
| 100-task ablation definitions and scoring | `src/housing_agent/evaluation.py`, `artifacts/eval/run_manifest.json` |
| Synthetic/public-data boundary and team attribution | `README.md`, `TEAM_PROJECT_ATTRIBUTION.md`, `docs/evidence.md` |
| Cloud isolation and resource caps | `compose.yaml`, `.env.example`, `docs/deployment.md` |
| Executable regression evidence | `tests/`, `.github/workflows/ci.yml` |

# Error Handling And Limitations

This document records the reliability and limitation notes that support the
final report and demo. It is kept as a concise reference document for the final
repository.

## Data Collection Risks

| Risk | Handling in the system | Submission evidence |
|------|------------------------|---------------------|
| API rate limits or temporary source failures | Harvesters are designed to run in batches and can be rerun from saved source files or scheduled jobs. | Harvesting code, Fission timer evidence, and runtime screenshots. |
| Duplicate posts across repeated harvesting runs | Normalisation generates stable `doc_id` values, and Elasticsearch indexing uses document IDs to make reruns safer. | Normalisation code and ingestion scripts. |
| Irrelevant posts after broad collection | Housing keyword rules and relevance filtering reduce unrelated records while preserving source metadata for review. | `docs/housing_labeling.md` and normalisation code. |
| Missing or weak location metadata | Region fields are treated as approximate signals and cleaned with documented city/state heuristics. | Regional analysis section in `docs/final_report.md`. |

## Normalisation And Ingestion Risks

| Risk | Handling in the system | Submission evidence |
|------|------------------------|---------------------|
| Different source schemas | BlueSky, Mastodon, GDELT, and YouTube records are converted into the shared `housing_posts` schema. | `backend/analytics/normalisation/` and harvesting samples. |
| Elasticsearch bulk failures | Bulk ingestion reports failed records and can be rerun after mapping or data fixes. | `backend/analytics/ingestion/` scripts. |
| Mapping mismatch | Index mappings are stored in the repository and used during index creation. | `backend/mappings/` and `database/`. |

## Runtime Service Risks

| Risk | Handling in the system | Submission evidence |
|------|------------------------|---------------------|
| Elasticsearch unavailable from API or Fission | API health routes and Fission functions return clear error responses rather than silently failing. | Backend routes and Fission function code. |
| Fission function or timer missing | Demo verification uses `fission function list` and `fission timer list`. | `docs/runtime_evidence.md`. |
| Kubernetes pod or image failure | Deployment status can be checked with `kubectl get pods -A` and relevant pod logs. | Kubernetes runtime screenshots and deployment manifests. |

## Analytics Limitations

- Sentiment labels are approximate signals rather than ground truth.
- Keyword and topic outputs depend on the selected housing vocabulary.
- Official datasets are used as comparative context and do not share the same
  sampling frame as online discussion data.
- Online discussion volume is affected by platform activity, API availability,
  and collection rules, so it should not be interpreted as population-level
  prevalence.

## Report Summary

The system handles operational failures mainly through repeatable ingestion,
stable document identifiers, documented filtering rules, health-check endpoints,
and runtime verification commands. The main residual limitations are source
bias, incomplete location metadata, approximate sentiment/topic labels, and the
difference between official data definitions and online discussion language.

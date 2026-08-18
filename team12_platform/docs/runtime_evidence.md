# Runtime Evidence Summary

> Public-copy note: the referenced command screenshots are intentionally excluded. This file preserves the original verification checklist but is not itself proof of a current deployment.

**Source material:** teammate-supplied command screenshot document
**Extracted on:** 2026-05-18
**Image folder:** `docs/evidence/screenshots/`

This file records the runtime command evidence added during final integration.
The extracted screenshots are stored as numbered PNG files so the report/demo can
refer to them without committing the original Word document.

## 1. Kubernetes Cluster And Workloads

Commands captured:

```bash
kubectl get nodes -o wide
kubectl get pods -A
kubectl get pvc -A
kubectl get svc -A
kubectl get hpa -A
```

Purpose:

- prove the `comp90024` cluster is reachable;
- show cluster workloads across namespaces;
- show persistent volumes, services and HPA configuration.

Relevant screenshots:

- `docs/evidence/screenshots/command_screenshot_01.png`
- `docs/evidence/screenshots/command_screenshot_02.png`
- `docs/evidence/screenshots/command_screenshot_03.png`
- `docs/evidence/screenshots/command_screenshot_04.png`

## 2. Elasticsearch Health, Indices And Counts

Commands captured:

```bash
kubectl port-forward service/elasticsearch-es-http -n elastic 9200:9200
curl -k 'https://127.0.0.1:9200/_cluster/health' --user elastic:elastic
curl -k 'https://127.0.0.1:9200/_cat/indices/housing_posts,official_housing_rows,harvester_state,harvester_errors,dashboard_cache?v&s=index' --user elastic:elastic
curl -k 'https://127.0.0.1:9200/housing_posts/_count' --user elastic:elastic
curl -k 'https://127.0.0.1:9200/official_housing_rows/_count' --user elastic:elastic
```

Purpose:

- prove Elasticsearch is accessible through port-forwarding;
- show cluster health;
- show required indices;
- confirm online-discussion and official-data document counts.

Relevant screenshots:

- `docs/evidence/screenshots/command_screenshot_05.png`
- `docs/evidence/screenshots/command_screenshot_06.png`
- `docs/evidence/screenshots/command_screenshot_07.png`

## 3. Fission Functions And Timers

Commands captured:

```bash
fission function list
fission timer list
```

Purpose:

- prove Fission is installed and reachable;
- show the functions and timers used for the serverless part of the system.

Relevant screenshots:

- `docs/evidence/screenshots/command_screenshot_08.png`
- `docs/evidence/screenshots/command_screenshot_09.png`

## 4. Platform Freshness And Counts

Commands captured:

```bash
for plat in bluesky mastodon gdelt_doc youtube; do
  curl -sk 'https://127.0.0.1:9200/housing_posts/_search?size=1&sort=collected_at:desc' \
    --user elastic:elastic \
    -H 'Content-Type: application/json' \
    -d "{\"query\":{\"term\":{\"platform\":\"$plat\"}}}"
done

for plat in bluesky mastodon gdelt_doc youtube; do
  curl -sk 'https://127.0.0.1:9200/housing_posts/_count' \
    --user elastic:elastic \
    -H 'Content-Type: application/json' \
    -d "{\"query\":{\"term\":{\"platform\":\"$plat\"}}}"
done
```

Purpose:

- show each platform has indexed records;
- show latest collection examples where available;
- support the platform distribution used in the final report.

Relevant screenshots:

- `docs/evidence/screenshots/command_screenshot_10.png`
- `docs/evidence/screenshots/command_screenshot_11.png`

## 5. YouTube Pipeline

Commands captured:

```bash
kubectl get cronjob -A
kubectl get jobs -n comp90024 | grep youtube
curl -sk 'https://127.0.0.1:9200/dashboard_cache/_doc/youtube' --user elastic:elastic
kubectl get cronjob youtube-harvest -n comp90024 -o yaml | grep -E "search-max|published-after|quota|save-every" | head -6
```

Purpose:

- show YouTube harvest and ingest scheduling;
- show dashboard cache values such as videos, comments and discussion units;
- document the harvest search/quota strategy.

Relevant screenshots:

- `docs/evidence/screenshots/command_screenshot_12.png`
- `docs/evidence/screenshots/command_screenshot_13.png`
- `docs/evidence/screenshots/command_screenshot_14.png`

## 6. GDELT Pipeline

Commands captured:

```bash
kubectl logs deploy/gdelt-gkg-harvest -n comp90024 --tail=15
curl -sk 'https://127.0.0.1:9200/harvester_state/_doc/gdelt_gkg' --user elastic:elastic
```

Purpose:

- show the GDELT deployment is running;
- show checkpoint/state evidence for incremental operation.

Relevant screenshots:

- `docs/evidence/screenshots/command_screenshot_15.png`
- `docs/evidence/screenshots/command_screenshot_16.png`

## 7. Harvester State And Error Logs

Commands captured:

```bash
curl -sk 'https://127.0.0.1:9200/harvester_state/_search?size=5' --user elastic:elastic
curl -sk 'https://127.0.0.1:9200/harvester_errors/_search?size=5&sort=time:desc' --user elastic:elastic
curl -sk 'https://127.0.0.1:9200/harvester_errors/_search?size=3' \
  --user elastic:elastic \
  -H 'Content-Type: application/json' \
  -d '{"query":{"term":{"error_type":"volume_anomaly"}}}'
```

Purpose:

- show crash recovery state;
- show operational error visibility;
- show volume anomaly monitoring where available.

Relevant screenshots:

- `docs/evidence/screenshots/command_screenshot_17.png`
- `docs/evidence/screenshots/command_screenshot_18.png`
- `docs/evidence/screenshots/command_screenshot_19.png`

## 8. Backend API, Dashboard Cache And Self-Healing Evidence

Commands captured:

```bash
kubectl exec -n comp90024 deploy/housing-backend -- python3 -c "<API smoke checks>"
curl -sk 'https://127.0.0.1:9200/dashboard_cache/_search?size=10' --user elastic:elastic
kubectl get pods -n comp90024 -o wide
kubectl get deploy -n comp90024
```

Purpose:

- show backend routes can be queried from inside the cluster;
- show precomputed dashboard cache entries;
- show deployments and pod distribution for resilience.

Relevant screenshots:

- `docs/evidence/screenshots/command_screenshot_20.png`
- `docs/evidence/screenshots/command_screenshot_21.png`
- `docs/evidence/screenshots/command_screenshot_22.png`

## 9. Redis / MQ / KEDA Runtime Checks

Commands captured:

```bash
kubectl get deploy,pod,svc -n redis
kubectl get messagequeuetrigger -n default
kubectl get hpa -A | grep keda
```

Purpose:

- record teammate-supplied runtime evidence for queue and event-driven scaling
  checks;
- keep these checks separate from repository manifest evidence, because not all
  cluster-side resources are represented as final source files in
  `backend/deployment/`.

Relevant screenshots:

- `docs/evidence/screenshots/command_screenshot_23.png`

## Notes

- The original Word document is not committed to avoid storing duplicate binary
  evidence in two formats.
- Screenshots are numbered in extraction order from the Word document.
- The final report remains the canonical interpretation of runtime evidence.

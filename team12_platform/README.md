# COMP90024 Team 12

> Sanitized public portfolio snapshot of the Team 12 course platform. Member identities, student identifiers, credentials, identifiable records, notebook outputs, command screenshots and the report PDF were removed. This directory is a **team-authored baseline**, not an individual-authorship claim. See [`../TEAM_PROJECT_ATTRIBUTION.md`](../TEAM_PROJECT_ATTRIBUTION.md).

**Topic:** How is housing insecurity discussed in Australian online communities?
**Course:** COMP90024 Cluster and Cloud Computing, University of Melbourne, 2026 Semester 1
**Team size:** 5 students
**Deadline:** 20 May 2026; demonstrations 21–22 May 2026

---

## i. User Guide

### Prerequisites

Access to the cluster requires a valid kubeconfig file (`config.12.yaml`). The notebook communicates with the backend API through a local port-forward:

```bash
export KUBECONFIG=/path/to/config.12.yaml
kubectl port-forward -n comp90024 svc/housing-backend-api 8080:80
```

This command must remain running while the notebook is in use.

### HTML Dashboard

To open the static HTML dashboard (`frontend/index_1.html`), serve it locally and keep the port-forward running:

```bash
kubectl port-forward -n comp90024 svc/housing-backend-api 8080:80 &
cd frontend && python3 -m http.server 8889
# open http://localhost:8889/index_1.html
```

### Notebook

Open `frontend/housing_api_dashboard.ipynb`. Run all cells from a clean kernel. The notebook retrieves all data from `http://localhost:8080`; no local data files are required.

The notebook generates the following visualisations: platform distribution, sentiment histograms, keyword frequency charts, daily post volume timelines, YouTube channel comparisons, and official data comparisons.

### API Endpoints

```
GET  /api/cache/all                 all dashboard panels in one response
GET  /api/housing/search?q=&size=   full-text search across housing_posts
GET  /api/housing/volume-by-platform post counts grouped by platform
GET  /api/health                    backend health check
```

All responses include the header `Access-Control-Allow-Origin: *` to permit cross-origin requests from the notebook.

---

## ii. Deployment

The system requires two categories of components: infrastructure provided by the course, and application workloads deployed from this repository.

### Part A: Course-Provided Infrastructure

The following manifests are taken from the course public repository ([`feit-comp90024/comp90024`](https://gitlab.unimelb.edu.au/feit-comp90024/comp90024)) and are not maintained in this repository:

| Path | Purpose |
|------|---------|
| `installation/elasticsearch.yaml` | ECK Elasticsearch cluster (2 data nodes) |
| `installation/kibana.yaml` | Kibana deployment |
| `installation/storage-class.yaml` | Cinder SSD StorageClass (`perfretain`) |

These must be applied before any team-specific workloads:

```bash
kubectl create ns elastic
kubectl apply -f installation/storage-class.yaml
kubectl apply -f installation/elasticsearch.yaml
kubectl apply -f installation/kibana.yaml
```

### Part B: Team-Provided Workloads

All application-layer components are defined under `backend/deployment/` in this repository.

```bash
export KUBECONFIG=/path/to/config.12.yaml

# Cluster-level services
kubectl apply -f https://github.com/fission/fission/releases/download/v1.22.0/fission-all-v1.22.0.yaml
# Redis (no auth, internal cluster access only)
kubectl create ns redis
kubectl create deployment redis -n redis --image=redis:latest
kubectl expose deployment redis -n redis --port=6379
kubectl create ns keda
helm repo add kedacore https://kedacore.github.io/charts
helm repo update
helm install keda kedacore/keda -n keda

# Backend API (package source into ConfigMap first)
tar -czf /tmp/backend.tar.gz backend/
kubectl create configmap backend-code-cm -n comp90024 --from-file=backend.tar.gz=/tmp/backend.tar.gz --dry-run=client -o yaml | kubectl apply -f -
kubectl apply -f backend/deployment/k8s/

# GDELT harvester
kubectl create configmap gdelt-harvest-code -n comp90024 \
  --from-file=backend/deployment/k8s/gdelt_incremental.py
kubectl apply -f backend/deployment/k8s/gdelt_deployment.yaml 2>/dev/null || \
kubectl apply -f - <<EOF
apiVersion: apps/v1
kind: Deployment
metadata: {name: gdelt-gkg-harvest, namespace: comp90024}
spec:
  replicas: 1
  selector: {matchLabels: {app: gdelt-gkg-harvest}}
  template:
    metadata: {labels: {app: gdelt-gkg-harvest}}
    spec:
      containers:
      - name: harvester
        image: fission/python-env-3.9
        command: ["python3", "-u", "/code/gdelt_incremental.py"]
        volumeMounts: [{name: code, mountPath: /code}]
        env:
        - {name: ES_HOST, value: "https://elasticsearch-es-http.elastic.svc.cluster.local:9200"}
        - {name: ES_USERNAME, value: elastic}
        - {name: ES_PASSWORD, valueFrom: {secretKeyRef: {name: housing-es-credentials, key: password}}}
        - {name: ES_VERIFY_CERTS, value: "0"}
      volumes:
      - {name: code, configMap: {name: gdelt-harvest-code}}
EOF

# YouTube CronJobs + KEDA ScaledObject
# YouTube scripts (harvest_youtube_v3.py, ingest_youtube_master.py) live on the cluster PVC.
# Create ConfigMaps from those files before applying the CronJob manifests.
kubectl apply -f backend/deployment/k8s/06-youtube-cronjob.yaml
kubectl apply -f backend/deployment/k8s/05-keda-scaledobject.yaml

# Fission environment
fission env create --name python39 --image fission/python-env-3.9 --builder fission/python-builder-3.9 --poolsize 3

# Package functions with dependencies
cd backend/deployment/fission/functions
echo "textblob" > requirements.txt
zip bluesky.zip bluesky_harvest.py requirements.txt
zip mastodon.zip mastodon_harvest.py requirements.txt
zip processor.zip housing_processor.py requirements.txt
zip dashboard.zip compute_dashboard.py
zip health.zip health.py

# Deploy via sourcearchive (builder runs pip install -r requirements.txt)
fission function create --name bluesky-harvest   --env python39 --sourcearchive bluesky.zip   --entrypoint bluesky_harvest.main   --secret bluesky-accounts --fntimeout 180
fission function create --name mastodon-harvest   --env python39 --sourcearchive mastodon.zip   --entrypoint mastodon_harvest.main   --secret mastodon-tokens   --fntimeout 240
fission function create --name housing-processor  --env python39 --sourcearchive processor.zip  --entrypoint housing_processor.main
fission function create --name compute-dashboard  --env python39 --sourcearchive dashboard.zip  --entrypoint compute_dashboard.main --executortype newdeploy
fission function create --name health             --env python39 --sourcearchive health.zip      --entrypoint health.main

# Triggers
fission timetrigger create --name bluesky-timer  --function bluesky-harvest   --cron '@every 30m'
fission timetrigger create --name mastodon-timer  --function mastodon-harvest   --cron '@every 30m'
fission timetrigger create --name dashboard-timer --function compute-dashboard  --cron '@every 30m'

fission route create --method POST --url /bluesky-harvest   --function bluesky-harvest
fission route create --method POST --url /mastodon-harvest   --function mastodon-harvest
fission route create --method POST --url /compute-dashboard --function compute-dashboard
fission route create --method GET  --url /health            --function health

fission mqtrigger create --name housing-mq --function housing-processor --mqtype redis --topic housing-posts --mqtkind keda
```

### CI/CD Pipeline

The repository includes a GitLab CI/CD pipeline (`.gitlab-ci.yml`) with three stages:

| Stage | Trigger | Description |
|-------|---------|-------------|
| `lint` | Automatic, every push | Compiles all Python files under `backend/` |
| `test` | Automatic, every push | Executes sentiment and normalisation unit tests |
| `deploy` | Manual | Applies K8s manifests and updates Fission functions |

The `lint` and `test` stages run on every push and are the primary CI checks. The `deploy` stage requires `KUBECONFIG_B64` configured as a GitLab CI variable and a live cluster. MRC clusters are periodically rebuilt; stored kubeconfig expires. Manual deployment is the standard workflow; the deploy stage shows CI/CD capability.

---

## iii. Special Environments

### Fission Python 3.9 Environment

```bash
fission env create --name python39 --image fission/python-env-3.9 --builder fission/python-builder-3.9 --poolsize 3
```

### Function Deployment

Functions are deployed via `--sourcearchive`. Include a `requirements.txt` so the builder installs dependencies (e.g. textblob):

```bash
echo "textblob" > requirements.txt
zip function.zip <function>.py requirements.txt

fission function create --name <name> --env python39 \
  --sourcearchive function.zip \
  --entrypoint <module>.<handler>
```

Function-specific configuration:

| Function | Additional flags | Notes |
|----------|-----------------|-------|
| `mastodon-harvest` | `--fntimeout 240 --secret mastodon-tokens` | 214 API calls; needs 240s timeout |
| `bluesky-harvest` | `--fntimeout 180 --secret bluesky-accounts` | |
| `compute-dashboard` | `--executortype newdeploy` | Long-running; newdeploy isolates from poolmgr |
| `housing-processor` | (none) | Invoked by MQ trigger |
| `health` | (none) | |

### Secrets

BlueSky accounts use comma-separated `handle=password` pairs:

```bash
kubectl create secret generic bluesky-accounts -n default \
  --from-literal=BSKY_ACCOUNTS='<HANDLE>=<APP_PASSWORD>'
```

Mastodon tokens use comma-separated `instance=token` pairs:

```bash
kubectl create secret generic mastodon-tokens -n default \
  --from-literal=MASTODON_TOKENS='<INSTANCE>=<TOKEN>'
```

---

## iv. Message Queue

The BlueSky and Mastodon harvesters publish raw posts to a Redis queue. A dedicated Fission function consumes the queue via an MQ trigger, computes sentiment, and bulk-indexes normalised documents to Elasticsearch. KEDA monitors the Redis queue depth and scales the processor from 0 to 3 replicas.

```
Harvester → Redis LPUSH housing-posts → KEDA watches queue length
  → Fission MQ trigger → housing-processor → sentiment analysis → ES bulk index
```

**Components:**

- **Redis:** single-node deployment in the `redis` namespace. Harvesters write via raw RESP protocol; no Redis client library is required.
- **KEDA ScaledObject:** `housing-mq`, min=0, max=3 replicas, triggers when `housing-posts` list length reaches 5.
- **Fission MQ Trigger:** `housing-mq` → `housing-processor`, message queue type `redis`, topic `housing-posts`.
- **Fallback:** if Redis is unreachable, harvesters detect the connection failure and write directly to Elasticsearch with inline sentiment computation.

---

## v. HTTP Triggers

### Timer Triggers

```bash
fission timetrigger create --name bluesky-timer   --function bluesky-harvest   --cron '@every 30m'
fission timetrigger create --name mastodon-timer   --function mastodon-harvest   --cron '@every 30m'
fission timetrigger create --name dashboard-timer  --function compute-dashboard  --cron '@every 30m'
```

### HTTP Routes

```bash
fission route create --method POST --url /bluesky-harvest   --function bluesky-harvest
fission route create --method POST --url /mastodon-harvest   --function mastodon-harvest
fission route create --method POST --url /compute-dashboard --function compute-dashboard
fission route create --method GET  --url /health            --function health
```

### Manual Invocation

Functions can be invoked through the Fission router:

```bash
kubectl port-forward -n fission svc/router 9090:80 &
curl -X POST http://localhost:9090/fission-function/bluesky-harvest

# or via the fission CLI
fission function test --name bluesky-harvest --timeout 60s
```

---

## vi. Testing

Tests are located in `test/`. See `test/README.md` for details.

```bash
cd ~/Desktop/comp90024_team_12
PYTHONPATH="$(pwd)" python3 test/smoke_tests.py
```

The smoke test suite validates ES mapping files, normalises sample records from all four platforms, and checks notebook syntax. Additional live-cluster verification commands are documented in `test/README.md`.

---

## vii. Repository Layout

- `backend/api/` Flask REST API (app, housing, official, analysis, cache routes)
- `backend/analytics/` data processing (normalisation, sentiment, ingestion, dashboard, core)
- `backend/harvesting/` raw data specs, sample records, schema, normalise scripts
- `backend/deployment/` K8s manifests and Fission function source code
- `backend/mappings/` Elasticsearch index mappings
- `database/` copy of ES index mappings
- `data/` collected datasets (large files excluded from Git)
- `docs/` architecture, final report, evidence screenshots, figures
- `frontend/` Jupyter notebook dashboard
- `test/` smoke tests and unit tests
- `llm/` LLM usage disclosure
- `.gitlab-ci.yml` CI/CD pipeline

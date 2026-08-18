# COMP90024 Team 12
# Public attribution: COMP90024 Team 12; member identities removed from this portfolio copy.

# Tests

## Smoke Tests (`smoke_tests.py`)

Run from the repository root:

```bash
cd ~/Desktop/comp90024_team_12
PYTHONPATH="$(pwd)" python3 test/smoke_tests.py
```

Three checks are performed:

1. **ES mapping validation**: checks `backend/mappings/` and `database/` JSON files are valid with `properties`
2. **Normalisation**: runs sample records from all four platforms through the normaliser, checks all 13 required fields present
3. **Notebook syntax**: parses code cells in the dashboard notebook, skips shell and magic commands

## Live Cluster Verification

After deploying, run these checks against the running cluster:

```bash
export KUBECONFIG=/path/to/config.12.yaml

# Elasticsearch cluster health
kubectl port-forward -n elastic svc/elasticsearch-es-default 9200:9200 &
curl -sk 'https://127.0.0.1:9200/_cluster/health' --user elastic:elastic

# Backend API
kubectl port-forward -n comp90024 svc/housing-backend-api 8080:80 &
curl http://localhost:8080/api/health

# Fission functions and triggers
fission function list
fission timetrigger list
fission route list
fission mqtrigger list

# Individual function test
fission function test --name health --timeout 10s

# Timer activity: should show entries from the last 10 minutes
kubectl logs -n fission deployment/timer --since=10m

# Redis MQ queue depth
kubectl exec -n redis deployment/redis -- redis-cli LLEN housing-posts
```

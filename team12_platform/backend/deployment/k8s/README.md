# COMP90024 Team 12
# Public attribution: COMP90024 Team 12; member identities removed from this portfolio copy.

# Kubernetes deployment

This folder deploys the Flask backend API and harvester workloads to Kubernetes.

## Assumptions

- Elasticsearch is already running in the `elastic` namespace.
- `housing_posts` and `official_housing_rows` indices already exist.
- The backend is deployed via ConfigMap (no container registry required).

## Apply manifests

```bash
kubectl apply -f backend/deployment/k8s/00-namespace.yaml
kubectl apply -f backend/deployment/k8s/01-backend-configmap.yaml
kubectl apply -f backend/deployment/k8s/02-backend-deployment.yaml
kubectl apply -f backend/deployment/k8s/03-backend-service.yaml
kubectl apply -f backend/deployment/k8s/04-backend-hpa.yaml
```

The Deployment uses an init container to unpack the backend source from a ConfigMap, so no Docker image build or registry push is needed.

## GDELT harvester

```bash
kubectl create configmap gdelt-harvest-code -n comp90024 \
  --from-file=backend/deployment/k8s/gdelt_incremental.py
kubectl apply -f - <<EOF
apiVersion: apps/v1
kind: Deployment
metadata:
  name: gdelt-gkg-harvest
  namespace: comp90024
spec:
  replicas: 1
  selector:
    matchLabels:
      app: gdelt-gkg-harvest
  template:
    spec:
      containers:
      - name: harvester
        image: fission/python-env-3.9
        command: ["python3", "-u", "/code/gdelt_incremental.py"]
        volumeMounts:
        - name: code
          mountPath: /code
        env:
        - name: ES_HOST
          value: https://elasticsearch-es-http.elastic.svc.cluster.local:9200
        - name: ES_USERNAME
          value: elastic
        - name: ES_PASSWORD
          value: elastic
        - name: ES_VERIFY_CERTS
          value: "0"
      volumes:
      - name: code
        configMap:
          name: gdelt-harvest-code
EOF
```

## Validate

```bash
kubectl get pods -n comp90024
kubectl get svc -n comp90024
kubectl port-forward -n comp90024 svc/housing-backend-api 8080:80
curl http://localhost:8080/api/health
```

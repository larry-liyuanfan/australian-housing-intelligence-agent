# Backend deployment: Kubernetes + Fission

This folder adds the cloud deployment layer required by COMP90024 Assignment 2.

## Structure

```text
deployment/
├── k8s/       # Kubernetes Deployment/Service/HPA for the full Flask backend API
└── fission/   # Fission functions and route deployment script
```

## Recommended architecture

```text
Jupyter Notebook frontend
        ↓
Kubernetes Service / Fission Router
        ↓
Flask backend API or Fission functions
        ↓
ElasticSearch service
```

## Division of responsibility

- Kubernetes runs the long-lived REST backend service.
- Fission demonstrates serverless ingestion and lightweight analytical functions.
- ElasticSearch stores `housing_posts` and `official_housing_rows`.

This keeps batch processing, storage, serverless event handling and frontend API access clearly separated.

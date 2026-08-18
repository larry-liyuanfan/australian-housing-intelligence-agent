# COMP90024 Team 12
# Public attribution: COMP90024 Team 12; member identities removed from this portfolio copy.

# Fission deployment

This folder contains the Fission function source code for the assignment's serverless requirements.

## Functions

| Function | Trigger | Purpose |
|----------|---------|---------|
| `bluesky-harvest` | Timer @every 30m | Collects BlueSky posts via AT Protocol, publishes to Redis MQ |
| `mastodon-harvest` | Timer @every 30m | Collects Mastodon posts via instance APIs, publishes to Redis MQ |
| `housing-processor` | MQ trigger (Redis) | Consumes Redis queue, computes sentiment, bulk-indexes to ES |
| `compute-dashboard` | Timer @every 30m | Pre-computes dashboard cache panels in ES |
| `health` | HTTP GET /health | Cluster health check |

## Deployment

Functions are deployed via `--sourcearchive`, which triggers the builder to install dependencies from `requirements.txt`:

```bash
cd backend/deployment/fission/functions
echo "textblob" > requirements.txt
zip bluesky.zip bluesky_harvest.py requirements.txt
zip mastodon.zip mastodon_harvest.py requirements.txt
zip processor.zip housing_processor.py requirements.txt
zip dashboard.zip compute_dashboard.py
zip health.zip health.py

fission function create --name bluesky-harvest  --env python39 --sourcearchive bluesky.zip  --entrypoint bluesky_harvest.main  --secret bluesky-accounts --fntimeout 180
fission function create --name mastodon-harvest  --env python39 --sourcearchive mastodon.zip  --entrypoint mastodon_harvest.main  --secret mastodon-tokens  --fntimeout 240
fission function create --name housing-processor --env python39 --sourcearchive processor.zip --entrypoint housing_processor.main
fission function create --name compute-dashboard --env python39 --sourcearchive dashboard.zip --entrypoint compute_dashboard.main --executortype newdeploy
fission function create --name health            --env python39 --sourcearchive health.zip     --entrypoint health.main
```

## Triggers

```bash
fission timetrigger create --name bluesky-timer  --function bluesky-harvest  --cron '@every 30m'
fission timetrigger create --name mastodon-timer  --function mastodon-harvest  --cron '@every 30m'
fission timetrigger create --name dashboard-timer --function compute-dashboard --cron '@every 30m'

fission route create --method POST --url /bluesky-harvest   --function bluesky-harvest
fission route create --method POST --url /mastodon-harvest   --function mastodon-harvest
fission route create --method POST --url /compute-dashboard --function compute-dashboard
fission route create --method GET  --url /health            --function health

fission mqtrigger create --name housing-mq --function housing-processor --mqtype redis --topic housing-posts --mqtkind keda
```

## Validate

```bash
fission function list
fission timetrigger list
fission route list
fission mqtrigger list

# Manual function test
fission function test --name health --timeout 10s
```

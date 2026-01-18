# Multi-Node Deployment Guide (Workspace Events + Notion Webhooks)

## Cloud (GitHub Actions + Cloud Run)

### 1) Required GitHub Secrets

Configured in `.github/workflows/workspace-events-cloud.yml`:

- `GCP_PROJECT_ID`
- `GCP_SERVICE_ACCOUNT_KEY` (service account JSON)
- `NOTION_API_KEY`
- `NOTION_ENV_INSTANCES_DB`
- `GOOGLE_DRIVE_ID`
- `WEBHOOK_DASHBOARD_API_KEY`

### 2) Deploy Cloud Run

- Push to `main` (any change under `seren-media-workflows/scripts/workspace_events/**`), or
- Run the workflow manually via `workflow_dispatch`.

Cloud Run entrypoint:

- `seren-media-workflows/scripts/workspace_events/cloud_run_main.py`

Docker entrypoint:

- `seren-media-workflows/scripts/workspace_events/Dockerfile`

### 3) Pub/Sub push subscription

Create a Pub/Sub subscription that pushes to:

- `POST https://<cloud-run-host>/pubsub/push`

Ensure IAM is set so Pub/Sub can invoke Cloud Run (service account publisher role + invoker).

### 4) Poll safety-net (optional)

The workflow includes a scheduled job that runs:

- `seren-media-workflows/scripts/workspace_events/cloud_run_poll.py`

This is intended as a **backstop**; primary mode should be Pub/Sub push.

## Local (MM2 node)

### 1) Environment variables

At minimum:

- `NOTION_API_TOKEN` (used by Notion webhook server)
- Any Google credentials needed for Pub/Sub pull (ADC or service account)

Optional tuning:

- `WORKSPACE_EVENTS_POLLING_INTERVAL` (default 10)
- `WORKSPACE_EVENTS_MAX_MESSAGES` (default 10)
- `WORKSPACE_EVENTS_AUTO_RENEWAL` (default true)

### 2) Start services

Use:

- `webhook-server/start_multi_node_server.sh`

This creates/uses `webhook-server/venv`, installs `webhook-server/requirements.txt`, and starts:

- `webhook-server/notion_event_subscription_webhook_server_v5_multi_node.py`
- `webhook-server/webhook_dashboard_service_v2.py`

## Google Apps Script (complementary)

### 1) Deploy

Project files:

- `gas-scripts/workspace-events-sync/`

### 2) Set Script Properties

Required:

- `NOTION_TOKEN`
- `GCP_PROJECT_ID`
- `PUBSUB_SUBSCRIPTION_NAME` (or `PUBSUB_SUBSCRIPTION_PATH`)
- `WORKSPACE_EVENTS_CSV_FOLDER_ID`

Recommended:

- `WORKSPACE_EVENTS_AUTOMATION_SOURCE_VALUE=gas_workspace_events`
- `SEREN_AUTOMATION_SOURCE_PROPERTY=Seren Automation Source`

### 3) Install trigger

Run:

- `workspaceEvents_installTrigger(5)`

## Loop-Guard configuration

Notion webhook ignore list is controlled by:

- `SEREN_AUTOMATION_IGNORE_SOURCES` (comma-separated)

Defaults include:

- `workspace_events,gas_workspace_events,drivesheetsync,notion_webhook_server`


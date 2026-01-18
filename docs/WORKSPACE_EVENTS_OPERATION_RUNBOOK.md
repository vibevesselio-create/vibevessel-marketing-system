# Operations Runbook (Multi-Node)

## Health checks

### Cloud Run (Workspace Events)

- `GET /health` (Cloud Run service)
- `GET /metrics` (processing metrics)

Entry: `seren-media-workflows/scripts/workspace_events/cloud_run_main.py`

### Local Notion webhook server (MM2)

- `GET http://localhost:5001/health`
- `GET http://localhost:5001/workspace-events/health`
- `GET http://localhost:5001/workspace-events/status`

Entry: `webhook-server/notion_event_subscription_webhook_server_v5_multi_node.py`

### Local Dashboard service (MM2)

- `GET http://localhost:5003/dashboard/api/status`
- `GET http://localhost:5003/dashboard/api/nodes`
- `GET http://localhost:5003/dashboard/api/csv-stats`

Entry: `webhook-server/webhook_dashboard_service_v2.py`

## Verifying CSV outputs

### Workspace Events CSV

- Python exporter: `seren-media-workflows/scripts/workspace_events/core/csv_exporter.py`
- File pattern: `webhook_events_{node_id}_{timestamp}.csv`

### Notion webhook CSV

- Daily log file: `notion_database_webhooks_{YYYY-MM-DD}.csv`
- Path configured in:
  - `webhook-server/notion_event_subscription_webhook_server_v4_enhanced.py` (`WEBHOOK_CSV_DIR`)

## Circular-flow troubleshooting (critical)

### Symptom: Notion changes trigger repeated webhooks / infinite loops

**Expected safeguard**:

- Workspace Events writes to Notion add:
  - `Seren Automation Source=workspace_events` (or `gas_workspace_events`)
- Notion webhook server ignores those events.

Check:

- On a page that loops, verify the `Seren Automation Source` property exists and is populated.
- If the property is missing, ensure the DB schema update is permitted:
  - `seren-media-workflows/scripts/workspace_events/drive_sync_handler.py` will attempt to add the property.

### Symptom: Drive artifacts cause unnecessary Notion sync

**Expected safeguard**:

- Drive→Notion sync ignores files with prefixes:
  - `webhook_events_`, `workspace_events_`, `notion_database_webhooks_`

Check:

- `WORKSPACE_EVENTS_IGNORE_NAME_PREFIXES` (Python env) or GAS config.

## Pub/Sub processing reliability

Local node Pub/Sub consumer acks **only after** successful processing:

- `webhook-server/workspace_events_integration.py`

If you see message loss, verify:

- Pub/Sub subscription ack deadlines
- Any exceptions in the processing loop

## Slack Event Subscriptions alignment

Slack Event Subscriptions are handled by the same server and are **queued** for processing so they don’t compete with Notion/Workspace processing or exceed Slack response time limits.

- Endpoint: `POST /slack/events`
- Receipt behavior: verifies signature, handles `url_verification`, then **queues** the payload and returns immediately.

Safeguards:

- **Deduplication** by `event_id` (short-term TTL cache)
- **Bot-message suppression** by default for `message` events (prevents feedback loops)
- **CSV logging** to `SLACK_EVENTS_CSV_DIR`
- **Optional dashboard ingest** to `WEBHOOK_DASHBOARD_INGEST_URL` (requires `WEBHOOK_DASHBOARD_API_KEY`)


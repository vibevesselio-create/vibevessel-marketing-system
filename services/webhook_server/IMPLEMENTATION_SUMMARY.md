# Notion Event Subscription Webhook Server - Implementation Summary

**Document Generated:** 2026-01-16
**Server Version:** v4 Enhanced
**Status:** Operational

---

## Executive Summary

The Notion Event Subscription Webhook Server is a FastAPI-based service that receives and processes webhook events from Notion's Event Subscription API (v2025-09-03). This document summarizes the implementation, recent fixes, and operational status.

### Key Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/webhook` | POST | Receives Notion webhook events |
| `/health` | GET | Health check endpoint |
| `/auth/google/callback` | GET | Google OAuth2 callback |

### Public URLs

- **Webhook URL:** `https://webhook.vibevessel.space/webhook`
- **Health Check:** `https://webhook.vibevessel.space/health`
- **Local Access:** `http://localhost:5001/webhook`

---

## Architecture

### System Components

```
Notion API ──► Cloudflare Tunnel ──► Webhook Server (localhost:5001) ──► Processing Queue
                    │                         │
                    ▼                         ▼
        webhook.vibevessel.space        CSV Logging + Notion API
```

### Service Configuration

| Component | Configuration |
|-----------|---------------|
| **Server Port** | 5001 |
| **Python Path** | /opt/homebrew/bin/python3 |
| **PYTHONPATH** | /Users/brianhellemn/Projects/github-production |
| **Cloudflare Tunnel** | 8f70cf6f-551f-4fb7-b1f9-0349f2f688f3 |

### LaunchAgent Services

1. **com.seren.webhook-server.plist** - Auto-starts webhook server on boot
2. **com.seren.cloudflared-tunnel.plist** - Auto-starts Cloudflare tunnel on boot

---

## Supported Event Types

The webhook server accepts and processes all Notion Event Subscription webhook types:

| Event Type | Description | Status |
|------------|-------------|--------|
| `page.created` | New page created in database | Supported |
| `page.properties_updated` | Page properties modified | Supported |
| `page.content_updated` | Page content/blocks modified | Supported |
| `page.deleted` | Page deleted from database | Supported |
| `data_source.schema_updated` | Database schema changed | Supported |

### Event Statistics (2026-01-16)

| Event Type | Count |
|------------|-------|
| page.properties_updated | 747 |
| page.content_updated | 350 |
| page.created | 201 |
| page.deleted | 40 |
| data_source.schema_updated | 9 |

---

## CSV Logging Implementation

### Fix Applied: 2026-01-16

**Issue:** Event subscription webhooks were not being logged to CSV. Only 1 out of 81 webhooks was recorded.

**Root Cause:** The `log_webhook_to_csv()` function was not called in the `event_subscription` processing path (line 3074-3084).

**Fix:** Added CSV logging call for event_subscription webhooks:

```python
elif is_event_subscription:
    print(f"Received Notion Event Subscription webhook: {payload.get('type', 'unknown')}")
    log_webhook_to_csv(payload, "event_subscription", {"status": "webhook_queued", "event_type": payload.get('type', 'unknown')})
    # ... rest of processing
```

### CSV Output Location

```
/Users/brianhellemn/Library/CloudStorage/GoogleDrive-brian@serenmedia.co/
  My Drive/Seren Internal/Automation Files/Notion-Database-Webhooks/
    notion_database_webhooks_YYYY-MM-DD.csv
```

### CSV Schema

| Column | Description |
|--------|-------------|
| timestamp | ISO 8601 timestamp |
| event_type | Notion event type |
| entity_id | Page/Database UUID |
| entity_type | page or database |
| database_id | Parent database UUID |
| name | Entity name/title |
| file_path | File path (if applicable) |
| actions_info | Related actions |
| processing_status | Processing result |
| actions_processed | Count of processed actions |
| error_message | Error details (if any) |
| payload | Full JSON payload |

---

## Processing Flow

### Webhook Receipt Flow

```
1. POST /webhook receives payload
2. Verify format (event_subscription vs automation)
3. Log to CSV immediately
4. Add to processing queue
5. Return 200 OK to Notion
```

### Queue Processing Flow

```
1. Dequeue webhook item
2. Extract event_type and entity_id
3. Fetch full entity from Notion API
4. Route to appropriate handler:
   - Scripts DB → Script sync handler
   - Workflows DB → Workflow handler
   - Prompts DB → Prompt handler
   - Agent-Tasks DB → Linear/GitHub sync
   - Other → Legacy handler
5. Log completion status
```

---

## Database Routing

The webhook server routes events based on parent database:

| Database | Handler | Purpose |
|----------|---------|---------|
| Scripts (SCRIPT_ROUTER_DB_ID) | `_handle_script_sync_webhook` | Script synchronization |
| Workflows (WORKFLOWS_ROUTER_DB_ID) | `_handle_workflow_webhook` | Workflow processing |
| Prompts (PROMPTS_DB_ID) | `_handle_prompt_webhook` | Prompt execution |
| Agent-Tasks (AGENT_TASKS_DB_ID) | `_handle_agent_task_linear_github_sync` | Linear/GitHub sync |
| Others | `_handle_legacy_webhook` | Default processing |

---

## Logging Methodology

### Current Implementation

The webhook server uses multiple logging approaches:

1. **Console Logging** - Print statements with emoji indicators
2. **CSV Logging** - `log_webhook_to_csv()` for audit trail
3. **Notification Events** - `_emit_notification()` for system alerts
4. **Event Line Logging** - `_log_event_line()` for structured logs

### Unified Logging Modules Available

The codebase provides these unified logging modules:

1. **`shared_core.logging.UnifiedLogger`** - Enterprise-grade with metrics, Notion integration
2. **`music_workflow.utils.logging.MusicWorkflowLogger`** - Domain-specific for music workflows
3. **`seren_utils.logging.StructuredLogger`** - Correlation ID support for distributed systems
4. **`unified_config.setup_unified_logging()`** - Environment-driven configuration

### Recommendation

Consider migrating to `shared_core.logging.UnifiedLogger` for:
- Triple logging (Console + JSONL + .log)
- Metrics tracking
- Notion execution log integration
- Sensitive data redaction

---

## Operational Commands

### Start Services

```bash
# Start webhook server (canonical path)
cd /Users/brianhellemn/Projects/github-production/services/webhook_server
PYTHONPATH=/Users/brianhellemn/Projects/github-production \
  /opt/homebrew/bin/python3 notion_event_subscription_webhook_server_v4_enhanced.py

# Start Cloudflare tunnel
cloudflared tunnel run
```

### Check Status

```bash
# Check if services are running
lsof -i :5001 | grep LISTEN
pgrep -f cloudflared

# Health check
curl http://localhost:5001/health

# View recent logs
tail -f /Users/brianhellemn/Library/Logs/webhook-server.log
```

### LaunchAgent Management

```bash
# Load services
launchctl load ~/Library/LaunchAgents/com.seren.webhook-server.plist
launchctl load ~/Library/LaunchAgents/com.seren.cloudflared-tunnel.plist

# Unload services
launchctl unload ~/Library/LaunchAgents/com.seren.webhook-server.plist
launchctl unload ~/Library/LaunchAgents/com.seren.cloudflared-tunnel.plist
```

---

## Known Issues & Resolutions

### Issue 1: Webhook Subscription Paused (Resolved)

**Symptom:** Notion dashboard showed webhook subscription as "Paused"
**Root Cause:** Cloudflare tunnel and webhook server not running
**Resolution:** Started both services and installed LaunchAgents for auto-start

### Issue 2: CSV Logging Missing (Resolved)

**Symptom:** Only 1 of 81 webhooks logged to CSV
**Root Cause:** `log_webhook_to_csv()` not called for event_subscription webhooks
**Resolution:** Added CSV logging call at line 3077

### Issue 3: ModuleNotFoundError for shared_core (Resolved)

**Symptom:** Server failed to start with import error
**Root Cause:** PYTHONPATH not set
**Resolution:** Added PYTHONPATH to LaunchAgent plist and startup commands

---

## File Locations

| File | Purpose |
|------|---------|
| `/Users/brianhellemn/Projects/github-production/services/webhook_server/notion_event_subscription_webhook_server_v4_enhanced.py` | Main server (CANONICAL) |
| `/Users/brianhellemn/Projects/github-production/services/webhook_server/launchagents/` | LaunchAgent templates |
| `/Users/brianhellemn/Projects/github-production/services/webhook_server/cloudflared/config.yml` | Cloudflare tunnel config template |
| `/Users/brianhellemn/.cloudflared/config.yml` | Active Cloudflare tunnel config |
| `/Users/brianhellemn/Library/LaunchAgents/com.seren.webhook-server.plist` | Server LaunchAgent (installed) |
| `/Users/brianhellemn/Library/LaunchAgents/com.seren.cloudflared-tunnel.plist` | Tunnel LaunchAgent (installed) |
| `/Users/brianhellemn/Library/Logs/webhook-server.log` | Server stdout |
| `/Users/brianhellemn/Library/Logs/webhook-server.err.log` | Server stderr |

**Note:** The `/webhook-server/` directory at the repo root is deprecated. Use `/services/webhook_server/` as the canonical location.

---

## Related Documentation

- [Notion Event Types & Delivery](https://developers.notion.com/reference/webhooks-events-delivery)
- [Notion Webhooks Reference](https://developers.notion.com/reference/webhooks)

---

**Document Status:** Complete
**Last Updated:** 2026-01-16T11:00:00

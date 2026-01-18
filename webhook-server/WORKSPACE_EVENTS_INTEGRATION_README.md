# Google Workspace Events API Integration

**Status:** ✅ **Integrated into Webhook Server**

---

## Overview

The Google Workspace Events API workflow has been integrated into the Notion webhook server for persistent, resource-efficient background execution. The service automatically processes Google Drive events and synchronizes them to Notion databases.

---

## Features

- ✅ **Background Processing** - Runs automatically in background threads
- ✅ **Resource Efficient** - Configurable polling intervals (default: 10 seconds)
- ✅ **Automatic Subscription Renewal** - Prevents subscription expiration
- ✅ **Error Recovery** - Automatic retry and error handling
- ✅ **Health Monitoring** - Status endpoints for monitoring
- ✅ **Execution Logging** - All events logged to Notion Execution-Logs
- ✅ **Safeguarded** - Graceful shutdown and error handling

---

## Configuration

### Environment Variables

```bash
# Polling configuration
WORKSPACE_EVENTS_POLLING_INTERVAL=10        # Seconds between Pub/Sub polls
WORKSPACE_EVENTS_MAX_MESSAGES=10            # Max messages per poll
WORKSPACE_EVENTS_AUTO_RENEWAL=true         # Enable subscription auto-renewal

# Required (already configured)
NOTION_API_KEY=your_notion_api_key
GCP_PROJECT_ID=your_project_id
GOOGLE_SERVICE_ACCOUNT_FILE=/path/to/service-account.json
```

---

## API Endpoints

### Health Check
```
GET /health
```
Includes Workspace Events service status in response.

### Workspace Events Status
```
GET /workspace-events/status
```
Returns detailed status and statistics:
- Running status
- Messages processed/failed
- Last poll time
- Subscription health
- Error history

### Workspace Events Health
```
GET /workspace-events/health
```
Returns health check information:
- Service status
- Subscription accessibility
- Last activity times

---

## Architecture

```
Webhook Server (FastAPI)
├── Notion Webhook Processing (Port 5001)
│   └── WebhookQueue (Sequential Processing)
│
└── Google Workspace Events API Service
    ├── Message Processing Thread
    │   └── Pulls from Pub/Sub → Processes → Acknowledges
    │
    └── Subscription Renewal Thread
        └── Checks health → Auto-renews expiring subscriptions
```

---

## How It Works

1. **Startup**: Service initializes on webhook server startup
   - Creates WorkspaceEventHandler
   - Initializes SubscriptionManager
   - Connects to Pub/Sub subscription
   - Starts background processing threads

2. **Message Processing**:
   - Polls Pub/Sub every `WORKSPACE_EVENTS_POLLING_INTERVAL` seconds
   - Pulls up to `WORKSPACE_EVENTS_MAX_MESSAGES` messages
   - Processes each message through WorkspaceEventHandler
   - Acknowledges successful processing
   - Nacks failed messages for retry

3. **Subscription Renewal**:
   - Checks subscription health every hour
   - Auto-renews subscriptions expiring within 12 hours
   - Logs renewal activity

4. **Shutdown**: Service stops gracefully on webhook server shutdown
   - Stops processing threads
   - Closes Pub/Sub connections
   - Updates execution logs

---

## Monitoring

### Check Service Status
```bash
curl http://localhost:5001/workspace-events/status
```

### Check Health
```bash
curl http://localhost:5001/workspace-events/health
```

### View Logs
The service logs to the webhook server log file:
```bash
tail -f webhook-server/webhook_server.log | grep "Workspace Events"
```

---

## Resource Management

### Polling Interval
- **Default**: 10 seconds
- **Impact**: Lower = more responsive but higher CPU usage
- **Recommendation**: 10-30 seconds for production

### Max Messages
- **Default**: 10 messages per poll
- **Impact**: Higher = processes more events per poll but longer processing time
- **Recommendation**: 10-50 depending on event volume

### Thread Safety
- Uses daemon threads (automatically stop on server shutdown)
- Thread-safe queue processing
- No blocking of main webhook server

---

## Safeguards

1. **Error Handling**:
   - All errors caught and logged
   - Failed messages nacked for retry
   - Service continues even if individual messages fail

2. **Resource Limits**:
   - Configurable polling intervals prevent CPU overload
   - Max messages per poll prevents memory issues
   - Error history limited to last 100 errors

3. **Graceful Shutdown**:
   - Service stops cleanly on server shutdown
   - Threads join with timeout
   - No orphaned processes

4. **Health Monitoring**:
   - Status endpoints for monitoring
   - Health checks include subscription accessibility
   - Error tracking and reporting

---

## Troubleshooting

### Service Not Starting
- Check environment variables are set
- Verify Google credentials are valid
- Check Pub/Sub subscription exists
- Review logs for initialization errors

### No Messages Processing
- Verify subscription is active
- Check subscription health: `GET /workspace-events/health`
- Verify Pub/Sub topic has messages
- Check polling interval isn't too high

### High Error Rate
- Check error history in status endpoint
- Verify Notion API key is valid
- Check Drive service account permissions
- Review execution logs in Notion

---

## Production Deployment

The service runs automatically when the webhook server starts. No additional deployment steps required.

### Recommended Settings for Production
```bash
WORKSPACE_EVENTS_POLLING_INTERVAL=15        # 15 seconds
WORKSPACE_EVENTS_MAX_MESSAGES=20            # 20 messages
WORKSPACE_EVENTS_AUTO_RENEWAL=true         # Enable renewal
```

---

**Last Updated:** 2026-01-18  
**Integration Status:** ✅ Complete  
**Production Ready:** ✅ Yes

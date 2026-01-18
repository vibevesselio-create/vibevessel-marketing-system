# Google Workspace Events API - Production Deployment Guide

**Date:** 2026-01-18  
**Status:** ✅ **Ready for Production**

---

## Quick Start

### 1. Install Dependencies

```bash
cd webhook-server
pip3 install -r requirements.txt
```

### 2. Configure Environment Variables

Add to your `.env` file or environment:

```bash
# Google Workspace Events API
WORKSPACE_EVENTS_POLLING_INTERVAL=10        # Seconds between polls
WORKSPACE_EVENTS_MAX_MESSAGES=10            # Max messages per poll
WORKSPACE_EVENTS_AUTO_RENEWAL=true         # Enable auto-renewal

# Required (should already be set)
NOTION_API_KEY=your_notion_api_key
GCP_PROJECT_ID=your_project_id
GOOGLE_SERVICE_ACCOUNT_FILE=/path/to/service-account.json
```

### 3. Start the Server

**Option A: Using the startup script (recommended)**
```bash
./start_with_workspace_events.sh
```

**Option B: Direct Python execution**
```bash
python3 notion_event_subscription_webhook_server_v4_enhanced.py
```

The Google Workspace Events API service will start automatically in the background.

---

## Verification

### Check Service Status

```bash
# Health check (includes Workspace Events status)
curl http://localhost:5001/health

# Detailed Workspace Events status
curl http://localhost:5001/workspace-events/status

# Workspace Events health check
curl http://localhost:5001/workspace-events/health
```

### Expected Response

```json
{
  "running": true,
  "polling_interval": 10,
  "max_messages": 10,
  "auto_renewal_enabled": true,
  "stats": {
    "messages_processed": 0,
    "messages_failed": 0,
    "last_poll_time": "2026-01-18T12:00:00Z",
    "subscriptions_renewed": 0
  }
}
```

---

## Persistent Background Execution

### Using launchd (macOS)

Create a launch agent for automatic startup:

```bash
# Copy template
cp launchagents/com.seren.webhook-server.plist.template \
   ~/Library/LaunchAgents/com.seren.webhook-server.plist

# Edit the plist file to set:
# - WorkingDirectory to webhook-server directory
# - ProgramArguments to use start_with_workspace_events.sh
# - EnvironmentVariables for WORKSPACE_EVENTS_* vars

# Load the service
launchctl load ~/Library/LaunchAgents/com.seren.webhook-server.plist

# Start the service
launchctl start com.seren.webhook-server
```

### Using systemd (Linux)

Create a systemd service file:

```ini
[Unit]
Description=Notion Webhook Server with Workspace Events
After=network.target

[Service]
Type=simple
User=your_user
WorkingDirectory=/path/to/webhook-server
Environment="WORKSPACE_EVENTS_POLLING_INTERVAL=10"
Environment="WORKSPACE_EVENTS_MAX_MESSAGES=10"
Environment="WORKSPACE_EVENTS_AUTO_RENEWAL=true"
ExecStart=/usr/bin/python3 notion_event_subscription_webhook_server_v4_enhanced.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Then:
```bash
sudo systemctl enable webhook-server
sudo systemctl start webhook-server
```

---

## Resource Management

### Recommended Production Settings

```bash
# Balanced (default)
WORKSPACE_EVENTS_POLLING_INTERVAL=15
WORKSPACE_EVENTS_MAX_MESSAGES=20

# High Volume
WORKSPACE_EVENTS_POLLING_INTERVAL=5
WORKSPACE_EVENTS_MAX_MESSAGES=50

# Low Volume / Resource Constrained
WORKSPACE_EVENTS_POLLING_INTERVAL=30
WORKSPACE_EVENTS_MAX_MESSAGES=5
```

### Monitoring Resource Usage

```bash
# Check process
ps aux | grep "notion_event_subscription_webhook_server"

# Monitor logs
tail -f webhook_server.log | grep "Workspace Events"

# Check memory/CPU
top -p $(pgrep -f "notion_event_subscription_webhook_server")
```

---

## Safeguards

### Automatic Safeguards

1. **Error Recovery**: Failed messages are automatically nacked for retry
2. **Thread Safety**: Uses daemon threads that stop cleanly
3. **Resource Limits**: Configurable polling prevents CPU overload
4. **Graceful Shutdown**: Service stops cleanly on server shutdown
5. **Health Monitoring**: Status endpoints for monitoring

### Manual Safeguards

1. **Monitor Error Rate**: Check `/workspace-events/status` regularly
2. **Set Up Alerts**: Monitor health endpoint for failures
3. **Review Logs**: Check execution logs in Notion regularly
4. **Subscription Health**: Monitor subscription renewal status

---

## Troubleshooting

### Service Not Starting

1. Check dependencies: `pip3 list | grep google-cloud`
2. Verify environment variables are set
3. Check logs: `tail -f webhook_server.log`
4. Verify Google credentials: `gcloud auth application-default login`

### No Messages Processing

1. Check subscription exists: `gcloud pubsub subscriptions list`
2. Verify subscription is active: `GET /workspace-events/health`
3. Check Pub/Sub topic has messages
4. Verify polling interval isn't too high

### High Error Rate

1. Check error history: `GET /workspace-events/status`
2. Verify Notion API key is valid
3. Check Drive service account permissions
4. Review execution logs in Notion

---

## Production Checklist

- [ ] Dependencies installed (`pip3 install -r requirements.txt`)
- [ ] Environment variables configured
- [ ] Google credentials configured
- [ ] Pub/Sub subscription exists and is active
- [ ] Service starts successfully
- [ ] Health endpoints respond correctly
- [ ] Test event processing works
- [ ] Monitoring/alerting configured
- [ ] Logs are being written
- [ ] Subscription renewal is working

---

**Last Updated:** 2026-01-18  
**Production Status:** ✅ Ready

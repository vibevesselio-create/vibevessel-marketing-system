# Multi-Environment Music Sync Automation

**Version:** 1.0.0
**Created:** 2026-01-30
**Status:** Ready for Deployment

## Overview

This document describes the comprehensive multi-environment automation system for music track synchronization across:

1. **Google Apps Script** (Cloud-based 5-minute triggers)
2. **Local Cron Jobs** (System-level automation)
3. **Webhook Integration** (Cross-environment communication)
4. **Notion Database** (Configuration management)

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Multi-Environment Sync Architecture               │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌──────────────────┐         ┌──────────────────┐                 │
│  │  Google Apps     │ ──────► │  Notion Database │ ◄──────────────┐│
│  │  Script (GAS)    │         │  (Music Tracks)  │                ││
│  │  ┌────────────┐  │         └────────┬─────────┘                ││
│  │  │ 5-min      │  │                  │                          ││
│  │  │ Trigger    │  │                  │                          ││
│  │  └────────────┘  │                  │                          ││
│  │  ┌────────────┐  │                  │                          ││
│  │  │ Spotify    │  │                  │                          ││
│  │  │ OAuth      │  │                  │                          ││
│  │  └────────────┘  │                  │                          ││
│  └────────┬─────────┘                  │                          ││
│           │                            │                          ││
│           │  Webhook                   │                          ││
│           ▼                            │                          ││
│  ┌──────────────────┐                  │                          ││
│  │  Local Webhook   │                  │                          ││
│  │  Server (FastAPI)│ ◄────────────────┘                          ││
│  │  Port: 5001      │                                             ││
│  │  ┌────────────┐  │                                             ││
│  │  │ /gas/*     │  │                                             ││
│  │  │ endpoints  │  │                                             ││
│  │  └────────────┘  │                                             ││
│  └────────┬─────────┘                                             ││
│           │                                                       ││
│           │  Triggers                                             ││
│           ▼                                                       ││
│  ┌──────────────────┐         ┌──────────────────┐               ││
│  │  Local Cron Job  │ ──────► │  Production      │ ──────────────┘│
│  │  (cron_music_    │         │  Workflow        │                │
│  │   sync.py)       │         │  (soundcloud_    │                │
│  │  ┌────────────┐  │         │   download.py)   │                │
│  │  │ */5 * * *  │  │         └──────────────────┘                │
│  │  └────────────┘  │                                             │
│  └──────────────────┘                                             │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘
```

## Components

### 1. Google Apps Script (GAS)

**Location:** `gas-scripts/spotify-sync/`

**Files:**
- `Code.js` - Main entry point and OAuth flow
- `SpotifyConfig.js` - Configuration and state management
- `SpotifyClient.js` - Spotify API client
- `NotionSync.js` - Notion database operations

**Functions:**
| Function | Description | Trigger |
|----------|-------------|---------|
| `syncSpotifyToNotion()` | Main sync (saved tracks) | 5-minute time trigger |
| `syncRecentlyPlayed()` | Sync recently played | Manual or secondary trigger |
| `syncPlaylist(playlistId)` | Sync specific playlist | Manual |
| `setupTimeTrigger()` | Install 5-minute trigger | One-time setup |
| `removeTimeTrigger()` | Remove trigger | Manual |
| `getTriggerStatus()` | Check trigger status | Manual |
| `authorizeSpotify()` | OAuth flow | One-time setup |
| `fullSync()` | Complete library sync | Manual (WARNING: slow) |
| `testSpotifyConnection()` | Test connectivity | Manual |

**Deployment:**
```bash
# Navigate to GAS directory
cd gas-scripts/spotify-sync

# Deploy with clasp
clasp login
clasp push
clasp deploy

# Or deploy via Google Apps Script web UI
```

### 2. Local Cron Jobs

**Script:** `scripts/cron_music_sync.py`

**Cron Configuration:**
```bash
# Edit crontab
crontab -e

# Add these entries:
# Incremental sync every 5 minutes
*/5 * * * * /usr/bin/python3 /Users/brianhellemn/Projects/github-production/scripts/cron_music_sync.py --mode incremental >> /tmp/cron_music_sync.log 2>&1

# Full sync daily at 3am
0 3 * * * /usr/bin/python3 /Users/brianhellemn/Projects/github-production/scripts/cron_music_sync.py --mode full >> /tmp/cron_music_sync_full.log 2>&1
```

**Features:**
- Lock file to prevent concurrent runs
- State persistence between runs
- Webhook notifications to GAS
- Error recovery and logging

### 3. Webhook Server Integration

**Endpoint:** `webhook-server/gas_integration_endpoints.py`

**Routes:**
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/gas/trigger-sync` | POST | Trigger local sync from GAS |
| `/gas/webhook` | POST | Receive GAS notifications |
| `/gas/status` | GET | Get sync status |
| `/gas/config` | POST | Update configuration |
| `/gas/health` | GET | Health check |

**Integration with main server:**
```python
# In notion_event_subscription_webhook_server_v4_enhanced.py
from gas_integration_endpoints import gas_router
app.include_router(gas_router)
```

### 4. Notion Configuration Database

**Database ID:** `27ce7361-6c27-80fb-b40e-fefdd47d6640`

**Properties for Automation Management:**
- `Sync Enabled` (Checkbox) - Enable/disable auto-sync
- `Last Sync` (Date) - Last successful sync timestamp
- `Sync Interval` (Number) - Minutes between syncs
- `Sync Mode` (Select) - incremental/full/manual
- `GAS Trigger Active` (Checkbox) - GAS trigger status
- `Cron Active` (Checkbox) - Cron job status

## Setup Instructions

### Step 1: Deploy GAS Script

1. Open Google Apps Script at https://script.google.com
2. Create new project or use existing
3. Copy files from `gas-scripts/spotify-sync/`
4. Set Script Properties:
   - `SPOTIFY_CLIENT_ID`
   - `SPOTIFY_CLIENT_SECRET`
   - `NOTION_TOKEN`
   - `TRACKS_DB_ID`
5. Run `initializeSpotifySync()`
6. Run `authorizeSpotify()` and complete OAuth
7. Run `setupTimeTrigger()`

### Step 2: Configure Local Cron

```bash
# Make script executable
chmod +x /Users/brianhellemn/Projects/github-production/scripts/cron_music_sync.py

# Test run
python3 /Users/brianhellemn/Projects/github-production/scripts/cron_music_sync.py --mode incremental

# Add to crontab
crontab -e
# Add entries from above
```

### Step 3: Add Webhook Router

```python
# In your FastAPI app
from gas_integration_endpoints import gas_router
app.include_router(gas_router)
```

### Step 4: Start Webhook Server

```bash
# Start the webhook server
python3 webhook-server/notion_event_subscription_webhook_server_v4_enhanced.py
```

## Configuration Management

### Via Notion

Create a "Sync Configuration" database with:
- Automation name
- Trigger type (GAS/Cron/Webhook)
- Interval (minutes)
- Enabled status
- Last run timestamp
- Error count

### Via API

```bash
# Update config via webhook endpoint
curl -X POST http://localhost:5001/gas/config \
  -H "Content-Type: application/json" \
  -d '{"trigger_interval_minutes": 5, "enabled": true}'

# Check status
curl http://localhost:5001/gas/status
```

### Via GAS

```javascript
// In Google Apps Script
function updateConfig() {
  var result = initializeSpotifySync({
    triggerIntervalMinutes: 5,
    syncBatchSize: 50
  });
  Logger.log(result);
}
```

## Monitoring

### Logs

- **GAS:** View in Google Cloud Console (Stackdriver Logging)
- **Cron:** `/tmp/cron_music_sync.log`
- **Webhook:** `logs/webhook_server.log`

### Alerts

Configure notifications for:
- Sync failures
- Token expiration
- Rate limiting
- Connection errors

## Troubleshooting

### GAS Not Triggering

1. Check trigger exists: `getTriggerStatus()`
2. Verify OAuth: `testSpotifyConnection()`
3. Check execution logs in Google Apps Script

### Cron Not Running

1. Check crontab: `crontab -l`
2. Check logs: `tail -f /tmp/cron_music_sync.log`
3. Test manual run: `python3 scripts/cron_music_sync.py --mode incremental`

### Webhook Errors

1. Verify server running: `curl http://localhost:5001/gas/health`
2. Check firewall settings
3. Verify Cloudflare tunnel active

## Security

- **Spotify tokens:** Stored in GAS Script Properties (encrypted)
- **Notion tokens:** Environment variables
- **Webhook auth:** Consider adding API key validation
- **Lock files:** Prevent race conditions

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2026-01-30 | Initial release |

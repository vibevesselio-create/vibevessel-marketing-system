# Adobe Lightroom API Integration — Setup Guide

**Version:** 1.0.0
**Created:** 2026-01-18
**Author:** Claude Code Agent

This guide covers the complete setup process for the Adobe Lightroom API integration, which provides a hybrid Google Apps Script + Python implementation for syncing Lightroom assets to Notion.

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Adobe Console Configuration](#adobe-console-configuration)
3. [Python Backend Setup](#python-backend-setup)
4. [Google Apps Script Deployment](#google-apps-script-deployment)
5. [Notion Database Configuration](#notion-database-configuration)
6. [Testing the Integration](#testing-the-integration)
7. [Troubleshooting](#troubleshooting)

---

## Prerequisites

### Required Accounts & Access

- **Adobe Creative Cloud** account with Lightroom subscription
- **Adobe Developer Console** access
- **Google Account** with Apps Script access
- **Notion** workspace with API access

### Required Software

- Python 3.10+
- Node.js 18+ (for clasp)
- Git

### Required Dependencies (Python)

```bash
pip install httpx
```

---

## Adobe Console Configuration

### 1. Create Adobe Project

1. Go to [Adobe Developer Console](https://developer.adobe.com/console/)
2. Click **Create new project**
3. Name your project (e.g., "Lightroom-Notion-Sync")

### 2. Add Lightroom API

1. In your project, click **Add API**
2. Select **Lightroom Services** (LightroomPartnersSDK)
3. Select **OAuth 2.0** as the authentication type
4. Configure OAuth:
   - **Redirect URI**: Your GAS web app URL (see GAS Deployment section)
   - **Default scopes**:
     - `openid`
     - `lr_partner_apis`
     - `lr_partner_rendition_apis`

### 3. Save Credentials

After configuration, note these values:

| Property | Description |
|----------|-------------|
| Client ID | Public identifier for your app |
| Client Secret | **KEEP SECRET** - only use in Python backend |
| Organization ID | Your Adobe IMS Org ID |

**Example Configuration:**
```
Project ID: 4566206088345368374
Project Name: 456TealPeacock
Organization: brian-serenmedia.co (1C4B1E8067E590AF0A495F8A@AdobeOrg)
Client ID: 4b7ad02b266948b28123b46abdd900c0
```

---

## Python Backend Setup

The Python backend handles secure token exchange (with client_secret) and provides full API access.

### 1. Environment Variables

Create a `.env` file or set environment variables:

```bash
# Adobe OAuth (REQUIRED)
ADOBE_CLIENT_ID=your_client_id
ADOBE_CLIENT_SECRET=your_client_secret  # NEVER expose this!

# Notion API (REQUIRED for sync)
NOTION_TOKEN=your_notion_integration_token

# Optional: Pre-configured tokens
ADOBE_ACCESS_TOKEN=
ADOBE_REFRESH_TOKEN=
```

### 2. Module Location

The Python modules are located at:
```
/shared_core/integrations/adobe/
├── __init__.py
├── lightroom_oauth.py    # OAuth token handling
├── lightroom_client.py   # API client
└── lightroom_sync.py     # Notion sync
```

### 3. Basic Usage

```python
from shared_core.integrations.adobe import (
    AdobeLightroomOAuth,
    LightroomClient,
    LightroomNotionSync,
)

# Token exchange (call from your webhook server)
oauth = AdobeLightroomOAuth(
    client_id="your_client_id",
    client_secret="your_client_secret"
)

# Exchange authorization code for tokens
tokens = oauth.exchange_code(code, redirect_uri)
print(f"Access token: {tokens.access_token[:20]}...")

# API client usage
client = LightroomClient(
    access_token=tokens.access_token,
    client_id="your_client_id"
)

# Get catalog
catalog = client.get_catalog()
print(f"Catalog ID: {catalog['id']}")

# List assets
for asset in client.list_assets(catalog['id']):
    print(f"Asset: {asset.filename}")
```

### 4. Webhook Server Integration

Add these endpoints to your webhook server:

```python
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI()

class TokenExchangeRequest(BaseModel):
    code: str
    redirect_uri: str
    client_id: str

class TokenRefreshRequest(BaseModel):
    refresh_token: str
    client_id: str

oauth = AdobeLightroomOAuth()

@app.post("/api/adobe/token")
async def exchange_token(request: TokenExchangeRequest):
    if request.client_id != oauth.client_id:
        raise HTTPException(400, "Invalid client_id")
    tokens = oauth.exchange_code(request.code, request.redirect_uri)
    return tokens.to_dict()

@app.post("/api/adobe/refresh")
async def refresh_token(request: TokenRefreshRequest):
    if request.client_id != oauth.client_id:
        raise HTTPException(400, "Invalid client_id")
    tokens = oauth.refresh_token(request.refresh_token)
    return tokens.to_dict()
```

---

## Google Apps Script Deployment

### 1. Module Location

GAS modules are located at:
```
/gas-scripts/lightroom-api/
├── appsscript.json       # Manifest
├── Config.js             # Configuration
├── LightroomOAuth.js     # OAuth flow
├── LightroomClient.js    # API client
└── NotionSync.js         # Notion sync
```

### 2. Deploy with clasp

```bash
# Install clasp if not already installed
npm install -g @google/clasp

# Login to Google
clasp login

# Create new GAS project
cd /gas-scripts/lightroom-api
clasp create --title "Lightroom API Integration" --type webapp

# Push code
clasp push

# Deploy as web app
clasp deploy --description "v1.0.0"
```

### 3. Configure Script Properties

In the Apps Script editor, go to **Project Settings > Script Properties** and add:

| Property | Value | Description |
|----------|-------|-------------|
| ADOBE_CLIENT_ID | `your_client_id` | Adobe OAuth client ID |
| ADOBE_REDIRECT_URI | `your_webapp_url` | Your deployed web app URL |
| NOTION_TOKEN | `your_notion_token` | Notion integration token |
| TOKEN_EXCHANGE_ENDPOINT | `https://your-server/api/adobe/token` | Python backend URL |
| TOKEN_REFRESH_ENDPOINT | `https://your-server/api/adobe/refresh` | Python backend URL |
| PHOTOS_LIBRARY_DB_NAME | `Photos Library` | Target Notion database name |

### 4. Get Redirect URI

After deploying, your redirect URI will be:
```
https://script.google.com/macros/d/YOUR_SCRIPT_ID/exec
```

Add this to your Adobe Console OAuth configuration.

---

## Notion Database Configuration

### 1. Create Integration

1. Go to [Notion Integrations](https://www.notion.so/my-integrations)
2. Click **New integration**
3. Name it "Lightroom Sync"
4. Select your workspace
5. Copy the **Internal Integration Token**

### 2. Database Schema

Create or configure a "Photos Library" database with these properties:

| Property | Type | Description |
|----------|------|-------------|
| Name | Title | Asset filename |
| Lightroom-Asset-ID | Rich text | Unique asset identifier |
| File Type | Rich text | image/video |
| Original Filename | Rich text | Original filename |
| Import Date | Rich text | Import timestamp |
| Capture Date | Date | Photo capture date |
| Width | Number | Image width in pixels |
| Height | Number | Image height in pixels |
| Location | Rich text | GPS coordinates |
| Camera | Rich text | Camera make/model |
| Seren-Automation-Source | Rich text | Loop-guard property |
| Seren-Automation-Event-ID | Rich text | Loop-guard property |
| Seren-Automation-Node-ID | Rich text | Loop-guard property |

### 3. Share with Integration

1. Open your database in Notion
2. Click **...** > **Connect to** > Select your integration

---

## Testing the Integration

### 1. Test OAuth Flow

```bash
# Open authorization URL in browser
python -c "
from shared_core.integrations.adobe import AdobeLightroomOAuth
oauth = AdobeLightroomOAuth()
print(oauth.get_authorization_url('YOUR_REDIRECT_URI'))
"
```

### 2. Test API Access

```python
from shared_core.integrations.adobe import LightroomClient

client = LightroomClient()

# Test account access
account = client.get_account()
print(f"Account: {account}")

# Test catalog access
catalog = client.get_catalog()
print(f"Catalog ID: {catalog['id']}")
```

### 3. Test Notion Sync

```python
from shared_core.integrations.adobe import LightroomClient, LightroomNotionSync

client = LightroomClient()
sync = LightroomNotionSync(
    lightroom_client=client,
    database_name="Photos Library"
)

# Dry run first
result = sync.sync_assets(dry_run=True, limit=5)
print(result.message)

# Actual sync (limited)
result = sync.sync_assets(limit=5)
print(result.message)
```

### 4. Test GAS Functions

In the Apps Script editor, run:

1. `validateLightroomConfig()` - Check configuration
2. `testGetAuthorizationUrl()` - Get OAuth URL
3. `testSyncDryRun()` - Test sync without changes
4. `testSyncLimited()` - Sync 5 assets

---

## Troubleshooting

### OAuth Errors

| Error | Cause | Solution |
|-------|-------|----------|
| `invalid_client` | Wrong client_id | Verify client_id matches Adobe Console |
| `invalid_grant` | Code expired | Authorization codes expire in 5 minutes |
| `unauthorized_client` | Wrong redirect_uri | Ensure redirect_uri matches exactly |

### API Errors

| Error | Cause | Solution |
|-------|-------|----------|
| `401 Unauthorized` | Token expired | Refresh the access token |
| `403 Forbidden` | Insufficient scopes | Add required scopes in Adobe Console |
| `429 Too Many Requests` | Rate limited | Wait for retry-after period |

### Notion Errors

| Error | Cause | Solution |
|-------|-------|----------|
| `Database not found` | Wrong name or not shared | Share database with integration |
| `Property not found` | Missing property | Create the property manually |

### Common Issues

1. **Token Exchange Fails**
   - Ensure Python backend is running
   - Verify TOKEN_EXCHANGE_ENDPOINT is correct
   - Check client_secret is set in environment

2. **Sync Creates Duplicates**
   - Ensure "Lightroom-Asset-ID" property exists
   - Property must be exact match (case-sensitive)

3. **Loop Detection Triggers**
   - Loop-guard properties are working correctly
   - Webhook server should ignore events from "GAS-Lightroom-Sync" or "Python-Lightroom-Sync"

---

## Related Documentation

- [Adobe Lightroom API Documentation](https://developer.adobe.com/lightroom/lightroom-api-docs/)
- [Notion API Documentation](https://developers.notion.com/)
- [Agent Coordination Protocol](https://www.notion.so/2e933d7a491b81f8a5dec0d125c33d4c)
- [Control Plane Architecture](https://www.notion.so/2e933d7a491b8189b3b5e54083d800fb)

---

*Document created by Claude Code Agent — 2026-01-18*

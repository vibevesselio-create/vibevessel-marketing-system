# HANDOFF: Execute Cross-Workspace Database Sync — Critical Blockers Resolution

**Trigger Type**: Critical Blocker Resolution + Validation
**Priority**: Urgent
**Created By**: Claude Cowork Agent (Opus 4.5)
**Created Date**: 2026-01-19
**Linear Issue**: VV-7 (In Progress)

---

## Preconditions (MUST be true before executing)

### Verify Gap Analysis Document Exists
- Location: `/Users/brianhellemn/Projects/github-production/../Cross-Workspace-Database-Sync-Gap-Analysis-Remediation-Plan.md`
- Alternative: Check parent `Projects/` folder for the markdown file

### Verify DriveSheetsSync Codebase Ready
- Confirm git status shows commits ahead of origin in `gas-scripts/drive-sheets-sync/`
- Confirm `Code.js` contains inter-workspace token routing functions

### Verify Network Access
- Cloudflare tunnel operational: `curl https://webhook.vibevessel.space/health`
- Google Cloud Console accessible for OAuth credentials

---

## Context (Current State)

The Cross-Workspace Database Synchronization project is **70% complete** with 4 critical blockers preventing production deployment:

| Gap ID | Description | Severity |
|--------|-------------|----------|
| GAP-001 | DriveSheetsSync v2.5 not deployed to Apps Script | CRITICAL |
| GAP-002 | Workspace tokens not configured in Apps Script properties | CRITICAL |
| GAP-003 | Google OAuth client secrets file empty (0 bytes) | CRITICAL |
| GAP-004 | Slack webhook URL not configured in LaunchAgent | CRITICAL |

### Components Ready (No Action Needed)
- Notion Event Subscription Webhook Server v4 — Operational at `https://webhook.vibevessel.space/webhook`
- DriveSheetsSync Phase 1 core functions — Implemented and tested locally
- Inter-workspace token routing code — Complete in `Code.js`
- CSV logging for webhooks — Fixed and operational

---

## Execution Objectives

### Phase A: Deploy DriveSheetsSync to Apps Script (GAP-001)

**Step A1: Push code to Apps Script**
```bash
cd /Users/brianhellemn/Projects/github-production/gas-scripts/drive-sheets-sync
npx clasp push
```

**Verification:**
- Open Apps Script editor: `npx clasp open`
- Confirm `Code.js` contains:
  - `setupWorkspaceToken()` function
  - `testInterWorkspaceSync()` function
  - `CLIENT_TO_WORKSPACE_TOKEN_PROP` mapping
  - `syncWorkspaceDatabasesRow_()` function

---

### Phase B: Configure Workspace Tokens (GAP-002)

**Step B1: Create Notion integrations** (if not already created)
For each workspace, create an internal integration at https://www.notion.so/my-integrations:
- Seren Media Internal workspace
- VibeVessel workspace
- Ocean Frontiers workspace (token exists in `/clients/.env.ocean-frontiers-compass-point`)

**Step B2: Configure tokens in Apps Script**
In Apps Script editor (https://script.google.com), run these in the execution log:

```javascript
// Seren Media Internal
setupWorkspaceToken('seren-media-internal', 'secret_REPLACE_WITH_ACTUAL_TOKEN');

// VibeVessel
setupWorkspaceToken('vibe-vessel', 'secret_REPLACE_WITH_ACTUAL_TOKEN');

// Ocean Frontiers (from .env file)
setupWorkspaceToken('ocean-frontiers', 'ntn_541874813768A5mH...');  // Get full token from .env
```

**Step B3: Validate configuration**
```javascript
testInterWorkspaceSync();
```

**Expected Output:**
```
=== Inter-Workspace Sync Configuration Test ===
Token Configuration:
  SEREN_INTERNAL_WORKSPACE_TOKEN: ✓ Set
  VIBEVESSEL_WORKSPACE_TOKEN: ✓ Set
  OCEAN_FRONTIERS_WORKSPACE_TOKEN: ✓ Set

API Connectivity Tests:
  Seren Media Internal: ✓ Connected (user: ...)
  VibeVessel: ✓ Connected (user: ...)
  Ocean Frontiers: ✓ Connected (user: ...)

Client Context Routing Table:
  ...
```

---

### Phase C: Fix Google OAuth Credentials (GAP-003)

**Step C1: Access Google Cloud Console**
- URL: https://console.cloud.google.com/apis/credentials?project=797362328200
- Navigate to OAuth 2.0 Client IDs

**Step C2: Download credentials**
- Find client: `797362328200-9cro3bms23fse7hgqh2es4sk35hl4jln.apps.googleusercontent.com`
- Click download (JSON format)

**Step C3: Save to correct location**
```bash
# Target path (currently empty):
/Users/brianhellemn/Projects/github-production/credentials/google-oauth/VibeVessel/client_secret_2_797362328200-9cro3bms23fse7hgqh2es4sk35hl4jln.apps.googleusercontent.com.json
```

**Verification:**
```bash
cat /Users/brianhellemn/Projects/github-production/credentials/google-oauth/VibeVessel/client_secret_*.json | jq .client_id
# Should output: "797362328200-9cro3bms23fse7hgqh2es4sk35hl4jln.apps.googleusercontent.com"
```

---

### Phase D: Configure Slack Webhook (GAP-004)

**Step D1: Create Slack incoming webhook**
- URL: https://api.slack.com/apps
- Select or create app for Seren Media workspace
- Add incoming webhook to target channel (e.g., #automation-alerts)

**Step D2: Update LaunchAgent**
Edit: `~/Library/LaunchAgents/com.seren.webhook-server.plist`

Add to `<dict>` under `EnvironmentVariables`:
```xml
<key>SLACK_WEBHOOK_URL</key>
<string>https://hooks.slack.com/services/T.../B.../xxx</string>
```

**Step D3: Reload LaunchAgent**
```bash
launchctl unload ~/Library/LaunchAgents/com.seren.webhook-server.plist
launchctl load ~/Library/LaunchAgents/com.seren.webhook-server.plist
```

**Verification:**
```bash
# Check server is running
curl http://localhost:5001/health

# Check logs for Slack initialization
tail -20 /Users/brianhellemn/Library/Logs/webhook-server.log | grep -i slack
```

---

### Phase E: End-to-End Validation

**Step E1: Test cross-workspace sync**
In Apps Script editor, run:
```javascript
function testCrossWorkspaceSync() {
  const UL = initUnifiedLogger_();

  // Get a test row from workspace-databases registry
  const testRow = {
    'Data Source ID': 'test-datasource-id-' + Date.now(),
    'Database Name': 'Test Database',
    'Workspace': 'seren-media-internal'
  };

  // Attempt sync to VibeVessel workspace
  const result = syncWorkspaceDatabasesRow_(
    testRow,
    'TARGET_WORKSPACE_DATABASES_REGISTRY_ID',  // Replace with actual ID
    { idMappings: {} },
    UL
  );

  UL.info('Sync result', result);
  UL.flush();
  return result;
}
```

**Step E2: Verify webhook flow**
1. Make a test edit in a monitored Notion database
2. Check webhook server logs: `tail -f ~/Library/Logs/webhook-server.log`
3. Verify CSV logging in Google Drive: `Seren Internal/Automation Files/Notion-Database-Webhooks/`

**Step E3: Verify Slack notification**
Trigger a test notification via webhook server or manual test endpoint.

---

## Required Deliverables

1. **Execution Log** saved to:
   - `reports/CROSS_WORKSPACE_SYNC_EXECUTION_LOG_20260119.md`

2. **Updated Linear Issues**:
   - VV-22: Mark as Done (Push DriveSheetsSync changes)
   - VV-23: Mark as Done (Configure workspace tokens)
   - VV-7: Update with completion status

3. **Validation Evidence**:
   - Screenshot or log output of `testInterWorkspaceSync()` passing
   - Confirmation of OAuth credentials file populated
   - Confirmation of Slack webhook test message received

4. **Blockers Encountered** (if any):
   - Document any issues preventing completion
   - Create new Linear issues for discovered blockers

---

## Completion Criteria

- [ ] DriveSheetsSync v2.5 deployed to Apps Script (verified in editor)
- [ ] All 3 workspace tokens configured and connectivity verified
- [ ] Google OAuth credentials file populated (non-zero bytes, valid JSON)
- [ ] Slack webhook configured and test notification sent
- [ ] `testInterWorkspaceSync()` returns all green checks
- [ ] Cross-workspace sync test completes successfully
- [ ] Linear issues VV-22 and VV-23 marked as Done

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Notion integration permissions insufficient | Request all content capabilities when creating integration |
| clasp authentication expired | Run `npx clasp login` to re-authenticate |
| Apps Script quota exceeded | Wait 24 hours or use different Google account |
| Webhook server crash on reload | Check error logs, verify PYTHONPATH in plist |

---

## Related Resources

- Gap Analysis Document: `Projects/Cross-Workspace-Database-Sync-Gap-Analysis-Remediation-Plan.md`
- Webhook Server Implementation: `/services/webhook_server/IMPLEMENTATION_SUMMARY.md`
- Phase 1 Completion Summary: `/CROSS_WORKSPACE_SYNC_PHASE1_COMPLETION_SUMMARY.md`
- Linear Project: https://linear.app/vibevessel/issue/VV-7

---

**Handoff Created**: 2026-01-19T19:15:00Z
**Source Agent**: Claude Cowork Agent (Opus 4.5)
**Target Agent**: Claude Code Agent
**Estimated Effort**: 2-3 hours

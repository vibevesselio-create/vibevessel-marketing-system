# Codebase Audit Findings
**Date:** 2026-01-19
**Agent:** Claude Cowork Agent
**Status:** COMPLETE

---

## Token Inventory

### Configured Notion Tokens

| Token Property | Status | Value (first 20 chars) | Workspace |
|---------------|--------|------------------------|-----------|
| NOTION_TOKEN | ✅ Configured | `ntn_620653066639QWYs...` | **Archive Workspace** (PHASING OUT) |
| NOTION_API_KEY | ✅ Configured | `ntn_620653066639QWYs...` | **Archive Workspace** (PHASING OUT) |
| ARCHIVE_WORKSPACE_TOKEN | ✅ Configured | `ntn_61904180510aqzPe...` | Secondary/Backup |
| VIBEVESSEL_WORKSPACE_TOKEN | ❌ NOT Configured | - | VibeVessel |
| SEREN_INTERNAL_WORKSPACE_TOKEN | ❌ NOT Configured | - | Seren Media Internal (NEW PRIMARY) |

**IMPORTANT:** The current NOTION_TOKEN points to the Archive Workspace which is being phased out.
The system needs to migrate to client-specific workspace tokens.

### Client-Specific Tokens (from `clients/` directory)

| Client | Token Status | Notes |
|--------|-------------|-------|
| Ocean Frontiers | ✅ Has own token | `ntn_541874813768A5mH...` |
| Mandy Cavanaugh | ✅ Has own token | `ntn_620653066639pqvZ...` |
| VibeVessel | ❌ NO NOTION TOKEN | Only has Google OAuth config |
| Boats & Coves | ⚠️ Unknown | Needs verification |
| Eagle Rays | ⚠️ Unknown | Needs verification |

---

## DriveSheetsSync Configuration

### Current Token Routing (Code.js lines 461-464)
```javascript
const CLIENT_TO_WORKSPACE_TOKEN_PROP = {
  'seren-media-internal': 'NOTION_TOKEN',           // ✅ Configured
  'vibe-vessel': 'VIBEVESSEL_WORKSPACE_TOKEN',      // ❌ NOT Configured
  'ocean-frontiers': 'NOTION_TOKEN'                 // ✅ Uses primary
};
```

### Findings

1. **ARCHIVE_WORKSPACE_TOKEN IS CONFIGURED** (.env line 67)
   - Token: `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`
   - This was NOT being used in the code until inter-workspace sync was added

2. **VIBEVESSEL_WORKSPACE_TOKEN IS NOT CONFIGURED**
   - Not in .env
   - Not in clients/.env.vibevessel
   - Needs to be created in VibeVessel Notion workspace

3. **Ocean Frontiers uses primary NOTION_TOKEN**
   - Despite having its own token in clients/.env.ocean-frontiers-compass-point
   - Code maps ocean-frontiers → NOTION_TOKEN (not its own token)

---

## Required Actions

### Already Done (by this session)
1. ✅ Added inter-workspace token routing to `notionFetch_()`
2. ✅ Added `setupWorkspaceToken()` helper
3. ✅ Added `testInterWorkspaceSync()` diagnostic
4. ✅ Code supports `ARCHIVE_WORKSPACE_TOKEN` (already in .env)

### Still Needed (Human Action)
1. **Create VibeVessel Notion Integration**
   - Go to VibeVessel Notion workspace
   - Create internal integration
   - Copy token

2. **Add Token to Apps Script**
   ```javascript
   // In Apps Script console:
   setupWorkspaceToken('vibe-vessel', 'secret_YOUR_VIBEVESSEL_TOKEN')
   ```

3. **Push Code to Apps Script**
   ```bash
   cd gas-scripts/drive-sheets-sync
   clasp push
   ```

4. **Test Configuration**
   ```javascript
   // In Apps Script console:
   testInterWorkspaceSync()
   ```

---

## Corrected Task Status

Based on audit findings, updating pending tasks:

| Task | Original Status | Corrected Status | Notes |
|------|----------------|------------------|-------|
| notionFetch_() workspace routing | Done | ✅ Done | Code complete |
| setupWorkspaceToken() helper | Done | ✅ Done | Code complete |
| testInterWorkspaceSync() diagnostic | Done | ✅ Done | Code complete |
| Configure VibeVessel token | To Do | ⚠️ Still To Do | Token doesn't exist |
| Push to Apps Script | To Do | ⚠️ Still To Do | Human action required |

---

## Database ID Inventory

### From .env
- `ARTISTS_DB_ID`: 20ee73616c27816d9817d4348f6de07c
- `MUSIC_PLAYLISTS_DB_ID`: 20ee7361-6c27-819c-b0b3-e691f104d5e6
- `PLAYLISTS_DB_ID`: 27ce73616c27803fb957eadbd479f39a
- `TRACKS_DB_ID`: 27ce7361-6c27-80fb-b40e-fefdd47d6640
- `SCRIPT_RUN_LOGS_DB_ID`: 27be7361-6c27-8033-a323-dca0fafa80e6
- `FOLDERS_DATABASE_ID`: 26ce7361-6c27-81bb-81b7-dd43760ee6cc
- `VOLUMES_DATABASE_ID`: 26ce7361-6c27-8148-8719-fbd26a627d17

### From clients/.env.vibevessel
- `CLIENT_DB_PARENT_PAGE_ID`: 238e73616c278147ae8ce48b315fe2e4

---

## Summary

The inter-workspace sync code is complete and ready. The only missing piece is the **VibeVessel workspace Notion token**, which must be created by a human in the VibeVessel Notion workspace settings.

The ARCHIVE_WORKSPACE_TOKEN was already configured in .env but wasn't being used until this session's code changes enabled inter-workspace routing.

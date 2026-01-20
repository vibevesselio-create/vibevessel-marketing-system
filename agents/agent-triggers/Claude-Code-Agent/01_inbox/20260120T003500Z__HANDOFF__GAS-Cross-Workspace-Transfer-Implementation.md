# HANDOFF TASK: Google Apps Script Cross-Workspace Database Transfer Implementation

**Timestamp:** 2026-01-20T00:35:00Z  
**Source Agent:** Cursor MM1 Agent  
**Priority:** CRITICAL  
**Target Agent:** Claude Code Agent  

---

## Executive Summary

Create a new Google Apps Script project that implements cross-workspace Notion database transfer functionality. This is a port of the Python implementation in `scripts/cross_workspace_sync.py` to Google Apps Script, enabling the workflow to run from Google's infrastructure.

---

## Task Description

### Primary Objective

Create a new Google Apps Script project called `notion-cross-workspace-transfer` that:

1. **Transfers databases** from one Notion workspace to another
2. **Recreates relation properties** pointing to equivalent databases in the target workspace
3. **Maps page IDs** from source to target for relation value resolution
4. **Implements usage-driven property creation** - only creates properties that have actual values in source items
5. **Self-corrects schemas** - removes unused properties from target databases
6. **Copies page content blocks** in addition to properties

### Key Features to Implement

1. **CrossWorkspaceTransfer Class/Module**
   - `transferDatabase(sourceDbId, targetToken, targetParentPageId, options)`
   - `findOrCreateTargetDatabase(sourceDbId, sourceName)`
   - `queryAllItems(dbId, headers, maxItems)`
   - `copyPropertyValue(propName, propValue, targetProps)`
   - `copyBlocksToPage(sourcePageId, targetPageId)`

2. **Usage-Driven Property Analysis**
   - Scan all source items to identify populated properties
   - Only create properties in target that have actual values
   - Remove unused properties from target schema

3. **Two-Pass Transfer Algorithm**
   - Pass 1: Create all items without relations (build page ID map)
   - Pass 2: Update relation properties using the mapped IDs

4. **Token Management**
   - Support multiple workspace tokens
   - Store tokens in Script Properties
   - Token registry for known workspaces

5. **Error Handling & Logging**
   - Comprehensive logging with timestamps
   - Error collection and summary
   - Rate limiting handling for Notion API

---

## Reference Implementation

The Python implementation is in `scripts/cross_workspace_sync.py`. Key sections:

### CrossWorkspaceTransfer Class (lines 198-808)
```python
class CrossWorkspaceTransfer:
    """
    Handles one-way transfer/relocation of databases between workspaces.
    
    Unlike sync, this:
    - Recreates relation properties pointing to equivalent databases in target workspace
    - Creates related databases if they don't exist (recursive create-if-not-found)
    - Maps source page IDs to target page IDs for relation values
    - Transfers all items with their full content
    """
```

### Key Methods to Port
- `_find_or_create_target_database()` - Find by name or create with minimal schema
- `_query_all_items()` - Paginated database query
- `_copy_property_value()` - Property value conversion with relation mapping
- `_copy_blocks_to_page()` - Block content transfer
- `transfer_database()` - Main orchestration with usage analysis

### Property Types to Support
- title, rich_text, number, select, multi_select
- date, checkbox, url, email, phone_number
- files (external only), status, relation

### Property Types to Skip
- created_by, last_edited_by, created_time, last_edited_time
- formula, unique_id, rollup

---

## GAS Project Structure

Create the project with this file structure:

```
gas-scripts/notion-cross-workspace-transfer/
├── appsscript.json       # Project manifest
├── Config.js             # Configuration and token management
├── NotionClient.js       # Notion API wrapper
├── PropertyUtils.js      # Property value handling utilities
├── BlockUtils.js         # Block content utilities
├── TransferEngine.js     # Main transfer logic
├── Code.js               # Entry points and menu functions
└── README.md             # Usage documentation
```

---

## Token Configuration

Use Script Properties for token storage:

```javascript
// Config.js
const CONFIG = {
  WORKSPACES: {
    'seren-internal': {
      name: 'Seren Media Internal',
      tokenKey: 'SEREN_NOTION_TOKEN'
    },
    'vibevessel-client': {
      name: 'VibeVessel Client Workspace',
      tokenKey: 'VIBEVESSEL_CLIENT_TOKEN',
      parentPageId: '2cf33d7a-491b-806d-8ac7-f401ddde95f9'
    }
  }
};

function getToken(workspaceKey) {
  const props = PropertiesService.getScriptProperties();
  const workspace = CONFIG.WORKSPACES[workspaceKey];
  return props.getProperty(workspace.tokenKey);
}
```

---

## GAS API Module Integration

The project should be deployable via the existing GAS API module at `shared_core/gas/gas_deployment.py`.

### Fix Any Issues with the Module

If the GAS API module has issues preventing deployment, fix them:

1. Check `shared_core/gas/gas_deployment.py` for any bugs
2. Verify OAuth credentials are properly configured
3. Test API availability and fallback to clasp if needed
4. Document any fixes made

---

## Success Criteria

1. **New GAS project created** at `gas-scripts/notion-cross-workspace-transfer/`
2. **All core transfer functions implemented** and tested
3. **Usage-driven property creation** working correctly
4. **Relation mapping** functional with two-pass algorithm
5. **Block content** transferred correctly
6. **Error handling** comprehensive with clear logging
7. **GAS API module** working or issues documented and fixed
8. **Deployed successfully** to Google Apps Script
9. **Test transfer** of a small database completed successfully

---

## Token Configuration (for testing)

Tokens are stored in environment variables (see `.env` file):
- **Seren Internal:** `NOTION_TOKEN`
- **VibeVessel Client:** `NOTION_VIBEVESSELCLIENT_TOKEN`
  - Parent Page: `2cf33d7a-491b-806d-8ac7-f401ddde95f9`

**SECURITY NOTE:** Never hardcode tokens in source files. Use environment variables or token_manager.

---

## Blocking Issues to Address

1. **GAS API Module** - Has been returning 404 errors. Diagnose and fix.
2. **OAuth Flow** - Ensure credentials are properly configured for API access.
3. **Rate Limiting** - Implement exponential backoff for Notion API calls.

---

## Return Handoff Requirements

When complete, create a return handoff to Cursor MM1 Agent with:
1. Summary of implementation
2. Any issues encountered and how they were resolved
3. Test results
4. Script ID for the deployed project
5. Instructions for running transfers

---

## References

- `scripts/cross_workspace_sync.py` - Python reference implementation
- `shared_core/gas/gas_deployment.py` - GAS deployment module
- `docs/CROSS_WORKSPACE_TOKEN_REGISTRY.md` - Token documentation
- `gas-scripts/drive-sheets-sync/` - Example GAS project structure

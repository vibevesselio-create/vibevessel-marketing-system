# DEPLOY DRIVESHEETSSYNC NOW

## Option 1: Using clasp (Recommended)
```bash
cd gas-scripts/drive-sheets-sync
clasp push
```

## Option 2: Using Apps Script API
```bash
python3 scripts/execute_gas_api_deployment.py --project gas-scripts/drive-sheets-sync
```

## Option 3: Manual in Apps Script Editor
1. Go to https://script.google.com/d/1n8vraQ0Rrfbeor7c3seWv2dh8saRVAJBJzgKm0oVQzgJrp5E1dLrAGf-/edit
2. Copy contents of `gas-scripts/drive-sheets-sync/Code.js`
3. Paste into Code.gs
4. Save

---

## After Deployment: Configure Tokens

Run in Apps Script console:
```javascript
// Test current configuration
testInterWorkspaceSync()

// Configure tokens (only if not already set)
setupWorkspaceToken('seren-media-internal', 'YOUR_SEREN_INTERNAL_TOKEN')
setupWorkspaceToken('vibe-vessel', 'YOUR_VIBEVESSEL_TOKEN')
setupWorkspaceToken('ocean-frontiers', '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')
```

---

## Changes Being Deployed

1. **Inter-workspace token routing** in `notionFetch_()`
2. **setupWorkspaceToken()** helper function
3. **testInterWorkspaceSync()** diagnostic function
4. **Corrected client-to-token mappings**:
   - seren-media-internal → SEREN_INTERNAL_WORKSPACE_TOKEN
   - vibe-vessel → VIBEVESSEL_WORKSPACE_TOKEN
   - ocean-frontiers → OCEAN_FRONTIERS_WORKSPACE_TOKEN
   - archive → NOTION_TOKEN (legacy)

---

## Git Commits Ready to Push

```bash
git push origin main
```

15 commits ahead of origin including:
- Dynamic discovery for Folders/Clients/database-parent-page
- Inter-workspace database synchronization support
- Corrected workspace token mappings
- Audit findings documentation

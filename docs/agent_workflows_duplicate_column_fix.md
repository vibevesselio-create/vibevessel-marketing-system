# Agent-Workflows Duplicate Column Fix

## Issue Summary
The Agent-Workflows database has duplicate 'Sub-workflows' column definitions:
- **'Sub-workflows'** (relation property) - ✅ KEEP
- **'sub-workflows'** (rich_text property) - ❌ REMOVE

This duplicate is blocking all SQL queries via the query-data-sources tool.

## Database Details
- **Database ID:** `259e7361-6c27-8192-ae2e-e6d54b4198e1`
- **Database Name:** Agent-Workflows
- **Issue ID:** `14df06ea-a01d-4082-b255-801486cdeb9e`

## Root Cause
The database schema has two properties with similar names but different types:
1. `Sub-workflows` (relation) - Correct property for linking to child workflows
2. `sub-workflows` (rich_text) - Duplicate text property that should be removed

When Notion exports to SQLite for query-data-sources, both properties map to columns, causing conflicts.

## Solution Steps

### Step 1: Access Agent-Workflows Database
1. Open Notion and navigate to the Agent-Workflows database
2. Database URL: https://www.notion.so/259e73616c278192ae2ee6d54b4198e1

### Step 2: Identify the Duplicate Property
1. Click on the database view
2. Look for the property column named **'sub-workflows'** (lowercase, rich_text type)
3. Verify there is also a property named **'Sub-workflows'** (capitalized, relation type)

### Step 3: Remove the Duplicate Property
1. Click on the **'sub-workflows'** column header
2. Select **"Delete property"** from the dropdown menu
3. Confirm deletion
4. **IMPORTANT:** Do NOT delete the **'Sub-workflows'** (capitalized, relation) property

### Step 4: Verify the Fix
Run the verification script:
```bash
python3 scripts/check_agent_workflows_schema.py
```

Expected output:
- Should show only 1 Sub-workflows property (the relation property)
- No duplicates detected

### Step 5: Test SQL Queries
After removal, test that SQL queries work:
```bash
# Use query-data-sources tool or Notion API to verify
# SQL queries should now work without column conflicts
```

## Verification Script
The script `scripts/check_agent_workflows_schema.py` can be used to:
1. Check current schema state
2. Verify duplicates are removed
3. Generate findings report

## Impact
- **Before Fix:** All SQL queries via query-data-sources tool fail
- **After Fix:** SQL queries work normally, enabling:
  - Automated data migration workflows
  - Analytics and reporting
  - Compliance validation

## Notes
- Schema changes cannot be done via Notion API - requires Notion UI access
- The relation property 'Sub-workflows' is the correct one to keep
- The text property 'sub-workflows' appears to be unused/unnecessary

## Related Files
- Issue: `current_critical_issue.json`
- Schema Findings: `agent_workflows_schema_findings.json`
- Verification Script: `scripts/check_agent_workflows_schema.py`

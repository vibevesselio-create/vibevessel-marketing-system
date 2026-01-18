# Execute Production Workflow - DriveSheetsSync

**Date:** 2026-01-18  
**Action:** Execute `manualRunDriveSheets()` in production

---

## ⚠️ PRODUCTION EXECUTION

This will execute the **REAL** DriveSheetsSync workflow that:
- ✅ Processes real Notion databases
- ✅ Creates/updates real Google Drive folders
- ✅ Makes real updates to Notion
- ✅ Syncs real data between Drive and Notion

---

## Execution Steps

### Step 1: Deploy Latest Code (if needed)

```bash
cd /Users/brianhellemn/Projects/github-production/gas-scripts/drive-sheets-sync
clasp push
```

### Step 2: Execute Production Workflow

**In Apps Script Editor:**

1. Open: https://script.google.com
2. Select your DriveSheetsSync project
3. Run function: `manualRunDriveSheets`
4. Click "Run" button

**OR via clasp:**

```bash
clasp run manualRunDriveSheets
```

---

## What Will Happen

1. **Lock Acquisition** - Script acquires lock to prevent concurrent runs
2. **Archive Audit** - Checks/creates archive folders
3. **Two-Way Sync** - Processes all databases:
   - Reads from Notion databases
   - Creates/updates Google Drive folders
   - Syncs CSV files
   - Updates Notion with sync status
4. **Lock Release** - Releases lock when complete

---

## Monitor Execution

### Check Execution Logs

1. Open Apps Script execution transcript
2. Watch for:
   - `🔒 Attempting to obtain DriveSheets script lock`
   - `🚀 Initiating two-way sync workflow`
   - `✅ Sync workflow completed successfully`
   - Or any errors

### Check Google Drive

- Verify folders are created/updated
- Check for any new duplicate folders (should be zero)

### Check Notion

- Verify database updates
- Check sync status properties
- Review any log entries

---

## Expected Duration

- Small sync: 1-5 minutes
- Medium sync: 5-15 minutes
- Large sync: 15-30 minutes

---

## If Errors Occur

1. **Check execution logs** for error details
2. **Verify script properties** are configured:
   - `NOTION_API_KEY`
   - `WORKSPACE_DATABASES_FOLDER_ID`
   - Other required properties
3. **Check permissions** - Script needs Drive and Notion access
4. **Review error messages** - Fix issues and retry

---

## Post-Execution Verification

- [ ] Execution completed successfully
- [ ] No errors in logs
- [ ] Folders created/updated correctly
- [ ] No duplicate folders created
- [ ] Notion databases updated
- [ ] Sync status reflects completion

---

**Ready to execute:** `manualRunDriveSheets()`

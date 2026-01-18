# DriveSheetsSync Monitoring Guide

**Date:** January 6, 2026  
**Purpose:** Guide for monitoring production runs after fixes and improvements

---

## Monitoring Checklist

### 1. Archive Folders Audit

**How to Run:**
```javascript
// From Apps Script editor
runArchiveFoldersAudit();

// Or via clasp
clasp run runArchiveFoldersAudit
```

**What to Monitor:**
- Number of folders scanned
- Number of missing archive folders
- Number of archive folders created
- Any errors during creation

**Expected Results:**
- All database folders should have `.archive` subfolders
- Missing archives should be created automatically
- No errors should occur

**Action Items:**
- If errors occur, check folder permissions
- If many missing archives found, investigate root cause
- Document any persistent issues

---

### 2. Database Query Errors

**What to Monitor:**
- Check execution logs for "Cannot query database - data_source_id not available" warnings
- Verify queries are using `data_sources` API exclusively
- Check for any "Invalid request URL" errors

**Expected Behavior:**
- Queries should use `data_sources/${dsId}/query` format
- Warnings should appear when `data_source_id` unavailable (graceful degradation)
- No fallback to legacy `databases` endpoint

**Action Items:**
- If warnings appear frequently, investigate database accessibility
- Verify all databases are shared with Notion integration
- Check `resolveDatabaseToDataSourceId_` function is working correctly

---

### 3. Property Matching

**What to Monitor:**
- Check execution logs for property matching reports
- Verify exact matches are working (should be Strategy 1)
- Monitor for "Some properties could not be matched" warnings

**Expected Behavior:**
- Exact matches should succeed immediately (Strategy 1)
- Fallback strategies should only be used when exact match fails
- Warnings should be logged for unmatched properties

**Action Items:**
- If many properties fail to match, review property names
- Verify database schemas are up to date
- Check property matching logic if issues persist

---

### 4. Error Handling

**What to Monitor:**
- Check for graceful degradation (script continues when optional features fail)
- Verify error messages are clear and actionable
- Monitor for any fatal errors that stop execution

**Expected Behavior:**
- Script should continue execution when optional features fail
- Clear error messages with context
- No silent failures

**Action Items:**
- Review error logs for patterns
- Address any recurring errors
- Improve error handling if needed

---

## Execution Log Review

### Key Log Messages to Watch For:

1. **Archive Audit:**
   ```
   [INFO] Archive folder audit complete
   ```

2. **Database Queries:**
   ```
   [WARN] Cannot query database - data_source_id not available
   ```

3. **Property Matching:**
   ```
   [DEBUG] Property matching report
   [WARN] Some properties could not be matched
   ```

4. **API Usage:**
   ```
   [INFO] Resolved data_source_id from database
   [DEBUG] Input is already a data_source_id
   ```

---

## Production Run Monitoring

### Daily Checks:
1. Review execution logs in Notion Execution-Logs database
2. Check Drive log files for errors
3. Verify archive folders audit runs successfully
4. Monitor database query success rates

### Weekly Reviews:
1. Analyze error patterns
2. Review property matching success rates
3. Check for any recurring issues
4. Update documentation as needed

### Monthly Audits:
1. Run full diagnostic suite
2. Review all outstanding issues
3. Plan improvements
4. Update monitoring procedures

---

## Troubleshooting

### Issue: Archive folders not being created
**Check:**
- `WORKSPACE_DATABASES_FOLDER_ID` is set correctly
- Folder permissions allow creation
- Archive audit is enabled (`ENABLE_ARCHIVE_AUDIT` not set to false)

### Issue: Database queries failing
**Check:**
- Database IDs are correct in CONFIG
- Databases are shared with Notion integration
- `data_source_id` resolution is working
- Notion API token is valid

### Issue: Properties not matching
**Check:**
- Property names match exactly (case-sensitive)
- Database schema is up to date
- Property types are correct
- Review property matching logs for details

---

## Success Metrics

### Target Metrics:
- ✅ Archive folders: 100% coverage
- ✅ Database queries: <1% failure rate
- ✅ Property matching: >95% success rate
- ✅ Error handling: 0 fatal errors

### Monitoring Tools:
- Notion Execution-Logs database
- Drive log files (.jsonl and .log)
- Apps Script execution logs
- Diagnostic functions

---

## Reporting

### Weekly Status Report Should Include:
1. Number of execution runs
2. Error count and types
3. Archive folders audit results
4. Database query success rate
5. Property matching success rate
6. Any outstanding issues

### Monthly Review Should Include:
1. Trend analysis
2. Improvement recommendations
3. Documentation updates
4. Process improvements

---

**Last Updated:** January 6, 2026  
**Next Review:** January 13, 2026

























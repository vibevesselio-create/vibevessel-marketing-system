# DriveSheetsSync Race Condition Fix - Monitoring Guide

**Fix Commit:** `a7d8c35`  
**Monitoring Period:** 48 hours post-deployment (minimum)

---

## Monitoring Objectives

1. Verify race condition fix is working correctly
2. Detect any new duplicate folder creation
3. Monitor lock acquisition and timeout scenarios
4. Ensure consolidation logic functions properly
5. Identify any performance impacts

---

## Key Metrics to Monitor

### 1. Duplicate Folder Creation

**Metric:** Number of new folders with `(1)`, `(2)` suffixes  
**Target:** Zero  
**Frequency:** Check every 6 hours for first 48 hours, then daily

**Monitoring Method:**
```javascript
// Run this function periodically
function monitorDuplicateFolders() {
  const parentId = PropertiesService.getScriptProperties()
    .getProperty('WORKSPACE_DATABASES_FOLDER_ID');
  
  if (!parentId) {
    console.error('WORKSPACE_DATABASES_FOLDER_ID not set');
    return;
  }
  
  const parent = DriveApp.getFolderById(parentId);
  const folders = parent.getFolders();
  const duplicates = [];
  const folderMap = {};
  
  while (folders.hasNext()) {
    const folder = folders.next();
    const name = folder.getName();
    
    // Check for duplicate pattern: name (1), name (2), etc.
    const match = name.match(/^(.+?)\s*\((\d+)\)\s*$/);
    if (match) {
      const baseName = match[1];
      const suffix = parseInt(match[2]);
      
      if (!folderMap[baseName]) {
        folderMap[baseName] = [];
      }
      folderMap[baseName].push({
        name,
        id: folder.getId(),
        suffix,
        trashed: folder.isTrashed(),
        lastUpdated: folder.getLastUpdated()
      });
    }
  }
  
  // Find actual duplicates (multiple folders with same base name)
  for (const [baseName, folderList] of Object.entries(folderMap)) {
    if (folderList.length > 0) {
      // Check if base folder exists
      const baseFolders = parent.getFoldersByName(baseName);
      const baseExists = baseFolders.hasNext();
      
      duplicates.push({
        baseName,
        baseExists,
        duplicates: folderList,
        totalCount: folderList.length + (baseExists ? 1 : 0)
      });
    }
  }
  
  // Log results
  console.log(`Found ${duplicates.length} sets of duplicate folders`);
  duplicates.forEach(dup => {
    console.log(`\n${dup.baseName}:`);
    console.log(`  Base folder exists: ${dup.baseExists}`);
    console.log(`  Duplicate count: ${dup.duplicates.length}`);
    dup.duplicates.forEach(d => {
      console.log(`    - ${d.name} (trashed: ${d.trashed}, updated: ${d.lastUpdated})`);
    });
  });
  
  return {
    timestamp: new Date().toISOString(),
    duplicateSets: duplicates.length,
    totalDuplicates: duplicates.reduce((sum, d) => sum + d.duplicates.length, 0),
    details: duplicates
  };
}
```

---

### 2. Lock Acquisition Success Rate

**Metric:** Percentage of successful lock acquisitions  
**Target:** > 95%  
**Frequency:** Review logs after each sync run

**What to Look For:**

✅ **Success Indicators:**
- `🔒 Attempting to obtain DriveSheets script lock`
- Lock acquired, sync proceeds normally
- Lock released in `finally` block

⚠️ **Warning Indicators:**
- `⚠️ Unable to obtain DriveSheets script lock` (occasional is OK)
- `DriveSheetsSync: another run is already in progress. Aborting...` (expected during overlap)

❌ **Error Indicators:**
- Frequent lock timeouts (> 10% of runs)
- Lock not released (check for orphaned locks)
- Sync failures due to lock issues

**Monitoring Query:**
```javascript
// Search execution logs for lock-related messages
// In Apps Script execution transcript, search for:
// - "Attempting to obtain DriveSheets script lock"
// - "Unable to obtain DriveSheets script lock"
// - "another run is already in progress"
// - "Failed to release DriveSheets script lock"
```

---

### 3. Consolidation Activity

**Metric:** Number of duplicate folders consolidated per run  
**Target:** Decreasing over time (should reach zero)  
**Frequency:** Check after each sync run

**What to Look For:**

✅ **Success Indicators:**
- Log messages: `Consolidating X duplicate folder(s)`
- Log messages: `Consolidated and trashed duplicate folder: {name}`
- Duplicate folders moved to trash
- Contents moved to primary folder

**Monitoring:**
```javascript
// Check logs for consolidation messages
// Search for:
// - "Found X folders for database"
// - "Consolidating X duplicate folder(s)"
// - "Consolidated and trashed duplicate folder"
// - "Consolidation complete: moved X files and Y folders"
```

---

### 4. Execution Performance

**Metric:** Sync execution time  
**Target:** No significant increase (< 5% overhead)  
**Frequency:** Compare weekly averages

**Baseline:** Pre-fix execution time (if available)  
**Current:** Post-fix execution time

**Monitoring:**
- Check execution transcript for execution duration
- Compare with historical averages
- Note any significant increases

---

### 5. Error Rates

**Metric:** Number of errors per sync run  
**Target:** Zero (or same as pre-fix baseline)  
**Frequency:** Review after each run

**What to Monitor:**
- Lock-related errors
- Folder creation errors
- Consolidation errors
- Any new error types

---

## Monitoring Schedule

### First 6 Hours (Critical Period)

**Frequency:** Every 2 hours

- [ ] Check for new duplicate folders
- [ ] Review execution logs for errors
- [ ] Verify lock acquisition working
- [ ] Check consolidation activity

### First 24 Hours

**Frequency:** Every 6 hours

- [ ] Continue duplicate folder checks
- [ ] Monitor lock acquisition success rate
- [ ] Review error logs
- [ ] Check performance metrics

### First 48 Hours

**Frequency:** Every 12 hours

- [ ] Continue all monitoring
- [ ] Assess overall fix effectiveness
- [ ] Document any issues encountered

### Ongoing (Weekly)

**Frequency:** Weekly review

- [ ] Check for any new duplicates
- [ ] Review weekly error summary
- [ ] Assess performance trends
- [ ] Update monitoring documentation

---

## Alert Conditions

### Critical Alerts (Immediate Action Required)

- ❌ **New duplicate folders created** (indicates fix not working)
- ❌ **Lock mechanism failing** (> 50% failure rate)
- ❌ **Sync failures** due to lock issues
- ❌ **Registry corruption** detected

**Action:** Investigate immediately, consider rollback

### Warning Alerts (Investigate)

- ⚠️ **Lock timeouts** (> 10% of runs)
- ⚠️ **Consolidation failures** (folders not consolidating)
- ⚠️ **Performance degradation** (> 10% slower)
- ⚠️ **Frequent lock contention** (multiple overlaps)

**Action:** Monitor closely, investigate root cause

### Info Alerts (Monitor)

- ℹ️ **Occasional lock timeouts** (< 10% of runs) - expected during overlap
- ℹ️ **Consolidation in progress** - normal during cleanup phase
- ℹ️ **Lock acquisition working** - positive indicator

---

## Monitoring Dashboard

Create a simple dashboard to track:

```
DriveSheetsSync Race Condition Fix - Monitoring Dashboard
=========================================================

Date Range: [Start] to [End]

Key Metrics:
- Duplicate Folders Created: 0 (Target: 0) ✅
- Lock Acquisition Success Rate: 98% (Target: >95%) ✅
- Consolidation Activity: 5 folders consolidated ✅
- Average Execution Time: 2.3 min (Baseline: 2.2 min) ✅
- Error Rate: 0% (Target: 0%) ✅

Recent Activity:
- [Timestamp] Sync completed successfully, 0 duplicates
- [Timestamp] Lock acquired successfully
- [Timestamp] Consolidated 2 duplicate folders

Issues:
- None

Status: ✅ HEALTHY
```

---

## Log Analysis Queries

### Find Lock-Related Messages

```javascript
// In Apps Script execution transcript, search for:
"Attempting to obtain DriveSheets script lock"
"Unable to obtain DriveSheets script lock"
"another run is already in progress"
"Failed to release DriveSheets script lock"
```

### Find Consolidation Activity

```javascript
// Search for:
"Found.*folders for database"
"Consolidating.*duplicate folder"
"Consolidated and trashed"
"Consolidation complete"
```

### Find Errors

```javascript
// Search for:
"ERROR"
"Failed"
"Exception"
"Error:"
```

---

## Reporting

### Daily Summary (First 48 Hours)

Report daily with:
- Number of sync runs
- Duplicate folders detected/created
- Lock acquisition success rate
- Any errors encountered
- Overall status

### Weekly Summary (Ongoing)

Report weekly with:
- Weekly metrics summary
- Trends analysis
- Any issues or concerns
- Recommendations

---

## Troubleshooting

### Issue: New Duplicate Folders Created

**Possible Causes:**
- Lock not working correctly
- Race condition still exists
- Lock timeout too short

**Investigation:**
1. Check logs for lock acquisition messages
2. Verify lock is acquired before folder checks
3. Check for lock timeout scenarios
4. Review code changes

### Issue: Frequent Lock Timeouts

**Possible Causes:**
- Sync runs taking longer than expected
- Multiple triggers overlapping
- Lock wait time too short

**Investigation:**
1. Check sync execution times
2. Review trigger configuration
3. Consider increasing `LOCK_WAIT_MS`
4. Check for stuck locks

### Issue: Consolidation Not Working

**Possible Causes:**
- Consolidation logic not executing
- Permissions issues
- Folder access problems

**Investigation:**
1. Check logs for consolidation messages
2. Verify folder permissions
3. Test consolidation manually
4. Review consolidation code

---

## Success Criteria

Monitoring period is successful if:

✅ **No new duplicate folders** created for 48+ hours  
✅ **Lock acquisition success rate** > 95%  
✅ **Consolidation working** (existing duplicates being cleaned up)  
✅ **No performance degradation** (< 5% overhead)  
✅ **No new errors** introduced  
✅ **Trigger overlap handled** gracefully

---

**Monitoring Guide Created:** 2026-01-18  
**Status:** Ready for use

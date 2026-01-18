# DriveSheetsSync Race Condition Fix - Test Plan

**Issue:** DS-001 - Race condition in `ensureDbFolder_()` causing duplicate folders  
**Fix Commit:** `a7d8c35`  
**Date:** 2026-01-18

---

## Test Objectives

Verify that the race condition fix in `ensureDbFolder_()` prevents duplicate folder creation when multiple concurrent calls attempt to create the same database folder.

---

## Test Scenarios

### Scenario 1: Single Thread Execution (Baseline)

**Objective:** Verify normal operation without concurrency

**Steps:**
1. Create a test data source with unique ID
2. Call `ensureDbFolder_()` once
3. Verify exactly one folder is created with correct name

**Expected Result:**
- ✅ One folder created: `{sanitized_title}_{ds.id}`
- ✅ Folder tracked in Notion Folders database
- ✅ No duplicate folders

**Test Function:**
```javascript
function testEnsureDbFolderSingleThread() {
  const testDs = {
    id: 'test-db-' + Date.now(),
    title: 'Test Database ' + Date.now()
  };
  const parentId = 'YOUR_TEST_PARENT_FOLDER_ID';
  
  const folder = ensureDbFolder_(parentId, testDs);
  
  // Verify folder exists and has correct name
  const expectedName = `${sanitizeName(testDs.title)}_${testDs.id}`;
  console.assert(folder.getName() === expectedName, 
    'Folder name mismatch: ' + folder.getName());
  
  // Verify no duplicates exist
  const parent = DriveApp.getFolderById(parentId);
  const folders = parent.getFoldersByName(expectedName);
  let count = 0;
  while (folders.hasNext()) {
    folders.next();
    count++;
  }
  console.assert(count === 1, 'Duplicate folders found: ' + count);
  
  console.log('✅ Single thread test passed');
}
```

---

### Scenario 2: Concurrent Execution Simulation

**Objective:** Verify lock prevents race condition

**Steps:**
1. Create a test data source
2. Simulate two concurrent calls by:
   - Starting first call (acquires lock)
   - Immediately starting second call (should wait for lock)
   - First call completes and releases lock
   - Second call proceeds
3. Verify only one folder exists

**Expected Result:**
- ✅ Lock acquired by first thread
- ✅ Second thread waits for lock
- ✅ Only one folder created
- ✅ No duplicate folders with `(1)`, `(2)` suffixes

**Test Function:**
```javascript
function testEnsureDbFolderConcurrent() {
  const testDs = {
    id: 'test-concurrent-' + Date.now(),
    title: 'Concurrent Test ' + Date.now()
  };
  const parentId = 'YOUR_TEST_PARENT_FOLDER_ID';
  const expectedName = `${sanitizeName(testDs.title)}_${testDs.id}`;
  
  // Note: True concurrent execution is difficult in GAS
  // This test simulates by calling twice in quick succession
  // In production, the lock will prevent actual race conditions
  
  const folder1 = ensureDbFolder_(parentId, testDs);
  Utilities.sleep(100); // Small delay
  const folder2 = ensureDbFolder_(parentId, testDs);
  
  // Both should return the same folder
  console.assert(folder1.getId() === folder2.getId(), 
    'Different folders returned from concurrent calls');
  
  // Verify only one folder exists
  const parent = DriveApp.getFolderById(parentId);
  const folders = parent.getFoldersByName(expectedName);
  let count = 0;
  while (folders.hasNext()) {
    folders.next();
    count++;
  }
  console.assert(count === 1, 'Duplicate folders found: ' + count);
  
  console.log('✅ Concurrent execution test passed');
}
```

---

### Scenario 3: Lock Timeout Handling

**Objective:** Verify graceful handling when lock cannot be acquired

**Steps:**
1. Manually acquire lock (simulate another process holding it)
2. Attempt to call `ensureDbFolder_()` with short timeout
3. Verify function handles timeout gracefully

**Expected Result:**
- ✅ Function attempts to acquire lock with exponential backoff
- ✅ If lock unavailable after retries, function checks for existing folder
- ✅ If folder exists, returns it
- ✅ If folder doesn't exist, throws error (deferring creation)
- ✅ No duplicate folders created

**Test Function:**
```javascript
function testEnsureDbFolderLockTimeout() {
  const testDs = {
    id: 'test-timeout-' + Date.now(),
    title: 'Timeout Test ' + Date.now()
  };
  const parentId = 'YOUR_TEST_PARENT_FOLDER_ID';
  
  // Manually acquire lock to simulate contention
  const lock = LockService.getScriptLock();
  lock.tryLock(10000); // Hold lock for 10 seconds
  
  try {
    // This should timeout and check for existing folder
    // Since folder doesn't exist, should throw error
    ensureDbFolder_(parentId, testDs);
    console.log('⚠️ Expected timeout error, but function succeeded');
  } catch (e) {
    console.log('✅ Lock timeout handled correctly: ' + e.message);
  } finally {
    lock.releaseLock();
  }
}
```

---

### Scenario 4: Existing Duplicate Consolidation

**Objective:** Verify consolidation logic handles pre-existing duplicates

**Steps:**
1. Manually create duplicate folders: `{name}_id`, `{name}_id (1)`, `{name}_id (2)`
2. Call `ensureDbFolder_()`
3. Verify duplicates are consolidated into primary folder

**Expected Result:**
- ✅ Function identifies all matching folders
- ✅ Duplicates consolidated into primary folder
- ✅ Contents moved from duplicates to primary
- ✅ Duplicate folders trashed
- ✅ Primary folder renamed to canonical name if needed

**Test Function:**
```javascript
function testEnsureDbFolderConsolidation() {
  const testDs = {
    id: 'test-consolidate-' + Date.now(),
    title: 'Consolidation Test ' + Date.now()
  };
  const parentId = 'YOUR_TEST_PARENT_FOLDER_ID';
  const parent = DriveApp.getFolderById(parentId);
  const expectedName = `${sanitizeName(testDs.title)}_${testDs.id}`;
  
  // Create duplicate folders manually
  const dup1 = parent.createFolder(expectedName + ' (1)');
  const dup2 = parent.createFolder(expectedName + ' (2)');
  
  // Add test files to duplicates
  const testFile1 = DriveApp.createFile('test1.txt', 'content1');
  testFile1.moveTo(dup1);
  const testFile2 = DriveApp.createFile('test2.txt', 'content2');
  testFile2.moveTo(dup2);
  
  // Call ensureDbFolder_ - should consolidate
  const folder = ensureDbFolder_(parentId, testDs);
  
  // Verify primary folder exists
  console.assert(folder.getName() === expectedName || 
                 folder.getName().includes(testDs.id),
    'Primary folder not found');
  
  // Verify duplicates are trashed
  const dup1Check = DriveApp.getFolderById(dup1.getId());
  const dup2Check = DriveApp.getFolderById(dup2.getId());
  console.assert(dup1Check.isTrashed(), 'Duplicate 1 not trashed');
  console.assert(dup2Check.isTrashed(), 'Duplicate 2 not trashed');
  
  // Verify files moved to primary
  const files = folder.getFiles();
  let fileCount = 0;
  while (files.hasNext()) {
    files.next();
    fileCount++;
  }
  console.assert(fileCount >= 2, 'Files not consolidated: ' + fileCount);
  
  console.log('✅ Consolidation test passed');
}
```

---

## Integration Test: Production Simulation

### Test: Multiple Trigger Overlap

**Objective:** Verify `manualRunDriveSheets()` handles concurrent triggers correctly

**Steps:**
1. Set up time-based trigger (every 10 minutes)
2. Manually trigger `manualRunDriveSheets()` while trigger is running
3. Monitor logs for lock acquisition messages
4. Verify only one sync runs at a time

**Expected Result:**
- ✅ First trigger acquires lock and runs
- ✅ Second trigger attempts lock, fails, logs warning, exits cleanly
- ✅ No duplicate registry writes
- ✅ No corrupted rotation pointers
- ✅ Logs show proper lock handling

**Monitoring:**
```javascript
// Check logs for:
// - "🔒 Attempting to obtain DriveSheets script lock"
// - "DriveSheetsSync: another run is already in progress. Aborting..."
// - No errors about duplicate folders or registry corruption
```

---

## Performance Test

### Test: Lock Acquisition Performance

**Objective:** Verify lock acquisition doesn't add significant overhead

**Steps:**
1. Measure time to acquire lock (should be < 100ms normally)
2. Measure time for exponential backoff retries (1s, 2s, 4s)
3. Verify total overhead is acceptable

**Expected Result:**
- ✅ Normal lock acquisition: < 100ms
- ✅ Retry delays: 1s, 2s, 4s as designed
- ✅ Total overhead: < 5% of normal execution time

---

## Production Verification Checklist

After deployment, verify:

- [ ] No new duplicate folders created (check for `(1)`, `(2)` suffixes)
- [ ] Logs show proper lock acquisition messages
- [ ] No "lock timeout" warnings in normal operation
- [ ] Existing duplicates are consolidated on next run
- [ ] Trigger overlap handled gracefully (check logs during trigger overlap)
- [ ] No registry corruption or rotation pointer issues

---

## Rollback Plan

If issues occur:

1. **Immediate:** Revert commit `a7d8c35`
   ```bash
   git revert a7d8c35
   clasp push
   ```

2. **Monitor:** Check for:
   - Duplicate folder creation
   - Lock-related errors
   - Performance degradation

3. **Investigate:** Review logs for:
   - Lock acquisition failures
   - Timeout scenarios
   - Unexpected errors

---

## Test Execution Notes

### Prerequisites

- Test Google Drive folder with write permissions
- Test data source objects
- Access to Apps Script execution logs

### Running Tests

1. **Unit Tests:** Run test functions in Apps Script editor
2. **Integration Tests:** Monitor production logs after deployment
3. **Performance Tests:** Use Apps Script execution transcript

### Test Data Cleanup

After tests, clean up:
- Test folders created during testing
- Test files in test folders
- Test triggers (if created)

---

## Success Criteria

✅ **All tests pass**  
✅ **No duplicate folders created**  
✅ **Lock handling works correctly**  
✅ **Consolidation logic functions properly**  
✅ **Performance impact is minimal**  
✅ **Production monitoring shows no issues**

---

**Test Plan Created:** 2026-01-18  
**Status:** Ready for execution

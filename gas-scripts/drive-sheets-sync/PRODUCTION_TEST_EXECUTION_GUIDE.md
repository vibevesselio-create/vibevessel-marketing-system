# Production Test Execution Guide

**Date:** 2026-01-18  
**Fix:** DriveSheetsSync Race Condition Fix (commit a7d8c35)

---

## ⚠️ IMPORTANT: Production Testing Safety

These tests are designed to be **SAFE for production execution**. They:
- Create test folders that are automatically cleaned up
- Use unique test IDs to avoid conflicts
- Verify behavior without modifying production data
- Can be run multiple times safely

**However:** Always test during low-traffic periods and monitor execution logs.

---

## Quick Start

### Step 1: Deploy Test Functions

1. Open Apps Script project: `gas-scripts/drive-sheets-sync`
2. Copy contents of `PRODUCTION_TEST_EXECUTION.js` into a new file
3. Save the project

### Step 2: Run Individual Tests

Run these functions one at a time in Apps Script editor:

```javascript
// Test 1: Verify lock-first pattern
PRODUCTION_TEST_1_LockFirstPattern()

// Test 2: Simulate concurrent execution
PRODUCTION_TEST_2_ConcurrentExecution()

// Test 3: Verify lock timeout handling
PRODUCTION_TEST_3_LockTimeout()

// Test 4: Verify concurrency guard
PRODUCTION_TEST_4_ConcurrencyGuard()

// Test 5: Check for existing duplicates
PRODUCTION_TEST_5_CheckExistingDuplicates()
```

### Step 3: Run Full Test Suite

```javascript
// Run all tests at once
RUN_ALL_PRODUCTION_TESTS()
```

---

## Test Descriptions

### Test 1: Lock-First Pattern Verification

**What it tests:**
- Verifies `ensureDbFolder_()` acquires lock before checking folders
- Creates a test folder and verifies no duplicates
- Checks execution time and folder naming

**Expected result:** ✅ PASS
- Folder created successfully
- No duplicate folders
- Execution completes in < 10 seconds

**Safety:** Creates and immediately deletes test folder

---

### Test 2: Concurrent Execution Simulation

**What it tests:**
- Simulates rapid sequential calls to `ensureDbFolder_()`
- Verifies both calls return the same folder (no duplicates)
- Checks that lock prevents race conditions

**Expected result:** ✅ PASS
- Both calls return same folder ID
- Only one folder exists
- No duplicate folders created

**Safety:** Creates and immediately deletes test folder

---

### Test 3: Lock Timeout Handling

**What it tests:**
- Verifies timeout handling code exists
- Checks for exponential backoff implementation
- Validates error handling structure

**Expected result:** ✅ PASS
- Timeout handling code present
- Exponential backoff implemented

**Safety:** Code inspection only, no execution

---

### Test 4: Concurrency Guard Verification

**What it tests:**
- Verifies `manualRunDriveSheets()` has lock mechanism
- Checks for clean exit on lock failure
- Validates lock release in finally block

**Expected result:** ✅ PASS
- Lock acquisition code found
- Clean exit code found
- Finally block with lock release found

**Safety:** Code inspection only, no execution

---

### Test 5: Existing Duplicates Check

**What it tests:**
- Scans for existing duplicate folders (pre-fix)
- Identifies folders that need consolidation
- Reports on duplicate sets

**Expected result:** Informational
- Reports duplicate sets found
- These should be consolidated on next sync run

**Safety:** Read-only, no modifications

---

## Production Test Execution Steps

### Pre-Test Checklist

- [ ] Code deployed to Apps Script (commit a7d8c35)
- [ ] `WORKSPACE_DATABASES_FOLDER_ID` configured in script properties
- [ ] Low-traffic period selected
- [ ] Execution logs accessible
- [ ] Rollback plan ready (if needed)

### Execution Steps

1. **Deploy Test Functions**
   ```bash
   cd gas-scripts/drive-sheets-sync
   # Copy PRODUCTION_TEST_EXECUTION.js into Apps Script project
   clasp push
   ```

2. **Run Test 1** (Lock-First Pattern)
   - Execute: `PRODUCTION_TEST_1_LockFirstPattern()`
   - Verify: ✅ PASS
   - Check logs for any errors

3. **Run Test 2** (Concurrent Execution)
   - Execute: `PRODUCTION_TEST_2_ConcurrentExecution()`
   - Verify: ✅ PASS
   - Check logs for any errors

4. **Run Test 3** (Lock Timeout)
   - Execute: `PRODUCTION_TEST_3_LockTimeout()`
   - Verify: ✅ PASS

5. **Run Test 4** (Concurrency Guard)
   - Execute: `PRODUCTION_TEST_4_ConcurrencyGuard()`
   - Verify: ✅ PASS

6. **Run Test 5** (Existing Duplicates)
   - Execute: `PRODUCTION_TEST_5_CheckExistingDuplicates()`
   - Review: Check for existing duplicates

7. **Run Full Suite** (Optional)
   - Execute: `RUN_ALL_PRODUCTION_TESTS()`
   - Review: All tests should pass

### Post-Test Verification

- [ ] All tests passed
- [ ] No errors in execution logs
- [ ] No duplicate folders created during tests
- [ ] Test folders cleaned up
- [ ] Production sync still working

---

## Monitoring During Tests

### What to Watch For

1. **Execution Logs**
   - Check for lock acquisition messages
   - Verify no errors during folder creation
   - Confirm cleanup completed

2. **Google Drive**
   - Verify test folders are created and deleted
   - Check for any unexpected folders
   - Confirm no duplicates created

3. **Performance**
   - Test execution should complete in < 10 seconds
   - No significant delays
   - Lock acquisition should be fast

---

## Expected Test Results

### All Tests Should Pass

```
✅ PASS Test 1: Lock-First Pattern Verification
✅ PASS Test 2: Concurrent Execution Test
✅ PASS Test 3: Lock Timeout Handling
✅ PASS Test 4: Concurrency Guard Verification
✅ PASS Test 5: Existing Duplicates Check

Results: 5/5 tests passed
```

### If Tests Fail

1. **Review error messages** in execution logs
2. **Check script properties** - ensure `WORKSPACE_DATABASES_FOLDER_ID` is set
3. **Verify code deployment** - ensure latest code is deployed
4. **Check permissions** - ensure script has Drive access
5. **Review test output** - check detailed error messages

---

## Production Validation

After tests pass, validate in production:

1. **Monitor next sync run**
   - Check execution logs
   - Verify no duplicate folders created
   - Confirm lock acquisition working

2. **Check for consolidation**
   - Existing duplicates should be consolidated
   - No new duplicates should appear

3. **Monitor performance**
   - Sync should complete normally
   - No significant performance impact

---

## Rollback Plan

If issues occur:

1. **Immediate:** Revert to previous version
   ```bash
   git revert a7d8c35
   clasp push
   ```

2. **Investigate:** Review test results and logs
3. **Fix:** Address any issues found
4. **Retest:** Run tests again before redeploying

---

## Success Criteria

Tests are successful if:

✅ **All 5 tests pass**  
✅ **No duplicate folders created**  
✅ **Lock mechanism working correctly**  
✅ **No errors in execution logs**  
✅ **Test folders cleaned up properly**

---

## Next Steps After Tests Pass

1. ✅ **Deploy to production** (if not already deployed)
2. ✅ **Monitor first sync run**
3. ✅ **Verify no new duplicates**
4. ✅ **Check consolidation of existing duplicates**
5. ✅ **Continue monitoring for 48 hours**

---

**Test Guide Created:** 2026-01-18  
**Status:** Ready for production testing

/**
 * DriveSheetsSync Race Condition Fix - Verification Helper Functions
 * 
 * These functions help verify that the race condition fix (commit a7d8c35)
 * is properly implemented and working correctly.
 * 
 * Usage: Copy these functions into your Apps Script project for verification.
 */

/**
 * Verify that ensureDbFolder_() uses lock-first pattern
 * 
 * This function checks the code structure to verify the fix is in place.
 * Note: This is a manual code review helper - actual verification requires
 * running the function and checking behavior.
 */
function verifyRaceConditionFix() {
  const code = DriveApp.getFileById(ScriptApp.getScriptId()).getBlob().getDataAsString();
  
  const checks = {
    lockBeforeCheck: false,
    lockInFinally: false,
    exponentialBackoff: false,
    errorHandling: false
  };
  
  // Check 1: Lock acquired before folder checks
  const lockBeforeCheckPattern = /const\s+lock\s*=\s*LockService\.getScriptLock\(\)[\s\S]*?findMatchingFolders_\(\)/;
  checks.lockBeforeCheck = lockBeforeCheckPattern.test(code);
  
  // Check 2: Lock released in finally block
  const finallyPattern = /finally\s*\{[\s\S]*?lock\.releaseLock\(\)/;
  checks.lockInFinally = finallyPattern.test(code);
  
  // Check 3: Exponential backoff retry logic
  const backoffPattern = /\[1000,\s*2000,\s*4000\]/;
  checks.exponentialBackoff = backoffPattern.test(code);
  
  // Check 4: Error handling for lock timeout
  const errorHandlingPattern = /if\s*\(!lockAcquired\)[\s\S]*?throw\s+new\s+Error/;
  checks.errorHandling = errorHandlingPattern.test(code);
  
  // Report results
  console.log('=== Race Condition Fix Verification ===');
  console.log('Lock acquired before folder checks:', checks.lockBeforeCheck ? '✅' : '❌');
  console.log('Lock released in finally block:', checks.lockInFinally ? '✅' : '❌');
  console.log('Exponential backoff implemented:', checks.exponentialBackoff ? '✅' : '❌');
  console.log('Error handling for lock timeout:', checks.errorHandling ? '✅' : '❌');
  
  const allPassed = Object.values(checks).every(v => v === true);
  console.log('\nOverall Status:', allPassed ? '✅ FIX VERIFIED' : '⚠️ ISSUES DETECTED');
  
  return {
    passed: allPassed,
    checks: checks,
    timestamp: new Date().toISOString()
  };
}

/**
 * Verify manualRunDriveSheets() has concurrency guard
 * 
 * Checks that manualRunDriveSheets() properly implements lock mechanism.
 */
function verifyConcurrencyGuard() {
  const code = DriveApp.getFileById(ScriptApp.getScriptId()).getBlob().getDataAsString();
  
  const checks = {
    lockAcquired: false,
    cleanExit: false,
    lockReleased: false,
    logging: false
  };
  
  // Check 1: Lock acquired in manualRunDriveSheets
  const lockPattern = /function\s+manualRunDriveSheets[\s\S]*?LockService\.getScriptLock\(\)/;
  checks.lockAcquired = lockPattern.test(code);
  
  // Check 2: Clean exit when lock unavailable
  const cleanExitPattern = /if\s*\(!lockAcquired\)[\s\S]*?return/;
  checks.cleanExit = cleanExitPattern.test(code);
  
  // Check 3: Lock released in finally
  const releasePattern = /finally\s*\{[\s\S]*?lock\.releaseLock\(\)/;
  checks.lockReleased = releasePattern.test(code);
  
  // Check 4: Proper logging
  const loggingPattern = /another run is already in progress/;
  checks.logging = loggingPattern.test(code);
  
  // Report results
  console.log('=== Concurrency Guard Verification ===');
  console.log('Lock acquired:', checks.lockAcquired ? '✅' : '❌');
  console.log('Clean exit on lock failure:', checks.cleanExit ? '✅' : '❌');
  console.log('Lock released in finally:', checks.lockReleased ? '✅' : '❌');
  console.log('Proper logging:', checks.logging ? '✅' : '❌');
  
  const allPassed = Object.values(checks).every(v => v === true);
  console.log('\nOverall Status:', allPassed ? '✅ GUARD VERIFIED' : '⚠️ ISSUES DETECTED');
  
  return {
    passed: allPassed,
    checks: checks,
    timestamp: new Date().toISOString()
  };
}

/**
 * Check for duplicate folders in workspace databases folder
 * 
 * This function scans for folders with (1), (2) suffixes that indicate
 * race condition duplicates.
 */
function checkForDuplicateFolders() {
  const parentId = PropertiesService.getScriptProperties()
    .getProperty('WORKSPACE_DATABASES_FOLDER_ID');
  
  if (!parentId) {
    console.error('WORKSPACE_DATABASES_FOLDER_ID not set in script properties');
    return {
      error: 'WORKSPACE_DATABASES_FOLDER_ID not configured',
      timestamp: new Date().toISOString()
    };
  }
  
  try {
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
    
    // Report results
    console.log('=== Duplicate Folder Check ===');
    console.log('Timestamp:', new Date().toISOString());
    console.log('Duplicate sets found:', duplicates.length);
    
    if (duplicates.length === 0) {
      console.log('✅ No duplicate folders detected');
    } else {
      console.log('⚠️ Duplicate folders detected:');
      duplicates.forEach(dup => {
        console.log(`\n  ${dup.baseName}:`);
        console.log(`    Base folder exists: ${dup.baseExists}`);
        console.log(`    Duplicate count: ${dup.duplicates.length}`);
        dup.duplicates.forEach(d => {
          console.log(`      - ${d.name} (trashed: ${d.trashed})`);
        });
      });
    }
    
    return {
      timestamp: new Date().toISOString(),
      duplicateSets: duplicates.length,
      totalDuplicates: duplicates.reduce((sum, d) => sum + d.duplicates.length, 0),
      details: duplicates,
      status: duplicates.length === 0 ? 'CLEAN' : 'DUPLICATES_FOUND'
    };
    
  } catch (e) {
    console.error('Error checking for duplicates:', e);
    return {
      error: String(e),
      timestamp: new Date().toISOString()
    };
  }
}

/**
 * Monitor lock acquisition success rate
 * 
 * Analyzes recent execution logs to determine lock acquisition success rate.
 * Note: This requires access to execution logs, which may not be available
 * programmatically. This is a helper for manual log analysis.
 */
function analyzeLockAcquisition() {
  console.log('=== Lock Acquisition Analysis ===');
  console.log('Note: This function provides guidance for manual log analysis.');
  console.log('Search execution logs for the following patterns:\n');
  
  console.log('1. Lock acquisition attempts:');
  console.log('   Search for: "Attempting to obtain DriveSheets script lock"');
  console.log('   Count total occurrences\n');
  
  console.log('2. Lock acquisition failures:');
  console.log('   Search for: "Unable to obtain DriveSheets script lock"');
  console.log('   Count failures\n');
  
  console.log('3. Clean exits (lock unavailable):');
  console.log('   Search for: "another run is already in progress"');
  console.log('   These are expected during trigger overlap\n');
  
  console.log('4. Lock release failures:');
  console.log('   Search for: "Failed to release DriveSheets script lock"');
  console.log('   Should be zero\n');
  
  console.log('Expected success rate: > 95%');
  console.log('Calculation: (Total - Failures) / Total * 100');
  
  return {
    guidance: 'Manual log analysis required',
    searchPatterns: [
      'Attempting to obtain DriveSheets script lock',
      'Unable to obtain DriveSheets script lock',
      'another run is already in progress',
      'Failed to release DriveSheets script lock'
    ],
    expectedSuccessRate: '> 95%'
  };
}

/**
 * Run all verification checks
 * 
 * Executes all verification functions and provides a summary report.
 */
function runAllVerificationChecks() {
  console.log('========================================');
  console.log('DriveSheetsSync Race Condition Fix');
  console.log('Comprehensive Verification Report');
  console.log('========================================\n');
  
  const results = {
    timestamp: new Date().toISOString(),
    raceConditionFix: verifyRaceConditionFix(),
    concurrencyGuard: verifyConcurrencyGuard(),
    duplicateFolders: checkForDuplicateFolders(),
    lockAnalysis: analyzeLockAcquisition()
  };
  
  console.log('\n========================================');
  console.log('Summary');
  console.log('========================================');
  console.log('Race Condition Fix:', results.raceConditionFix.passed ? '✅ VERIFIED' : '❌ ISSUES');
  console.log('Concurrency Guard:', results.concurrencyGuard.passed ? '✅ VERIFIED' : '❌ ISSUES');
  console.log('Duplicate Folders:', results.duplicateFolders.status === 'CLEAN' ? '✅ CLEAN' : '⚠️ FOUND');
  console.log('\nReport generated:', results.timestamp);
  
  return results;
}

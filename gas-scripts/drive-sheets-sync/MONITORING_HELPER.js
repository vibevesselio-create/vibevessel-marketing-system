/**
 * DriveSheetsSync Race Condition Fix - Monitoring Helper Functions
 * 
 * These functions help monitor the race condition fix after deployment.
 * Add these to your Apps Script project for ongoing monitoring.
 */

/**
 * Monitor duplicate folder creation
 * 
 * Checks for new duplicate folders and logs findings.
 * Run this periodically (e.g., after each sync) to monitor for issues.
 */
function monitorDuplicateFolders() {
  const parentId = PropertiesService.getScriptProperties()
    .getProperty('WORKSPACE_DATABASES_FOLDER_ID');
  
  if (!parentId) {
    console.warn('[MONITOR] WORKSPACE_DATABASES_FOLDER_ID not set');
    return null;
  }
  
  try {
    const parent = DriveApp.getFolderById(parentId);
    const folders = parent.getFolders();
    const duplicates = [];
    const folderMap = {};
    const now = new Date();
    
    while (folders.hasNext()) {
      const folder = folders.next();
      const name = folder.getName();
      
      // Check for duplicate pattern
      const match = name.match(/^(.+?)\s*\((\d+)\)\s*$/);
      if (match) {
        const baseName = match[1];
        
        if (!folderMap[baseName]) {
          folderMap[baseName] = [];
        }
        folderMap[baseName].push({
          name,
          id: folder.getId(),
          trashed: folder.isTrashed(),
          lastUpdated: folder.getLastUpdated(),
          ageDays: Math.floor((now - folder.getLastUpdated()) / (1000 * 60 * 60 * 24))
        });
      }
    }
    
    // Find actual duplicates
    for (const [baseName, folderList] of Object.entries(folderMap)) {
      if (folderList.length > 0) {
        const baseFolders = parent.getFoldersByName(baseName);
        const baseExists = baseFolders.hasNext();
        
        // Check if any duplicates were created recently (last 24 hours)
        const recentDuplicates = folderList.filter(f => f.ageDays === 0);
        
        duplicates.push({
          baseName,
          baseExists,
          duplicates: folderList,
          recentCount: recentDuplicates.length,
          totalCount: folderList.length + (baseExists ? 1 : 0)
        });
      }
    }
    
    // Log results
    const recentDuplicates = duplicates.filter(d => d.recentCount > 0);
    
    if (recentDuplicates.length > 0) {
      console.warn(`[MONITOR] ⚠️ ${recentDuplicates.length} sets of RECENT duplicate folders detected!`);
      recentDuplicates.forEach(dup => {
        console.warn(`[MONITOR]   ${dup.baseName}: ${dup.recentCount} new duplicate(s) in last 24h`);
      });
    } else if (duplicates.length > 0) {
      console.log(`[MONITOR] ℹ️ ${duplicates.length} sets of existing duplicate folders (pre-fix)`);
    } else {
      console.log('[MONITOR] ✅ No duplicate folders detected');
    }
    
    // Store monitoring data
    const monitoringData = {
      timestamp: now.toISOString(),
      duplicateSets: duplicates.length,
      recentDuplicates: recentDuplicates.length,
      totalDuplicates: duplicates.reduce((sum, d) => sum + d.duplicates.length, 0),
      status: recentDuplicates.length > 0 ? 'ALERT' : duplicates.length > 0 ? 'INFO' : 'CLEAN'
    };
    
    // Store in PropertiesService for trend analysis
    const historyKey = 'MONITOR_DUPLICATE_HISTORY';
    const history = JSON.parse(PropertiesService.getScriptProperties().getProperty(historyKey) || '[]');
    history.push(monitoringData);
    
    // Keep last 100 entries
    if (history.length > 100) {
      history.shift();
    }
    
    PropertiesService.getScriptProperties().setProperty(historyKey, JSON.stringify(history));
    
    return monitoringData;
    
  } catch (e) {
    console.error('[MONITOR] Error monitoring duplicate folders:', e);
    return {
      error: String(e),
      timestamp: new Date().toISOString()
    };
  }
}

/**
 * Get monitoring history
 * 
 * Retrieves stored monitoring data for trend analysis.
 */
function getMonitoringHistory() {
  const historyKey = 'MONITOR_DUPLICATE_HISTORY';
  const history = JSON.parse(PropertiesService.getScriptProperties().getProperty(historyKey) || '[]');
  
  if (history.length === 0) {
    console.log('[MONITOR] No history data available');
    return [];
  }
  
  console.log(`[MONITOR] History: ${history.length} entries`);
  
  // Calculate trends
  const recent = history.slice(-10); // Last 10 entries
  const alerts = recent.filter(h => h.status === 'ALERT').length;
  const clean = recent.filter(h => h.status === 'CLEAN').length;
  
  console.log(`[MONITOR] Recent trends (last 10 checks):`);
  console.log(`[MONITOR]   Alerts: ${alerts}`);
  console.log(`[MONITOR]   Clean: ${clean}`);
  
  if (alerts > 0) {
    console.warn(`[MONITOR] ⚠️ ${alerts} alert(s) in recent checks - investigate!`);
  } else {
    console.log('[MONITOR] ✅ No alerts in recent checks');
  }
  
  return history;
}

/**
 * Check lock acquisition in recent runs
 * 
 * This is a helper for manual log analysis. Provides guidance on what to look for.
 */
function checkLockAcquisitionStatus() {
  console.log('[MONITOR] Lock Acquisition Status Check');
  console.log('[MONITOR] ========================================');
  console.log('[MONITOR] Manual log analysis required.');
  console.log('[MONITOR]');
  console.log('[MONITOR] Steps:');
  console.log('[MONITOR] 1. Open Apps Script execution transcript');
  console.log('[MONITOR] 2. Search for: "Attempting to obtain DriveSheets script lock"');
  console.log('[MONITOR] 3. Count total occurrences');
  console.log('[MONITOR] 4. Search for: "Unable to obtain DriveSheets script lock"');
  console.log('[MONITOR] 5. Count failures');
  console.log('[MONITOR] 6. Calculate: (Total - Failures) / Total * 100');
  console.log('[MONITOR]');
  console.log('[MONITOR] Expected: > 95% success rate');
  console.log('[MONITOR]');
  console.log('[MONITOR] Also check for:');
  console.log('[MONITOR] - "another run is already in progress" (expected during overlap)');
  console.log('[MONITOR] - "Failed to release DriveSheets script lock" (should be zero)');
  
  return {
    guidance: 'Manual log analysis required',
    expectedSuccessRate: '> 95%',
    searchTerms: [
      'Attempting to obtain DriveSheets script lock',
      'Unable to obtain DriveSheets script lock',
      'another run is already in progress',
      'Failed to release DriveSheets script lock'
    ]
  };
}

/**
 * Generate monitoring report
 * 
 * Creates a comprehensive monitoring report combining all checks.
 */
function generateMonitoringReport() {
  console.log('========================================');
  console.log('DriveSheetsSync Monitoring Report');
  console.log('========================================\n');
  
  const timestamp = new Date().toISOString();
  console.log('Generated:', timestamp);
  console.log('');
  
  // Check duplicate folders
  console.log('1. Duplicate Folder Check:');
  console.log('---');
  const duplicateCheck = monitorDuplicateFolders();
  if (duplicateCheck) {
    console.log(`   Status: ${duplicateCheck.status}`);
    console.log(`   Duplicate sets: ${duplicateCheck.duplicateSets}`);
    console.log(`   Recent duplicates: ${duplicateCheck.recentDuplicates}`);
  }
  console.log('');
  
  // Check history
  console.log('2. Historical Trends:');
  console.log('---');
  const history = getMonitoringHistory();
  console.log('');
  
  // Lock acquisition guidance
  console.log('3. Lock Acquisition:');
  console.log('---');
  checkLockAcquisitionStatus();
  console.log('');
  
  // Summary
  console.log('========================================');
  console.log('Summary');
  console.log('========================================');
  
  if (duplicateCheck) {
    if (duplicateCheck.status === 'ALERT') {
      console.log('⚠️ ALERT: Recent duplicate folders detected!');
      console.log('   Action: Investigate immediately');
    } else if (duplicateCheck.status === 'INFO') {
      console.log('ℹ️ INFO: Existing duplicates found (pre-fix)');
      console.log('   Action: Monitor for consolidation');
    } else {
      console.log('✅ CLEAN: No duplicate folders');
    }
  }
  
  console.log('\nReport complete.');
  
  return {
    timestamp,
    duplicateCheck,
    history: history.slice(-10), // Last 10 entries
    status: duplicateCheck?.status || 'UNKNOWN'
  };
}

/**
 * Set up automated monitoring
 * 
 * Creates a time-based trigger to run monitoring periodically.
 * Run this once to set up automated monitoring.
 */
function setupAutomatedMonitoring() {
  // Delete existing monitoring triggers
  ScriptApp.getProjectTriggers().forEach(trigger => {
    if (trigger.getHandlerFunction() === 'generateMonitoringReport') {
      ScriptApp.deleteTrigger(trigger);
    }
  });
  
  // Create new trigger (runs daily at 9 AM)
  ScriptApp.newTrigger('generateMonitoringReport')
    .timeBased()
    .everyDays(1)
    .atHour(9)
    .create();
  
  console.log('[MONITOR] ✅ Automated monitoring set up');
  console.log('[MONITOR] Report will run daily at 9 AM');
  console.log('[MONITOR] To disable: delete trigger for generateMonitoringReport');
}

/**
 * Remove automated monitoring
 * 
 * Removes the automated monitoring trigger.
 */
function removeAutomatedMonitoring() {
  let removed = 0;
  ScriptApp.getProjectTriggers().forEach(trigger => {
    if (trigger.getHandlerFunction() === 'generateMonitoringReport') {
      ScriptApp.deleteTrigger(trigger);
      removed++;
    }
  });
  
  console.log(`[MONITOR] Removed ${removed} monitoring trigger(s)`);
}

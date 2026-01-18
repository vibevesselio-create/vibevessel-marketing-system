/**
 * Archive Folders Audit Runner
 * 
 * This script can be run from the Apps Script editor or via clasp run
 * 
 * Usage:
 *   1. From Apps Script editor: Run runArchiveFoldersAudit() function
 *   2. Via clasp: clasp run runArchiveFoldersAudit
 */

/**
 * Main function to run archive folders audit
 * @returns {Object} Audit summary
 */
function runArchiveFoldersAudit() {
  console.log('Starting Archive Folders Audit...\n');
  
  try {
    // Initialize minimal logger for diagnostic
    const UL = {
      debug: (msg, ctx) => console.log(`[DEBUG] ${msg}`, ctx || ''),
      info: (msg, ctx) => console.log(`[INFO] ${msg}`, ctx || ''),
      warn: (msg, ctx) => console.warn(`[WARN] ${msg}`, ctx || ''),
      error: (msg, ctx) => console.error(`[ERROR] ${msg}`, ctx || '')
    };
    
    const summary = ensureArchiveFoldersInWorkspace_(UL);
    
    console.log('\n' + '='.repeat(60));
    console.log('ARCHIVE FOLDERS AUDIT RESULTS');
    console.log('='.repeat(60));
    console.log(`📁 Folders Scanned: ${summary.scanned}`);
    console.log(`❌ Missing Archives: ${summary.missing}`);
    console.log(`✅ Archives Created: ${summary.created}`);
    console.log(`⚠️  Errors: ${summary.errors}`);
    console.log(`⏭️  Skipped: ${summary.skipped ? 'Yes' : 'No'}`);
    console.log('='.repeat(60) + '\n');
    
    if (summary.missing > 0 && summary.created === summary.missing) {
      console.log('✅ SUCCESS: All missing archive folders have been created!');
    } else if (summary.missing > 0) {
      console.log(`⚠️  WARNING: ${summary.missing - summary.created} archive folders could not be created.`);
    } else if (summary.scanned > 0) {
      console.log('✅ SUCCESS: All folders have archive folders!');
    }
    
    return summary;
  } catch (e) {
    console.error('Archive folders audit failed:', e);
    console.error('Stack:', e.stack);
    return { 
      error: String(e), 
      stack: e.stack,
      scanned: 0,
      missing: 0,
      created: 0,
      errors: 1,
      skipped: true
    };
  }
}

























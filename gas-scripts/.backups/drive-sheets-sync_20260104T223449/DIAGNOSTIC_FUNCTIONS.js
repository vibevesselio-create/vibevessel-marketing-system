/**
 * Diagnostic helpers for DriveSheetsSync.
 * Safe to run from Apps Script editor or via clasp.
 */

function _redactDiagnosticValue_(key, value) {
  if (value === null || value === undefined) return value;
  const upperKey = String(key || '').toUpperCase();
  if (upperKey.includes('TOKEN') || upperKey.includes('SECRET') || upperKey.includes('KEY')) {
    return '[REDACTED]';
  }
  return value;
}

function _collectScriptProperties_() {
  const props = PROPS.getProperties();
  const redacted = {};
  Object.keys(props).forEach((key) => {
    redacted[key] = _redactDiagnosticValue_(key, props[key]);
  });
  return redacted;
}

function listTriggers() {
  return ScriptApp.getProjectTriggers().map((t) => {
    let handler = null;
    let eventType = null;
    try {
      handler = t.getHandlerFunction ? t.getHandlerFunction() : null;
      eventType = t.getEventType ? String(t.getEventType()) : null;
    } catch (e) {
      // Keep best-effort data only
    }
    return {
      handler: handler,
      eventType: eventType,
      source: t.getTriggerSource ? String(t.getTriggerSource()) : null,
      uniqueId: t.getUniqueId ? t.getUniqueId() : null
    };
  });
}

function getScriptProperties() {
  return _collectScriptProperties_();
}

function getScriptInfo() {
  return {
    scriptId: ScriptApp.getScriptId(),
    timezone: Session.getScriptTimeZone(),
    userEmail: Session.getActiveUser().getEmail() || null,
    effectiveUserEmail: Session.getEffectiveUser().getEmail() || null,
    triggerCount: ScriptApp.getProjectTriggers().length,
    notionApiVersion: CONFIG.NOTION_VERSION
  };
}

function validateScriptProperties() {
  const required = ['NOTION_API_KEY'];
  const missing = [];
  const warnings = [];

  required.forEach((key) => {
    const value = PROPS.getProperty(key);
    if (!value || !String(value).trim()) {
      missing.push(key);
    }
  });

  if (!PROPS.getProperty('WORKSPACE_DATABASES_FOLDER_ID') && !PROPS.getProperty('WORKSPACE_DATABASES_URL')) {
    warnings.push('WORKSPACE_DATABASES_FOLDER_ID/URL not set - will fallback to default folder.');
  }

  const config = getDatabaseConfig();
  const invalidIds = [];
  Object.entries(config).forEach(([name, id]) => {
    if (!id) return;
    const normalized = String(id).replace(/-/g, '');
    if (!/^[0-9a-f]{32}$/i.test(normalized)) {
      invalidIds.push({ name: name, value: id });
    }
  });

  // Check for DB ID mismatches between script properties and canonical values
  const dbIdMismatches = validateDbIdConsolidation();

  return {
    ok: missing.length === 0 && dbIdMismatches.length === 0,
    missing: missing,
    warnings: warnings,
    invalidDbIds: invalidIds,
    dbIdMismatches: dbIdMismatches
  };
}

/**
 * Validates that all database ID sources are consolidated and consistent.
 * Checks for conflicts between:
 *   - Canonical hardcoded values in getDatabaseConfig()
 *   - Legacy script properties (EXECUTION_LOGS_DB_ID, WORKSPACE_REGISTRY_DB_ID, etc.)
 *   - Environment-specific overrides (DB_ID_{ENV}_{NAME})
 *
 * @returns {Array<Object>} Array of mismatch objects with property, canonical, and actual values
 */
function validateDbIdConsolidation() {
  const mismatches = [];
  const props = PROPS.getProperties();

  // Canonical database IDs (must match getDatabaseConfig() defaults)
  const canonical = {
    AGENT_TASKS_PRIMARY: '26de73616c278038b839c5333237000a',
    AGENT_TASKS_SECONDARY: '284e73616c278018872aeb14e82e0392',
    EXECUTION_LOGS: '27be73616c278033a323dca0fafa80e6',
    WORKSPACE_REGISTRY: '299e73616c2780f1b264f020e4a4b041',
    SCRIPTS: '26ce73616c278178bc77f43aff00eddf',
    PROJECTS: '286e73616c2781ffa450db2ecad4b0ba',
    TASKS: '20fe73616c27814a8f84d3f47b413c2a'
  };

  // Legacy property name mappings to canonical names
  const legacyMappings = {
    'EXECUTION_LOGS_DB_ID': 'EXECUTION_LOGS',
    'WORKSPACE_REGISTRY_DB_ID': 'WORKSPACE_REGISTRY',
    'WORKSPACE_DATABASES_NOTION_DB_ID': 'WORKSPACE_REGISTRY',
    'AGENT_TASKS_DB_ID': 'AGENT_TASKS_SECONDARY',
    'SCRIPTS_DB_ID': 'SCRIPTS',
    'PROJECTS_DB_ID': 'PROJECTS',
    'TASKS_DB_ID': 'TASKS'
  };

  // Check legacy properties for conflicts
  for (const [legacyProp, canonicalName] of Object.entries(legacyMappings)) {
    const propValue = props[legacyProp];
    if (propValue && propValue.trim()) {
      const canonicalValue = canonical[canonicalName];
      const normalizedProp = propValue.replace(/-/g, '').toLowerCase();
      const normalizedCanonical = canonicalValue.replace(/-/g, '').toLowerCase();

      if (normalizedProp !== normalizedCanonical) {
        mismatches.push({
          property: legacyProp,
          canonicalName: canonicalName,
          canonicalValue: canonicalValue,
          actualValue: propValue,
          resolution: 'DELETE_LEGACY_PROPERTY'
        });
      }
    }
  }

  // Check environment-specific overrides
  const env = props['LOG_ENV'] || 'DEV';
  const envPrefix = `DB_ID_${env}_`;

  for (const [propName, propValue] of Object.entries(props)) {
    if (propName.startsWith(envPrefix)) {
      const dbName = propName.replace(envPrefix, '').toUpperCase();
      const canonicalValue = canonical[dbName];

      if (canonicalValue) {
        const normalizedProp = propValue.replace(/-/g, '').toLowerCase();
        const normalizedCanonical = canonicalValue.replace(/-/g, '').toLowerCase();

        if (normalizedProp !== normalizedCanonical) {
          mismatches.push({
            property: propName,
            canonicalName: dbName,
            canonicalValue: canonicalValue,
            actualValue: propValue,
            resolution: 'UPDATE_OR_DELETE_OVERRIDE'
          });
        }
      }
    }
  }

  return mismatches;
}

/**
 * Cleans up legacy database ID properties that conflict with canonical values.
 * Should be run once to consolidate all DB IDs to use canonical values.
 *
 * @param {boolean} dryRun - If true, only reports what would be changed
 * @returns {Object} Summary of changes made or proposed
 */
function consolidateDbIds(dryRun) {
  if (dryRun === undefined) dryRun = true;

  const mismatches = validateDbIdConsolidation();
  const changes = [];

  for (const mismatch of mismatches) {
    if (mismatch.resolution === 'DELETE_LEGACY_PROPERTY') {
      changes.push({
        action: 'DELETE',
        property: mismatch.property,
        oldValue: mismatch.actualValue,
        reason: `Conflicts with canonical ${mismatch.canonicalName}: ${mismatch.canonicalValue}`
      });

      if (!dryRun) {
        PROPS.deleteProperty(mismatch.property);
      }
    } else if (mismatch.resolution === 'UPDATE_OR_DELETE_OVERRIDE') {
      changes.push({
        action: 'DELETE',
        property: mismatch.property,
        oldValue: mismatch.actualValue,
        reason: `Environment override conflicts with canonical ${mismatch.canonicalName}: ${mismatch.canonicalValue}`
      });

      if (!dryRun) {
        PROPS.deleteProperty(mismatch.property);
      }
    }
  }

  return {
    dryRun: dryRun,
    mismatchesFound: mismatches.length,
    changesApplied: dryRun ? 0 : changes.length,
    changes: changes
  };
}

function checkWorkspaceDatabasesFolder() {
  const parent = resolveDriveParent_();
  const folder = DriveApp.getFolderById(parent.id);
  const it = folder.getFolders();
  let total = 0;
  let missing = 0;
  const samples = [];

  while (it.hasNext()) {
    const child = it.next();
    total += 1;
    const archiveIt = child.getFoldersByName('.archive');
    if (!archiveIt.hasNext()) {
      missing += 1;
      if (samples.length < 20) {
        samples.push(child.getName());
      }
    }
  }

  return {
    parentFolderId: parent.id,
    parentFolderUrl: parent.url,
    totalFolders: total,
    missingArchiveCount: missing,
    missingArchiveSamples: samples
  };
}

function runDiagnostics() {
  return {
    scriptInfo: getScriptInfo(),
    triggers: listTriggers(),
    scriptProperties: getScriptProperties(),
    propertyValidation: validateScriptProperties(),
    dbIdConsolidation: {
      mismatches: validateDbIdConsolidation(),
      proposedChanges: consolidateDbIds(true).changes
    },
    workspaceDatabases: checkWorkspaceDatabasesFolder()
  };
}

function exportDiagnosticsToSheet() {
  const diagnostics = runDiagnostics();
  const parent = resolveDriveParent_();
  const ss = getOrCreateRegistrySpreadsheet_(parent.id);
  let sheet = ss.getSheetByName('Diagnostics');
  if (!sheet) {
    sheet = ss.insertSheet('Diagnostics');
  }
  sheet.clearContents();
  const generatedAt = new Date().toISOString();
  sheet.getRange(1, 1, 1, 2).setValues([['Generated At', generatedAt]]);
  const rows = [
    ['scriptInfo', JSON.stringify(diagnostics.scriptInfo)],
    ['triggers', JSON.stringify(diagnostics.triggers)],
    ['scriptProperties', JSON.stringify(diagnostics.scriptProperties)],
    ['propertyValidation', JSON.stringify(diagnostics.propertyValidation)],
    ['dbIdConsolidation', JSON.stringify(diagnostics.dbIdConsolidation)],
    ['workspaceDatabases', JSON.stringify(diagnostics.workspaceDatabases)]
  ];
  sheet.getRange(3, 1, rows.length, 2).setValues(rows);
  return {
    spreadsheetId: ss.getId(),
    spreadsheetUrl: ss.getUrl(),
    sheetName: 'Diagnostics',
    generatedAt: generatedAt
  };
}

/**
 * Test Scripts database access to verify the normalizeNotionId_ fix.
 * This function tests whether the Scripts database can be accessed
 * after the ID normalization fix was applied.
 *
 * @returns {Object} Result containing success status and details
 */
function testScriptsDatabaseAccess() {
  const scriptsId = CONFIG.SCRIPTS_DB_ID || DB_CONFIG.SCRIPTS;
  console.log('Scripts DB ID (raw):', scriptsId);
  console.log('Scripts DB ID (normalized):', normalizeNotionId_(scriptsId));

  try {
    // Test the resolution function with the Scripts database ID
    const dsId = resolveDatabaseToDataSourceId_(scriptsId, null);
    console.log('Resolved data_source_id:', dsId);

    if (dsId) {
      // Try to fetch the data source to confirm it's accessible
      const ds = notionFetch_(`data_sources/${dsId}`, 'GET');
      console.log('Data source accessible:', ds.id === dsId);
      console.log('Data source title:', ds.title || '[No title]');

      return {
        success: true,
        scriptsDbId: scriptsId,
        normalizedId: normalizeNotionId_(scriptsId),
        dataSourceId: dsId,
        accessible: true,
        title: ds.title || null
      };
    } else {
      return {
        success: false,
        scriptsDbId: scriptsId,
        normalizedId: normalizeNotionId_(scriptsId),
        dataSourceId: null,
        error: 'resolveDatabaseToDataSourceId_ returned null'
      };
    }
  } catch (e) {
    console.error('Failed:', e.message);
    return {
      success: false,
      scriptsDbId: scriptsId,
      normalizedId: normalizeNotionId_(scriptsId),
      error: e.message,
      stack: e.stack || 'No stack trace'
    };
  }
}

/**
 * Test normalizeNotionId_ function with various input formats.
 *
 * @returns {Object} Test results for ID normalization
 */
function testNormalizeNotionId() {
  const testCases = [
    { input: '26ce73616c278178bc77f43aff00eddf', expected: '26ce7361-6c27-8178-bc77-f43aff00eddf' },
    { input: '26ce7361-6c27-8178-bc77-f43aff00eddf', expected: '26ce7361-6c27-8178-bc77-f43aff00eddf' },
    { input: '', expected: '' },
    { input: null, expected: null },
    { input: 'invalid', expected: 'invalid' },
    { input: '12345', expected: '12345' }
  ];

  const results = testCases.map(tc => {
    const actual = normalizeNotionId_(tc.input);
    const passed = actual === tc.expected;
    return {
      input: tc.input,
      expected: tc.expected,
      actual: actual,
      passed: passed
    };
  });

  const allPassed = results.every(r => r.passed);
  console.log('All tests passed:', allPassed);

  return {
    allPassed: allPassed,
    results: results
  };
}

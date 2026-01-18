/**
 * Notion ↔ Google Drive + Sheets Sync
 * Two-way rows + Two-way SCHEMA + safer rich_text chunking
 * API version: 2025-09-03
 *
 * VERSION: 2.5 - Fix missing ensureItemTypePropertyExists_ function (2026-01-14)
 *
 * IMPROVEMENTS IN 2.5:
 *   - BUGFIX: Added missing ensureItemTypePropertyExists_ function definition
 *     * Resolves ReferenceError that was causing all database processing to fail
 *     * Function gracefully skips when ITEM_TYPES database is not configured
 *     * Creates Item-Type relation property on databases when Item-Types DB is available
 *     * Follows existing patterns from ensurePropertyExists_ for consistency
 *
 * IMPROVEMENTS IN 2.4:
 *   - Multi-Script Compatibility & Deduplication - FULLY IMPLEMENTED
 *     * Enhanced deduplication logic respects both DriveSheetsSync (.md) and Project Manager Bot (.json) files
 *     * Task-specific file detection using both short ID (8 chars) and full ID (with/without dashes)
 *     * Script-aware cleanup: only deletes own files (.md) to respect Project Manager Bot files (.json)
 *     * Age-based deduplication: only deletes files older than 10 minutes to avoid conflicts with active processes
 *     * Comprehensive logging identifies file format and source script for debugging
 *     * Idempotent behavior: returns success if any trigger file exists for the task (regardless of format)
 *     * Preserves 2-way Google Drive ↔ Notion sync functionality
 * 
 * IMPROVEMENTS IN 2.3:
 *   - Dynamic Property Validation with Intelligent Name Variations - FULLY IMPLEMENTED
 *     * Enhanced property matching with 10+ variation strategies
 *     * Retry logic with configurable max attempts (default: 3)
 *     * Property type-aware matching with naming hints
 *     * Comprehensive match reporting for debugging
 *     * Enhanced property caching to reduce API calls
 *     * Zero breaking changes - backward compatible with existing callers
 * 
 * IMPROVEMENTS IN 2.2:
 *   - MGM Triple Logging Infrastructure (Priority 0) - FULLY IMPLEMENTED
 *     * Canonical path: /My Drive/Seren Internal/Automation Files/script_runs/logs/
 *     * File naming convention v2 with status in filename
 *     * JSONL format with all required MGM fields
 *     * Plaintext log mirror with structured formatting
 *     * Path validation enforcement
 *   - Database ID Configuration Management (Priority 1) - IMPLEMENTED
 *     * Environment-aware database ID loading
 *     * Configuration-based (not hardcoded) database IDs
 *   - Comprehensive Property Validation and Auto-Creation (Priority 0) - FULLY IMPLEMENTED
 *     * Validates required properties exist before operations
 *     * Auto-creates missing required properties with correct types
 *     * Validates properties for Execution-Logs, Workspace Registry, and Agent-Tasks databases
 *     * Ensures properties exist before querying, creating pages, or updating values
 *     * Graceful error handling with detailed logging
 *     * Property type validation and mismatch detection
 *     * UUID validation
 *   - Lifecycle Tracking (Priority 2) - IMPLEMENTED
 *     * Automatic lifecycle property setting on new pages
 *     * Lifecycle transition tracking
 *   - Relation Validation (Priority 2) - IMPLEMENTED
 *     * Pre-check validation of relation targets
 *     * Automatic removal of invalid relations
 *   - Single In Progress Invariant Validation - IMPLEMENTED
 *     * Non-blocking validation for Agent-Tasks database
 *     * Violation logging with task IDs
 * 
 * IMPROVEMENTS IN 2.1:
 *   - Enhanced property matching with case-insensitive fallback
 *   - Guaranteed page body content population
 *   - Improved error handling for property updates
 *   - Performance metrics tracking
 *   - Better execution log population reliability
 *
 * MODIFICATION: Agent-Tasks database (26de73616c278038b839c5333237000a) 
 * is ALWAYS processed as the 2nd database in each run, regardless of rotation.
 *
 * ENHANCED LOGGING: Comprehensive execution logs with full content in Notion page body,
 * detailed error tracking, script configuration, and maximum agent value.
 *
 * AUDIT FIXES APPLIED:
 *   - Fix #1: Execution log population - Enhanced error handling and property matching
 *   - Fix #2: Error logging - Full context and stack traces captured
 *   - Fix #3: Single In Progress invariant validation for Agent-Tasks
 *   - Fix #4: Data integrity validation - Post-sync comparison
 *   - Fix #5: Performance optimization - Better error handling and property batching
 *
 * What this run does for each Notion database:
 *   1) If a CSV already exists:
 *        • Read the CSV header (row 1) and type row (row 2).
 *        • Create any missing Notion properties to match new CSV columns.
 *        • Delete Notion properties removed from the CSV (safe list only).
 *        • Upsert rows from CSV back into Notion pages.
 *   2) Export a fresh CSV from Notion that mirrors the final schema + data.
 *   3) Update a registry Google Sheet for quick visibility.
 *   4) Enhanced logging:
 *        • Human .log and JSONL saved to Drive
 *        • Console
 *        • COMPREHENSIVE Notion Execution Logs database page with:
 *          - Full execution log in page body
 *          - Detailed error tracking in properties
 *          - Complete script configuration and metadata
 *          - Database processing results
 */

// MGM Database Configuration - DYNAMIC DISCOVERY (no hardcoded IDs)
// All database IDs are discovered dynamically by searching Notion workspace
// Override via script properties: DB_ID_{ENV}_{NAME} or DB_CACHE_{NAME}

/**
 * Database name to config key mapping for dynamic discovery
 * Maps friendly database names to their config keys
 */
const DB_NAME_MAP = {
  'Agent-Tasks': ['AGENT_TASKS_PRIMARY', 'AGENT_TASKS_SECONDARY'],
  'Execution-Logs': ['EXECUTION_LOGS'],
  'Workspace-Registry': ['WORKSPACE_REGISTRY'],
  'Scripts': ['SCRIPTS'],
  'Projects': ['PROJECTS'],
  'Tasks': ['TASKS'],
  'Item-Types': ['ITEM_TYPES']
};

/**
 * Discovers a database ID by name using Notion search API
 * Caches results in script properties to avoid repeated lookups
 * @param {string} dbName - The database name to search for
 * @returns {string|null} The database ID if found, null otherwise
 */
function discoverDatabaseByName_(dbName) {
  const scriptProps = PropertiesService.getScriptProperties();
  const cacheKey = `DB_CACHE_${dbName.replace(/[^a-zA-Z0-9]/g, '_').toUpperCase()}`;

  // Check cache first
  const cached = scriptProps.getProperty(cacheKey);
  if (cached) {
    return cached;
  }

  // Search Notion for the database by name
  try {
    const searchBody = {
      query: dbName,
      page_size: 100,
      filter: { property: 'object', value: 'data_source' }
    };

    let cursor = null;
    let loops = 0;

    while (loops < 10) {
      if (cursor) searchBody.start_cursor = cursor;

      const response = UrlFetchApp.fetch('https://api.notion.com/v1/search', {
        method: 'POST',
        headers: {
          'Authorization': 'Bearer ' + PropertiesService.getScriptProperties().getProperty('NOTION_TOKEN'),
          'Notion-Version': '2025-09-03',
          'Content-Type': 'application/json'
        },
        payload: JSON.stringify(searchBody),
        muteHttpExceptions: true
      });

      const result = JSON.parse(response.getContentText());

      if (result.results) {
        for (const ds of result.results) {
          // Match by title (case-insensitive)
          const title = ds.title?.[0]?.plain_text || ds.name || '';
          if (title.toLowerCase() === dbName.toLowerCase()) {
            const foundId = ds.id?.replace(/-/g, '') || '';
            if (foundId) {
              // Cache the result
              scriptProps.setProperty(cacheKey, foundId);
              console.log(`[INFO] Discovered database "${dbName}" with ID: ${foundId}`);
              return foundId;
            }
          }
        }
      }

      if (!result.has_more) break;
      cursor = result.next_cursor;
      loops++;
    }

    console.warn(`[WARN] Could not find database by name: ${dbName}`);
    return null;
  } catch (e) {
    console.error(`[ERROR] Failed to discover database "${dbName}": ${e}`);
    return null;
  }
}

/**
 * Clears the database ID cache - run this if databases are recreated
 */
function clearDatabaseCache() {
  const scriptProps = PropertiesService.getScriptProperties();
  const props = scriptProps.getProperties();
  let cleared = 0;

  for (const key of Object.keys(props)) {
    if (key.startsWith('DB_CACHE_')) {
      scriptProps.deleteProperty(key);
      cleared++;
    }
  }

  console.log(`[INFO] Cleared ${cleared} cached database IDs`);
  return cleared;
}

/**
 * Gets database configuration - dynamically discovers IDs if not cached
 * Environment-specific overrides can be set via script properties: DB_ID_{ENV}_{NAME}
 */
function getDatabaseConfig() {
  const scriptProps = PropertiesService.getScriptProperties();
  const env = scriptProps.getProperty('LOG_ENV') || 'DEV';
  const envPrefix = `DB_ID_${env}_`;

  // Start with empty config - NO HARDCODED DEFAULTS
  const config = {};

  // Load environment-specific overrides from script properties
  const props = scriptProps.getProperties();
  for (const [key, value] of Object.entries(props)) {
    if (key.startsWith(envPrefix)) {
      const dbName = key.replace(envPrefix, '').toUpperCase();
      config[dbName] = value;
    }
    // Also check for direct DB_ID_ properties (without env)
    if (key.startsWith('DB_ID_') && !key.includes('_DEV_') && !key.includes('_PROD_')) {
      const dbName = key.replace('DB_ID_', '').toUpperCase();
      if (!config[dbName]) {
        config[dbName] = value;
      }
    }
  }

  // Also check legacy property names
  const legacyMappings = {
    'ITEM_TYPES_DB_ID': 'ITEM_TYPES',
    'EXECUTION_LOGS_DB_ID': 'EXECUTION_LOGS',
    'WORKSPACE_REGISTRY_DB_ID': 'WORKSPACE_REGISTRY'
  };

  for (const [propName, configKey] of Object.entries(legacyMappings)) {
    const value = scriptProps.getProperty(propName);
    if (value && !config[configKey]) {
      config[configKey] = value;
    }
  }

  // Dynamic discovery - find missing databases by name
  // This happens lazily when the config is first loaded
  for (const [dbName, configKeys] of Object.entries(DB_NAME_MAP)) {
    for (const configKey of configKeys) {
      if (!config[configKey]) {
        // Try to discover from cache first
        const cacheKey = `DB_CACHE_${dbName.replace(/[^a-zA-Z0-9]/g, '_').toUpperCase()}`;
        const cached = props[cacheKey];
        if (cached) {
          config[configKey] = cached;
        }
        // Note: Full discovery is deferred until first use to avoid slow startup
        // The discoverDatabaseByName_ function will be called when actually needed
      }
    }
  }

  // Validate UUID format for any configured IDs
  for (const [name, id] of Object.entries(config)) {
    if (!id) continue;
    const normalizedId = String(id).replace(/-/g, '');
    if (!/^[0-9a-f]{32}$/i.test(normalizedId)) {
      console.warn(`[WARN] Invalid database ID format for ${name}: ${id}`);
    }
  }

  return config;
}

/**
 * Gets a specific database ID, discovering it dynamically if needed
 * This is the primary entry point for getting database IDs
 * @param {string} configKey - The config key (e.g., 'AGENT_TASKS_PRIMARY')
 * @returns {string|null} The database ID
 */
function getDatabaseId_(configKey) {
  // Check if already in config
  if (DB_CONFIG[configKey]) {
    return DB_CONFIG[configKey];
  }

  // Find the database name for this config key
  for (const [dbName, configKeys] of Object.entries(DB_NAME_MAP)) {
    if (configKeys.includes(configKey)) {
      // Discover and cache the ID
      const foundId = discoverDatabaseByName_(dbName);
      if (foundId) {
        DB_CONFIG[configKey] = foundId;
        return foundId;
      }
    }
  }

  console.warn(`[WARN] Could not find database for config key: ${configKey}`);
  return null;
}

const DB_CONFIG = getDatabaseConfig();

/**
 * External Database IDs Configuration
 * ===================================
 * 
 * All database IDs are loaded via getDatabaseConfig() with environment support.
 * Environment-specific overrides can be set via script properties: DB_ID_{ENV}_{NAME}
 * 
 * Database IDs:
 * - EXECUTION_LOGS_DB_ID: Notion Execution-Logs database for structured run logs
 *   → Used by UnifiedLoggerGAS to create execution log pages
 *   → Required properties: Name, Start Time, End Time, Duration (s), Final Status, etc.
 * 
 * - WORKSPACE_REGISTRY_DB_ID: Notion Workspace Registry database for database metadata
 *   → Tracks all Notion data sources with properties, row counts, sync status
 *   → Used for round-robin processing and workspace observability
 *   → Required properties: Database Name, Data Source ID, URL, Status, Row Count, etc.
 * 
 * - AGENT_TASKS_DB_IDS: Notion Agent-Tasks databases (primary + secondary)
 *   → Always processed as 2nd database in each run (regardless of rotation)
 *   → Used for task management and agent coordination
 *   → Validates "Single In Progress" invariant
 * 
 * - WORKSPACE_DATABASES_FOLDER_ID: Google Drive folder for CSV exports
 *   → Created/validated via DRIVE_PARENT_FALLBACK_NAME if not set
 *   → Contains one subfolder per data source (Name + ID)
 *   → Each subfolder contains current CSV + archive folder
 * 
 * - PROJECTS_DB_ID, TASKS_DB_ID: Additional workspace databases (if configured)
 */
const CONFIG = {
  NOTION_VERSION: '2025-09-03',
  API_RETRY_COUNT: 3,
  API_RETRY_DELAY_MS: 1000,
  API_RATE_LIMIT_DELAY_MS: 800,

  BATCH_SIZE: 3,
  MAX_RUNTIME_MS: 29 * 60 * 1000,
  MAX_PAGES_PER_DATA_SOURCE: 1000,

  // MGM: Database IDs loaded from configuration (environment-aware)
  // Note: AGENT_TASKS_PRIMARY (legacy) may return 404 - use SECONDARY as primary
  // Filter to only include accessible databases at runtime
  AGENT_TASKS_DB_IDS: [DB_CONFIG.AGENT_TASKS_SECONDARY, DB_CONFIG.AGENT_TASKS_PRIMARY],
  AGENT_TASKS_DB_IDS_FALLBACK: [DB_CONFIG.AGENT_TASKS_PRIMARY, DB_CONFIG.AGENT_TASKS_SECONDARY], // Legacy order for reference
  AGENT_TASKS_DB_NAME: 'Agent-Tasks',
  EXECUTION_LOGS_DB_ID: DB_CONFIG.EXECUTION_LOGS,
  WORKSPACE_REGISTRY_DB_ID: DB_CONFIG.WORKSPACE_REGISTRY,
  SCRIPTS_DB_ID: DB_CONFIG.SCRIPTS,
  PROJECTS_DB_ID: DB_CONFIG.PROJECTS,
  TASKS_DB_ID: DB_CONFIG.TASKS,
  
  // Database parent page for creating new databases
  DATABASE_PARENT_PAGE_ID: '26ce73616c278141af54dd115915445c', // database-parent-page

  STATE_KEY_PREFIX: 'nds_drive_sheets_',
  DRIVE_PARENT_FALLBACK_NAME: 'workspace-databases',

  REGISTRY_SPREADSHEET_NAME: 'Notion Meta-DB Registry',
  SHEET_DATABASES: 'Databases',
  SHEET_PROPERTIES: 'Properties',

  LOGGING: {
    SCRIPT_NAME_PROP: 'LOG_SCRIPT_NAME',
    ENV_PROP: 'LOG_ENV',
    DEFAULT_SCRIPT_NAME: 'DriveSheetsSync v2.6',
    DEFAULT_ENV: 'DEV',
    ROOT_FOLDER_ID_PROP: 'LOG_ROOT_FOLDER_ID',
    FLUSH_LINES: 20,
    FLUSH_MS: 10000
  },

  SYNC: {
    CONFLICT_MODE: 'guard',      // 'guard' | 'csv_wins'
    CSV_AUTHORIZES_SCHEMA: true, // CSV may add/delete schema in Notion
    ALLOW_SCHEMA_DELETIONS: false, // Guard against accidental property drops (renames show as add+delete)
    ALLOWED_SYNC_PROPS: [],      // if non-empty, only these property names sync values back to Notion
    ENABLE_LIFECYCLE_TRACKING: true,  // MGM: Track lifecycle state transitions
    ENABLE_RELATION_VALIDATION: true,  // MGM: Validate relations before creating
    ENABLE_MARKDOWN_SYNC: true,  // Enable 2-way sync for individual markdown item files in clone directories
    ENABLE_MULTI_FILE_SYNC: true,  // Enable 2-way sync for all file types (not just markdown)
    REQUIRE_ITEM_TYPE: true,  // Require Item-Type relation property on all database items
    ITEM_TYPE_PROPERTY_NAME: 'Item-Type',  // Name of the Item-Type relation property
    LOCK_WAIT_MS: 8000               // Concurrency guard wait time for time-based triggers
  }
};

const PROPS = PropertiesService.getScriptProperties();

/* ============================== CLIENT CONTEXT DETECTION ============================== */
/**
 * Multi-Account Google Drive For Desktop Integration
 * Detects client context and local Drive path for deployment to multiple Google accounts.
 *
 * This enables DriveSheetsSync to be deployed to multiple Google accounts, each linked
 * to a different client in Notion. The script automatically detects which account it's
 * running under and registers the appropriate local Drive folder in Notion.
 */

/**
 * Maps Google account emails to client identifiers
 * @const {Object}
 */
const EMAIL_TO_CLIENT = {
  'brian@serenmedia.co': 'seren-media-internal',
  'vibe.vessel.io@gmail.com': 'vibe-vessel',
  'marketing@oceanfrontiers.com': 'ocean-frontiers'
};

/**
 * Maps client identifiers to their local Google Drive For Desktop paths
 * @const {Object}
 */
const CLIENT_TO_LOCAL_PATH = {
  'seren-media-internal': '/Users/brianhellemn/Library/CloudStorage/GoogleDrive-brian@serenmedia.co/My Drive',
  'vibe-vessel': '/Users/brianhellemn/Library/CloudStorage/GoogleDrive-vibe.vessel.io@gmail.com/My Drive',
  'ocean-frontiers': '/Users/brianhellemn/Library/CloudStorage/GoogleDrive-marketing@oceanfrontiers.com/My Drive'
};

/**
 * Maps client identifiers to client names in Notion
 * @const {Object}
 */
const CLIENT_TO_NAME = {
  'seren-media-internal': 'Seren Media',
  'vibe-vessel': 'Vibe Vessel',
  'ocean-frontiers': 'Ocean Frontiers'
};

/** Notion Folders database ID */
const FOLDERS_DB_ID = '26ce73616c2781bb81b7dd43760ee6cc';

/** Notion Clients database ID */
const CLIENTS_DB_ID = '20fe73616c278100a2aee337bfdcb535';

/**
 * Get the client context for this script instance.
 * Detection priority: CLIENT_ID prop > CLIENT_EMAIL prop > Active user email
 * @returns {string|null} Client identifier or null if not identified
 */
function getClientContext() {
  // First, check explicit CLIENT_ID script property
  const clientId = PROPS.getProperty('CLIENT_ID');
  if (clientId && clientId.trim()) {
    return clientId.trim();
  }

  // Second, check CLIENT_EMAIL script property
  const clientEmail = PROPS.getProperty('CLIENT_EMAIL');
  if (clientEmail && EMAIL_TO_CLIENT[clientEmail]) {
    return EMAIL_TO_CLIENT[clientEmail];
  }

  // Third, try to detect from active user email
  try {
    const activeEmail = Session.getActiveUser().getEmail();
    if (activeEmail && EMAIL_TO_CLIENT[activeEmail]) {
      return EMAIL_TO_CLIENT[activeEmail];
    }
  } catch (e) {
    // Session may not have access to email in some trigger contexts
  }

  return null;
}

/**
 * Get the local Google Drive For Desktop path for the current client context.
 * @returns {string|null} Local filesystem path or null if not identified
 */
function getLocalDrivePath() {
  const clientContext = getClientContext();
  if (clientContext && CLIENT_TO_LOCAL_PATH[clientContext]) {
    return CLIENT_TO_LOCAL_PATH[clientContext];
  }
  return null;
}

/**
 * Get the client name for the current context (for display in Notion).
 * @returns {string} Client name or 'Unknown' if not identified
 */
function getClientName() {
  const clientContext = getClientContext();
  return CLIENT_TO_NAME[clientContext] || 'Unknown';
}

/**
 * Get the current user's email (from property or active session).
 * @returns {string|null} Email address or null if not available
 */
function getClientEmail() {
  // First check script property
  const propEmail = PROPS.getProperty('CLIENT_EMAIL');
  if (propEmail && propEmail.trim()) {
    return propEmail.trim();
  }

  // Fall back to active user
  try {
    return Session.getActiveUser().getEmail() || null;
  } catch (e) {
    return null;
  }
}

/**
 * Registers the local Google Drive For Desktop sync folder in Notion Folders database.
 * Called during script initialization to ensure the folder entry exists.
 *
 * @param {UnifiedLoggerGAS} UL - Unified logger instance (optional)
 * @returns {string|null} Notion page ID of folder entry, or null if failed
 */
function registerLocalDriveFolderInNotion_(UL) {
  try {
    const localPath = getLocalDrivePath();
    const clientContext = getClientContext();
    const clientEmail = getClientEmail();

    if (!localPath) {
      UL?.warn?.('Cannot register local Drive folder - client context not identified', {
        clientContext: clientContext,
        clientEmail: clientEmail
      });
      return null;
    }

    UL?.info?.('Registering local Drive folder in Notion', {
      localPath: localPath,
      clientContext: clientContext,
      clientEmail: clientEmail
    });

    // Resolve Folders database to data_source_id
    const foldersDsId = resolveDatabaseToDataSourceId_(FOLDERS_DB_ID, UL);

    // Check if folder entry already exists
    const existingId = findFolderEntryByPath_(FOLDERS_DB_ID, foldersDsId, localPath, UL);

    // Get client ID from Notion Clients database
    const clientNotionId = getClientIdFromNotion_(clientContext, UL);

    // Get script page ID (DriveSheetsSync)
    const scriptPageId = findScriptPageInNotion_(UL);

    // Build properties
    const clientName = getClientName();
    const props = {
      'Script Name': { title: [{ type: 'text', text: { content: `Google Drive For Desktop - ${clientName}` } }] },

      'Absolute Path': { rich_text: richTextChunks_(localPath) },
      'Folder Path': { rich_text: richTextChunks_(localPath) },
      'Folder Name': { rich_text: richTextChunks_('My Drive') },
      'Folder Type': { select: { name: 'root' } },
      'Folder Depth': { number: 0 },
      'Folder Role': { multi_select: [
        { name: 'Script Root' },
        { name: 'Logs Root' },
        { name: 'Config Root' }
      ]},
      'Environment': { select: { name: clientContext === 'seren-media-internal' ? 'DEV' : 'PROD' } },
      'Data Source': { select: { name: 'Google Drive' } },
      'Storage Location': { multi_select: [{ name: 'Local File System' }] },
      'Path Verified': { checkbox: true },
      'Path Verified At': { date: { start: nowIso() } },
      'Last Sync Time': { date: { start: nowIso() } },
      'Sync Status': { select: { name: 'Synced' } },
      'Description': { rich_text: richTextChunks_(`Google Drive For Desktop sync folder for ${clientEmail || clientContext}. Managed by DriveSheetsSync.`) }
    };

    // Add client relation if available
    if (clientNotionId) {
      props['Clients'] = { relation: [{ id: clientNotionId }] };
    }

    // Add script relation if available
    if (scriptPageId) {
      props['Scripts'] = { relation: [{ id: scriptPageId }] };
    }

    // Filter properties to existing schema
    const safeProps = _filterDbPropsToExisting_(FOLDERS_DB_ID, props);

    if (existingId) {
      // Update existing entry
      notionFetch_(`pages/${existingId}`, 'PATCH', { properties: safeProps });
      UL?.info?.('Updated local Drive folder entry in Notion', {
        pageId: existingId,
        localPath: localPath,
        clientContext: clientContext
      });
      return existingId;
    } else {
      // Create new entry
      const parent = foldersDsId ?
        { type: 'data_source_id', data_source_id: foldersDsId } :
        { type: 'database_id', database_id: FOLDERS_DB_ID };

      const newPage = notionFetch_('pages', 'POST', { parent: parent, properties: safeProps });
      UL?.info?.('Created local Drive folder entry in Notion', {
        pageId: newPage.id,
        localPath: localPath,
        clientContext: clientContext
      });
      return newPage.id;
    }
  } catch (e) {
    UL?.error?.('Failed to register local Drive folder in Notion', {
      error: String(e),
      stack: e.stack
    });
    return null;
  }
}

/**
 * Finds existing folder entry by absolute path in Notion Folders database.
 * @param {string} dbId - Database ID
 * @param {string} dsId - Data source ID (optional)
 * @param {string} absolutePath - Absolute path to search for
 * @param {UnifiedLoggerGAS} UL - Logger instance
 * @returns {string|null} Page ID if found, null otherwise
 */
function findFolderEntryByPath_(dbId, dsId, absolutePath, UL) {
  try {
    // Only query if we have a valid data_source_id - skip if database is not accessible
    if (!dsId) {
      UL?.debug?.('Cannot query Folders database by path - database not accessible via data_source_id', {
        dbId: dbId,
        absolutePath: absolutePath
      });
      return null;
    }

    const queryResource = `data_sources/${dsId}/query`;
    const body = {
      filter: {
        property: 'Folder Path',
        rich_text: { equals: absolutePath }
      },
      page_size: 1
    };
    const res = notionFetch_(queryResource, 'POST', body);
    return (res.results && res.results.length > 0) ? res.results[0].id : null;
  } catch (e) {
    UL?.warn?.('Could not search for existing folder entry', { error: String(e) });
    return null;
  }
}

/**
 * Gets or creates a folder entry in Notion Folders database for a Google Drive folder.
 * Tracks all folders created, queried, or processed by the script.
 * @param {GoogleAppsScript.Drive.Folder} driveFolder - Google Drive folder
 * @param {UnifiedLoggerGAS} UL - Logger instance
 * @returns {string|null} Notion page ID of folder entry, or null if failed
 */
function getOrCreateFolderInNotion_(driveFolder, UL) {
  try {
    if (!driveFolder) {
      UL?.warn?.('Cannot track folder - folder is null');
      return null;
    }
    
    const folderId = driveFolder.getId();
    const folderName = driveFolder.getName();
    const folderUrl = driveFolder.getUrl();
    const folderPath = getFolderAbsolutePath_(driveFolder);
    
    if (!folderPath) {
      UL?.warn?.('Cannot track folder - could not determine absolute path', {
        folderName: folderName,
        folderId: folderId
      });
      return null;
    }
    
    // Resolve Folders database to data_source_id
    const foldersDsId = resolveDatabaseToDataSourceId_(FOLDERS_DB_ID, UL);
    
    // Check if folder entry already exists
    let existingId = findFolderEntryByPath_(FOLDERS_DB_ID, foldersDsId, folderPath, UL);
    
    // Note: Folder ID property queries removed - Folders database schema uses 'Folder Path' as the unique identifier
    // If folder wasn't found by path above, it doesn't exist and will be created below
    
    // Get client context
    const clientContext = getClientContext();
    const clientEmail = getClientEmail();
    const clientName = getClientName();
    const clientNotionId = getClientIdFromNotion_(clientContext, UL);
    const scriptPageId = findScriptPageInNotion_(UL);
    
    // Calculate folder depth
    const folderDepth = calculateFolderDepth_(folderPath);
    
    // Determine folder type
    let folderType = 'subfolder';
    if (folderDepth === 0) {
      folderType = 'root';
    } else if (folderName === 'workspace-databases' || folderName.includes('workspace-databases')) {
      folderType = 'workspace-databases';
    } else if (folderName.startsWith('.') || folderName === '.archive') {
      folderType = 'system';
    }
    
    // Build properties
    const props = {
      'Name': { title: [{ type: 'text', text: { content: folderName } }] },
      'Absolute Path': { rich_text: richTextChunks_(folderPath) },
      'Folder Path': { rich_text: richTextChunks_(folderPath) },
      'Folder Name': { rich_text: richTextChunks_(folderName) },
      'Folder Type': { select: { name: folderType } },
      'Folder Depth': { number: folderDepth },
      'Data Source': { select: { name: 'Google Drive' } },
      'Storage Location': { multi_select: [{ name: 'Local File System' }] },
      'Last Sync Time': { date: { start: nowIso() } },
      'Sync Status': { select: { name: 'Synced' } },
      'Description': { rich_text: richTextChunks_(`Google Drive folder tracked by DriveSheetsSync. Path: ${folderPath}`) }
    };
    
    // Add folder URL if available
    if (folderUrl) {
      props['URL'] = { url: folderUrl };
      props['Google Drive URL'] = { url: folderUrl };
    }
    
    // Add folder ID
    props['Folder ID'] = { rich_text: richTextChunks_(folderId) };
    props['Google Drive Folder ID'] = { rich_text: richTextChunks_(folderId) };
    
    // Add client relation if available
    if (clientNotionId) {
      props['Clients'] = { relation: [{ id: clientNotionId }] };
    }
    
    // Add script relation if available
    if (scriptPageId) {
      props['Scripts'] = { relation: [{ id: scriptPageId }] };
    }
    
    // Filter properties to existing schema
    const safeProps = _filterDbPropsToExisting_(FOLDERS_DB_ID, props);
    
    if (existingId) {
      // Update existing entry
      notionFetch_(`pages/${existingId}`, 'PATCH', { properties: safeProps });
      UL?.info?.('Updated folder entry in Notion', {
        pageId: existingId,
        folderName: folderName,
        folderPath: folderPath
      });
      return existingId;
    } else {
      // Create new entry
      const parent = foldersDsId ?
        { type: 'data_source_id', data_source_id: foldersDsId } :
        { type: 'database_id', database_id: FOLDERS_DB_ID };
      
      const newPage = notionFetch_('pages', 'POST', { parent: parent, properties: safeProps });
      UL?.info?.('Created folder entry in Notion', {
        pageId: newPage.id,
        folderName: folderName,
        folderPath: folderPath
      });
      return newPage.id;
    }
  } catch (e) {
    UL?.error?.('Failed to get or create folder entry in Notion', {
      error: String(e),
      stack: e.stack,
      folderName: driveFolder?.getName() || 'unknown'
    });
    return null;
  }
}

/**
 * Gets the absolute path of a Google Drive folder by traversing up to root.
 * @param {GoogleAppsScript.Drive.Folder} folder - Google Drive folder
 * @returns {string|null} Absolute path or null if cannot determine
 */
function getFolderAbsolutePath_(folder) {
  try {
    if (!folder) return null;
    
    const localPath = getLocalDrivePath();
    if (!localPath) return null;
    
    // Get folder name
    const folderName = folder.getName();
    
    // Try to get parent folders
    const pathParts = [folderName];
    let current = folder;
    let depth = 0;
    const maxDepth = 50; // Prevent infinite loops
    
    while (current && depth < maxDepth) {
      try {
        const parents = current.getParents();
        if (!parents.hasNext()) {
          break;
        }
        current = parents.next();
        if (current) {
          const parentName = current.getName();
          if (parentName === 'My Drive' || parentName === 'Drive') {
            break;
          }
          pathParts.unshift(parentName);
          depth++;
        } else {
          break;
        }
      } catch (e) {
        break;
      }
    }
    
    // Construct absolute path
    const relativePath = pathParts.join('/');
    const absolutePath = `${localPath}/${relativePath}`;
    
    return absolutePath;
  } catch (e) {
    return null;
  }
}

/**
 * Calculates folder depth based on absolute path.
 * @param {string} absolutePath - Absolute path
 * @returns {number} Folder depth (0 for root)
 */
function calculateFolderDepth_(absolutePath) {
  if (!absolutePath) return 0;
  const parts = absolutePath.split('/').filter(p => p && p.trim());
  const localPath = getLocalDrivePath();
  if (localPath) {
    const localParts = localPath.split('/').filter(p => p && p.trim());
    return Math.max(0, parts.length - localParts.length - 1);
  }
  return parts.length - 1;
}

/**
 * Gets client ID from Notion Clients database by client context.
 * @param {string} clientContext - Client identifier (e.g., 'seren-media-internal')
 * @param {UnifiedLoggerGAS} UL - Logger instance
 * @returns {string|null} Notion page ID of client, or null if not found
 */
function getClientIdFromNotion_(clientContext, UL) {
  try {
    const clientsDsId = resolveDatabaseToDataSourceId_(CLIENTS_DB_ID, UL);
    
    // Only query if we have a valid data_source_id - skip if database is not accessible
    if (!clientsDsId) {
      UL?.warn?.('Cannot query Clients database - database not accessible via data_source_id', {
        clientContext: clientContext,
        clientsDbId: CLIENTS_DB_ID
      });
      return null;
    }

    const queryResource = `data_sources/${clientsDsId}/query`;
    const clientName = CLIENT_TO_NAME[clientContext];
    if (!clientName) return null;

    const body = {
      filter: {
        property: 'Name',
        title: { equals: clientName }
      },
      page_size: 1
    };
    const res = notionFetch_(queryResource, 'POST', body);
    return (res.results && res.results.length > 0) ? res.results[0].id : null;
  } catch (e) {
    UL?.warn?.('Could not find client in Notion', { clientContext, error: String(e) });
    return null;
  }
}

/**
 * Finds DriveSheetsSync script page in Notion Scripts database.
 * @param {UnifiedLoggerGAS} UL - Logger instance
 * @returns {string|null} Notion page ID of script, or null if not found
 */
function findScriptPageInNotion_(UL) {
  try {
    const scriptsDsId = resolveDatabaseToDataSourceId_(CONFIG.SCRIPTS_DB_ID, UL);
    
    // Only query if we have a valid data_source_id - skip if database is not accessible
    if (!scriptsDsId) {
      UL?.debug?.('Cannot query Scripts database - database not accessible via data_source_id', {
        scriptsDbId: CONFIG.SCRIPTS_DB_ID
      });
      return null;
    }

    const queryResource = `data_sources/${scriptsDsId}/query`;
    const body = {
      filter: {
        property: 'Script Name',
        title: { contains: 'DriveSheetsSync' }
      },
      page_size: 1
    };
    const res = notionFetch_(queryResource, 'POST', body);
    return (res.results && res.results.length > 0) ? res.results[0].id : null;
  } catch (e) {
    UL?.warn?.('Could not find DriveSheetsSync script in Notion', { error: String(e) });
    return null;
  }
}

/* ============================== UTILS ============================== */
const nowIso = () => new Date().toISOString();
const sleep = (ms) => Utilities.sleep(Math.max(0, ms | 0));
const trunc = (s, n = 1800) => {
  s = String(s ?? '');
  return s.length > n ? s.slice(0, n) + '…' : s;
};
const escapeCsv = (v) => {
  const s = String(v ?? '');
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
};
const sanitizeName = (s) =>
  String(s || 'Untitled').replace(/[\\/:*?"<>|#%\u0000-\u001F]/g, '').trim().substring(0, 150);

const INTERNAL_COLS = new Set(['__page_id', '__last_synced_iso']);

/* 2000-char per text span limit helpers */
function chunkText_(txt, max = 2000) {
  const s = String(txt || '');
  if (s.length <= max) return [s];
  const out = [];
  for (let i = 0; i < s.length; i += max) out.push(s.slice(i, i + max));
  return out;
}
function richTextChunks_(txt) {
  return chunkText_(txt, 2000).map(t => ({ type: 'text', text: { content: t } }));
}
function dsTitle_(ds) { return ds?.title?.[0]?.plain_text || 'Untitled database'; }

/* ============================== UNIFIED LOGGER (GAS) - ENHANCED WITH AUDIT FIXES ============================== */
class UnifiedLoggerGAS {
  constructor(cfg) {
    this.cfg = cfg;
    this.runId = Utilities.getUuid().slice(0, 12);
    this.lines = [];
    this.lastFlush = Date.now();
    this.jsonlFile = null;
    this.humanFile = null;
    this.started = nowIso();
    this.script = null;
    this.env = null;
    this.notionLogPageId = null;
    this.errorMessages = [];
    this.warnMessages = [];
    this.logEntries = []; // Store all log entries for page body
    this.databaseResults = []; // Track database processing results
    this.scriptConfig = {}; // Store script configuration
    this.systemInfo = {}; // Store system information
    this._scriptPageIdCache = null; // Cache for script page ID lookup
    this.executionLogProperties = {}; // Cache of Execution-Logs DB properties
    this._propertyCache = {}; // Cache for database properties by dbId
  }

  // Property type naming hints for intelligent matching
  static get TYPE_NAMING_HINTS() {
    return {
      'date': ['Date', 'Time', 'At', 'On'],
      'number': ['Count', 'Total', 'Sum', 'Duration', 'Size'],
      'select': ['Status', 'Type', 'Category', 'Level'],
      'rich_text': ['Name', 'Description', 'Notes', 'Content', 'Summary'],
      'checkbox': ['Is', 'Has', 'Enable', 'Allow']
    };
  }

  init() {
    this.script = PROPS.getProperty(this.cfg.SCRIPT_NAME_PROP) || this.cfg.DEFAULT_SCRIPT_NAME;
    this.env = PROPS.getProperty(this.cfg.ENV_PROP) || this.cfg.DEFAULT_ENV;

    // Capture script configuration
    this._captureScriptConfig();
    
    // Capture system information
    this._captureSystemInfo();

    const now = new Date();
    const yyyy = String(now.getFullYear());
    const mm = String(now.getMonth() + 1).padStart(2, '0');
    const dd = String(now.getDate()).padStart(2, '0');
    const HH = String(now.getHours()).padStart(2, '0');
    const MM = String(now.getMinutes()).padStart(2, '0');
    const SS = String(now.getSeconds()).padStart(2, '0');
    const timestamp = `${yyyy}-${mm}-${dd}_${HH}${MM}${SS}`;

    // MGM Canonical Path: /My Drive/Seren Internal/Automation Files/script_runs/logs/{Script Name}/{ENV}/{YYYY}/{MM}/
    const rootId = this._resolveRootFolder();
    const scriptNameFormatted = this.script || this.cfg.DEFAULT_SCRIPT_NAME;
    const envFormatted = this.env || this.cfg.DEFAULT_ENV;
    const folder = this._ensurePath(rootId, [scriptNameFormatted, envFormatted, yyyy, mm]);

    // MGM File Naming Convention v2: {Script Name} — {VER} — {ENV} — {TIMESTAMP} — {STATUS} [{SCRIPTID}] ({RUNID})
    // Status will be updated at finalization, start with "Running"
    const scriptId = this.systemInfo.scriptId || 'N/A';
    const ver = '2.5'; // Script version
    const status = 'Running'; // Will be updated to Completed/Failed at finalization
    const base = `${scriptNameFormatted} — ${ver} — ${envFormatted} — ${timestamp} — ${status} [${scriptId}] (${this.runId})`;
    
    this.jsonlFile = this._createFileOnce(folder, `${base}.jsonl`, '');
    this.humanFile = this._createFileOnce(folder, `${base}.log`, '');
    
    // CRITICAL: Verify files were created successfully and log their locations prominently
    if (!this.jsonlFile || !this.jsonlFile.getId()) {
      throw new Error(`Failed to create JSONL log file in folder: ${folder.getId()}`);
    }
    if (!this.humanFile || !this.humanFile.getId()) {
      throw new Error(`Failed to create human-readable log file in folder: ${folder.getId()}`);
    }
    
    // Verify files are accessible and log their locations
    try {
      const jsonlUrl = this.jsonlFile.getUrl();
      const humanUrl = this.humanFile.getUrl();
      const jsonlId = this.jsonlFile.getId();
      const humanId = this.humanFile.getId();
      const folderPath = this._getFolderPath(folder);
      const folderUrl = folder.getUrl();
      
      // Log file locations prominently so user can find them
      console.log('\n' + '='.repeat(80));
      console.log('📁 LOG FILES CREATED - LOCATION INFORMATION');
      console.log('='.repeat(80));
      console.log(`📂 Folder Path: ${folderPath}`);
      console.log(`🔗 Folder URL: ${folderUrl}`);
      console.log(`\n📄 JSONL File (Machine Readable):`);
      console.log(`   File ID: ${jsonlId}`);
      console.log(`   File URL: ${jsonlUrl}`);
      console.log(`   File Name: ${this.jsonlFile.getName()}`);
      console.log(`\n📄 Log File (Human Readable):`);
      console.log(`   File ID: ${humanId}`);
      console.log(`   File URL: ${humanUrl}`);
      console.log(`   File Name: ${this.humanFile.getName()}`);
      console.log('='.repeat(80) + '\n');
      
      // Get Notion execution log page URL if available
      const notionLogPageUrl = this.notionLogPageId ? getNotionPageUrl_(this.notionLogPageId) : null;
      
      this.info('📁 Log files created - location information', {
        folderPath: folderPath,
        folderUrl: folderUrl,
        jsonlFileId: jsonlId,
        jsonlFileUrl: jsonlUrl,
        jsonlFileName: this.jsonlFile.getName(),
        humanFileId: humanId,
        humanFileUrl: humanUrl,
        humanFileName: this.humanFile.getName(),
        notionLogPageId: this.notionLogPageId || null,
        notionLogPageUrl: notionLogPageUrl
      });
    } catch (e) {
      this.error('Failed to verify log file creation', {
        error: String(e),
        stack: e.stack,
        folderId: folder.getId()
      });
      throw new Error(`Log files created but not accessible: ${String(e)}`);
    }
    
    // Store base name for finalization (to rename files with final status)
    this.fileBaseName = base;
    this.logFolder = folder;

    // Pre-load Execution-Logs database properties for better error handling
    this._loadExecutionLogProperties();

    this._createNotionExecutionLogPage();

    // Register local Google Drive For Desktop folder in Notion (non-blocking)
    // This enables multi-account deployment tracking
    try {
      registerLocalDriveFolderInNotion_(this);
    } catch (e) {
      this.warn('Failed to register local Drive folder (non-blocking)', { error: String(e) });
    }

    this.info('Logger initialized successfully', {
      runId: this.runId,
      logJsonlFileId: this.jsonlFile.getId(),
      logHumanFileId: this.humanFile.getId(),
      scriptName: this.script,
      environment: this.env,
      executionLogPageId: this.notionLogPageId || 'NOT CREATED',
      clientContext: getClientContext() || 'NOT DETECTED',
      localDrivePath: getLocalDrivePath() || 'NOT MAPPED'
    });
  }

  _loadExecutionLogProperties() {
    if (!CONFIG.EXECUTION_LOGS_DB_ID) {
      this.warn('EXECUTION_LOGS_DB_ID not configured', {});
      return;
    }
    try {
      this.debug('Loading Execution-Logs database properties', { 
        dbId: CONFIG.EXECUTION_LOGS_DB_ID 
      });
      const props = this._getDbProperties_(CONFIG.EXECUTION_LOGS_DB_ID);
      this.executionLogProperties = props;
      if (Object.keys(props).length === 0) {
        this.warn('Execution-Logs database properties loaded but empty - API may have failed silently', { 
          dbId: CONFIG.EXECUTION_LOGS_DB_ID,
          propertyCount: 0
        });
      } else {
        this.debug('Loaded Execution-Logs database properties', { 
          propertyCount: Object.keys(props).length,
          properties: Object.keys(props).slice(0, 20) // Log first 20 for debugging
        });
      }
    } catch (e) {
      this.error('Could not load Execution-Logs database properties', { 
        error: String(e),
        stack: e.stack,
        dbId: CONFIG.EXECUTION_LOGS_DB_ID
      });
      this.executionLogProperties = {};
    }
  }

  _captureScriptConfig() {
    this.scriptConfig = {
      CONFIG: JSON.parse(JSON.stringify(CONFIG)),
      scriptProperties: {
        NOTION_API_KEY: PROPS.getProperty('NOTION_API_KEY') ? '[REDACTED]' : '[NOT SET]',
        WORKSPACE_DATABASES_FOLDER_ID: PROPS.getProperty('WORKSPACE_DATABASES_FOLDER_ID') || '[NOT SET]',
        WORKSPACE_DATABASES_URL: PROPS.getProperty('WORKSPACE_DATABASES_URL') || '[NOT SET]',
        WORKSPACE_DATABASES_NOTION_DB_ID: PROPS.getProperty('WORKSPACE_DATABASES_NOTION_DB_ID') || '[NOT SET]',
        EXECUTION_LOGS_DB_ID: PROPS.getProperty('EXECUTION_LOGS_DB_ID') || CONFIG.EXECUTION_LOGS_DB_ID,
        LOG_SCRIPT_NAME: this.script,
        LOG_ENV: this.env,
        LOG_ROOT_FOLDER_ID: PROPS.getProperty(this.cfg.ROOT_FOLDER_ID_PROP) || '[AUTO-DETECT]',
        REGISTRY_SHEET_ID: PROPS.getProperty('REGISTRY_SHEET_ID') || '[NOT SET]'
      }
    };
  }

  _captureSystemInfo() {
    this.systemInfo = {
      scriptId: ScriptApp.getScriptId(),
      timezone: Session.getScriptTimeZone(),
      userEmail: Session.getActiveUser().getEmail() || '[ANONYMOUS]',
      effectiveUserEmail: Session.getEffectiveUser().getEmail() || '[ANONYMOUS]',
      triggerType: 'MANUAL', // Updated if triggered
      gasVersion: 'V8',
      driveApiVersion: 'v3',
      notionApiVersion: CONFIG.NOTION_VERSION
    };
  }

  _resolveRootFolder() {
    // MGM Canonical Path: /My Drive/Seren Internal/Automation Files/script_runs/logs/
    const canonicalPath = ['Seren Internal', 'Automation Files', 'script_runs', 'logs'];
    
    // Try to find canonical path first
    let root = DriveApp.getRootFolder();
    let folder = root;
    
    for (const part of canonicalPath) {
      const it = folder.getFoldersByName(part);
      if (it.hasNext()) {
        folder = it.next();
      } else {
        // Create canonical path if it doesn't exist
        const parentFolder = folder; // Store parent before creating
        folder = folder.createFolder(part);
        // Use getParents() correctly - it returns a FolderIterator
        const parents = folder.getParents();
        const parentId = parents.hasNext() ? parents.next().getId() : parentFolder.getId();
        this.info('Created canonical path component', { part, parentId: parentId });
      }
    }
    
    // Validate we're in the canonical location
    const folderPath = this._getFolderPath(folder);
    const expectedPath = 'My Drive/' + canonicalPath.join('/');
    if (!folderPath.includes('Seren Internal/Automation Files')) {
      this.warn('Path validation warning - not in canonical location', {
        actualPath: folderPath,
        expectedPath: expectedPath
      });
    }
    
    return folder.getId();
  }
  
  _getFolderPath(folder) {
    let path = [];
    let current = folder;
    while (current && current.getName() !== 'My Drive') {
      path.unshift(current.getName());
      try {
        current = current.getParents().next();
      } catch (e) {
        break;
      }
    }
    return path.join('/');
  }
  
  _validateCanonicalPath(folder) {
    // MGM requirement: Path must be inside canonical directory structure
    const folderPath = this._getFolderPath(folder);
    const canonicalBase = 'Seren Internal/Automation Files/script_runs/logs';
    
    if (!folderPath.includes(canonicalBase)) {
      const error = `Path validation failed: ${folderPath} is not inside canonical ${canonicalBase}`;
      this.error('Non-canonical log path rejected', {
        actualPath: folderPath,
        canonicalBase: canonicalBase,
        error: error
      });
      throw new Error(error);
    }
    return true;
  }
  
  _ensurePath(parentId, parts) {
    let cur = DriveApp.getFolderById(parentId);
    for (const part of parts) {
      const it = cur.getFoldersByName(part);
      cur = it.hasNext() ? it.next() : cur.createFolder(part);
    }
    // Validate canonical path
    this._validateCanonicalPath(cur);
    return cur;
  }
  
  _createFileOnce(folder, name, content) {
    try {
      // Check if file already exists
      const it = folder.getFilesByName(name);
      if (it.hasNext()) {
        const existing = it.next();
        this.debug('Found existing file, reusing', {
          fileName: name,
          fileId: existing.getId(),
          fileUrl: existing.getUrl()
        });
        return existing;
      }
      
      // Create new file
      const file = folder.createFile(Utilities.newBlob(content, 'text/plain', name));
      
      // CRITICAL: Verify file was created and is accessible
      if (!file || !file.getId()) {
        throw new Error(`File creation returned null or invalid file object for: ${name}`);
      }
      
      // Verify file is in the correct folder
      const parents = file.getParents();
      let parentFound = false;
      while (parents.hasNext()) {
        const parent = parents.next();
        if (parent.getId() === folder.getId()) {
          parentFound = true;
          break;
        }
      }
      
      if (!parentFound) {
        this.warn('Created file is not in expected folder', {
          fileName: name,
          fileId: file.getId(),
          expectedFolderId: folder.getId(),
          fileUrl: file.getUrl()
        });
      }
      
      this.debug('Created new file successfully', {
        fileName: name,
        fileId: file.getId(),
        fileUrl: file.getUrl(),
        folderId: folder.getId(),
        folderUrl: folder.getUrl(),
        contentLength: content.length
      });
      
      return file;
    } catch (e) {
      const errorMsg = String(e);
      const stack = e.stack || 'No stack trace available';
      this.error('Failed to create file', {
        fileName: name,
        folderId: folder.getId(),
        folderUrl: folder.getUrl(),
        error: errorMsg,
        stack: stack
      });
      throw new Error(`Failed to create file "${name}" in folder ${folder.getId()}: ${errorMsg}`);
    }
  }

  _getDbProperties_(dbId) {
    try {
      let resource = `databases/${dbId}`;
      let isExecutionLogs = false;
      
      // If this is the Execution-Logs target, resolve database_id to data_source_id
      if (dbId === CONFIG.EXECUTION_LOGS_DB_ID) {
        isExecutionLogs = true;
        const dsId = resolveDatabaseToDataSourceId_(dbId, this);
        if (dsId) {
          resource = `data_sources/${dsId}`;
        } else {
          // Fall back to /databases/{id} so we at least don't 404
          this.warn('Execution-Logs data_source_id could not be resolved; falling back to /databases/{id}', {
            databaseId: dbId
          });
        }
      }

      this.debug('Fetching database properties from Notion API', { 
        dbId, 
        isExecutionLogs,
        resource 
      });
      
      const db = notionFetch_(resource, 'GET');
      if (!db) {
        this.warn('Database fetch returned null/undefined', { dbId, resource });
        return {};
      }
      
      // Log full response structure for debugging
      this.debug('Database API response received', {
        dbId,
        resource,
        hasProperties: !!db.properties,
        propertiesType: typeof db.properties,
        propertiesIsArray: Array.isArray(db.properties),
        dbKeys: Object.keys(db).slice(0, 10),
        dbIdFromResponse: db.id,
        dbTitle: db.title ? (Array.isArray(db.title) ? db.title.map(t => t.plain_text).join('') : String(db.title)) : 'N/A',
        propertiesCount: db.properties ? Object.keys(db.properties).length : 0
      });
      
      if (!db.properties) {
        this.warn('Database object missing properties field', { 
          dbId, 
          resource,
          dbKeys: Object.keys(db),
          dbIdFromResponse: db.id,
          dbTitle: db.title
        });
        return {};
      }
      
      const props = {};
      const propertyEntries = Object.entries(db.properties || {});
      this.debug('Processing property entries', { 
        dbId,
        entryCount: propertyEntries.length
      });
      
      for (const [k, v] of propertyEntries) {
        if (v && v.type) {
          props[k] = v.type;
        } else {
          this.debug('Property missing type', { 
            propertyName: k, 
            propertyValue: v,
            propertyValueType: typeof v,
            propertyValueKeys: v ? Object.keys(v).slice(0, 5) : []
          });
        }
      }
      
      this.debug('Successfully extracted database properties', { 
        dbId, 
        propertyCount: Object.keys(props).length,
        propertyNames: Object.keys(props).slice(0, 10)
      });
      
      if (Object.keys(props).length === 0 && propertyEntries.length > 0) {
        this.warn('Properties found but none had valid type field', {
          dbId,
          propertyEntryCount: propertyEntries.length,
          sampleProperty: propertyEntries[0] ? JSON.stringify(propertyEntries[0]) : 'N/A'
        });
      }
      
      return props;
    } catch (e) {
      this.warn('Could not fetch database properties', { 
        dbId, 
        error: String(e),
        stack: e.stack
      });
      return {};
    }
  }

  _getDbPropertiesWithCache_(dbId) {
    const cacheKey = `props_${dbId}`;
    if (this._propertyCache && this._propertyCache[cacheKey]) {
      return this._propertyCache[cacheKey];
    }
    
    const props = this._getDbProperties_(dbId);
    if (!this._propertyCache) {
      this._propertyCache = {};
    }
    this._propertyCache[cacheKey] = props;
    return props;
  }

  /**
   * Generates multiple name variations for property matching
   * @param {string} name - The property name to generate variations for
   * @returns {Array<string>} Array of name variations
   */
  _generateNameVariations_(name) {
    if (!name || typeof name !== 'string') return [name];
    
    const variations = new Set();
    const original = name.trim();
    
    // 1. Original
    variations.add(original);
    
    // 2. Lowercase
    variations.add(original.toLowerCase());
    
    // 3. Uppercase
    variations.add(original.toUpperCase());
    
    // Helper to split into words
    const words = original.split(/[\s\-_]+/).filter(w => w.length > 0);
    
    if (words.length > 0) {
      // 4. Snake_case (spaces/hyphens → underscores)
      variations.add(words.join('_'));
      variations.add(words.join('_').toLowerCase());
      variations.add(words.join('_').toUpperCase());
      
      // 5. camelCase (first word lowercase, subsequent capitalized)
      if (words.length > 1) {
        const camel = words[0].toLowerCase() + words.slice(1).map(w => 
          w.charAt(0).toUpperCase() + w.slice(1).toLowerCase()
        ).join('');
        variations.add(camel);
      }
      
      // 6. PascalCase (all words capitalized, no separators)
      const pascal = words.map(w => 
        w.charAt(0).toUpperCase() + w.slice(1).toLowerCase()
      ).join('');
      variations.add(pascal);
      
      // 7. kebab-case (spaces/underscores → hyphens)
      variations.add(words.join('-'));
      variations.add(words.join('-').toLowerCase());
      variations.add(words.join('-').toUpperCase());
      
      // 8. Space-normalized (collapse multiple spaces, trim)
      variations.add(words.join(' '));
      variations.add(words.join(' ').toLowerCase());
      variations.add(words.join(' ').toUpperCase());
    }
    
    // 9. Parentheses-stripped (remove (...) suffixes)
    const parenMatch = original.match(/^(.+?)\s*\([^)]*\)\s*$/);
    if (parenMatch) {
      const base = parenMatch[1].trim();
      variations.add(base);
      variations.add(base.toLowerCase());
      variations.add(base.toUpperCase());
      // Also try variations of the base
      const baseWords = base.split(/[\s\-_]+/).filter(w => w.length > 0);
      if (baseWords.length > 0) {
        variations.add(baseWords.join('_'));
        variations.add(baseWords.join('-'));
        variations.add(baseWords.join(' '));
      }
    }
    
    // 10. Separator-agnostic (try all separator combinations)
    if (words.length > 1) {
      const separators = [' ', '-', '_', ''];
      for (const sep of separators) {
        if (sep === '') {
          // No separator - try camelCase and PascalCase
          continue; // Already handled above
        } else {
          variations.add(words.join(sep));
          variations.add(words.join(sep).toLowerCase());
          variations.add(words.join(sep).toUpperCase());
        }
      }
    }
    
    return Array.from(variations).filter(v => v && v.length > 0);
  }

  /**
   * Attempts to match a proposed property name against existing DB properties
   * using multiple strategies with configurable retry attempts
   * 
   * @param {string} proposedName - The property name to match
   * @param {Object} existingProps - Map of existing property names to types
   * @param {number} maxRetries - Maximum retry attempts (default: 3)
   * @returns {Object} { matched: boolean, actualName: string|null, strategy: string, attempts: number, triedVariations: Array }
   */
  _validateAndMatchProperty_(proposedName, existingProps, maxRetries = 3) {
    if (!proposedName || typeof proposedName !== 'string') {
      return {
        matched: false,
        actualName: null,
        strategy: 'FAILED',
        attempts: 0,
        triedVariations: []
      };
    }
    
    const triedVariations = [];
    let attempts = 0;
    
    // Strategy 1: Exact match (PREFERRED - highest priority)
    // This is the most reliable and should always be tried first
    if (existingProps[proposedName]) {
      return {
        matched: true,
        actualName: proposedName,
        strategy: 'exact',
        attempts: 1,
        triedVariations: [proposedName],
        priority: 'highest'
      };
    }
    triedVariations.push(proposedName);
    attempts++;
    
    // Strategy 2: Case-insensitive match
    const existingLower = {};
    for (const key of Object.keys(existingProps)) {
      existingLower[key.toLowerCase()] = key;
    }
    const lowerKey = proposedName.toLowerCase();
    if (existingLower[lowerKey]) {
      return {
        matched: true,
        actualName: existingLower[lowerKey],
        strategy: 'case-insensitive',
        attempts: 2,
        triedVariations: [proposedName, lowerKey]
      };
    }
    triedVariations.push(lowerKey);
    attempts++;
    
    // Strategy 3: Generate variations and try each
    const variations = this._generateNameVariations_(proposedName);
    const hints = UnifiedLoggerGAS.TYPE_NAMING_HINTS;
    
    // Sort variations by priority (exact matches first, then type-hint matches)
    const sortedVariations = [];
    for (const variation of variations) {
      if (triedVariations.includes(variation)) continue;
      
      // Check if variation matches any existing property
      if (existingProps[variation]) {
        sortedVariations.unshift(variation); // High priority
      } else if (existingLower[variation.toLowerCase()]) {
        sortedVariations.push(variation); // Medium priority
      } else {
        // Check type hints
        let hasHint = false;
        for (const [type, hintWords] of Object.entries(hints)) {
          for (const hint of hintWords) {
            if (variation.toLowerCase().includes(hint.toLowerCase()) || 
                hint.toLowerCase().includes(variation.toLowerCase())) {
              // Check if any existing property of this type might match
              for (const [existingName, existingType] of Object.entries(existingProps)) {
                if (existingType === type && 
                    (existingName.toLowerCase().includes(variation.toLowerCase()) ||
                     variation.toLowerCase().includes(existingName.toLowerCase()))) {
                  hasHint = true;
                  break;
                }
              }
              if (hasHint) break;
            }
          }
          if (hasHint) break;
        }
        if (hasHint) {
          sortedVariations.push(variation); // Lower priority but still try
        } else {
          sortedVariations.push(variation); // Try anyway
        }
      }
    }
    
    // Try each variation
    for (const variation of sortedVariations) {
      if (attempts >= maxRetries) break;
      
      triedVariations.push(variation);
      attempts++;
      
      // Try exact match
      if (existingProps[variation]) {
        return {
          matched: true,
          actualName: variation,
          strategy: 'variation-exact',
          attempts: attempts,
          triedVariations: triedVariations
        };
      }
      
      // Try case-insensitive
      const varLower = variation.toLowerCase();
      if (existingLower[varLower]) {
        return {
          matched: true,
          actualName: existingLower[varLower],
          strategy: 'variation-case-insensitive',
          attempts: attempts,
          triedVariations: triedVariations
        };
      }
      
      // Try separator-agnostic matching (fuzzy)
      for (const [existingName, existingType] of Object.entries(existingProps)) {
        // Normalize both names by removing separators and comparing
        const normalize = (str) => str.toLowerCase().replace(/[\s\-_]/g, '');
        if (normalize(variation) === normalize(existingName)) {
          return {
            matched: true,
            actualName: existingName,
            strategy: 'separator-agnostic',
            attempts: attempts,
            triedVariations: triedVariations
          };
        }
        
        // Try parentheses-stripped matching
        const varNoParen = variation.replace(/\s*\([^)]*\)\s*$/, '').trim();
        const existingNoParen = existingName.replace(/\s*\([^)]*\)\s*$/, '').trim();
        if (varNoParen && existingNoParen && 
            normalize(varNoParen) === normalize(existingNoParen)) {
          return {
            matched: true,
            actualName: existingName,
            strategy: 'parentheses-stripped',
            attempts: attempts,
            triedVariations: triedVariations
          };
        }
      }
    }
    
    // No match found
    return {
      matched: false,
      actualName: null,
      strategy: 'FAILED',
      attempts: attempts,
      triedVariations: triedVariations
    };
  }
  _filterExistingProps_(dbId, proposed) {
    // Use cached properties if available, otherwise fetch with caching
    const existing = Object.keys(this.executionLogProperties).length > 0 
      ? this.executionLogProperties 
      : this._getDbPropertiesWithCache_(dbId);
    
    const out = {};
    const matchReport = [];
    
    for (const [proposedName, value] of Object.entries(proposed || {})) {
      const matchResult = this._validateAndMatchProperty_(proposedName, existing, 3);
      
      if (matchResult.matched) {
        out[matchResult.actualName] = value;
        matchReport.push({
          proposed: proposedName,
          matched: matchResult.actualName,
          strategy: matchResult.strategy,
          attempts: matchResult.attempts
        });
        
        // Log successful match if not exact
        if (matchResult.strategy !== 'exact') {
          this.debug('Property matched with variation strategy', { 
            requested: proposedName,
            actual: matchResult.actualName,
            strategy: matchResult.strategy,
            attempts: matchResult.attempts
          });
        }
      } else {
        matchReport.push({
          proposed: proposedName,
          matched: null,
          strategy: 'FAILED',
          attempts: matchResult.attempts,
          triedVariations: matchResult.triedVariations.slice(0, 10) // Limit to first 10 for logging
        });
        
        // Log missing properties for debugging
        this.debug('Property not found in database after all retry strategies', { 
          propertyName: proposedName, 
          dbId,
          attempts: matchResult.attempts,
          triedVariations: matchResult.triedVariations.slice(0, 10),
          availableProperties: Object.keys(existing).slice(0, 20)
        });
      }
    }
    
    // Comprehensive match report logging
    this.debug('Property matching report', {
      totalProposed: Object.keys(proposed || {}).length,
      totalMatched: Object.keys(out).length,
      matchReport: matchReport
    });
    
    // Warn if any properties failed to match
    const failed = matchReport.filter(r => !r.matched);
    if (failed.length > 0) {
      this.warn('Some properties could not be matched', { 
        missingProperties: failed.map(r => r.proposed),
        totalProposed: Object.keys(proposed || {}).length,
        matched: Object.keys(out).length,
        matchReport: matchReport
      });
    }
    
    return out;
  }

  _createNotionExecutionLogPage() {
    try {
      if (!CONFIG.EXECUTION_LOGS_DB_ID) {
        this.warn('Execution-Logs database ID not configured - skipping Notion logging');
        return;
      }
      
      const title = `${this.script || 'DriveSheetsSync'} — ${this.env || 'DEV'} — ${this.runId}`;
      
      // Resolve database_id to data_source_id for API 2025-09-03
      const execLogsDsId = resolveDatabaseToDataSourceId_(CONFIG.EXECUTION_LOGS_DB_ID, this);
      
      // Create page with title
      // API 2025-09-03: Use data_source_id parent type (resolve database_id to data_source_id)
      let parent;
      if (execLogsDsId) {
        parent = { type: 'data_source_id', data_source_id: execLogsDsId };
      } else {
        this.warn('Cannot resolve Execution-Logs data_source_id, using database_id fallback', {
          databaseId: CONFIG.EXECUTION_LOGS_DB_ID
        });
        parent = { type: 'database_id', database_id: CONFIG.EXECUTION_LOGS_DB_ID };
      }
      
      const baseResp = notionFetch_('pages', 'POST', {
        parent: parent,
        properties: { Name: { title: [{ type: 'text', text: { content: title } }] } }
      });
      this.notionLogPageId = baseResp.id;

      // Add initial properties with better error handling
      const proposed = {
        "Start Time": { date: { start: this.started } },
        "Final Status": { select: { name: "Running" } },
        "Script Name-AI": { rich_text: richTextChunks_(this.script || this.cfg.DEFAULT_SCRIPT_NAME) },
        "Session ID": { rich_text: richTextChunks_(this.runId) },
        "Environment": { rich_text: richTextChunks_(this.env || 'DEV') },
        "Script ID": { rich_text: richTextChunks_(this.systemInfo.scriptId || 'N/A') },
        "Timezone": { rich_text: richTextChunks_(this.systemInfo.timezone || 'N/A') },
        "User Email": { rich_text: richTextChunks_(this.systemInfo.userEmail || 'N/A') }
      };
      
      // Ensure all proposed properties exist before trying to set them
      for (const [propName, propValue] of Object.entries(proposed)) {
        // Determine property type from value structure
        let propType = 'rich_text'; // default
        if (propValue.date) propType = 'date';
        else if (propValue.select) propType = 'select';
        else if (propValue.number !== undefined) propType = 'number';
        else if (propValue.checkbox !== undefined) propType = 'checkbox';
        else if (propValue.url) propType = 'url';
        
        ensurePropertyExists_(CONFIG.EXECUTION_LOGS_DB_ID, propName, propType, this);
      }
      
      const safeProps = this._filterExistingProps_(CONFIG.EXECUTION_LOGS_DB_ID, proposed);
      if (Object.keys(safeProps).length) {
        try {
          notionFetch_(`pages/${this.notionLogPageId}`, 'PATCH', { properties: safeProps });
          this.debug('Updated initial execution log properties', { 
            propertiesUpdated: Object.keys(safeProps).length,
            totalProposed: Object.keys(proposed).length
          });
        } catch (e) {
          this.error('Failed to update initial execution log properties', { 
            error: String(e),
            pageId: this.notionLogPageId,
            attemptedProperties: Object.keys(safeProps)
          });
        }
      } else {
        this.warn('No execution log properties could be updated', { 
          proposedProperties: Object.keys(proposed),
          availableProperties: Object.keys(this.executionLogProperties).slice(0, 10)
        });
      }

      // Add initial page content with configuration
      this._appendNotionPageContent([
        { type: 'heading_1', heading_1: { rich_text: richTextChunks_('📋 Execution Log') } },
        { type: 'paragraph', paragraph: { rich_text: richTextChunks_(`Run ID: ${this.runId}`) } },
        { type: 'paragraph', paragraph: { rich_text: richTextChunks_(`Started: ${this.started}`) } },
        { type: 'paragraph', paragraph: { rich_text: richTextChunks_(`Script: ${this.script} | Environment: ${this.env}`) } },
        { type: 'divider', divider: {} },
        { type: 'heading_2', heading_2: { rich_text: richTextChunks_('⚙️ Script Configuration') } },
        { type: 'code', code: { 
          rich_text: richTextChunks_(JSON.stringify(this.scriptConfig, null, 2)),
          language: 'json'
        }},
        { type: 'heading_2', heading_2: { rich_text: richTextChunks_('🖥️ System Information') } },
        { type: 'code', code: { 
          rich_text: richTextChunks_(JSON.stringify(this.systemInfo, null, 2)),
          language: 'json'
        }},
        { type: 'divider', divider: {} },
        { type: 'heading_2', heading_2: { rich_text: richTextChunks_('📝 Execution Log Messages') } }
      ]);

      const notionLogPageUrl = getNotionPageUrl_(this.notionLogPageId);
      console.info(`[INFO] Created execution log page in Notion. Page ID: ${this.notionLogPageId}`);
      console.info(`[INFO] Notion Execution Log URL: ${notionLogPageUrl}`);
      
      this.info('Created execution log page in Notion', {
        pageId: this.notionLogPageId,
        pageUrl: notionLogPageUrl
      });
      
      // Link execution log to script page in Scripts database
      this._linkExecutionLogToScriptPage();
    } catch (e) {
      const errorMsg = String(e);
      const stackTrace = e.stack || 'No stack trace available';
      console.error('[ERROR] Could not create execution log page in Notion:', errorMsg);
      this.error('Failed to create execution log page', { 
        error: errorMsg,
        stack: stackTrace,
        dbId: CONFIG.EXECUTION_LOGS_DB_ID
      });
      this.notionLogPageId = null;
    }
  }
  
  /**
   * Links the execution log page to the script page in Scripts database
   * Updates the "Most Recent Log" relation property on the script page
   */
  _linkExecutionLogToScriptPage() {
    if (!this.notionLogPageId) {
      this.warn('Cannot link execution log to script page - execution log page ID is null');
      return;
    }
    
    if (!CONFIG.SCRIPTS_DB_ID) {
      this.debug('Scripts database ID not configured - skipping script page linking');
      return;
    }
    
    // Ensure Scripts database exists - create if not accessible
    const scriptsDbId = ensureScriptsDatabaseExists_(this);
    if (!scriptsDbId) {
      this.warn('Cannot ensure Scripts database exists - skipping script page linking');
      return;
    }
    
    if (!this.systemInfo.scriptId || this.systemInfo.scriptId === 'N/A') {
      this.debug('Script ID not available - skipping script page linking');
      return;
    }
    
    try {
      // Find script page in Scripts database by Script ID
      const scriptPageId = this._findScriptPageByScriptId_(this.systemInfo.scriptId);
      
      if (!scriptPageId) {
        this.debug('Script page not found in Scripts database - skipping linking', {
          scriptId: this.systemInfo.scriptId
        });
        return;
      }
      
      // Ensure "Most Recent Log" property exists on script page
      // If database is not accessible, skip property creation but still try to link
      let mostRecentLogPropCreated = false;
      let propertyCreationSkipped = false;
      
      // Ensure Scripts database exists before property creation
      const scriptsDbId = ensureScriptsDatabaseExists_(this);
      if (!scriptsDbId) {
        this.warn('Cannot ensure Scripts database exists - skipping Most Recent Log property creation');
        propertyCreationSkipped = true;
      } else {
        try {
          mostRecentLogPropCreated = ensurePropertyExists_(scriptsDbId, 'Most Recent Log', 'relation', this);
        } catch (e) {
          // Database may not be accessible - skip property creation
          propertyCreationSkipped = true;
          this.warn('Skipping Most Recent Log property creation - Scripts database not accessible', {
            scriptPageId: scriptPageId,
            dbId: scriptsDbId,
            error: String(e),
            note: 'Will attempt to link anyway - property may already exist'
          });
        }
      }
      
      if (!mostRecentLogPropCreated && !propertyCreationSkipped) {
        this.debug('Most Recent Log property not created - attempting link anyway (property may already exist)', {
          scriptPageId: scriptPageId
        });
      }
      
      // Update script page with execution log relation
      try {
        notionFetch_(`pages/${scriptPageId}`, 'PATCH', {
          properties: {
            'Most Recent Log': {
              relation: [{ id: this.notionLogPageId }]
            }
          }
        });
        
        this.info('Linked execution log to script page', {
          scriptPageId: scriptPageId,
          executionLogPageId: this.notionLogPageId,
          scriptId: this.systemInfo.scriptId
        });
      } catch (e) {
        this.error('Failed to update script page with execution log relation', {
          error: String(e),
          scriptPageId: scriptPageId,
          executionLogPageId: this.notionLogPageId,
          stack: e.stack
        });
      }
    } catch (e) {
      this.error('Failed to link execution log to script page', {
        error: String(e),
        stack: e.stack,
        scriptId: this.systemInfo.scriptId
      });
    }
  }
  
  /**
   * Finds script page in Scripts database by Script ID
   * Uses cache to avoid repeated lookups
   * @param {string} scriptId - Google Apps Script ID
   * @returns {string|null} Script page ID or null if not found
   */
  _findScriptPageByScriptId_(scriptId) {
    // Return cached value if available
    if (this._scriptPageIdCache !== null) {
      return this._scriptPageIdCache;
    }
    
    try {
      if (!CONFIG.SCRIPTS_DB_ID) {
        this._scriptPageIdCache = false; // Cache false to avoid repeated checks
        return null;
      }
      
      // Ensure Scripts database exists - create if not accessible
      const scriptsDbId = ensureScriptsDatabaseExists_(this);
      if (!scriptsDbId) {
        this.warn('Cannot ensure Scripts database exists - skipping script page lookup');
        this._scriptPageIdCache = false;
        return null;
      }
      
      // Try to find by Script ID property (various possible property names)
      const scriptIdPropNames = ['Script ID', 'Google Apps Script ID', 'GAS Script ID', 'Script-ID'];
      
      // Try to resolve Scripts database to data_source_id (use actual accessible ID)
      let scriptsDsId = null;
      let queryResource = null;
      try {
        scriptsDsId = resolveDatabaseToDataSourceId_(scriptsDbId, this);
        // Only use query if we have a valid data_source_id - skip if database is not accessible
        if (!scriptsDsId) {
          this.warn('Cannot query Scripts database - database not accessible via data_source_id', {
            dbId: scriptsDbId
          });
          this._scriptPageIdCache = false;
          return null;
        }
        queryResource = `data_sources/${scriptsDsId}/query`;
      } catch (resolveErr) {
        // Scripts database not accessible even after creation attempt - skip script page lookup
        this.warn('Cannot resolve Scripts database after creation attempt - skipping script page lookup', {
          dbId: scriptsDbId,
          error: String(resolveErr),
          note: 'Script page linking will be skipped'
        });
        this._scriptPageIdCache = false; // Cache false to avoid repeated lookups
        return null;
      }
      
      if (!queryResource) {
        this.warn('Cannot determine query resource for Scripts database - skipping script page lookup', {
          dbId: CONFIG.SCRIPTS_DB_ID
        });
        this._scriptPageIdCache = false;
        return null;
      }
      
      for (const propName of scriptIdPropNames) {
        try {
          // Try to ensure property exists before querying (skip if database not accessible)
          try {
            ensurePropertyExists_(scriptsDbId, propName, 'rich_text', this);
          } catch (propErr) {
            // Database not accessible - skip property creation, try querying anyway
            this.debug('Skipping property creation for Scripts database - database not accessible', {
              property: propName,
              dbId: scriptsDbId,
              error: String(propErr)
            });
            // Continue to try querying - property might already exist
          }
          
          const filter = {
            property: propName,
            rich_text: {
              equals: scriptId
            }
          };
          
          const results = notionFetch_(queryResource, 'POST', { 
            filter: filter,
            page_size: 1
          });
          
          if (results.results && results.results.length > 0) {
            const pageId = results.results[0].id;
            this._scriptPageIdCache = pageId; // Cache the result
            this.debug('Found script page by Script ID', {
              scriptId: scriptId,
              propertyName: propName,
              pageId: pageId
            });
            return pageId;
          }
        } catch (e) {
          // Continue to next property name
          this.debug('Could not query by property', {
            propertyName: propName,
            error: String(e)
          });
        }
      }
      
      // Fallback: Try to find by script name if Script ID search fails
      const scriptName = this.script || this.cfg.DEFAULT_SCRIPT_NAME;
      const namePropNames = ['Script Name', 'Name', 'Title'];
      
      for (const propName of namePropNames) {
        try {
          const filter = {
            property: propName,
            title: {
              equals: scriptName
            }
          };
          
          const results = notionFetch_(queryResource, 'POST', { 
            filter: filter,
            page_size: 1
          });
          
          if (results.results && results.results.length > 0) {
            const pageId = results.results[0].id;
            this._scriptPageIdCache = pageId; // Cache the result
            this.debug('Found script page by name', {
              scriptName: scriptName,
              propertyName: propName,
              pageId: pageId
            });
            return pageId;
          }
        } catch (e) {
          // Continue to next property name
          this.debug('Could not query by name property', {
            propertyName: propName,
            error: String(e)
          });
        }
      }
      
      this._scriptPageIdCache = false; // Cache false to avoid repeated lookups
      return null;
    } catch (e) {
      this.error('Failed to find script page by Script ID', {
        error: String(e),
        scriptId: scriptId,
        stack: e.stack
      });
      this._scriptPageIdCache = false; // Cache false on error
      return null;
    }
  }

  _appendNotionPageContent(blocks) {
    if (!this.notionLogPageId || !blocks || !blocks.length) return;
    try {
      // Notion API limit: 100 blocks per request
      const chunkSize = 100;
      for (let i = 0; i < blocks.length; i += chunkSize) {
        const chunk = blocks.slice(i, i + chunkSize);
        notionFetch_(`blocks/${this.notionLogPageId}/children`, 'PATCH', {
          children: chunk
        });
        if (blocks.length > chunkSize) sleep(500); // Rate limiting
      }
    } catch (e) {
      const errorMsg = String(e);
      const stackTrace = e.stack || 'No stack trace available';
      console.error('[ERROR] Failed to append content to Notion page:', errorMsg);
      this.error('Failed to append content to Notion page', { 
        error: errorMsg,
        stack: stackTrace,
        pageId: this.notionLogPageId,
        blockCount: blocks.length
      });
    }
  }

  _updateNotionExecutionLogPage(finalStatus, summary) {
    if (!this.notionLogPageId) {
      this.warn('Cannot update execution log page - page ID is null');
      return;
    }
    
    try {
      const ended = nowIso();
      const duration = Math.round((new Date(ended) - new Date(this.started)) / 1000);
      const finalSelect =
        finalStatus === 'Success' || finalStatus === true ? 'Completed'
          : finalStatus === 'Failed' || finalStatus === false ? 'Failed'
            : 'Completed';

      // Update properties with detailed information
      const proposed = {
        "Final Status": { select: { name: finalSelect } },
        "End Time": { date: { start: ended } },
        "Duration (s)": { number: duration }
      };

      // Add comprehensive summary
      if (summary) {
        const summaryText = [
          `📊 EXECUTION SUMMARY`,
          ``,
          `Databases Processed: ${summary.processed ?? 0}`,
          `Databases Failed: ${summary.failed ?? 0}`,
          `Total Discovered: ${summary.total ?? 0}`,
          `Agent-Tasks Status: ${summary.agentTasksProcessed ? '✅ Processed' : '⚠️ Not Processed'}`,
          `Rotation: ${summary.rotation || 'N/A'}`,
          ``,
          `Processed Databases:`,
          summary.processedDatabases || 'None'
        ].join('\n');
        proposed["Log Summary"] = { rich_text: richTextChunks_(summaryText) };
      }

      // Add Drive file links and Notion page link
      const linkParts = [];
      if (this.jsonlFile && this.humanFile) {
        linkParts.push(`📁 Drive Log Files:`, ``);
        linkParts.push(`JSONL (Machine): ${this.jsonlFile.getUrl()}`);
        linkParts.push(`Human Readable: ${this.humanFile.getUrl()}`);
      }
      if (this.notionLogPageId) {
        const notionLogPageUrl = getNotionPageUrl_(this.notionLogPageId);
        linkParts.push(``, `📝 Notion Execution Log:`, ``);
        linkParts.push(`Page URL: ${notionLogPageUrl}`);
      }
      if (linkParts.length > 0) {
        proposed["Log Content"] = { rich_text: richTextChunks_(linkParts.join('\n')) };
      }

      // Add error details with full context and stack traces
      if (this.errorMessages.length > 0) {
        const errorText = this.errorMessages.slice(0, 20).join('\n\n'); // Increased from 10 to 20
        proposed["Errors (JSON)"] = { rich_text: richTextChunks_(trunc(errorText, 2000)) };
        proposed["Error Count"] = { number: this.errorMessages.length };
      }

      // Add warning details
      if (this.warnMessages.length > 0) {
        const warnText = this.warnMessages.slice(0, 20).join('\n\n'); // Increased from 10 to 20
        proposed["Warnings (JSON)"] = { rich_text: richTextChunks_(trunc(warnText, 2000)) };
        proposed["Warning Count"] = { number: this.warnMessages.length };
      }

      // Add database processing results
      if (this.databaseResults.length > 0) {
        const dbText = this.databaseResults.map(r => 
          `${r.success ? '✅' : '❌'} ${r.name} (${r.id})\n` +
          `  Rows: ${r.rowCount ?? 'N/A'} | Status: ${r.status || 'Unknown'}` +
          (r.error ? `\n  Error: ${trunc(r.error, 200)}` : '')
        ).join('\n\n');
        proposed["Database Results"] = { rich_text: richTextChunks_(trunc(dbText, 2000)) };
      }

      // Add performance metrics
      const performanceMetrics = {
        totalLogs: this.logEntries.length,
        totalErrors: this.errorMessages.length,
        totalWarnings: this.warnMessages.length,
        databasesProcessed: this.databaseResults.length,
        durationSeconds: duration
      };
      proposed["Performance Metrics"] = { rich_text: richTextChunks_(JSON.stringify(performanceMetrics, null, 2)) };

      const safeProps = this._filterExistingProps_(CONFIG.EXECUTION_LOGS_DB_ID, proposed);
      if (Object.keys(safeProps).length) {
        try {
          notionFetch_(`pages/${this.notionLogPageId}`, 'PATCH', { properties: safeProps });
          this.debug('Updated final execution log properties', { 
            propertiesUpdated: Object.keys(safeProps).length,
            finalStatus: finalSelect
          });
        } catch (e) {
          this.error('Failed to update final execution log properties', { 
            error: String(e),
            stack: e.stack || 'No stack trace',
            pageId: this.notionLogPageId,
            attemptedProperties: Object.keys(safeProps)
          });
        }
      } else {
        this.warn('No final execution log properties could be updated', { 
          proposedProperties: Object.keys(proposed),
          availableProperties: Object.keys(this.executionLogProperties).slice(0, 10)
        });
      }
      
      // Ensure execution log is linked to script page (retry if initial linking failed)
      this._linkExecutionLogToScriptPage();

      // Append final summary and database results to page body
      const finalBlocks = [
        { type: 'divider', divider: {} },
        { type: 'heading_2', heading_2: { rich_text: richTextChunks_('✅ Execution Complete') } },
        { type: 'paragraph', paragraph: { rich_text: richTextChunks_(`Status: ${finalSelect}`) } },
        { type: 'paragraph', paragraph: { rich_text: richTextChunks_(`Ended: ${ended}`) } },
        { type: 'paragraph', paragraph: { rich_text: richTextChunks_(`Duration: ${duration}s`) } }
      ];

      if (summary) {
        finalBlocks.push(
          { type: 'heading_3', heading_3: { rich_text: richTextChunks_('📊 Summary') } },
          { type: 'code', code: { 
            rich_text: richTextChunks_(JSON.stringify(summary, null, 2)),
            language: 'json'
          }}
        );
      }

      if (this.databaseResults.length > 0) {
        finalBlocks.push(
          { type: 'heading_3', heading_3: { rich_text: richTextChunks_('🗄️ Database Processing Results') } },
          { type: 'code', code: { 
            rich_text: richTextChunks_(JSON.stringify(this.databaseResults, null, 2)),
            language: 'json'
          }}
        );
      }

      if (this.errorMessages.length > 0) {
        finalBlocks.push(
          { type: 'heading_3', heading_3: { rich_text: richTextChunks_(`❌ Errors (${this.errorMessages.length})`) } },
          { type: 'code', code: { 
            rich_text: richTextChunks_(trunc(this.errorMessages.join('\n\n'), 20000)),
            language: 'plain text'
          }}
        );
      }

      if (this.warnMessages.length > 0) {
        finalBlocks.push(
          { type: 'heading_3', heading_3: { rich_text: richTextChunks_(`⚠️ Warnings (${this.warnMessages.length})`) } },
          { type: 'code', code: { 
            rich_text: richTextChunks_(trunc(this.warnMessages.join('\n\n'), 20000)),
            language: 'plain text'
          }}
        );
      }

      // CRITICAL: Always write page body content, even if properties fail
      // This ensures logs are always populated
      try {
        this._appendNotionPageContent(finalBlocks);
        this.debug('Successfully appended final content to execution log page', {
          blockCount: finalBlocks.length,
          pageId: this.notionLogPageId
        });
      } catch (e) {
        // Log error but don't fail - properties may have been updated
        this.error('Failed to append final content to execution log page', {
          error: String(e),
          stack: e.stack || 'No stack trace',
          pageId: this.notionLogPageId
        });
        // Try to write a minimal summary as fallback
        try {
          this._appendNotionPageContent([
            { type: 'paragraph', paragraph: { rich_text: richTextChunks_(`Status: ${finalSelect} | Duration: ${duration}s | Errors: ${this.errorMessages.length}`) } }
          ]);
        } catch (e2) {
          this.error('Failed to write fallback content', { error: String(e2) });
        }
      }

      console.info(`[INFO] Finalized execution log page with status: ${finalSelect}`);
    } catch (e) {
      const errorMsg = String(e);
      const stackTrace = e.stack || 'No stack trace available';
      console.error('[ERROR] Could not finalize execution log page:', errorMsg);
      this.error('Failed to finalize execution log page', { 
        error: errorMsg,
        stack: stackTrace,
        pageId: this.notionLogPageId
      });
    }
  }

  addDatabaseResult(dbName, dbId, success, status, rowCount, error) {
    this.databaseResults.push({
      name: dbName,
      id: dbId,
      success: success,
      status: status,
      rowCount: rowCount,
      error: error || null,
      timestamp: nowIso()
    });
  }

  _flushIfNeeded(force = false) {
    if (!this.lines.length) return;
    if (!force && this.lines.length < CONFIG.LOGGING.FLUSH_LINES && (Date.now() - this.lastFlush) < CONFIG.LOGGING.FLUSH_MS) return;
    
    // CRITICAL: Verify files exist before attempting to write
    // If files aren't initialized yet, buffer logs until they are (don't error - that would cause recursion)
    if (!this.jsonlFile || !this.humanFile) {
      // Files not ready yet - keep buffering logs
      // This can happen if logging occurs before init() completes or if init() fails
      // Logs will be flushed once files are initialized or during finalize()
      return;
    }
    
    const buf = this.lines.join('');
    this.lines.length = 0;
    this.lastFlush = Date.now();
    
    try {
      // Get existing content (handle empty files)
      let existingJsonl = '';
      let existingHuman = '';
      
      try {
        existingJsonl = this.jsonlFile.getBlob().getDataAsString() || '';
      } catch (e) {
        this.warn('Could not read existing JSONL content, starting fresh', {
          error: String(e),
          fileId: this.jsonlFile.getId()
        });
        existingJsonl = '';
      }
      
      try {
        existingHuman = this.humanFile.getBlob().getDataAsString() || '';
      } catch (e) {
        this.warn('Could not read existing human log content, starting fresh', {
          error: String(e),
          fileId: this.humanFile.getId()
        });
        existingHuman = '';
      }
      
      // Prepare new content
      const jsonl = existingJsonl + buf;
      const human = existingHuman + buf.replace(/\n$/, '');
      
      // Write content with verification
      this.jsonlFile.setContent(jsonl);
      this.humanFile.setContent(human);
      
      // CRITICAL: Verify files were written successfully
      try {
        const verifyJsonl = this.jsonlFile.getBlob().getDataAsString();
        const verifyHuman = this.humanFile.getBlob().getDataAsString();
        
        if (verifyJsonl.length < jsonl.length) {
          throw new Error(`JSONL file write verification failed: expected ${jsonl.length} bytes, got ${verifyJsonl.length}`);
        }
        if (verifyHuman.length < human.length) {
          throw new Error(`Human log file write verification failed: expected ${human.length} bytes, got ${verifyHuman.length}`);
        }
        
        this.debug('Successfully flushed logs to Drive files', {
          jsonlFileId: this.jsonlFile.getId(),
          jsonlFileUrl: this.jsonlFile.getUrl(),
          humanFileId: this.humanFile.getId(),
          humanFileUrl: this.humanFile.getUrl(),
          jsonlSize: verifyJsonl.length,
          humanSize: verifyHuman.length,
          bytesWritten: buf.length
        });
      } catch (verifyError) {
        this.error('File write verification failed', {
          error: String(verifyError),
          jsonlFileId: this.jsonlFile.getId(),
          humanFileId: this.humanFile.getId(),
          stack: verifyError.stack
        });
        throw verifyError; // Re-throw to be caught by outer catch
      }
    } catch (e) {
      const errorMsg = String(e);
      const stack = e.stack || 'No stack trace available';
      this.error('Failed to flush logs to Drive files', { 
        error: errorMsg,
        stack: stack,
        jsonlFileId: this.jsonlFile?.getId(),
        jsonlFileUrl: this.jsonlFile?.getUrl(),
        humanFileId: this.humanFile?.getId(),
        humanFileUrl: this.humanFile?.getUrl(),
        bufferLength: buf.length
      });
      
      // Try to re-create files if they're missing or inaccessible
      if (this.logFolder) {
        try {
          this.warn('Attempting to recreate log files', {
            folderId: this.logFolder.getId(),
            folderUrl: this.logFolder.getUrl()
          });
          
          // Re-create files if they don't exist or are inaccessible
          if (!this.jsonlFile || !this.jsonlFile.getId()) {
            const base = this.fileBaseName || `DriveSheetsSync — ${this.runId}`;
            this.jsonlFile = this._createFileOnce(this.logFolder, `${base}.jsonl`, buf);
            this.info('Recreated JSONL file', { fileId: this.jsonlFile.getId() });
          }
          
          if (!this.humanFile || !this.humanFile.getId()) {
            const base = this.fileBaseName || `DriveSheetsSync — ${this.runId}`;
            this.humanFile = this._createFileOnce(this.logFolder, `${base}.log`, buf.replace(/\n$/, ''));
            this.info('Recreated human log file', { fileId: this.humanFile.getId() });
          }
        } catch (recreateError) {
          this.error('Failed to recreate log files', {
            error: String(recreateError),
            stack: recreateError.stack
          });
        }
      }
    }
  }

  _push(level, msg, ctx) {
    const rec = { ts: nowIso(), level, script: this.script, env: this.env, run: this.runId, msg, ...(ctx || {}) };
    this.lines.push(JSON.stringify(rec) + '\n');
    this._flushIfNeeded(false);

    // Store log entry for page body
    const levelEmoji = {
      error: '❌',
      warn: '⚠️',
      info: 'ℹ️',
      debug: '🔍'
    }[level] || '📝';

    const logEntry = {
      level,
      message: msg,
      context: ctx,
      timestamp: rec.ts
    };
    this.logEntries.push(logEntry);

    // Collect errors and warnings with full context and stack traces
    if (level === 'error') {
      const fullError = `[${rec.ts}] ${msg}${ctx ? '\nContext: ' + JSON.stringify(ctx, null, 2) : ''}${ctx?.stack ? '\nStack: ' + ctx.stack : ''}`;
      this.errorMessages.push(fullError);
    } else if (level === 'warn') {
      const fullWarn = `[${rec.ts}] ${msg}${ctx ? '\nContext: ' + JSON.stringify(ctx, null, 2) : ''}${ctx?.stack ? '\nStack: ' + ctx.stack : ''}`;
      this.warnMessages.push(fullWarn);
    }

    // Append to Notion page periodically (every 10 messages or on errors)
    if (this.notionLogPageId && (this.logEntries.length % 10 === 0 || level === 'error')) {
      this._flushLogsToNotionPage();
    }

    const ctxStr = ctx && Object.keys(ctx).length ? ` ${JSON.stringify(ctx)}` : '';
    const logMsg = `[${level.toUpperCase()}] ${msg}${ctxStr}`;
    if (level === 'error') console.error(logMsg);
    else if (level === 'warn') console.warn(logMsg);
    else if (level === 'debug') console.log(logMsg);
    else console.info(logMsg);
  }

  _flushLogsToNotionPage() {
    if (!this.notionLogPageId || this.logEntries.length === 0) return;
    
    try {
      // Create blocks for recent log entries
      const blocks = [];
      const entriesToFlush = this.logEntries.splice(0); // Get all and clear
      
      for (const entry of entriesToFlush.slice(-20)) { // Last 20 entries
        const levelEmoji = {
          error: '❌',
          warn: '⚠️',
          info: 'ℹ️',
          debug: '🔍'
        }[entry.level] || '📝';

        const text = `${levelEmoji} [${entry.timestamp}] ${entry.message}`;
        blocks.push({
          type: 'paragraph',
          paragraph: { rich_text: richTextChunks_(text) }
        });

        if (entry.context && Object.keys(entry.context).length > 0) {
          blocks.push({
            type: 'code',
            code: {
              rich_text: richTextChunks_(JSON.stringify(entry.context, null, 2)),
              language: 'json'
            }
          });
        }
      }

      if (blocks.length > 0) {
        this._appendNotionPageContent(blocks);
      }
    } catch (e) {
      const errorMsg = String(e);
      const stackTrace = e.stack || 'No stack trace available';
      console.error('[ERROR] Failed to flush logs to Notion page:', errorMsg);
      this.error('Failed to flush logs to Notion page', { 
        error: errorMsg,
        stack: stackTrace,
        pageId: this.notionLogPageId
      });
    }
  }

  debug(m, c) { this._push('debug', m, c); }
  info(m, c)  { this._push('info',  m, c); }
  warn(m, c)  { this._push('warn',  m, c); }
  error(m, c) { this._push('error', m, c); }

  finalize(ok = true, err = null, summary = null) {
    this.info('Finalizing execution log', { 
      success: ok, 
      error: err ? String(err).slice(0, 500) : null,
      totalErrors: this.errorMessages.length,
      totalWarnings: this.warnMessages.length,
      totalLogs: this.logEntries.length
    });
    
    // Flush any remaining logs to Notion
    if (this.logEntries.length > 0) {
      this._flushLogsToNotionPage();
    }
    
    // Determine final status
    const finalStatus = ok ? 'Completed' : 'Failed';
    
    // Flush final logs to files (only if files are initialized)
    if (this.jsonlFile && this.humanFile) {
      this._flushIfNeeded(true);
      
      // MGM requirement: Rename files with final status
      this._renameFilesWithFinalStatus(finalStatus);
      
      // Write final JSONL entry with all required MGM fields
      this._writeFinalJsonlEntry(finalStatus, summary);
    } else {
      // Files not initialized - log warning but continue with Notion update
      console.warn('[WARN] Cannot flush logs to files - files not initialized. Logs may be lost.');
    }
    
    // Update Notion execution log page
    this._updateNotionExecutionLogPage(finalStatus, summary);
    
    // CRITICAL: Log final file locations prominently so user can find them
    if (this.jsonlFile && this.humanFile && this.logFolder) {
      try {
        const folderPath = this._getFolderPath(this.logFolder);
        const folderUrl = this.logFolder.getUrl();
        const jsonlUrl = this.jsonlFile.getUrl();
        const humanUrl = this.humanFile.getUrl();
        
        console.log('\n' + '='.repeat(80));
        console.log('✅ EXECUTION COMPLETE - LOG FILES LOCATION');
        console.log('='.repeat(80));
        console.log(`📂 Folder Path: ${folderPath}`);
        console.log(`🔗 Folder URL: ${folderUrl}`);
        console.log(`\n📄 JSONL File (Machine Readable):`);
        console.log(`   File Name: ${this.jsonlFile.getName()}`);
        console.log(`   File URL: ${jsonlUrl}`);
        console.log(`   File ID: ${this.jsonlFile.getId()}`);
        console.log(`\n📄 Log File (Human Readable):`);
        console.log(`   File Name: ${this.humanFile.getName()}`);
        console.log(`   File URL: ${humanUrl}`);
        console.log(`   File ID: ${this.humanFile.getId()}`);
        console.log(`\n💡 TIP: Click the URLs above to open files directly in Google Drive`);
        console.log('='.repeat(80) + '\n');
        
        this.info('✅ Execution complete - log files location', {
          finalStatus: finalStatus,
          folderPath: folderPath,
          folderUrl: folderUrl,
          jsonlFileId: this.jsonlFile.getId(),
          jsonlFileUrl: jsonlUrl,
          jsonlFileName: this.jsonlFile.getName(),
          humanFileId: this.humanFile.getId(),
          humanFileUrl: humanUrl,
          humanFileName: this.humanFile.getName()
        });
      } catch (e) {
        this.error('Failed to log final file locations', {
          error: String(e),
          stack: e.stack
        });
      }
    }
  }
  
  _renameFilesWithFinalStatus(finalStatus) {
    if (!this.jsonlFile || !this.humanFile || !this.fileBaseName) return;
    
    try {
      // Extract components from current filename
      const currentBase = this.fileBaseName;
      // Replace "Running" with final status
      const newBase = currentBase.replace(' — Running ', ` — ${finalStatus} `);
      
      // Rename JSONL file
      if (this.jsonlFile.getName().includes('Running')) {
        const newJsonlName = `${newBase}.jsonl`;
        this.jsonlFile.setName(newJsonlName);
        // Refresh file object to ensure it reflects the new name
        this.jsonlFile = DriveApp.getFileById(this.jsonlFile.getId());
        this.info('Renamed JSONL file with final status', { newName: newJsonlName });
      }
      
      // Rename plaintext log file
      if (this.humanFile.getName().includes('Running')) {
        const newLogName = `${newBase}.log`;
        this.humanFile.setName(newLogName);
        // Refresh file object to ensure it reflects the new name
        this.humanFile = DriveApp.getFileById(this.humanFile.getId());
        this.info('Renamed log file with final status', { newName: newLogName });
      }
    } catch (e) {
      this.error('Failed to rename files with final status', {
        error: String(e),
        stack: e.stack,
        finalStatus: finalStatus
      });
    }
  }
  
  _writeFinalJsonlEntry(finalStatus, summary) {
    if (!this.jsonlFile) {
      // File not initialized - skip writing final entry (logs may be lost)
      // Don't log error here as it would cause recursion
      return;
    }
    
    try {
      const ended = nowIso();
      const duration = Math.round((new Date(ended) - new Date(this.started)) / 1000);
      
      // MGM required JSONL fields
      const finalEntry = {
        execution_id: this.runId,
        script_name: this.script || this.cfg.DEFAULT_SCRIPT_NAME,
        start_time: this.started,
        end_time: ended,
        final_status: finalStatus,
        duration_seconds: duration,
        environment: this.env || this.cfg.DEFAULT_ENV,
        script_id: this.systemInfo.scriptId || 'N/A',
        steps: this.databaseResults.map(r => ({
          database: r.name,
          database_id: r.id,
          success: r.success,
          status: r.status,
          row_count: r.rowCount,
          error: r.error || null,
          timestamp: r.timestamp
        })),
        errors: this.errorMessages.map((msg, idx) => ({
          index: idx + 1,
          message: msg,
          timestamp: nowIso()
        })),
        warnings: this.warnMessages.map((msg, idx) => ({
          index: idx + 1,
          message: msg,
          timestamp: nowIso()
        })),
        summary: summary || {},
        performance_metrics: {
          total_logs: this.logEntries.length,
          total_errors: this.errorMessages.length,
          total_warnings: this.warnMessages.length,
          databases_processed: this.databaseResults.length,
          duration_seconds: duration
        }
      };
      
      // Append final entry to JSONL file with verification
      const jsonlLine = JSON.stringify(finalEntry) + '\n';
      let currentContent = '';
      try {
        currentContent = this.jsonlFile.getBlob().getDataAsString() || '';
      } catch (e) {
        this.warn('Could not read existing JSONL content for final entry', {
          error: String(e),
          fileId: this.jsonlFile.getId()
        });
        currentContent = '';
      }
      
      const newContent = currentContent + jsonlLine;
      this.jsonlFile.setContent(newContent);
      
      // CRITICAL: Verify the write succeeded
      try {
        const verifyContent = this.jsonlFile.getBlob().getDataAsString();
        if (verifyContent.length < newContent.length) {
          throw new Error(`Final JSONL write verification failed: expected ${newContent.length} bytes, got ${verifyContent.length}`);
        }
        
        this.info('Wrote final JSONL entry with verification', {
          executionId: this.runId,
          finalStatus: finalStatus,
          fileId: this.jsonlFile.getId(),
          fileUrl: this.jsonlFile.getUrl(),
          fileSize: verifyContent.length,
          entrySize: jsonlLine.length
        });
      } catch (verifyError) {
        this.error('Final JSONL entry write verification failed', {
          error: String(verifyError),
          stack: verifyError.stack,
          executionId: this.runId,
          fileId: this.jsonlFile.getId(),
          fileUrl: this.jsonlFile.getUrl()
        });
        throw verifyError;
      }
      
      // Append final entry to plaintext log file
      const logEntry = [
        '',
        '='.repeat(80),
        `FINAL EXECUTION SUMMARY`,
        '='.repeat(80),
        `Execution ID: ${finalEntry.execution_id}`,
        `Script: ${finalEntry.script_name}`,
        `Status: ${finalEntry.final_status}`,
        `Start Time: ${finalEntry.start_time}`,
        `End Time: ${finalEntry.end_time}`,
        `Duration: ${finalEntry.duration_seconds}s`,
        `Environment: ${finalEntry.environment}`,
        '',
        `Steps Processed: ${finalEntry.steps.length}`,
        ...finalEntry.steps.map(s => `  - ${s.database}: ${s.success ? 'SUCCESS' : 'FAILED'} (${s.row_count || 0} rows)`),
        '',
        `Errors: ${finalEntry.errors.length}`,
        ...finalEntry.errors.slice(0, 10).map(e => `  [${e.index}] ${e.message.substring(0, 200)}`),
        '',
        `Warnings: ${finalEntry.warnings.length}`,
        ...finalEntry.warnings.slice(0, 10).map(w => `  [${w.index}] ${w.message.substring(0, 200)}`),
        '',
        '='.repeat(80)
      ].join('\n');
      
      const currentLogContent = this.humanFile.getBlob().getDataAsString();
      this.humanFile.setContent(currentLogContent + logEntry);
      
      this.info('Wrote final JSONL entry with MGM required fields', {
        executionId: finalEntry.execution_id,
        finalStatus: finalStatus,
        stepCount: finalEntry.steps.length,
        errorCount: finalEntry.errors.length
      });
    } catch (e) {
      this.error('Failed to write final JSONL entry', {
        error: String(e),
        stack: e.stack,
        finalStatus: finalStatus
      });
    }
  }

  /**
   * Test function for property matching validation
   * Run via: clasp run testPropertyMatching
   */
  testPropertyMatching() {
    const testCases = [
      {
        name: 'Test 1: Case variation',
        proposed: 'final status',
        existing: { 'Final Status': 'select' },
        expected: { matched: true, actualName: 'Final Status', strategy: 'case-insensitive' }
      },
      {
        name: 'Test 2: Separator variation',
        proposed: 'Script_Name_AI',
        existing: { 'Script Name-AI': 'rich_text' },
        expected: { matched: true, actualName: 'Script Name-AI', strategy: 'separator-agnostic' }
      },
      {
        name: 'Test 3: Parentheses stripping',
        proposed: 'Duration',
        existing: { 'Duration (s)': 'number' },
        expected: { matched: true, actualName: 'Duration (s)', strategy: 'parentheses-stripped' }
      },
      {
        name: 'Test 4: No match (expected failure)',
        proposed: 'NonExistent',
        existing: { 'Actual Prop': 'text' },
        expected: { matched: false, actualName: null, strategy: 'FAILED' }
      }
    ];

    const results = [];
    for (const testCase of testCases) {
      const result = this._validateAndMatchProperty_(testCase.proposed, testCase.existing, 3);
      const passed = result.matched === testCase.expected.matched &&
                     result.actualName === testCase.expected.actualName;
      
      results.push({
        test: testCase.name,
        passed: passed,
        expected: testCase.expected,
        actual: {
          matched: result.matched,
          actualName: result.actualName,
          strategy: result.strategy,
          attempts: result.attempts
        }
      });
      
      console.log(`${passed ? '✅' : '❌'} ${testCase.name}`);
      console.log(`  Expected: ${JSON.stringify(testCase.expected)}`);
      console.log(`  Actual: ${JSON.stringify(results[results.length - 1].actual)}`);
    }
    
    const allPassed = results.every(r => r.passed);
    console.log(`\n${allPassed ? '✅ All tests passed' : '❌ Some tests failed'}`);
    
    return {
      allPassed: allPassed,
      results: results
    };
  }
}

/**
 * Global wrapper for clasp run: testPropertyMatching
 */
function testPropertyMatching() {
  const UL = new UnifiedLoggerGAS(CONFIG.LOGGING);
  return UL.testPropertyMatching();
}

/**
 * Test function to diagnose Execution-Logs property loading
 * Run this from Apps Script editor to see detailed diagnostic logs
 */
function testExecutionLogProperties() {
  const UL = new UnifiedLoggerGAS(CONFIG.LOGGING);
  UL.init();
  // Force reload properties
  UL._loadExecutionLogProperties();
  console.log('Execution-Logs properties:', UL.executionLogProperties);
  console.log('Property count:', Object.keys(UL.executionLogProperties).length);
  return {
    propertyCount: Object.keys(UL.executionLogProperties).length,
    properties: UL.executionLogProperties
  };
}

/* ============================== NOTION CORE ============================== */
function getNotionApiKey() {
  let k = PROPS.getProperty('NOTION_API_KEY') || '';
  k = k.replace(/^[\'"\s]+|[\'"\s]+$/g, '').replace(/[\u200B-\u200D\uFEFF]/g, '').replace(/[^\x20-\x7E]/g, '');
  if (!k) {
    const errorMsg = 'NOTION_API_KEY is empty. Please set it using: setupScriptProperties("your-notion-api-key") or manually via File > Project Settings > Script Properties.';
    console.error('[ERROR]', errorMsg);
    throw new Error(errorMsg);
  }
  return k;
}
/**
 * Normalize a Notion database or page ID to UUID format (8-4-4-4-12).
 * The Notion API may require UUID format with hyphens for certain endpoints.
 * @param {string} idString - Notion ID in compact (32-char) or UUID format
 * @returns {string} ID in UUID format (8-4-4-4-12) or original if invalid
 */
function normalizeNotionId_(idString) {
  if (!idString) return idString;
  const cleanId = String(idString).trim().replace(/-/g, '');
  if (!/^[0-9a-f]{32}$/i.test(cleanId)) return idString;
  return [
    cleanId.slice(0, 8),
    cleanId.slice(8, 12),
    cleanId.slice(12, 16),
    cleanId.slice(16, 20),
    cleanId.slice(20, 32)
  ].join('-');
}

function notionFetch_(endpoint, method = 'GET', body = null) {
  const url = `https://api.notion.com/v1/${endpoint}`;
  const base = {
    method,
    muteHttpExceptions: true,
    headers: {
      'Authorization': `Bearer ${getNotionApiKey()}`,
      'Notion-Version': CONFIG.NOTION_VERSION,
      'Content-Type': 'application/json'
    }
  };
  for (let attempt = 0; attempt <= CONFIG.API_RETRY_COUNT; attempt++) {
    const opts = { ...base };
    if (body && method !== 'GET') { opts.payload = JSON.stringify(body); opts.contentType = 'application/json'; }
    const res = UrlFetchApp.fetch(url, opts);
    const code = res.getResponseCode();
    const txt = res.getContentText();
    if (code === 429) {
      const headers = res.getAllHeaders();
      const ra = Number(headers['Retry-After'] || headers['retry-after'] || 0) || (CONFIG.API_RATE_LIMIT_DELAY_MS / 1000);
      sleep((ra * 1000) + attempt * 250);
      continue;
    }
    if (code >= 500 && attempt < CONFIG.API_RETRY_COUNT) { sleep(CONFIG.API_RETRY_DELAY_MS * (attempt + 1)); continue; }
    if (code >= 400) {
      const errorDetails = {
        code,
        endpoint,
        method,
        response: txt,
        attempt: attempt + 1
      };
      throw new Error(`Notion API ${code}: ${txt} | Endpoint: ${endpoint} | Method: ${method} | Attempt: ${attempt + 1}`);
    }
    try { return JSON.parse(txt); } catch { throw new Error(`Cannot parse Notion response: ${txt}`); }
  }
  throw new Error('Notion request failed after retries.');
}

/* ============================== SINGLE IN PROGRESS INVARIANT VALIDATION ============================== */
function validateSingleInProgressInvariant_(dbId, UL) {
  if (!CONFIG.AGENT_TASKS_DB_IDS.includes(dbId)) return; // Only for Agent-Tasks

  try {
    UL.debug('Validating Single In Progress Invariant', { dbId });

    // Ensure Status property exists before querying
    const dsId = resolveDatabaseToDataSourceId_(dbId, UL);
    const statusPropNames = ['MCP Execution Status', 'Status', 'Execution Status'];
    let statusPropName = null;
    try {
      const endpoint = dsId ? `data_sources/${dsId}` : `databases/${dbId}`;
      const db = notionFetch_(endpoint, 'GET');
      const existingProps = db.properties || {};
      for (const propName of statusPropNames) {
        if (existingProps[propName]) {
          statusPropName = propName;
          break;
        }
      }
    } catch (e) {
      UL.warn('Unable to inspect database properties for Status', { dbId, error: String(e) });
    }

    if (!statusPropName) {
      try {
        if (ensurePropertyExists_(dbId, 'Status', 'select', UL)) {
          statusPropName = 'Status';
        }
      } catch (e) {
        // ensurePropertyExists_ already logs on failure
      }
    }

    if (!statusPropName) {
      UL.warn('Cannot validate Single In Progress Invariant - Status property missing', { dbId });
      return;
    }

    // Query for all tasks with Status = "In Progress"
    // Use the status property name we found/created
    const filter = {
      property: statusPropName,
      select: {
        equals: 'In Progress'
      }
    };

    // Use data_sources API exclusively (standardized on 2025-09-03+)
    if (!dsId) {
      UL?.warn?.('Cannot query database - data_source_id not available', { dbId });
      return { results: [], inProgressCount: 0 };
    }
    const queryResource = `data_sources/${dsId}/query`;
    const results = notionFetch_(queryResource, 'POST', { filter });
    const inProgressCount = results.results.length;

    if (inProgressCount === 0) {
      UL.info('Single In Progress Invariant: No tasks in progress (valid)');
    } else if (inProgressCount === 1) {
      UL.info('Single In Progress Invariant: Exactly one task in progress (valid)', {
        taskId: results.results[0].id
      });
    } else {
      // VIOLATION: More than one task in progress
      const taskIds = results.results.map(p => p.id);
      const taskTitles = results.results.map(p => {
        const titleProp = p.properties['Name'] || p.properties['Task'] || p.properties['title'];
        if (titleProp?.title?.[0]?.plain_text) {
          return titleProp.title[0].plain_text;
        }
        return 'Unknown';
      });

      UL.warn('Single In Progress Invariant VIOLATED', {
        count: inProgressCount,
        taskIds: taskIds,
        taskTitles: taskTitles,
        message: `Found ${inProgressCount} tasks with Status "In Progress". Expected 0 or 1.`
      });
    }
  } catch (e) {
    UL.error('Failed to validate Single In Progress Invariant', {
      error: String(e),
      stack: e.stack,
      dbId: dbId
    });
  }
}

/* ============================== TASK ROUTING LOGIC ============================== */
/**
 * Maps agent names to their trigger inbox folder paths
 * @returns {Object} Map of agent names to folder paths
 */
function getAgentTriggerInboxPaths_() {
  const basePath = '/Users/brianhellemn/Library/CloudStorage/GoogleDrive-brian@serenmedia.co/My Drive/Agents/Agent-Triggers-gd';
  
  return {
    'Cursor MM1 Agent': `${basePath}/Cursor-MM1-Agent-Trigger-gd/01_inbox`,
    'Cursor MM2 Agent': `${basePath}/Cursor-MM2-Agent-Trigger-gd/01_inbox`,
    'Claude MM1 Agent': `${basePath}/Claude-MM1-Agent-Trigger-gd/01_inbox`,
    'Claude MM2 Agent': `${basePath}/Claude-MM2-Agent-Trigger-gd/01_inbox`,
    'Codex MM1 Agent': `${basePath}/Codex-MM1-Agent-Trigger-gd/01_inbox`,
    'ChatGPT Code Review Agent': `${basePath}/ChatGPT-Code-Review-Agent-Trigger-gd/01_inbox`,
    'ChatGPT Personal Assistant Agent': `${basePath}/ChatGPT-Personal-Assistant-Agent-Trigger-gd/01_inbox`,
    'ChatGPT Strategic Agent': `${basePath}/ChatGPT-Strategic-Agent-Trigger-gd/01_inbox`,
    'Notion AI Data Operations Agent': `${basePath}/Notion-AI-Data-Operations-Agent-Trigger-gd/01_Inbox`,
    'Notion AI Research Agent': `${basePath}/Notion-AI-Research-Agent-Trigger-gd/01_inbox`
  };
}

/**
 * Queries Agent-Tasks database for In Progress tasks and returns task details
 * @param {string} dbId - Agent-Tasks database ID
 * @param {Object} UL - Unified logger instance
 * @returns {Array} Array of task objects with pageId, title, assignedAgent, and pageUrl
 */
function getInProgressTasks_(dbId, UL) {
  try {
    UL.debug('Querying for In Progress tasks', { dbId });
    
    // COMPREHENSIVE PROPERTY VALIDATION: Ensure required properties exist before querying
    // Try to create Status property if it doesn't exist
    const statusPropNames = ['MCP Execution Status', 'Status', 'Execution Status'];
    let statusPropName = null;
    let statusPropCreated = false;
    
    for (const propName of statusPropNames) {
      // Check if property exists first
      try {
        const dsId = resolveDatabaseToDataSourceId_(dbId, UL);
        const endpoint = dsId ? `data_sources/${dsId}` : `databases/${dbId}`;
        const db = notionFetch_(endpoint, 'GET');
        const existingProps = db.properties || {};
        
        if (existingProps[propName]) {
          statusPropName = propName;
          break;
        }
      } catch (e) {
        // Continue to next property name
      }
    }
    
    // If no status property found, create one
    if (!statusPropName) {
      const defaultStatusProp = 'Status';
      if (ensurePropertyExists_(dbId, defaultStatusProp, 'select', UL)) {
        statusPropName = defaultStatusProp;
        statusPropCreated = true;
        UL.info('Created Status property for task querying', {
          dbId,
          propertyName: defaultStatusProp
        });
      }
    }
    
    if (!statusPropName) {
      UL.warn('Cannot query In Progress tasks - no Status property found or created', { dbId });
      return [];
    }
    
    // Ensure Name/Task/Title property exists for extracting task titles
    const titlePropNames = ['Name', 'Task', 'Title', 'title'];
    let titlePropExists = false;
    for (const propName of titlePropNames) {
      if (ensurePropertyExists_(dbId, propName, 'title', UL)) {
        titlePropExists = true;
        break;
      }
    }
    
    if (!titlePropExists) {
      // Create Name property as fallback
      if (ensurePropertyExists_(dbId, 'Name', 'title', UL)) {
        UL.info('Created Name property for task title extraction', { dbId });
      }
    }
    
    const filter = {
      property: statusPropName,
      select: {
        equals: 'In Progress'
      }
    };
    
    // Resolve database_id to data_source_id for querying (standardized on data_sources API)
    const dsId = resolveDatabaseToDataSourceId_(dbId, UL);
    if (!dsId) {
      UL?.warn?.('Cannot query database - data_source_id not available', { dbId });
      return [];
    }
    const queryResource = `data_sources/${dsId}/query`;
    const results = notionFetch_(queryResource, 'POST', { filter });
    const tasks = [];
    
    for (const page of results.results) {
      // Extract task title
      const titleProp = page.properties['Name'] || page.properties['Task'] || page.properties['Title'] || page.properties['title'];
      let title = 'Untitled Task';
      if (titleProp?.title?.[0]?.plain_text) {
        title = titleProp.title[0].plain_text;
      } else if (titleProp?.rich_text?.[0]?.plain_text) {
        title = titleProp.rich_text[0].plain_text;
      }
      
      // Extract assigned agent
      const agentProp = page.properties['MCP Assigned Agent'] || page.properties['Assigned Agent'] || page.properties['Agent'];
      let assignedAgent = null;
      if (agentProp?.select?.name) {
        assignedAgent = agentProp.select.name;
      } else if (agentProp?.rich_text?.[0]?.plain_text) {
        assignedAgent = agentProp.rich_text[0].plain_text;
      }
      
      // Get page URL
      const pageUrl = page.url || `https://www.notion.so/${page.id.replace(/-/g, '')}`;
      
      tasks.push({
        pageId: page.id,
        title: title,
        assignedAgent: assignedAgent,
        pageUrl: pageUrl,
        page: page
      });
    }
    
    UL.info('Found In Progress tasks', { 
      count: tasks.length, 
      taskIds: tasks.map(t => t.pageId),
      tasks: tasks.map(t => ({
        pageId: t.pageId,
        pageUrl: t.pageUrl,
        title: t.title,
        assignedAgent: t.assignedAgent
      }))
    });
    return tasks;
    
  } catch (e) {
    UL.error('Failed to query In Progress tasks', {
      error: String(e),
      stack: e.stack,
      dbId: dbId
    });
    return [];
  }
}

/**
 * Gets the backup file path/URL for a task from the CSV export
 * @param {string} taskPageId - Notion page ID of the task
 * @param {Folder} parentFolder - Google Drive parent folder for workspace databases
 * @param {Object} UL - Unified logger instance
 * @returns {string|null} File URL or path, null if not found
 */
function getTaskBackupFilePath_(taskPageId, parentFolder, UL) {
  try {
    // The CSV files are stored in folders named after the database
    // Format: {parentFolder}/Agent-Tasks_{dbId}/Agent-Tasks_{dbId}.csv
    const baseAgentTasksId = (CONFIG.AGENT_TASKS_DB_IDS || []).find(Boolean) || DB_CONFIG.AGENT_TASKS_PRIMARY;
    if (!baseAgentTasksId) {
      UL.warn('Agent-Tasks database ID not configured for backup path lookup', { taskPageId });
      return null;
    }
    const dbId = baseAgentTasksId.replace(/-/g, '');
    const csvFileName = `Agent-Tasks_${dbId}.csv`;
    const folderName = `Agent-Tasks_${dbId}`;
    
    // Try to find the folder and file in Drive
    try {
      const dbFolders = parentFolder.getFoldersByName(folderName);
      if (dbFolders.hasNext()) {
        const dbFolder = dbFolders.next();
        const csvFiles = dbFolder.getFilesByName(csvFileName);
        if (csvFiles.hasNext()) {
          const csvFile = csvFiles.next();
          const fileUrl = csvFile.getUrl();
          UL.debug('Found task backup CSV file', {
            taskPageId: taskPageId,
            fileName: csvFileName,
            fileUrl: fileUrl
          });
          return fileUrl;
        }
      }
    } catch (searchError) {
      UL.debug('Could not search for CSV file in Drive', {
        error: String(searchError),
        folderName: folderName,
        fileName: csvFileName
      });
    }
    
    // Fallback: return the expected path structure
    const parentUrl = parentFolder.getUrl();
    return `${parentUrl} (expected: ${folderName}/${csvFileName})`;
    
  } catch (e) {
    UL.warn('Could not determine task backup file path', { error: String(e), taskPageId });
    return null;
  }
}

/**
 * Gets or creates the agent's inbox folder in Google Drive
 * @param {string} agentName - Name of the agent
 * @param {Object} UL - Unified logger instance
 * @returns {Folder|null} Google Drive folder or null if not found/created
 */
function getOrCreateAgentInboxFolder_(agentName, UL) {
  try {
    const agentPaths = getAgentTriggerInboxPaths_();
    const inboxPath = agentPaths[agentName];
    
    if (!inboxPath) {
      UL.warn('Unknown agent name, cannot find inbox folder', { agentName, knownAgents: Object.keys(agentPaths) });
      return null;
    }
    
    // Parse the path: /Users/.../My Drive/Agents/Agent-Triggers-gd/{Agent-Name}/01_inbox
    // Extract the folder name (last part before 01_inbox)
    const pathParts = inboxPath.split('/');
    const agentFolderName = pathParts[pathParts.length - 2]; // e.g., "Cursor-MM1-Agent-Trigger-gd"
    const inboxFolderName = pathParts[pathParts.length - 1]; // "01_inbox"
    
    // Start from root and navigate to the folder
    // Path structure: My Drive/Agents/Agent-Triggers-gd/{agentFolderName}/01_inbox
    let currentFolder = DriveApp.getRootFolder();
    
    // Navigate to Agents folder
    let agentsFolder = null;
    const agentsFolders = currentFolder.getFoldersByName('Agents');
    if (agentsFolders.hasNext()) {
      agentsFolder = agentsFolders.next();
    } else {
      UL.warn('Agents folder not found in Drive root', { path: inboxPath });
      return null;
    }
    
    // Navigate to Agent-Triggers-gd folder
    let triggersFolder = null;
    const triggersFolders = agentsFolder.getFoldersByName('Agent-Triggers-gd');
    if (triggersFolders.hasNext()) {
      triggersFolder = triggersFolders.next();
    } else {
      UL.warn('Agent-Triggers-gd folder not found', { path: inboxPath });
      return null;
    }
    
    // Navigate to agent-specific folder
    let agentFolder = null;
    const agentFolders = triggersFolder.getFoldersByName(agentFolderName);
    if (agentFolders.hasNext()) {
      agentFolder = agentFolders.next();
    } else {
      UL.warn('Agent folder not found, attempting to create', { agentFolderName, path: inboxPath });
      // Try to create if it doesn't exist (may fail due to permissions)
      try {
        agentFolder = triggersFolder.createFolder(agentFolderName);
        UL.info('Created agent folder', { agentFolderName });
      } catch (createError) {
        UL.error('Failed to create agent folder', { error: String(createError), agentFolderName });
        return null;
      }
    }
    
    // Navigate to 01_inbox folder
    let inboxFolder = null;
    const inboxFolders = agentFolder.getFoldersByName(inboxFolderName);
    if (inboxFolders.hasNext()) {
      inboxFolder = inboxFolders.next();
    } else {
      UL.info('Inbox folder not found, creating', { inboxFolderName, agentFolderName });
      try {
        inboxFolder = agentFolder.createFolder(inboxFolderName);
        UL.info('Created inbox folder', { inboxFolderName, agentFolderName });
      } catch (createError) {
        UL.error('Failed to create inbox folder', { error: String(createError), inboxFolderName });
        return null;
      }
    }
    
    return inboxFolder;
    
  } catch (e) {
    UL.error('Failed to get or create agent inbox folder', {
      error: String(e),
      stack: e.stack,
      agentName: agentName
    });
    return null;
  }
}

/**
 * Checks if a trigger file already exists for a specific task
 * Respects both DriveSheetsSync (.md) and Project Manager Bot (.json) file formats
 * @param {Folder} inboxFolder - Google Drive inbox folder
 * @param {string} taskPageId - Notion page ID of the task
 * @param {Object} UL - Unified logger instance
 * @returns {File|null} Existing trigger file or null
 */
function findExistingTriggerFileForTask_(inboxFolder, taskPageId, UL) {
  try {
    const taskIdShort = taskPageId.substring(0, 8);
    const taskIdFull = taskPageId.replace(/-/g, ''); // Also check without dashes
    const existingFiles = inboxFolder.getFiles();
    const maxAge = 10 * 60 * 1000; // 10 minutes in milliseconds
    const now = Date.now();
    
    while (existingFiles.hasNext()) {
      const file = existingFiles.next();
      const fileName = file.getName();
      
      // Check for trigger files in multiple formats:
      // 1. DriveSheetsSync format: task-{taskIdShort}-{timestamp}.md
      // 2. Project Manager Bot format: agent-task-{taskIdFull}-{timestamp}.json
      // 3. Any file containing the task ID (with or without dashes)
      const isTriggerFile = (fileName.endsWith('.md') || fileName.endsWith('.json')) &&
                           (fileName.includes(taskIdShort) || fileName.includes(taskIdFull) ||
                            fileName.includes('agent-task-') || fileName.startsWith('task-'));
      
      if (isTriggerFile) {
        // Additional validation: ensure it's actually for this task
        const matchesTask = fileName.includes(taskIdShort) || 
                           fileName.includes(taskIdFull) ||
                           (fileName.includes('agent-task-') && fileName.includes(taskPageId.replace(/-/g, '')));
        
        if (matchesTask) {
          const fileAge = now - file.getDateCreated().getTime();
          
          // If file is recent (within 10 minutes), consider it existing
          // This prevents conflicts between DriveSheetsSync and Project Manager Bot
          if (fileAge < maxAge) {
            UL.debug('Found existing trigger file for task (respecting multi-script coexistence)', {
              fileName: fileName,
              fileId: file.getId(),
              taskPageId: taskPageId,
              ageMinutes: Math.round(fileAge / 60000),
              format: fileName.endsWith('.md') ? 'markdown' : 'json',
              source: fileName.includes('agent-task-') ? 'ProjectManagerBot' : 'DriveSheetsSync'
            });
            return file;
          }
        }
      }
    }
    return null;
  } catch (e) {
    UL.warn('Error checking for existing trigger file', {
      error: String(e),
      taskPageId: taskPageId
    });
    return null;
  }
}

/**
 * Deletes existing trigger files in the inbox folder
 * Supports both .md (DriveSheetsSync) and .json (Project Manager Bot) trigger files
 * Respects multi-script coexistence: only deletes files for the specific task
 * @param {Folder} inboxFolder - Google Drive inbox folder
 * @param {string} taskPageId - Optional: specific task ID to delete files for (if null, deletes all)
 * @param {Object} UL - Unified logger instance
 * @param {boolean} onlyOwnFiles - If true, only delete DriveSheetsSync files (.md), not Project Manager Bot files (.json)
 * @returns {number} Number of files deleted
 */
function deleteExistingTriggerFiles_(inboxFolder, taskPageId, UL, onlyOwnFiles) {
  onlyOwnFiles = onlyOwnFiles !== undefined ? onlyOwnFiles : false;
  let deletedCount = 0;
  try {
    const existingFiles = inboxFolder.getFiles();
    const taskIdShort = taskPageId ? taskPageId.substring(0, 8) : null;
    const taskIdFull = taskPageId ? taskPageId.replace(/-/g, '') : null;
    
    while (existingFiles.hasNext()) {
      const file = existingFiles.next();
      const fileName = file.getName();
      
      // Identify trigger file types
      const isMarkdownFile = fileName.endsWith('.md');
      const isJsonFile = fileName.endsWith('.json');
      const isProjectManagerBotFile = fileName.startsWith('agent-task-');
      const isDriveSheetsSyncFile = fileName.startsWith('task-') && isMarkdownFile;
      
      // If onlyOwnFiles is true, only delete DriveSheetsSync files (respect Project Manager Bot files)
      if (onlyOwnFiles && (isJsonFile || isProjectManagerBotFile)) {
        continue; // Skip Project Manager Bot files
      }
      
      // Check if it's a trigger file
      const isTriggerFile = isMarkdownFile || isJsonFile || isProjectManagerBotFile || fileName.startsWith('task-');
      
      // If taskPageId is provided, only delete files for that specific task
      // Match both short ID (first 8 chars) and full ID (with/without dashes)
      let matchesTask = true;
      if (taskIdShort || taskIdFull) {
        matchesTask = (taskIdShort && fileName.includes(taskIdShort)) ||
                     (taskIdFull && fileName.includes(taskIdFull)) ||
                     (taskPageId && fileName.includes(taskPageId.replace(/-/g, '')));
      }
      
      if (isTriggerFile && matchesTask) {
        // Only delete old files (older than 10 minutes) to avoid conflicts with active processes
        const fileAge = Date.now() - file.getDateCreated().getTime();
        const maxAge = 10 * 60 * 1000; // 10 minutes
        
        if (fileAge > maxAge) {
          file.setTrashed(true);
          deletedCount++;
          UL.debug('Deleted old trigger file (respecting multi-script coexistence)', {
            fileName: fileName,
            fileId: file.getId(),
            taskPageId: taskPageId || 'all',
            ageMinutes: Math.round(fileAge / 60000),
            format: isMarkdownFile ? 'markdown' : 'json',
            source: isProjectManagerBotFile ? 'ProjectManagerBot' : 'DriveSheetsSync'
          });
        } else {
          UL.debug('Skipped recent trigger file (may be active)', {
            fileName: fileName,
            ageMinutes: Math.round(fileAge / 60000)
          });
        }
      }
    }
    if (deletedCount > 0) {
      UL.info('Cleaned up old trigger files (respecting multi-script coexistence)', {
        deletedCount: deletedCount,
        taskPageId: taskPageId || 'all',
        onlyOwnFiles: onlyOwnFiles
      });
    }
  } catch (cleanupError) {
    UL.warn('Failed to clean up existing trigger files', {
      error: String(cleanupError),
      taskPageId: taskPageId || 'all'
    });
  }
  return deletedCount;
}

/**
 * Creates a trigger file in the agent's inbox folder
 * Implements deduplication: checks for existing files before creating
 * @param {string} agentName - Name of the agent
 * @param {Object} task - Task object with pageId, title, pageUrl, etc.
 * @param {string} backupFilePath - Local backup file path
 * @param {Object} UL - Unified logger instance
 * @returns {boolean} Success status
 */
function createAgentTriggerFile_(agentName, task, backupFilePath, UL) {
  try {
    // Get or create the inbox folder
    const inboxFolder = getOrCreateAgentInboxFolder_(agentName, UL);
    if (!inboxFolder) {
      UL.warn('Could not access agent inbox folder', { agentName });
      return false;
    }
    
    // Check if trigger file for this task already exists (deduplication)
    // This respects both DriveSheetsSync (.md) and Project Manager Bot (.json) files
    const existingFile = findExistingTriggerFileForTask_(inboxFolder, task.pageId, UL);
    if (existingFile) {
      UL.info('Trigger file for this task already exists (multi-script coexistence), skipping creation', {
        agentName: agentName,
        taskPageId: task.pageId,
        taskTitle: task.title,
        existingFileName: existingFile.getName(),
        existingFileId: existingFile.getId(),
        existingFileUrl: existingFile.getUrl(),
        existingFormat: existingFile.getName().endsWith('.md') ? 'markdown' : 'json',
        existingSource: existingFile.getName().includes('agent-task-') ? 'ProjectManagerBot' : 'DriveSheetsSync'
      });
      return true; // Consider it successful since file already exists (respects other scripts)
    }
    
    // Delete any old trigger files for this specific task (cleanup)
    // Only delete DriveSheetsSync files (.md) to respect Project Manager Bot files (.json)
    const deletedCount = deleteExistingTriggerFiles_(inboxFolder, task.pageId, UL, true);
    if (deletedCount > 0) {
      UL.info('Deleted old trigger files for task', {
        agentName: agentName,
        taskPageId: task.pageId,
        deletedCount: deletedCount
      });
    }
    
    // Create trigger file content
    const timestamp = nowIso();
    const fileName = `task-${task.pageId.substring(0, 8)}-${Date.now()}.md`;
    const triggerContent = `# Task Continuation Trigger

**Created:** ${timestamp}
**Task:** ${task.title}
**Notion Page ID:** ${task.pageId}
**Notion Page URL:** ${task.pageUrl}

## Instructions

Continue work on this task. The task is currently marked as "In Progress" in the Agent-Tasks database.

## Resources

- **Notion Task Page:** ${task.pageUrl}
- **Local Backup File:** ${backupFilePath || 'Path not available'}

## Context

This trigger was automatically created by the DriveSheetsSync script to ensure task continuity. Please review the task in Notion and proceed with execution according to the task requirements and workflow documentation.

**Note:** This script respects the 2-way Google Drive ↔ Notion sync and coexists with Project Manager Bot trigger files. Both scripts check for existing trigger files before creating new ones to prevent duplicates.

---
*Generated by DriveSheetsSync v2.4 - Task Routing System (Multi-Script Compatible)*
`;
    
    // Create the file in the inbox folder
    const triggerFile = inboxFolder.createFile(fileName, triggerContent, 'text/markdown');
    
    UL.info('Created agent trigger file', {
      agentName: agentName,
      taskTitle: task.title,
      taskPageId: task.pageId,
      fileName: fileName,
      fileId: triggerFile.getId(),
      fileUrl: triggerFile.getUrl()
    });
    
    return true;
    
  } catch (e) {
    UL.error('Failed to create agent trigger file', {
      error: String(e),
      stack: e.stack,
      agentName: agentName,
      taskPageId: task.pageId
    });
    return false;
  }
}

/**
 * Creates a task for Cursor MM1 Agent to review Agent-Tasks database and identify high-priority tasks
 * @param {string} dbId - Agent-Tasks database ID
 * @param {Object} UL - Unified logger instance
 * @returns {boolean} Success status
 */
function createCursorMM1ReviewTask_(dbId, UL) {
  try {
    UL.info('Creating Cursor MM1 Agent review task - no In Progress tasks found');
    
    // Get or create the Cursor MM1 Agent inbox folder
    const inboxFolder = getOrCreateAgentInboxFolder_('Cursor MM1 Agent', UL);
    if (!inboxFolder) {
      UL.error('Could not access Cursor MM1 Agent inbox folder');
      return false;
    }
    
    // Check if review task trigger file already exists (deduplication)
    const reviewFileNamePattern = 'review-agent-tasks-';
    const existingFiles = inboxFolder.getFiles();
    let existingReviewFile = null;
    
    while (existingFiles.hasNext()) {
      const file = existingFiles.next();
      const fileName = file.getName();
      if (fileName.includes(reviewFileNamePattern) && 
          (fileName.endsWith('.md') || fileName.endsWith('.json'))) {
        const fileAge = Date.now() - file.getDateCreated().getTime();
        // If file is recent (within 10 minutes), consider it existing
        if (fileAge < 10 * 60 * 1000) {
          existingReviewFile = file;
          break;
        }
      }
    }
    
    if (existingReviewFile) {
      UL.info('Review task trigger file already exists, skipping creation', {
        fileName: existingReviewFile.getName(),
        fileId: existingReviewFile.getId(),
        fileUrl: existingReviewFile.getUrl()
      });
      return true; // Consider it successful since file already exists
    }
    
    // Delete old review task trigger files (cleanup)
    // Only delete DriveSheetsSync files (.md) to respect Project Manager Bot files (.json)
    const deletedCount = deleteExistingTriggerFiles_(inboxFolder, null, UL, true);
    if (deletedCount > 0) {
      UL.info('Deleted old trigger files', {
        agentName: 'Cursor MM1 Agent',
        deletedCount: deletedCount
      });
    }
    
    const timestamp = nowIso();
    const dbUrl = `https://www.notion.so/${dbId.replace(/-/g, '')}`;
    const fileName = `review-agent-tasks-${Date.now()}.md`;
    
    const triggerContent = `# Agent-Tasks Database Review & Task Orchestration

**Created:** ${timestamp}
**Trigger Type:** No In Progress Tasks Found
**Agent:** Cursor MM1 Agent

## Instructions

Review the Agent-Tasks database and identify the most high-priority/urgent task based on:
1. Priority field (Critical → High → Medium → Low)
2. Created time (older tasks first)
3. Dependency Status (Ready or Dependencies Met)
4. Execution Authorization (if applicable)

## Task Selection Criteria

1. Filter tasks where:
   - MCP Execution Status != Completed
   - Dependency Status in [Ready, Dependencies Met]
   - If approvals used: Execution Authorization = Authorized OR Approval Status in [Approved, Conditionally Approved]

2. Sort by:
   - Priority (Critical → Low)
   - Created time (ascending)

3. Select the first matching task

## Next Steps

1. Review Agent-Tasks database: ${dbUrl}
2. Identify highest priority task
3. Proceed with orchestration and task handoff flow preparation
4. Create handoff tasks for:
   - Task execution (assign to appropriate execution agent based on environment/location/capabilities)
   - Task monitoring/review (assign to appropriate review agent)

## Resources

- **Agent-Tasks Database:** ${dbUrl}
- **Database ID:** ${dbId}

## Documentation

Refer to workspace documentation for:
- Task prioritization logic
- Agent selection criteria
- Handoff flow procedures
- Environment/location-based agent routing

---
*Generated by DriveSheetsSync v2.2 - Task Routing System*
`;
    
    // Create the file in the inbox folder
    const triggerFile = inboxFolder.createFile(fileName, triggerContent, 'text/markdown');
    
    UL.info('Created Cursor MM1 Agent review trigger', {
      fileName: fileName,
      fileId: triggerFile.getId(),
      fileUrl: triggerFile.getUrl(),
      dbId: dbId,
      dbUrl: dbUrl
    });
    
    return true;
    
  } catch (e) {
    UL.error('Failed to create Cursor MM1 review task', {
      error: String(e),
      stack: e.stack,
      dbId: dbId
    });
    return false;
  }
}

/**
 * Main task routing function - creates trigger files for In Progress tasks or review task
 * 
 * GLOBAL SINGLE-ITEM RULE: Only the single most recently created In Progress task
 * is selected for trigger file creation. All other tasks are skipped for this cycle.
 * 
 * @param {string} dbId - Agent-Tasks database ID
 * @param {Folder} parentFolder - Google Drive parent folder for workspace databases
 * @param {Object} UL - Unified logger instance
 */
function routeTasksToAgents_(dbId, parentFolder, UL) {
  try {
    UL.info('🔄 Starting task routing logic');
    
    // Query for In Progress tasks
    const inProgressTasks = getInProgressTasks_(dbId, UL);
    
    if (inProgressTasks.length === 0) {
      // No In Progress tasks - create review task for Cursor MM1 Agent
      UL.info('No In Progress tasks found - creating Cursor MM1 Agent review task');
      createCursorMM1ReviewTask_(dbId, UL);
      return;
    }
    
    // GLOBAL SINGLE-ITEM RULE: Select only the most recently created task
    // Sort tasks by created_time descending (most recent first)
    const sortedTasks = inProgressTasks.sort((a, b) => {
      const aTime = a.page?.created_time || a.createdTime || '';
      const bTime = b.page?.created_time || b.createdTime || '';
      // Compare ISO timestamps (most recent first)
      if (!aTime && !bTime) return 0;
      if (!aTime) return 1;
      if (!bTime) return -1;
      return bTime.localeCompare(aTime); // Most recent first
    });
    
    const selectedTask = sortedTasks[0];
    const skippedTasks = sortedTasks.slice(1);
    
    // Log skipped tasks due to global single-item rule
    if (skippedTasks.length > 0) {
      UL.info('Global single-item rule: Selecting single most recent task, skipping others', {
        selectedTask: {
          pageId: selectedTask.pageId,
          title: selectedTask.title,
          assignedAgent: selectedTask.assignedAgent,
          createdTime: selectedTask.page?.created_time || selectedTask.createdTime
        },
        skippedCount: skippedTasks.length,
        skippedTasks: skippedTasks.map(t => ({
          pageId: t.pageId,
          title: t.title,
          assignedAgent: t.assignedAgent,
          createdTime: t.page?.created_time || t.createdTime
        }))
      });
    }
    
    // Process only the selected task
    if (!selectedTask.assignedAgent) {
      UL.warn('Selected task has no assigned agent, skipping trigger creation', {
        taskPageId: selectedTask.pageId,
        taskTitle: selectedTask.title
      });
      return;
    }
    
    // Get backup file path/URL
    const backupFilePath = getTaskBackupFilePath_(selectedTask.pageId, parentFolder, UL);
    
    // Create trigger file only for selected task
    const success = createAgentTriggerFile_(selectedTask.assignedAgent, selectedTask, backupFilePath, UL);
    
    if (success) {
      UL.info('Created trigger file for selected task', {
        agentName: selectedTask.assignedAgent,
        taskTitle: selectedTask.title,
        taskPageId: selectedTask.pageId,
        skippedCount: skippedTasks.length
      });
    } else {
      UL.warn('Failed to create trigger file for selected task', {
        agentName: selectedTask.assignedAgent,
        taskPageId: selectedTask.pageId
      });
    }
    
    UL.info('✅ Task routing completed (global single-item rule applied)', {
      tasksRouted: 1,
      tasksSkipped: skippedTasks.length,
      agentNotified: selectedTask.assignedAgent
    });
    
  } catch (e) {
    UL.error('Task routing failed', {
      error: String(e),
      stack: e.stack,
      dbId: dbId
    });
  }
}

/* ============================== DATA SOURCES ============================== */
function searchAllDataSources_() {
  const out = [];
  let cursor = null, loops = 0;
  while (loops < 30) {
    const body = { page_size: 100, filter: { property: 'object', value: 'data_source' } };
    if (cursor) body.start_cursor = cursor;
    const res = notionFetch_('search', 'POST', body);
    (res.results || []).forEach(r => { if (r.object === 'data_source') out.push(r); });
    if (!res.has_more) break;
    cursor = res.next_cursor;
    loops++;
  }
  return out;
}

/**
 * Legacy/meta helper for diagnostics only.
 * Uses the Data Sources API to stay aligned with the data_sources-first model.
 */
function listAllNotionDatabases() {
  try {
    return searchAllDataSources_();
  } catch (e) {
    const err = String(e);
    console.error('Error listing data sources:', err);
    return [];
  }
}

/**
 * Resolves Notion databases (data_sources) from search results - diagnostics only.
 */
function resolveNotionDatabases() {
  try {
    return listAllNotionDatabases();
  } catch (e) {
    const err = String(e);
    console.error('Failed to resolve Notion data sources:', err);
    return [];
  }
}

/**
 * Resolves runtime configuration and databases for meta/diagnostic flows.
 */
function resolveRuntime() {
  try {
    const databases = resolveNotionDatabases();
    return {
      databases: databases,
      count: databases.length,
      resolved: true,
      apiModel: 'data_source'
    };
  } catch (e) {
    const err = String(e);
    console.error('Failed to resolve runtime:', err);
    return {
      databases: [],
      count: 0,
      resolved: false,
      error: err,
      apiModel: 'data_source'
    };
  }
}

/**
 * Meta database sync function (non-destructive placeholder for diagnostics)
 */
function runMetaDatabaseSync() {
  try {
    const runtime = resolveRuntime();
    if (!runtime.resolved) {
      console.error('Cannot run meta database sync - runtime resolution failed');
      return { success: false, error: runtime.error };
    }
    return { success: true, databasesProcessed: runtime.count, apiModel: runtime.apiModel };
  } catch (e) {
    const err = String(e);
    console.error('Meta database sync failed:', err);
    return { success: false, error: err };
  }
}

function getDataSource_(dataSourceId, UL) {
  try {
    return notionFetch_(`data_sources/${dataSourceId}`, 'GET');
  } catch (e) {
    const err = String(e);
    const stack = e.stack || 'No stack trace available';
    if (err.includes('404')) { 
      UL?.warn?.('Database not shared with integration (404)', { dataSourceId, error: err, stack }); 
      return null; 
    }
    if (err.includes('403')) { 
      UL?.warn?.('Insufficient permissions for database (403)', { dataSourceId, error: err, stack }); 
      return null; 
    }
    UL?.error?.('Unexpected error reading database', { dataSourceId, error: err, stack }); 
    return null;
  }
}
function queryDataSourcePages_(dataSourceId, UL) {
  const pages = [];
  let cursor = null, loops = 0;
  const maxLoops = Math.ceil(CONFIG.MAX_PAGES_PER_DATA_SOURCE / 100);
  while (loops < maxLoops) {
    try {
      const body = { page_size: 100 };
      if (cursor) body.start_cursor = cursor;
      const res = notionFetch_(`data_sources/${dataSourceId}/query`, 'POST', body);
      const results = res.results || [];
      pages.push(...results);
      UL?.debug?.('Fetched page batch from database', { dataSourceId, fetched: results.length, totalSoFar: pages.length });
      if (!res.has_more || pages.length >= CONFIG.MAX_PAGES_PER_DATA_SOURCE) break;
      cursor = res.next_cursor;
      loops++;
    } catch (e) {
      const errorMsg = String(e);
      const stack = e.stack || 'No stack trace available';
      UL?.error?.('Failed to query pages from database', { dataSourceId, error: errorMsg, stack });
      break;
    }
  }
  return pages;
}

/* ============================== SCHEMA HELPERS ============================== */

/**
 * Resolve a database_id to its first data_source_id, or return the ID if it's already a data_source_id.
 * Caches results per run so we only hit the API once.
 * 
 * This function handles both cases:
 * 1. Input is a database_id (from config) - resolves to data_source_id
 * 2. Input is already a data_source_id (from search results) - returns it directly
 * 
 * @param {string} databaseId - The database container ID or data_source_id
 * @param {Object} UL - Logger utility
 * @returns {string|null} The data_source_id or null if resolution fails
 */
function resolveDatabaseToDataSourceId_(databaseId, UL) {
  if (!databaseId) return null;

  // Normalize the ID to UUID format (8-4-4-4-12) - Notion API may require this
  const normalizedId = normalizeNotionId_(databaseId);

  // Cache key for this database (use normalized ID for consistent caching)
  const cacheKey = `_DS_ID_${normalizedId}`;
  if (CONFIG[cacheKey]) {
    return CONFIG[cacheKey];
  }

  // First, try if the ID is already a data_source_id (from search results)
  // This is the common case when processing databases from searchAllDataSources_()
  try {
    const ds = notionFetch_(`data_sources/${normalizedId}`, 'GET');
    if (ds && ds.id) {
      // It's already a data_source_id - cache and return it
      CONFIG[cacheKey] = normalizedId;
      UL?.debug?.('Input is already a data_source_id', {
        dataSourceId: normalizedId,
        originalId: databaseId
      });
      return normalizedId;
    }
  } catch (e) {
    // Not a data_source_id, continue to try as database_id
    UL?.debug?.('Input is not a data_source_id, trying as database_id', {
      databaseId: normalizedId,
      originalId: databaseId
    });
  }
  
  // Second, try if it's a database_id (from config) - resolve to data_source_id
  try {
    const db = notionFetch_(`databases/${normalizedId}`, 'GET');

    // Try different possible field names for data sources
    const sources = db.data_sources || db.dataSources || db.sources || [];

    if (!sources || sources.length === 0) {
      UL?.debug?.('Database has no data sources array in direct response, trying search fallback', {
        databaseId: normalizedId,
        originalId: databaseId,
        dbKeys: Object.keys(db).slice(0, 20)
      });
      // Don't return null here - fall through to search API fallback
      throw new Error('No data_sources array - try search fallback');
    }

    const dsId = sources[0].id;
    CONFIG[cacheKey] = dsId; // cache for this run

    UL?.info?.('Resolved data_source_id from database', {
      databaseId: normalizedId,
      originalId: databaseId,
      dataSourceId: dsId
    });

    return dsId;
  } catch (e) {
    const err = String(e);
    // If direct access failed, try search API as fallback (database might be accessible via search)
    if (err.includes('404') || err.includes('object_not_found')) {
      UL?.debug?.('Direct database access failed, trying search API as fallback', {
        databaseId: normalizedId,
        originalId: databaseId
      });

      try {
        // Try to find database via search API
        // Search API only accepts "page" or "data_source" as filter values, not "database"
        // So we search for data_source objects and match by compact ID
        const compactId = normalizedId.replace(/-/g, '').toLowerCase();
        let found = null;
        
        // Try searching for data_source objects
        const searchBody = {
          filter: { property: 'object', value: 'data_source' },
          page_size: 100
        };
        
        let searchCursor = null;
        
        // Search through results to find matching data_source
        // Match by: 1) parent.database_id, 2) direct ID match (for data_source IDs passed as input)
        for (let searchLoops = 0; searchLoops < 10 && !found; searchLoops++) {
          if (searchCursor) searchBody.start_cursor = searchCursor;

          const searchResults = notionFetch_('search', 'POST', searchBody);
          const results = searchResults.results || [];

          for (const result of results) {
            // Check if this data_source's parent database matches our database_id
            const parentDbId = (result.parent?.database_id || '').replace(/-/g, '').toLowerCase();
            if (parentDbId === compactId) {
              found = result;
              UL?.debug?.('Found data_source by parent.database_id match', {
                dataSourceId: result.id,
                parentDatabaseId: result.parent?.database_id,
                targetDatabaseId: normalizedId
              });
              break;
            }
            // Also check direct ID match (in case input was already a data_source_id)
            const resultId = (result.id || '').replace(/-/g, '').toLowerCase();
            if (resultId === compactId) {
              found = result;
              UL?.debug?.('Found data_source by direct ID match', {
                dataSourceId: result.id,
                targetId: normalizedId
              });
              break;
            }
          }

          if (found || !searchResults.next_cursor) break;
          searchCursor = searchResults.next_cursor;
        }

        if (found && found.object === 'data_source' && found.id) {
          // Found matching data_source - cache and return
          CONFIG[cacheKey] = found.id;
          UL?.info?.('Resolved data_source_id via search API', {
            databaseId: normalizedId,
            originalId: databaseId,
            dataSourceId: found.id
          });
          return found.id;
        }

        // Since we've already normalized the ID at the top of the function,
        // the "formatted ID" retry logic is no longer needed here.
        // The normalizeNotionId_ function handles the UUID formatting.

      } catch (searchErr) {
        UL?.debug?.('Search API fallback also failed', {
          databaseId: normalizedId,
          originalId: databaseId,
          error: String(searchErr)
        });
      }

      UL?.debug?.('Input is not a database_id (expected if already a data_source_id)', {
        databaseId: normalizedId,
        originalId: databaseId
      });
    } else {
      UL?.error?.('Failed to resolve data_source_id from database', {
        databaseId: normalizedId,
        originalId: databaseId,
        error: err,
        stack: e.stack || 'No stack trace'
      });
    }
    return null;
  }
}

function fetchDatabaseSchema_(dbId, UL) {
  // Special case: If this is Execution-Logs, resolve database_id to data_source_id first
  if (dbId === CONFIG.EXECUTION_LOGS_DB_ID) {
    const dsId = resolveDatabaseToDataSourceId_(dbId, UL);
    if (dsId) {
      try {
        const ds = notionFetch_(`data_sources/${dsId}`, 'GET');
        const props = ds.properties || {};
        let titleName = null;
        for (const [k, v] of Object.entries(props)) {
          if (v.type === 'title') {
            titleName = k;
            break;
          }
        }
        return { ok: true, props, titleName };
      } catch (e) {
        UL?.warn?.('Failed to fetch Execution-Logs schema via data_sources, falling back to databases', {
          databaseId: dbId,
          dataSourceId: dsId,
          error: String(e)
        });
        // Fall through to database fallback
      }
    }
  }
  
  // Primary path for modern workspaces: treat IDs as data_source IDs first.
  try {
    const ds = notionFetch_(`data_sources/${dbId}`, 'GET');
    const props = ds.properties || {};
    let titleName = null;
    for (const [k, v] of Object.entries(props)) {
      if (v.type === 'title') {
        titleName = k;
        break;
      }
    }
    return { ok: true, props, titleName };
  } catch (e) {
    const err = String(e);
    const stack = e.stack || 'No stack trace available';

    // Fallback to legacy /databases/{id} for any true database IDs that may still exist.
    try {
      const db = notionFetch_(`databases/${dbId}`, 'GET');
      const props = db.properties || {};
      let titleName = null;
      for (const [k, v] of Object.entries(props)) {
        if (v.type === 'title') {
          titleName = k;
          break;
        }
      }
      return { ok: true, props, titleName };
    } catch (e2) {
      const err2 = String(e2);
      const stack2 = e2.stack || 'No stack trace available';
      if (err2.includes('404') || err2.includes('403')) {
        UL?.warn?.('Cannot access database schema via /databases API', {
          databaseId: dbId,
          error: err2,
          stack: stack2
        });
      } else {
        UL?.error?.('Unexpected error reading database schema', {
          databaseId: dbId,
          error: err2,
          stack: stack2
        });
      }
      return { ok: false, props: {}, titleName: null };
    }
  }
}

/**
 * Fallback: Fetch database schema by querying a page
 * This works even when the /databases/{id} endpoint returns 404
 * @param {string} dbId - The Notion database ID
 * @param {Object} UL - Logger utility
 * @returns {Object} { ok: boolean, props: Object, titleName: string|null }
 */
function fetchDatabaseSchemaFromPage_(dbId, UL) {
  try {
    // Resolve database_id to data_source_id for querying (standardized on data_sources API)
    const dsId = resolveDatabaseToDataSourceId_(dbId, UL);
    if (!dsId) {
      UL?.warn?.('Cannot query database - data_source_id not available', { dbId });
      return [];
    }
    const queryResource = `data_sources/${dsId}/query`;
    
    // Query the database to get at least one page
    const queryResult = notionFetch_(queryResource, 'POST', { page_size: 1 });
    
    if (!queryResult.results || queryResult.results.length === 0) {
      UL?.warn?.('Database appears empty, cannot extract schema from pages', { databaseId: dbId });
      return { ok: false, props: {}, titleName: null };
    }
    
    // Extract properties from the first page
    const firstPage = queryResult.results[0];
    const pageProperties = firstPage.properties || {};
    
    // Build property map: name -> { id, type, ... }
    const props = {};
    let titleName = null;
    
    for (const [propName, propData] of Object.entries(pageProperties)) {
      if (propData && propData.id) {
        // Reconstruct property structure similar to schema endpoint
        props[propName] = {
          id: propData.id,
          type: propData.type,
          name: propName
        };
        // Also preserve any other metadata that might be useful
        if (propData.type === 'title') {
          titleName = propName;
        }
      }
    }
    
    UL?.info?.('Successfully extracted schema from page', { 
      databaseId: dbId, 
      propertyCount: Object.keys(props).length 
    });
    
    return { ok: true, props, titleName };
  } catch (fallbackError) {
    const fallbackErr = String(fallbackError);
    const fallbackStack = fallbackError.stack || 'No stack trace available';
    UL?.error?.('Page-based schema fallback also failed', { 
      databaseId: dbId, 
      error: fallbackErr, 
      stack: fallbackStack 
    });
    return { ok: false, props: {}, titleName: null };
  }
}

function buildPropertyConfigFromType_(type, sampleValues = []) {
  const t = String(type || '').trim().toLowerCase();
  switch (t) {
    case 'title':       return { title: {} };
    case 'rich_text':
    case 'text':        return { rich_text: {} };
    case 'number':      return { number: { format: 'number' } };
    case 'checkbox':    return { checkbox: {} };
    case 'date':        return { date: {} };
    case 'url':         return { url: {} };
    case 'email':       return { email: {} };
    case 'phone_number':return { phone_number: {} };
    case 'status':      return { status: {} };
    case 'select': {
      const opts = Array.from(new Set(sampleValues.filter(Boolean).map(v => String(v).trim())))
        .slice(0, 80)
        .map(name => ({ name }));
      return { select: { options: opts } };
    }
    case 'multi_select': {
      const flat = [];
      (sampleValues || []).forEach(s => String(s || '').split(',').forEach(x => flat.push(x.trim())));
      const opts = Array.from(new Set(flat.filter(Boolean))).slice(0, 80).map(name => ({ name }));
      return { multi_select: { options: opts } };
    }
    default:
      return { rich_text: {} };
  }
}
function isSafeToDeleteProp_(type) {
  const forbidden = new Set(['title', 'formula', 'rollup', 'relation', 'people', 'files', 'created_time', 'created_by', 'last_edited_time', 'last_edited_by', 'unique_id']);
  return !forbidden.has(type);
}

/* ============================== VALUE MAPS ============================== */
function extractPropertyValue_(propertyValue, propertyType) {
  if (!propertyValue) return '';
  try {
    switch (propertyType) {
      case 'title':
        return (propertyValue.title || []).map(t => t.plain_text || '').join('');
      case 'rich_text':
        return (propertyValue.rich_text || []).map(t => t.plain_text || '').join('');
      case 'number':
        return propertyValue.number != null ? String(propertyValue.number) : '';
      case 'select':
        return propertyValue.select?.name || '';
      case 'multi_select':
        return (propertyValue.multi_select || []).map(s => s.name).join(', ');
      case 'date': {
        if (!propertyValue.date) return '';
        const start = propertyValue.date.start || '';
        const end = propertyValue.date.end ? ` → ${propertyValue.date.end}` : '';
        return start + end;
      }
      case 'people':
        return (propertyValue.people || []).map(p => p.name || p.id).join(', ');
      case 'files':
        return (propertyValue.files || []).map(f => f.name || '').join(', ');
      case 'checkbox':
        return propertyValue.checkbox ? 'true' : 'false';
      case 'url':
        return propertyValue.url || '';
      case 'email':
        return propertyValue.email || '';
      case 'phone_number':
        return propertyValue.phone_number || '';
      case 'formula': {
        if (propertyValue.formula?.type === 'string') return propertyValue.formula.string || '';
        if (propertyValue.formula?.type === 'number') return String(propertyValue.formula.number || '');
        if (propertyValue.formula?.type === 'boolean') return propertyValue.formula.boolean ? 'true' : 'false';
        if (propertyValue.formula?.type === 'date') return propertyValue.formula.date?.start || '';
        return '';
      }
      case 'relation':
        return (propertyValue.relation || []).map(r => r.id).join(', ');
      case 'rollup': {
        if (propertyValue.rollup?.type === 'number') return String(propertyValue.rollup.number || '');
        if (propertyValue.rollup?.type === 'array') return (propertyValue.rollup.array || []).length.toString();
        return '';
      }
      case 'created_time':
        return propertyValue.created_time || '';
      case 'created_by':
        return propertyValue.created_by?.name || propertyValue.created_by?.id || '';
      case 'last_edited_time':
        return propertyValue.last_edited_time || '';
      case 'last_edited_by':
        return propertyValue.last_edited_by?.name || propertyValue.last_edited_by?.id || '';
      case 'status':
        return propertyValue.status?.name || '';
      case 'unique_id':
        return propertyValue.unique_id?.prefix ? `${propertyValue.unique_id.prefix}-${propertyValue.unique_id.number}` : String(propertyValue.unique_id?.number || '');
      default:
        return JSON.stringify(propertyValue);
    }
  } catch (_) { return ''; }
}
function csvCellToPropertyValue_(type, raw) {
  const v = (raw ?? '').toString().trim();
  if (v === '') {
    switch (type) {
      case 'number': return { number: null };
      case 'checkbox': return { checkbox: false };
      case 'date': return { date: null };
      case 'select': return { select: null };
      case 'multi_select': return { multi_select: [] };
      case 'url': return { url: null };
      case 'email': return { email: null };
      case 'phone_number': return { phone_number: null };
      case 'title': return { title: [] };
      case 'rich_text': return { rich_text: [] };
      case 'status': return { status: null };
      default: return null;
    }
  }
  switch (String(type || '').toLowerCase()) {
    case 'title':       return { title: richTextChunks_(v) };
    case 'rich_text':
    case 'text':        return { rich_text: richTextChunks_(v) };
    case 'number':      { const n = Number(v); return { number: isNaN(n) ? null : n }; }
    case 'checkbox':    return { checkbox: /^true|1|yes$/i.test(v) };
    case 'date': {
      const m = v.split('→').map(s => s.trim());
      if (m.length === 2) return { date: { start: m[0] || null, end: m[1] || null } };
      return { date: { start: v } };
    }
    case 'select':      return { select: { name: v } };
    case 'multi_select':return { multi_select: v.split(',').map(s => ({ name: s.trim() })).filter(x => x.name) };
    case 'url':         return { url: v };
    case 'email':       return { email: v };
    case 'phone_number':return { phone_number: v };
    case 'status':      return { status: { name: v } };
    case 'relation':
    case 'people':
    case 'files':
    case 'formula':
    case 'rollup':
    case 'unique_id':
      return null;
    default:
      return { rich_text: richTextChunks_(v) };
  }
}

/* ============================== DATA INTEGRITY VALIDATION ============================== */
function validateDataIntegrity_(folder, ds, csvResult, UL) {
  try {
    const title = dsTitle_(ds);
    const csvName = `${sanitizeName(title)}_${ds.id}.csv`;
    const it = folder.getFilesByName(csvName);
    
    if (!it.hasNext()) {
      UL.warn('Cannot validate data integrity - CSV file not found', { database: title });
      return { valid: false, reason: 'CSV_NOT_FOUND' };
    }

    const file = it.next();
    const rows = Utilities.parseCsv(file.getBlob().getDataAsString());
    if (!rows || rows.length < 3) {
      UL.warn('Cannot validate data integrity - CSV too short', { database: title });
      return { valid: false, reason: 'CSV_TOO_SHORT' };
    }

    const header = rows[0];
    const idxPageId = header.indexOf('__page_id');
    if (idxPageId < 0) {
      UL.warn('Cannot validate data integrity - __page_id column missing', { database: title });
      return { valid: false, reason: 'MISSING_PAGE_ID_COLUMN' };
    }

    // Sample validation: Check first 10 rows exist in Notion
    const sampleSize = Math.min(10, rows.length - 2);
    let validated = 0;
    let notFound = 0;
    let errors = 0;

    for (let i = 2; i < Math.min(2 + sampleSize, rows.length); i++) {
      const pageId = rows[i][idxPageId];
      if (!pageId) continue;

      try {
        const page = notionFetch_(`pages/${pageId}`, 'GET');
        if (page && page.id === pageId) {
          validated++;
        } else {
          notFound++;
        }
      } catch (e) {
        errors++;
        UL.debug('Page validation error', { pageId, error: String(e) });
      }
    }

    const validationResult = {
      valid: errors === 0 && notFound === 0,
      sampleSize,
      validated,
      notFound,
      errors,
      totalRows: rows.length - 2
    };

    if (validationResult.valid) {
      UL.info('✅ Data integrity validation passed', { database: title, ...validationResult });
    } else {
      UL.warn('⚠️ Data integrity validation found issues', { database: title, ...validationResult });
    }

    return validationResult;
  } catch (e) {
    UL.error('Data integrity validation failed', { 
      database: dsTitle_(ds),
      error: String(e),
      stack: e.stack || 'No stack trace'
    });
    return { valid: false, reason: 'VALIDATION_ERROR', error: String(e) };
  }
}

/* ============================== WORKSPACE DB LOGGING (OPTIONAL) ============================== */
function getWorkspaceDbNotionDatabaseId_(UL) {
  const dbId = PROPS.getProperty('WORKSPACE_DATABASES_NOTION_DB_ID');
  if (!dbId) { UL?.debug?.('Workspace DB logging not configured'); return null; }
  try {
    notionFetch_(`databases/${dbId}`, 'GET');
    UL?.debug?.('Workspace DB accessible', { dbId });
    return dbId;
  } catch (e) {
    const errorMsg = String(e);
    const stack = e.stack || 'No stack trace available';
    UL?.warn?.('Workspace DB configured but inaccessible', { dbId, error: errorMsg, stack });
    return null;
  }
}
function _filterDbPropsToExisting_(dbId, props) {
  try {
    // Try data_sources first, then fall back to databases
    let db = null;
    try {
      const dsId = resolveDatabaseToDataSourceId_(dbId, null);
      if (dsId) {
        db = notionFetch_(`data_sources/${dsId}`, 'GET');
      }
    } catch (e) {
      // Fall through to databases endpoint
    }

    if (!db) {
      db = notionFetch_(`databases/${dbId}`, 'GET');
    }

    const schemaProps = db.properties || {};
    const out = {};

    // Map of proposed property format to expected Notion property types
    const typeMapping = {
      'title': ['title'],
      'rich_text': ['rich_text'],
      'number': ['number'],
      'select': ['select', 'status'],
      'multi_select': ['multi_select'],
      'date': ['date'],
      'checkbox': ['checkbox'],
      'url': ['url'],
      'email': ['email'],
      'phone_number': ['phone_number'],
      'relation': ['relation'],
      'people': ['people'],
      'files': ['files']
    };

    for (const [propName, propValue] of Object.entries(props || {})) {
      // Check if property exists in schema
      if (!schemaProps[propName]) continue;

      const schemaType = schemaProps[propName].type;

      // Determine the type being sent based on the property value structure
      let sendingType = null;
      if (propValue && typeof propValue === 'object') {
        // Get the first key of the property value object (e.g., 'rich_text', 'select', etc.)
        const keys = Object.keys(propValue);
        if (keys.length > 0) {
          sendingType = keys[0];
        }
      }

      // Check if the type matches
      if (sendingType) {
        const allowedTypes = typeMapping[sendingType] || [sendingType];
        if (!allowedTypes.includes(schemaType)) {
          // Type mismatch - skip this property to avoid API errors
          console.warn(`[WARN] Skipping property "${propName}": sending ${sendingType} but schema expects ${schemaType}`);
          continue;
        }
      }

      out[propName] = propValue;
    }

    return out;
  } catch (_) { return {}; }
}
function findWorkspaceDbPage_(dbId, dataSourceId, UL) {
  try {
    // Ensure "Data Source ID" property exists before querying
    try {
      ensurePropertyExists_(dbId, 'Data Source ID', 'rich_text', UL);
    } catch (e) {
      UL?.warn?.('Could not ensure Data Source ID property exists - query may fail', {
        dbId,
        error: String(e)
      });
    }
    
    // Resolve database_id to data_source_id for querying (standardized on data_sources API)
    const dsId = resolveDatabaseToDataSourceId_(dbId, UL);
    if (!dsId) {
      UL?.warn?.('Cannot query database - data_source_id not available', { dbId });
      return [];
    }
    const queryResource = `data_sources/${dsId}/query`;
    
    // Query for existing page by Data Source ID (deduplication key)
    const body = { 
      filter: { 
        property: 'Data Source ID', 
        rich_text: { equals: dataSourceId } 
      }, 
      page_size: 1 
    };
    const res = notionFetch_(queryResource, 'POST', body);
    
    if (res.results && res.results.length > 0) {
      const existingPageId = res.results[0].id;
      UL?.debug?.('Found existing Workspace Registry page (deduplication)', {
        dataSourceId: dataSourceId,
        existingPageId: existingPageId,
        note: 'Will update existing page instead of creating duplicate'
      });
      return existingPageId;
    }
    
    UL?.debug?.('No existing Workspace Registry page found', {
      dataSourceId: dataSourceId,
      note: 'Will create new page'
    });
    return null;
  } catch (e) {
    const errorMsg = String(e);
    const stack = e.stack || 'No stack trace available';
    UL?.warn?.('Could not search Workspace DB for existing page', { 
      dataSourceId, 
      error: errorMsg, 
      stack,
      note: 'Will attempt to create new page (may result in duplicate if page exists)'
    });
    return null;
  }
}
function logToNotionWorkspaceDb_(dataSource, csvFileId, driveFolder, rowCount, status, UL) {
  try {
    const dbId = getWorkspaceDbNotionDatabaseId_(UL);
    if (!dbId) return;

    // Validate and create required properties before logging
    const wsDbDsId = resolveDatabaseToDataSourceId_(dbId, UL);
    const propsValid = validateRequiredProperties_(dbId, wsDbDsId, UL, true);
    if (!propsValid) {
      UL.warn('Property validation failed for Workspace Registry - proceeding anyway', {
        dbId
      });
    }

    const title = dsTitle_(dataSource);
    const props = dataSource.properties || {};
    const propNames = Object.keys(props);
    const propsText = propNames.map(name => `${name} (${props[name]?.type || '?'})`).join(', ');

    // Get database schema to check property names
    let dbSchema = null;
    try {
      const wsDbDsId = resolveDatabaseToDataSourceId_(dbId, UL);
      const endpoint = wsDbDsId ? `data_sources/${wsDbDsId}` : `databases/${dbId}`;
      dbSchema = notionFetch_(endpoint, 'GET');
    } catch (e) {
      UL?.warn?.('Could not fetch Workspace Registry schema for property name resolution', { error: String(e) });
    }
    
    // Determine correct title property name (try "Database Name" first, fallback to "Name")
    const titlePropNames = ['Database Name', 'Name'];
    let titlePropName = 'Database Name'; // Default
    if (dbSchema && dbSchema.properties) {
      for (const propName of titlePropNames) {
        if (dbSchema.properties[propName]) {
          titlePropName = propName;
          break;
        }
      }
    }
    
    // Ensure title property exists
    if (dbSchema && !dbSchema.properties[titlePropName]) {
      // Try to create it if missing
      try {
        ensurePropertyExists_(dbId, titlePropName, 'title', UL);
        // Refresh schema
        const wsDbDsId = resolveDatabaseToDataSourceId_(dbId, UL);
        const endpoint = wsDbDsId ? `data_sources/${wsDbDsId}` : `databases/${dbId}`;
        dbSchema = notionFetch_(endpoint, 'GET');
      } catch (e) {
        UL?.warn?.('Could not ensure title property exists', { property: titlePropName, error: String(e) });
      }
    }

    // Resolve property names from schema (handle variations like "URL" vs "Database URL")
    let urlPropName = 'URL'; // Default
    if (dbSchema && dbSchema.properties) {
      // Try "Database URL" first (as per validate_schemas.gs), then "URL"
      if (dbSchema.properties['Database URL']) {
        urlPropName = 'Database URL';
      } else if (dbSchema.properties['URL']) {
        urlPropName = 'URL';
      }
    }
    
    const proposed = {
      [titlePropName]: { title: [{ type: 'text', text: { content: title } }] }, // Use resolved property name
      'Data Source ID': { rich_text: richTextChunks_(dataSource.id) },
      [urlPropName]: { url: dataSource.url || null }, // Use resolved property name
      'Status': { select: { name: status } },
      'Row Count': { number: rowCount },
      'Property Count': { number: propNames.length },
      'Properties': { rich_text: richTextChunks_(trunc(propsText, 2000)) },
      'Last Sync': { date: { start: nowIso() } },
      'Archived': { checkbox: !!dataSource.archived }
    };
    
    // Conditional properties (only set if value exists)
    if (csvFileId) proposed['CSV File ID'] = { rich_text: richTextChunks_(csvFileId) };
    if (driveFolder) proposed['Drive Folder'] = { url: driveFolder.getUrl() };
    
    // Optional properties that may exist in schema (set if they exist)
    // "Rotation Last Processed" - optional date property for tracking rotation processing
    if (dbSchema && dbSchema.properties && dbSchema.properties['Rotation Last Processed']) {
      // Only set if we have rotation processing logic (currently not implemented, but property may exist)
      // proposed['Rotation Last Processed'] = { date: { start: nowIso() } };
    }

    const safeProps = _filterDbPropsToExisting_(dbId, proposed);
    
    // CRITICAL: Ensure required properties are always included (even if filtered out, re-add them)
    // Title property is required and must be set
    if (!safeProps[titlePropName] && title) {
      safeProps[titlePropName] = { title: [{ type: 'text', text: { content: title } }] };
      UL?.debug?.('Re-added title property to safeProps', {
        propertyName: titlePropName,
        title: title,
        note: 'Title property is required and must be set'
      });
    }
    
    // Data Source ID is required and must be set
    if (!safeProps['Data Source ID'] && dataSource.id) {
      safeProps['Data Source ID'] = { rich_text: richTextChunks_(dataSource.id) };
      UL?.debug?.('Re-added Data Source ID property to safeProps', {
        dataSourceId: dataSource.id,
        note: 'Data Source ID property is required and must be set'
      });
    }
    
    // Status is required and must be set
    if (!safeProps['Status'] && status) {
      safeProps['Status'] = { select: { name: status } };
      UL?.debug?.('Re-added Status property to safeProps', {
        status: status,
        note: 'Status property is required and must be set'
      });
    }
    const existingPageId = findWorkspaceDbPage_(dbId, dataSource.id, UL);

    if (existingPageId) {
      notionFetch_(`pages/${existingPageId}`, 'PATCH', { properties: safeProps });
      const pageUrl = getNotionPageUrl_(existingPageId);
      UL?.info?.('Updated Workspace DB row', { 
        database: title, 
        pageId: existingPageId,
        pageUrl: pageUrl
      });
    } else {
      // API 2025-09-03: Use data_source_id parent type (resolve database_id to data_source_id)
      let parent;
      const wsDbDsId = resolveDatabaseToDataSourceId_(dbId, UL);
      if (wsDbDsId) {
        parent = { type: 'data_source_id', data_source_id: wsDbDsId };
      } else {
        UL?.warn?.('Cannot resolve Workspace DB data_source_id, using database_id fallback', { dbId });
        parent = { type: 'database_id', database_id: dbId };
      }
      
      const newPage = notionFetch_('pages', 'POST', { parent: parent, properties: safeProps });
      const pageUrl = getNotionPageUrl_(newPage.id);
      UL?.info?.('Created Workspace DB row', { 
        database: title, 
        pageId: newPage.id,
        pageUrl: pageUrl
      });
    }
  } catch (e) {
    const errorMsg = String(e);
    const stack = e.stack || 'No stack trace available';
    UL?.error?.('Failed to log to Workspace DB', { dataSourceId: dataSource.id, error: errorMsg, stack });
  }
}

/* ============================== NOTION URL HELPERS ============================== */
/**
 * Generates a Notion page URL from a page ID
 * @param {string} pageId - Notion page ID (with or without dashes)
 * @returns {string} Notion page URL
 */
function getNotionPageUrl_(pageId) {
  if (!pageId) return null;
  // Remove dashes from UUID for Notion URL format
  const cleanId = pageId.replace(/-/g, '');
  return `https://www.notion.so/${cleanId}`;
}

/**
 * Generates a Notion database/data source URL from an ID
 * @param {string} dbId - Database ID or data source ID
 * @returns {string} Notion database URL
 */
function getNotionDatabaseUrl_(dbId) {
  if (!dbId) return null;
  // Remove dashes from UUID for Notion URL format
  const cleanId = dbId.replace(/-/g, '');
  return `https://www.notion.so/${cleanId}`;
}

/* ============================== DRIVE HELPERS ============================== */
function resolveDriveParent_() {
  const url = PROPS.getProperty('WORKSPACE_DATABASES_URL');
  const idProp = PROPS.getProperty('WORKSPACE_DATABASES_FOLDER_ID');

  let id = null;
  if (url) { const m = String(url).match(/\/folders\/([a-zA-Z0-9_-]+)/); if (m) id = m[1]; }
  if (!id && idProp) id = idProp;

  if (id) { try { DriveApp.getFolderById(id); } catch { id = null; } }
  if (!id) {
    const it = DriveApp.getFoldersByName(CONFIG.DRIVE_PARENT_FALLBACK_NAME);
    id = it.hasNext() ? it.next().getId() : DriveApp.createFolder(CONFIG.DRIVE_PARENT_FALLBACK_NAME).getId();
  }

  let web = `https://drive.google.com/drive/folders/${id}`;
  try {
    const folder = DriveApp.getFolderById(id);
    web = folder.getUrl();
  } catch (_) {}

  PROPS.setProperty('WORKSPACE_DATABASES_FOLDER_ID', id);
  PROPS.setProperty('WORKSPACE_DATABASES_URL', web);
  return { id, url: web };
}
/**
 * Ensures a database folder exists, with robust duplicate detection, cleanup, and race condition prevention.
 * Uses ScriptLock to prevent concurrent executions from creating duplicate folders.
 * Consolidates duplicate folders (those with (1), (2) suffixes) by moving contents to primary folder.
 * @param {string} parentId - Parent folder ID
 * @param {Object} ds - Data source object with id and title
 * @returns {Folder} The canonical database folder
 */
function ensureDbFolder_(parentId, ds) {
  const title = dsTitle_(ds);
  const expectedName = `${sanitizeName(title)}_${ds.id}`;
  const parent = DriveApp.getFolderById(parentId);
  const dbIdPattern = `_${ds.id}`;

  // Track parent folder in Notion Folders database
  // Note: UL is not available in this context, passing null (function handles gracefully)
  try {
    getOrCreateFolderInNotion_(parent, null);
  } catch (e) {
    // Non-critical - continue even if folder tracking fails
    console.warn(`[WARN] Could not track parent folder in Notion: ${e}`);
  }

  /**
   * Helper function to find all matching folders for this database
   */
  function findMatchingFolders_() {
    const allFolders = parent.getFolders();
    const matching = [];
    while (allFolders.hasNext()) {
      const folder = allFolders.next();
      const folderName = folder.getName();
      // Match folders that contain the database ID pattern (catches duplicates with (1), (2) etc.)
      if (folderName.includes(dbIdPattern)) {
        matching.push({
          folder: folder,
          name: folderName,
          isExactMatch: folderName === expectedName,
          isDuplicate: /\s*\(\d+\)\s*$/.test(folderName),
          lastUpdated: folder.getLastUpdated()
        });
      }
    }
    return matching;
  }

  /**
   * Helper to consolidate duplicate folders into the primary folder
   */
  function consolidateDuplicates_(primaryFolder, duplicateFolders) {
    let movedFiles = 0;
    let movedFolders = 0;

    for (const dupInfo of duplicateFolders) {
      const dupFolder = dupInfo.folder;
      try {
        // Move all files from duplicate to primary
        const files = dupFolder.getFiles();
        while (files.hasNext()) {
          const file = files.next();
          file.moveTo(primaryFolder);
          movedFiles++;
        }

        // Move all subfolders from duplicate to primary
        const subfolders = dupFolder.getFolders();
        while (subfolders.hasNext()) {
          const subfolder = subfolders.next();
          subfolder.moveTo(primaryFolder);
          movedFolders++;
        }

        // Trash the now-empty duplicate folder
        dupFolder.setTrashed(true);
        console.log(`[INFO] Consolidated and trashed duplicate folder: ${dupInfo.name}`);
      } catch (consolidateErr) {
        console.warn(`[WARN] Failed to consolidate duplicate folder ${dupInfo.name}: ${consolidateErr}`);
      }
    }

    if (movedFiles > 0 || movedFolders > 0) {
      console.log(`[INFO] Consolidation complete: moved ${movedFiles} files and ${movedFolders} folders`);
    }
  }

  // FIX 2026-01-18: Acquire lock BEFORE any folder checks to eliminate race condition window
  // Previous pattern: check → lock → re-check → create (race in first check)
  // Fixed pattern: lock → check → create if needed (no race window)
  const lock = LockService.getScriptLock();
  const lockWaitMs = CONFIG.SYNC.LOCK_WAIT_MS || 10000;
  let matchingFolders = [];

  // Try to acquire lock with exponential backoff retry
  let lockAcquired = lock.tryLock(lockWaitMs);
  if (!lockAcquired) {
    for (const waitMs of [1000, 2000, 4000]) {
      Utilities.sleep(waitMs);
      lockAcquired = lock.tryLock(lockWaitMs);
      if (lockAcquired) break;
    }
  }

  if (lockAcquired) {
    try {
      // Phase 1: Check for existing folders INSIDE lock (no race condition)
      matchingFolders = findMatchingFolders_();

      // Phase 2: If no folders found, create one (still inside lock)
      if (matchingFolders.length === 0) {
        const newFolder = parent.createFolder(expectedName);
        console.log(`[INFO] Created new database folder: ${expectedName}`);

        // Track newly created folder in Notion Folders database
        try {
          getOrCreateFolderInNotion_(newFolder, null);
        } catch (e) {
          console.warn(`[WARN] Could not track new folder in Notion: ${e}`);
        }

        return newFolder;
      }
      // Else: folder exists, fall through to consolidation logic
    } finally {
      lock.releaseLock();
    }
  } else {
    // Could not acquire lock after retries - check for folder without creating
    console.warn(`[WARN] Lock timeout for database ${ds.id}; checking for existing folder`);
    Utilities.sleep(2000);
    matchingFolders = findMatchingFolders_();
    if (matchingFolders.length === 0) {
      const msg = `Lock timeout creating folder for ${ds.id}; deferring creation to avoid duplicates`;
      console.warn(`[WARN] ${msg}`);
      throw new Error(msg);
    }
  }

  // Phase 3: If exactly one folder found and it's the exact match, return it
  if (matchingFolders.length === 1 && matchingFolders[0].isExactMatch) {
    return matchingFolders[0].folder;
  }

  // Phase 4: Multiple folders or non-exact matches found - need to consolidate
  // Prefer: 1) Exact name match, 2) Non-duplicate name, 3) Most recently updated
  matchingFolders.sort((a, b) => {
    // Exact matches first
    if (a.isExactMatch && !b.isExactMatch) return -1;
    if (!a.isExactMatch && b.isExactMatch) return 1;
    // Non-duplicates over duplicates
    if (!a.isDuplicate && b.isDuplicate) return -1;
    if (a.isDuplicate && !b.isDuplicate) return 1;
    // Most recently updated
    return b.lastUpdated.getTime() - a.lastUpdated.getTime();
  });

  const primaryFolder = matchingFolders[0].folder;

  // Phase 5: Consolidate duplicate folders into primary (move contents and trash duplicates)
  if (matchingFolders.length > 1) {
    console.warn(`[WARN] Found ${matchingFolders.length} folders for database ${ds.id}. Using: ${matchingFolders[0].name}`);
    const duplicates = matchingFolders.slice(1);
    console.log(`[INFO] Consolidating ${duplicates.length} duplicate folder(s): ${duplicates.map(f => f.name).join(', ')}`);
    consolidateDuplicates_(primaryFolder, duplicates);
  }

  // Phase 6: If primary folder doesn't have the exact expected name, try to rename it
  if (!matchingFolders[0].isExactMatch) {
    try {
      // Check if a folder with the exact name already exists
      const exactNameCheck = parent.getFoldersByName(expectedName);
      if (!exactNameCheck.hasNext()) {
        primaryFolder.setName(expectedName);
        console.log(`[INFO] Renamed folder to canonical name: ${expectedName}`);
      }
    } catch (renameErr) {
      console.warn(`[WARN] Could not rename folder to ${expectedName}: ${renameErr}`);
    }
  }

  return primaryFolder;
}

/* ============================== ARCHIVAL AND VERSIONING HELPERS (Notion-style) ============================== */
/**
 * Ensures an archive folder exists within the database folder for versioning
 * Similar to Notion's version history structure
 */
function ensureArchiveFolder_(dbFolder, UL) {
  try {
    const archiveName = '.archive';
    const it = dbFolder.getFoldersByName(archiveName);
    if (it.hasNext()) {
      return it.next();
    }
    const archiveFolder = dbFolder.createFolder(archiveName);
    UL?.debug?.('Created archive folder', { archiveFolderId: archiveFolder.getId() });
    return archiveFolder;
  } catch (e) {
    UL?.error?.('Failed to create archive folder', { error: String(e), stack: e.stack });
    return null;
  }
}

/**
 * Creates a versioned backup of a file before updating it
 * Mirrors Notion's version history system - creates timestamped snapshots
 */
function createVersionedBackup_(file, archiveFolder, UL) {
  if (!file || !archiveFolder) return null;
  
  try {
    const timestamp = nowIso().replace(/[:.]/g, '-').replace('T', '_').split('.')[0];
    const baseName = file.getName();
    const nameWithoutExt = baseName.replace(/\.csv$/, '');
    const versionedName = `${nameWithoutExt}_v${timestamp}.csv`;
    
    // Copy file to archive with versioned name
    const backupBlob = file.getBlob();
    const backupFile = archiveFolder.createFile(backupBlob.setName(versionedName));
    
    UL?.info?.('Created versioned backup', {
      originalFile: baseName,
      backupFile: versionedName,
      backupFileId: backupFile.getId(),
      timestamp: timestamp
    });
    
    return backupFile;
  } catch (e) {
    UL?.error?.('Failed to create versioned backup', {
      error: String(e),
      stack: e.stack,
      fileName: file?.getName()
    });
    return null;
  }
}

/**
 * Archives old versions, keeping only the most recent N versions (similar to Notion's version retention)
 * This prevents unlimited growth while maintaining version history
 */
function archiveOldVersions_(archiveFolder, baseFileName, maxVersions = 50, UL) {
  if (!archiveFolder) return;
  
  try {
    const nameWithoutExt = baseFileName.replace(/\.csv$/, '');
    const versionPattern = new RegExp(`^${nameWithoutExt.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}_v\\d{4}-\\d{2}-\\d{2}_\\d{2}-\\d{2}-\\d{2}\\.csv$`);
    
    const files = archiveFolder.getFiles();
    const versionFiles = [];
    
    while (files.hasNext()) {
      const file = files.next();
      if (versionPattern.test(file.getName())) {
        versionFiles.push({
          file: file,
          name: file.getName(),
          modified: file.getLastUpdated()
        });
      }
    }
    
    // Sort by modification time (newest first)
    versionFiles.sort((a, b) => b.modified.getTime() - a.modified.getTime());
    
    // Archive (move to deeper archive) or delete versions beyond maxVersions
    if (versionFiles.length > maxVersions) {
      const toArchive = versionFiles.slice(maxVersions);
      UL?.info?.('Archiving old versions', {
        totalVersions: versionFiles.length,
        keeping: maxVersions,
        archiving: toArchive.length
      });
      
      for (const version of toArchive) {
        try {
          // Move to trash (archived) instead of permanent delete
          // This mirrors Notion's behavior where old versions are archived but recoverable
          version.file.setTrashed(true);
          UL?.debug?.('Archived old version', { fileName: version.name });
        } catch (e) {
          UL?.warn?.('Failed to archive old version', {
            fileName: version.name,
            error: String(e)
          });
        }
      }
    }
  } catch (e) {
    UL?.error?.('Failed to archive old versions', {
      error: String(e),
      stack: e.stack
    });
  }
}

/**
 * Gets or creates the main CSV file, updating it in place.
 * Searches for files with duplicate suffixes (1), (2) and consolidates to canonical name.
 * This ensures we always update the same document (Notion-style)
 */
function getOrCreateMainCsvFile_(folder, csvName, UL) {
  try {
    // Phase 1: Search for exact match first
    const exactIt = folder.getFilesByName(csvName);
    if (exactIt.hasNext()) {
      let mostRecentFile = exactIt.next();
      let mostRecentTime = mostRecentFile.getLastUpdated();

      // Check for additional files with same name
      while (exactIt.hasNext()) {
        const candidate = exactIt.next();
        const candidateTime = candidate.getLastUpdated();
        if (candidateTime > mostRecentTime) {
          UL?.warn?.('Multiple files with same name found - using most recent', {
            fileName: csvName,
            previousFileId: mostRecentFile.getId(),
            newFileId: candidate.getId()
          });
          mostRecentFile = candidate;
          mostRecentTime = candidateTime;
        }
      }

      UL?.debug?.('Found existing CSV file (reusing persistent item)', {
        fileName: csvName,
        fileId: mostRecentFile.getId()
      });
      return mostRecentFile;
    }

    // Phase 2: Search for files with duplicate suffixes like "name (1).csv", "name (2).csv"
    // This handles race condition artifacts from previous runs
    const baseName = csvName.replace(/\.csv$/, '');
    const allFiles = folder.getFiles();
    const matchingFiles = [];

    while (allFiles.hasNext()) {
      const file = allFiles.next();
      const fileName = file.getName();
      // Match files that start with base name and end with optional (n).csv
      if (fileName.startsWith(baseName) && fileName.endsWith('.csv')) {
        const isExactMatch = fileName === csvName;
        const isDuplicate = /\s*\(\d+\)\.csv$/.test(fileName);
        if (isExactMatch || isDuplicate) {
          matchingFiles.push({
            file: file,
            name: fileName,
            isExactMatch: isExactMatch,
            isDuplicate: isDuplicate,
            lastUpdated: file.getLastUpdated(),
            size: file.getSize()
          });
        }
      }
    }

    // Phase 3: If we found files with duplicate suffixes, use the best one
    if (matchingFiles.length > 0) {
      // Sort: exact matches first, then by size (larger = more data), then by date
      matchingFiles.sort((a, b) => {
        if (a.isExactMatch && !b.isExactMatch) return -1;
        if (!a.isExactMatch && b.isExactMatch) return 1;
        // Prefer larger files (more complete data)
        if (a.size !== b.size) return b.size - a.size;
        // Most recently updated
        return b.lastUpdated.getTime() - a.lastUpdated.getTime();
      });

      const primaryFile = matchingFiles[0].file;

      if (matchingFiles.length > 1) {
        UL?.warn?.('Found CSV files with duplicate suffixes - consolidating', {
          csvName: csvName,
          foundFiles: matchingFiles.map(f => f.name),
          usingFile: matchingFiles[0].name
        });
      }

      // Try to rename to canonical name if needed
      if (!matchingFiles[0].isExactMatch) {
        try {
          primaryFile.setName(csvName);
          UL?.info?.('Renamed CSV file to canonical name', {
            from: matchingFiles[0].name,
            to: csvName
          });
        } catch (renameErr) {
          UL?.warn?.('Could not rename CSV file to canonical name', {
            from: matchingFiles[0].name,
            to: csvName,
            error: String(renameErr)
          });
        }
      }

      return primaryFile;
    }

    // Phase 4: No files found - create new file
    const newFile = folder.createFile(Utilities.newBlob('', 'text/csv', csvName));
    UL?.info?.('Created new CSV file (will be reused in future runs)', {
      fileName: csvName,
      fileId: newFile.getId(),
      fileUrl: newFile.getUrl()
    });
    return newFile;
  } catch (e) {
    UL?.error?.('Failed to get or create main CSV file', {
      error: String(e),
      stack: e.stack,
      csvName: csvName
    });
    return null;
  }
}

/* ============================== CSV → NOTION: SCHEMA SYNC ============================== */
function syncSchemaFromCsvToNotion_(folder, ds, UL) {
  const result = { added: [], deleted: [], skipped: [], skippedDueToConfig: [] };
  if (!CONFIG.SYNC.CSV_AUTHORIZES_SCHEMA) return result;

  const title = dsTitle_(ds);
  const csvName = `${sanitizeName(title)}_${ds.id}.csv`;
  const it = folder.getFilesByName(csvName);
  if (!it.hasNext()) {
    UL.info('No existing CSV found - skipping schema sync', { database: title });
    return result;
  }

  // COMPREHENSIVE PROPERTY VALIDATION: Ensure database schema is accessible before sync
  if (!ds.properties || Object.keys(ds.properties).length === 0) {
    UL.warn('Database has no properties - attempting to refresh schema', {
      database: title,
      dataSourceId: ds.id
    });
    try {
      const fresh = getDataSource_(ds.id, UL);
      if (fresh && fresh.properties) {
        ds.properties = fresh.properties;
        UL.info('Refreshed database schema', {
          database: title,
          propertyCount: Object.keys(fresh.properties).length
        });
      } else {
        UL.warn('Could not refresh schema - database may be inaccessible', {
          database: title,
          dataSourceId: ds.id
        });
      }
    } catch (e) {
      UL.error('Failed to refresh database schema', {
        database: title,
        dataSourceId: ds.id,
        error: String(e)
      });
    }
  }
  
  const schemaInfo = fetchDatabaseSchema_(ds.id, UL);
  if (!schemaInfo.ok) {
    UL.warn('Cannot modify schema - database not shared with integration', { database: title });
    result.skipped.push('inaccessible');
    return result;
  }

  const file = it.next();
  const rows = Utilities.parseCsv(file.getBlob().getDataAsString());
  if (!rows || rows.length < 2) {
    UL.warn('CSV too short for schema inference', { database: title, csvName });
    return result;
  }

  const header = rows[0];
  const types = rows[1];
  const csvProps = {};
  for (let i = 0; i < header.length; i++) {
    const name = header[i];
    if (!name || INTERNAL_COLS.has(name)) continue;
    csvProps[name] = String(types[i] || 'rich_text');
  }

  const { props: dbProps, titleName } = schemaInfo;
  const dbMap = {};
  for (const [k, v] of Object.entries(dbProps)) dbMap[k] = v.type;

  const additions = result.added;
  for (const [name, type] of Object.entries(csvProps)) {
    if (dbMap[name]) continue;
    if (type === 'title' && titleName) {
      UL.warn('CSV requests second title column - skipping', { database: title, column: name, existingTitle: titleName });
      continue;
    }
    const colIdx = header.indexOf(name);
    const samples = [];
    for (let r = 2; r < Math.min(rows.length, 200); r++) samples.push(rows[r][colIdx]);
    additions.push({ name, type, config: buildPropertyConfigFromType_(type, samples) });
  }

  const deletionCandidates = [];
  for (const [name, type] of Object.entries(dbMap)) {
    if (name === titleName) continue;
    if (csvProps[name] != null) continue;
    if (isSafeToDeleteProp_(type)) deletionCandidates.push({ name, type });
  }

  if (!additions.length && !deletionCandidates.length) {
    UL.info('Schema already aligned - no changes needed', { database: title });
    return result;
  }

  const allowDeletions = CONFIG.SYNC.ALLOW_SCHEMA_DELETIONS === true;
  const effectiveDeletions = allowDeletions ? deletionCandidates : [];
  result.deleted = effectiveDeletions;
  
  if (!allowDeletions && deletionCandidates.length) {
    // Log what *would* be deleted, but don't actually do it (per requirements)
    UL.info(
      `Schema deletions are disabled (ALLOW_SCHEMA_DELETIONS=false). ` +
      `Would have deleted ${deletionCandidates.length} propert` +
      (deletionCandidates.length === 1 ? 'y' : 'ies') +
      ` from "${title}".`,
      { 
        database: title,
        dataSourceId: ds.id,
        wouldDelete: deletionCandidates.map(d => ({ name: d.name, type: d.type }))
      }
    );
    result.skippedDueToConfig = deletionCandidates;
  } else if (effectiveDeletions.length) {
    UL.warn('Deleting Notion properties to match CSV schema (config enabled)', {
      database: title,
      dataSourceId: ds.id,
      properties: effectiveDeletions.map(d => `${d.name}:${d.type}`)
    });
  }

  const patch = { properties: {} };
  additions.forEach(a => { patch.properties[a.name] = a.config; });
  effectiveDeletions.forEach(d => { patch.properties[d.name] = null; });

  if (Object.keys(patch.properties).length) {
    // Use data_sources endpoint (API 2025-09-03): /databases/{id} is deprecated
    // ds.id is a data_source_id from search results, so use data_sources endpoint
    notionFetch_(`data_sources/${ds.id}`, 'PATCH', patch);
  }

  if (additions.length) UL.info('Added properties to database', { 
    database: title, 
    count: additions.length, 
    properties: additions.map(a => `${a.name}:${a.type}`)
  });
  if (effectiveDeletions.length) UL.info('Deleted properties from database', { 
    database: title, 
    dataSourceId: ds.id,
    count: effectiveDeletions.length, 
    properties: effectiveDeletions.map(d => `${d.name}:${d.type}`)
  });

  return result;
}

/* ============================== NOTION → CSV EXPORT ============================== */
function writeDataSourceCsv_(folder, ds, UL) {
  try {
    const props = ds.properties || {};
    let propNames = Object.keys(props);
    let propTypes = propNames.map(name => props[name]?.type || '');

    const title = dsTitle_(ds);
    UL?.info?.('Exporting database to CSV', { database: title, properties: propNames.length });
    
    // COMPREHENSIVE PROPERTY VALIDATION: Ensure database has properties before export
    if (propNames.length === 0) {
      UL.warn('Database has no properties - attempting to refresh schema', {
        database: title,
        dataSourceId: ds.id
      });
      // Try to refresh schema
      try {
        const fresh = getDataSource_(ds.id, UL);
        if (fresh && fresh.properties) {
          Object.assign(props, fresh.properties);
          propNames = Object.keys(fresh.properties);
          propTypes = propNames.map(name => fresh.properties[name]?.type || '');
          if (propNames.length > 0) {
            UL.info('Refreshed schema and found properties', {
              database: title,
              propertyCount: propNames.length
            });
          } else {
            UL.warn('Database still has no properties after refresh', {
              database: title,
              dataSourceId: ds.id
            });
          }
        }
      } catch (e) {
        UL.warn('Could not refresh schema for empty database', {
          database: title,
          error: String(e)
        });
      }
    }

    const pages = queryDataSourcePages_(ds.id, UL);
    UL?.info?.('Pulled pages from database', { database: title, rowCount: pages.length });

    const csvLines = [];
    csvLines.push(['__page_id', '__last_synced_iso', ...propNames].map(escapeCsv).join(','));
    csvLines.push(['', '', ...propTypes].map(escapeCsv).join(','));

    for (const page of pages) {
      const row = [];
      row.push(page.id);
      row.push(nowIso());
      for (const propName of propNames) {
        const propType = props[propName]?.type;
        row.push(extractPropertyValue_(page.properties?.[propName], propType));
      }
      csvLines.push(row.map(escapeCsv).join(','));
    }

    const csv = csvLines.join('\n');
    const csvName = `${sanitizeName(title)}_${ds.id}.csv`;

    // ARCHIVAL AND VERSIONING: Get or create main CSV file (update in place, Notion-style)
    const mainFile = getOrCreateMainCsvFile_(folder, csvName, UL);
    if (!mainFile) {
      throw new Error('Failed to get or create main CSV file');
    }

    // ARCHIVAL AND VERSIONING: Create versioned backup before updating (Notion version history)
    const archiveFolder = ensureArchiveFolder_(folder, UL);
    if (archiveFolder) {
      // Only create backup if file has content (not first creation)
      const existingContent = mainFile.getBlob().getDataAsString();
      if (existingContent && existingContent.trim().length > 0) {
        createVersionedBackup_(mainFile, archiveFolder, UL);
        // Clean up old versions (keep last 50 versions, similar to Notion's retention)
        archiveOldVersions_(archiveFolder, csvName, 50, UL);
      }
    }

    // ARCHIVAL AND VERSIONING: Update the same file in place (don't create new items)
    // This ensures the CSV file is a persistent clone/backup that is updated over time
    // The file is reused across script runs and updated in place (Notion-style)
    mainFile.setContent(csv);
    
    // CRITICAL: Verify CSV file was written successfully
    try {
      const verifyContent = mainFile.getBlob().getDataAsString();
      if (verifyContent.length < csv.length) {
        UL?.error?.('CSV file write verification failed', {
          database: title,
          csvName: csvName,
          expectedSize: csv.length,
          actualSize: verifyContent.length,
          fileId: mainFile.getId(),
          fileUrl: mainFile.getUrl()
        });
        throw new Error(`CSV write verification failed: expected ${csv.length} bytes, got ${verifyContent.length}`);
      }
      
      UL?.debug?.('CSV file write verified successfully', {
        database: title,
        csvName: csvName,
        fileSize: verifyContent.length,
        fileId: mainFile.getId(),
        fileUrl: mainFile.getUrl()
      });
    } catch (verifyError) {
      UL?.error?.('CSV file write verification error', {
        database: title,
        csvName: csvName,
        error: String(verifyError),
        stack: verifyError.stack,
        fileId: mainFile.getId(),
        fileUrl: mainFile.getUrl()
      });
      // Continue - file may still be partially written
    }

    UL?.info?.('CSV export completed with versioning', { 
      database: title, 
      csvName, 
      fileId: mainFile.getId(),
      fileUrl: mainFile.getUrl(),
      rows: pages.length, 
      columns: propNames.length,
      versioned: !!archiveFolder,
      fileSize: csv.length
    });
    return { fileId: mainFile.getId(), rowCount: pages.length, csvName };
  } catch (e) {
    const errorMsg = String(e);
    const stack = e.stack || 'No stack trace available';
    UL?.error?.('Failed to export database to CSV', { dataSourceId: ds.id, error: errorMsg, stack });
    return { fileId: null, rowCount: 0, csvName: null };
  }
}

/* ============================== CSV → NOTION VALUE SYNC ============================== */
function extractFirstTitleFromPage_(page) {
  if (!page || !page.properties) return '';
  
  // Find title property (case-insensitive)
  for (const [k, v] of Object.entries(page.properties)) {
    if (v && v.type === 'title') {
      const titleText = (v.title || []).map(t => t.plain_text || '').join('');
      if (titleText) return titleText;
    }
  }
  
  // Fallback: try common title property names
  const titlePropNames = ['Name', 'Title', 'Task', 'name', 'title', 'task'];
  for (const propName of titlePropNames) {
    const prop = page.properties[propName];
    if (prop) {
      if (prop.type === 'title' && prop.title) {
        return (prop.title || []).map(t => t.plain_text || '').join('');
      } else if (prop.type === 'rich_text' && prop.rich_text) {
        return (prop.rich_text || []).map(t => t.plain_text || '').join('');
      }
    }
  }
  
  return '';
}
function syncCsvToNotion_(folder, ds, UL, options = {}) {
  const title = dsTitle_(ds);
  const csvName = `${sanitizeName(title)}_${ds.id}.csv`;

  const it = folder.getFilesByName(csvName);
  if (!it.hasNext()) { 
    UL.info('No CSV found - skipping value sync', { database: title }); 
    return { created: 0, updated: 0, skipped: 0 }; 
  }

  // COMPREHENSIVE PROPERTY VALIDATION: Ensure database schema is accessible
  if (!ds.properties || Object.keys(ds.properties).length === 0) {
    UL.warn('Database has no properties - attempting to refresh schema', {
      database: title,
      dataSourceId: ds.id
    });
    try {
      const fresh = getDataSource_(ds.id, UL);
      if (fresh && fresh.properties) {
        ds.properties = fresh.properties;
        UL.info('Refreshed database schema', {
          database: title,
          propertyCount: Object.keys(fresh.properties).length
        });
      }
    } catch (e) {
      UL.warn('Could not refresh schema', {
        database: title,
        error: String(e)
      });
    }
  }
  
  const schemaInfo = fetchDatabaseSchema_(ds.id, UL);
  if (!schemaInfo.ok) {
    UL.warn('Cannot update pages - database not shared with integration', { database: title });
    return { created: 0, updated: 0, skipped: 0 };
  }
  let { props: dbProps, titleName } = schemaInfo;
  
  // COMPREHENSIVE PROPERTY VALIDATION: Ensure title property exists
  if (!titleName) {
    UL.warn('Database missing title property - attempting to create', {
      database: title,
      dataSourceId: ds.id
    });
    const titlePropNames = ['Name', 'Title', 'Task'];
    let titleCreated = false;
    for (const propName of titlePropNames) {
      if (ensurePropertyExists_(ds.id, propName, 'title', UL)) {
        titleCreated = true;
        UL.info('Created title property for database', {
          database: title,
          propertyName: propName
        });
        break;
      }
    }
    
    if (titleCreated) {
      // Re-fetch schema to get updated titleName
      const freshSchema = fetchDatabaseSchema_(ds.id, UL);
      if (freshSchema.ok && freshSchema.titleName) {
        // Update local variables
        Object.assign(dbProps, freshSchema.props);
        const updatedTitleName = freshSchema.titleName;
        UL.debug('Refreshed schema after creating title property', {
          database: title,
          titleProperty: updatedTitleName
        });
      }
    }
  }

  const file = it.next();
  const rows = Utilities.parseCsv(file.getBlob().getDataAsString());
  if (!rows || rows.length < 2) { 
    UL.warn('CSV too short for value sync', { database: title, csvName }); 
    return { created:0, updated:0, skipped:0 }; 
  }

  const header = rows[0];
  const types  = rows[1];
  const idxPageId = header.indexOf('__page_id');
  const idxSynced = header.indexOf('__last_synced_iso');

  const csvSchema = {};
  const headerMap = {};
  for (let i = 0; i < header.length; i++) {
    const h = header[i];
    if (!h || INTERNAL_COLS.has(h)) continue;
    const t = String(types[i] || 'rich_text');

    if (CONFIG.SYNC.ALLOWED_SYNC_PROPS.length && !CONFIG.SYNC.ALLOWED_SYNC_PROPS.includes(h)) continue;

    if (t === 'title' && titleName && h !== titleName) {
      headerMap[h] = titleName;
      csvSchema[titleName] = t;
    } else {
      headerMap[h] = h;
      csvSchema[h] = t;
    }
  }

  let created = 0, updated = 0, skipped = 0;
  for (let r = 2; r < rows.length; r++) {
    const row = rows[r];
    if (!row || !row.length) continue;

    const pageId = idxPageId >= 0 ? row[idxPageId] : '';
    const lastSynced = idxSynced >= 0 ? row[idxSynced] : null;

    const propsPayload = {};
    for (const [csvNameCol, type] of Object.entries(csvSchema)) {
      const dbPropName = headerMap[csvNameCol] || csvNameCol;
      const i = header.indexOf(csvNameCol);
      if (i < 0) continue;

      const dbPropType = dbProps[dbPropName]?.type;
      if (!dbPropType) {
        // Property doesn't exist - try to create it
        UL.warn('Property missing in database schema - attempting to create', {
          database: title,
          property: dbPropName,
          expectedType: type
        });
        
        // Ensure property exists before using it
        // ds.id is already a data_source_id from search results, but ensurePropertyExists_ expects either
        // resolveDatabaseToDataSourceId_ now handles both data_source_id and database_id
        const dsId = resolveDatabaseToDataSourceId_(ds.id, UL);
        const targetId = dsId || ds.id;
        const propCreated = ensurePropertyExists_(targetId, dbPropName, type, UL);
        
        if (propCreated) {
          // Re-fetch schema to get the new property
          try {
            const endpoint = dsId ? `data_sources/${dsId}` : `databases/${ds.id}`;
            const freshDb = notionFetch_(endpoint, 'GET');
            ds.properties = freshDb.properties;
            dbProps = freshDb.properties;
            
            // Try again with the new property
            const dbPropTypeNew = dbProps[dbPropName]?.type;
            if (dbPropTypeNew) {
              const pv = csvCellToPropertyValue_(type, row[i]);
              if (pv) propsPayload[dbPropName] = pv;
            }
          } catch (e) {
            UL.error('Failed to refresh schema after property creation', {
              database: title,
              property: dbPropName,
              error: String(e)
            });
          }
        }
        continue;
      }

      const pv = csvCellToPropertyValue_(type, row[i]);
      if (pv) propsPayload[dbPropName] = pv;
    }

    if (Object.keys(propsPayload).length === 0) { skipped++; continue; }

    // COMPREHENSIVE PROPERTY VALIDATION: Ensure all properties in payload exist before update/create
    const missingProps = [];
    for (const propName of Object.keys(propsPayload)) {
      if (!dbProps[propName]) {
        missingProps.push(propName);
      }
    }
    
    if (missingProps.length > 0) {
      UL.warn('Some properties in payload do not exist in database schema - attempting to create', {
        database: title,
        missingProperties: missingProps,
        pageId: pageId || 'NEW'
      });
      
      // Try to create missing properties
      // ds.id is already a data_source_id from search results
      // resolveDatabaseToDataSourceId_ now handles both data_source_id and database_id
      const dsId = resolveDatabaseToDataSourceId_(ds.id, UL);
      const targetId = dsId || ds.id;
      let anyCreated = false;
      
      for (const propName of missingProps) {
        // Try to infer type from CSV schema
        const csvType = csvSchema[propName] || 'rich_text';
        if (ensurePropertyExists_(targetId, propName, csvType, UL)) {
          anyCreated = true;
          UL.info('Created missing property', {
            database: title,
            property: propName,
            type: csvType
          });
        }
      }
      
      // Refresh schema after property creation
      if (anyCreated) {
        try {
          const endpoint = dsId ? `data_sources/${dsId}` : `databases/${ds.id}`;
          const freshDb = notionFetch_(endpoint, 'GET');
          ds.properties = freshDb.properties;
          dbProps = freshDb.properties;
          UL.debug('Refreshed schema after creating missing properties', {
            database: title,
            propertiesCreated: missingProps.length
          });
        } catch (e) {
          UL.warn('Could not refresh schema after creating properties', {
            database: title,
            error: String(e)
          });
        }
      }
    }

    // MGM: Validate relations before creating/updating
    validateRelations_(propsPayload, dbProps, UL);
    
    // MGM: Set lifecycle property on new pages
    const isNewPage = !pageId;
    setLifecycleProperty_(propsPayload, dbProps, UL, isNewPage, ds.id);

    if (Object.keys(propsPayload).length === 0) { skipped++; continue; }
    
    // Final validation: ensure all properties exist before update/create
    const finalMissingProps = [];
    for (const propName of Object.keys(propsPayload)) {
      if (!dbProps[propName]) {
        finalMissingProps.push(propName);
      }
    }
    
    if (finalMissingProps.length > 0) {
      UL.warn('Some properties still missing after creation attempt - removing from payload', {
        database: title,
        pageId: pageId || 'NEW',
        missingProperties: finalMissingProps
      });
      // Remove missing properties from payload
      for (const propName of finalMissingProps) {
        delete propsPayload[propName];
      }
    }
    
    if (Object.keys(propsPayload).length === 0) {
      skipped++;
      UL.warn('No valid properties to sync - skipping', {
        database: title,
        pageId: pageId || 'NEW'
      });
      continue;
    }

    try {
      if (pageId) {
        if ((options.conflict === 'guard') || (CONFIG.SYNC.CONFLICT_MODE === 'guard')) {
          let p;
          try {
            p = notionFetch_(`pages/${pageId}`, 'GET');
          } catch (e) {
            UL.error('Failed to fetch page for conflict check', {
              database: title,
              pageId: pageId,
              error: String(e)
            });
            skipped++;
            continue;
          }
          
          const edited = p.last_edited_time || '';
          const pageTitle = extractFirstTitleFromPage_(p) || pageId;
          
          // COMPREHENSIVE PROPERTY VALIDATION: Ensure page has properties
          if (!p.properties || Object.keys(p.properties).length === 0) {
            UL.warn('Page has no properties - this may indicate a schema issue', {
              database: title,
              pageId: pageId,
              pageTitle: pageTitle
            });
          }
          
          if (lastSynced && edited && edited > lastSynced) {
            skipped++;
            UL.warn('Skipped page - edited after CSV snapshot', { 
              database: title, 
              page: pageTitle, 
              pageId, 
              edited, 
              lastSynced 
            });
            continue;
          }
        }
        notionFetch_(`pages/${pageId}`, 'PATCH', { properties: propsPayload });
        if (idxSynced >= 0) rows[r][idxSynced] = nowIso();
        updated++;
      } else {
        // TITLE VALIDATION GATE: Skip rows where title property is empty/null (P0 fix)
        // This prevents creating orphaned rows with empty names per issue:
        // "DriveSheetsSync v2.2 — Critical Issues Causing Orphaned Rows & Relation Data Loss"
        if (titleName && (!propsPayload[titleName] ||
            !propsPayload[titleName].title ||
            !propsPayload[titleName].title.length ||
            !propsPayload[titleName].title[0]?.text?.content?.trim())) {
          skipped++;
          UL.warn('Skipped row - title property empty (prevents orphaned rows)', {
            database: title,
            row: r,
            titleProperty: titleName,
            hasPayloadEntry: !!propsPayload[titleName]
          });
          continue;
        }

        const body = { parent: { type: 'data_source_id', data_source_id: ds.id }, properties: propsPayload };
        const createdPage = notionFetch_('pages', 'POST', body);
        if (idxPageId >= 0) rows[r][idxPageId] = createdPage.id;
        if (idxSynced >= 0) rows[r][idxSynced] = nowIso();
        created++;
      }
    } catch (e) {
      skipped++;
      const errorMsg = String(e);
      const stack = e.stack || 'No stack trace available';
      UL.error('Failed to sync row to Notion', { database: title, row: r, error: errorMsg, stack });
    }
  }

  try {
    // ARCHIVAL AND VERSIONING: Create versioned backup before updating CSV (Notion version history)
    const archiveFolder = ensureArchiveFolder_(folder, UL);
    if (archiveFolder && file) {
      // Create backup before updating (captures state before sync changes)
      createVersionedBackup_(file, archiveFolder, UL);
      // Clean up old versions (keep last 50 versions)
      archiveOldVersions_(archiveFolder, csvName, 50, UL);
    }
    
    // ARCHIVAL AND VERSIONING: Update the same file in place (don't create new items)
    // This ensures the CSV file is a persistent clone/backup that is updated over time
    const rebuilt = rows.map(cols => (cols || []).map(escapeCsv).join(',')).join('\n');
    file.setContent(rebuilt);
    
    // Verify the update was successful
    try {
      const verifyContent = file.getBlob().getDataAsString();
      if (verifyContent.length < rebuilt.length) {
        UL?.error?.('CSV file update verification failed', {
          database: title,
          csvName: csvName,
          expectedSize: rebuilt.length,
          actualSize: verifyContent.length,
          fileId: file.getId(),
          fileUrl: file.getUrl()
        });
      } else {
        UL?.debug?.('CSV file updated successfully (persistent item updated in place)', {
          database: title,
          csvName: csvName,
          fileId: file.getId(),
          fileUrl: file.getUrl(),
          fileSize: verifyContent.length,
          rowsUpdated: rows.length - 2, // Exclude header and type rows
          note: 'File is persistent and will be reused in next run'
        });
      }
    } catch (verifyError) {
      UL?.warn?.('Could not verify CSV file update', {
        database: title,
        csvName: csvName,
        error: String(verifyError),
        fileId: file.getId()
      });
    }
  } catch (e) {
    UL.error('Failed to update CSV file after sync', { database: title, error: String(e) });
  }

  UL.info('CSV value sync completed', { database: title, created, updated, skipped });
  return { created, updated, skipped };
}

/* ============================== MULTI-FILE TYPE SYNC (2-WAY) ============================== */

/**
 * Extract basic file metadata (size, dates, etc.)
 * @param {GoogleAppsScript.Drive.File} file - Drive file
 * @returns {Object} File metadata
 */
function extractFileMetadata_(file) {
  const metadata = {
    fileName: file.getName(),
    fileSize: file.getSize(),
    dateCreated: file.getDateCreated(),
    dateModified: file.getLastUpdated(),
    mimeType: file.getMimeType(),
    fileId: file.getId(),
    url: file.getUrl()
  };
  
  // Try to get thumbnail URL for images
  if (metadata.mimeType && metadata.mimeType.startsWith('image/')) {
    try {
      const thumbnail = file.getThumbnail();
      if (thumbnail) {
        metadata.thumbnailUrl = thumbnail.getAs('image/png').getBlob().getDataAsString();
      }
    } catch (e) {
      // Thumbnail not available
    }
  }
  
  return metadata;
}

/**
 * Calculate file hash for deduplication (SHA-256)
 * Note: GAS doesn't have native crypto, so this uses Utilities.computeDigest
 * @param {GoogleAppsScript.Drive.File} file - Drive file
 * @returns {string} File hash (or file ID as fallback)
 */
function calculateFileHash_(file) {
  try {
    // Use Utilities.computeDigest for basic hashing
    const blob = file.getBlob();
    const hashBytes = Utilities.computeDigest(
      Utilities.DigestAlgorithm.SHA_256,
      blob.getBytes()
    );
    const hashString = hashBytes.map(byte => ('0' + (byte & 0xFF).toString(16)).slice(-2)).join('');
    return hashString;
  } catch (e) {
    // Fallback to file ID + size as identifier
    return `${file.getId()}_${file.getSize()}`;
  }
}

/**
 * Map file metadata to Notion properties following Eagle sync patterns
 * @param {Object} metadata - File metadata from extractFileMetadata_
 * @param {string} fileHash - File hash from calculateFileHash_
 * @param {string} fileType - File type from detectFileType_
 * @param {Object} dbProps - Database properties schema
 * @param {Object} ds - Data source object
 * @param {Object} UL - Unified logger
 * @returns {Object} Properties payload for Notion
 */
function mapFileMetadataToProperties_(metadata, fileHash, fileType, dbProps, ds, UL) {
  const propsPayload = {};
  const title = dsTitle_(ds);
  
  // Get title property name
  let titleName = null;
  for (const [k, v] of Object.entries(dbProps)) {
    if (v.type === 'title') {
      titleName = k;
      break;
    }
  }
  
  // Core properties (following Eagle sync pattern)
  if (titleName) {
    const titleValue = csvCellToPropertyValue_('title', metadata.fileName);
    if (titleValue) propsPayload[titleName] = titleValue;
  }
  
  // File hash for deduplication
  if (dbProps['Hash']) {
    propsPayload['Hash'] = csvCellToPropertyValue_('rich_text', fileHash);
  }
  
  // File size
  if (dbProps['Size'] && metadata.fileSize) {
    propsPayload['Size'] = csvCellToPropertyValue_('number', String(metadata.fileSize));
  }
  
  // MIME Type
  if (dbProps['MIME Type'] && metadata.mimeType) {
    propsPayload['MIME Type'] = csvCellToPropertyValue_('rich_text', metadata.mimeType);
  }
  
  // Date Created
  if (dbProps['Created At'] && metadata.dateCreated) {
    propsPayload['Created At'] = csvCellToPropertyValue_('date', metadata.dateCreated.toISOString());
  }
  
  // Last Modified
  if (dbProps['Last Modified'] && metadata.dateModified) {
    propsPayload['Last Modified'] = csvCellToPropertyValue_('date', metadata.dateModified.toISOString());
  }
  
  // Last Sync Time
  if (dbProps['Last Sync Time']) {
    propsPayload['Last Sync Time'] = csvCellToPropertyValue_('date', nowIso());
  }
  
  // Path (file path or URL)
  if (dbProps['Path']) {
    const pathValue = metadata.url || metadata.fileName;
    propsPayload['Path'] = csvCellToPropertyValue_('rich_text', pathValue);
  }
  
  // File Link (if URL property exists)
  if (dbProps['File Link'] && metadata.url) {
    propsPayload['File Link'] = csvCellToPropertyValue_('url', metadata.url);
  }
  
  // File Extension
  const fileExt = metadata.fileName.split('.').pop()?.toLowerCase() || '';
  if (dbProps['File Extension'] && fileExt) {
    const propType = dbProps['File Extension']?.type || 'rich_text';
    propsPayload['File Extension'] = csvCellToPropertyValue_(propType, fileExt);
  }
  
  // Data Source (indicate source)
  if (dbProps['Data Source']) {
    const propType = dbProps['Data Source']?.type || 'rich_text';
    propsPayload['Data Source'] = csvCellToPropertyValue_(propType, 'Google Drive Sync');
  }
  
  // For photos/videos, add additional properties if available
  if (fileType === 'Photo' || fileType === 'Video') {
    // Note: Full EXIF extraction would require external service
    // GAS cannot easily extract EXIF data from images
    // This would need to be done via:
    // 1. External API service
    // 2. Cloud Function
    // 3. Pre-processing script
    
    UL.debug('Photo/Video file detected - EXIF extraction not available in GAS', {
      fileName: metadata.fileName,
      fileType: fileType,
      note: 'Full metadata extraction requires external service'
    });
  }
  
  return propsPayload;
}

/* ============================== MARKDOWN FILE SYNC (2-WAY) ============================== */

/**
 * Parse markdown file with frontmatter
 * @param {string} content - Markdown file content
 * @returns {Object} { frontmatter: Object, body: string, hasFrontmatter: boolean }
 */
function parseMarkdownFile_(content) {
  const result = { frontmatter: {}, body: content, hasFrontmatter: false };
  
  // Check for YAML frontmatter (--- delimiters)
  const yamlMatch = content.match(/^---\s*\n([\s\S]*?)\n---\s*\n([\s\S]*)$/);
  if (yamlMatch) {
    result.hasFrontmatter = true;
    result.body = yamlMatch[2];
    
    // Simple YAML parsing (basic key: value pairs)
    const yamlContent = yamlMatch[1];
    const lines = yamlContent.split('\n');
    for (const line of lines) {
      const match = line.match(/^([^:]+):\s*(.+)$/);
      if (match) {
        const key = match[1].trim();
        let value = match[2].trim();
        
        // Remove quotes if present
        if ((value.startsWith('"') && value.endsWith('"')) || 
            (value.startsWith("'") && value.endsWith("'"))) {
          value = value.slice(1, -1);
        }
        
        // Try to parse as boolean or number
        if (value === 'true') value = true;
        else if (value === 'false') value = false;
        else if (/^-?\d+$/.test(value)) value = Number(value);
        else if (/^-?\d+\.\d+$/.test(value)) value = Number(value);
        
        result.frontmatter[key] = value;
      }
    }
  }
  
  return result;
}

/**
 * Extract page ID from filename or frontmatter
 * @param {string} filename - File name
 * @param {Object} frontmatter - Parsed frontmatter
 * @returns {string|null} Page ID or null
 */
function extractPageIdFromMarkdown_(filename, frontmatter) {
  // Check frontmatter first
  if (frontmatter.__page_id) return frontmatter.__page_id;
  if (frontmatter.page_id) return frontmatter.page_id;
  if (frontmatter.id) return frontmatter.id;
  
  // Check filename pattern: {page-id}.md or {name}_{page-id}.md
  const filenameMatch = filename.match(/([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})\.md$/i);
  if (filenameMatch) return filenameMatch[1];
  
  // Check for short ID (8 chars) at start of filename
  const shortIdMatch = filename.match(/^([a-f0-9]{8})/i);
  if (shortIdMatch) {
    // Try to find full page ID by querying Notion (would need database context)
    // For now, return null and let the system create a new page
    return null;
  }
  
  return null;
}

/**
 * Infer Notion property type from value
 * @param {*} value - Value to infer type from
 * @returns {string} Notion property type
 */
function inferPropertyType_(value) {
  if (typeof value === 'boolean') return 'checkbox';
  if (typeof value === 'number') return 'number';
  if (value instanceof Date || /^\d{4}-\d{2}-\d{2}/.test(String(value))) return 'date';
  if (String(value).includes(',')) return 'multi_select';
  if (/^https?:\/\//.test(String(value))) return 'url';
  if (/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(String(value))) return 'email';
  return 'rich_text';
}

/**
 * Map frontmatter to Notion property values
 * @param {Object} frontmatter - Parsed frontmatter
 * @param {Object} dbProps - Database properties schema
 * @param {Object} ds - Data source object
 * @param {Object} UL - Unified logger
 * @returns {Object} Properties payload for Notion
 */
function mapFrontmatterToProperties_(frontmatter, dbProps, ds, UL) {
  const propsPayload = {};
  const title = dsTitle_(ds);
  
  // Get title property name
  let titleName = null;
  for (const [k, v] of Object.entries(dbProps)) {
    if (v.type === 'title') {
      titleName = k;
      break;
    }
  }
  
  // Map each frontmatter field to Notion property
  for (const [key, value] of Object.entries(frontmatter)) {
    // Skip internal fields
    if (key.startsWith('__') || key === 'page_id' || key === 'id') continue;
    
    // Find matching property in database schema
    const dbProp = dbProps[key];
    if (!dbProp) {
      // Property doesn't exist - try to create it (infer type from value)
      const inferredType = inferPropertyType_(value);
      const dsId = resolveDatabaseToDataSourceId_(ds.id, UL);
      const targetId = dsId || ds.id;
      
      if (ensurePropertyExists_(targetId, key, inferredType, UL)) {
        UL.info('Created property from markdown frontmatter', {
          database: title,
          property: key,
          type: inferredType
        });
        // Refresh schema
        try {
          const endpoint = dsId ? `data_sources/${dsId}` : `databases/${ds.id}`;
          const freshDb = notionFetch_(endpoint, 'GET');
          dbProps[key] = freshDb.properties[key];
        } catch (e) {
          UL.warn('Could not refresh schema after property creation', {
            database: title,
            property: key,
            error: String(e)
          });
          continue;
        }
      } else {
        UL.warn('Could not create property from markdown frontmatter', {
          database: title,
          property: key
        });
        continue;
      }
    }
    
    const propType = dbProps[key]?.type;
    if (!propType) continue;
    
    // Use existing csvCellToPropertyValue_ function to convert value
    const pv = csvCellToPropertyValue_(propType, String(value));
    if (pv) {
      // Handle title property specially
      if (propType === 'title' && titleName && key !== titleName) {
        propsPayload[titleName] = pv;
      } else {
        propsPayload[key] = pv;
      }
    }
  }
  
  // If title is in frontmatter but not mapped, try to find it
  if (titleName && !propsPayload[titleName]) {
    const titleKeys = ['title', 'name', 'Title', 'Name'];
    for (const key of titleKeys) {
      if (frontmatter[key]) {
        const pv = csvCellToPropertyValue_('title', String(frontmatter[key]));
        if (pv) {
          propsPayload[titleName] = pv;
          break;
        }
      }
    }
  }
  
  return propsPayload;
}

/**
 * Sync markdown files from Google Drive clone directory to Notion
 * @param {GoogleAppsScript.Drive.Folder} folder - Database folder
 * @param {Object} ds - Data source object
 * @param {Object} UL - Unified logger
 * @param {Object} options - Sync options
 * @returns {Object} { created: number, updated: number, skipped: number }
 */
function syncMarkdownFilesToNotion_(folder, ds, UL, options = {}) {
  if (!CONFIG.SYNC.ENABLE_MARKDOWN_SYNC) {
    UL.debug('Markdown sync disabled - skipping', { database: dsTitle_(ds) });
    return { created: 0, updated: 0, skipped: 0 };
  }
  
  const title = dsTitle_(ds);
  let created = 0, updated = 0, skipped = 0;
  
  try {
    // Track the database folder in Notion Folders database
    if (folder) {
      getOrCreateFolderInNotion_(folder, UL);
    }
    
    // Get database schema
    const schemaInfo = fetchDatabaseSchema_(ds.id, UL);
    if (!schemaInfo.ok) {
      UL.warn('Cannot sync markdown files - database not accessible', { database: title });
      return { created: 0, updated: 0, skipped: 0 };
    }
    const { props: dbProps, titleName } = schemaInfo;
    
    // Scan for markdown files (exclude CSV files)
    const mdFiles = [];
    const files = folder.getFiles();
    while (files.hasNext()) {
      const file = files.next();
      const fileName = file.getName();
      const mimeType = file.getMimeType();
      
      // Include .md files and text/markdown mime type
      if (fileName.endsWith('.md') || mimeType === 'text/markdown' || mimeType === 'text/plain') {
        // Exclude CSV files (they have .csv extension)
        if (!fileName.endsWith('.csv')) {
          mdFiles.push(file);
        }
      }
    }
    
    UL.info('Found files to sync', { 
      database: title, 
      fileCount: mdFiles.length 
    });
    
    // Process each file
    for (const file of mdFiles) {
      try {
        const fileName = file.getName();
        const mimeType = file.getMimeType();
        
        // Detect file type
        const fileType = detectFileType_(fileName, mimeType);
        
        // Extract page ID from filename or frontmatter (for markdown files)
        let pageId = null;
        let frontmatter = {};
        let bodyContent = null;
        
        // For markdown files, parse frontmatter
        if (fileName.endsWith('.md') || mimeType === 'text/markdown') {
          try {
            const content = file.getBlob().getDataAsString();
            const parsed = parseMarkdownFile_(content);
            frontmatter = parsed.frontmatter;
            bodyContent = parsed.body;
            pageId = extractPageIdFromMarkdown_(fileName, frontmatter);
          } catch (e) {
            UL.warn('Could not parse markdown file', {
              database: title,
              fileName: fileName,
              error: String(e)
            });
          }
        } else {
          // For other file types, check filename for page ID pattern
          const filenameMatch = fileName.match(/([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})/i);
          if (filenameMatch) {
            pageId = filenameMatch[1];
          }
        }
        
        // Map frontmatter/metadata to Notion properties
        let propsPayload = {};
        
        // For markdown files, use frontmatter mapping
        if (fileName.endsWith('.md') || mimeType === 'text/markdown') {
          if (Object.keys(frontmatter).length > 0) {
            propsPayload = mapFrontmatterToProperties_(frontmatter, dbProps, ds, UL);
          }
        }
        
        // For photos/videos, extract file metadata following Eagle sync patterns
        if (fileType === 'Photo' || fileType === 'Video' || fileType === 'Image') {
          const fileMetadata = extractFileMetadata_(file);
          const fileHash = calculateFileHash_(file);
          const metadataProps = mapFileMetadataToProperties_(fileMetadata, fileHash, fileType, dbProps, ds, UL);
          
          // Merge with frontmatter if present
          propsPayload = { ...metadataProps, ...propsPayload };
        } else {
          // For other files, set basic properties
          if (titleName && !propsPayload[titleName]) {
            const baseName = fileName.replace(/\.[^/.]+$/, ''); // Remove extension
            const titleValue = csvCellToPropertyValue_('title', baseName);
            if (titleValue) {
              propsPayload[titleName] = titleValue;
            }
          }
          
          // Add basic file metadata
          const fileMetadata = extractFileMetadata_(file);
          if (dbProps['Size'] && fileMetadata.fileSize) {
            propsPayload['Size'] = csvCellToPropertyValue_('number', String(fileMetadata.fileSize));
          }
          if (dbProps['MIME Type'] && fileMetadata.mimeType) {
            propsPayload['MIME Type'] = csvCellToPropertyValue_('rich_text', fileMetadata.mimeType);
          }
        }
        
        // Get or create Item-Type and set relation
        if (CONFIG.SYNC.REQUIRE_ITEM_TYPE) {
          const itemTypePropName = CONFIG.SYNC.ITEM_TYPE_PROPERTY_NAME;
          if (dbProps[itemTypePropName]) {
            const itemTypePageId = getOrCreateItemType_(fileType, UL);
            if (itemTypePageId) {
              propsPayload[itemTypePropName] = { relation: [{ id: itemTypePageId }] };
              UL.debug('Set Item-Type relation', {
                database: title,
                fileName: fileName,
                itemType: fileType,
                itemTypePageId: itemTypePageId
              });
            }
          } else {
            UL.warn('Item-Type property not found in database schema', {
              database: title,
              propertyName: itemTypePropName
            });
          }
        }
        
        // Ensure Clone-URL and Clone-Parent-Folder properties exist
        const cloneUrlPropName = 'Clone-URL';
        const cloneParentPropName = 'Clone-Parent-Folder';
        
        try {
          ensurePropertyExists_(ds.id, cloneUrlPropName, 'url', UL);
        } catch (e) {
          UL.warn('Could not ensure Clone-URL property exists', {
            database: title,
            error: String(e)
          });
        }
        
        try {
          ensurePropertyExists_(ds.id, cloneParentPropName, 'relation', UL);
        } catch (e) {
          UL.warn('Could not ensure Clone-Parent-Folder property exists', {
            database: title,
            error: String(e)
          });
        }
        
        // Refresh schema to get newly created properties
        try {
          const dsId = resolveDatabaseToDataSourceId_(ds.id, UL);
          const endpoint = dsId ? `data_sources/${dsId}` : `databases/${ds.id}`;
          const freshDb = notionFetch_(endpoint, 'GET');
          Object.assign(dbProps, freshDb.properties || {});
        } catch (e) {
          UL.debug('Could not refresh schema after property creation', {
            database: title,
            error: String(e)
          });
        }
        
        // Set Clone-URL property (Google Drive URL to the clone file)
        const fileUrl = file.getUrl();
        if (fileUrl && dbProps[cloneUrlPropName]) {
          propsPayload[cloneUrlPropName] = { url: fileUrl };
        }
        
        // Get or create folder entry in Folders database and set Clone-Parent-Folder relation
        const parentFolders = file.getParents();
        if (parentFolders.hasNext() && dbProps[cloneParentPropName]) {
          const parentFolder = parentFolders.next();
          const folderNotionId = getOrCreateFolderInNotion_(parentFolder, UL);
          if (folderNotionId) {
            propsPayload[cloneParentPropName] = { relation: [{ id: folderNotionId }] };
            UL.debug('Set Clone-Parent-Folder relation', {
              database: title,
              fileName: fileName,
              folderNotionId: folderNotionId,
              folderName: parentFolder.getName()
            });
          }
        }
        
        // MGM: Validate relations
        validateRelations_(propsPayload, dbProps, UL);
        
        // MGM: Set lifecycle property on new pages
        const isNewPage = !pageId;
        setLifecycleProperty_(propsPayload, dbProps, UL, isNewPage, ds.id);
        
        // Ensure we have at least a title property
        if (Object.keys(propsPayload).length === 0 || (!titleName || !propsPayload[titleName])) {
          skipped++;
          UL.warn('No valid properties to sync from file', {
            database: title,
            fileName: fileName,
            pageId: pageId || 'NEW',
            fileType: fileType
          });
          continue;
        }
        
        // Check for conflicts (if page exists)
        if (pageId) {
          if ((options.conflict === 'guard') || (CONFIG.SYNC.CONFLICT_MODE === 'guard')) {
            try {
              const p = notionFetch_(`pages/${pageId}`, 'GET');
              const edited = p.last_edited_time || '';
              const fileModified = file.getLastUpdated();
              
              // If Notion page was edited after file, skip update
              if (edited && fileModified && new Date(edited) > fileModified) {
                skipped++;
                UL.warn('Skipped markdown file - Notion page edited after file', {
                  database: title,
                  fileName: fileName,
                  pageId: pageId,
                  notionEdited: edited,
                  fileModified: fileModified.toISOString()
                });
                continue;
              }
            } catch (e) {
              UL.warn('Could not check conflict for markdown file', {
                database: title,
                fileName: fileName,
                pageId: pageId,
                error: String(e)
              });
              // Continue anyway - try to update
            }
          }
          
          // Update existing page
          notionFetch_(`pages/${pageId}`, 'PATCH', { properties: propsPayload });
          
          // Update page body content if body exists (markdown files only)
          if (bodyContent && bodyContent.trim() && fileName.endsWith('.md')) {
            try {
              // Get existing blocks
              const blocks = notionFetch_(`blocks/${pageId}/children`, 'GET');
              
              // Clear existing content (optional - could append instead)
              // For now, we'll just update properties, not body content
              // Body content sync would require more complex block manipulation
            } catch (e) {
              UL.debug('Could not update page body content', {
                database: title,
                pageId: pageId,
                error: String(e)
              });
            }
          }
          
          updated++;
          UL.info('Updated Notion page from file', {
            database: title,
            fileName: fileName,
            fileType: fileType,
            pageId: pageId
          });
        } else {
          // Create new page
          const body = { 
            parent: { type: 'data_source_id', data_source_id: ds.id }, 
            properties: propsPayload 
          };
          const createdPage = notionFetch_('pages', 'POST', body);
          
          // Rename file to include page ID for future syncs
          const fileExt = fileName.split('.').pop() || '';
          const newFileName = `${createdPage.id}.${fileExt}`;
          try {
            file.setName(newFileName);
            UL.info('Renamed file to include page ID', {
              database: title,
              oldName: fileName,
              newName: newFileName,
              pageId: createdPage.id,
              fileType: fileType
            });
          } catch (e) {
            UL.warn('Could not rename file', {
              database: title,
              fileName: fileName,
              pageId: createdPage.id,
              fileType: fileType,
              error: String(e)
            });
          }
          
          created++;
          UL.info('Created Notion page from file', {
            database: title,
            fileName: fileName,
            fileType: fileType,
            pageId: createdPage.id
          });
        }
      } catch (e) {
        skipped++;
        const errorMsg = String(e);
        const stack = e.stack || 'No stack trace available';
        UL.error('Failed to sync file to Notion', {
          database: title,
          fileName: file.getName(),
          fileType: detectFileType_(file.getName(), file.getMimeType()),
          error: errorMsg,
          stack
        });
      }
    }
    
    UL.info('File sync completed', {
      database: title,
      created,
      updated,
      skipped,
      totalFiles: mdFiles.length
    });
    
    return { created, updated, skipped };
  } catch (e) {
    UL.error('File sync failed', {
      database: title,
      error: String(e),
      stack: e.stack || 'No stack trace available'
    });
    return { created: 0, updated: 0, skipped: 0 };
  }
}

/* ============================== PROPERTY VALIDATION AND AUTO-CREATION ============================== */

/**
 * Required properties configuration for critical databases
 * Maps database ID to required properties with their types and default configs
 */
const REQUIRED_PROPERTIES_CONFIG = {
  // Execution-Logs database
  [CONFIG.EXECUTION_LOGS_DB_ID]: {
    'Name': { type: 'title', required: true },
    'Start Time': { type: 'date', required: true },
    'End Time': { type: 'date', required: false },
    'Final Status': { type: 'select', required: true, options: ['Running', 'Completed', 'Failed', 'Cancelled'] },
    'Status': { type: 'rich_text', required: false }, // Legacy compatibility
    'Duration (s)': { type: 'number', required: false },
    'Script Name-AI': { type: 'rich_text', required: false },
    'Session ID': { type: 'rich_text', required: false },
    'Environment': { type: 'rich_text', required: false },
    'Script ID': { type: 'rich_text', required: false },
    'Timezone': { type: 'rich_text', required: false },
    'User Email': { type: 'rich_text', required: false },
    'Plain-English Summary': { type: 'rich_text', required: false },
    'Error Count': { type: 'number', required: false },
    'Warning Count': { type: 'number', required: false }
  },
  // Workspace Registry database
  [CONFIG.WORKSPACE_REGISTRY_DB_ID]: {
    'Database Name': { type: 'title', required: true },
    'Name': { type: 'title', required: false }, // Alternative title property name (as per validate_schemas.gs)
    'Data Source ID': { type: 'rich_text', required: true },
    'URL': { type: 'url', required: false },
    'Database URL': { type: 'url', required: false }, // Alternative URL property name (as per validate_schemas.gs)
    'Status': { type: 'select', required: true, options: ['Success', 'Failed', 'Partial', 'Running', 'Paused'] },
    'Row Count': { type: 'number', required: false },
    'Property Count': { type: 'number', required: false },
    'Properties': { type: 'rich_text', required: false },
    'Last Sync': { type: 'date', required: false },
    'Archived': { type: 'checkbox', required: false },
    'CSV File ID': { type: 'rich_text', required: false },
    'Drive Folder': { type: 'url', required: false },
    'Rotation Last Processed': { type: 'date', required: false } // Optional rotation tracking property (as per validate_schemas.gs)
  },
  // Scripts database
  [CONFIG.SCRIPTS_DB_ID]: {
    'Name': { type: 'title', required: true },
    'Script ID': { type: 'rich_text', required: false }, // Google Apps Script ID
    'Google Apps Script ID': { type: 'rich_text', required: false }, // Alternative property name
    'GAS Script ID': { type: 'rich_text', required: false }, // Alternative property name
    'Script-ID': { type: 'rich_text', required: false }, // Alternative property name
    'Most Recent Log': { type: 'relation', required: false }, // Relation to Execution-Logs
    'Script Name': { type: 'rich_text', required: false },
    'Title': { type: 'title', required: false } // Alternative title property
  }
};

/**
 * Validates and auto-creates required properties for a database
 * @param {string} dbId - Database ID
 * @param {string} dataSourceId - Data source ID (for API 2025-09-03)
 * @param {Object} UL - Unified logger instance
 * @returns {Object} Validation result with created/missing properties
 */
function validateAndCreateRequiredProperties_(dbId, dataSourceId, UL) {
  const result = {
    validated: true,
    created: [],
    missing: [],
    errors: []
  };
  
  try {
    const requiredProps = REQUIRED_PROPERTIES_CONFIG[dbId];
    if (!requiredProps) {
      // No required properties defined for this database - skip validation
      return result;
    }
    
    // Get current database schema
    let db = null;
    try {
      if (dataSourceId) {
        db = notionFetch_(`data_sources/${dataSourceId}`, 'GET');
      } else {
        const dsId = resolveDatabaseToDataSourceId_(dbId, UL);
        if (dsId) {
          db = notionFetch_(`data_sources/${dsId}`, 'GET');
        } else {
          db = notionFetch_(`databases/${dbId}`, 'GET');
        }
      }
    } catch (e) {
      UL.error('Failed to fetch database schema for property validation', {
        dbId,
        dataSourceId,
        error: String(e)
      });
      result.validated = false;
      result.errors.push({ step: 'fetch_schema', error: String(e) });
      return result;
    }
    
    const existingProps = db.properties || {};
    const propertiesToCreate = {};
    
    // Check each required property
    for (const [propName, propConfig] of Object.entries(requiredProps)) {
      if (!propConfig.required) continue; // Skip optional properties
      
      const existingProp = existingProps[propName];
      
      if (!existingProp) {
        // Property is missing - create it
        const propDef = buildPropertyConfigFromType_(propConfig.type, []);
        
        // Handle select properties with options
        if (propConfig.type === 'select' && propConfig.options) {
          propDef.select = { options: propConfig.options.map(opt => ({ name: opt })) };
        }
        
        propertiesToCreate[propName] = propDef;
        result.missing.push(propName);
      } else {
        // Property exists - verify type matches
        const actualType = existingProp.type;
        if (actualType !== propConfig.type && 
            !(propConfig.type === 'rich_text' && actualType === 'text') &&
            !(propConfig.type === 'text' && actualType === 'rich_text')) {
          UL.warn('Property type mismatch detected', {
            dbId,
            property: propName,
            expected: propConfig.type,
            actual: actualType
          });
        }
      }
    }
    
    // Create missing properties if any
    if (Object.keys(propertiesToCreate).length > 0) {
      try {
        const patch = { properties: propertiesToCreate };
        // dataSourceId might already be provided, or we need to resolve dbId
        // resolveDatabaseToDataSourceId_ now handles both data_source_id and database_id
        const targetId = dataSourceId || resolveDatabaseToDataSourceId_(dbId, UL) || dbId;
        // Determine endpoint: if targetId is same as dbId and dbId is not a data_source_id format,
        // use databases endpoint; otherwise use data_sources endpoint
        // Try to detect if targetId is already a data_source_id by checking if it resolves to itself
        const resolvedId = resolveDatabaseToDataSourceId_(targetId, UL);
        const endpoint = (resolvedId === targetId || dataSourceId) ? `data_sources/${targetId}` : `databases/${dbId}`;
        
        notionFetch_(endpoint, 'PATCH', patch);
        
        result.created = Object.keys(propertiesToCreate);
        UL.info('Created missing required properties', {
          dbId,
          propertiesCreated: result.created
        });
      } catch (e) {
        UL.error('Failed to create missing properties', {
          dbId,
          properties: Object.keys(propertiesToCreate),
          error: String(e)
        });
        result.validated = false;
        result.errors.push({ step: 'create_properties', error: String(e) });
      }
    }
    
    // Final validation: check if all required properties now exist
    if (result.created.length > 0) {
      // Re-fetch schema to verify
      try {
        const targetId = dataSourceId || resolveDatabaseToDataSourceId_(dbId, UL) || dbId;
        const endpoint = targetId === dbId ? `databases/${dbId}` : `data_sources/${targetId}`;
        const freshDb = notionFetch_(endpoint, 'GET');
        const freshProps = freshDb.properties || {};
        
        for (const propName of result.created) {
          if (!freshProps[propName]) {
            result.errors.push({
              step: 'verify_creation',
              property: propName,
              error: 'Property was not created successfully'
            });
            result.validated = false;
          }
        }
      } catch (e) {
        UL.warn('Could not verify property creation', {
          dbId,
          error: String(e)
        });
      }
    }
    
  } catch (e) {
    UL.error('Property validation failed', {
      dbId,
      dataSourceId,
      error: String(e),
      stack: e.stack
    });
    result.validated = false;
    result.errors.push({ step: 'validation', error: String(e) });
  }
  
  return result;
}

/**
 * Ensures Scripts database exists, creates it if not accessible
 * @param {Object} UL - Unified logger instance
 * @returns {string|null} Database ID if accessible or created, null if creation failed
 */
function ensureScriptsDatabaseExists_(UL) {
  if (!CONFIG.SCRIPTS_DB_ID) {
    UL.warn('Scripts database ID not configured - cannot ensure database exists');
    return null;
  }
  
  // First, try to access the database
  try {
    const dsId = resolveDatabaseToDataSourceId_(CONFIG.SCRIPTS_DB_ID, UL);
    if (dsId) {
      // Database exists and is accessible
      UL.debug('Scripts database is accessible', {
        dbId: CONFIG.SCRIPTS_DB_ID,
        dataSourceId: dsId
      });
      return CONFIG.SCRIPTS_DB_ID;
    }
  } catch (e) {
    // Database not accessible - will try to create
    UL.debug('Scripts database not accessible, will attempt to create', {
      dbId: CONFIG.SCRIPTS_DB_ID,
      error: String(e)
    });
  }
  
  // Database not accessible - try to create it
  try {
    UL.info('Creating Scripts database as it is not accessible', {
      dbId: CONFIG.SCRIPTS_DB_ID,
      parentPageId: CONFIG.DATABASE_PARENT_PAGE_ID
    });
    
    // Get required properties from config
    const requiredProps = REQUIRED_PROPERTIES_CONFIG[CONFIG.SCRIPTS_DB_ID];
    if (!requiredProps) {
      UL.error('Cannot create Scripts database - required properties not defined in config');
      return null;
    }
    
    // Build properties object for database creation
    const properties = {};
    for (const [propName, propConfig] of Object.entries(requiredProps)) {
      if (propConfig.type === 'title') {
        properties[propName] = { title: {} };
      } else if (propConfig.type === 'rich_text') {
        properties[propName] = { rich_text: {} };
      } else if (propConfig.type === 'relation') {
        // Relation properties need a target database - skip for now or use Execution-Logs
        // Skip Most Recent Log relation for initial creation (can be added later)
        if (propName === 'Most Recent Log') {
          // Try to create relation to Execution-Logs if available
          if (CONFIG.EXECUTION_LOGS_DB_ID) {
            try {
              const execLogsDsId = resolveDatabaseToDataSourceId_(CONFIG.EXECUTION_LOGS_DB_ID, UL);
              if (execLogsDsId) {
                properties[propName] = {
                  relation: {
                    data_source_id: execLogsDsId,
                    type: 'single_property'
                  }
                };
              }
            } catch (e) {
              UL.debug('Cannot create Most Recent Log relation - Execution-Logs database not accessible', {
                error: String(e)
              });
              // Skip this property for now
            }
          }
        }
      }
    }
    
    // Ensure Name property exists (required for database creation)
    if (!properties['Name'] && !properties['Title']) {
      properties['Name'] = { title: {} };
    }
    
    // Create the database
    // Notion API: POST /v1/databases
    const newDb = notionFetch_('databases', 'POST', {
      parent: {
        type: 'page_id',
        page_id: CONFIG.DATABASE_PARENT_PAGE_ID
      },
      title: [
        {
          type: 'text',
          text: {
            content: 'Scripts'
          }
        }
      ],
      properties: properties
    });
    
    const createdDbId = newDb.id;
    UL.info('Successfully created Scripts database', {
      createdDbId: createdDbId,
      originalDbId: CONFIG.SCRIPTS_DB_ID,
      url: newDb.url || `https://www.notion.so/${createdDbId.replace(/-/g, '')}`
    });
    
    // Note: The created database ID may differ from CONFIG.SCRIPTS_DB_ID
    // The user should update CONFIG.SCRIPTS_DB_ID if needed
    if (createdDbId !== CONFIG.SCRIPTS_DB_ID) {
      UL.warn('Created database ID differs from configured ID', {
        configuredId: CONFIG.SCRIPTS_DB_ID,
        createdId: createdDbId,
        note: 'Update CONFIG.SCRIPTS_DB_ID or script property DB_ID_DEV_SCRIPTS if needed'
      });
    }
    
    return createdDbId;
    
  } catch (e) {
    UL.error('Failed to create Scripts database', {
      dbId: CONFIG.SCRIPTS_DB_ID,
      parentPageId: CONFIG.DATABASE_PARENT_PAGE_ID,
      error: String(e),
      stack: e.stack
    });
    return null;
  }
}

function ensurePropertyExists_(dbId, propName, propType, UL) {
  try {
    // dbId might already be a data_source_id (from search results) or a database_id (from config)
    // resolveDatabaseToDataSourceId_ now handles both cases - it will return the data_source_id
    const dsId = resolveDatabaseToDataSourceId_(dbId, UL);
    
    // If resolution failed and we can't access the database, throw error to allow caller to handle gracefully
    if (!dsId && !dbId) {
      throw new Error('Database ID is null or empty');
    }
    
    // If resolution failed, try databases endpoint as fallback (for legacy database_id)
    const endpoint = dsId ? `data_sources/${dsId}` : `databases/${dbId}`;
    
    const db = notionFetch_(endpoint, 'GET');
    const existingProps = db.properties || {};
    
    if (existingProps[propName]) {
      return true; // Property exists
    }
    
    // Property missing - create it
    const propDef = buildPropertyConfigFromType_(propType, []);
    const patch = { properties: { [propName]: propDef } };
    
    notionFetch_(endpoint, 'PATCH', patch);
    
    UL.info('Created missing property', {
      dbId,
      property: propName,
      type: propType,
      endpoint: endpoint
    });
    
    return true;
  } catch (e) {
    const err = String(e);
    // If database is not accessible (404), throw error to allow caller to handle gracefully
    // Don't log as error if it's a 404 - this is expected for inaccessible databases
    if (err.includes('404') || err.includes('object_not_found')) {
      UL.warn('Cannot ensure property exists - database not accessible', {
        dbId,
        property: propName,
        type: propType,
        error: 'Database not shared with integration or does not exist'
      });
      // Throw to allow caller to handle gracefully
      throw e;
    } else {
      UL.error('Failed to ensure property exists', {
        dbId,
        property: propName,
        type: propType,
        error: err
      });
      return false;
    }
  }
}

/**
 * Ensures the Item-Type relation property exists on a database
 * This property links database items to entries in the Item-Types database
 * for categorization and type tracking across the workspace.
 *
 * @param {string} dbId - Database ID or data source ID
 * @param {Object} UL - Unified logger instance
 * @returns {boolean} True if property exists or was created, false if skipped/failed
 */
function ensureItemTypePropertyExists_(dbId, UL) {
  const itemTypesDbId = DB_CONFIG.ITEM_TYPES;
  const propName = CONFIG.SYNC.ITEM_TYPE_PROPERTY_NAME || 'Item-Type';

  // If Item-Types database is not configured, skip gracefully
  if (!itemTypesDbId) {
    UL.debug('Item-Type property check skipped - ITEM_TYPES database not configured', {
      dbId,
      propertyName: propName,
      hint: 'Set ITEM_TYPES_DB_ID script property to enable Item-Type relations'
    });
    return false;
  }

  try {
    // Resolve to data source ID for API 2025-09-03 compatibility
    const dsId = resolveDatabaseToDataSourceId_(dbId, UL);
    if (!dsId && !dbId) {
      UL.warn('Cannot ensure Item-Type property - database ID is null');
      return false;
    }

    const endpoint = dsId ? `data_sources/${dsId}` : `databases/${dbId}`;
    const db = notionFetch_(endpoint, 'GET');
    const existingProps = db.properties || {};

    // Check if property already exists
    if (existingProps[propName]) {
      UL.debug('Item-Type property already exists', {
        dbId,
        propertyName: propName,
        propertyType: existingProps[propName].type
      });
      return true;
    }

    // Resolve Item-Types database to data source ID for the relation target
    const itemTypesDsId = resolveDatabaseToDataSourceId_(itemTypesDbId, UL);
    if (!itemTypesDsId) {
      UL.warn('Cannot create Item-Type property - Item-Types database not accessible', {
        dbId,
        itemTypesDbId
      });
      return false;
    }

    // Create relation property pointing to Item-Types database
    // Use data_source_id for API 2025-09-03 compatibility
    const propDef = {
      relation: {
        data_source_id: itemTypesDsId,
        single_property: {}
      }
    };

    const patch = { properties: { [propName]: propDef } };
    notionFetch_(endpoint, 'PATCH', patch);

    UL.info('Created Item-Type relation property', {
      dbId,
      propertyName: propName,
      targetDatabase: itemTypesDbId
    });

    return true;
  } catch (e) {
    const err = String(e);
    // Don't treat 404 as critical - database may not be shared with integration
    if (err.includes('404') || err.includes('object_not_found')) {
      UL.debug('Item-Type property check skipped - database not accessible', {
        dbId,
        propertyName: propName
      });
    } else {
      UL.warn('Failed to ensure Item-Type property exists', {
        dbId,
        propertyName: propName,
        error: err
      });
    }
    return false;
  }
}

/**
 * Validates all required properties for a database before operations
 * Called before critical operations that depend on specific properties
 * @param {string} dbId - Database ID
 * @param {string} dataSourceId - Data source ID (optional, for API 2025-09-03)
 * @param {Object} UL - Unified logger instance
 * @param {boolean} forceCreate - If true, creates missing properties; if false, only validates
 * @returns {boolean} True if all required properties exist or were created
 */
function validateRequiredProperties_(dbId, dataSourceId, UL, forceCreate = true) {
  if (!dbId) {
    UL.warn('Cannot validate properties - database ID is missing');
    return false;
  }
  
  const validationResult = forceCreate 
    ? validateAndCreateRequiredProperties_(dbId, dataSourceId, UL)
    : { validated: true, created: [], missing: [], errors: [] };
  
  if (!validationResult.validated) {
    UL.error('Property validation failed', {
      dbId,
      dataSourceId,
      errors: validationResult.errors,
      missing: validationResult.missing
    });
    return false;
  }
  
  if (validationResult.missing.length > 0 && !forceCreate) {
    UL.warn('Required properties are missing', {
      dbId,
      missing: validationResult.missing
    });
    return false;
  }
  
  if (validationResult.created.length > 0) {
    UL.info('Property validation completed - created missing properties', {
      dbId,
      created: validationResult.created
    });
  }
  
  return true;
}

/* ============================== MGM COMPLIANCE HELPERS ============================== */

// Cache to track which databases we've already logged lifecycle property absence for
const _lifecycleLogCache = {};

/**
 * MGM Lifecycle Tracking: Set lifecycle property on new pages and track transitions
 * Auto-creates Lifecycle property if missing and ENABLE_LIFECYCLE_TRACKING is true
 */
function setLifecycleProperty_(propsPayload, dbProps, UL, isNewPage = false, databaseId = null) {
  if (!CONFIG.SYNC.ENABLE_LIFECYCLE_TRACKING) return;
  
  // Check if database has Lifecycle property
  let lifecycleProp = Object.keys(dbProps).find(k => 
    k.toLowerCase() === 'lifecycle' && dbProps[k]?.type === 'select'
  );
  
  if (!lifecycleProp && databaseId) {
    // Lifecycle property is missing - create it automatically
    const cacheKey = databaseId || 'unknown';
    if (!_lifecycleLogCache[cacheKey]) {
      _lifecycleLogCache[cacheKey] = true;
      
      try {
        // Create Lifecycle property with standard options
        const lifecycleOptions = [
          'Proposed',
          'Active',
          'In Review',
          'Deprecated',
          'Archived'
        ];
        
        const propDef = {
          select: {
            options: lifecycleOptions.map(opt => ({ name: opt }))
          }
        };
        
        // databaseId might already be a data_source_id (from search results) or a database_id (from config)
        // resolveDatabaseToDataSourceId_ now handles both cases
        const dsId = resolveDatabaseToDataSourceId_(databaseId, UL);
        // If resolution succeeded, use data_sources endpoint; otherwise try databases endpoint
        const endpoint = dsId ? `data_sources/${dsId}` : `databases/${databaseId}`;
        
        const patch = { properties: { 'Lifecycle': propDef } };
        notionFetch_(endpoint, 'PATCH', patch);
        
        UL.info('Created missing Lifecycle property', {
          databaseId: cacheKey,
          options: lifecycleOptions
        });
        
        // Re-fetch schema to get the new property
        try {
          const freshDb = notionFetch_(endpoint, 'GET');
          dbProps = freshDb.properties || {};
          lifecycleProp = Object.keys(dbProps).find(k => 
            k.toLowerCase() === 'lifecycle' && dbProps[k]?.type === 'select'
          );
        } catch (e) {
          UL.warn('Created Lifecycle property but could not refresh schema', {
            databaseId: cacheKey,
            error: String(e)
          });
        }
      } catch (e) {
        UL.error('Failed to create Lifecycle property', {
          databaseId: cacheKey,
          error: String(e)
        });
        return; // Can't proceed without the property
      }
    } else {
      // Already tried to create it - property still missing, skip silently
      return;
    }
  } else if (!lifecycleProp) {
    // No databaseId provided and property doesn't exist - can't create it
    const cacheKey = databaseId || 'unknown';
    if (!_lifecycleLogCache[cacheKey]) {
      _lifecycleLogCache[cacheKey] = true;
      UL.debug('Database does not have Lifecycle property and databaseId not provided - skipping lifecycle tracking', {
        databaseId: cacheKey
      });
    }
    return;
  }
  
  // Default lifecycle values based on database type
  const defaultLifecycle = isNewPage ? 'Proposed' : null; // Only set on new pages
  
  if (defaultLifecycle && !propsPayload[lifecycleProp]) {
    propsPayload[lifecycleProp] = { select: { name: defaultLifecycle } };
    UL.info('Set lifecycle property on new page', {
      lifecycle: defaultLifecycle,
      property: lifecycleProp
    });
  }
}

/**
 * MGM Relation Validation: Validate relation targets exist before creating links
 */
function validateRelations_(propsPayload, dbProps, UL) {
  if (!CONFIG.SYNC.ENABLE_RELATION_VALIDATION) return;
  
  const invalidRelations = [];
  
  for (const [propName, propValue] of Object.entries(propsPayload)) {
    const propType = dbProps[propName]?.type;
    
    if (propType === 'relation' && propValue.relation) {
      const relationIds = Array.isArray(propValue.relation) 
        ? propValue.relation.map(r => r.id)
        : [propValue.relation.id];
      
      for (const relationId of relationIds) {
        if (!relationId) continue;
        
        try {
          // Validate target page exists and is not trashed
          const targetPage = notionFetch_(`pages/${relationId}`, 'GET');
          if (targetPage.archived || targetPage.in_trash) {
            invalidRelations.push({
              property: propName,
              targetId: relationId,
              reason: 'Target page is archived or trashed'
            });
            // Remove invalid relation
            delete propsPayload[propName];
          }
        } catch (e) {
          invalidRelations.push({
            property: propName,
            targetId: relationId,
            reason: `Target page not found or not accessible: ${String(e)}`
          });
          // Remove invalid relation
          delete propsPayload[propName];
        }
      }
    }
  }
  
  if (invalidRelations.length > 0) {
    UL.warn('Invalid relations detected and removed', {
      invalidCount: invalidRelations.length,
      invalidRelations: invalidRelations
    });
  }
}

/* ============================== SHEETS HELPERS ============================== */
function getOrCreateRegistrySpreadsheet_(parentId) {
  const cached = PROPS.getProperty('REGISTRY_SHEET_ID');
  if (cached) { try { return SpreadsheetApp.openById(cached); } catch (_) {} }
  const parent = DriveApp.getFolderById(parentId);
  const it = parent.getFilesByName(CONFIG.REGISTRY_SPREADSHEET_NAME);
  if (it.hasNext()) {
    const f = it.next();
    PROPS.setProperty('REGISTRY_SHEET_ID', f.getId());
    return SpreadsheetApp.openById(f.getId());
  }
  const ss = SpreadsheetApp.create(CONFIG.REGISTRY_SPREADSHEET_NAME);
  const file = DriveApp.getFileById(ss.getId());
  parent.addFile(file);
  try { DriveApp.getRootFolder().removeFile(file); } catch (_) {}
  PROPS.setProperty('REGISTRY_SHEET_ID', ss.getId());
  return ss;
}
function ensureSheetWithHeader_(ss, name, header) {
  const sheet = ss.getSheetByName(name) || ss.insertSheet(name);
  sheet.clear();
  if (header && header.length) sheet.getRange(1, 1, 1, header.length).setValues([header]);
  return sheet;
}
function writeDatabasesSheet_(ss, rows) {
  const header = ['Name', 'Data Source ID', 'URL', 'Archived', 'Created time', 'Last edited time', 'Row Count'];
  const sh = ensureSheetWithHeader_(ss, CONFIG.SHEET_DATABASES, header);
  if (rows.length) sh.getRange(2, 1, rows.length, header.length).setValues(rows);
}
function writePropertiesSheet_(ss, rows) {
  const header = ['Data Source ID', 'Data Source Name', 'Property Name', 'Type', 'Property ID', 'Configuration JSON'];
  const sh = ensureSheetWithHeader_(ss, CONFIG.SHEET_PROPERTIES, header);
  if (rows.length) sh.getRange(2, 1, rows.length, header.length).setValues(rows);
}

/* ============================== STATE ============================== */
class State {
  constructor(key) { this.key = CONFIG.STATE_KEY_PREFIX + key; this.state = this._load(); }
  _load() { try { const raw = PROPS.getProperty(this.key); return raw ? JSON.parse(raw) : { rp: 0, cycle: 0, lastRun: null }; } catch { return { rp: 0, cycle: 0, lastRun: null }; } }
  save() { PROPS.setProperty(this.key, JSON.stringify(this.state)); }
  get rp() { return this.state.rp || 0; }
  set rp(v) { this.state.rp = v; this.save(); }
  cycleInc() { this.state.cycle = (this.state.cycle || 0) + 1; this.state.lastRun = nowIso(); this.save(); }
}

/* ============================== DATABASE PROCESSING ============================== */
function processSingleDatabase_(ds, parent, ss, dbRows, propRows, UL) {
  const humanName = dsTitle_(ds);
  const startTime = Date.now();
  
  try {
    const databaseUrl = getNotionDatabaseUrl_(ds.id);
    UL.info('🔄 Starting database processing', { 
      database: humanName, 
      dataSourceId: ds.id,
      databaseUrl: databaseUrl,
      propertiesCount: Object.keys(ds.properties || {}).length
    });

    // COMPREHENSIVE PROPERTY VALIDATION: Ensure all expected properties exist before processing
    // This validates and auto-creates properties for critical databases
    const propsValid = validateRequiredProperties_(ds.id, ds.id, UL, true);
    if (!propsValid) {
      UL.warn('Property validation had issues - continuing with processing', {
        databaseId: ds.id,
        databaseName: humanName
      });
    }
    
    // Refresh schema after property validation to ensure we have latest properties
    try {
      const fresh = getDataSource_(ds.id, UL);
      if (fresh && fresh.properties) {
        ds.properties = fresh.properties;
        UL.debug('Refreshed database schema after property validation', {
          database: humanName,
          propertyCount: Object.keys(fresh.properties).length
        });
      }
    } catch (e) {
      UL.warn('Could not refresh schema after property validation', {
        database: humanName,
        error: String(e)
      });
    }

    const folder = ensureDbFolder_(parent.id, ds);
    UL.info('📁 Drive folder ready', { 
      database: humanName, 
      dataSourceId: ds.id,
      databaseUrl: databaseUrl,
      folderId: folder.getId(), 
      folderUrl: folder.getUrl() 
    });

    // Validate single In Progress invariant for Agent-Tasks databases
    if (CONFIG.AGENT_TASKS_DB_IDS.includes(ds.id)) {
      // Ensure Status property exists for invariant validation
      const statusPropNames = ['Status', 'MCP Execution Status', 'Execution Status'];
      let statusPropCreated = false;
      for (const propName of statusPropNames) {
        if (ensurePropertyExists_(ds.id, propName, 'select', UL)) {
          statusPropCreated = true;
          break;
        }
      }
      
      if (!statusPropCreated) {
        UL.warn('Could not ensure Status property exists for Agent-Tasks - invariant validation may fail', {
          databaseId: ds.id
        });
      }
      
      UL.info('🔍 Validating single In Progress invariant for Agent-Tasks database', { databaseId: ds.id });
      const invariantResult = validateSingleInProgressInvariant_(ds.id, UL);
      if (invariantResult && !invariantResult.valid && invariantResult.count > 1) {
        UL.warn('⚠️ Single In Progress invariant violation detected', {
          databaseId: ds.id,
          inProgressCount: invariantResult.count,
          tasks: invariantResult.tasks
        });
      }
    }

    // Ensure Item-Type property exists if required (before schema sync)
    if (CONFIG.SYNC.REQUIRE_ITEM_TYPE) {
      ensureItemTypePropertyExists_(ds.id, UL);
    }
    
    // Schema sync - this will create properties from CSV if they don't exist
    const schemaResult = syncSchemaFromCsvToNotion_(folder, ds, UL);
    if (schemaResult.added?.length || schemaResult.deleted?.length) {
      UL.info('🔄 Refreshing database schema after changes', { database: humanName });
      const fresh = getDataSource_(ds.id, UL);
      if (fresh) {
        ds.properties = fresh.properties;
        UL.debug('Schema refreshed after sync', {
          database: humanName,
          propertiesAdded: schemaResult.added?.length || 0,
          propertiesDeleted: schemaResult.deleted?.length || 0,
          totalProperties: Object.keys(fresh.properties || {}).length
        });
      }
    }
    
    // COMPREHENSIVE PROPERTY VALIDATION: Ensure Lifecycle property exists if tracking is enabled
    if (CONFIG.SYNC.ENABLE_LIFECYCLE_TRACKING) {
      const dbProps = ds.properties || {};
      const lifecycleProp = Object.keys(dbProps).find(k => 
        k.toLowerCase() === 'lifecycle' && dbProps[k]?.type === 'select'
      );
      if (!lifecycleProp) {
        // Lifecycle property will be created by setLifecycleProperty_ when first accessed
        // But we can proactively create it here to ensure it exists
        try {
          const lifecycleOptions = ['Proposed', 'Active', 'In Review', 'Deprecated', 'Archived'];
          const propDef = {
            select: {
              options: lifecycleOptions.map(opt => ({ name: opt }))
            }
          };
          const dsId = resolveDatabaseToDataSourceId_(ds.id, UL);
          const targetId = dsId || ds.id;
          const endpoint = dsId ? `data_sources/${dsId}` : `databases/${ds.id}`;
          const patch = { properties: { 'Lifecycle': propDef } };
          notionFetch_(endpoint, 'PATCH', patch);
          
          // Refresh schema
          const fresh = getDataSource_(ds.id, UL);
          if (fresh) ds.properties = fresh.properties;
          
          UL.info('Created Lifecycle property for database', {
            database: humanName,
            options: lifecycleOptions
          });
        } catch (e) {
          UL.warn('Could not create Lifecycle property proactively', {
            database: humanName,
            error: String(e)
          });
        }
      }
    }
    if (schemaResult.skippedDueToConfig?.length) {
      UL.warn('Schema deletions skipped by configuration', {
        database: humanName,
        skippedProperties: schemaResult.skippedDueToConfig.map(p => `${p.name}:${p.type}`)
      });
    }
    
    // Value sync
    if (!schemaResult.skipped?.includes('inaccessible')) {
      const backSync = syncCsvToNotion_(folder, ds, UL, { conflict: CONFIG.SYNC.CONFLICT_MODE });
      UL.info('✅ CSV → Notion sync completed', { database: humanName, ...backSync });
      
      // Markdown file sync (2-way sync for individual item files)
      if (CONFIG.SYNC.ENABLE_MARKDOWN_SYNC) {
        const mdSync = syncMarkdownFilesToNotion_(folder, ds, UL, { conflict: CONFIG.SYNC.CONFLICT_MODE });
        if (mdSync.created > 0 || mdSync.updated > 0) {
          UL.info('✅ Markdown files → Notion sync completed', { database: humanName, ...mdSync });
        }
      }
    } else {
      UL.warn('⚠️ Skipping CSV → Notion value sync - database inaccessible', { database: humanName });
    }

    // Export CSV
    const csvResult = writeDataSourceCsv_(folder, ds, UL);

    // Data integrity validation
    const validationResult = validateDataIntegrity_(folder, ds, csvResult, UL);
    if (validationResult && !validationResult.valid) {
      UL.warn('⚠️ Data integrity validation found issues', {
        database: humanName,
        validationResult
      });
    }

    // Workspace DB logging
    const status = csvResult.fileId ? 'Success' : 'Failed';
    logToNotionWorkspaceDb_(ds, csvResult.fileId, folder, csvResult.rowCount, status, UL);

    // Registry sheets
    dbRows.push([
      humanName,
      ds.id,
      ds.url || '',
      !!ds.archived,
      ds.created_time || '',
      ds.last_edited_time || '',
      csvResult.rowCount
    ]);

    const props = ds.properties || {};
    for (const [name, cfg] of Object.entries(props)) {
      propRows.push([ds.id, humanName, name, cfg.type || '', cfg.id || '', trunc(JSON.stringify(cfg))]);
    }

    const processingTime = Math.round((Date.now() - startTime) / 1000);
    UL.info('✅ Database processing completed', { 
      database: humanName, 
      dataSourceId: ds.id,
      databaseUrl: databaseUrl,
      processingTime: `${processingTime}s`,
      rowCount: csvResult.rowCount,
      validationPassed: validationResult?.valid !== false
    });
    
    // Track result for final summary
    UL.addDatabaseResult(humanName, ds.id, true, status, csvResult.rowCount, null);
    
    return { success: true, name: humanName, id: ds.id, rowCount: csvResult.rowCount, status, validationResult };
  } catch (e) {
    const processingTime = Math.round((Date.now() - startTime) / 1000);
    const errorMsg = String(e);
    const stack = e.stack || 'No stack trace available';
    const databaseUrl = getNotionDatabaseUrl_(ds.id);
    UL.error('❌ Database processing failed', { 
      database: humanName, 
      dataSourceId: ds.id,
      databaseUrl: databaseUrl,
      processingTime: `${processingTime}s`,
      error: errorMsg,
      stack
    });
    
    // Track failed result
    UL.addDatabaseResult(humanName, ds.id, false, 'Failed', null, errorMsg);
    
    return { success: false, name: humanName, id: ds.id, error: errorMsg };
  }
}

/* ============================== MAIN WORKFLOW ============================== */
function runDriveSheetsOnce_(UL) {
  const start = Date.now();

  const parent = resolveDriveParent_();
  const ss = getOrCreateRegistrySpreadsheet_(parent.id);
  UL.info('🚀 Starting synchronization run', { 
    parentFolderUrl: parent.url, 
    registrySheetUrl: ss.getUrl() 
  });

  const hits = searchAllDataSources_();
  UL.info('🔍 Discovered databases in workspace', { totalDatabases: hits.length });

  // Helper function to normalize database IDs (remove dashes for comparison)
  const normalizeDbId = (id) => (id || '').replace(/-/g, '').toLowerCase();
  
  // Normalize expected Agent-Tasks IDs for comparison
  const normalizedAgentTasksIds = CONFIG.AGENT_TASKS_DB_IDS.map(id => normalizeDbId(id));

  // Find Agent-Tasks database (check both possible IDs, then fallback to name match)
  // Note: AGENT_TASKS_PRIMARY (legacy) may return 404 - prioritize SECONDARY
  let agentTasksDb = null;
  const regularDbs = [...hits];
  const inaccessibleAgentTasksIds = [];
  
  // First, try to match by ID
  for (let i = 0; i < CONFIG.AGENT_TASKS_DB_IDS.length; i++) {
    const agentTasksId = CONFIG.AGENT_TASKS_DB_IDS[i];
    const normalizedExpectedId = normalizedAgentTasksIds[i];
    
    // Compare normalized IDs (handles both with/without dashes)
    const agentTasksIdx = hits.findIndex(ds => normalizeDbId(ds.id) === normalizedExpectedId);
    if (agentTasksIdx !== -1) {
      agentTasksDb = hits[agentTasksIdx];
      regularDbs.splice(regularDbs.findIndex(ds => normalizeDbId(ds.id) === normalizedExpectedId), 1);
      UL.info('⭐ Agent-Tasks database found by ID (priority processing)', { 
        agentTasksId: agentTasksId,
        foundId: hits[agentTasksIdx].id,
        normalizedMatch: true
      });
      break;
    } else {
      // Database ID not found in workspace search results
      // This could mean it's not shared with the integration or doesn't exist
      inaccessibleAgentTasksIds.push(agentTasksId);
    }
  }
  
  // Fallback: If not found by ID, try to match by database name
  if (!agentTasksDb) {
    const nameMatchIdx = hits.findIndex(ds => {
      // Check if database title matches Agent-Tasks name
      const title = dsTitle_(ds);
      return title === CONFIG.AGENT_TASKS_DB_NAME || title.toLowerCase() === CONFIG.AGENT_TASKS_DB_NAME.toLowerCase();
    });
    
    if (nameMatchIdx !== -1) {
      agentTasksDb = hits[nameMatchIdx];
      const foundId = hits[nameMatchIdx].id;
      regularDbs.splice(nameMatchIdx, 1);
      UL.info('⭐ Agent-Tasks database found by name (priority processing)', { 
        foundId: foundId,
        foundName: dsTitle_(hits[nameMatchIdx]),
        expectedIds: CONFIG.AGENT_TASKS_DB_IDS,
        note: 'Database ID in workspace differs from CONFIG - using name match'
      });
    }
  }
  
  // Only warn if database is truly not found (neither by ID nor by name)
  if (!agentTasksDb) {
    UL.warn('⚠️ Agent-Tasks database not found in workspace', { 
      expectedIds: CONFIG.AGENT_TASKS_DB_IDS,
      expectedName: CONFIG.AGENT_TASKS_DB_NAME,
      inaccessibleIds: inaccessibleAgentTasksIds,
      note: 'Legacy database (AGENT_TASKS_PRIMARY) may return 404 - this is expected if not shared with integration'
    });
  } else if (inaccessibleAgentTasksIds.length > 0) {
    UL.info('ℹ️ Some Agent-Tasks database IDs not accessible (expected for legacy database)', {
      accessibleId: agentTasksDb.id,
      accessibleName: dsTitle_(agentTasksDb),
      inaccessibleIds: inaccessibleAgentTasksIds
    });
  }

  const st = new State('drive_sheets');
  const begin = st.rp;
  
  const batchSize = agentTasksDb ? Math.min(CONFIG.BATCH_SIZE, regularDbs.length) : CONFIG.BATCH_SIZE;
  const count = Math.min(batchSize, Math.max(0, regularDbs.length - begin));
  
  UL.info('📋 Batch processing strategy', { 
    rotation: `${begin}/${regularDbs.length}`,
    batchSize: count,
    agentTasksIncluded: !!agentTasksDb,
    processingOrder: '1st from rotation → Agent-Tasks → Remaining'
  });

  const dbRows = [];
  const propRows = [];
  let successCount = 0;
  let failCount = 0;
  let processedDbs = [];
  let agentTasksProcessed = false;

  // Process databases in order: 1st from rotation, Agent-Tasks, then remaining
  for (let i = 0; i < count; i++) {
    if (Date.now() - start > CONFIG.MAX_RUNTIME_MS * 0.9) {
      UL.warn('⏱️ Approaching time limit - stopping early', { 
        processedThisRun: i, 
        plannedBatch: count,
        timeElapsed: Math.round((Date.now() - start) / 1000) + 's'
      });
      break;
    }

    const idx = begin + i;
    if (idx >= regularDbs.length) break;

    // Process 1st database from rotation
    if (i === 0) {
      const entry = regularDbs[idx];
      const ds = getDataSource_(entry.id, UL);
      if (!ds) { 
        failCount++; 
        continue; 
      }
      const result = processSingleDatabase_(ds, parent, ss, dbRows, propRows, UL);
      if (result.success) {
        successCount++;
        processedDbs.push(result.name);
      } else {
        failCount++;
      }
      
      // Now process Agent-Tasks as 2nd item (if found)
      if (agentTasksDb) {
        UL.info('⭐ Processing Agent-Tasks database (priority slot #2)');
        const agentDs = getDataSource_(agentTasksDb.id, UL);
        if (agentDs) {
          const agentResult = processSingleDatabase_(agentDs, parent, ss, dbRows, propRows, UL);
          if (agentResult.success) {
            successCount++;
            processedDbs.push(agentResult.name + ' [PRIORITY]');
            agentTasksProcessed = true;
            
            // MGM: Validate Single In Progress invariant after processing Agent-Tasks
            const invariantCheck = validateSingleInProgressInvariant_(agentTasksDb.id, UL);
            if (invariantCheck && invariantCheck.violated) {
              UL.warn('⚠️ Single In Progress invariant violation detected in Agent-Tasks', {
                violationCount: invariantCheck.count,
                taskIds: invariantCheck.taskIds.slice(0, 5)
              });
            }
            
            // Task Routing: Create trigger files for In Progress tasks
            try {
              routeTasksToAgents_(agentTasksDb.id, parent, UL);
            } catch (routingError) {
              UL.error('Failed to route tasks to agents', {
                error: String(routingError),
                stack: routingError.stack
              });
            }
          } else {
            failCount++;
          }
        } else {
          UL.error('❌ Failed to retrieve Agent-Tasks database', { agentTasksId: agentTasksDb.id });
          failCount++;
        }
      }
    } else {
      // Process remaining databases from rotation
      const entry = regularDbs[idx];
      const ds = getDataSource_(entry.id, UL);
      if (!ds) { 
        failCount++; 
        continue; 
      }
      const result = processSingleDatabase_(ds, parent, ss, dbRows, propRows, UL);
      if (result.success) {
        successCount++;
        processedDbs.push(result.name);
      } else {
        failCount++;
      }
    }
  }

  // Update registry sheets
  if (dbRows.length) { 
    writeDatabasesSheet_(ss, dbRows); 
    UL.info('📊 Updated Databases sheet', { rows: dbRows.length }); 
  }
  if (propRows.length) { 
    writePropertiesSheet_(ss, propRows); 
    UL.info('📊 Updated Properties sheet', { rows: propRows.length }); 
  }
  SpreadsheetApp.flush();

  // Update rotation pointer
  let np = begin + count;
  if (np >= regularDbs.length) { 
    np = 0; 
    st.cycleInc(); 
  }
  st.rp = np;

  const summary = {
    processed: successCount,
    failed: failCount,
    total: hits.length,
    rotation: `${np}/${regularDbs.length}`,
    parentFolder: parent.url,
    sheetId: ss.getId(),
    sheetUrl: ss.getUrl(),
    agentTasksProcessed: agentTasksProcessed,
    processedDatabases: processedDbs.join(', '),
    executionTime: Math.round((Date.now() - start) / 1000) + 's'
  };
  
  UL.info('🎉 Synchronization run completed', summary);
  return summary;
}

/* ============================== ENTRYPOINTS ============================== */
function manualRunDriveSheets() {
  const UL = new UnifiedLoggerGAS(CONFIG.LOGGING);
  UL.init();
  const lock = LockService.getScriptLock();
  const lockWaitMs = CONFIG.SYNC.LOCK_WAIT_MS || 8000;
  let lockAcquired = false;

  const finalizeSafe = (success, err, info) => {
    try {
      UL.finalize(success, err, info);
    } catch (finalErr) {
      console.error('Failed to finalize logger:', String(finalErr));
    }
  };

  try {
    UL.info('🔒 Attempting to obtain DriveSheets script lock', { waitMs: lockWaitMs });
    lockAcquired = lock.tryLock(lockWaitMs);
  } catch (lockErr) {
    UL.warn('⚠️ Unable to obtain DriveSheets script lock', {
      waitMs: lockWaitMs,
      error: String(lockErr)
    });
  }

  if (!lockAcquired) {
    UL.warn('DriveSheetsSync: another run is already in progress. Aborting this trigger execution.', { waitMs: lockWaitMs });
    finalizeSafe(true, null, { skipped: 'lock_not_acquired', waitMs: lockWaitMs });
    return;
  }

  try {
    try {
      maybeEnsureArchiveFolders_(UL);
    } catch (archiveAuditError) {
      UL.warn('Archive audit failed (non-blocking)', { error: String(archiveAuditError) });
    }
    UL.info('🚀 Initiating two-way sync workflow');
    const info = runDriveSheetsOnce_(UL);
    UL.info('✅ Sync workflow completed successfully', info);
    finalizeSafe(true, null, info);
  } catch (e) {
    const errorMsg = String(e);
    const stack = e.stack || 'No stack trace available';
    UL.error('❌ Sync workflow failed with exception', { 
      error: errorMsg, 
      stack
    });
    finalizeSafe(false, e, null);
    throw e;
  } finally {
    if (lockAcquired) {
      try {
        lock.releaseLock();
      } catch (releaseErr) {
        UL.warn('⚠️ Failed to release DriveSheets script lock', { error: String(releaseErr) });
      }
    }
  }
}
/**
 * Pause all time-based triggers for DriveSheetsSync.
 */
function pauseDriveSheetsSyncTriggers() {
  ScriptApp.getProjectTriggers().forEach(t => {
    try {
      if (t.getHandlerFunction && t.getHandlerFunction() === 'manualRunDriveSheets') {
        ScriptApp.deleteTrigger(t);
      }
    } catch (e) {
      console.warn('[WARN] Failed to inspect/delete trigger', { error: String(e) });
    }
  });
}

function setupTimeTriggerEvery10m() {
  pauseDriveSheetsSyncTriggers();
  ScriptApp.newTrigger('manualRunDriveSheets').timeBased().everyMinutes(10).create();
}

/**
 * Setup time-based trigger to run every 30 minutes (safer default for production)
 * This reduces the risk of overlapping runs while still maintaining regular sync
 */
function setupTimeTriggerEvery30m() {
  pauseDriveSheetsSyncTriggers();
  ScriptApp.newTrigger('manualRunDriveSheets').timeBased().everyMinutes(30).create();
}
function resetDriveSheetsState() {
  PROPS.deleteProperty(CONFIG.STATE_KEY_PREFIX + 'drive_sheets');
}

/**
 * Setup function to configure required script properties
 * Run this function once to set up the script with required configuration
 *
 * @param {string} notionApiKey - Your Notion API key (starts with 'secret_' or 'ntn_')
 * @param {string} workspaceDatabasesFolderId - (Optional) Google Drive folder ID for workspace databases
 * @param {string} workspaceDatabasesUrl - (Optional) Google Drive folder URL for workspace databases
 * @param {string} clientId - (Optional) Client identifier (e.g., 'seren-media-internal', 'vibe-vessel', 'ocean-frontiers')
 * @param {string} clientEmail - (Optional) Google account email (auto-detected if not provided)
 */
function setupScriptProperties(notionApiKey, workspaceDatabasesFolderId = null, workspaceDatabasesUrl = null, clientId = null, clientEmail = null) {
  if (!notionApiKey || typeof notionApiKey !== 'string' || !notionApiKey.trim()) {
    throw new Error('notionApiKey is required and must be a non-empty string');
  }

  // Clean and validate API key
  const cleanedKey = notionApiKey.trim().replace(/^[\'"\s]+|[\'"\s]+$/g, '');
  if (!cleanedKey.startsWith('secret_') && !cleanedKey.startsWith('ntn_')) {
    console.warn('[WARN] Notion API key should start with "secret_" or "ntn_". Proceeding anyway...');
  }

  // Set required properties
  PROPS.setProperty('NOTION_API_KEY', cleanedKey);
  console.log('✅ Set NOTION_API_KEY');

  // Set optional properties if provided
  if (workspaceDatabasesFolderId) {
    PROPS.setProperty('WORKSPACE_DATABASES_FOLDER_ID', workspaceDatabasesFolderId.trim());
    console.log('✅ Set WORKSPACE_DATABASES_FOLDER_ID:', workspaceDatabasesFolderId);
  }

  if (workspaceDatabasesUrl) {
    PROPS.setProperty('WORKSPACE_DATABASES_URL', workspaceDatabasesUrl.trim());
    console.log('✅ Set WORKSPACE_DATABASES_URL:', workspaceDatabasesUrl);
  }

  // Set client context properties (Multi-Account Google Drive Integration)
  if (clientId) {
    PROPS.setProperty('CLIENT_ID', clientId.trim());
    console.log('✅ Set CLIENT_ID:', clientId);
  }

  if (clientEmail) {
    PROPS.setProperty('CLIENT_EMAIL', clientEmail.trim());
    console.log('✅ Set CLIENT_EMAIL:', clientEmail);
  } else {
    // Auto-detect from active user
    try {
      const detectedEmail = Session.getActiveUser().getEmail();
      if (detectedEmail) {
        PROPS.setProperty('CLIENT_EMAIL', detectedEmail);
        console.log('✅ Auto-detected CLIENT_EMAIL:', detectedEmail);
      }
    } catch (e) {
      console.warn('[WARN] Could not auto-detect client email:', e.message);
    }
  }

  // Display current configuration (with API key redacted)
  console.log('\n📋 Current Script Properties:');
  console.log('  NOTION_API_KEY:', cleanedKey ? '[SET]' : '[NOT SET]');
  console.log('  WORKSPACE_DATABASES_FOLDER_ID:', PROPS.getProperty('WORKSPACE_DATABASES_FOLDER_ID') || '[NOT SET]');
  console.log('  WORKSPACE_DATABASES_URL:', PROPS.getProperty('WORKSPACE_DATABASES_URL') || '[NOT SET]');
  console.log('  CLIENT_ID:', PROPS.getProperty('CLIENT_ID') || '[NOT SET - Will auto-detect]');
  console.log('  CLIENT_EMAIL:', PROPS.getProperty('CLIENT_EMAIL') || '[NOT SET - Will auto-detect]');
  console.log('  LOG_SCRIPT_NAME:', PROPS.getProperty('LOG_SCRIPT_NAME') || CONFIG.LOGGING.DEFAULT_SCRIPT_NAME);
  console.log('  LOG_ENV:', PROPS.getProperty('LOG_ENV') || CONFIG.LOGGING.DEFAULT_ENV);

  // Display client context info
  const detectedContext = getClientContext();
  const detectedPath = getLocalDrivePath();
  console.log('\n📁 Client Context:');
  console.log('  Detected Client:', detectedContext || '[UNKNOWN]');
  console.log('  Client Name:', getClientName());
  console.log('  Local Drive Path:', detectedPath || '[NOT MAPPED]');

  console.log('\n✅ Setup complete! You can now run manualRunDriveSheets()');
}


/**
 * Check script configuration and display current settings
 * Useful for debugging configuration issues
 */
function checkScriptConfiguration() {
  console.log('📋 Script Configuration Check:\n');

  const notionKey = PROPS.getProperty('NOTION_API_KEY');
  console.log('  NOTION_API_KEY:', notionKey ? '[SET - ' + notionKey.substring(0, 10) + '...]' : '[NOT SET - REQUIRED]');

  const workspaceFolderId = PROPS.getProperty('WORKSPACE_DATABASES_FOLDER_ID');
  console.log('  WORKSPACE_DATABASES_FOLDER_ID:', workspaceFolderId || '[NOT SET - Will auto-detect]');

  const workspaceUrl = PROPS.getProperty('WORKSPACE_DATABASES_URL');
  console.log('  WORKSPACE_DATABASES_URL:', workspaceUrl || '[NOT SET - Will auto-detect]');

  const logScriptName = PROPS.getProperty('LOG_SCRIPT_NAME');
  console.log('  LOG_SCRIPT_NAME:', logScriptName || CONFIG.LOGGING.DEFAULT_SCRIPT_NAME + ' (default)');

  const logEnv = PROPS.getProperty('LOG_ENV');
  console.log('  LOG_ENV:', logEnv || CONFIG.LOGGING.DEFAULT_ENV + ' (default)');

  const logRootFolderId = PROPS.getProperty('LOG_ROOT_FOLDER_ID');
  console.log('  LOG_ROOT_FOLDER_ID:', logRootFolderId || '[NOT SET - Will use canonical path]');

  // Client context properties (Multi-Account Google Drive Integration)
  const clientIdProp = PROPS.getProperty('CLIENT_ID');
  console.log('  CLIENT_ID:', clientIdProp || '[NOT SET - Will auto-detect]');

  const clientEmailProp = PROPS.getProperty('CLIENT_EMAIL');
  console.log('  CLIENT_EMAIL:', clientEmailProp || '[NOT SET - Will auto-detect]');

  console.log('\n📊 Configuration Status:');
  if (!notionKey) {
    console.error('  ❌ NOTION_API_KEY is missing - REQUIRED');
    console.log('     Run: setupScriptProperties("your-notion-api-key")');
  } else {
    console.log('  ✅ NOTION_API_KEY is set');
  }

  if (!workspaceFolderId && !workspaceUrl) {
    console.log('  ⚠️  WORKSPACE_DATABASES folder not set - will auto-detect or create fallback');
  } else {
    console.log('  ✅ WORKSPACE_DATABASES folder configured');
  }

  // Display client context detection results
  console.log('\n📁 Client Context Detection:');
  const detectedContext = getClientContext();
  const detectedPath = getLocalDrivePath();
  const detectedEmail = getClientEmail();

  console.log('  Detected Client Context:', detectedContext || '[UNKNOWN]');
  console.log('  Client Name:', getClientName());
  console.log('  Client Email:', detectedEmail || '[UNKNOWN]');
  console.log('  Local Drive Path:', detectedPath || '[NOT MAPPED]');

  if (detectedContext) {
    console.log('  ✅ Client context detected successfully');
  } else {
    console.log('  ⚠️  Client context not detected - folder registration will be skipped');
    console.log('     Set CLIENT_ID or CLIENT_EMAIL in script properties, or run from a recognized account');
  }
}

/* ============================== MAINTENANCE & CLEANUP UTILITIES ============================== */

/**
 * Runs a comprehensive cleanup of the workspace folder to fix issues from race conditions.
 * This function can be run manually to consolidate duplicates and create missing structure.
 * @param {boolean} dryRun - If true, only reports issues without making changes
 * @returns {Object} Summary of cleanup actions taken or needed
 */
function runWorkspaceCleanup(dryRun = true) {
  const UL = new UnifiedLoggerGAS(CONFIG.LOGGING);
  UL.init();

  console.log(`\n${'='.repeat(70)}`);
  console.log(`DRIVESHEETSSYNC WORKSPACE CLEANUP ${dryRun ? '(DRY RUN)' : '(LIVE)'}`);
  console.log(`${'='.repeat(70)}\n`);

  const summary = {
    dryRun: dryRun,
    duplicateFolders: { found: 0, consolidated: 0, details: [] },
    duplicateFiles: { found: 0, consolidated: 0, details: [] },
    missingArchives: { found: 0, created: 0, details: [] },
    orphanedItems: { found: 0, archived: 0, details: [] },
    errors: []
  };

  try {
    // Get workspace folder
    const folderId = PROPS.getProperty('WORKSPACE_DATABASES_FOLDER_ID');
    if (!folderId) {
      const msg = 'WORKSPACE_DATABASES_FOLDER_ID not set. Run the sync first to initialize.';
      console.error(msg);
      summary.errors.push(msg);
      return summary;
    }

    const parentFolder = DriveApp.getFolderById(folderId);
    console.log(`📁 Scanning workspace folder: ${parentFolder.getName()}`);
    console.log(`   URL: ${parentFolder.getUrl()}\n`);

    // Phase 1: Identify all folders and group by database ID
    console.log('Phase 1: Analyzing folder structure...');
    const allFolders = parentFolder.getFolders();
    const foldersByDbId = new Map();
    const orphanedFolders = [];

    while (allFolders.hasNext()) {
      const folder = allFolders.next();
      const name = folder.getName();

      // Extract database ID from folder name (UUID format at end)
      const uuidMatch = name.match(/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})(?:\s*\(\d+\))?$/i);

      if (uuidMatch) {
        const dbId = uuidMatch[1];
        if (!foldersByDbId.has(dbId)) {
          foldersByDbId.set(dbId, []);
        }
        foldersByDbId.get(dbId).push({
          folder: folder,
          name: name,
          isDuplicate: /\s*\(\d+\)\s*$/.test(name),
          lastUpdated: folder.getLastUpdated()
        });
      } else {
        // Folder doesn't match expected pattern
        orphanedFolders.push({ folder: folder, name: name });
      }
    }

    console.log(`   Found ${foldersByDbId.size} unique database IDs`);
    console.log(`   Found ${orphanedFolders.length} folders not matching DB pattern\n`);

    // Phase 2: Handle duplicate folders
    console.log('Phase 2: Checking for duplicate folders...');
    for (const [dbId, folders] of foldersByDbId.entries()) {
      if (folders.length > 1) {
        summary.duplicateFolders.found++;

        // Sort to find the primary (canonical) folder
        folders.sort((a, b) => {
          if (!a.isDuplicate && b.isDuplicate) return -1;
          if (a.isDuplicate && !b.isDuplicate) return 1;
          return b.lastUpdated.getTime() - a.lastUpdated.getTime();
        });

        const primary = folders[0];
        const duplicates = folders.slice(1);

        summary.duplicateFolders.details.push({
          dbId: dbId,
          primary: primary.name,
          duplicates: duplicates.map(f => f.name)
        });

        console.log(`   ⚠️  Duplicates for ${dbId}:`);
        console.log(`      Primary: ${primary.name}`);
        console.log(`      Duplicates: ${duplicates.map(f => f.name).join(', ')}`);

        if (!dryRun) {
          // Consolidate files from duplicates to primary
          for (const dup of duplicates) {
            try {
              consolidateFolderContents_(dup.folder, primary.folder, UL);
              // Move duplicate folder to trash after consolidation
              dup.folder.setTrashed(true);
              summary.duplicateFolders.consolidated++;
              console.log(`      ✅ Consolidated and trashed: ${dup.name}`);
            } catch (e) {
              summary.errors.push(`Failed to consolidate ${dup.name}: ${e}`);
              console.error(`      ❌ Failed to consolidate: ${dup.name}: ${e}`);
            }
          }
        }
      }
    }

    // Phase 3: Check for missing archive folders and duplicate CSV files
    console.log('\nPhase 3: Checking archive folders and CSV files...');
    for (const [dbId, folders] of foldersByDbId.entries()) {
      const primary = folders[0].folder;

      // Check for .archive folder
      const archiveIt = primary.getFoldersByName('.archive');
      if (!archiveIt.hasNext()) {
        summary.missingArchives.found++;
        summary.missingArchives.details.push({
          dbId: dbId,
          folderName: folders[0].name
        });

        if (!dryRun) {
          try {
            primary.createFolder('.archive');
            summary.missingArchives.created++;
            console.log(`   ✅ Created .archive folder in: ${folders[0].name}`);
          } catch (e) {
            summary.errors.push(`Failed to create .archive in ${folders[0].name}: ${e}`);
          }
        } else {
          console.log(`   📁 Missing .archive in: ${folders[0].name}`);
        }
      }

      // Check for duplicate CSV files
      const csvFiles = [];
      const allFiles = primary.getFiles();
      while (allFiles.hasNext()) {
        const file = allFiles.next();
        const fileName = file.getName();
        if (fileName.endsWith('.csv') && !fileName.startsWith('_v')) {
          csvFiles.push({
            file: file,
            name: fileName,
            isDuplicate: /\s*\(\d+\)\.csv$/.test(fileName),
            size: file.getSize(),
            lastUpdated: file.getLastUpdated()
          });
        }
      }

      // Group CSV files by base name
      const csvByBase = new Map();
      for (const csv of csvFiles) {
        const baseName = csv.name.replace(/\s*\(\d+\)\.csv$/, '.csv');
        if (!csvByBase.has(baseName)) {
          csvByBase.set(baseName, []);
        }
        csvByBase.get(baseName).push(csv);
      }

      // Find and consolidate duplicate CSVs
      for (const [baseName, files] of csvByBase.entries()) {
        if (files.length > 1) {
          summary.duplicateFiles.found++;

          files.sort((a, b) => {
            if (!a.isDuplicate && b.isDuplicate) return -1;
            if (a.isDuplicate && !b.isDuplicate) return 1;
            if (a.size !== b.size) return b.size - a.size;
            return b.lastUpdated.getTime() - a.lastUpdated.getTime();
          });

          const primaryCsv = files[0];
          const duplicateCsvs = files.slice(1);

          summary.duplicateFiles.details.push({
            baseName: baseName,
            primary: primaryCsv.name,
            duplicates: duplicateCsvs.map(f => f.name)
          });

          if (!dryRun) {
            // Archive duplicate CSVs (move to .archive folder)
            const archiveFolder = primary.getFoldersByName('.archive').hasNext()
              ? primary.getFoldersByName('.archive').next()
              : primary.createFolder('.archive');

            for (const dupCsv of duplicateCsvs) {
              try {
                dupCsv.file.moveTo(archiveFolder);
                summary.duplicateFiles.consolidated++;
                console.log(`   ✅ Archived duplicate: ${dupCsv.name}`);
              } catch (e) {
                summary.errors.push(`Failed to archive ${dupCsv.name}: ${e}`);
              }
            }

            // Rename primary to canonical name if needed
            if (primaryCsv.isDuplicate) {
              try {
                primaryCsv.file.setName(baseName);
                console.log(`   ✅ Renamed ${primaryCsv.name} to ${baseName}`);
              } catch (e) {
                summary.errors.push(`Failed to rename ${primaryCsv.name}: ${e}`);
              }
            }
          }
        }
      }
    }

    // Phase 4: Report orphaned folders
    if (orphanedFolders.length > 0) {
      console.log('\nPhase 4: Orphaned folders (not matching DB pattern)...');
      for (const orphan of orphanedFolders) {
        summary.orphanedItems.found++;
        summary.orphanedItems.details.push(orphan.name);
        console.log(`   ⚠️  Orphaned: ${orphan.name}`);
      }
    }

  } catch (e) {
    summary.errors.push(`Cleanup failed: ${String(e)}`);
    UL.error('Cleanup failed', { error: String(e), stack: e.stack });
  }

  // Print summary
  console.log(`\n${'='.repeat(70)}`);
  console.log('CLEANUP SUMMARY');
  console.log(`${'='.repeat(70)}`);
  console.log(`Mode: ${dryRun ? 'DRY RUN (no changes made)' : 'LIVE (changes applied)'}`);
  console.log(`Duplicate folders: ${summary.duplicateFolders.found} found, ${summary.duplicateFolders.consolidated} consolidated`);
  console.log(`Duplicate files: ${summary.duplicateFiles.found} found, ${summary.duplicateFiles.consolidated} archived`);
  console.log(`Missing .archive folders: ${summary.missingArchives.found} found, ${summary.missingArchives.created} created`);
  console.log(`Orphaned items: ${summary.orphanedItems.found} found`);
  console.log(`Errors: ${summary.errors.length}`);

  if (summary.errors.length > 0) {
    console.log('\nErrors:');
    summary.errors.forEach((e, i) => console.log(`  ${i + 1}. ${e}`));
  }

  if (dryRun && (summary.duplicateFolders.found > 0 || summary.duplicateFiles.found > 0 || summary.missingArchives.found > 0)) {
    console.log('\n💡 To apply fixes, run: runWorkspaceCleanup(false)');
  }

  UL.finalize(summary.errors.length === 0, null, summary);
  return summary;
}

/**
 * Ensures every workspace database folder has a .archive subfolder.
 * Lightweight maintenance task to keep versioning structure consistent.
 * @param {Object} UL - Unified logger instance
 * @returns {Object} Summary of archive folder audit
 */
function ensureArchiveFoldersInWorkspace_(UL) {
  const summary = {
    scanned: 0,
    missing: 0,
    created: 0,
    errors: 0,
    skipped: false
  };

  const folderId = PROPS.getProperty('WORKSPACE_DATABASES_FOLDER_ID');
  if (!folderId) {
    UL?.warn?.('Archive audit skipped: WORKSPACE_DATABASES_FOLDER_ID not set');
    summary.skipped = true;
    return summary;
  }

  const parentFolder = DriveApp.getFolderById(folderId);
  const allFolders = parentFolder.getFolders();
  const dbIdPattern = /([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})(?:\s*\(\d+\))?$/i;

  while (allFolders.hasNext()) {
    const folder = allFolders.next();
    const name = folder.getName();
    if (!dbIdPattern.test(name)) {
      continue;
    }

    summary.scanned++;
    const archiveIt = folder.getFoldersByName('.archive');
    if (!archiveIt.hasNext()) {
      summary.missing++;
      try {
        folder.createFolder('.archive');
        summary.created++;
      } catch (e) {
        summary.errors++;
        UL?.warn?.('Failed to create .archive folder', {
          folderName: name,
          error: String(e)
        });
      }
    }
  }

  UL?.info?.('Archive folder audit complete', summary);
  return summary;
}

/**
 * Runs archive folder audit on an interval to prevent missing .archive folders.
 * Controlled via script properties:
 * - ENABLE_ARCHIVE_AUDIT (default true)
 * - ARCHIVE_AUDIT_INTERVAL_HOURS (default 24)
 */
function maybeEnsureArchiveFolders_(UL) {
  const enabledProp = PROPS.getProperty('ENABLE_ARCHIVE_AUDIT');
  const enabled = enabledProp === null || String(enabledProp).toLowerCase() !== 'false';
  if (!enabled) {
    UL?.debug?.('Archive audit disabled via script property');
    return;
  }

  const intervalHours = Number(PROPS.getProperty('ARCHIVE_AUDIT_INTERVAL_HOURS') || 24);
  const lastTs = Number(PROPS.getProperty('ARCHIVE_AUDIT_LAST_TS') || 0);
  const now = Date.now();
  const intervalMs = Math.max(1, intervalHours) * 60 * 60 * 1000;

  if (lastTs && (now - lastTs) < intervalMs) {
    UL?.debug?.('Archive audit skipped (interval not reached)', {
      hoursSinceLast: Math.round((now - lastTs) / 3600000)
    });
    return;
  }

  const summary = ensureArchiveFoldersInWorkspace_(UL);
  if (summary && !summary.skipped) {
    PROPS.setProperty('ARCHIVE_AUDIT_LAST_TS', String(now));
  }
}

/**
 * Consolidates contents from a duplicate folder into the primary folder.
 * @param {Folder} sourceFolder - The duplicate folder to consolidate from
 * @param {Folder} targetFolder - The primary folder to consolidate into
 * @param {Object} UL - Unified logger instance
 */
function consolidateFolderContents_(sourceFolder, targetFolder, UL) {
  // Move files
  const files = sourceFolder.getFiles();
  while (files.hasNext()) {
    const file = files.next();
    const fileName = file.getName();

    // Check if file already exists in target
    const existingIt = targetFolder.getFilesByName(fileName);
    if (existingIt.hasNext()) {
      // File exists - compare and keep newer/larger one
      const existing = existingIt.next();
      const existingTime = existing.getLastUpdated();
      const sourceTime = file.getLastUpdated();

      if (sourceTime > existingTime || file.getSize() > existing.getSize()) {
        // Source is newer/larger - move to archive, replace with source
        const archiveFolder = targetFolder.getFoldersByName('.archive').hasNext()
          ? targetFolder.getFoldersByName('.archive').next()
          : targetFolder.createFolder('.archive');
        existing.moveTo(archiveFolder);
        file.moveTo(targetFolder);
        UL?.info?.('Replaced older file during consolidation', { fileName });
      } else {
        // Existing is better - just archive the source file
        file.setTrashed(true);
      }
    } else {
      // File doesn't exist in target - just move it
      file.moveTo(targetFolder);
    }
  }

  // Move subfolders (mainly .archive folders)
  const subfolders = sourceFolder.getFolders();
  while (subfolders.hasNext()) {
    const subfolder = subfolders.next();
    const subfolderName = subfolder.getName();

    if (subfolderName === '.archive') {
      // Merge archive contents
      const targetArchive = targetFolder.getFoldersByName('.archive').hasNext()
        ? targetFolder.getFoldersByName('.archive').next()
        : targetFolder.createFolder('.archive');

      const archiveFiles = subfolder.getFiles();
      while (archiveFiles.hasNext()) {
        archiveFiles.next().moveTo(targetArchive);
      }
      subfolder.setTrashed(true);
    } else {
      // Move other subfolders
      // Note: DriveApp doesn't have moveTo for folders, so we skip non-archive folders
      UL?.warn?.('Skipping non-archive subfolder during consolidation', { name: subfolderName });
    }
  }
}

/**
 * Generates a report of the current workspace state without making changes.
 * Alias for runWorkspaceCleanup(true) for convenience.
 */
function auditWorkspaceState() {
  return runWorkspaceCleanup(true);
}

/**
 * Applies cleanup fixes to the workspace.
 * Alias for runWorkspaceCleanup(false) for convenience.
 */
function applyWorkspaceCleanup() {
  return runWorkspaceCleanup(false);
}

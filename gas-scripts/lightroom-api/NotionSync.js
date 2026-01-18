/**
 * Lightroom Notion Sync
 * Sync Lightroom assets to Notion Photos Library database
 *
 * VERSION: 1.0.0
 * CREATED: 2026-01-18
 * AUTHOR: Claude Code Agent
 *
 * This module synchronizes Lightroom assets to a Notion database,
 * following the established patterns from DriveSheetsSync and
 * WorkspaceEventsSync projects.
 *
 * Features:
 * - Upsert operations (create or update)
 * - Loop-guard properties to prevent automation loops
 * - Incremental sync support
 * - Comprehensive logging
 */

/**
 * Lightroom Notion Sync module
 */
var LightroomNotionSync = (function() {
  'use strict';

  var NOTION_API_BASE = 'https://api.notion.com/v1/';

  // Database ID cache
  var _dbIdCache = {};
  var _dbSchemaCache = {};

  /**
   * Get Notion API headers
   * @private
   */
  function headers_() {
    var cfg = LightroomConfig.getConfig();
    return {
      'Authorization': 'Bearer ' + cfg.notionToken,
      'Notion-Version': cfg.notionVersion,
      'Content-Type': 'application/json'
    };
  }

  /**
   * Make Notion API request
   * @private
   */
  function notionRequest_(method, path, body) {
    var url = NOTION_API_BASE + path.replace(/^\//, '');
    var params = {
      method: method,
      headers: headers_(),
      muteHttpExceptions: true
    };
    if (body !== undefined) {
      params.payload = JSON.stringify(body);
    }

    var resp = UrlFetchApp.fetch(url, params);
    var code = resp.getResponseCode();
    var text = resp.getContentText();

    if (code >= 200 && code < 300) {
      return text ? JSON.parse(text) : {};
    }
    throw new Error('Notion API error ' + code + ': ' + text);
  }

  /**
   * Discover database ID by name
   * @param {string} dbName - Database name to search for
   * @returns {string|null} Database ID or null
   */
  function discoverDatabaseByName(dbName) {
    if (!dbName) return null;
    if (_dbIdCache[dbName]) return _dbIdCache[dbName];

    var scriptProps = PropertiesService.getScriptProperties();
    var cacheKey = 'DB_CACHE_' + dbName.replace(/[^a-zA-Z0-9]/g, '_').toUpperCase();
    var cached = scriptProps.getProperty(cacheKey);
    if (cached) {
      _dbIdCache[dbName] = cached;
      return cached;
    }

    var cursor = null;
    for (var i = 0; i < 10; i++) {
      var body = {
        query: dbName,
        page_size: 100,
        filter: { property: 'object', value: 'data_source' }
      };
      if (cursor) body.start_cursor = cursor;

      var res = notionRequest_('POST', 'search', body);
      var results = res.results || [];

      for (var r = 0; r < results.length; r++) {
        var ds = results[r];
        var title = '';
        if (ds.title && ds.title.length) title = ds.title[0].plain_text || '';
        if (!title && ds.name) title = ds.name;

        if (title && title.toLowerCase() === dbName.toLowerCase()) {
          var found = (ds.id || '').replace(/-/g, '');
          if (found) {
            scriptProps.setProperty(cacheKey, found);
            _dbIdCache[dbName] = found;
            return found;
          }
        }
      }

      if (!res.has_more) break;
      cursor = res.next_cursor;
    }

    return null;
  }

  /**
   * Ensure loop-guard properties exist on database
   * @private
   */
  function ensureLoopGuardProperties_(databaseId) {
    if (!databaseId) return false;
    var cfg = LightroomConfig.getConfig();

    try {
      var db = notionRequest_('GET', 'databases/' + databaseId);
      var props = db.properties || {};
      var toAdd = {};

      if (!props[cfg.serenAutomationSourceProperty]) {
        toAdd[cfg.serenAutomationSourceProperty] = { rich_text: {} };
      }
      if (!props[cfg.serenAutomationEventIdProperty]) {
        toAdd[cfg.serenAutomationEventIdProperty] = { rich_text: {} };
      }
      if (!props[cfg.serenAutomationNodeIdProperty]) {
        toAdd[cfg.serenAutomationNodeIdProperty] = { rich_text: {} };
      }

      if (Object.keys(toAdd).length) {
        notionRequest_('PATCH', 'databases/' + databaseId, { properties: toAdd });
      }
      return true;
    } catch (e) {
      console.warn('[NotionSync] Could not ensure loop-guard properties: ' + e.message);
      return false;
    }
  }

  /**
   * Apply loop-guard properties to page properties
   * @private
   */
  function applyLoopGuardProps_(properties, assetId) {
    var cfg = LightroomConfig.getConfig();
    var p = properties || {};

    try {
      p[cfg.serenAutomationSourceProperty] = {
        rich_text: [{ text: { content: cfg.automationSourceValue } }]
      };
      p[cfg.serenAutomationNodeIdProperty] = {
        rich_text: [{ text: { content: cfg.nodeId } }]
      };
      if (assetId) {
        p[cfg.serenAutomationEventIdProperty] = {
          rich_text: [{ text: { content: String(assetId) } }]
        };
      }
    } catch (e) {
      // Non-fatal
    }
    return p;
  }

  /**
   * Find existing page by Lightroom Asset ID
   * @private
   */
  function findPageByAssetId_(databaseId, assetId) {
    if (!databaseId || !assetId) return null;

    try {
      var query = {
        filter: {
          property: 'Lightroom-Asset-ID',
          rich_text: { equals: assetId }
        },
        page_size: 1
      };
      var res = notionRequest_('POST', 'databases/' + databaseId + '/query', query);
      if (res.results && res.results.length > 0) {
        return res.results[0].id;
      }
    } catch (e) {
      console.warn('[NotionSync] Could not find page by asset ID: ' + e.message);
    }
    return null;
  }

  /**
   * Map Lightroom asset to Notion properties
   * @param {Object} asset - Lightroom asset object
   * @returns {Object} Notion properties
   */
  function mapAssetToNotionProperties(asset) {
    var payload = asset.payload || {};
    var importSource = payload.importSource || {};
    var captureDate = payload.captureDate || '';
    var location = payload.location || {};

    // Build properties object
    var properties = {
      // Title (Name property)
      'Name': {
        title: [{ text: { content: importSource.fileName || asset.id || 'Untitled' } }]
      },
      // Lightroom Asset ID
      'Lightroom-Asset-ID': {
        rich_text: [{ text: { content: asset.id || '' } }]
      },
      // File type
      'File Type': {
        rich_text: [{ text: { content: payload.subtype || '' } }]
      },
      // Original filename
      'Original Filename': {
        rich_text: [{ text: { content: importSource.fileName || '' } }]
      },
      // Import date
      'Import Date': {
        rich_text: [{ text: { content: importSource.importTimestamp || '' } }]
      }
    };

    // Add capture date if available
    if (captureDate) {
      properties['Capture Date'] = {
        date: { start: captureDate.split('T')[0] }
      };
    }

    // Add dimensions if available
    if (payload.develop && payload.develop.croppedWidth) {
      properties['Width'] = {
        number: payload.develop.croppedWidth
      };
      properties['Height'] = {
        number: payload.develop.croppedHeight
      };
    }

    // Add GPS coordinates if available
    if (location.latitude && location.longitude) {
      properties['Location'] = {
        rich_text: [{ text: { content: location.latitude + ', ' + location.longitude } }]
      };
    }

    // Add camera info if available
    if (payload.exif) {
      var exif = payload.exif;
      if (exif.make || exif.model) {
        properties['Camera'] = {
          rich_text: [{ text: { content: (exif.make || '') + ' ' + (exif.model || '') } }]
        };
      }
    }

    return properties;
  }

  /**
   * Upsert a Lightroom asset to Notion
   * @param {string} databaseId - Notion database ID
   * @param {Object} asset - Lightroom asset object
   * @returns {Object} Result with success status
   */
  function upsertAsset(databaseId, asset) {
    if (!databaseId) return { ok: false, error: 'No database ID' };
    if (!asset || !asset.id) return { ok: false, error: 'No asset provided' };

    // Ensure loop-guard properties exist
    var canTag = ensureLoopGuardProperties_(databaseId);

    // Find existing page
    var pageId = findPageByAssetId_(databaseId, asset.id);

    // Map asset to properties
    var properties = mapAssetToNotionProperties(asset);
    if (canTag) {
      properties = applyLoopGuardProps_(properties, asset.id);
    }

    try {
      if (pageId) {
        // Update existing page
        notionRequest_('PATCH', 'pages/' + pageId, { properties: properties });
        return { ok: true, pageId: pageId, action: 'updated' };
      } else {
        // Create new page
        var created = notionRequest_('POST', 'pages', {
          parent: { database_id: databaseId },
          properties: properties
        });
        return { ok: true, pageId: created.id, action: 'created' };
      }
    } catch (e) {
      return { ok: false, error: e.message || String(e) };
    }
  }

  /**
   * Sync all assets from Lightroom catalog to Notion
   * @param {Object} options - Sync options
   * @param {number} options.limit - Max assets to sync (default: all)
   * @param {boolean} options.dryRun - If true, don't actually sync
   * @returns {Object} Sync results
   */
  function syncAssets(options) {
    options = options || {};
    var cfg = LightroomConfig.getConfig();

    // Find Photos Library database
    var databaseId = discoverDatabaseByName(cfg.photosLibraryDbName);
    if (!databaseId) {
      return {
        success: false,
        error: 'Could not find database: ' + cfg.photosLibraryDbName
      };
    }

    // Get Lightroom catalog
    var catalog;
    try {
      catalog = LightroomClient.getCatalog();
    } catch (e) {
      return {
        success: false,
        error: 'Could not get Lightroom catalog: ' + e.message
      };
    }

    if (!catalog || !catalog.id) {
      return {
        success: false,
        error: 'No Lightroom catalog found'
      };
    }

    // Get assets
    var assets;
    try {
      if (options.limit) {
        assets = LightroomClient.listAssets(catalog.id, { limit: options.limit }).resources || [];
      } else {
        assets = LightroomClient.listAllAssets(catalog.id, { maxPages: options.maxPages || 50 });
      }
    } catch (e) {
      return {
        success: false,
        error: 'Could not list assets: ' + e.message
      };
    }

    // Sync results
    var results = {
      success: true,
      total: assets.length,
      created: 0,
      updated: 0,
      errors: 0,
      errorDetails: [],
      dryRun: options.dryRun || false
    };

    if (options.dryRun) {
      console.log('[DRY RUN] Would sync ' + assets.length + ' assets');
      return results;
    }

    // Process each asset
    for (var i = 0; i < assets.length; i++) {
      var asset = assets[i];

      try {
        var result = upsertAsset(databaseId, asset);

        if (result.ok) {
          if (result.action === 'created') results.created++;
          if (result.action === 'updated') results.updated++;
        } else {
          results.errors++;
          results.errorDetails.push({
            assetId: asset.id,
            error: result.error
          });
        }
      } catch (e) {
        results.errors++;
        results.errorDetails.push({
          assetId: asset.id,
          error: e.message || String(e)
        });
      }

      // Rate limiting
      if (i > 0 && i % 10 === 0) {
        Utilities.sleep(500);
      }
    }

    console.log('[NotionSync] Sync complete: ' +
      results.created + ' created, ' +
      results.updated + ' updated, ' +
      results.errors + ' errors');

    return results;
  }

  /**
   * Create execution log in Notion
   * @param {Object} syncResults - Results from syncAssets
   * @returns {string|null} Created page ID
   */
  function createExecutionLog(syncResults) {
    try {
      var execDbId = discoverDatabaseByName('Execution-Logs');
      if (!execDbId) return null;

      var canTag = ensureLoopGuardProperties_(execDbId);
      var cfg = LightroomConfig.getConfig();

      var properties = {
        'Script Name': { title: [{ text: { content: 'GAS Lightroom Sync' } }] },
        'Execution Result': { rich_text: [{ text: { content: JSON.stringify(syncResults) } }] },
        'Last Run': { date: { start: new Date().toISOString() } }
      };

      if (canTag) {
        properties = applyLoopGuardProps_(properties, null);
      }

      var created = notionRequest_('POST', 'pages', {
        parent: { database_id: execDbId },
        properties: properties
      });

      return created && created.id ? created.id : null;
    } catch (e) {
      console.warn('[NotionSync] Could not create execution log: ' + e.message);
      return null;
    }
  }

  // Public API
  return {
    discoverDatabaseByName: discoverDatabaseByName,
    mapAssetToNotionProperties: mapAssetToNotionProperties,
    upsertAsset: upsertAsset,
    syncAssets: syncAssets,
    createExecutionLog: createExecutionLog
  };
})();

// ===== Global Functions =====

/**
 * Main sync function - run this to sync Lightroom assets to Notion
 */
function syncLightroomToNotion() {
  // Validate configuration
  var validation = LightroomConfig.validateConfig();
  if (!validation.valid) {
    console.error('[SYNC] Configuration error: ' + validation.message);
    return { success: false, error: validation.message };
  }

  // Check authentication
  if (!LightroomOAuth.isAuthenticated()) {
    console.error('[SYNC] Not authenticated. Please authorize first.');
    return { success: false, error: 'Not authenticated' };
  }

  // Run sync
  console.log('[SYNC] Starting Lightroom to Notion sync...');
  var results = LightroomNotionSync.syncAssets();

  // Create execution log
  if (results.success) {
    LightroomNotionSync.createExecutionLog(results);
  }

  return results;
}

/**
 * Dry run - test sync without making changes
 */
function testSyncDryRun() {
  return LightroomNotionSync.syncAssets({ dryRun: true, limit: 10 });
}

/**
 * Sync limited number of assets for testing
 */
function testSyncLimited() {
  return LightroomNotionSync.syncAssets({ limit: 5 });
}

/**
 * Create a time-based trigger for periodic sync
 * Run this once to set up automated syncing
 */
function createSyncTrigger() {
  // Delete existing triggers
  var triggers = ScriptApp.getProjectTriggers();
  for (var i = 0; i < triggers.length; i++) {
    if (triggers[i].getHandlerFunction() === 'syncLightroomToNotion') {
      ScriptApp.deleteTrigger(triggers[i]);
    }
  }

  // Create new trigger - run every 6 hours
  ScriptApp.newTrigger('syncLightroomToNotion')
    .timeBased()
    .everyHours(6)
    .create();

  console.log('[SYNC] Trigger created - sync will run every 6 hours');
}

/**
 * Remove sync trigger
 */
function removeSyncTrigger() {
  var triggers = ScriptApp.getProjectTriggers();
  for (var i = 0; i < triggers.length; i++) {
    if (triggers[i].getHandlerFunction() === 'syncLightroomToNotion') {
      ScriptApp.deleteTrigger(triggers[i]);
      console.log('[SYNC] Trigger removed');
    }
  }
}

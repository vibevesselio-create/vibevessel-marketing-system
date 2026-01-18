/**
 * Lightroom API Client
 * Google Apps Script client for Adobe Lightroom API operations
 *
 * VERSION: 1.0.0
 * CREATED: 2026-01-18
 * AUTHOR: Claude Code Agent
 *
 * This module provides a comprehensive client for Lightroom API operations:
 * - Account and catalog management
 * - Asset listing and retrieval
 * - Album management
 * - Rendition access
 *
 * All requests are authenticated using tokens from LightroomOAuth.
 */

/**
 * Lightroom API Client
 */
var LightroomClient = (function() {
  'use strict';

  var API_BASE = 'https://lr.adobe.io/v2';

  /**
   * Make authenticated API request
   * @private
   * @param {string} method - HTTP method
   * @param {string} endpoint - API endpoint (without base URL)
   * @param {Object} [body] - Request body for POST/PUT
   * @param {Object} [options] - Additional options
   * @returns {Object} Parsed JSON response
   */
  function request_(method, endpoint, body, options) {
    options = options || {};

    // Get valid access token
    var accessToken = LightroomOAuth.getValidAccessToken();
    if (!accessToken) {
      throw new Error('Not authenticated. Please authorize first.');
    }

    var cfg = LightroomConfig.getConfig();
    var url = API_BASE + '/' + endpoint.replace(/^\//, '');

    var headers = {
      'Authorization': 'Bearer ' + accessToken,
      'X-API-Key': cfg.clientId,
      'Content-Type': 'application/json'
    };

    var params = {
      method: method,
      headers: headers,
      muteHttpExceptions: true
    };

    if (body && (method === 'POST' || method === 'PUT' || method === 'PATCH')) {
      params.payload = JSON.stringify(body);
    }

    var response = UrlFetchApp.fetch(url, params);
    var code = response.getResponseCode();
    var text = response.getContentText();

    // Handle rate limiting
    if (code === 429) {
      var retryAfter = response.getHeaders()['Retry-After'] || 60;
      throw new Error('Rate limited. Retry after ' + retryAfter + ' seconds.');
    }

    // Handle authentication errors
    if (code === 401) {
      // Try to refresh token once
      var refreshResult = LightroomOAuth.refreshAccessToken();
      if (refreshResult.success) {
        // Retry the request
        return request_(method, endpoint, body, options);
      }
      throw new Error('Authentication expired. Please re-authorize.');
    }

    if (code >= 200 && code < 300) {
      return text ? JSON.parse(text) : {};
    }

    throw new Error('Lightroom API error ' + code + ': ' + text);
  }

  // ===== Account & Catalog Operations =====

  /**
   * Get Adobe account information
   * @returns {Object} Account details
   */
  function getAccount() {
    return request_('GET', 'account');
  }

  /**
   * Get the user's Lightroom catalog
   * @returns {Object} Catalog details including id
   */
  function getCatalog() {
    return request_('GET', 'catalog');
  }

  // ===== Asset Operations =====

  /**
   * List assets in catalog
   * @param {string} catalogId - Catalog ID
   * @param {Object} [options] - Query options
   * @param {number} [options.limit] - Max results per page (default 100)
   * @param {string} [options.start] - Pagination cursor
   * @param {string} [options.subtype] - Filter by subtype (image, video)
   * @param {string} [options.capturedAfter] - Filter by capture date
   * @param {string} [options.capturedBefore] - Filter by capture date
   * @returns {Object} Assets response with resources array
   */
  function listAssets(catalogId, options) {
    options = options || {};

    var queryParams = [];
    if (options.limit) queryParams.push('limit=' + options.limit);
    if (options.start) queryParams.push('start=' + options.start);
    if (options.subtype) queryParams.push('subtype=' + options.subtype);
    if (options.capturedAfter) queryParams.push('captured_after=' + options.capturedAfter);
    if (options.capturedBefore) queryParams.push('captured_before=' + options.capturedBefore);

    var endpoint = 'catalogs/' + catalogId + '/assets';
    if (queryParams.length > 0) {
      endpoint += '?' + queryParams.join('&');
    }

    return request_('GET', endpoint);
  }

  /**
   * List all assets with pagination
   * @param {string} catalogId - Catalog ID
   * @param {Object} [options] - Query options
   * @returns {Array} All assets
   */
  function listAllAssets(catalogId, options) {
    options = options || {};
    var allAssets = [];
    var cursor = null;
    var maxPages = options.maxPages || 100; // Safety limit
    var pageCount = 0;

    do {
      var opts = Object.assign({}, options, { start: cursor, limit: 100 });
      var response = listAssets(catalogId, opts);

      if (response.resources) {
        allAssets = allAssets.concat(response.resources);
      }

      cursor = response.links && response.links.next ? response.links.next.href : null;
      pageCount++;

      // Avoid rate limiting
      if (cursor) {
        Utilities.sleep(100);
      }
    } while (cursor && pageCount < maxPages);

    return allAssets;
  }

  /**
   * Get a single asset by ID
   * @param {string} catalogId - Catalog ID
   * @param {string} assetId - Asset ID
   * @returns {Object} Asset details
   */
  function getAsset(catalogId, assetId) {
    return request_('GET', 'catalogs/' + catalogId + '/assets/' + assetId);
  }

  // ===== Album Operations =====

  /**
   * List albums in catalog
   * @param {string} catalogId - Catalog ID
   * @param {Object} [options] - Query options
   * @returns {Object} Albums response
   */
  function listAlbums(catalogId, options) {
    options = options || {};

    var queryParams = [];
    if (options.limit) queryParams.push('limit=' + options.limit);
    if (options.start) queryParams.push('start=' + options.start);
    if (options.subtype) queryParams.push('subtype=' + options.subtype);

    var endpoint = 'catalogs/' + catalogId + '/albums';
    if (queryParams.length > 0) {
      endpoint += '?' + queryParams.join('&');
    }

    return request_('GET', endpoint);
  }

  /**
   * Get a single album by ID
   * @param {string} catalogId - Catalog ID
   * @param {string} albumId - Album ID
   * @returns {Object} Album details
   */
  function getAlbum(catalogId, albumId) {
    return request_('GET', 'catalogs/' + catalogId + '/albums/' + albumId);
  }

  /**
   * List assets in an album
   * @param {string} catalogId - Catalog ID
   * @param {string} albumId - Album ID
   * @param {Object} [options] - Query options
   * @returns {Object} Album assets response
   */
  function listAlbumAssets(catalogId, albumId, options) {
    options = options || {};

    var queryParams = [];
    if (options.limit) queryParams.push('limit=' + options.limit);
    if (options.start) queryParams.push('start=' + options.start);

    var endpoint = 'catalogs/' + catalogId + '/albums/' + albumId + '/assets';
    if (queryParams.length > 0) {
      endpoint += '?' + queryParams.join('&');
    }

    return request_('GET', endpoint);
  }

  // ===== Rendition Operations =====

  /**
   * Get rendition URL for an asset
   * @param {string} catalogId - Catalog ID
   * @param {string} assetId - Asset ID
   * @param {string} size - Rendition size (thumbnail2x, 640, 1280, 2048, full)
   * @returns {Object} Rendition response with URL
   */
  function getRendition(catalogId, assetId, size) {
    size = size || '1280';
    return request_('GET', 'catalogs/' + catalogId + '/assets/' + assetId + '/renditions/' + size);
  }

  /**
   * Get rendition URLs for multiple sizes
   * @param {string} catalogId - Catalog ID
   * @param {string} assetId - Asset ID
   * @returns {Object} Object with rendition URLs by size
   */
  function getRenditions(catalogId, assetId) {
    var sizes = ['thumbnail2x', '640', '1280', '2048'];
    var renditions = {};

    sizes.forEach(function(size) {
      try {
        var result = getRendition(catalogId, assetId, size);
        renditions[size] = result;
      } catch (e) {
        renditions[size] = { error: e.message };
      }
    });

    return renditions;
  }

  // ===== Utility Functions =====

  /**
   * Get summary statistics for catalog
   * @param {string} catalogId - Catalog ID
   * @returns {Object} Statistics including asset counts
   */
  function getCatalogStats(catalogId) {
    var catalog = getCatalog();
    var albums = listAlbums(catalogId);

    return {
      catalogId: catalogId,
      totalAssets: catalog.payload && catalog.payload.stats ? catalog.payload.stats.images : 0,
      totalAlbums: albums.resources ? albums.resources.length : 0,
      catalogCreated: catalog.payload ? catalog.payload.created : null
    };
  }

  /**
   * Search assets by filename
   * @param {string} catalogId - Catalog ID
   * @param {string} filename - Filename to search for
   * @returns {Array} Matching assets
   */
  function searchByFilename(catalogId, filename) {
    var allAssets = listAllAssets(catalogId, { maxPages: 50 });

    return allAssets.filter(function(asset) {
      var name = asset.payload && asset.payload.importSource ?
        asset.payload.importSource.fileName : '';
      return name && name.toLowerCase().indexOf(filename.toLowerCase()) !== -1;
    });
  }

  // Public API
  return {
    // Account & Catalog
    getAccount: getAccount,
    getCatalog: getCatalog,
    getCatalogStats: getCatalogStats,

    // Assets
    listAssets: listAssets,
    listAllAssets: listAllAssets,
    getAsset: getAsset,
    searchByFilename: searchByFilename,

    // Albums
    listAlbums: listAlbums,
    getAlbum: getAlbum,
    listAlbumAssets: listAlbumAssets,

    // Renditions
    getRendition: getRendition,
    getRenditions: getRenditions
  };
})();

// ===== Global Test Functions =====

function testGetAccount() {
  var account = LightroomClient.getAccount();
  console.log('Account:', JSON.stringify(account, null, 2));
  return account;
}

function testGetCatalog() {
  var catalog = LightroomClient.getCatalog();
  console.log('Catalog:', JSON.stringify(catalog, null, 2));
  return catalog;
}

function testListAssets() {
  var catalog = LightroomClient.getCatalog();
  if (catalog && catalog.id) {
    var assets = LightroomClient.listAssets(catalog.id, { limit: 10 });
    console.log('Assets:', JSON.stringify(assets, null, 2));
    return assets;
  }
  return { error: 'No catalog found' };
}

function testListAlbums() {
  var catalog = LightroomClient.getCatalog();
  if (catalog && catalog.id) {
    var albums = LightroomClient.listAlbums(catalog.id);
    console.log('Albums:', JSON.stringify(albums, null, 2));
    return albums;
  }
  return { error: 'No catalog found' };
}

function testGetCatalogStats() {
  var catalog = LightroomClient.getCatalog();
  if (catalog && catalog.id) {
    var stats = LightroomClient.getCatalogStats(catalog.id);
    console.log('Stats:', JSON.stringify(stats, null, 2));
    return stats;
  }
  return { error: 'No catalog found' };
}

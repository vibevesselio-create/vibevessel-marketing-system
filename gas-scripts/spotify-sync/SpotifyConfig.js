/**
 * Spotify API Configuration
 * Google Apps Script module for Spotify integration
 *
 * VERSION: 1.0.0
 * CREATED: 2026-01-30
 * AUTHOR: Claude Code Agent
 *
 * This module provides configuration management for the Spotify API integration.
 * Follows the same pattern as LightroomConfig for consistency.
 *
 * SECURITY NOTE: client_secret is stored in Script Properties.
 * For production, consider using a backend token refresh endpoint.
 */

/**
 * Configuration namespace for Spotify API
 */
var SpotifyConfig = (function() {
  'use strict';

  // Spotify OAuth endpoints
  var SPOTIFY_AUTH_URL = 'https://accounts.spotify.com/authorize';
  var SPOTIFY_TOKEN_URL = 'https://accounts.spotify.com/api/token';
  var SPOTIFY_API_BASE = 'https://api.spotify.com/v1';

  // Required OAuth scopes for playlist and track access
  var OAUTH_SCOPES = [
    'user-library-read',
    'playlist-read-private',
    'playlist-read-collaborative',
    'user-read-recently-played'
  ];

  // State tracking keys
  var STATE_KEY_LAST_SYNC = 'SPOTIFY_LAST_SYNC_TIMESTAMP';
  var STATE_KEY_SYNC_CURSOR = 'SPOTIFY_SYNC_CURSOR';
  var STATE_KEY_SYNC_BATCH = 'SPOTIFY_SYNC_BATCH_INDEX';

  // Playlist exclusion configuration
  // Playlists in the "Non-Rotation" folder - these are excluded from sync
  // NOTE: Spotify API doesn't expose folder membership, so we maintain explicit list
  var EXCLUDED_PLAYLIST_NAMES = [
    'Release Radar',
    'Liked Songs Pre-2025',
    'This Is What So Not',
    'Daily Mix 1',
    'Chill Vibes',
    'State of Jazz',
    'golden hour',
    'Life is Beautiful',
    "Today's Top Hits",
    'New Classical'
  ];

  // Also exclude by pattern matching
  var EXCLUDED_PLAYLIST_PATTERNS = [
    /^Daily Mix \d+$/i,        // All Daily Mix playlists (Daily Mix 1, 2, 3, etc.)
    /^Release Radar$/i,        // Release Radar (personalized)
    /^Discover Weekly$/i,      // Discover Weekly (personalized)
    /^On Repeat$/i,            // On Repeat (personalized)
    /^Repeat Rewind$/i         // Repeat Rewind (personalized)
  ];

  /**
   * Get configuration from Script Properties
   * @returns {Object} Configuration object
   */
  function getConfig() {
    var props = PropertiesService.getScriptProperties();

    return {
      // Spotify OAuth settings
      clientId: props.getProperty('SPOTIFY_CLIENT_ID') || '',
      clientSecret: props.getProperty('SPOTIFY_CLIENT_SECRET') || '',
      redirectUri: props.getProperty('SPOTIFY_REDIRECT_URI') || getDefaultRedirectUri_(),

      // Token storage
      accessToken: props.getProperty('SPOTIFY_ACCESS_TOKEN') || '',
      refreshToken: props.getProperty('SPOTIFY_REFRESH_TOKEN') || '',
      tokenExpiresAt: parseInt(props.getProperty('SPOTIFY_TOKEN_EXPIRES_AT') || '0', 10),

      // Notion settings
      notionToken: props.getProperty('NOTION_TOKEN') || '',
      notionVersion: '2022-06-28',
      tracksDbId: props.getProperty('TRACKS_DB_ID') || '',
      playlistsDbId: props.getProperty('PLAYLISTS_DB_ID') || '',
      artistsDbId: props.getProperty('ARTISTS_DB_ID') || '',

      // Sync settings
      market: props.getProperty('SPOTIFY_MARKET') || 'US',
      syncBatchSize: parseInt(props.getProperty('SPOTIFY_SYNC_BATCH_SIZE') || '50', 10),
      triggerIntervalMinutes: parseInt(props.getProperty('SPOTIFY_TRIGGER_INTERVAL') || '5', 10),

      // State tracking
      lastSyncTimestamp: props.getProperty(STATE_KEY_LAST_SYNC) || '',
      syncCursor: props.getProperty(STATE_KEY_SYNC_CURSOR) || '',
      syncBatchIndex: parseInt(props.getProperty(STATE_KEY_SYNC_BATCH) || '0', 10),

      // API endpoints
      spotifyAuthUrl: SPOTIFY_AUTH_URL,
      spotifyTokenUrl: SPOTIFY_TOKEN_URL,
      spotifyApiBase: SPOTIFY_API_BASE,
      oauthScopes: OAUTH_SCOPES,

      // Loop-guard properties
      serenAutomationSourceProperty: 'Seren-Automation-Source',
      automationSourceValue: 'GAS-Spotify-Sync',
      nodeId: 'spotify-sync-v1'
    };
  }

  /**
   * Get default redirect URI based on script deployment
   * @private
   * @returns {string} Default redirect URI
   */
  function getDefaultRedirectUri_() {
    try {
      return ScriptApp.getService().getUrl();
    } catch (e) {
      return 'https://script.google.com/macros/d/' + ScriptApp.getScriptId() + '/usercallback';
    }
  }

  /**
   * Store tokens securely in Script Properties
   * @param {Object} tokens - Token response from OAuth
   */
  function storeTokens(tokens) {
    if (!tokens) {
      throw new Error('No tokens provided');
    }

    var props = PropertiesService.getScriptProperties();
    var now = Math.floor(Date.now() / 1000);

    if (tokens.access_token) {
      props.setProperty('SPOTIFY_ACCESS_TOKEN', tokens.access_token);
    }
    if (tokens.refresh_token) {
      props.setProperty('SPOTIFY_REFRESH_TOKEN', tokens.refresh_token);
    }
    if (tokens.expires_in) {
      // Store expiry time with 5-minute buffer
      var expiresAt = now + tokens.expires_in - 300;
      props.setProperty('SPOTIFY_TOKEN_EXPIRES_AT', String(expiresAt));
    }

    console.log('[SpotifyConfig] Tokens stored successfully');
  }

  /**
   * Clear stored tokens
   */
  function clearTokens() {
    var props = PropertiesService.getScriptProperties();
    props.deleteProperty('SPOTIFY_ACCESS_TOKEN');
    props.deleteProperty('SPOTIFY_REFRESH_TOKEN');
    props.deleteProperty('SPOTIFY_TOKEN_EXPIRES_AT');
    console.log('[SpotifyConfig] Tokens cleared');
  }

  /**
   * Check if access token is expired
   * @returns {boolean} True if token needs refresh
   */
  function isTokenExpired() {
    var cfg = getConfig();
    if (!cfg.accessToken) {
      return true;
    }
    var now = Math.floor(Date.now() / 1000);
    return now >= cfg.tokenExpiresAt;
  }

  /**
   * Update sync state tracking with atomic compare-and-set semantics
   * Prevents race conditions by verifying expected state before update
   * @param {Object} state - State to update
   * @param {Object} expected - Expected current state for CAS (optional)
   * @returns {boolean} True if update succeeded
   */
  function updateSyncState(state, expected) {
    var props = PropertiesService.getScriptProperties();
    var lock = LockService.getScriptLock();

    try {
      // Acquire lock with 10-second timeout
      lock.waitLock(10000);

      // If expected state provided, verify it matches current
      if (expected && expected.syncBatchIndex !== undefined) {
        var currentBatch = parseInt(props.getProperty(STATE_KEY_SYNC_BATCH) || '0', 10);
        if (currentBatch !== expected.syncBatchIndex) {
          console.warn('[SpotifyConfig] CAS conflict: expected batch ' + expected.syncBatchIndex + ', got ' + currentBatch);
          return false;
        }
      }

      // Update state version
      var currentVersion = parseInt(props.getProperty('STATE_VERSION') || '0', 10);
      props.setProperty('STATE_VERSION', String(currentVersion + 1));
      props.setProperty('STATE_UPDATED_AT', new Date().toISOString());

      if (state.lastSyncTimestamp !== undefined) {
        props.setProperty(STATE_KEY_LAST_SYNC, state.lastSyncTimestamp);
      }
      if (state.syncCursor !== undefined) {
        props.setProperty(STATE_KEY_SYNC_CURSOR, state.syncCursor);
      }
      if (state.syncBatchIndex !== undefined) {
        props.setProperty(STATE_KEY_SYNC_BATCH, String(state.syncBatchIndex));
      }

      return true;
    } catch (e) {
      console.error('[SpotifyConfig] Failed to update state: ' + e.message);
      return false;
    } finally {
      lock.releaseLock();
    }
  }

  /**
   * Get current state version for conflict detection
   * @returns {Object} Current state with version
   */
  function getStateWithVersion() {
    var props = PropertiesService.getScriptProperties();
    return {
      syncBatchIndex: parseInt(props.getProperty(STATE_KEY_SYNC_BATCH) || '0', 10),
      syncCursor: props.getProperty(STATE_KEY_SYNC_CURSOR) || '',
      lastSyncTimestamp: props.getProperty(STATE_KEY_LAST_SYNC) || '',
      version: parseInt(props.getProperty('STATE_VERSION') || '0', 10),
      updatedAt: props.getProperty('STATE_UPDATED_AT') || ''
    };
  }

  /**
   * Reset sync state for fresh sync
   */
  function resetSyncState() {
    var props = PropertiesService.getScriptProperties();
    props.deleteProperty(STATE_KEY_SYNC_CURSOR);
    props.deleteProperty(STATE_KEY_SYNC_BATCH);
    console.log('[SpotifyConfig] Sync state reset');
  }

  /**
   * Validate required configuration
   * @returns {Object} Validation result
   */
  function validateConfig() {
    var cfg = getConfig();
    var missing = [];

    if (!cfg.clientId) missing.push('SPOTIFY_CLIENT_ID');
    if (!cfg.clientSecret) missing.push('SPOTIFY_CLIENT_SECRET');
    if (!cfg.notionToken) missing.push('NOTION_TOKEN');
    if (!cfg.tracksDbId) missing.push('TRACKS_DB_ID');

    return {
      valid: missing.length === 0,
      missing: missing,
      message: missing.length === 0
        ? 'Configuration valid'
        : 'Missing required properties: ' + missing.join(', ')
    };
  }

  /**
   * Initialize configuration with required values
   * @param {Object} settings - Initial settings
   */
  function initialize(settings) {
    var props = PropertiesService.getScriptProperties();

    var settingsMap = {
      clientId: 'SPOTIFY_CLIENT_ID',
      clientSecret: 'SPOTIFY_CLIENT_SECRET',
      redirectUri: 'SPOTIFY_REDIRECT_URI',
      notionToken: 'NOTION_TOKEN',
      tracksDbId: 'TRACKS_DB_ID',
      playlistsDbId: 'PLAYLISTS_DB_ID',
      artistsDbId: 'ARTISTS_DB_ID',
      market: 'SPOTIFY_MARKET',
      syncBatchSize: 'SPOTIFY_SYNC_BATCH_SIZE',
      triggerIntervalMinutes: 'SPOTIFY_TRIGGER_INTERVAL'
    };

    for (var key in settingsMap) {
      if (settings[key]) {
        props.setProperty(settingsMap[key], String(settings[key]));
      }
    }

    console.log('[SpotifyConfig] Configuration initialized');
    return validateConfig();
  }

  /**
   * Check if a playlist should be excluded from sync
   * @param {Object} playlist - Spotify playlist object
   * @returns {boolean} True if playlist should be excluded
   */
  function isPlaylistExcluded(playlist) {
    if (!playlist || !playlist.name) return false;

    var name = playlist.name;

    // Check explicit exclusion list
    for (var i = 0; i < EXCLUDED_PLAYLIST_NAMES.length; i++) {
      if (name === EXCLUDED_PLAYLIST_NAMES[i]) {
        return true;
      }
    }

    // Check pattern exclusions
    for (var j = 0; j < EXCLUDED_PLAYLIST_PATTERNS.length; j++) {
      if (EXCLUDED_PLAYLIST_PATTERNS[j].test(name)) {
        return true;
      }
    }

    // Check custom exclusions from Script Properties
    var props = PropertiesService.getScriptProperties();
    var customExclusions = props.getProperty('EXCLUDED_PLAYLIST_IDS');
    if (customExclusions) {
      var excludedIds = customExclusions.split(',');
      if (excludedIds.indexOf(playlist.id) !== -1) {
        return true;
      }
    }

    return false;
  }

  /**
   * Filter playlists to exclude Non-Rotation folder playlists
   * @param {Array} playlists - Array of playlist objects
   * @returns {Array} Filtered playlists
   */
  function filterExcludedPlaylists(playlists) {
    if (!playlists || !Array.isArray(playlists)) return [];

    return playlists.filter(function(playlist) {
      var excluded = isPlaylistExcluded(playlist);
      if (excluded) {
        console.log('[SpotifyConfig] Excluding playlist: ' + playlist.name);
      }
      return !excluded;
    });
  }

  /**
   * Add a playlist ID to the custom exclusion list
   * @param {string} playlistId - Spotify playlist ID to exclude
   */
  function addPlaylistExclusion(playlistId) {
    var props = PropertiesService.getScriptProperties();
    var current = props.getProperty('EXCLUDED_PLAYLIST_IDS') || '';
    var ids = current ? current.split(',') : [];

    if (ids.indexOf(playlistId) === -1) {
      ids.push(playlistId);
      props.setProperty('EXCLUDED_PLAYLIST_IDS', ids.join(','));
    }
  }

  /**
   * Remove a playlist ID from the custom exclusion list
   * @param {string} playlistId - Spotify playlist ID to remove from exclusions
   */
  function removePlaylistExclusion(playlistId) {
    var props = PropertiesService.getScriptProperties();
    var current = props.getProperty('EXCLUDED_PLAYLIST_IDS') || '';
    var ids = current ? current.split(',') : [];

    var newIds = ids.filter(function(id) { return id !== playlistId; });
    props.setProperty('EXCLUDED_PLAYLIST_IDS', newIds.join(','));
  }

  /**
   * Get list of all excluded playlist names
   * @returns {Array} Array of excluded playlist names
   */
  function getExcludedPlaylistNames() {
    return EXCLUDED_PLAYLIST_NAMES.slice();
  }

  // Public API
  return {
    getConfig: getConfig,
    storeTokens: storeTokens,
    clearTokens: clearTokens,
    isTokenExpired: isTokenExpired,
    updateSyncState: updateSyncState,
    getStateWithVersion: getStateWithVersion,
    resetSyncState: resetSyncState,
    validateConfig: validateConfig,
    initialize: initialize,
    isPlaylistExcluded: isPlaylistExcluded,
    filterExcludedPlaylists: filterExcludedPlaylists,
    addPlaylistExclusion: addPlaylistExclusion,
    removePlaylistExclusion: removePlaylistExclusion,
    getExcludedPlaylistNames: getExcludedPlaylistNames,

    // Constants
    SPOTIFY_AUTH_URL: SPOTIFY_AUTH_URL,
    SPOTIFY_TOKEN_URL: SPOTIFY_TOKEN_URL,
    SPOTIFY_API_BASE: SPOTIFY_API_BASE,
    OAUTH_SCOPES: OAUTH_SCOPES
  };
})();

// Global functions
function getSpotifyConfig() {
  return SpotifyConfig.getConfig();
}

function validateSpotifyConfig() {
  return SpotifyConfig.validateConfig();
}

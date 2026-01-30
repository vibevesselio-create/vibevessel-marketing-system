/**
 * Spotify Sync - Main Entry Point
 * Google Apps Script for automatic Spotify to Notion synchronization
 *
 * VERSION: 1.0.0
 * CREATED: 2026-01-30
 * AUTHOR: Claude Code Agent
 *
 * This script provides:
 * - 5-minute time-triggered sync of Spotify tracks to Notion
 * - Incremental sync with batch processing and state tracking
 * - OAuth flow for Spotify authorization
 * - Manual sync functions for testing
 *
 * SETUP:
 * 1. Run initializeSpotifySync() to set up configuration
 * 2. Run authorizeSpotify() to initiate OAuth flow
 * 3. Run setupTimeTrigger() to enable automatic 5-minute sync
 */

/**
 * Main sync function - called by time trigger every 5 minutes
 * Implements incremental sync with batching and state tracking
 */
function syncSpotifyToNotion() {
  console.log('[SpotifySync] Starting scheduled sync...');

  // Validate configuration
  var validation = SpotifyConfig.validateConfig();
  if (!validation.valid) {
    console.error('[SpotifySync] Invalid configuration: ' + validation.message);
    return { success: false, error: validation.message };
  }

  // Check token validity
  if (SpotifyConfig.isTokenExpired()) {
    console.log('[SpotifySync] Token expired, refreshing...');
    if (!SpotifyClient.refreshAccessToken()) {
      console.error('[SpotifySync] Failed to refresh token');
      return { success: false, error: 'Token refresh failed' };
    }
  }

  var cfg = SpotifyConfig.getConfig();
  var stats = { processed: 0, created: 0, updated: 0, errors: 0 };

  try {
    // Get current batch info from state
    var batchIndex = cfg.syncBatchIndex || 0;
    var batchSize = cfg.syncBatchSize || 50;

    console.log('[SpotifySync] Processing batch ' + batchIndex + ' (size: ' + batchSize + ')');

    // Fetch batch of saved tracks
    var batchResult = SpotifyClient.getSavedTracksBatch(batchIndex, batchSize);
    var tracks = batchResult.tracks;

    if (tracks.length === 0) {
      // No more tracks - reset to beginning for next run
      console.log('[SpotifySync] No tracks in batch, resetting cursor');
      SpotifyConfig.updateSyncState({
        syncBatchIndex: 0,
        lastSyncTimestamp: new Date().toISOString()
      });
      return { success: true, message: 'Sync complete - reset to beginning', stats: stats };
    }

    // Sync batch to Notion
    stats = NotionSpotifySync.syncTrackBatch(tracks);

    // Update state for next run
    if (batchResult.hasMore) {
      SpotifyConfig.updateSyncState({
        syncBatchIndex: batchResult.nextBatchIndex
      });
    } else {
      // Reached end, reset for next full sync
      SpotifyConfig.updateSyncState({
        syncBatchIndex: 0,
        lastSyncTimestamp: new Date().toISOString()
      });
    }

    console.log('[SpotifySync] Batch complete: ' + JSON.stringify(stats));

    return {
      success: stats.errors === 0,
      batchIndex: batchIndex,
      hasMore: batchResult.hasMore,
      stats: stats
    };

  } catch (e) {
    console.error('[SpotifySync] Sync error: ' + e.message);
    return { success: false, error: e.message };
  }
}

/**
 * Sync recently played tracks (alternative sync mode)
 * Useful for catching tracks played since last sync
 */
function syncRecentlyPlayed() {
  console.log('[SpotifySync] Syncing recently played tracks...');

  var validation = SpotifyConfig.validateConfig();
  if (!validation.valid) {
    return { success: false, error: validation.message };
  }

  try {
    var recentTracks = SpotifyClient.getRecentlyPlayed(50);
    if (recentTracks.length === 0) {
      return { success: true, message: 'No recently played tracks' };
    }

    // Convert to standard track item format
    var trackItems = recentTracks.map(function(item) {
      return { track: item.track };
    });

    var stats = NotionSpotifySync.syncTrackBatch(trackItems);

    console.log('[SpotifySync] Recently played sync complete: ' + JSON.stringify(stats));
    return { success: true, stats: stats };

  } catch (e) {
    console.error('[SpotifySync] Error syncing recently played: ' + e.message);
    return { success: false, error: e.message };
  }
}

/**
 * Sync a specific playlist to Notion
 * @param {string} playlistId - Spotify playlist ID
 */
function syncPlaylist(playlistId) {
  console.log('[SpotifySync] Syncing playlist: ' + playlistId);

  var validation = SpotifyConfig.validateConfig();
  if (!validation.valid) {
    return { success: false, error: validation.message };
  }

  try {
    // Get playlist info
    var playlistInfo = SpotifyClient.getPlaylistInfo(playlistId);
    if (!playlistInfo) {
      return { success: false, error: 'Failed to get playlist info' };
    }

    // Find or create playlist page
    var playlistPageId = NotionSpotifySync.findPlaylistBySpotifyId(playlistId);
    if (!playlistPageId) {
      playlistPageId = NotionSpotifySync.createPlaylistPage(playlistInfo);
    }

    // Get all playlist tracks
    var tracks = SpotifyClient.getAllPlaylistTracks(playlistId);
    console.log('[SpotifySync] Found ' + tracks.length + ' tracks in playlist');

    // Sync tracks with playlist link
    var stats = NotionSpotifySync.syncTrackBatch(tracks, playlistPageId);

    console.log('[SpotifySync] Playlist sync complete: ' + JSON.stringify(stats));
    return {
      success: stats.errors === 0,
      playlistName: playlistInfo.name,
      totalTracks: tracks.length,
      stats: stats
    };

  } catch (e) {
    console.error('[SpotifySync] Error syncing playlist: ' + e.message);
    return { success: false, error: e.message };
  }
}

/**
 * Setup the 5-minute time trigger
 * Call this once during initial setup
 */
function setupTimeTrigger() {
  // Delete existing triggers first
  var triggers = ScriptApp.getProjectTriggers();
  for (var i = 0; i < triggers.length; i++) {
    if (triggers[i].getHandlerFunction() === 'syncSpotifyToNotion') {
      ScriptApp.deleteTrigger(triggers[i]);
    }
  }

  // Create new 5-minute trigger
  ScriptApp.newTrigger('syncSpotifyToNotion')
    .timeBased()
    .everyMinutes(5)
    .create();

  console.log('[SpotifySync] 5-minute trigger installed');
  return { success: true, message: 'Trigger installed - sync will run every 5 minutes' };
}

/**
 * Remove the time trigger
 */
function removeTimeTrigger() {
  var triggers = ScriptApp.getProjectTriggers();
  var removed = 0;

  for (var i = 0; i < triggers.length; i++) {
    if (triggers[i].getHandlerFunction() === 'syncSpotifyToNotion') {
      ScriptApp.deleteTrigger(triggers[i]);
      removed++;
    }
  }

  console.log('[SpotifySync] Removed ' + removed + ' trigger(s)');
  return { success: true, removed: removed };
}

/**
 * Get current trigger status
 */
function getTriggerStatus() {
  var triggers = ScriptApp.getProjectTriggers();
  var spotifyTriggers = [];

  for (var i = 0; i < triggers.length; i++) {
    if (triggers[i].getHandlerFunction() === 'syncSpotifyToNotion') {
      spotifyTriggers.push({
        id: triggers[i].getUniqueId(),
        handler: triggers[i].getHandlerFunction(),
        type: triggers[i].getTriggerSource().toString()
      });
    }
  }

  return {
    active: spotifyTriggers.length > 0,
    triggers: spotifyTriggers,
    config: SpotifyConfig.getConfig()
  };
}

/**
 * Initialize Spotify OAuth flow
 * Returns authorization URL for user to visit
 */
function authorizeSpotify() {
  var cfg = SpotifyConfig.getConfig();

  if (!cfg.clientId) {
    return { success: false, error: 'SPOTIFY_CLIENT_ID not configured' };
  }

  var scopes = SpotifyConfig.OAUTH_SCOPES.join(' ');
  var state = Utilities.getUuid();

  // Store state for verification
  PropertiesService.getScriptProperties().setProperty('SPOTIFY_OAUTH_STATE', state);

  var authUrl = SpotifyConfig.SPOTIFY_AUTH_URL +
    '?client_id=' + encodeURIComponent(cfg.clientId) +
    '&response_type=code' +
    '&redirect_uri=' + encodeURIComponent(cfg.redirectUri) +
    '&scope=' + encodeURIComponent(scopes) +
    '&state=' + state;

  console.log('[SpotifySync] Authorization URL: ' + authUrl);

  return {
    success: true,
    authUrl: authUrl,
    message: 'Visit the authorization URL to grant Spotify access'
  };
}

/**
 * Handle OAuth callback (called when user authorizes)
 * @param {Object} e - Event object with query parameters
 */
function doGet(e) {
  var params = e.parameter || {};

  // Check if this is an OAuth callback
  if (params.code) {
    return handleOAuthCallback(params);
  }

  // Otherwise show status page
  return HtmlService.createHtmlOutput(
    '<h1>Spotify Sync</h1>' +
    '<p>Status: ' + (SpotifyConfig.getConfig().accessToken ? 'Authorized' : 'Not authorized') + '</p>' +
    '<p><a href="' + authorizeSpotify().authUrl + '">Authorize Spotify</a></p>'
  );
}

/**
 * Handle OAuth callback and exchange code for tokens
 */
function handleOAuthCallback(params) {
  var cfg = SpotifyConfig.getConfig();

  // Verify state
  var savedState = PropertiesService.getScriptProperties().getProperty('SPOTIFY_OAUTH_STATE');
  if (params.state !== savedState) {
    return HtmlService.createHtmlOutput('<h1>Error</h1><p>Invalid state parameter</p>');
  }

  // Exchange code for tokens
  var authString = Utilities.base64Encode(cfg.clientId + ':' + cfg.clientSecret);

  var options = {
    method: 'post',
    headers: {
      'Authorization': 'Basic ' + authString,
      'Content-Type': 'application/x-www-form-urlencoded'
    },
    payload: {
      grant_type: 'authorization_code',
      code: params.code,
      redirect_uri: cfg.redirectUri
    },
    muteHttpExceptions: true
  };

  try {
    var response = UrlFetchApp.fetch(SpotifyConfig.SPOTIFY_TOKEN_URL, options);
    var code = response.getResponseCode();

    if (code === 200) {
      var tokens = JSON.parse(response.getContentText());
      SpotifyConfig.storeTokens(tokens);

      return HtmlService.createHtmlOutput(
        '<h1>Success!</h1>' +
        '<p>Spotify authorization complete. You can close this window.</p>' +
        '<p>Run setupTimeTrigger() to enable automatic sync.</p>'
      );
    } else {
      return HtmlService.createHtmlOutput(
        '<h1>Error</h1>' +
        '<p>Token exchange failed: ' + response.getContentText() + '</p>'
      );
    }
  } catch (e) {
    return HtmlService.createHtmlOutput('<h1>Error</h1><p>' + e.message + '</p>');
  }
}

/**
 * Initialize configuration with required values
 * Call this during initial setup
 * @param {Object} settings - Configuration settings
 */
function initializeSpotifySync(settings) {
  settings = settings || {};

  // Default settings if not provided
  if (!settings.triggerIntervalMinutes) {
    settings.triggerIntervalMinutes = 5;
  }
  if (!settings.syncBatchSize) {
    settings.syncBatchSize = 50;
  }

  var result = SpotifyConfig.initialize(settings);

  console.log('[SpotifySync] Initialization: ' + result.message);

  if (!result.valid) {
    console.log('[SpotifySync] Required properties to set:');
    console.log('  - SPOTIFY_CLIENT_ID: Your Spotify app client ID');
    console.log('  - SPOTIFY_CLIENT_SECRET: Your Spotify app client secret');
    console.log('  - NOTION_TOKEN: Your Notion integration token');
    console.log('  - TRACKS_DB_ID: Notion database ID for tracks');
    console.log('');
    console.log('Optional properties:');
    console.log('  - PLAYLISTS_DB_ID: Notion database ID for playlists');
    console.log('  - ARTISTS_DB_ID: Notion database ID for artists');
    console.log('  - SPOTIFY_MARKET: Market code (default: US)');
  }

  return result;
}

/**
 * Manual full sync - sync all saved tracks
 * WARNING: This may take a long time for large libraries
 */
function fullSync() {
  console.log('[SpotifySync] Starting full sync...');

  // Reset state to start from beginning
  SpotifyConfig.resetSyncState();

  var totalStats = { processed: 0, created: 0, updated: 0, errors: 0 };
  var batchCount = 0;
  var maxBatches = 100; // Safety limit

  while (batchCount < maxBatches) {
    var result = syncSpotifyToNotion();

    if (!result.success && result.error) {
      console.error('[SpotifySync] Full sync error: ' + result.error);
      break;
    }

    if (result.stats) {
      totalStats.processed += result.stats.processed;
      totalStats.created += result.stats.created;
      totalStats.updated += result.stats.updated;
      totalStats.errors += result.stats.errors;
    }

    batchCount++;

    if (!result.hasMore) {
      break;
    }

    // Rate limit protection
    Utilities.sleep(1000);
  }

  console.log('[SpotifySync] Full sync complete: ' + JSON.stringify(totalStats));
  return {
    success: totalStats.errors === 0,
    batches: batchCount,
    stats: totalStats
  };
}

/**
 * Test function - verify configuration and connectivity
 */
function testSpotifyConnection() {
  console.log('[SpotifySync] Testing connection...');

  var validation = SpotifyConfig.validateConfig();
  console.log('Configuration: ' + (validation.valid ? 'Valid' : 'Invalid - ' + validation.message));

  if (!validation.valid) {
    return { success: false, error: validation.message };
  }

  // Test Spotify API
  var playlists = SpotifyClient.getUserPlaylists(1);
  console.log('Spotify API: ' + (playlists.length > 0 ? 'Working' : 'No playlists or error'));

  // Test Notion API
  var cfg = SpotifyConfig.getConfig();
  var testQuery = NotionSpotifySync.notionRequest('/databases/' + cfg.tracksDbId, 'GET');
  console.log('Notion API: ' + (testQuery ? 'Working' : 'Error'));

  return {
    success: validation.valid && testQuery,
    configValid: validation.valid,
    spotifyConnected: playlists.length >= 0,
    notionConnected: !!testQuery
  };
}

/**
 * Sync ALL user playlists to Notion
 * Creates/updates playlist pages and links all tracks
 * Excludes playlists in the "Non-Rotation" folder
 * @returns {Object} Summary of sync results
 */
function syncAllPlaylists() {
  console.log('[SpotifySync] Starting full playlist sync...');

  var validation = SpotifyConfig.validateConfig();
  if (!validation.valid) {
    return { success: false, error: validation.message };
  }

  var cfg = SpotifyConfig.getConfig();
  if (!cfg.playlistsDbId) {
    return { success: false, error: 'PLAYLISTS_DB_ID not configured' };
  }

  try {
    // Get all user playlists and filter out excluded ones (Non-Rotation folder)
    var allPlaylists = SpotifyClient.getAllUserPlaylists();
    var playlists = SpotifyConfig.filterExcludedPlaylists(allPlaylists);
    console.log('[SpotifySync] Found ' + allPlaylists.length + ' playlists, ' + playlists.length + ' after exclusions');

    var results = {
      playlistsProcessed: 0,
      playlistsCreated: 0,
      playlistsUpdated: 0,
      totalTracksProcessed: 0,
      totalTracksCreated: 0,
      totalTracksUpdated: 0,
      errors: []
    };

    for (var i = 0; i < playlists.length; i++) {
      var playlist = playlists[i];

      try {
        console.log('[SpotifySync] Processing playlist: ' + playlist.name + ' (' + (i + 1) + '/' + playlists.length + ')');

        var playlistResult = syncPlaylist(playlist.id);

        if (playlistResult.success) {
          results.playlistsProcessed++;
          if (playlistResult.stats) {
            results.totalTracksProcessed += playlistResult.stats.processed || 0;
            results.totalTracksCreated += playlistResult.stats.created || 0;
            results.totalTracksUpdated += playlistResult.stats.updated || 0;
          }
        } else {
          results.errors.push({ playlist: playlist.name, error: playlistResult.error });
        }

        // Rate limit protection between playlists
        Utilities.sleep(500);

      } catch (e) {
        console.error('[SpotifySync] Error processing playlist ' + playlist.name + ': ' + e.message);
        results.errors.push({ playlist: playlist.name, error: e.message });
      }
    }

    console.log('[SpotifySync] Full playlist sync complete: ' + JSON.stringify(results));
    return {
      success: results.errors.length === 0,
      totalPlaylists: playlists.length,
      results: results
    };

  } catch (e) {
    console.error('[SpotifySync] Error in syncAllPlaylists: ' + e.message);
    return { success: false, error: e.message };
  }
}

/**
 * Sync playlists incrementally (one per trigger run)
 * Tracks progress through playlist list across multiple runs
 * Excludes playlists in the "Non-Rotation" folder
 * @returns {Object} Sync result
 */
function syncPlaylistsIncremental() {
  console.log('[SpotifySync] Starting incremental playlist sync...');

  var validation = SpotifyConfig.validateConfig();
  if (!validation.valid) {
    return { success: false, error: validation.message };
  }

  var cfg = SpotifyConfig.getConfig();
  if (!cfg.playlistsDbId) {
    return { success: false, error: 'PLAYLISTS_DB_ID not configured' };
  }

  try {
    // Get current playlist index from state
    var props = PropertiesService.getScriptProperties();
    var playlistIndex = parseInt(props.getProperty('PLAYLIST_SYNC_INDEX') || '0', 10);

    // Get all playlists and filter out excluded ones (Non-Rotation folder)
    var allPlaylists = SpotifyClient.getAllUserPlaylists();
    var playlists = SpotifyConfig.filterExcludedPlaylists(allPlaylists);

    if (playlists.length === 0) {
      return { success: true, message: 'No playlists found' };
    }

    // Reset if we've gone past the end
    if (playlistIndex >= playlists.length) {
      playlistIndex = 0;
    }

    var playlist = playlists[playlistIndex];
    console.log('[SpotifySync] Syncing playlist ' + (playlistIndex + 1) + '/' + playlists.length + ': ' + playlist.name);

    var result = syncPlaylist(playlist.id);

    // Update index for next run
    var nextIndex = playlistIndex + 1;
    if (nextIndex >= playlists.length) {
      nextIndex = 0;
      props.setProperty('PLAYLISTS_LAST_FULL_SYNC', new Date().toISOString());
    }
    props.setProperty('PLAYLIST_SYNC_INDEX', String(nextIndex));

    return {
      success: result.success,
      playlistName: playlist.name,
      playlistIndex: playlistIndex + 1,
      totalPlaylists: playlists.length,
      stats: result.stats
    };

  } catch (e) {
    console.error('[SpotifySync] Error in incremental playlist sync: ' + e.message);
    return { success: false, error: e.message };
  }
}

/**
 * Setup playlist sync trigger (runs less frequently than track sync)
 * Default: every 30 minutes
 */
function setupPlaylistTrigger() {
  // Delete existing playlist triggers
  var triggers = ScriptApp.getProjectTriggers();
  for (var i = 0; i < triggers.length; i++) {
    if (triggers[i].getHandlerFunction() === 'syncPlaylistsIncremental') {
      ScriptApp.deleteTrigger(triggers[i]);
    }
  }

  // Create 30-minute trigger for playlists
  ScriptApp.newTrigger('syncPlaylistsIncremental')
    .timeBased()
    .everyMinutes(30)
    .create();

  console.log('[SpotifySync] Playlist trigger installed (30-minute interval)');
  return { success: true, message: 'Playlist sync trigger installed' };
}

/**
 * Get all tracks from a playlist and match to existing Notion track pages
 * Updates the relation property to link tracks ↔ playlists
 * @param {string} playlistId - Spotify playlist ID
 * @returns {Object} Matching results
 */
function matchPlaylistTracks(playlistId) {
  console.log('[SpotifySync] Matching tracks for playlist: ' + playlistId);

  var validation = SpotifyConfig.validateConfig();
  if (!validation.valid) {
    return { success: false, error: validation.message };
  }

  try {
    // Get playlist info
    var playlistInfo = SpotifyClient.getPlaylistInfo(playlistId);
    if (!playlistInfo) {
      return { success: false, error: 'Failed to get playlist info' };
    }

    // Find or create playlist page
    var playlistPageId = NotionSpotifySync.findPlaylistBySpotifyId(playlistId);
    if (!playlistPageId) {
      playlistPageId = NotionSpotifySync.createPlaylistPage(playlistInfo);
      if (!playlistPageId) {
        return { success: false, error: 'Failed to create playlist page' };
      }
    }

    // Get all playlist tracks
    var tracks = SpotifyClient.getAllPlaylistTracks(playlistId);
    console.log('[SpotifySync] Found ' + tracks.length + ' tracks to match');

    var results = {
      total: tracks.length,
      matched: 0,
      created: 0,
      linked: 0,
      errors: 0
    };

    for (var i = 0; i < tracks.length; i++) {
      var item = tracks[i];
      var track = item.track;

      if (!track || !track.id) {
        results.errors++;
        continue;
      }

      try {
        // Try to find existing track page
        var trackPageId = NotionSpotifySync.findTrackBySpotifyId(track.id);

        if (!trackPageId) {
          // Try fuzzy match by name + duration
          trackPageId = NotionSpotifySync.findTrackByNameAndDuration(track.name, track.duration_ms);
        }

        if (trackPageId) {
          results.matched++;
        } else {
          // Create new track page
          trackPageId = NotionSpotifySync.createTrackPage(track);
          if (trackPageId) {
            results.created++;
          }
        }

        if (trackPageId) {
          // Link track to playlist
          if (NotionSpotifySync.linkTrackToPlaylist(trackPageId, playlistPageId)) {
            results.linked++;
          }
        }

        // Rate limit protection
        Utilities.sleep(150);

      } catch (e) {
        console.error('[SpotifySync] Error matching track ' + track.name + ': ' + e.message);
        results.errors++;
      }
    }

    console.log('[SpotifySync] Track matching complete: ' + JSON.stringify(results));
    return {
      success: results.errors < results.total,
      playlistName: playlistInfo.name,
      results: results
    };

  } catch (e) {
    console.error('[SpotifySync] Error in matchPlaylistTracks: ' + e.message);
    return { success: false, error: e.message };
  }
}

/**
 * Batch match all playlists - find existing tracks and link relations
 * Use this when you already have tracks synced and just need to establish playlist links
 * Excludes playlists in the "Non-Rotation" folder
 * @returns {Object} Batch results
 */
function batchMatchAllPlaylistTracks() {
  console.log('[SpotifySync] Starting batch playlist-track matching...');

  var validation = SpotifyConfig.validateConfig();
  if (!validation.valid) {
    return { success: false, error: validation.message };
  }

  try {
    var allPlaylists = SpotifyClient.getAllUserPlaylists();
    var playlists = SpotifyConfig.filterExcludedPlaylists(allPlaylists);
    console.log('[SpotifySync] Processing ' + playlists.length + ' playlists (excluded ' + (allPlaylists.length - playlists.length) + ')');

    var totalResults = {
      playlistsProcessed: 0,
      totalMatched: 0,
      totalCreated: 0,
      totalLinked: 0,
      errors: []
    };

    for (var i = 0; i < playlists.length; i++) {
      var playlist = playlists[i];
      console.log('[SpotifySync] Matching playlist ' + (i + 1) + '/' + playlists.length + ': ' + playlist.name);

      var result = matchPlaylistTracks(playlist.id);

      if (result.success && result.results) {
        totalResults.playlistsProcessed++;
        totalResults.totalMatched += result.results.matched || 0;
        totalResults.totalCreated += result.results.created || 0;
        totalResults.totalLinked += result.results.linked || 0;
      } else {
        totalResults.errors.push({ playlist: playlist.name, error: result.error });
      }

      // Rate limit protection
      Utilities.sleep(1000);
    }

    console.log('[SpotifySync] Batch matching complete: ' + JSON.stringify(totalResults));
    return {
      success: totalResults.errors.length === 0,
      results: totalResults
    };

  } catch (e) {
    console.error('[SpotifySync] Error in batchMatchAllPlaylistTracks: ' + e.message);
    return { success: false, error: e.message };
  }
}

/**
 * Sync a Spotify album to Notion
 * Creates album tracks and optionally links to album page
 * Mirrors Python sync_spotify_album() functionality
 * @param {string} albumId - Spotify album ID
 * @param {number} maxTracks - Maximum tracks to process (optional)
 * @returns {Object} Sync results
 */
function syncAlbum(albumId, maxTracks) {
  console.log('[SpotifySync] Syncing album: ' + albumId);

  var validation = SpotifyConfig.validateConfig();
  if (!validation.valid) {
    return { success: false, error: validation.message };
  }

  try {
    // Get album info
    var albumInfo = SpotifyClient.getAlbumInfo(albumId);
    if (!albumInfo) {
      return { success: false, error: 'Failed to get album info' };
    }

    console.log('[SpotifySync] Album: ' + albumInfo.name);

    // Get album tracks
    var tracks = SpotifyClient.getAlbumTracks(albumId);
    console.log('[SpotifySync] Found ' + tracks.length + ' tracks in album');

    // Apply max tracks limit if specified
    if (maxTracks && maxTracks > 0 && tracks.length > maxTracks) {
      tracks = tracks.slice(0, maxTracks);
      console.log('[SpotifySync] Limited to ' + maxTracks + ' tracks');
    }

    var results = {
      processed: 0,
      created: 0,
      updated: 0,
      errors: 0
    };

    for (var i = 0; i < tracks.length; i++) {
      var track = tracks[i];

      if (!track || !track.id) {
        results.errors++;
        continue;
      }

      try {
        console.log('[SpotifySync] Processing track ' + (i + 1) + '/' + tracks.length + ': ' + track.name);

        // Enrich track with album info (album tracks don't have full album object)
        track.album = {
          id: albumInfo.id,
          name: albumInfo.name,
          release_date: albumInfo.release_date,
          external_urls: albumInfo.external_urls
        };

        // Find or create track
        var trackPageId = NotionSpotifySync.findTrackBySpotifyId(track.id);

        if (!trackPageId) {
          trackPageId = NotionSpotifySync.findTrackByNameAndDuration(track.name, track.duration_ms);
        }

        if (trackPageId) {
          // Update existing
          if (NotionSpotifySync.updateTrackPage(trackPageId, track)) {
            results.updated++;
            results.processed++;
          }
        } else {
          // Create new
          trackPageId = NotionSpotifySync.createTrackPage(track);
          if (trackPageId) {
            results.created++;
            results.processed++;
          } else {
            results.errors++;
          }
        }

        // Rate limit protection
        Utilities.sleep(200);

      } catch (e) {
        console.error('[SpotifySync] Error processing track ' + track.name + ': ' + e.message);
        results.errors++;
      }
    }

    console.log('[SpotifySync] Album sync complete: ' + JSON.stringify(results));
    return {
      success: results.errors === 0,
      albumId: albumId,
      albumName: albumInfo.name,
      totalTracks: tracks.length,
      results: results
    };

  } catch (e) {
    console.error('[SpotifySync] Error in syncAlbum: ' + e.message);
    return { success: false, error: e.message };
  }
}

/**
 * Sync saved tracks (Liked Songs) incrementally
 * Mirrors Python sync logic for user's saved library
 * @param {number} limit - Max tracks per batch
 * @returns {Object} Sync results
 */
function syncSavedTracksIncremental(limit) {
  limit = limit || 50;
  console.log('[SpotifySync] Syncing saved tracks (batch size: ' + limit + ')');

  var validation = SpotifyConfig.validateConfig();
  if (!validation.valid) {
    return { success: false, error: validation.message };
  }

  try {
    var cfg = SpotifyConfig.getConfig();
    var batchIndex = cfg.syncBatchIndex || 0;

    var batchResult = SpotifyClient.getSavedTracksBatch(batchIndex, limit);
    var tracks = batchResult.tracks;

    if (tracks.length === 0) {
      // Reset to beginning
      SpotifyConfig.updateSyncState({
        syncBatchIndex: 0,
        lastSyncTimestamp: new Date().toISOString()
      });
      return { success: true, message: 'No tracks in batch - reset to beginning' };
    }

    console.log('[SpotifySync] Processing batch ' + batchIndex + ' with ' + tracks.length + ' tracks');

    var stats = NotionSpotifySync.syncTrackBatch(tracks);

    // Update state for next run
    if (batchResult.hasMore) {
      SpotifyConfig.updateSyncState({
        syncBatchIndex: batchResult.nextBatchIndex
      });
    } else {
      SpotifyConfig.updateSyncState({
        syncBatchIndex: 0,
        lastSyncTimestamp: new Date().toISOString()
      });
    }

    return {
      success: stats.errors === 0,
      batchIndex: batchIndex,
      hasMore: batchResult.hasMore,
      stats: stats
    };

  } catch (e) {
    console.error('[SpotifySync] Error in syncSavedTracksIncremental: ' + e.message);
    return { success: false, error: e.message };
  }
}

/**
 * Find or create a track by Spotify ID or name+duration match
 * Mirrors Python find_track_by_spotify_id + find_track_by_name_and_duration
 * @param {Object} track - Spotify track object
 * @returns {string|null} Notion page ID or null
 */
function findOrCreateTrack(track) {
  if (!track || !track.id) return null;

  // Try by Spotify ID first
  var pageId = NotionSpotifySync.findTrackBySpotifyId(track.id);

  // Fall back to name + duration match
  if (!pageId && track.name && track.duration_ms) {
    pageId = NotionSpotifySync.findTrackByNameAndDuration(track.name, track.duration_ms);
  }

  // Create if not found
  if (!pageId) {
    pageId = NotionSpotifySync.createTrackPage(track);
  }

  return pageId;
}

/**
 * Get sync status for all playlists
 * Shows which playlists are synced and their track counts
 * Separates excluded playlists (Non-Rotation folder) from active ones
 * @returns {Object} Status report
 */
function getPlaylistSyncStatus() {
  console.log('[SpotifySync] Getting playlist sync status...');

  var validation = SpotifyConfig.validateConfig();
  if (!validation.valid) {
    return { success: false, error: validation.message };
  }

  var cfg = SpotifyConfig.getConfig();
  if (!cfg.playlistsDbId) {
    return { success: false, error: 'PLAYLISTS_DB_ID not configured' };
  }

  try {
    // Get all Spotify playlists
    var allPlaylists = SpotifyClient.getAllUserPlaylists();
    var spotifyPlaylists = SpotifyConfig.filterExcludedPlaylists(allPlaylists);

    var status = {
      totalSpotifyPlaylists: allPlaylists.length,
      excludedPlaylists: allPlaylists.length - spotifyPlaylists.length,
      activePlaylists: spotifyPlaylists.length,
      syncedPlaylists: 0,
      unsyncedPlaylists: [],
      excludedPlaylistNames: SpotifyConfig.getExcludedPlaylistNames(),
      playlists: []
    };

    for (var i = 0; i < spotifyPlaylists.length; i++) {
      var playlist = spotifyPlaylists[i];
      var notionPageId = NotionSpotifySync.findPlaylistBySpotifyId(playlist.id);

      var playlistStatus = {
        name: playlist.name,
        spotifyId: playlist.id,
        spotifyTrackCount: (playlist.tracks || {}).total || 0,
        synced: !!notionPageId,
        notionPageId: notionPageId || null
      };

      status.playlists.push(playlistStatus);

      if (notionPageId) {
        status.syncedPlaylists++;
      } else {
        status.unsyncedPlaylists.push(playlist.name);
      }

      // Rate limit
      Utilities.sleep(100);
    }

    return {
      success: true,
      status: status
    };

  } catch (e) {
    console.error('[SpotifySync] Error getting status: ' + e.message);
    return { success: false, error: e.message };
  }
}

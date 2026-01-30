/**
 * Notion Sync Module for Spotify Integration
 * Google Apps Script module for syncing Spotify data to Notion
 *
 * VERSION: 1.0.0
 * CREATED: 2026-01-30
 * AUTHOR: Claude Code Agent
 *
 * This module handles all Notion database operations:
 * - Track page creation and updates
 * - Playlist page creation and updates
 * - Deduplication by Spotify ID
 * - Property mapping
 */

/**
 * NotionSpotifySync namespace
 */
var NotionSpotifySync = (function() {
  'use strict';

  var NOTION_API_BASE = 'https://api.notion.com/v1';

  /**
   * Make a Notion API request
   * @param {string} endpoint - API endpoint
   * @param {string} method - HTTP method
   * @param {Object} payload - Request payload
   * @returns {Object|null} Response data or null on error
   */
  function notionRequest(endpoint, method, payload) {
    var cfg = SpotifyConfig.getConfig();
    var url = NOTION_API_BASE + endpoint;

    var options = {
      method: method || 'GET',
      headers: {
        'Authorization': 'Bearer ' + cfg.notionToken,
        'Notion-Version': cfg.notionVersion,
        'Content-Type': 'application/json'
      },
      muteHttpExceptions: true
    };

    if (payload) {
      options.payload = JSON.stringify(payload);
    }

    try {
      var response = UrlFetchApp.fetch(url, options);
      var code = response.getResponseCode();

      if (code === 200 || code === 201) {
        return JSON.parse(response.getContentText());
      } else if (code === 429) {
        var retryAfter = parseInt(response.getHeaders()['Retry-After'] || '1', 10);
        console.warn('[NotionSync] Rate limited, waiting ' + retryAfter + 's');
        Utilities.sleep(retryAfter * 1000);
        return notionRequest(endpoint, method, payload);
      } else {
        console.error('[NotionSync] API error: ' + code + ' - ' + response.getContentText());
        return null;
      }
    } catch (e) {
      console.error('[NotionSync] Request error: ' + e.message);
      return null;
    }
  }

  /**
   * Find track by Spotify ID
   * @param {string} spotifyId - Spotify track ID
   * @returns {string|null} Notion page ID or null
   */
  function findTrackBySpotifyId(spotifyId) {
    if (!spotifyId) return null;

    var cfg = SpotifyConfig.getConfig();
    var query = {
      filter: {
        property: 'Spotify ID',
        rich_text: { equals: spotifyId }
      },
      page_size: 1
    };

    var result = notionRequest('/databases/' + cfg.tracksDbId + '/query', 'POST', query);
    if (result && result.results && result.results.length > 0) {
      return result.results[0].id;
    }
    return null;
  }

  /**
   * Find playlist by Spotify ID
   * @param {string} spotifyId - Spotify playlist ID
   * @returns {string|null} Notion page ID or null
   */
  function findPlaylistBySpotifyId(spotifyId) {
    if (!spotifyId) return null;

    var cfg = SpotifyConfig.getConfig();
    if (!cfg.playlistsDbId) return null;

    var query = {
      filter: {
        property: 'Spotify ID',
        rich_text: { equals: spotifyId }
      },
      page_size: 1
    };

    var result = notionRequest('/databases/' + cfg.playlistsDbId + '/query', 'POST', query);
    if (result && result.results && result.results.length > 0) {
      return result.results[0].id;
    }
    return null;
  }

  /**
   * Find track by name and duration (fuzzy match)
   * @param {string} name - Track name
   * @param {number} durationMs - Duration in milliseconds
   * @param {number} windowMs - Duration match window (default: 2000ms)
   * @returns {string|null} Notion page ID or null
   */
  function findTrackByNameAndDuration(name, durationMs, windowMs) {
    if (!name) return null;
    windowMs = windowMs || 2000;

    var cfg = SpotifyConfig.getConfig();
    var query = {
      filter: {
        property: 'Title',
        rich_text: { equals: name }
      },
      page_size: 10
    };

    var result = notionRequest('/databases/' + cfg.tracksDbId + '/query', 'POST', query);
    if (!result || !result.results) return null;

    for (var i = 0; i < result.results.length; i++) {
      var page = result.results[i];
      var pageDuration = (page.properties['Duration (ms)'] || {}).number;
      if (pageDuration !== undefined && pageDuration !== null) {
        var diff = Math.abs(pageDuration - durationMs);
        if (diff <= windowMs) {
          return page.id;
        }
      }
    }
    return null;
  }

  /**
   * Build track properties from Spotify track data
   * @param {Object} track - Spotify track object
   * @param {Object} audioFeatures - Audio features (optional)
   * @returns {Object} Notion properties
   */
  function buildTrackProperties(track, audioFeatures) {
    var artistNames = (track.artists || []).map(function(a) { return a.name; }).join(', ') || 'Unknown Artist';
    var albumName = (track.album || {}).name || '';
    var releaseDate = (track.album || {}).release_date || '';
    var isrc = ((track.external_ids || {}).isrc) || '';
    var previewUrl = track.preview_url || '';

    var properties = {
      'Title': { title: [{ text: { content: track.name || 'Unknown Track' } }] },
      'Artist Name': { rich_text: [{ text: { content: artistNames } }] },
      'Spotify ID': { rich_text: [{ text: { content: track.id || '' } }] },
      'Spotify URL': { url: ((track.external_urls || {}).spotify) || null },
      'Duration (ms)': { number: track.duration_ms || 0 },
      'Popularity': { number: track.popularity || 0 },
      'Explicit': { checkbox: track.explicit || false }
    };

    // Optional fields
    if (albumName) {
      properties['Album'] = { rich_text: [{ text: { content: albumName } }] };
    }
    if (releaseDate) {
      // Parse and format date for Notion
      var dateStr = releaseDate;
      if (releaseDate.length === 4) {
        dateStr = releaseDate + '-01-01';
      } else if (releaseDate.length === 7) {
        dateStr = releaseDate + '-01';
      }
      properties['Release Date'] = { date: { start: dateStr } };
    }
    if (isrc) {
      properties['ISRC'] = { rich_text: [{ text: { content: isrc } }] };
    }
    if (previewUrl) {
      properties['Preview URL'] = { url: previewUrl };
    }

    // Audio features (if available)
    if (audioFeatures) {
      var audioProps = {
        'Danceability': audioFeatures.danceability,
        'Energy': audioFeatures.energy,
        'Key': audioFeatures.key,
        'Loudness': audioFeatures.loudness,
        'Mode': audioFeatures.mode,
        'Speechiness': audioFeatures.speechiness,
        'Acousticness': audioFeatures.acousticness,
        'Instrumentalness': audioFeatures.instrumentalness,
        'Liveness': audioFeatures.liveness,
        'Valence': audioFeatures.valence,
        'Tempo': audioFeatures.tempo,
        'Time Signature': audioFeatures.time_signature
      };

      for (var key in audioProps) {
        if (audioProps[key] !== undefined && audioProps[key] !== null) {
          properties[key] = { number: audioProps[key] };
        }
      }
    }

    return properties;
  }

  /**
   * Create a track page in Notion
   * @param {Object} track - Spotify track object
   * @param {Object} audioFeatures - Audio features (optional)
   * @returns {string|null} Created page ID or null
   */
  function createTrackPage(track, audioFeatures) {
    var cfg = SpotifyConfig.getConfig();
    var properties = buildTrackProperties(track, audioFeatures);

    var payload = {
      parent: { database_id: cfg.tracksDbId },
      properties: properties
    };

    var result = notionRequest('/pages', 'POST', payload);
    if (result && result.id) {
      console.log('[NotionSync] Created track: ' + track.name);
      return result.id;
    }
    return null;
  }

  /**
   * Update a track page in Notion
   * @param {string} pageId - Notion page ID
   * @param {Object} track - Spotify track object
   * @param {Object} audioFeatures - Audio features (optional)
   * @returns {boolean} True if update succeeded
   */
  function updateTrackPage(pageId, track, audioFeatures) {
    if (!pageId) return false;

    var properties = buildTrackProperties(track, audioFeatures);
    var payload = { properties: properties };

    var result = notionRequest('/pages/' + pageId, 'PATCH', payload);
    return !!result;
  }

  /**
   * Create a playlist page in Notion
   * @param {Object} playlist - Spotify playlist object
   * @returns {string|null} Created page ID or null
   */
  function createPlaylistPage(playlist) {
    var cfg = SpotifyConfig.getConfig();
    if (!cfg.playlistsDbId) {
      console.log('[NotionSync] Playlists database not configured');
      return null;
    }

    var properties = {
      'Title': { title: [{ text: { content: playlist.name || 'Unknown Playlist' } }] },
      'Spotify ID': { rich_text: [{ text: { content: playlist.id || '' } }] },
      'Spotify URL': { url: ((playlist.external_urls || {}).spotify) || null },
      'Track Count': { number: (playlist.tracks || {}).total || 0 },
      'Public': { checkbox: playlist.public || false },
      'Description': { rich_text: [{ text: { content: playlist.description || '' } }] }
    };

    var payload = {
      parent: { database_id: cfg.playlistsDbId },
      properties: properties
    };

    var result = notionRequest('/pages', 'POST', payload);
    if (result && result.id) {
      console.log('[NotionSync] Created playlist: ' + playlist.name);
      return result.id;
    }
    return null;
  }

  /**
   * Link a track to a playlist via relation property
   * @param {string} trackPageId - Track page ID
   * @param {string} playlistPageId - Playlist page ID
   * @param {string} relationProp - Relation property name (default: 'Playlists')
   * @returns {boolean} True if link succeeded
   */
  function linkTrackToPlaylist(trackPageId, playlistPageId, relationProp) {
    if (!trackPageId || !playlistPageId) return false;
    relationProp = relationProp || 'Playlists';

    // Get existing relations
    var page = notionRequest('/pages/' + trackPageId, 'GET');
    if (!page) return false;

    var existingRelations = [];
    var relationData = (page.properties || {})[relationProp] || {};
    if (relationData.relation) {
      existingRelations = relationData.relation.map(function(r) { return r.id; });
    }

    // Check if already linked
    if (existingRelations.indexOf(playlistPageId) !== -1) {
      return true;
    }

    // Add new relation
    existingRelations.push(playlistPageId);
    var updatedRelations = existingRelations.map(function(id) { return { id: id }; });

    var payload = {
      properties: {}
    };
    payload.properties[relationProp] = { relation: updatedRelations };

    var result = notionRequest('/pages/' + trackPageId, 'PATCH', payload);
    return !!result;
  }

  /**
   * Upsert a track - find or create, then update
   * @param {Object} track - Spotify track object
   * @param {Object} audioFeatures - Audio features (optional)
   * @returns {string|null} Page ID or null
   */
  function upsertTrack(track, audioFeatures) {
    if (!track || !track.id) return null;

    // First try to find by Spotify ID
    var pageId = findTrackBySpotifyId(track.id);

    // If not found, try by name and duration
    if (!pageId && track.name && track.duration_ms) {
      pageId = findTrackByNameAndDuration(track.name, track.duration_ms);
    }

    // If found, update; otherwise create
    if (pageId) {
      if (updateTrackPage(pageId, track, audioFeatures)) {
        return pageId;
      }
    } else {
      return createTrackPage(track, audioFeatures);
    }

    return pageId;
  }

  /**
   * Sync a batch of tracks to Notion
   * @param {Array} trackItems - Array of { track: {...} } items from Spotify
   * @param {string} playlistPageId - Optional playlist page ID to link
   * @returns {Object} { processed: number, created: number, updated: number, errors: number }
   */
  function syncTrackBatch(trackItems, playlistPageId) {
    var stats = { processed: 0, created: 0, updated: 0, errors: 0 };

    for (var i = 0; i < trackItems.length; i++) {
      var item = trackItems[i];
      var track = item.track;

      if (!track || !track.id) {
        stats.errors++;
        continue;
      }

      try {
        var existingPageId = findTrackBySpotifyId(track.id);
        var pageId;

        if (existingPageId) {
          // Update existing
          if (updateTrackPage(existingPageId, track)) {
            pageId = existingPageId;
            stats.updated++;
          }
        } else {
          // Create new
          pageId = createTrackPage(track);
          if (pageId) {
            stats.created++;
          }
        }

        if (pageId) {
          stats.processed++;

          // Link to playlist if provided
          if (playlistPageId) {
            linkTrackToPlaylist(pageId, playlistPageId);
          }
        } else {
          stats.errors++;
        }

        // Rate limit protection
        Utilities.sleep(200);

      } catch (e) {
        console.error('[NotionSync] Error processing track: ' + e.message);
        stats.errors++;
      }
    }

    return stats;
  }

  /**
   * Update a playlist page in Notion
   * @param {string} pageId - Notion page ID
   * @param {Object} playlist - Spotify playlist object
   * @returns {boolean} True if update succeeded
   */
  function updatePlaylistPage(pageId, playlist) {
    if (!pageId) return false;

    var properties = {
      'Title': { title: [{ text: { content: playlist.name || 'Unknown Playlist' } }] },
      'Spotify ID': { rich_text: [{ text: { content: playlist.id || '' } }] },
      'Spotify URL': { url: ((playlist.external_urls || {}).spotify) || null },
      'Track Count': { number: (playlist.tracks || {}).total || 0 },
      'Public': { checkbox: playlist.public || false },
      'Description': { rich_text: [{ text: { content: playlist.description || '' } }] }
    };

    var payload = { properties: properties };
    var result = notionRequest('/pages/' + pageId, 'PATCH', payload);
    return !!result;
  }

  /**
   * Upsert a playlist - find or create, then update
   * @param {Object} playlist - Spotify playlist object
   * @returns {string|null} Page ID or null
   */
  function upsertPlaylist(playlist) {
    if (!playlist || !playlist.id) return null;

    var cfg = SpotifyConfig.getConfig();
    if (!cfg.playlistsDbId) return null;

    // Try to find existing
    var pageId = findPlaylistBySpotifyId(playlist.id);

    if (pageId) {
      // Update existing
      if (updatePlaylistPage(pageId, playlist)) {
        return pageId;
      }
    } else {
      // Create new
      return createPlaylistPage(playlist);
    }

    return pageId;
  }

  /**
   * Get all tracks linked to a playlist via relation
   * @param {string} playlistPageId - Playlist page ID
   * @returns {Array} Array of track page IDs
   */
  function getPlaylistLinkedTracks(playlistPageId) {
    if (!playlistPageId) return [];

    var cfg = SpotifyConfig.getConfig();

    // Query tracks database for those with relation to this playlist
    var query = {
      filter: {
        property: 'Playlists',
        relation: { contains: playlistPageId }
      },
      page_size: 100
    };

    var allTracks = [];
    var hasMore = true;
    var startCursor = null;

    while (hasMore) {
      if (startCursor) {
        query.start_cursor = startCursor;
      }

      var result = notionRequest('/databases/' + cfg.tracksDbId + '/query', 'POST', query);
      if (!result || !result.results) break;

      for (var i = 0; i < result.results.length; i++) {
        allTracks.push(result.results[i].id);
      }

      hasMore = result.has_more;
      startCursor = result.next_cursor;

      // Rate limit
      Utilities.sleep(100);
    }

    return allTracks;
  }

  /**
   * Unlink a track from a playlist (remove relation)
   * @param {string} trackPageId - Track page ID
   * @param {string} playlistPageId - Playlist page ID to remove
   * @param {string} relationProp - Relation property name
   * @returns {boolean} True if unlink succeeded
   */
  function unlinkTrackFromPlaylist(trackPageId, playlistPageId, relationProp) {
    if (!trackPageId || !playlistPageId) return false;
    relationProp = relationProp || 'Playlists';

    // Get existing relations
    var page = notionRequest('/pages/' + trackPageId, 'GET');
    if (!page) return false;

    var existingRelations = [];
    var relationData = (page.properties || {})[relationProp] || {};
    if (relationData.relation) {
      existingRelations = relationData.relation.map(function(r) { return r.id; });
    }

    // Remove the playlist from relations
    var newRelations = existingRelations.filter(function(id) {
      return id !== playlistPageId;
    });

    // Only update if something changed
    if (newRelations.length === existingRelations.length) {
      return true; // Already not linked
    }

    var updatedRelations = newRelations.map(function(id) { return { id: id }; });

    var payload = { properties: {} };
    payload.properties[relationProp] = { relation: updatedRelations };

    var result = notionRequest('/pages/' + trackPageId, 'PATCH', payload);
    return !!result;
  }

  /**
   * Sync playlist relations - ensure all Spotify playlist tracks are linked in Notion
   * @param {string} playlistPageId - Notion playlist page ID
   * @param {Array} spotifyTrackIds - Array of Spotify track IDs in the playlist
   * @returns {Object} { added: number, removed: number, errors: number }
   */
  function syncPlaylistRelations(playlistPageId, spotifyTrackIds) {
    if (!playlistPageId || !spotifyTrackIds) {
      return { added: 0, removed: 0, errors: 0 };
    }

    var stats = { added: 0, removed: 0, errors: 0 };

    // Get currently linked tracks
    var linkedTracks = getPlaylistLinkedTracks(playlistPageId);
    var linkedTrackMap = {};
    for (var i = 0; i < linkedTracks.length; i++) {
      linkedTrackMap[linkedTracks[i]] = true;
    }

    // Find Notion page IDs for all Spotify tracks
    var spotifyToNotion = {};
    for (var j = 0; j < spotifyTrackIds.length; j++) {
      var spotifyId = spotifyTrackIds[j];
      var notionPageId = findTrackBySpotifyId(spotifyId);
      if (notionPageId) {
        spotifyToNotion[spotifyId] = notionPageId;
      }
      Utilities.sleep(50);
    }

    // Add missing links
    for (var spotifyId in spotifyToNotion) {
      var notionId = spotifyToNotion[spotifyId];
      if (!linkedTrackMap[notionId]) {
        if (linkTrackToPlaylist(notionId, playlistPageId)) {
          stats.added++;
        } else {
          stats.errors++;
        }
        Utilities.sleep(100);
      }
    }

    return stats;
  }

  // Public API
  return {
    notionRequest: notionRequest,
    findTrackBySpotifyId: findTrackBySpotifyId,
    findPlaylistBySpotifyId: findPlaylistBySpotifyId,
    findTrackByNameAndDuration: findTrackByNameAndDuration,
    buildTrackProperties: buildTrackProperties,
    createTrackPage: createTrackPage,
    updateTrackPage: updateTrackPage,
    createPlaylistPage: createPlaylistPage,
    updatePlaylistPage: updatePlaylistPage,
    upsertPlaylist: upsertPlaylist,
    linkTrackToPlaylist: linkTrackToPlaylist,
    unlinkTrackFromPlaylist: unlinkTrackFromPlaylist,
    getPlaylistLinkedTracks: getPlaylistLinkedTracks,
    syncPlaylistRelations: syncPlaylistRelations,
    upsertTrack: upsertTrack,
    syncTrackBatch: syncTrackBatch
  };
})();

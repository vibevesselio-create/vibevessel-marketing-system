/**
 * Spotify API Client
 * Google Apps Script module for Spotify API interactions
 *
 * VERSION: 1.0.0
 * CREATED: 2026-01-30
 * AUTHOR: Claude Code Agent
 *
 * This module handles all Spotify API calls including:
 * - OAuth token refresh
 * - Playlist fetching
 * - Track metadata retrieval
 * - Recently played tracks
 */

/**
 * SpotifyClient namespace
 */
var SpotifyClient = (function() {
  'use strict';

  /**
   * Refresh the access token using refresh_token grant
   * @returns {boolean} True if refresh succeeded
   */
  function refreshAccessToken() {
    var cfg = SpotifyConfig.getConfig();

    if (!cfg.refreshToken) {
      console.error('[SpotifyClient] No refresh token available');
      return false;
    }

    var authString = Utilities.base64Encode(cfg.clientId + ':' + cfg.clientSecret);

    var options = {
      method: 'post',
      headers: {
        'Authorization': 'Basic ' + authString,
        'Content-Type': 'application/x-www-form-urlencoded'
      },
      payload: {
        grant_type: 'refresh_token',
        refresh_token: cfg.refreshToken
      },
      muteHttpExceptions: true
    };

    try {
      var response = UrlFetchApp.fetch(SpotifyConfig.SPOTIFY_TOKEN_URL, options);
      var code = response.getResponseCode();

      if (code === 200) {
        var data = JSON.parse(response.getContentText());
        SpotifyConfig.storeTokens(data);
        console.log('[SpotifyClient] Token refreshed successfully');
        return true;
      } else {
        console.error('[SpotifyClient] Token refresh failed: ' + code + ' - ' + response.getContentText());
        return false;
      }
    } catch (e) {
      console.error('[SpotifyClient] Token refresh error: ' + e.message);
      return false;
    }
  }

  /**
   * Ensure we have a valid access token
   * @returns {string|null} Valid access token or null
   */
  function getValidToken() {
    if (SpotifyConfig.isTokenExpired()) {
      console.log('[SpotifyClient] Token expired, refreshing...');
      if (!refreshAccessToken()) {
        return null;
      }
    }
    return SpotifyConfig.getConfig().accessToken;
  }

  /**
   * Make an authenticated API request to Spotify
   * @param {string} endpoint - API endpoint (without base URL)
   * @param {Object} params - Query parameters
   * @param {string} method - HTTP method (default: GET)
   * @returns {Object|null} Response data or null on error
   */
  function apiRequest(endpoint, params, method) {
    method = method || 'GET';
    var token = getValidToken();

    if (!token) {
      console.error('[SpotifyClient] No valid token for API request');
      return null;
    }

    var cfg = SpotifyConfig.getConfig();
    var url = cfg.spotifyApiBase + endpoint;

    // Add query params for GET requests
    if (method === 'GET' && params) {
      var queryString = Object.keys(params).map(function(key) {
        return encodeURIComponent(key) + '=' + encodeURIComponent(params[key]);
      }).join('&');
      url += '?' + queryString;
    }

    var options = {
      method: method,
      headers: {
        'Authorization': 'Bearer ' + token,
        'Content-Type': 'application/json'
      },
      muteHttpExceptions: true
    };

    // Add body for POST/PUT requests
    if ((method === 'POST' || method === 'PUT') && params) {
      options.payload = JSON.stringify(params);
    }

    try {
      var response = UrlFetchApp.fetch(url, options);
      var code = response.getResponseCode();

      if (code === 200) {
        return JSON.parse(response.getContentText());
      } else if (code === 429) {
        // Rate limited
        var retryAfter = response.getHeaders()['Retry-After'] || '1';
        console.warn('[SpotifyClient] Rate limited, retry after ' + retryAfter + 's');
        return { error: 'rate_limited', retryAfter: parseInt(retryAfter, 10) };
      } else if (code === 401) {
        // Token expired mid-request, try refresh
        console.warn('[SpotifyClient] Token expired, refreshing...');
        if (refreshAccessToken()) {
          return apiRequest(endpoint, params, method);
        }
        return null;
      } else {
        console.error('[SpotifyClient] API error: ' + code + ' - ' + response.getContentText());
        return null;
      }
    } catch (e) {
      console.error('[SpotifyClient] Request error: ' + e.message);
      return null;
    }
  }

  /**
   * Get user's playlists
   * @param {number} limit - Max playlists to return (default: 50)
   * @param {number} offset - Offset for pagination (default: 0)
   * @returns {Array} List of playlist objects
   */
  function getUserPlaylists(limit, offset) {
    limit = limit || 50;
    offset = offset || 0;

    var data = apiRequest('/me/playlists', {
      limit: Math.min(limit, 50),
      offset: offset
    });

    if (!data || data.error) {
      return [];
    }

    return data.items || [];
  }

  /**
   * Get all user playlists with pagination
   * @returns {Array} All playlists
   */
  function getAllUserPlaylists() {
    var allPlaylists = [];
    var offset = 0;
    var limit = 50;

    while (true) {
      var playlists = getUserPlaylists(limit, offset);
      if (playlists.length === 0) break;

      allPlaylists = allPlaylists.concat(playlists);
      offset += playlists.length;

      if (playlists.length < limit) break;

      // Respect rate limits
      Utilities.sleep(100);
    }

    return allPlaylists;
  }

  /**
   * Get tracks from a playlist
   * @param {string} playlistId - Spotify playlist ID
   * @param {number} limit - Max tracks to return
   * @param {number} offset - Offset for pagination
   * @returns {Array} List of track items
   */
  function getPlaylistTracks(playlistId, limit, offset) {
    limit = limit || 100;
    offset = offset || 0;

    var cfg = SpotifyConfig.getConfig();
    var data = apiRequest('/playlists/' + playlistId + '/tracks', {
      limit: Math.min(limit, 100),
      offset: offset,
      market: cfg.market
    });

    if (!data || data.error) {
      return [];
    }

    return data.items || [];
  }

  /**
   * Get all tracks from a playlist with pagination
   * @param {string} playlistId - Spotify playlist ID
   * @returns {Array} All tracks
   */
  function getAllPlaylistTracks(playlistId) {
    var allTracks = [];
    var offset = 0;
    var limit = 100;

    while (true) {
      var tracks = getPlaylistTracks(playlistId, limit, offset);
      if (tracks.length === 0) break;

      allTracks = allTracks.concat(tracks);
      offset += tracks.length;

      if (tracks.length < limit) break;

      Utilities.sleep(100);
    }

    return allTracks;
  }

  /**
   * Get playlist info
   * @param {string} playlistId - Spotify playlist ID
   * @returns {Object|null} Playlist info
   */
  function getPlaylistInfo(playlistId) {
    return apiRequest('/playlists/' + playlistId);
  }

  /**
   * Get track info
   * @param {string} trackId - Spotify track ID
   * @returns {Object|null} Track info
   */
  function getTrackInfo(trackId) {
    var cfg = SpotifyConfig.getConfig();
    return apiRequest('/tracks/' + trackId, { market: cfg.market });
  }

  /**
   * Get audio features for a track
   * NOTE: This endpoint was deprecated for non-partner apps in Nov 2024
   * Will return null for most apps
   * @param {string} trackId - Spotify track ID
   * @returns {Object|null} Audio features or null
   */
  function getAudioFeatures(trackId) {
    var data = apiRequest('/audio-features/' + trackId);
    // 403 is expected for non-partner apps
    if (!data) {
      console.log('[SpotifyClient] Audio features unavailable (deprecated API)');
    }
    return data;
  }

  /**
   * Get user's recently played tracks
   * @param {number} limit - Max tracks (default: 50)
   * @param {string} after - Unix timestamp in ms, return items after this
   * @returns {Array} Recently played track items
   */
  function getRecentlyPlayed(limit, after) {
    limit = limit || 50;
    var params = { limit: Math.min(limit, 50) };

    if (after) {
      params.after = after;
    }

    var data = apiRequest('/me/player/recently-played', params);
    if (!data || data.error) {
      return [];
    }

    return data.items || [];
  }

  /**
   * Get user's saved tracks (Liked Songs)
   * @param {number} limit - Max tracks
   * @param {number} offset - Offset for pagination
   * @returns {Array} Saved track items
   */
  function getSavedTracks(limit, offset) {
    limit = limit || 50;
    offset = offset || 0;

    var cfg = SpotifyConfig.getConfig();
    var data = apiRequest('/me/tracks', {
      limit: Math.min(limit, 50),
      offset: offset,
      market: cfg.market
    });

    if (!data || data.error) {
      return [];
    }

    return data.items || [];
  }

  /**
   * Get batch of saved tracks for incremental sync
   * @param {number} batchIndex - Current batch index
   * @param {number} batchSize - Tracks per batch
   * @returns {Object} { tracks: [], hasMore: boolean, nextBatchIndex: number }
   */
  function getSavedTracksBatch(batchIndex, batchSize) {
    batchIndex = batchIndex || 0;
    batchSize = batchSize || 50;

    var offset = batchIndex * batchSize;
    var tracks = getSavedTracks(batchSize, offset);

    return {
      tracks: tracks,
      hasMore: tracks.length === batchSize,
      nextBatchIndex: batchIndex + 1,
      offset: offset
    };
  }

  /**
   * Search for tracks
   * @param {string} query - Search query
   * @param {number} limit - Max results
   * @returns {Array} Track results
   */
  function searchTracks(query, limit) {
    limit = limit || 20;
    var cfg = SpotifyConfig.getConfig();

    var data = apiRequest('/search', {
      q: query,
      type: 'track',
      limit: Math.min(limit, 50),
      market: cfg.market
    });

    if (!data || data.error) {
      return [];
    }

    return (data.tracks && data.tracks.items) || [];
  }

  /**
   * Get album info
   * @param {string} albumId - Spotify album ID
   * @returns {Object|null} Album info
   */
  function getAlbumInfo(albumId) {
    var cfg = SpotifyConfig.getConfig();
    return apiRequest('/albums/' + albumId, { market: cfg.market });
  }

  /**
   * Get tracks from an album
   * @param {string} albumId - Spotify album ID
   * @param {number} limit - Max tracks
   * @param {number} offset - Offset for pagination
   * @returns {Array} Album tracks
   */
  function getAlbumTracks(albumId, limit, offset) {
    limit = limit || 50;
    offset = offset || 0;

    var cfg = SpotifyConfig.getConfig();
    var data = apiRequest('/albums/' + albumId + '/tracks', {
      limit: Math.min(limit, 50),
      offset: offset,
      market: cfg.market
    });

    if (!data || data.error) {
      return [];
    }

    return data.items || [];
  }

  /**
   * Get all tracks from an album with pagination
   * @param {string} albumId - Spotify album ID
   * @returns {Array} All album tracks
   */
  function getAllAlbumTracks(albumId) {
    var allTracks = [];
    var offset = 0;
    var limit = 50;

    while (true) {
      var tracks = getAlbumTracks(albumId, limit, offset);
      if (tracks.length === 0) break;

      allTracks = allTracks.concat(tracks);
      offset += tracks.length;

      if (tracks.length < limit) break;

      Utilities.sleep(100);
    }

    return allTracks;
  }

  // Public API
  return {
    refreshAccessToken: refreshAccessToken,
    getValidToken: getValidToken,
    apiRequest: apiRequest,
    getUserPlaylists: getUserPlaylists,
    getAllUserPlaylists: getAllUserPlaylists,
    getPlaylistTracks: getPlaylistTracks,
    getAllPlaylistTracks: getAllPlaylistTracks,
    getPlaylistInfo: getPlaylistInfo,
    getTrackInfo: getTrackInfo,
    getAudioFeatures: getAudioFeatures,
    getRecentlyPlayed: getRecentlyPlayed,
    getSavedTracks: getSavedTracks,
    getSavedTracksBatch: getSavedTracksBatch,
    searchTracks: searchTracks,
    getAlbumInfo: getAlbumInfo,
    getAlbumTracks: getAlbumTracks,
    getAllAlbumTracks: getAllAlbumTracks
  };
})();

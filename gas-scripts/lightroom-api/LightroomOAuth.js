/**
 * Lightroom OAuth Module
 * Google Apps Script OAuth 2.0 flow for Adobe Lightroom API
 *
 * VERSION: 1.0.0
 * CREATED: 2026-01-18
 * AUTHOR: Claude Code Agent
 *
 * This module handles the OAuth 2.0 authorization flow for Adobe Lightroom.
 * Token exchange is delegated to Python backend for secure client_secret handling.
 *
 * SECURITY: client_secret is NEVER stored or used in GAS code.
 * The Python backend handles all token exchange operations.
 */

/**
 * OAuth namespace for Lightroom authentication
 */
var LightroomOAuth = (function() {
  'use strict';

  /**
   * Generate OAuth authorization URL
   * @param {Object} options - Optional parameters
   * @param {string} options.state - State parameter for CSRF protection
   * @returns {string} Authorization URL
   */
  function getAuthorizationUrl(options) {
    var cfg = LightroomConfig.getConfig();
    options = options || {};

    // Generate state if not provided
    var state = options.state || generateState_();

    // Store state for validation
    PropertiesService.getScriptProperties().setProperty('OAUTH_STATE', state);

    var params = {
      client_id: cfg.clientId,
      redirect_uri: cfg.redirectUri,
      scope: cfg.oauthScopes.join(','),
      response_type: 'code',
      state: state
    };

    var queryString = Object.keys(params).map(function(key) {
      return encodeURIComponent(key) + '=' + encodeURIComponent(params[key]);
    }).join('&');

    return cfg.adobeAuthUrl + '?' + queryString;
  }

  /**
   * Generate random state parameter for CSRF protection
   * @private
   * @returns {string} Random state string
   */
  function generateState_() {
    var chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
    var state = '';
    for (var i = 0; i < 32; i++) {
      state += chars.charAt(Math.floor(Math.random() * chars.length));
    }
    return state;
  }

  /**
   * Handle OAuth callback
   * @param {Object} e - Event object from doGet
   * @returns {Object} Result with success status and message
   */
  function handleCallback(e) {
    var params = e.parameter || {};

    // Check for error from Adobe
    if (params.error) {
      return {
        success: false,
        error: params.error,
        errorDescription: params.error_description || 'Unknown error'
      };
    }

    // Validate authorization code
    if (!params.code) {
      return {
        success: false,
        error: 'missing_code',
        errorDescription: 'No authorization code received'
      };
    }

    // Validate state parameter
    var storedState = PropertiesService.getScriptProperties().getProperty('OAUTH_STATE');
    if (params.state && params.state !== storedState) {
      return {
        success: false,
        error: 'invalid_state',
        errorDescription: 'State parameter mismatch - possible CSRF attack'
      };
    }

    // Exchange code for tokens via Python backend
    try {
      var tokens = exchangeCodeForTokens_(params.code);
      LightroomConfig.storeTokens(tokens);

      // Clear state after successful exchange
      PropertiesService.getScriptProperties().deleteProperty('OAUTH_STATE');

      return {
        success: true,
        message: 'Authorization successful',
        expiresIn: tokens.expires_in
      };
    } catch (error) {
      return {
        success: false,
        error: 'token_exchange_failed',
        errorDescription: error.message || String(error)
      };
    }
  }

  /**
   * Exchange authorization code for tokens via Python backend
   * @private
   * @param {string} code - Authorization code
   * @returns {Object} Token response
   */
  function exchangeCodeForTokens_(code) {
    var cfg = LightroomConfig.getConfig();

    if (!cfg.tokenExchangeEndpoint) {
      throw new Error('TOKEN_EXCHANGE_ENDPOINT not configured');
    }

    var payload = {
      code: code,
      redirect_uri: cfg.redirectUri,
      client_id: cfg.clientId
    };

    var response = UrlFetchApp.fetch(cfg.tokenExchangeEndpoint, {
      method: 'POST',
      contentType: 'application/json',
      payload: JSON.stringify(payload),
      muteHttpExceptions: true
    });

    var code = response.getResponseCode();
    var text = response.getContentText();

    if (code >= 200 && code < 300) {
      return JSON.parse(text);
    }

    throw new Error('Token exchange failed: ' + code + ' - ' + text);
  }

  /**
   * Refresh access token
   * @returns {Object} Result with success status
   */
  function refreshAccessToken() {
    var cfg = LightroomConfig.getConfig();

    if (!cfg.refreshToken) {
      return {
        success: false,
        error: 'no_refresh_token',
        errorDescription: 'No refresh token available'
      };
    }

    if (!cfg.tokenRefreshEndpoint) {
      throw new Error('TOKEN_REFRESH_ENDPOINT not configured');
    }

    var payload = {
      refresh_token: cfg.refreshToken,
      client_id: cfg.clientId
    };

    try {
      var response = UrlFetchApp.fetch(cfg.tokenRefreshEndpoint, {
        method: 'POST',
        contentType: 'application/json',
        payload: JSON.stringify(payload),
        muteHttpExceptions: true
      });

      var code = response.getResponseCode();
      var text = response.getContentText();

      if (code >= 200 && code < 300) {
        var tokens = JSON.parse(text);
        LightroomConfig.storeTokens(tokens);
        return {
          success: true,
          message: 'Token refreshed successfully',
          expiresIn: tokens.expires_in
        };
      }

      return {
        success: false,
        error: 'refresh_failed',
        errorDescription: 'Token refresh failed: ' + code + ' - ' + text
      };
    } catch (error) {
      return {
        success: false,
        error: 'refresh_error',
        errorDescription: error.message || String(error)
      };
    }
  }

  /**
   * Get valid access token (refresh if needed)
   * @returns {string|null} Valid access token or null
   */
  function getValidAccessToken() {
    var cfg = LightroomConfig.getConfig();

    // Check if token exists and is valid
    if (cfg.accessToken && !LightroomConfig.isTokenExpired()) {
      return cfg.accessToken;
    }

    // Try to refresh
    if (cfg.refreshToken) {
      var result = refreshAccessToken();
      if (result.success) {
        return LightroomConfig.getConfig().accessToken;
      }
      console.error('[LightroomOAuth] Token refresh failed: ' + result.errorDescription);
    }

    return null;
  }

  /**
   * Check if user is authenticated
   * @returns {boolean} True if authenticated with valid tokens
   */
  function isAuthenticated() {
    return getValidAccessToken() !== null;
  }

  /**
   * Revoke tokens and log out
   */
  function logout() {
    LightroomConfig.clearTokens();
    PropertiesService.getScriptProperties().deleteProperty('OAUTH_STATE');
    console.log('[LightroomOAuth] Logged out successfully');
  }

  // Public API
  return {
    getAuthorizationUrl: getAuthorizationUrl,
    handleCallback: handleCallback,
    refreshAccessToken: refreshAccessToken,
    getValidAccessToken: getValidAccessToken,
    isAuthenticated: isAuthenticated,
    logout: logout
  };
})();

/**
 * Web app entry point for OAuth callback
 * Deploy this script as a web app to handle OAuth redirects
 */
function doGet(e) {
  var params = e.parameter || {};

  // Check if this is an OAuth callback
  if (params.code || params.error) {
    var result = LightroomOAuth.handleCallback(e);

    if (result.success) {
      return HtmlService.createHtmlOutput(
        '<html><head><title>Adobe Lightroom - Authorization Successful</title></head>' +
        '<body style="font-family: Arial, sans-serif; max-width: 600px; margin: 40px auto; padding: 20px;">' +
        '<h1 style="color: #2d9a2d;">Authorization Successful</h1>' +
        '<p>Your Adobe Lightroom account has been connected.</p>' +
        '<p>You can close this window and return to the application.</p>' +
        '</body></html>'
      );
    } else {
      return HtmlService.createHtmlOutput(
        '<html><head><title>Adobe Lightroom - Authorization Failed</title></head>' +
        '<body style="font-family: Arial, sans-serif; max-width: 600px; margin: 40px auto; padding: 20px;">' +
        '<h1 style="color: #d93025;">Authorization Failed</h1>' +
        '<p><strong>Error:</strong> ' + result.error + '</p>' +
        '<p><strong>Description:</strong> ' + result.errorDescription + '</p>' +
        '<p><a href="' + LightroomOAuth.getAuthorizationUrl() + '">Try again</a></p>' +
        '</body></html>'
      );
    }
  }

  // Display authorization link
  var authUrl = LightroomOAuth.getAuthorizationUrl();
  var validation = LightroomConfig.validateConfig();

  if (!validation.valid) {
    return HtmlService.createHtmlOutput(
      '<html><head><title>Adobe Lightroom - Configuration Error</title></head>' +
      '<body style="font-family: Arial, sans-serif; max-width: 600px; margin: 40px auto; padding: 20px;">' +
      '<h1 style="color: #d93025;">Configuration Error</h1>' +
      '<p>' + validation.message + '</p>' +
      '<p>Please configure the required Script Properties.</p>' +
      '</body></html>'
    );
  }

  if (LightroomOAuth.isAuthenticated()) {
    return HtmlService.createHtmlOutput(
      '<html><head><title>Adobe Lightroom - Connected</title></head>' +
      '<body style="font-family: Arial, sans-serif; max-width: 600px; margin: 40px auto; padding: 20px;">' +
      '<h1 style="color: #2d9a2d;">Already Connected</h1>' +
      '<p>Your Adobe Lightroom account is already connected.</p>' +
      '<p><a href="?action=logout">Disconnect</a></p>' +
      '</body></html>'
    );
  }

  return HtmlService.createHtmlOutput(
    '<html><head><title>Adobe Lightroom - Connect</title></head>' +
    '<body style="font-family: Arial, sans-serif; max-width: 600px; margin: 40px auto; padding: 20px;">' +
    '<h1>Connect Adobe Lightroom</h1>' +
    '<p>Click the button below to authorize access to your Adobe Lightroom account.</p>' +
    '<a href="' + authUrl + '" style="display: inline-block; padding: 12px 24px; ' +
    'background-color: #fa0f00; color: white; text-decoration: none; border-radius: 4px; ' +
    'font-weight: bold;">Connect with Adobe</a>' +
    '</body></html>'
  );
}

// Global functions for testing and manual operations
function testGetAuthorizationUrl() {
  var url = LightroomOAuth.getAuthorizationUrl();
  console.log('Authorization URL: ' + url);
  return url;
}

function testRefreshToken() {
  return LightroomOAuth.refreshAccessToken();
}

function testIsAuthenticated() {
  return LightroomOAuth.isAuthenticated();
}

/**
 * Lightroom API Configuration
 * Google Apps Script module for Adobe Lightroom integration
 *
 * VERSION: 1.0.0
 * CREATED: 2026-01-18
 * AUTHOR: Claude Code Agent
 *
 * This module provides configuration management for the Lightroom API integration.
 * Credentials are stored securely in Script Properties and environment variables.
 *
 * SECURITY NOTE: client_secret is handled by Python backend only.
 * GAS code never has access to client_secret.
 */

/**
 * Configuration namespace for Lightroom API
 */
var LightroomConfig = (function() {
  'use strict';

  // Adobe OAuth endpoints
  var ADOBE_AUTH_URL = 'https://ims-na1.adobelogin.com/ims/authorize/v2';
  var ADOBE_TOKEN_URL = 'https://ims-na1.adobelogin.com/ims/token/v3';
  var LIGHTROOM_API_BASE = 'https://lr.adobe.io/v2';

  // Required OAuth scopes for Lightroom API
  var OAUTH_SCOPES = [
    'openid',
    'lr_partner_apis',
    'lr_partner_rendition_apis'
  ];

  /**
   * Get configuration from Script Properties
   * @returns {Object} Configuration object
   */
  function getConfig() {
    var props = PropertiesService.getScriptProperties();

    return {
      // Adobe OAuth settings
      clientId: props.getProperty('ADOBE_CLIENT_ID') || '',
      redirectUri: props.getProperty('ADOBE_REDIRECT_URI') || getDefaultRedirectUri_(),

      // Token storage keys
      accessToken: props.getProperty('ADOBE_ACCESS_TOKEN') || '',
      refreshToken: props.getProperty('ADOBE_REFRESH_TOKEN') || '',
      tokenExpiresAt: parseInt(props.getProperty('ADOBE_TOKEN_EXPIRES_AT') || '0', 10),

      // Notion settings
      notionToken: props.getProperty('NOTION_TOKEN') || '',
      notionVersion: props.getProperty('NOTION_VERSION') || '2025-09-03',
      photosLibraryDbName: props.getProperty('PHOTOS_LIBRARY_DB_NAME') || 'Photos Library',

      // Python backend URL for token exchange (handles client_secret securely)
      tokenExchangeEndpoint: props.getProperty('TOKEN_EXCHANGE_ENDPOINT') || '',
      tokenRefreshEndpoint: props.getProperty('TOKEN_REFRESH_ENDPOINT') || '',

      // API endpoints
      adobeAuthUrl: ADOBE_AUTH_URL,
      adobeTokenUrl: ADOBE_TOKEN_URL,
      lightroomApiBase: LIGHTROOM_API_BASE,
      oauthScopes: OAUTH_SCOPES,

      // Loop-guard properties (prevent automation loops)
      serenAutomationSourceProperty: 'Seren-Automation-Source',
      serenAutomationEventIdProperty: 'Seren-Automation-Event-ID',
      serenAutomationNodeIdProperty: 'Seren-Automation-Node-ID',
      automationSourceValue: 'GAS-Lightroom-Sync',
      nodeId: 'lightroom-api-v1'
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
      // Fallback for non-deployed scripts
      return 'https://script.google.com/macros/d/' + ScriptApp.getScriptId() + '/usercallback';
    }
  }

  /**
   * Store tokens securely in Script Properties
   * @param {Object} tokens - Token response from OAuth
   * @param {string} tokens.access_token - Access token
   * @param {string} tokens.refresh_token - Refresh token
   * @param {number} tokens.expires_in - Token expiry in seconds
   */
  function storeTokens(tokens) {
    if (!tokens) {
      throw new Error('No tokens provided');
    }

    var props = PropertiesService.getScriptProperties();
    var now = Math.floor(Date.now() / 1000);

    if (tokens.access_token) {
      props.setProperty('ADOBE_ACCESS_TOKEN', tokens.access_token);
    }
    if (tokens.refresh_token) {
      props.setProperty('ADOBE_REFRESH_TOKEN', tokens.refresh_token);
    }
    if (tokens.expires_in) {
      // Store expiry time with 5-minute buffer
      var expiresAt = now + tokens.expires_in - 300;
      props.setProperty('ADOBE_TOKEN_EXPIRES_AT', String(expiresAt));
    }

    console.log('[LightroomConfig] Tokens stored successfully');
  }

  /**
   * Clear stored tokens (for logout/revocation)
   */
  function clearTokens() {
    var props = PropertiesService.getScriptProperties();
    props.deleteProperty('ADOBE_ACCESS_TOKEN');
    props.deleteProperty('ADOBE_REFRESH_TOKEN');
    props.deleteProperty('ADOBE_TOKEN_EXPIRES_AT');
    console.log('[LightroomConfig] Tokens cleared');
  }

  /**
   * Check if access token is expired or about to expire
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
   * Validate required configuration is present
   * @returns {Object} Validation result with status and missing fields
   */
  function validateConfig() {
    var cfg = getConfig();
    var missing = [];

    if (!cfg.clientId) missing.push('ADOBE_CLIENT_ID');
    if (!cfg.notionToken) missing.push('NOTION_TOKEN');
    if (!cfg.tokenExchangeEndpoint) missing.push('TOKEN_EXCHANGE_ENDPOINT');

    return {
      valid: missing.length === 0,
      missing: missing,
      message: missing.length === 0
        ? 'Configuration valid'
        : 'Missing required properties: ' + missing.join(', ')
    };
  }

  /**
   * Set a configuration property
   * @param {string} key - Property key
   * @param {string} value - Property value
   */
  function setProperty(key, value) {
    PropertiesService.getScriptProperties().setProperty(key, value);
  }

  /**
   * Initialize configuration with required values
   * Call this once during setup
   * @param {Object} settings - Initial settings
   */
  function initialize(settings) {
    var props = PropertiesService.getScriptProperties();

    if (settings.clientId) {
      props.setProperty('ADOBE_CLIENT_ID', settings.clientId);
    }
    if (settings.redirectUri) {
      props.setProperty('ADOBE_REDIRECT_URI', settings.redirectUri);
    }
    if (settings.notionToken) {
      props.setProperty('NOTION_TOKEN', settings.notionToken);
    }
    if (settings.tokenExchangeEndpoint) {
      props.setProperty('TOKEN_EXCHANGE_ENDPOINT', settings.tokenExchangeEndpoint);
    }
    if (settings.tokenRefreshEndpoint) {
      props.setProperty('TOKEN_REFRESH_ENDPOINT', settings.tokenRefreshEndpoint);
    }
    if (settings.photosLibraryDbName) {
      props.setProperty('PHOTOS_LIBRARY_DB_NAME', settings.photosLibraryDbName);
    }

    console.log('[LightroomConfig] Configuration initialized');
    return validateConfig();
  }

  // Public API
  return {
    getConfig: getConfig,
    storeTokens: storeTokens,
    clearTokens: clearTokens,
    isTokenExpired: isTokenExpired,
    validateConfig: validateConfig,
    setProperty: setProperty,
    initialize: initialize,

    // Constants
    ADOBE_AUTH_URL: ADOBE_AUTH_URL,
    ADOBE_TOKEN_URL: ADOBE_TOKEN_URL,
    LIGHTROOM_API_BASE: LIGHTROOM_API_BASE,
    OAUTH_SCOPES: OAUTH_SCOPES
  };
})();

// Global function for easy access
function getLightroomConfig() {
  return LightroomConfig.getConfig();
}

function validateLightroomConfig() {
  return LightroomConfig.validateConfig();
}

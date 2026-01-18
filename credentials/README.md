# Credentials Directory

This directory contains local copies of OAuth credentials that should NOT rely on cloud sync.

## Google OAuth

### For CLI/Desktop Scripts (Apps Script API)

**Required File:** `google-oauth/desktop_credentials.json`

**Type:** Desktop/Installed OAuth (has `"installed"` key - required for CLI scripts)

**Status:** Copied on 2026-01-18

**Source:** `client_secret_2_967911427356-7cks1g25agfiromgovdudd37uepf1lbp.apps.googleusercontent.com.json`

**Environment Variable:**
```bash
GAS_API_CREDENTIALS_PATH="/Users/brianhellemn/Projects/github-production/credentials/google-oauth/desktop_credentials.json"
```

### For Web Applications (Webhook Server)

**File:** `google-oauth/client_secret_2_967911427356-on752r03pvv0b7a18e38sc0bikhgufvu.apps.googleusercontent.com.json`

**Type:** Web OAuth (has `"web"` key - for server applications with redirect URIs)

## Important Notes

- **Desktop vs Web OAuth:** CLI scripts require "installed" type credentials, web apps require "web" type
- Google Drive CloudStorage sync times out when reading files directly - always copy locally
- Project ID: `967911427356` (seventh-atom-435416-u5)
- Account: `brian@serenmedia.co`

---
*Updated by Claude Code Agent - 2026-01-18*

# OAuth Redirect URI Migration Plan

## Goal
Align OAuth redirect URIs across Google, Spotify, and Adobe Lightroom with the Cloudflare public endpoint while preserving local dev fallbacks.

## Canonical Redirect URIs
Public (Cloudflare):
- Google: `https://webhook.vibevessel.space/auth/google/callback`
- Spotify: `https://webhook.vibevessel.space/auth/spotify/callback`
- Adobe Lightroom: `https://webhook.vibevessel.space/auth/adobe/callback`

Local (fallback):
- Google: `http://localhost:5001/auth/google/callback`
- Spotify: `http://localhost:5001/auth/spotify/callback`
- Adobe Lightroom: `http://localhost:5001/auth/adobe/callback`

## Code/Config Updates
- `.env` and example files now include both public and local URIs.
- Google, Spotify, and Adobe callback endpoints are implemented in the webhook server.
- Webhook server relocated to canonical path: `/Users/brianhellemn/Projects/github-production/services/webhook_server/`

## Provider Console Updates
1) Google Cloud OAuth Client
   - Add the public and local redirect URIs to the authorized list.
   - Verify `GOOGLE_OAUTH_REDIRECT_URI` matches the chosen URI.

2) Spotify Developer Dashboard
   - Add the public and local redirect URIs.
   - When generating tokens, use the same URI configured in `SPOTIFY_REDIRECT_URI`.

3) Adobe Lightroom API Console
   - Add the public and local redirect URIs.
   - Ensure the redirect URI matches the API client registration.

## Validation Checklist
- Google:
  - `GET /auth/google` returns an authorization URL.
  - Callback succeeds at `/auth/google/callback` and tokens are stored.
- Spotify:
  - Authorization URL uses the configured redirect URI.
  - Refresh token generated and saved in env or token store.
- Adobe Lightroom:
  - OAuth flow completes and API calls succeed.

## Gaps to Close
- Confirm Cloudflare tunnel is connected so public redirects can be reached.
- Update provider console redirect URI lists to include both public + local callbacks.
- Update Notion docs to reflect the new public OAuth base.

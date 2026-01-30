# Spotify Sync - Google Apps Script

Automatic synchronization of Spotify tracks to Notion using Google Apps Script with a 5-minute time trigger.

## Features

- **Automatic Sync**: 5-minute time trigger for continuous sync
- **Incremental Batching**: Processes tracks in batches with state tracking
- **Deduplication**: Finds existing tracks by Spotify ID or name+duration
- **OAuth Management**: Handles Spotify token refresh automatically
- **Playlist Support**: Sync specific playlists with track-playlist linking

## Setup

### 1. Create Google Apps Script Project

```bash
cd gas-scripts/spotify-sync
clasp create --title "Spotify Sync" --type webapp
clasp push
```

### 2. Configure Script Properties

Run `initializeSpotifySync()` in the Apps Script editor, then set these properties in Project Settings > Script Properties:

**Required:**
- `SPOTIFY_CLIENT_ID` - Your Spotify app client ID
- `SPOTIFY_CLIENT_SECRET` - Your Spotify app client secret
- `NOTION_TOKEN` - Your Notion integration token
- `TRACKS_DB_ID` - Notion database ID for tracks (with hyphens)

**Optional:**
- `PLAYLISTS_DB_ID` - Notion database ID for playlists
- `ARTISTS_DB_ID` - Notion database ID for artists
- `SPOTIFY_MARKET` - Market code (default: US)
- `SPOTIFY_SYNC_BATCH_SIZE` - Tracks per batch (default: 50)

### 3. Authorize Spotify

1. Run `authorizeSpotify()` in the Apps Script editor
2. Copy the authorization URL from the logs
3. Visit the URL and authorize the app
4. The callback will store the tokens automatically

### 4. Enable Time Trigger

Run `setupTimeTrigger()` to install the 5-minute automatic sync.

## Functions

### Automatic Sync
- `syncSpotifyToNotion()` - Main sync function (called by trigger)
- `setupTimeTrigger()` - Install 5-minute trigger
- `removeTimeTrigger()` - Remove trigger
- `getTriggerStatus()` - Check trigger status

### Manual Sync
- `fullSync()` - Sync all saved tracks (may take time)
- `syncRecentlyPlayed()` - Sync recently played tracks
- `syncPlaylist(playlistId)` - Sync specific playlist

### Configuration
- `initializeSpotifySync(settings)` - Initialize configuration
- `authorizeSpotify()` - Start OAuth flow
- `testSpotifyConnection()` - Test connectivity

## State Tracking

The sync maintains state between runs:
- `SPOTIFY_SYNC_BATCH_INDEX` - Current batch position
- `SPOTIFY_LAST_SYNC_TIMESTAMP` - Last complete sync time

Reset state with `SpotifyConfig.resetSyncState()` for a fresh sync.

## Notion Database Schema

The Tracks database should have these properties:
- `Title` (title) - Track name
- `Artist Name` (rich_text)
- `Spotify ID` (rich_text)
- `Spotify URL` (url)
- `Duration (ms)` (number)
- `Popularity` (number)
- `Explicit` (checkbox)
- `Album` (rich_text)
- `Release Date` (date)
- `ISRC` (rich_text)
- `Preview URL` (url)

Optional audio features:
- `Danceability`, `Energy`, `Key`, `Loudness`, `Mode` (number)
- `Speechiness`, `Acousticness`, `Instrumentalness` (number)
- `Liveness`, `Valence`, `Tempo`, `Time Signature` (number)

## Troubleshooting

**Token expired errors**: Run `SpotifyClient.refreshAccessToken()` or re-authorize.

**Rate limiting**: The sync includes built-in delays. If you hit limits, increase `SPOTIFY_SYNC_BATCH_SIZE` to reduce API calls.

**Missing properties**: The sync only updates properties that exist in the database. Add missing properties to your Notion database schema.

## Architecture

```
Code.js              - Entry points, triggers, OAuth flow
SpotifyConfig.js     - Configuration and state management
SpotifyClient.js     - Spotify API client with token refresh
NotionSync.js        - Notion database operations
```

This follows the same modular pattern as the Lightroom API integration.

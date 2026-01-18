# Spotify CSV Backup Integration Plan

**Date:** 2026-01-13  
**Status:** 📋 IMPLEMENTATION PLAN  
**Purpose:** Integrate CSV backup files as documented backup data source for all Spotify API functions

---

## Executive Summary

This plan outlines the integration of CSV backup files (`/Volumes/SYSTEM_SSD/Dropbox/Music/Spotify Library/`) as a comprehensive backup and alternative data source for Spotify API functions. CSV files will serve as:

1. **Backup Data Source** - Fallback when API is unavailable or rate-limited
2. **Alternative Data Source** - For compute-intensive operations to reduce API calls
3. **Metadata Remediation** - Secondary checks and metadata fixing
4. **Historical Reference** - Access to less-frequently-updated backup data

---

## CSV File Structure Analysis

### CSV Schema
The CSV files contain comprehensive Spotify metadata matching the API response structure:

**Columns:**
- `Track URI` - Spotify track ID (format: `spotify:track:...`)
- `Track Name` - Track title
- `Album Name` - Album name
- `Artist Name(s)` - Comma-separated artist names
- `Release Date` - ISO date format (YYYY-MM-DD)
- `Duration (ms)` - Track duration in milliseconds
- `Popularity` - Spotify popularity score (0-100)
- `Explicit` - Boolean flag
- `Added By` - User ID who added track
- `Added At` - ISO timestamp when track was added
- `Genres` - Comma-separated genres
- `Record Label` - Record label name
- **Audio Features:**
  - `Danceability`, `Energy`, `Key`, `Loudness`, `Mode`
  - `Speechiness`, `Acousticness`, `Instrumentalness`
  - `Liveness`, `Valence`, `Tempo`, `Time Signature`

### File Locations
- **Liked Songs:** `/Volumes/SYSTEM_SSD/Dropbox/Music/Spotify Library/Liked_Songs.csv`
- **Playlists:** `/Volumes/SYSTEM_SSD/Dropbox/Music/Spotify Library/spotify_playlists/*.csv`
- **Count:** 132 playlist CSV files + 1 Liked Songs CSV

---

## Integration Architecture

### 1. CSV Backup Reader Module

**File:** `monolithic-scripts/spotify_csv_backup.py`

**Purpose:** Read and parse CSV backup files with caching and indexing

**Key Features:**
- CSV file parsing with proper encoding handling
- Track indexing by Spotify ID, name, artist
- Playlist mapping (filename → playlist name)
- Caching for performance
- Metadata normalization to match API response format

### 2. Enhanced Spotify API Client

**File:** `monolithic-scripts/spotify_integration_module.py` (modify)

**Purpose:** Add CSV fallback to all API methods

**Integration Pattern:**
```python
def get_track_info(self, track_id: str, use_csv_fallback: bool = True) -> Optional[Dict]:
    # Try API first
    result = self._make_request("GET", f"/tracks/{track_id}")
    if result:
        return result
    
    # Fallback to CSV if enabled and API fails
    if use_csv_fallback:
        csv_backup = SpotifyCSVBackup()
        return csv_backup.get_track_by_id(track_id)
    
    return None
```

### 3. Use Cases

#### A. Rate Limiting Fallback
When Spotify API returns 429 (rate limited), automatically fallback to CSV:
- Reduces wait time
- Allows workflow to continue
- Logs CSV usage for monitoring

#### B. Compute-Intensive Operations
For operations requiring many API calls, use CSV first:
- Batch playlist syncs
- Metadata remediation across many tracks
- Historical data analysis
- Deduplication checks

#### C. Metadata Remediation
Use CSV for secondary verification:
- Compare API data vs CSV data
- Identify missing metadata
- Fix inconsistencies
- Validate audio features

#### D. Offline/API Unavailable
When API is unavailable (network issues, token expired, etc.):
- Full fallback to CSV
- Continue workflow with backup data
- Log all CSV usage for later API sync

---

## Implementation Details

### Phase 1: CSV Backup Reader Module

**File:** `monolithic-scripts/spotify_csv_backup.py`

**Classes:**
1. `SpotifyCSVBackup` - Main CSV reader and cache manager
2. `CSVTrackCache` - In-memory cache for performance
3. `PlaylistCSVIndex` - Index of playlist CSV files

**Methods:**
- `get_track_by_id(track_id: str) -> Optional[Dict]`
- `get_track_by_name_artist(name: str, artist: str) -> Optional[Dict]`
- `get_playlist_tracks(playlist_name: str) -> List[Dict]`
- `get_liked_songs() -> List[Dict]`
- `search_tracks(query: str) -> List[Dict]`
- `get_all_tracks() -> List[Dict]`
- `refresh_cache() -> None`

### Phase 2: API Client Enhancement

**Modify:** `monolithic-scripts/spotify_integration_module.py`

**Changes:**
1. Add CSV backup instance to `SpotifyAPI` class
2. Add `use_csv_fallback` parameter to all API methods
3. Implement fallback logic in `_make_request()`
4. Add CSV usage logging

**Methods to Enhance:**
- `get_track_info()` - Add CSV fallback
- `get_audio_features()` - Add CSV fallback
- `get_playlist_tracks()` - Add CSV fallback
- `get_user_playlists()` - Add CSV fallback
- `search_tracks()` - Add CSV fallback

### Phase 3: Integration Points

**Files to Modify:**
1. `execute_music_track_sync_workflow.py` - Use CSV for batch operations
2. `scripts/sync_spotify_playlist.py` - Use CSV for playlist sync fallback
3. `monolithic-scripts/soundcloud_download_prod_merge-2.py` - Use CSV for metadata remediation

**Integration Pattern:**
```python
# In workflow scripts
spotify_api = SpotifyAPI()
spotify_api.use_csv_fallback = True  # Enable CSV fallback

# For compute-intensive operations
csv_backup = SpotifyCSVBackup()
tracks = csv_backup.get_all_tracks()  # Use CSV instead of API
```

### Phase 4: Metadata Remediation Tools

**New File:** `scripts/spotify_metadata_remediation.py`

**Purpose:** Use CSV for metadata fixing and validation

**Features:**
- Compare Notion data vs CSV data
- Identify missing metadata fields
- Fix inconsistencies
- Validate audio features
- Generate remediation reports

---

## Configuration

### Environment Variables

Add to `.env`:
```bash
# Spotify CSV Backup Configuration
SPOTIFY_CSV_BACKUP_ENABLED=true
SPOTIFY_CSV_BACKUP_PATH=/Volumes/SYSTEM_SSD/Dropbox/Music/Spotify Library
SPOTIFY_CSV_CACHE_ENABLED=true
SPOTIFY_CSV_CACHE_TTL=3600  # Cache TTL in seconds
SPOTIFY_CSV_FALLBACK_ON_RATE_LIMIT=true
SPOTIFY_CSV_FALLBACK_ON_ERROR=true
```

### Feature Flags

```python
# In spotify_integration_module.py
USE_CSV_BACKUP = os.getenv("SPOTIFY_CSV_BACKUP_ENABLED", "true").lower() == "true"
CSV_FALLBACK_ON_RATE_LIMIT = os.getenv("SPOTIFY_CSV_FALLBACK_ON_RATE_LIMIT", "true").lower() == "true"
CSV_FALLBACK_ON_ERROR = os.getenv("SPOTIFY_CSV_FALLBACK_ON_ERROR", "true").lower() == "true"
```

---

## Usage Examples

### Example 1: Rate Limiting Fallback

```python
from spotify_integration_module import SpotifyAPI

api = SpotifyAPI()
api.use_csv_fallback = True

# If API rate limited, automatically uses CSV
track = api.get_track_info("4cPeIoEz3nKshMqLKgTAfw")
```

### Example 2: Batch Operations (Compute-Intensive)

```python
from spotify_csv_backup import SpotifyCSVBackup

csv_backup = SpotifyCSVBackup()

# Get all tracks from CSV (no API calls)
all_tracks = csv_backup.get_all_tracks()

# Process in batch
for track in all_tracks:
    # Use CSV data instead of making API calls
    process_track(track)
```

### Example 3: Metadata Remediation

```python
from spotify_csv_backup import SpotifyCSVBackup
from notion_client import Client

csv_backup = SpotifyCSVBackup()
notion = Client(auth=os.getenv("NOTION_TOKEN"))

# Get track from Notion
notion_track = get_notion_track(track_id)

# Get same track from CSV backup
csv_track = csv_backup.get_track_by_id(notion_track["spotify_id"])

# Compare and fix inconsistencies
if csv_track and csv_track.get("tempo") != notion_track.get("tempo"):
    # CSV has different tempo - use CSV value
    update_notion_track(notion_track["id"], {"tempo": csv_track["tempo"]})
```

### Example 4: Secondary Verification

```python
from spotify_integration_module import SpotifyAPI
from spotify_csv_backup import SpotifyCSVBackup

api = SpotifyAPI()
csv_backup = SpotifyCSVBackup()

# Get track from API
api_track = api.get_track_info(track_id)

# Verify with CSV backup
csv_track = csv_backup.get_track_by_id(track_id)

if api_track and csv_track:
    # Compare key fields
    if api_track.get("name") != csv_track.get("name"):
        logger.warning(f"Name mismatch: API={api_track['name']}, CSV={csv_track['name']}")
```

---

## Benefits

### 1. Reduced API Calls
- **Before:** 1000 tracks = 1000 API calls
- **After:** 1000 tracks = 0 API calls (use CSV)
- **Savings:** 100% API call reduction for batch operations

### 2. Rate Limit Resilience
- **Before:** Rate limited → wait → retry → potential failure
- **After:** Rate limited → CSV fallback → continue immediately
- **Benefit:** No workflow interruption

### 3. Offline Capability
- **Before:** API unavailable → workflow stops
- **After:** API unavailable → CSV fallback → workflow continues
- **Benefit:** Workflow resilience

### 4. Metadata Remediation
- **Before:** Manual checking of API vs Notion
- **After:** Automated CSV comparison and fixing
- **Benefit:** Data quality improvement

### 5. Historical Analysis
- **Before:** Only current API data available
- **After:** Access to CSV backup (less-frequently-updated snapshot)
- **Benefit:** Historical data analysis

---

## Implementation Checklist

### Phase 1: CSV Backup Reader
- [ ] Create `spotify_csv_backup.py` module
- [ ] Implement CSV parsing
- [ ] Implement track indexing
- [ ] Implement playlist mapping
- [ ] Add caching mechanism
- [ ] Add error handling
- [ ] Add logging

### Phase 2: API Client Enhancement
- [ ] Add CSV backup instance to `SpotifyAPI`
- [ ] Add `use_csv_fallback` parameter
- [ ] Implement fallback in `get_track_info()`
- [ ] Implement fallback in `get_audio_features()`
- [ ] Implement fallback in `get_playlist_tracks()`
- [ ] Implement fallback in `get_user_playlists()`
- [ ] Add CSV usage logging

### Phase 3: Integration Points
- [ ] Update `execute_music_track_sync_workflow.py`
- [ ] Update `sync_spotify_playlist.py`
- [ ] Update `soundcloud_download_prod_merge-2.py`
- [ ] Add configuration options

### Phase 4: Metadata Remediation
- [ ] Create `spotify_metadata_remediation.py`
- [ ] Implement comparison logic
- [ ] Implement fixing logic
- [ ] Add reporting

### Phase 5: Documentation
- [ ] Update API documentation
- [ ] Add usage examples
- [ ] Document configuration
- [ ] Add troubleshooting guide

---

## Testing Strategy

### Unit Tests
- CSV parsing accuracy
- Track lookup by ID
- Track lookup by name/artist
- Playlist mapping
- Cache functionality

### Integration Tests
- API fallback to CSV
- Rate limit handling
- Error handling
- Metadata comparison

### Performance Tests
- CSV loading time
- Cache hit rates
- Memory usage
- Batch operation performance

---

## Monitoring and Logging

### Metrics to Track
- CSV fallback usage count
- API call reduction percentage
- CSV cache hit rate
- Metadata mismatch count
- Remediation fixes applied

### Logging
```python
logger.info(f"Using CSV backup for track {track_id} (API unavailable)")
logger.info(f"CSV fallback: {fallback_count} tracks processed")
logger.warning(f"Metadata mismatch detected: {field}={api_value} vs CSV={csv_value}")
```

---

## Risk Mitigation

### Risks
1. **CSV Data Staleness** - CSV may be outdated
2. **CSV Format Changes** - Spotify export format may change
3. **File Access Issues** - CSV files may be inaccessible
4. **Memory Usage** - Large CSV files may consume memory

### Mitigations
1. **Staleness:** Log CSV usage, prefer API when available
2. **Format Changes:** Version detection, format validation
3. **Access Issues:** Graceful fallback, error handling
4. **Memory:** Streaming parser, cache limits, lazy loading

---

## Next Steps

1. **Review and Approve Plan** - Get approval for implementation
2. **Create CSV Backup Module** - Implement Phase 1
3. **Enhance API Client** - Implement Phase 2
4. **Integrate Workflows** - Implement Phase 3
5. **Add Remediation Tools** - Implement Phase 4
6. **Test and Validate** - Comprehensive testing
7. **Deploy and Monitor** - Production deployment

---

**Plan Status:** 📋 READY FOR IMPLEMENTATION  
**Estimated Effort:** 8-12 hours  
**Priority:** HIGH (reduces API calls, improves resilience)

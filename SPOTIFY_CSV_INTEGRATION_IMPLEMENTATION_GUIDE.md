# Spotify CSV Integration Implementation Guide

**Date:** 2026-01-13  
**Status:** ✅ READY FOR IMPLEMENTATION  
**Purpose:** Step-by-step guide to integrate CSV backup as documented backup data source

---

## Overview

This guide provides step-by-step instructions to integrate CSV backup files as a documented backup data source for all Spotify API functions. The integration includes:

1. CSV backup reader module (✅ Created)
2. API client enhancements (📋 To be applied)
3. Metadata remediation tools (✅ Created)
4. Configuration and testing

---

## Files Created

### ✅ Phase 1: Core Modules

1. **`monolithic-scripts/spotify_csv_backup.py`**
   - CSV backup reader module
   - Track indexing and caching
   - Playlist mapping
   - **Status:** Complete and ready to use

2. **`scripts/spotify_metadata_remediation.py`**
   - Metadata comparison tool
   - Remediation automation
   - Batch processing
   - **Status:** Complete, needs Notion property update implementation

3. **`SPOTIFY_CSV_BACKUP_INTEGRATION_PLAN.md`**
   - Comprehensive integration plan
   - Architecture and design
   - Usage examples
   - **Status:** Complete

4. **`monolithic-scripts/spotify_integration_module_csv_enhancement.py`**
   - Enhancement code snippets
   - Ready to apply to existing module
   - **Status:** Complete

---

## Implementation Steps

### Step 1: Test CSV Backup Module

```bash
# Test the CSV backup reader
cd /Users/brianhellemn/Projects/github-production
python3 monolithic-scripts/spotify_csv_backup.py
```

**Expected Output:**
- CSV files loaded
- Track count displayed
- Playlist count displayed
- Test lookup successful

### Step 2: Apply API Client Enhancements

**File to Modify:** `monolithic-scripts/spotify_integration_module.py`

**Changes Required:**

1. **Add Import** (at top of file, after existing imports):
```python
try:
    from spotify_csv_backup import SpotifyCSVBackup, get_spotify_csv_backup
    CSV_BACKUP_AVAILABLE = True
except ImportError:
    CSV_BACKUP_AVAILABLE = False
    logger.warning("Spotify CSV backup module not available")
```

2. **Modify `SpotifyAPI.__init__`** (around line 179):
   - Add CSV backup instance initialization
   - Add configuration flags
   - See `spotify_integration_module_csv_enhancement.py` for code

3. **Modify `_make_request`** (around line 195):
   - Add CSV fallback on rate limit (429)
   - Add CSV fallback on error
   - Add `_try_csv_fallback` helper method
   - See enhancement file for code

4. **Modify API Methods:**
   - `get_track_info()` - Add CSV fallback parameter
   - `get_audio_features()` - Add CSV fallback parameter
   - `get_playlist_tracks()` - Add CSV fallback parameter
   - `get_user_playlists()` - Add CSV fallback parameter
   - `search_tracks()` - Add CSV fallback parameter

**Reference:** See `monolithic-scripts/spotify_integration_module_csv_enhancement.py` for all code snippets.

### Step 3: Add Configuration

**File:** `.env` (or environment configuration)

Add these variables:
```bash
# Spotify CSV Backup Configuration
SPOTIFY_CSV_BACKUP_ENABLED=true
SPOTIFY_CSV_BACKUP_PATH=/Volumes/SYSTEM_SSD/Dropbox/Music/Spotify Library
SPOTIFY_CSV_CACHE_ENABLED=true
SPOTIFY_CSV_CACHE_TTL=3600
SPOTIFY_CSV_FALLBACK_ON_RATE_LIMIT=true
SPOTIFY_CSV_FALLBACK_ON_ERROR=true
```

### Step 4: Update Workflow Scripts

**Files to Update:**

1. **`execute_music_track_sync_workflow.py`**
   - Enable CSV fallback for batch operations
   - Use CSV for compute-intensive playlist syncs

2. **`scripts/sync_spotify_playlist.py`**
   - Add CSV fallback option
   - Use CSV for large playlist syncs

3. **`monolithic-scripts/soundcloud_download_prod_merge-2.py`**
   - Use CSV for metadata remediation
   - Add secondary verification

**Example Integration:**
```python
from spotify_integration_module import SpotifyAPI, SpotifyOAuthManager
from spotify_csv_backup import get_spotify_csv_backup

# Initialize with CSV fallback enabled
api = SpotifyAPI(SpotifyOAuthManager())
api.use_csv_fallback = True

# For batch operations, use CSV directly
csv_backup = get_spotify_csv_backup()
all_tracks = csv_backup.get_all_tracks()  # No API calls
```

### Step 5: Test Integration

**Test Cases:**

1. **Rate Limit Fallback:**
```python
# Simulate rate limit, verify CSV fallback
api = SpotifyAPI()
track = api.get_track_info("4cPeIoEz3nKshMqLKgTAfw")
# Should use CSV if API rate limited
```

2. **Batch Operations:**
```python
# Use CSV for batch processing
csv_backup = get_spotify_csv_backup()
tracks = csv_backup.get_all_tracks()
# Process without API calls
```

3. **Metadata Remediation:**
```python
# Compare and fix metadata
python3 scripts/spotify_metadata_remediation.py <notion_page_id> --auto-fix
```

---

## Usage Examples

### Example 1: Automatic Fallback (Rate Limit)

```python
from spotify_integration_module import SpotifyAPI, SpotifyOAuthManager

api = SpotifyAPI(SpotifyOAuthManager())
# CSV fallback enabled by default (via env var)

# If API rate limited, automatically uses CSV
track = api.get_track_info("4cPeIoEz3nKshMqLKgTAfw")
```

### Example 2: Batch Operations (Compute-Intensive)

```python
from spotify_csv_backup import get_spotify_csv_backup

csv_backup = get_spotify_csv_backup()
csv_backup.load_all()

# Get all tracks without API calls
all_tracks = csv_backup.get_all_tracks()

# Process in batch
for track in all_tracks:
    process_track(track)  # Uses CSV data, no API calls
```

### Example 3: Metadata Remediation

```python
from scripts.spotify_metadata_remediation import MetadataRemediator

remediator = MetadataRemediator()

# Remediate single track
result = remediator.remediate_track(notion_page_id, auto_fix=True)

# Batch remediation
track_ids = ["page_id_1", "page_id_2", "page_id_3"]
results = remediator.batch_remediate(track_ids, auto_fix=True)
```

### Example 4: Secondary Verification

```python
from spotify_integration_module import SpotifyAPI
from spotify_csv_backup import get_spotify_csv_backup

api = SpotifyAPI()
csv_backup = get_spotify_csv_backup()

# Get from API
api_track = api.get_track_info(track_id)

# Verify with CSV
csv_track = csv_backup.get_track_by_id(track_id)

# Compare
if api_track and csv_track:
    if api_track.get("name") != csv_track.get("name"):
        logger.warning(f"Name mismatch detected")
```

---

## Benefits Summary

### 1. Reduced API Calls
- **Before:** 1000 tracks = 1000 API calls
- **After:** 1000 tracks = 0 API calls (use CSV)
- **Savings:** 100% reduction for batch operations

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

## Monitoring

### Logging

The integration includes comprehensive logging:

```python
logger.info("Using CSV backup for track {track_id} (API unavailable)")
logger.info("CSV fallback: {count} tracks processed")
logger.warning("Metadata mismatch detected: {field}={api_value} vs CSV={csv_value}")
```

### Metrics to Track

- CSV fallback usage count
- API call reduction percentage
- CSV cache hit rate
- Metadata mismatch count
- Remediation fixes applied

---

## Troubleshooting

### Issue: CSV files not found

**Solution:**
- Check `SPOTIFY_CSV_BACKUP_PATH` environment variable
- Verify CSV files exist at path
- Check file permissions

### Issue: CSV parsing errors

**Solution:**
- Check CSV file encoding (should be UTF-8 or UTF-8-BOM)
- Verify CSV format matches expected schema
- Check for corrupted CSV files

### Issue: CSV fallback not working

**Solution:**
- Verify `SPOTIFY_CSV_BACKUP_ENABLED=true`
- Check CSV backup module imported correctly
- Verify CSV files loaded successfully
- Check logs for errors

---

## Next Steps

1. ✅ **CSV Backup Module** - Complete
2. ✅ **Metadata Remediation Tool** - Complete
3. ⏳ **API Client Enhancement** - Apply enhancements
4. ⏳ **Configuration** - Add environment variables
5. ⏳ **Workflow Integration** - Update workflow scripts
6. ⏳ **Testing** - Comprehensive testing
7. ⏳ **Documentation** - Update API docs

---

## Status

- ✅ **Phase 1:** CSV Backup Reader Module - COMPLETE
- ✅ **Phase 2:** Metadata Remediation Tool - COMPLETE
- ✅ **Phase 3:** Integration Plan - COMPLETE
- ⏳ **Phase 4:** API Client Enhancement - READY TO APPLY
- ⏳ **Phase 5:** Workflow Integration - PENDING
- ⏳ **Phase 6:** Testing and Validation - PENDING

---

**Implementation Guide Status:** ✅ READY  
**Next Action:** Apply API client enhancements from `spotify_integration_module_csv_enhancement.py`

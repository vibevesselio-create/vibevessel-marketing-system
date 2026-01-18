# Playlist Processing Gap Analysis
## Requirements: Process up to 500 tracks from a SoundCloud playlist in a single run

**Date:** 2025-12-31  
**Current Script:** `monolithic-scripts/soundcloud_download_prod_merge-2.py`

---

## Current Implementation Status

### ✅ **What's Already Implemented**

1. **Batch Processing Infrastructure**
   - `efficient_batch_process_tracks()` function exists
   - Supports `--mode batch` and `--mode all`
   - Batch size: 100 tracks per query (configurable)
   - Pagination support via `query_database_paginated()`
   - Max concurrency: 4 parallel jobs (configurable via `SC_MAX_CONCURRENCY`)

2. **Deduplication**
   - ✅ Pre-download duplicate checking (Eagle library)
   - ✅ Artist validation for filename matches
   - ✅ Strict filename matching (start/end position or high similarity)
   - ✅ In-batch duplicate merging (`dedupe_within_batch()`)
   - ✅ Cross-batch duplicate detection (`try_merge_duplicates_for_page()`)
   - ✅ Fingerprint-based matching (most reliable)

3. **Metadata Processing**
   - ✅ Audio analysis (BPM, Key, Duration)
   - ✅ Format conversion (AIFF, M4A, WAV)
   - ✅ Metadata embedding
   - ✅ Eagle import with tags
   - ✅ Notion updates with all metadata

4. **Error Handling**
   - ✅ Try/except blocks around track processing
   - ✅ Retry logic for downloads (max 20 retries)
   - ✅ Basic error logging

5. **Progress Tracking**
   - ✅ Batch summaries
   - ✅ Total processed/failed/skipped counts
   - ✅ Per-track logging

---

## ❌ **What's Missing for 500-Track Playlist Processing**

### 1. **Playlist URL Processing** (CRITICAL - NOT IMPLEMENTED)

**Gap:** No functionality to extract tracks from a SoundCloud playlist URL and add them to Notion.

**Required Implementation:**
- Function to extract playlist URL and get all track URLs from it
- Use `yt-dlp` or SoundCloud API to enumerate playlist tracks
- Batch create Notion pages for all tracks in playlist
- Handle playlist metadata (name, description, etc.)

**Example API:**
```python
def process_playlist_url(playlist_url: str) -> List[str]:
    """Extract all track URLs from a SoundCloud playlist"""
    # Use yt-dlp to get playlist info
    # Return list of track URLs
    pass

def add_playlist_tracks_to_notion(playlist_url: str, playlist_name: str = None) -> int:
    """Add all tracks from playlist to Notion database"""
    # Extract tracks
    # Batch create Notion pages
    # Return count of tracks added
    pass
```

**Priority:** 🔴 **CRITICAL** - Without this, playlist processing is impossible.

---

### 2. **Resume/Checkpoint System** (HIGH PRIORITY)

**Gap:** No ability to resume processing after interruption.

**Required Implementation:**
- Save checkpoint after each successfully processed track
- Checkpoint file format: JSON with track IDs, status, timestamps
- Resume function that skips already-processed tracks
- Handle partial failures gracefully

**Example:**
```python
def save_checkpoint(batch_number: int, processed_tracks: List[str], failed_tracks: List[str]):
    """Save processing state to checkpoint file"""
    pass

def load_checkpoint() -> dict:
    """Load previous checkpoint if exists"""
    pass

def resume_from_checkpoint(checkpoint_file: str) -> int:
    """Resume processing from checkpoint"""
    pass
```

**Priority:** 🟠 **HIGH** - Essential for long-running 500-track jobs.

---

### 3. **Rate Limiting & Backoff** (HIGH PRIORITY)

**Gap:** Basic 429 handling exists but no comprehensive rate limiting strategy.

**Current State:**
- Basic 429 detection in Notion API calls
- No exponential backoff
- No rate limit tracking for SoundCloud downloads
- No rate limit tracking for Notion API

**Required Implementation:**
- Exponential backoff for 429 errors
- Rate limit tracking per API (Notion, SoundCloud, Eagle)
- Request throttling to prevent hitting limits
- Configurable rate limits per API

**Example:**
```python
class RateLimiter:
    def __init__(self, max_requests_per_minute: int = 60):
        self.max_requests = max_requests_per_minute
        self.requests = []
    
    def wait_if_needed(self):
        """Wait if rate limit would be exceeded"""
        pass

def exponential_backoff_retry(func, max_retries: int = 5):
    """Retry with exponential backoff"""
    pass
```

**Priority:** 🟠 **HIGH** - Will cause failures on large batches.

---

### 4. **Progress Persistence & Reporting** (MEDIUM PRIORITY)

**Gap:** Progress is logged but not persisted or easily queryable.

**Required Implementation:**
- SQLite or JSON file for progress tracking
- Real-time progress percentage calculation
- Estimated time remaining
- Success/failure rate tracking
- Detailed error logs per track

**Example:**
```python
class ProgressTracker:
    def __init__(self, total_tracks: int):
        self.total = total_tracks
        self.processed = 0
        self.failed = 0
        self.skipped = 0
    
    def update(self, track_id: str, status: str, error: str = None):
        """Update progress for a track"""
        pass
    
    def get_summary(self) -> dict:
        """Get current progress summary"""
        pass
```

**Priority:** 🟡 **MEDIUM** - Nice to have for monitoring.

---

### 5. **Concurrent Processing Improvements** (MEDIUM PRIORITY)

**Gap:** Concurrency exists but may not be optimal for 500 tracks.

**Current State:**
- Max concurrency: 4 (configurable)
- Sequential processing within batch
- No thread pool or async processing

**Required Implementation:**
- Thread pool for parallel downloads
- Async processing for I/O-bound operations
- Configurable concurrency per operation type
- Resource management (memory, disk space)

**Example:**
```python
from concurrent.futures import ThreadPoolExecutor

def process_batch_parallel(tracks: List[dict], max_workers: int = 4):
    """Process tracks in parallel using thread pool"""
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(process_track, track) for track in tracks]
        results = [f.result() for f in futures]
    return results
```

**Priority:** 🟡 **MEDIUM** - Will significantly speed up processing.

---

### 6. **Memory Management** (MEDIUM PRIORITY)

**Gap:** No memory management for large batches.

**Required Implementation:**
- Stream processing (don't load all 500 tracks into memory)
- Garbage collection hints
- Memory usage monitoring
- Batch size optimization based on available memory

**Priority:** 🟡 **MEDIUM** - May cause issues with 500 tracks.

---

### 7. **Validation & Pre-flight Checks** (MEDIUM PRIORITY)

**Gap:** Limited validation before starting large batch.

**Required Implementation:**
- Check available disk space
- Verify API credentials and rate limits
- Validate playlist URL format
- Estimate processing time
- Check for existing tracks in Notion (avoid duplicates)

**Example:**
```python
def preflight_checks(playlist_url: str, estimated_tracks: int) -> dict:
    """Run pre-flight checks before processing"""
    checks = {
        "disk_space": check_disk_space(estimated_tracks * 50_000_000),  # ~50MB per track
        "api_credentials": verify_api_credentials(),
        "playlist_valid": validate_playlist_url(playlist_url),
        "notion_duplicates": check_existing_tracks(playlist_url),
    }
    return checks
```

**Priority:** 🟡 **MEDIUM** - Prevents wasted processing time.

---

### 8. **Error Recovery & Retry Strategy** (MEDIUM PRIORITY)

**Gap:** Basic retry exists but no sophisticated error recovery.

**Required Implementation:**
- Categorize errors (transient vs permanent)
- Different retry strategies per error type
- Dead letter queue for permanently failed tracks
- Automatic retry of transient failures
- Manual review queue for ambiguous failures

**Example:**
```python
class ErrorCategorizer:
    TRANSIENT_ERRORS = [429, 503, 500, 502, 503]
    PERMANENT_ERRORS = [404, 403, 400]
    
    def categorize(self, error: Exception) -> str:
        """Categorize error as transient or permanent"""
        pass

def retry_with_strategy(func, error_category: str, max_retries: int):
    """Retry with strategy based on error category"""
    pass
```

**Priority:** 🟡 **MEDIUM** - Improves success rate.

---

### 9. **Deduplication Across Playlist** (LOW PRIORITY - Mostly Done)

**Gap:** Deduplication exists but may need playlist-specific logic.

**Current State:**
- ✅ Cross-batch deduplication exists
- ✅ In-batch deduplication exists
- ✅ Pre-download duplicate checking

**Potential Enhancement:**
- Deduplicate tracks within playlist before adding to Notion
- Check for duplicates across entire library before processing
- Batch duplicate check for all 500 tracks upfront

**Priority:** 🟢 **LOW** - Mostly implemented, minor enhancements needed.

---

### 10. **CLI Interface for Playlist Processing** (LOW PRIORITY)

**Gap:** No dedicated CLI command for playlist processing.

**Required Implementation:**
- `--playlist-url` argument
- `--playlist-name` argument (optional)
- `--max-tracks` argument (default: 500)
- Integration with existing batch processing

**Example:**
```bash
python soundcloud_download_prod_merge-2.py \
    --playlist-url "https://soundcloud.com/user/sets/playlist-id" \
    --playlist-name "My Playlist" \
    --max-tracks 500 \
    --mode batch
```

**Priority:** 🟢 **LOW** - Convenience feature.

---

## Implementation Priority Summary

| Priority | Feature | Estimated Effort | Impact |
|----------|---------|------------------|--------|
| 🔴 **CRITICAL** | Playlist URL Processing | 4-6 hours | Blocks all playlist processing |
| 🟠 **HIGH** | Resume/Checkpoint System | 3-4 hours | Essential for reliability |
| 🟠 **HIGH** | Rate Limiting & Backoff | 2-3 hours | Prevents API failures |
| 🟡 **MEDIUM** | Progress Persistence | 2-3 hours | Better monitoring |
| 🟡 **MEDIUM** | Concurrent Processing | 3-4 hours | Speed improvement |
| 🟡 **MEDIUM** | Memory Management | 2-3 hours | Stability for large batches |
| 🟡 **MEDIUM** | Pre-flight Checks | 1-2 hours | Prevents wasted time |
| 🟡 **MEDIUM** | Error Recovery | 2-3 hours | Better success rate |
| 🟢 **LOW** | Playlist Deduplication | 1-2 hours | Minor enhancement |
| 🟢 **LOW** | CLI Interface | 1 hour | Convenience |

**Total Estimated Effort:** 21-29 hours

---

## Recommended Implementation Order

1. **Phase 1: Core Functionality** (Critical Path)
   - Playlist URL Processing
   - Basic CLI integration
   - Test with small playlist (10-20 tracks)

2. **Phase 2: Reliability** (High Priority)
   - Resume/Checkpoint System
   - Rate Limiting & Backoff
   - Error Recovery improvements

3. **Phase 3: Performance & Monitoring** (Medium Priority)
   - Concurrent Processing
   - Progress Persistence
   - Memory Management
   - Pre-flight Checks

4. **Phase 4: Polish** (Low Priority)
   - Playlist-specific deduplication
   - Enhanced CLI features
   - Documentation

---

## Testing Strategy

1. **Unit Tests:**
   - Playlist URL extraction
   - Checkpoint save/load
   - Rate limiter logic
   - Error categorization

2. **Integration Tests:**
   - Small playlist (10 tracks)
   - Medium playlist (50 tracks)
   - Large playlist (200 tracks)
   - Full playlist (500 tracks)

3. **Failure Scenario Tests:**
   - Interrupt during processing (resume test)
   - Rate limit hit (backoff test)
   - Network failure (retry test)
   - Disk full (error handling test)

---

## Notes

- Current batch processing can handle 500 tracks, but needs playlist URL processing first
- Deduplication is mostly complete, just needs playlist-specific enhancements
- Error handling exists but needs refinement for large batches
- Consider using a task queue (Celery, RQ) for very large playlists (1000+ tracks)



































































































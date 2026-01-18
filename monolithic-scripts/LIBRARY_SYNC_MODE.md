# Full Library Sync Mode - Documentation

## Overview

The **Full Library Sync Mode** is a new processing mode added to `soundcloud_download_prod_merge-2.py` that enables comprehensive library synchronization with conflict-aware distributed locking. This mode is designed to safely process large numbers of tracks while allowing multiple instances of the script to run concurrently without conflicts.

## Key Features

### 1. Single-Query Architecture
Unlike the incremental batch mode that makes repeated queries, library-sync mode:
- Queries ALL matching tracks from Notion in a single paginated request
- Pre-caches the entire Eagle library for efficient deduplication lookups
- Reduces API calls and improves overall throughput

### 2. Distributed Process Locking
When multiple instances run simultaneously, the system uses Notion-based locking:
- **Lock Format**: `PID:HOSTNAME:UUID:TIMESTAMP`
- **Lock Property**: Stored in "Processing Lock" text property in Notion
- **Lock Timeout**: 30 minutes (configurable)
- **Automatic Cleanup**: Stale locks from crashed processes are cleaned up

### 3. Conflict-Aware Processing
Each track is processed with lock management:
1. Attempt to acquire lock before processing
2. Skip if locked by another process
3. Re-verify track status after lock acquisition (double-check)
4. Release lock after processing (success or failure)

## Usage

### Basic Commands

```bash
# Full library sync (all unprocessed tracks)
python soundcloud_download_prod_merge-2.py --mode library-sync

# Sync with limit
python soundcloud_download_prod_merge-2.py --mode library-sync --limit 50

# Parallel processing (4 workers)
python soundcloud_download_prod_merge-2.py --mode library-sync --parallel

# Custom worker count
python soundcloud_download_prod_merge-2.py --mode library-sync --parallel --workers 8

# Different filter criteria
python soundcloud_download_prod_merge-2.py --mode library-sync --filter all
python soundcloud_download_prod_merge-2.py --mode library-sync --filter missing_eagle

# Skip lock cleanup
python soundcloud_download_prod_merge-2.py --mode library-sync --no-cleanup
```

### Utility Commands

```bash
# Check library status
python soundcloud_download_prod_merge-2.py --mode status

# Clean up stale locks manually
python soundcloud_download_prod_merge-2.py --mode cleanup
```

## Filter Criteria

| Filter | Description |
|--------|-------------|
| `unprocessed` | Tracks with DL=False and no file paths (default) |
| `all` | All tracks with SoundCloud URLs regardless of status |
| `missing_eagle` | Downloaded tracks (DL=True) missing Eagle File ID |

## Notion Database Setup

### Required Property for Locking

To enable the distributed locking feature, add a new property to your Notion database:

1. Open your **Music Tracks** database in Notion
2. Click **+** to add a new property
3. Name it: **Processing Lock**
4. Type: **Text**
5. Save

The script will automatically detect this property and use it for locking. If the property doesn't exist, locking is disabled and the script continues without conflict prevention.

### Lock Value Format

When a track is locked, the property contains:
```
12345:MacBook-Pro:a1b2c3d4:2026-01-16T10:30:00+00:00
```

Components:
- `12345` - Process ID (PID)
- `MacBook-Pro` - Hostname
- `a1b2c3d4` - Unique process UUID
- `2026-01-16T10:30:00+00:00` - Lock acquisition timestamp (ISO format)

## Environment Variables

### Process Locking Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `PROCESS_LOCK_ENABLED` | `1` | Enable/disable locking (`1`/`0`) |
| `PROCESS_LOCK_TIMEOUT_MINUTES` | `30` | Lock expiration time in minutes |

### Concurrency Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `SC_MAX_CONCURRENCY` | `4` | Default number of parallel workers |
| `SC_ENABLE_PARALLEL_BATCH` | `1` | Enable parallel processing in batch mode |

## Concurrent Operation Scenarios

### Scenario 1: Library Sync + Batch Mode

Running simultaneously:
- Terminal 1: `python soundcloud_download_prod_merge-2.py --mode library-sync`
- Terminal 2: `python soundcloud_download_prod_merge-2.py --mode batch --limit 10`

**Result**: Both processes run safely. If they attempt to process the same track, one will acquire the lock and the other will skip it.

### Scenario 2: Multiple Library Sync Instances

Running on different machines:
- Machine A: `python soundcloud_download_prod_merge-2.py --mode library-sync --filter unprocessed`
- Machine B: `python soundcloud_download_prod_merge-2.py --mode library-sync --filter unprocessed`

**Result**: Tracks are distributed between instances. Each machine processes different tracks with no duplicates.

### Scenario 3: Recovery from Crashed Process

If a process crashes while holding locks:
1. Locks will expire after 30 minutes automatically
2. Or run cleanup manually: `python soundcloud_download_prod_merge-2.py --mode cleanup`

## Output Structure

Library sync uses the new 3-file output structure:

| Output | Location | Purpose |
|--------|----------|---------|
| WAV | Eagle Library (`Playlists/{playlist}/`) | Primary lossless format |
| AIFF | Eagle Library (`Playlists/{playlist}/`) | Secondary lossless format |
| WAV Copy | `playlist-tracks/{playlist}/` | Playlist-organized copies |

## Return Codes

| Code | Meaning |
|------|---------|
| `0` | Success (at least some tracks processed) |
| `1` | Complete failure (errors, no tracks processed) |
| `2` | No tracks processed (library may be up to date) |

## Logging

Library sync provides detailed logging:

```
═══════════════════════════════════════════════════════════════════════════════
📚 FULL LIBRARY SYNC MODE
═══════════════════════════════════════════════════════════════════════════════
🔧 Filter: unprocessed
🔧 Max tracks: unlimited
🔧 Parallel: False (workers: 4)
🔧 Process ID: 12345:MacBook-Pro:a1b2c3d4
═══════════════════════════════════════════════════════════════════════════════

🧹 Step 1: Cleaning up stale processing locks...
🧹 Cleared 2 stale locks

🦅 Step 2: Pre-caching Eagle library...
   ✅ Cached 15432 Eagle items

📋 Step 3: Querying all unprocessed tracks from Notion...
   ✅ Found 47 tracks matching criteria

📋 TRACKS TO PROCESS (47 total):
   1. Track Name by Artist
   2. Another Track by Another Artist
   ...

🚀 Step 4: Processing 47 tracks...
🔄 Using sequential processing

──────────────────────────────────────────────────────
🎵 [1/47] Processing: Track Name by Artist
──────────────────────────────────────────────────────
...

═══════════════════════════════════════════════════════════════════════════════
📚 FULL LIBRARY SYNC COMPLETE
═══════════════════════════════════════════════════════════════════════════════
   Total Found:        47
   Processed:          45
   Failed:             1
   Skipped (locked):   0
   Skipped (done):     1
   Duration:           1234.5s
═══════════════════════════════════════════════════════════════════════════════
```

## Best Practices

1. **Initial Setup**: Use `--mode library-sync` for initial library migration
2. **Ongoing Maintenance**: Use `--mode batch` for incremental processing
3. **Scheduled Jobs**: Safe to run library-sync in cron jobs on multiple machines
4. **Large Libraries**: Use `--parallel` for faster processing
5. **Debugging**: Use `--debug` flag for verbose logging
6. **Lock Issues**: Run `--mode cleanup` if processes crash frequently

## Troubleshooting

### Tracks Stuck with Locks

```bash
# Check status first
python soundcloud_download_prod_merge-2.py --mode status

# Clean up stale locks
python soundcloud_download_prod_merge-2.py --mode cleanup
```

### Processing Lock Property Missing

If you see:
```
Processing Lock property not found in database - locking disabled
```

Add the "Processing Lock" text property to your Notion database (see setup section).

### High Skip Rate (Locked)

If many tracks are being skipped as locked:
1. Another process is running - this is normal
2. Previous process crashed - run `--mode cleanup`
3. Lock timeout too short - increase `PROCESS_LOCK_TIMEOUT_MINUTES`

## Unified State Tracking System

As of 2026-01-16, all processing modes use a **Unified State Tracking System** that ensures consistent:

### 1. Deduplication Across All Modes

Every track processed goes through:
- **Batch-level deduplication** (`dedupe_within_batch()`) - Merges obvious duplicates within queried batches
- **Per-track deduplication** (`try_merge_duplicates_for_page()`) - Checks each track against database before processing
- **Eagle pre-download check** (`eagle_find_best_matching_item()`) - Prevents duplicate imports

### 2. Error Recording

All errors are classified and recorded to Notion's "Audio Processing Status" property:

| Error Type | Description |
|------------|-------------|
| `SC_404` | SoundCloud track not found |
| `SC_Geo_Blocked` | Region restricted content |
| `Download_Failed` | General download failure |
| `Conversion_Failed` | FFmpeg conversion error |
| `Eagle_Import_Failed` | Eagle import error |
| `Notion_Update_Failed` | Notion API error |
| `Dedup_Failed` | Deduplication error |
| `Lock_Conflict` | Locked by another process |

### 3. Completion Marking

The `mark_track_complete()` function ensures:
- DL checkbox only set when files exist OR Eagle ID exists
- All file paths written atomically
- Verification that track won't be reprocessed after update

### 4. TrackResult Object

All modes return consistent results via the `TrackResult` dataclass:
- `page_id`, `title`, `artist`
- `status` (TrackStatus enum)
- `file_paths` (wav, aiff, m4a, playlist_wav)
- `eagle_item_id`, `eagle_aiff_item_id`
- `error_type`, `error_message`
- `dedupe_redirected`, `dedupe_keeper_id`
- `processing_time_seconds`

## Version History

- **2026-01-16**: Initial release of library-sync mode with distributed locking
- **2026-01-16**: Added status and cleanup modes
- **2026-01-16**: Updated to 3-file output structure (WAV, AIFF, WAV copy)
- **2026-01-16**: Implemented Unified State Tracking System across all modes

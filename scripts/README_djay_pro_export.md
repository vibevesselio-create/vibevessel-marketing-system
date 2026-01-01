# djay Pro Library Export Script

## Overview

Comprehensive Python script to extract **ALL data** from djay Pro's SQLite database (`MediaLibrary.db`) and export it to structured CSV and JSON formats.

## Features

- ✅ **Complete Data Extraction**: Extracts all collections from the YapDatabase structure
- ✅ **Dual Format Export**: Exports to both JSON (complete structure) and CSV (per-collection files)
- ✅ **Media Items Consolidation**: Creates a consolidated CSV of all media items (tracks)
- ✅ **Read-Only Access**: Safely accesses database without locking issues
- ✅ **System-Aligned**: Follows workspace logging and configuration standards
- ✅ **Comprehensive Metadata**: Extracts BPM, key, duration, file paths, playlists, sessions, and more

## Requirements

- Python 3.x
- SQLite3 (standard library)
- djay Pro database file at default location or custom path

## Usage

### Basic Usage

```bash
# Export all data to default output directory
python scripts/djay_pro_library_export.py

# Or make executable and run directly
./scripts/djay_pro_library_export.py
```

### Advanced Options

```bash
# Custom database path
python scripts/djay_pro_library_export.py --db-path "/path/to/MediaLibrary.db"

# Custom output directory
python scripts/djay_pro_library_export.py --output-dir "./my_export"

# Export only JSON (skip CSV)
python scripts/djay_pro_library_export.py --json-only

# Export only CSV (skip JSON)
python scripts/djay_pro_library_export.py --csv-only

# Enable debug logging
python scripts/djay_pro_library_export.py --debug
```

## Output Files

The script generates the following files in the output directory:

### JSON Export
- `djay_pro_library_export_YYYYMMDD_HHMMSS.json` - Complete database structure with all collections

### CSV Exports (per collection)
- `djay_pro_[table_name]_YYYYMMDD_HHMMSS.csv` - One CSV file per database table/collection
- `djay_pro_media_items_YYYYMMDD_HHMMSS.csv` - Consolidated media items (tracks) with standardized fields

### Summary Report
- `djay_pro_export_summary_YYYYMMDD_HHMMSS.json` - Export statistics and metadata

## Configuration

The script uses workspace-standard configuration:

1. **Environment Variables:**
   - `DJAY_DB_PATH` - Custom database path (default: `/Users/brianhellemn/Music/djay/djay Media Library.djayMediaLibrary/MediaLibrary.db`)
   - `DJAY_EXPORT_DIR` - Custom output directory (default: `./djay_pro_export`)
   - `LOG_LEVEL` - Logging level (default: `INFO`)

2. **Unified Config:**
   - `djay_db_path` - Database path override
   - `djay_export_dir` - Output directory override

## Data Structure

### Media Items (Tracks)
The script extracts and standardizes the following fields:
- `title` - Track title
- `artist` - Artist name
- `album` - Album name
- `bpm` - Beats per minute
- `key` - Musical key
- `duration` - Track duration
- `file_path` - File location
- `genre` - Genre
- `year` - Release year
- `bitrate` - Audio bitrate
- `sample_rate` - Sample rate
- `play_count` - Number of plays
- `rating` - User rating
- `date_added` - Date added to library
- `last_played` - Last play date

### Collections Extracted
- All database tables/collections
- Media items (tracks)
- Playlists
- DJ sessions
- User data (ratings, tags, cue points)
- CloudKit sync records
- MIDI mappings
- And more...

## Integration with Music Sync Workflow

This script is designed to integrate with the **Music Library Unified Sync Orchestrator**:

1. **Ingest Phase**: Extract djay Pro library data → Notion
2. **Sync Phase**: Use CSV exports for auto-import folder integration
3. **Validation**: Compare exported data with Notion Music Tracks database

## Error Handling

- ✅ Database file not found → Clear error message
- ✅ Database locked → Read-only mode prevents locking
- ✅ Missing tables → Graceful handling with warnings
- ✅ Binary data → Automatic encoding/string conversion
- ✅ Large datasets → Efficient memory usage

## Example Output

```
================================================================================
djay Pro Library Complete Export
================================================================================
Database: /Users/brianhellemn/Music/djay/djay Media Library.djayMediaLibrary/MediaLibrary.db
Output: ./djay_pro_export

✅ Connected to database: /Users/.../MediaLibrary.db
📊 Found 21 tables
📦 Processing table: mediaItem
   ✓ Extracted 12770 rows from mediaItem
📦 Processing table: playlist
   ✓ Extracted 27 rows from playlist
...
✅ Exported JSON: ./djay_pro_export/djay_pro_library_export_20250127_120000.json
✅ Exported CSV: ./djay_pro_export/djay_pro_mediaItem_20250127_120000.csv (12770 rows)
✅ Exported media items CSV: ./djay_pro_export/djay_pro_media_items_20250127_120000.csv

================================================================================
EXPORT COMPLETE
================================================================================
Total collections: 21
Total rows: 85128
Media items: 12770
Playlists: 27
Sessions: 40
Summary: ./djay_pro_export/djay_pro_export_summary_20250127_120000.json
================================================================================
```

## Notes

- The script uses **read-only** database access to avoid conflicts with djay Pro
- YapDatabase key-value structure is preserved in JSON export
- CSV exports flatten the data structure for easy import into spreadsheets/Notion
- Binary data (waveforms, etc.) is handled gracefully
- All timestamps are in UTC ISO format

## Troubleshooting

### Database Not Found
```
❌ Database file not found: /path/to/MediaLibrary.db
```
**Solution**: Check the database path. Default location is:
`~/Music/djay/djay Media Library.djayMediaLibrary/MediaLibrary.db`

### Database Locked
The script uses read-only mode, but if issues persist:
1. Close djay Pro application
2. Run the export script
3. Reopen djay Pro

### No Data Extracted
If collections show 0 rows:
- Verify database is not corrupted
- Check database file permissions
- Enable debug logging: `--debug`

## Related Documentation

- [Research Summary](../docs/research/djay-pro-library-csv-export-research.md)
- [Music Sync Orchestrator](https://www.notion.so/Music-Sync-Music-Library-Unified-Sync-Orchestrator-2d6e73616c27814ba4e1db6aaef09bde)
- [djay Pro Library Technical Spec](https://www.notion.so/djay-Pro-2b5e73616c278105a927da9bb3e1fef7)


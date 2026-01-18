# VIBES Tracks Relocation Strategy

## Overview

This document outlines the strategy for relocating tracks from VIBES directories to the correct playlist folders within the `playlist-tracks` directory structure.

## Source Directories

1. `/Volumes/VIBES/Playlists` - Currently empty (only contains .DS_Store)
2. `/Volumes/VIBES/Apple-Music-Auto-Add` - Contains WAV files (hundreds of tracks)
3. `/Volumes/VIBES/Djay-Pro-Auto-Import` - Contains M4A files (hundreds of tracks)

## Target Directory Structure

```
/Volumes/SYSTEM_SSD/Dropbox/Music/playlists/playlist-tracks/
├── {playlist_name_1}/
│   ├── track1.wav
│   ├── track2.m4a
│   └── ...
├── {playlist_name_2}/
│   └── ...
└── Uncategorized/
    └── ...
```

## Relocation Method

### Approach: Notion-Based Playlist Matching

The most effective and system-compliant method is to:

1. **Match files to Notion tracks** by filename/title similarity
2. **Retrieve playlist assignments** from Notion database relations
3. **Move files** to appropriate playlist folders based on Notion data

### Why This Approach?

1. **System Compliance**: Uses the existing Notion database as the source of truth for playlist assignments
2. **Accuracy**: Leverages existing track metadata and playlist relations already stored in Notion
3. **Consistency**: Follows the same pattern used by `soundcloud_download_prod_merge-2.py` for organizing tracks
4. **Maintainability**: Aligns with the existing codebase patterns and workflows

### Implementation Details

#### File Matching Strategy

1. **Clean filename** (remove extension, normalize)
2. **Query Notion** for tracks with matching titles
3. **Calculate similarity score** using SequenceMatcher
4. **Match threshold**: 70% similarity minimum

#### Playlist Assignment Logic

1. **Extract playlist names** from track's Notion properties:
   - Check relation properties (links to playlist pages)
   - Check rich_text properties (direct text input)
   - Check select/multi_select properties
2. **Use first playlist** if multiple playlists assigned
3. **Fallback to "Uncategorized"** if no playlist found or no Notion match

#### File Handling

- **Preserve original filenames** (no renaming)
- **Create playlist folders** as needed
- **Skip files** that already exist at destination
- **Sanitize folder names** (remove invalid filesystem characters)

## Script: `relocate_vibes_tracks_to_playlist_folders.py`

### Features

- ✅ Dry-run mode for preview
- ✅ Notion track matching with similarity scoring
- ✅ Playlist assignment from Notion relations
- ✅ Safe file operations (skip existing, create directories)
- ✅ Comprehensive logging and error handling
- ✅ Progress tracking and summary statistics

### Usage

```bash
# Preview changes (recommended first step)
python scripts/relocate_vibes_tracks_to_playlist_folders.py --dry-run

# Execute relocation
python scripts/relocate_vibes_tracks_to_playlist_folders.py --execute
```

### Process Flow

1. **Scan** source directories for audio files
2. **Match** each file to Notion track by filename similarity
3. **Retrieve** playlist assignments from matched track
4. **Generate** relocation plan with destinations
5. **Execute** file moves (or preview in dry-run mode)
6. **Report** summary statistics

### Safety Features

- **Dry-run mode**: Preview all changes before executing
- **Skip existing**: Won't overwrite files already at destination
- **Error handling**: Continues processing even if individual files fail
- **Logging**: Detailed logs for troubleshooting

## Alternative Approaches Considered

### 1. Manual Folder Matching
- ❌ **Rejected**: Too time-consuming, error-prone, doesn't scale

### 2. Filename Pattern Matching
- ❌ **Rejected**: Filenames don't consistently contain playlist information

### 3. Metadata-Based Matching (ID3 tags)
- ⚠️ **Considered**: Would require reading metadata from each file, slower and less reliable than Notion

### 4. Notion-Based Matching (Selected)
- ✅ **Selected**: Most accurate, leverages existing system, maintains consistency

## Expected Outcomes

### Files Processed
- **Apple-Music-Auto-Add**: ~500+ WAV files
- **Djay-Pro-Auto-Import**: ~100+ M4A files
- **Total**: ~600+ audio files

### Distribution
- Files matched to Notion tracks → Assigned to correct playlists
- Files not matched → Moved to "Uncategorized" folder
- Files already at destination → Skipped

### Benefits

1. **Organization**: Tracks properly organized by playlist
2. **Consistency**: Aligned with existing system structure
3. **Automation**: Reduces manual effort
4. **Traceability**: All moves logged and tracked

## Next Steps

1. **Review** the script and strategy
2. **Run dry-run** to preview changes
3. **Verify** matches look correct
4. **Execute** relocation
5. **Verify** files are in correct locations
6. **Clean up** source directories if desired

## Notes

- The script preserves original filenames
- Playlist folder names are sanitized for filesystem compatibility
- The script can be run multiple times safely (skips existing files)
- Source files are moved (not copied) to preserve disk space

# Dropbox Music Cleanup - Executive Summary

**Date:** 2026-01-06  
**Status:** 📋 READY FOR REVIEW

## Quick Overview

The Dropbox Music directory (`/Volumes/SYSTEM_SSD/Dropbox/Music`) contains **~112GB** of music files that need cleanup, deduplication, and reorganization to align with the production workflow.

## Key Findings

### Current State
- **49GB** in `wav-tracks/` (588 files) - Legacy WAV files
- **45GB** in `m4A-tracks/` (1,664 files) - Legacy M4A files  
- **15GB** in `playlists/` - Metadata files (CSV/JSON)
- **3 root-level files** - Need relocation
- **3 empty directories** - Can be removed

### Proposed Solution

**New Unified Structure:**
```
/Volumes/SYSTEM_SSD/Dropbox/Music/
├── processed/          # Workflow output files (replaces VIBES paths)
│   ├── playlists/     # Playlist-organized AIFF/M4A
│   ├── backups/       # M4A and WAV backups
│   └── temp/          # Temporary processing files
├── legacy/            # Old files for deduplication
├── user-content/      # User-created mixes/mashups
└── metadata/          # Library metadata files
```

**Updated Configuration:**
- `OUT_DIR` → `/Volumes/SYSTEM_SSD/Dropbox/Music/processed/playlists`
- `BACKUP_DIR` → `/Volumes/SYSTEM_SSD/Dropbox/Music/processed/backups/m4a`
- `WAV_BACKUP_DIR` → `/Volumes/SYSTEM_SSD/Dropbox/Music/processed/backups/wav`
- `EAGLE_LIBRARY_PATH` → **UNCHANGED** (`/Volumes/VIBES/Music-Library-2.library`)

## Action Items

1. ✅ **Strategy Document Created** - Full plan in `DROPBOX_MUSIC_CLEANUP_AND_REORGANIZATION_STRATEGY.md`
2. ⏳ **Review Strategy** - Review and approve reorganization plan
3. ⏳ **Create Backup** - Backup all files before migration
4. ⏳ **Implement Scripts** - Create deduplication and migration scripts
5. ⏳ **Test Migration** - Test on small subset first
6. ⏳ **Execute Migration** - Full migration with verification
7. ⏳ **Update Configuration** - Update workflow configs with new paths

## Estimated Impact

- **Storage Savings**: ~50-70GB (after deduplication)
- **Organization**: Unified structure aligned with workflow
- **Maintenance**: Easier to manage and maintain
- **Workflow**: Seamless integration with existing processes

## Risk Level

**Medium** - Requires careful execution but low risk with proper backup and testing.

---

**See Full Strategy**: `DROPBOX_MUSIC_CLEANUP_AND_REORGANIZATION_STRATEGY.md`























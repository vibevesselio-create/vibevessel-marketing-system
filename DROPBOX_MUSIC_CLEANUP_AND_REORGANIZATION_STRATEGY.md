# Dropbox Music Cleanup and Reorganization Strategy

**Date:** 2026-01-06  
**Status:** 📋 PLANNING  
**Target:** `/Volumes/SYSTEM_SSD/Dropbox/Music`

## Executive Summary

This document outlines a comprehensive strategy to cleanup, deduplicate, and reorganize the Dropbox Music directory structure to align with the production music download workflow while maintaining the Eagle library import location unchanged.

## Current State Analysis

### Directory Structure and Sizes

| Directory/File | Size | Contents | Status |
|---------------|------|----------|--------|
| **Root Level Files** | ~60MB | 2 WAV, 1 M4A | ⚠️ Needs relocation |
| `wav-tracks/` | 49GB | 588 WAV files | ⚠️ Needs deduplication & reorganization |
| `m4A-tracks/` | 45GB | 1,664 M4A files | ⚠️ Needs deduplication & reorganization |
| `mixes/` | 905MB | User-created mix WAVs | ✅ Keep as-is |
| `mashups/` | 2.2GB | User-created mashup WAVs | ✅ Keep as-is |
| `playlists/` | 15GB | CSV/JSON metadata files | ✅ Keep as-is |
| `Spotify Library/` | 5MB | 132 CSV playlist exports | ✅ Keep as-is |
| `SoundCloud Library/` | 1MB | 14 JSON playlist exports | ✅ Keep as-is |
| `djaypro-library/` | 1.7MB | Music.csv file | ✅ Keep as-is |
| `artist-json-files/` | 0B | Empty | ⚠️ Can remove |
| `rekordbox-library/` | 0B | Empty | ⚠️ Can remove |
| `stems/` | 0B | Empty | ⚠️ Can remove |

### Current Workflow Output Directories

The production workflow currently uses:
- **OUT_DIR**: `/Volumes/VIBES/Playlists` - Playlist-organized AIFF/M4A files
- **BACKUP_DIR**: `/Volumes/VIBES/Djay-Pro-Auto-Import` - M4A backup files
- **WAV_BACKUP_DIR**: `/Volumes/VIBES/Apple-Music-Auto-Add` - WAV files for Serato
- **EAGLE_WAV_TEMP_DIR**: `/Volumes/PROJECTS-MM1/OTHER/TEMP` - Temporary WAV for Eagle import
- **EAGLE_LIBRARY_PATH**: `/Volumes/VIBES/Music-Library-2.library` - **UNCHANGED** (primary output)

## Proposed Reorganization Strategy

### Phase 1: Directory Structure Cleanup

#### 1.1 Remove Empty Directories
```bash
# Remove empty directories that are no longer used
rmdir /Volumes/SYSTEM_SSD/Dropbox/Music/artist-json-files
rmdir /Volumes/SYSTEM_SSD/Dropbox/Music/rekordbox-library
rmdir /Volumes/SYSTEM_SSD/Dropbox/Music/stems
```

#### 1.2 Relocate Root Level Files
Move root-level audio files to appropriate directories:
- `Take Care In Your Dreaming.wav` → `wav-tracks/` (temporary, will be processed)
- `82 92 feat Mac Miller.wav` → `wav-tracks/` (temporary, will be processed)
- `NO CAP.m4a` → `m4A-tracks/` (temporary, will be processed)

### Phase 2: Deduplication Strategy

#### 2.1 Identify Duplicates

**Strategy:**
1. **Audio Fingerprinting**: Use audio fingerprinting to identify true duplicates (same audio content, different filenames)
2. **Filename Matching**: Identify files with similar names but different formats
3. **Eagle Library Cross-Reference**: Check against Eagle library to identify files already imported
4. **Notion Database Cross-Reference**: Check against Notion database for processed tracks

**Tools Required:**
- Audio fingerprinting library (e.g., `dejavu`, `acoustid`)
- File hash comparison (MD5/SHA256)
- Eagle API integration for cross-referencing
- Notion API integration for track metadata

#### 2.2 Deduplication Process

**Step 1: Create File Inventory**
```python
# Generate comprehensive inventory of all audio files
- File path
- File size
- File hash (MD5/SHA256)
- Audio fingerprint
- Metadata (title, artist, duration, BPM, key)
- Format (WAV, M4A, AIFF)
- Last modified date
```

**Step 2: Group by Audio Fingerprint**
- Group files with identical audio fingerprints
- Keep highest quality version (AIFF > WAV > M4A)
- Keep most recent version if quality is equal
- Mark duplicates for removal

**Step 3: Cross-Reference with Eagle**
- Query Eagle library for existing files
- Match by filename, fingerprint, or metadata
- Avoid re-importing duplicates

**Step 4: Cross-Reference with Notion**
- Query Notion database for processed tracks
- Match by URL, title, artist, or fingerprint
- Update Notion with file paths if missing

### Phase 3: Reorganization Structure

#### 3.1 New Directory Structure

**Proposed Structure:**
```
/Volumes/SYSTEM_SSD/Dropbox/Music/
├── processed/                    # NEW: Workflow-processed files
│   ├── playlists/               # Playlist-organized files (from OUT_DIR)
│   │   ├── Unassigned/          # Tracks without playlists
│   │   ├── [Playlist Name 1]/  # Playlist folders
│   │   └── [Playlist Name N]/
│   ├── backups/                 # Backup files
│   │   ├── m4a/                 # M4A backups (from BACKUP_DIR)
│   │   └── wav/                 # WAV backups (from WAV_BACKUP_DIR)
│   └── temp/                    # Temporary files for processing
│       └── eagle-import/        # WAV files for Eagle import
├── legacy/                      # NEW: Legacy files to be reviewed
│   ├── wav-tracks/             # Old WAV files (to be deduplicated)
│   └── m4a-tracks/              # Old M4A files (to be deduplicated)
├── user-content/                # NEW: User-created content
│   ├── mixes/                   # User-created mixes
│   └── mashups/                 # User-created mashups
├── metadata/                    # NEW: Library metadata
│   ├── playlists/               # Playlist CSV/JSON files
│   ├── spotify/                 # Spotify library exports
│   ├── soundcloud/              # SoundCloud library exports
│   └── djaypro/                 # djay Pro library files
└── [other existing dirs]        # Keep other directories as-is
```

#### 3.2 Updated Workflow Configuration

**New Environment Variables:**
```bash
# Primary output directory (replaces OUT_DIR)
OUT_DIR=/Volumes/SYSTEM_SSD/Dropbox/Music/processed/playlists

# Backup directories (replaces BACKUP_DIR and WAV_BACKUP_DIR)
BACKUP_DIR=/Volumes/SYSTEM_SSD/Dropbox/Music/processed/backups/m4a
WAV_BACKUP_DIR=/Volumes/SYSTEM_SSD/Dropbox/Music/processed/backups/wav

# Temporary directory for Eagle import (replaces EAGLE_WAV_TEMP_DIR)
EAGLE_WAV_TEMP_DIR=/Volumes/SYSTEM_SSD/Dropbox/Music/processed/temp/eagle-import

# Eagle library path (UNCHANGED - primary output location)
EAGLE_LIBRARY_PATH=/Volumes/VIBES/Music-Library-2.library
```

### Phase 4: Migration Plan

#### 4.1 Pre-Migration Checklist

- [ ] Backup all existing files
- [ ] Verify Eagle library is accessible
- [ ] Verify Notion database is accessible
- [ ] Create deduplication script
- [ ] Test deduplication on small subset
- [ ] Create migration script
- [ ] Test migration on small subset

#### 4.2 Migration Steps

**Step 1: Create New Directory Structure**
```bash
mkdir -p /Volumes/SYSTEM_SSD/Dropbox/Music/processed/{playlists,backups/{m4a,wav},temp/eagle-import}
mkdir -p /Volumes/SYSTEM_SSD/Dropbox/Music/legacy/{wav-tracks,m4a-tracks}
mkdir -p /Volumes/SYSTEM_SSD/Dropbox/Music/user-content/{mixes,mashups}
mkdir -p /Volumes/SYSTEM_SSD/Dropbox/Music/metadata/{playlists,spotify,soundcloud,djaypro}
```

**Step 2: Move User Content**
```bash
# Move user-created content (preserve structure)
mv /Volumes/SYSTEM_SSD/Dropbox/Music/mixes /Volumes/SYSTEM_SSD/Dropbox/Music/user-content/
mv /Volumes/SYSTEM_SSD/Dropbox/Music/mashups /Volumes/SYSTEM_SSD/Dropbox/Music/user-content/
```

**Step 3: Move Metadata Files**
```bash
# Move metadata files
mv /Volumes/SYSTEM_SSD/Dropbox/Music/playlists/*.csv /Volumes/SYSTEM_SSD/Dropbox/Music/metadata/playlists/
mv /Volumes/SYSTEM_SSD/Dropbox/Music/playlists/*.json /Volumes/SYSTEM_SSD/Dropbox/Music/metadata/playlists/
mv /Volumes/SYSTEM_SSD/Dropbox/Music/Spotify\ Library/*.csv /Volumes/SYSTEM_SSD/Dropbox/Music/metadata/spotify/
mv /Volumes/SYSTEM_SSD/Dropbox/Music/SoundCloud\ Library/*.json /Volumes/SYSTEM_SSD/Dropbox/Music/metadata/soundcloud/
mv /Volumes/SYSTEM_SSD/Dropbox/Music/djaypro-library/* /Volumes/SYSTEM_SSD/Dropbox/Music/metadata/djaypro/
```

**Step 4: Move Legacy Files**
```bash
# Move legacy files for deduplication
mv /Volumes/SYSTEM_SSD/Dropbox/Music/wav-tracks /Volumes/SYSTEM_SSD/Dropbox/Music/legacy/
mv /Volumes/SYSTEM_SSD/Dropbox/Music/m4A-tracks /Volumes/SYSTEM_SSD/Dropbox/Music/legacy/m4a-tracks
```

**Step 5: Migrate Current Workflow Outputs**
```bash
# Migrate current workflow outputs to new structure
# This should be done carefully to preserve playlist organization
# Use rsync or similar to maintain structure
rsync -av /Volumes/VIBES/Playlists/ /Volumes/SYSTEM_SSD/Dropbox/Music/processed/playlists/
rsync -av /Volumes/VIBES/Djay-Pro-Auto-Import/ /Volumes/SYSTEM_SSD/Dropbox/Music/processed/backups/m4a/
rsync -av /Volumes/VIBES/Apple-Music-Auto-Add/ /Volumes/SYSTEM_SSD/Dropbox/Music/processed/backups/wav/
```

#### 4.3 Deduplication Process

**Step 1: Generate File Inventory**
- Scan all audio files in legacy directories
- Generate audio fingerprints
- Extract metadata
- Create inventory database

**Step 2: Identify Duplicates**
- Match by audio fingerprint
- Match by filename similarity
- Cross-reference with Eagle library
- Cross-reference with Notion database

**Step 3: Resolve Duplicates**
- Keep highest quality version
- Keep most recent version if quality equal
- Update Notion with correct file paths
- Remove duplicate files

**Step 4: Integrate Non-Duplicates**
- Move unique files to appropriate processed directories
- Organize by playlist if metadata available
- Update Notion with file paths
- Import to Eagle if not already imported

### Phase 5: Post-Migration Tasks

#### 5.1 Update Configuration Files

**Update `unified_config.py`:**
```python
"out_dir": get_env_value("OUT_DIR", "/Volumes/SYSTEM_SSD/Dropbox/Music/processed/playlists"),
"backup_dir": get_env_value("BACKUP_DIR", "/Volumes/SYSTEM_SSD/Dropbox/Music/processed/backups/m4a"),
"wav_backup_dir": get_env_value("WAV_BACKUP_DIR", "/Volumes/SYSTEM_SSD/Dropbox/Music/processed/backups/wav"),
"eagle_wav_temp_dir": get_env_value("EAGLE_WAV_TEMP_DIR", "/Volumes/SYSTEM_SSD/Dropbox/Music/processed/temp/eagle-import"),
```

**Update Environment Variables:**
```bash
export OUT_DIR="/Volumes/SYSTEM_SSD/Dropbox/Music/processed/playlists"
export BACKUP_DIR="/Volumes/SYSTEM_SSD/Dropbox/Music/processed/backups/m4a"
export WAV_BACKUP_DIR="/Volumes/SYSTEM_SSD/Dropbox/Music/processed/backups/wav"
export EAGLE_WAV_TEMP_DIR="/Volumes/SYSTEM_SSD/Dropbox/Music/processed/temp/eagle-import"
```

#### 5.2 Update Workflow Scripts

- Update all references to old directory paths
- Update file path generation logic
- Test workflow with new paths
- Verify playlist organization is maintained

#### 5.3 Cleanup Old Directories

After successful migration and verification:
- Archive old VIBES directories (if no longer needed)
- Remove empty legacy directories after deduplication
- Update documentation with new paths

## Implementation Scripts

### Script 1: Directory Structure Creation
```python
#!/usr/bin/env python3
"""
Create new directory structure for Dropbox Music reorganization
"""
from pathlib import Path

BASE_DIR = Path("/Volumes/SYSTEM_SSD/Dropbox/Music")

directories = [
    "processed/playlists",
    "processed/backups/m4a",
    "processed/backups/wav",
    "processed/temp/eagle-import",
    "legacy/wav-tracks",
    "legacy/m4a-tracks",
    "user-content/mixes",
    "user-content/mashups",
    "metadata/playlists",
    "metadata/spotify",
    "metadata/soundcloud",
    "metadata/djaypro",
]

for dir_path in directories:
    full_path = BASE_DIR / dir_path
    full_path.mkdir(parents=True, exist_ok=True)
    print(f"Created: {full_path}")
```

### Script 2: File Inventory Generator
```python
#!/usr/bin/env python3
"""
Generate comprehensive inventory of all audio files for deduplication
"""
import hashlib
import json
from pathlib import Path
from typing import Dict, List

def generate_file_inventory(directory: Path) -> List[Dict]:
    """Generate inventory of all audio files in directory"""
    inventory = []
    audio_extensions = {'.wav', '.m4a', '.aiff', '.mp3', '.flac'}
    
    for file_path in directory.rglob('*'):
        if file_path.suffix.lower() in audio_extensions and file_path.is_file():
            # Calculate file hash
            with open(file_path, 'rb') as f:
                file_hash = hashlib.md5(f.read()).hexdigest()
            
            # Get file metadata
            stat = file_path.stat()
            
            inventory.append({
                'path': str(file_path),
                'name': file_path.name,
                'size': stat.st_size,
                'hash': file_hash,
                'modified': stat.st_mtime,
                'extension': file_path.suffix.lower(),
            })
    
    return inventory

# Generate inventory for legacy directories
legacy_wav = Path("/Volumes/SYSTEM_SSD/Dropbox/Music/legacy/wav-tracks")
legacy_m4a = Path("/Volumes/SYSTEM_SSD/Dropbox/Music/legacy/m4a-tracks")

inventory = []
if legacy_wav.exists():
    inventory.extend(generate_file_inventory(legacy_wav))
if legacy_m4a.exists():
    inventory.extend(generate_file_inventory(legacy_m4a))

# Save inventory to JSON
with open('/tmp/music_inventory.json', 'w') as f:
    json.dump(inventory, f, indent=2)

print(f"Generated inventory for {len(inventory)} files")
```

### Script 3: Deduplication Script
```python
#!/usr/bin/env python3
"""
Deduplicate audio files using file hash and audio fingerprinting
"""
import json
from pathlib import Path
from collections import defaultdict

def deduplicate_files(inventory_file: str):
    """Identify and resolve duplicate files"""
    with open(inventory_file, 'r') as f:
        inventory = json.load(f)
    
    # Group by hash (exact duplicates)
    hash_groups = defaultdict(list)
    for item in inventory:
        hash_groups[item['hash']].append(item)
    
    # Identify duplicates
    duplicates = []
    for hash_val, files in hash_groups.items():
        if len(files) > 1:
            # Sort by quality (WAV > AIFF > M4A > MP3) and recency
            quality_order = {'.wav': 4, '.aiff': 3, '.m4a': 2, '.mp3': 1}
            files.sort(key=lambda x: (
                quality_order.get(x['extension'], 0),
                x['modified']
            ), reverse=True)
            
            # Keep first (highest quality/most recent), mark others as duplicates
            keep = files[0]
            for dup in files[1:]:
                duplicates.append({
                    'keep': keep,
                    'remove': dup,
                    'reason': 'exact_duplicate'
                })
    
    return duplicates

# Run deduplication
inventory_file = '/tmp/music_inventory.json'
duplicates = deduplicate_files(inventory_file)

print(f"Found {len(duplicates)} duplicate files")
for dup in duplicates[:10]:  # Show first 10
    print(f"Keep: {dup['keep']['path']}")
    print(f"Remove: {dup['remove']['path']}")
    print()
```

## Risk Assessment

### High Risk
- **Data Loss**: Incorrect deduplication could remove unique files
- **Path Breaking**: Changing directory paths could break existing workflows
- **Eagle Library**: Incorrect migration could affect Eagle library integrity

### Medium Risk
- **Metadata Loss**: Moving files could lose metadata or tags
- **Playlist Organization**: Reorganization could break playlist associations
- **Notion Sync**: File path changes could desync Notion database

### Low Risk
- **Temporary Disruption**: Migration process could temporarily disrupt workflow
- **Storage Space**: Migration might require additional temporary storage

## Mitigation Strategies

1. **Comprehensive Backup**: Backup all files before migration
2. **Incremental Migration**: Migrate in small batches with verification
3. **Dry Run**: Test all scripts on small subset first
4. **Rollback Plan**: Maintain ability to rollback changes
5. **Verification**: Verify file integrity after each migration step
6. **Documentation**: Document all changes for future reference

## Success Criteria

- [ ] All files successfully migrated to new structure
- [ ] No duplicate files remain in processed directories
- [ ] All unique files preserved and organized
- [ ] Workflow continues to function with new paths
- [ ] Eagle library integrity maintained
- [ ] Notion database updated with correct paths
- [ ] Storage space optimized (duplicates removed)
- [ ] Directory structure clean and organized

## Timeline Estimate

- **Phase 1**: 1-2 hours (directory cleanup)
- **Phase 2**: 4-8 hours (deduplication analysis and implementation)
- **Phase 3**: 2-4 hours (reorganization planning)
- **Phase 4**: 8-16 hours (migration execution)
- **Phase 5**: 2-4 hours (post-migration tasks)

**Total Estimated Time**: 17-34 hours

## Next Steps

1. Review and approve this strategy
2. Create backup of all files
3. Implement directory structure creation script
4. Implement file inventory generator
5. Implement deduplication script
6. Test on small subset
7. Execute full migration
8. Verify and validate results
9. Update configuration and documentation

---

**Document Status**: 📋 DRAFT - Awaiting Review  
**Last Updated**: 2026-01-06  
**Author**: Cursor MM1 Agent























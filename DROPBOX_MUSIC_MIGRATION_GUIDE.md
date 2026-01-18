# Dropbox Music Migration Guide

**Date:** 2026-01-08
**Status:** DRAFT - Requires Implementation
**Source:** Plans Directory Audit (Gap Reconciliation)

---

## Executive Summary

This guide outlines the migration process for reorganizing the Dropbox Music library from legacy directories to the unified directory structure. The migration should be executed in phases to minimize risk and allow for rollback.

---

## Pre-Migration Requirements

### Before Starting

1. **Backup Required:**
   - [ ] Full backup of `/Volumes/SYSTEM_SSD/Dropbox/Music/`
   - [ ] Export current Eagle library metadata
   - [ ] Export current Notion database

2. **System Requirements:**
   - [ ] Sufficient disk space for migration (at least 2x current size temporarily)
   - [ ] Eagle application running
   - [ ] Notion API access verified
   - [ ] All volumes mounted

3. **Scripts Required (To Be Created):**
   - [ ] `scripts/create_dropbox_music_structure.py`
   - [ ] `scripts/dropbox_music_deduplication.py`
   - [ ] `scripts/dropbox_music_migration.py`

---

## Target Directory Structure

```
/Volumes/SYSTEM_SSD/Dropbox/Music/
├── processed/
│   ├── playlists/           # OUT_DIR - Playlist-organized M4A/ALAC files
│   │   ├── {playlist_name}/
│   │   └── Unassigned/      # Tracks without playlist assignment
│   ├── backups/
│   │   ├── m4a/             # BACKUP_DIR - M4A backups
│   │   └── wav/             # WAV_BACKUP_DIR - WAV backups
│   └── temp/
│       └── eagle-import/    # EAGLE_WAV_TEMP_DIR - Temporary files
├── library/                 # Consolidated library files
├── archive/                 # Archived/old versions
└── _legacy/                 # Preserved legacy structure (read-only after migration)
```

---

## Migration Phases

### Phase 1: Create Directory Structure

**Script:** `scripts/create_dropbox_music_structure.py`

**Actions:**
1. Create target directory structure
2. Set appropriate permissions
3. Validate paths are accessible

**Validation:**
- All directories created successfully
- Permissions allow read/write
- Paths match configuration

---

### Phase 2: Inventory Current Files

**Script:** Part of `scripts/dropbox_music_migration.py`

**Actions:**
1. Scan all current music directories
2. Generate inventory report
3. Calculate total size and file counts

**Expected Results (from Analysis):**
- WAV files: 588 files, ~49GB
- M4A files: 1,664 files, ~45GB
- Total: ~112GB (before deduplication)

**Validation:**
- Inventory matches expected counts (within 5%)
- All files accessible
- No permission errors

---

### Phase 3: Deduplication Analysis

**Script:** `scripts/dropbox_music_deduplication.py`

**Actions:**
1. Generate audio fingerprints for all files
2. Compare with Eagle library
3. Compare with Notion database
4. Identify duplicates by:
   - File hash (MD5/SHA256)
   - Audio fingerprint
   - Filename similarity

**Expected Results:**
- Identify duplicate sets
- Calculate space savings
- Generate deduplication report

**Validation:**
- Fingerprints generated for all files
- Duplicates correctly identified
- Report generated successfully

---

### Phase 4: Execute Migration

**Script:** `scripts/dropbox_music_migration.py`

**Actions:**
1. Copy files to new structure (preserve originals)
2. Handle duplicates per deduplication plan
3. Update file paths in Notion
4. Update file paths in Eagle
5. Generate migration report

**Migration Rules:**
- Files with playlist associations → `processed/playlists/{playlist}/`
- Files without playlist → `processed/playlists/Unassigned/`
- WAV backups → `processed/backups/wav/`
- M4A backups → `processed/backups/m4a/`

**Validation:**
- All files copied successfully
- File integrity verified (checksums)
- Notion references updated
- Eagle references updated

---

### Phase 5: Verification

**Actions:**
1. Run production workflow on test track
2. Verify files created in correct locations
3. Verify Notion integration works
4. Verify Eagle integration works

**Validation:**
- Workflow completes successfully
- Files in expected directories
- No path errors in logs

---

### Phase 6: Cleanup (Optional)

**Actions:**
1. Move legacy directories to `_legacy/`
2. Mark as read-only
3. Schedule deletion after verification period (30 days recommended)

**Validation:**
- Legacy files accessible in `_legacy/`
- New structure operational
- All workflows using new paths

---

## Configuration Updates

### unified_config.py Updates

```python
MUSIC_CONFIG = {
    "out_dir": "/Volumes/SYSTEM_SSD/Dropbox/Music/processed/playlists",
    "backup_dir": "/Volumes/SYSTEM_SSD/Dropbox/Music/processed/backups/m4a",
    "wav_backup_dir": "/Volumes/SYSTEM_SSD/Dropbox/Music/processed/backups/wav",
    "eagle_wav_temp_dir": "/Volumes/SYSTEM_SSD/Dropbox/Music/processed/temp/eagle-import",
}
```

### Environment Variables

```bash
# .env updates
OUT_DIR=/Volumes/SYSTEM_SSD/Dropbox/Music/processed/playlists
BACKUP_DIR=/Volumes/SYSTEM_SSD/Dropbox/Music/processed/backups/m4a
WAV_BACKUP_DIR=/Volumes/SYSTEM_SSD/Dropbox/Music/processed/backups/wav
```

---

## Rollback Plan

### If Issues Detected

1. **Stop migration immediately**
2. **Preserve state:**
   - Do not delete any files
   - Export current Notion state
   - Export current Eagle state

3. **Rollback steps:**
   - Restore Notion database from backup
   - Restore Eagle library from backup
   - Revert configuration to legacy paths
   - Verify workflow with legacy paths

4. **Analysis:**
   - Identify root cause
   - Update migration scripts
   - Re-plan migration

---

## Risk Assessment

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| Data loss | CRITICAL | LOW | Backups, copy-first approach |
| Broken references | HIGH | MEDIUM | Verification steps, rollback plan |
| Performance degradation | MEDIUM | LOW | Monitoring, phased approach |
| Integration failures | HIGH | MEDIUM | Testing phases, feature flags |

---

## Checklist

### Pre-Migration
- [ ] Backup complete
- [ ] Scripts created and tested
- [ ] Disk space verified
- [ ] All systems accessible

### Migration
- [ ] Phase 1: Directory structure created
- [ ] Phase 2: Inventory complete
- [ ] Phase 3: Deduplication analysis done
- [ ] Phase 4: Migration executed
- [ ] Phase 5: Verification passed

### Post-Migration
- [ ] Configuration updated
- [ ] Workflow tested
- [ ] Legacy cleanup scheduled
- [ ] Documentation updated

---

## Support

### Troubleshooting

**Issue: "Path not found" errors**
- Verify volume is mounted
- Check path in configuration
- Verify permissions

**Issue: "Duplicate detected" warnings**
- Review deduplication report
- Verify correct file selected as primary
- Check fingerprint accuracy

**Issue: "Notion update failed"**
- Check API token validity
- Verify database permissions
- Check rate limits

---

**Document Status:** DRAFT
**Requires:** Script implementation before execution
**Created During:** Plans Directory Audit 2026-01-08

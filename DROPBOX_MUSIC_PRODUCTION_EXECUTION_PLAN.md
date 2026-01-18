# Dropbox Music Cleanup - Production Execution Plan

**Date:** 2026-01-15
**Author:** Claude Code Agent
**Issue ID:** 2e2e7361-6c27-8142-bf0c-f18fc419f7b1
**Status:** READY FOR EXECUTION

---

## Executive Summary

This document provides the production execution plan for the Dropbox Music cleanup scripts. All scripts have passed dry-run testing and are ready for production execution.

---

## 1. Execution Sequence

Execute scripts in this order - DO NOT skip steps:

### Phase 1: Pre-Execution Verification
```bash
# Verify base directory exists
ls -la /Volumes/SYSTEM_SSD/Dropbox/Music

# Check disk space (need ~500MB for archives)
df -h /Volumes/SYSTEM_SSD
```

### Phase 2: Structure Creation
```bash
cd /Users/brianhellemn/Projects/github-production

# Dry-run first
python3 scripts/create_dropbox_music_structure.py --dry-run

# Execute if dry-run looks correct
python3 scripts/create_dropbox_music_structure.py
```

### Phase 3: Deduplication
```bash
# Review deduplication plan
python3 scripts/dropbox_music_deduplication.py --dry-run

# IMPORTANT: Review the duplicate groups before executing!
# Execute with explicit confirmation
python3 scripts/dropbox_music_deduplication.py --execute --confirm
```

### Phase 4: Migration
```bash
# Review migration plan
python3 scripts/dropbox_music_migration.py --dry-run

# Execute with explicit confirmation
python3 scripts/dropbox_music_migration.py --execute --confirm
```

---

## 2. Prerequisites Checklist

Before executing, verify ALL items:

- [ ] Base directory exists: `/Volumes/SYSTEM_SSD/Dropbox/Music`
- [ ] At least 500MB free space on SYSTEM_SSD
- [ ] Virtual environment activated: `source /Users/brianhellemn/Projects/venv-unified-MM1/bin/activate`
- [ ] Scripts are in expected location: `/Users/brianhellemn/Projects/github-production/scripts/`
- [ ] Backup created (optional but recommended for first run)
- [ ] No active Dropbox sync in progress

---

## 3. Rollback Procedures

### Structure Creation Rollback
Structure creation only creates directories - no rollback needed unless you want to remove empty directories.

### Deduplication Rollback
Files are moved to archive, never deleted:
```bash
# Archive location
/Volumes/SYSTEM_SSD/Dropbox/Music/_Archive/Duplicates/

# To restore: move files from archive back to original location
# Original paths are logged in the deduplication report
```

### Migration Rollback
Migration creates copies, originals remain in legacy locations:
```bash
# Legacy files location (not modified)
/Volumes/SYSTEM_SSD/Dropbox/Music/_Legacy/

# To rollback: remove new files, legacy remains untouched
```

---

## 4. Safety Verification Steps

After each phase, verify:

1. **Structure Creation:**
   ```bash
   ls -la /Volumes/SYSTEM_SSD/Dropbox/Music/
   # Should show new directory structure
   ```

2. **Deduplication:**
   ```bash
   ls -la /Volumes/SYSTEM_SSD/Dropbox/Music/_Archive/Duplicates/
   # Should show archived duplicates
   ```

3. **Migration:**
   ```bash
   find /Volumes/SYSTEM_SSD/Dropbox/Music/ -name "*.m4a" | wc -l
   # Count should match expected files
   ```

---

## 5. Expected Outcomes

Based on dry-run results:

| Phase | Action | Expected Result |
|-------|--------|-----------------|
| Structure | Create directories | 13 directories created |
| Deduplication | Archive duplicates | 19 files archived, 185MB saved |
| Migration | Move files | 43 user files, 151 metadata files migrated |

---

## 6. Error Handling

If any script fails:

1. **Check Logs:** Review console output for error message
2. **Do Not Retry Blindly:** Understand the error before retrying
3. **Report Issue:** If blocked, create trigger file to Brian-Hellemn inbox
4. **No Manual Fixes:** Do not manually modify files - use rollback procedures

---

## 7. Completion Steps

After successful execution:

1. [ ] Verify all files in correct locations
2. [ ] Check no errors in script output
3. [ ] Update Notion issue to "Resolved"
4. [ ] Create execution log in Notion
5. [ ] Archive trigger files to 02_processed
6. [ ] Create handoff if additional work needed

---

## 8. Agent Assignment

**Execution Agent:** Cursor MM1 Agent
**Review Agent:** Claude MM1 Agent
**Escalation:** Brian-Hellemn inbox for blockers

---

**Plan Created By:** Claude Code Agent
**Date:** 2026-01-15

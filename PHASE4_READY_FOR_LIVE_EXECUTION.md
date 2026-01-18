# Phase 4: Second Production Run & Validation - READY

## ⚠️ WARNING: DESTRUCTIVE OPERATION

Phase 4 involves **LIVE EXECUTION** that will:
- Move duplicate items to Eagle's trash (if `--dedup-cleanup` is enabled)
- This is **IRREVERSIBLE** without restoring from trash
- **Backup recommended** before execution

## Status: READY FOR EXECUTION

All prerequisites met:
- ✅ Phase 0: System compliance verified
- ✅ Phase 1: Functions reviewed and verified
- ✅ Phase 2: Dry-run completed successfully
- ✅ Phase 3: No critical issues found
- ✅ Dry-run results reviewed: 5,830 duplicates, 147.77 GB recoverable

## Execution Command

```bash
cd /Users/brianhellemn/Projects/github-production

OUT_DIR=/tmp/eagle-dedup-temp \
BACKUP_DIR=/tmp/eagle-dedup-temp \
WAV_BACKUP_DIR=/tmp/eagle-dedup-temp \
python3 monolithic-scripts/soundcloud_download_prod_merge-2.py \
  --mode dedup \
  --dedup-threshold 0.75 \
  --dedup-live \
  --dedup-cleanup \
  --debug
```

## Expected Results

Based on dry-run:
- **5,830 duplicate items** will be moved to trash
- **147.77 GB** of space will be recovered
- **Best quality items** will be retained based on quality scoring
- **Detailed report** will be generated

## Pre-Execution Checklist

- [ ] Backup Eagle library (recommended)
- [ ] Review top 50 duplicate groups from dry-run report
- [ ] Verify quality scoring selected correct "best" items
- [ ] Ensure VIBES volume is mounted (if using default paths)
- [ ] Confirm Eagle application is running
- [ ] Verify Eagle API is accessible

## Post-Execution Validation

After execution, verify:
1. ✅ Duplicates moved to trash (check Eagle trash folder)
2. ✅ Best items retained in library
3. ✅ Library integrity maintained
4. ✅ Report generated and accurate
5. ✅ Space actually recovered matches estimates

## Phase 4.2: Document and Validate Results

After execution, will:
- Compare second run to first run
- Verify duplicates removed
- Validate performance and compliance
- Document any issues encountered

## Phase 4.3: Create Validation Report

Will create comprehensive validation report comparing:
- Pre-execution state vs post-execution state
- Expected vs actual duplicates removed
- Expected vs actual space recovered
- Performance metrics
- Any edge cases or issues

## Next Steps After Phase 4

**Phase 5: Iterative Execution Until Complete**
- Run another dry-run to check for remaining duplicates
- If duplicates remain, analyze why they weren't detected
- Adjust similarity threshold if needed
- Repeat Phases 1-4 until no duplicates remain

**Phase 6: Completion & Documentation**
- Final verification (zero duplicates)
- Update Notion documentation
- Create final execution report
- Update workflow documentation

## Current Status

**READY FOR LIVE EXECUTION** - All prerequisites met, dry-run successful, system verified.

**⚠️ IMPORTANT:** This is a destructive operation. Execute only after reviewing dry-run report and confirming readiness.

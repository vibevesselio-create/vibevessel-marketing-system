# Eagle Library Deduplication - System Compliant Prompt Summary

**Date:** 2026-01-08  
**Status:** ✅ COMPLETE  
**Created File:** `/Users/brianhellemn/Library/Mobile Documents/com~apple~CloudDocs/MM1-MM2-Sync/system-prompts/Eagle Library Deduplication - System Compliant Prompt.rtf`

---

## Executive Summary

Created a system-compliant version of the Eagle Library Deduplication prompt that:
1. **Verifies system compliance** - All music directories and Eagle libraries must be documented in Notion
2. **Scans local filesystem** - Identifies all music directories on local system
3. **Compares with Notion** - Ensures all local directories are documented
4. **Documents missing directories** - Creates Notion entries for any missing directories
5. **Maintains compliance** - Updates Notion documentation throughout workflow
6. **Executes deduplication** - Proceeds with full deduplication workflow after compliance verification

---

## Key Differences from Standard Version

### Phase 0: System Compliance Verification (NEW)

**Mandatory preliminary phase** that must complete before any deduplication execution:

**0.1 Verify Notion Music Directories Database:**
- Verify database exists and is accessible
- Verify database schema includes path properties
- Verify database contains entries

**0.2 Scan Local Filesystem for Music Directories:**
- Scan `/Users/brianhellemn/Music/Downloads/*`
- Scan `/Volumes/*/Music/*`
- Scan `/Volumes/*/Playlists`
- Scan `/Volumes/*/Djay-Pro-Auto-Import`
- Scan `/Volumes/*/Apple-Music-Auto-Add`
- Identify any directories containing audio files

**0.3 Load Documented Directories from Notion:**
- Query Music Directories database
- Extract all documented paths
- Document Notion page IDs and properties

**0.4 Compare Local Directories vs Notion Documentation:**
- Create comparison matrix
- Identify missing directories
- Identify incorrect paths
- Create Notion entries for missing directories
- Update incorrect paths in Notion

**0.5 Verify Eagle Library Documentation:**
- Check EAGLE_LIBRARY_PATH
- Query Notion for Eagle library entry
- Create entry if missing

**0.6 Document Compliance Status:**
- Total local directories found
- Total documented in Notion
- Missing directories list
- Incorrect paths list
- Compliance status: COMPLIANT / NON-COMPLIANT

**MANDATORY:** Execution cannot proceed until compliance is verified.

---

## System Compliance Requirements

### Music Directories Database

**Database ID:** `MUSIC_DIRECTORIES_DB_ID` (from unified_config or environment)

**Required Properties:**
- `Path` / `Directory` / `Folder` / `Folder Path` / `Volume Path` / `Root Path` / `Location` / `Music Directory`
- `Name` / `Title`
- `Status` (Active/Inactive)
- `Type` (Playlists, Downloads, Auto-Import, Eagle Library, etc.)
- `Volume` (volume name)
- `Last Verified` (date)

### Directory Types

- **Playlists** - Playlist directories
- **Downloads** - Download directories
- **Auto-Import** - Auto-import directories
- **Eagle Library** - Eagle library paths
- **Backup** - Backup directories

### Compliance Status

**COMPLIANT:**
- All local music directories found in Notion
- All paths are correct
- Eagle library is documented
- All entries have required properties

**NON-COMPLIANT:**
- Missing directories in Notion
- Incorrect paths in Notion
- Missing Eagle library documentation
- Missing required properties

---

## Workflow Phases

### Phase 0: System Compliance Verification (NEW)

**Purpose:** Ensure all music directories and Eagle libraries are documented in Notion

**Steps:**
1. Verify Music Directories database exists
2. Scan local filesystem for music directories
3. Load documented directories from Notion
4. Compare local vs Notion
5. Document missing directories in Notion
6. Update incorrect paths
7. Verify Eagle library documentation
8. Document compliance status

**Output:**
- Compliance report
- Notion entries created/updated
- Compliance status: COMPLIANT / NON-COMPLIANT

**Gate:** Cannot proceed until COMPLIANT status achieved

---

### Phase 1: Review & Status Identification

**Enhanced with:**
- System compliance verification
- Verification that functions use documented paths
- Compliance with Music Directories database

---

### Phase 2: Production Run Execution & Analysis

**Enhanced with:**
- System compliance verification in audit
- Verification that execution used documented paths
- Verification that no undocumented directories accessed

---

### Phase 3: Issue Remediation & Handoff

**Enhanced with:**
- Compliance issue categorization
- Compliance issue remediation
- Compliance status in handoff tasks

---

### Phase 4: Second Production Run & Validation

**Enhanced with:**
- Compliance validation
- Verification of documented path usage
- Verification of Notion documentation updates

---

### Phase 5: Iterative Execution Until Complete

**Same as standard version**

---

### Phase 6: Completion & Documentation

**Enhanced with:**
- **6.2 Update Notion Documentation (NEW):**
  - Update Eagle library entry with deduplication results
  - Update Last Deduplication date
  - Update Duplicates Removed count
  - Update Space Recovered
  - Update Status

---

## Notion Documentation Updates

### During Compliance Verification

**For Missing Directories:**
```json
{
  "Name": {"title": [{"text": {"content": "{directory_name}"}}]},
  "Path": {"url": "{full_path}"},
  "Status": {"select": {"name": "Active"}},
  "Type": {"select": {"name": "{directory_type}"}},
  "Volume": {"rich_text": [{"text": {"content": "{volume_name}"}}]},
  "Last Verified": {"date": {"start": "today"}}
}
```

**For Eagle Library:**
```json
{
  "Name": {"title": [{"text": {"content": "Eagle Music Library - Active"}}]},
  "Path": {"url": "{EAGLE_LIBRARY_PATH}"},
  "Type": {"select": {"name": "Eagle Library"}},
  "Status": {"select": {"name": "Active"}},
  "Library Name": {"rich_text": [{"text": {"content": "Music-Library-2"}}]},
  "Last Verified": {"date": {"start": "today"}}
}
```

### After Deduplication Completion

**Update Eagle Library Entry:**
```json
{
  "Last Deduplication": {"date": {"start": "today"}},
  "Duplicates Removed": {"number": {total_duplicates_removed}},
  "Space Recovered": {"number": {space_recovered_bytes}},
  "Status": {"select": {"name": "Deduplicated"}}
}
```

---

## Error Handling

### Compliance-Specific Errors

| Error Type | Severity | Action |
|------------|----------|--------|
| Music Directories DB not found | CRITICAL | Create Agent-Task, STOP execution |
| Local directory not in Notion | HIGH | Document in Notion, continue |
| Eagle library not documented | HIGH | Document in Notion, continue |
| Compliance verification fails | CRITICAL | Fix compliance issues, re-verify |

---

## Completion Gates

### Phase 0 Compliance Gates (NEW)

- ✅ Music Directories database accessible
- ✅ All local directories scanned
- ✅ All local directories documented in Notion
- ✅ Eagle library documented in Notion
- ✅ Compliance status: COMPLIANT

**MANDATORY:** Cannot proceed until all Phase 0 gates pass.

### Standard Gates (Enhanced)

All standard gates plus:
- ✅ System compliance verified
- ✅ Compliance maintained throughout
- ✅ Notion documentation updated

---

## Expected Outcomes

### Immediate Benefits

1. **System Compliance:** All directories documented in Notion
2. **Complete Deduplication:** Zero duplicates in Eagle library
3. **Space Recovery:** Recover storage space from duplicates
4. **Library Integrity:** Best quality items preserved
5. **Documentation:** Complete Notion documentation

### Long-Term Benefits

1. **Maintenance Workflow:** Established process for future deduplication
2. **System Compliance:** Maintained compliance with Notion documentation
3. **Function Validation:** Verified deduplication functions work correctly
4. **Issue Resolution:** All issues identified and resolved
5. **Documentation:** Complete execution history and recommendations

---

## Integration Points

### Notion Music Directories Database

- **Source of Truth:** All music directories must be documented
- **Compliance Verification:** Compare local filesystem with Notion
- **Documentation Updates:** Update entries throughout workflow
- **Eagle Library Tracking:** Track deduplication results

### Production Music Workflow

- Uses same deduplication functions
- Validates functions work independently
- Ensures consistency across workflows
- Maintains system compliance

### Notion Agent-Tasks Database

- Handoff tasks for issue remediation
- Execution tracking
- Results documentation
- Compliance issue tracking

---

## Usage Instructions

### For Agents Executing This Prompt

1. **Complete Phase 0:** Verify compliance before any execution
2. **Document Missing Directories:** Create Notion entries for any missing
3. **Verify Compliance:** Achieve COMPLIANT status
4. **Execute Phases 1-6:** Standard deduplication workflow
5. **Update Notion:** Update documentation throughout and at completion

### For Workflow Administrators

1. **Monitor Compliance:** Ensure Phase 0 completes successfully
2. **Review Notion Updates:** Verify all directories documented
3. **Monitor Execution:** Track progress through phases
4. **Review Handoffs:** Ensure Claude Code Agent completes remediation
5. **Validate Results:** Verify no duplicates remain and compliance maintained

---

## Metrics for Success

### Compliance Metrics

- ✅ All local directories documented in Notion
- ✅ Eagle library documented in Notion
- ✅ All paths are correct
- ✅ Compliance status: COMPLIANT
- ✅ Notion documentation updated

### Execution Metrics

- ✅ All deduplication functions reviewed and verified
- ✅ Production runs executed successfully
- ✅ Technical audit completed
- ✅ Gap analysis completed
- ✅ Issues remediated
- ✅ Zero duplicates remain

### Quality Metrics

- ✅ No false positives removed
- ✅ No false negatives missed
- ✅ Best items preserved
- ✅ Library integrity maintained
- ✅ Performance acceptable
- ✅ Compliance maintained

---

## Related Documents

- `EAGLE_LIBRARY_DEDUPLICATION_PROMPT_SUMMARY.md` - Standard version summary
- `PRODUCTION_MUSIC_DOWNLOAD_WORKFLOW_COMPREHENSIVE_REPORT.md` - Production workflow analysis
- `VALIDATION_REPORT_Deduplication_FuzzyMatching_NotionScriptRunner_*.md` - Validation reports
- `logs/deduplication/eagle_dedup_report_*.md` - Previous execution reports
- `scripts/music_library_remediation.py` - Music directory loading functions
- `scripts/build_music_volume_index.py` - Volume index building

---

**Last Updated:** 2026-01-08  
**Version:** 1.0  
**Status:** ✅ PROMPT CREATED - SYSTEM COMPLIANT EDITION

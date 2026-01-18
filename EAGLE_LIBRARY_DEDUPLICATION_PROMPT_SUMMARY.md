# Eagle Library Deduplication Prompt Summary

**Date:** 2026-01-08  
**Status:** ✅ COMPLETE  
**Created File:** `/Users/brianhellemn/Library/Mobile Documents/com~apple~CloudDocs/MM1-MM2-Sync/system-prompts/Eagle Library Deduplication Prompt.rtf`

---

## Executive Summary

Created a comprehensive prompt for executing Eagle library-wide deduplication that:
1. **Reviews and identifies** status of implemented deduplication functions
2. **Executes production runs** with comprehensive technical analysis
3. **Remediates issues** with handoff to Claude Code Agent
4. **Validates results** through iterative execution
5. **Continues until complete** - no duplicates remain in active Eagle library

---

## Key Features

### 1. Pre-Execution Intelligence Gathering

**Phase 0:** Before execution, agents must:
- Verify Eagle application is running and accessible
- Identify all production deduplication functions
- Review related documentation and previous reports
- Document current library state

**Functions Identified:**
- `eagle_library_deduplication()` - Library-wide scan
- `eagle_import_with_duplicate_management()` - Import with pre-check
- `eagle_cleanup_duplicate_items()` - Move duplicates to trash
- `sync_fingerprints_to_eagle_tags()` - Sync fingerprints

**Standalone Execution:**
```bash
python3 monolithic-scripts/soundcloud_download_prod_merge-2.py --mode dedup [OPTIONS]
```

---

### 2. Phase 1: Review & Status Identification

**1.1 Review Deduplication Function Implementation:**
- Verify function availability and callability
- Review function capabilities (fingerprint, fuzzy, quality analysis)
- Verify independent execution capability

**1.2 Document Function Status:**
- Create function availability matrix
- Capability assessment
- Independent execution verification
- Known limitations

---

### 3. Phase 2: Production Run Execution & Analysis

**2.1 Execute First Production Run (Dry-Run):**
```bash
python3 monolithic-scripts/soundcloud_download_prod_merge-2.py \
  --mode dedup \
  --dedup-threshold 0.75 \
  --debug
```

**2.2 Comprehensive Technical Output Audit:**
- Performance metrics (duration, throughput, memory)
- Detection accuracy (fingerprint, fuzzy, n-gram matches)
- Quality analysis effectiveness
- Report analysis

**2.3 Complete Gap Analysis:**
- Functional gaps (missing strategies, incomplete algorithms)
- Performance gaps (slow execution, high memory)
- Accuracy gaps (false positives/negatives)
- Documentation gaps

**2.4 Document Results & Issues:**
- Execution results summary
- Performance analysis
- Gap analysis report
- Issues encountered
- Recommendations

---

### 4. Phase 3: Issue Remediation & Handoff

**3.1 Categorize Issues:**
- By severity (Critical, High, Medium, Low)
- By type (Functional, Performance, Accuracy, Documentation)
- By remediation complexity

**3.2 Attempt Immediate Remediation:**
- Fix code bugs
- Update configuration
- Improve error handling
- Add documentation
- Optimize performance

**3.3 Create Handoff to Claude Code Agent:**
- Create Notion task with detailed issue description
- Include execution results and gap analysis
- Specify remediation requirements
- Define acceptance criteria
- **MANDATORY: Wait for remediation response before proceeding**

---

### 5. Phase 4: Second Production Run & Validation

**4.1 Execute Second Production Run:**
Only if Phase 3 remediation allows effective execution:
```bash
python3 monolithic-scripts/soundcloud_download_prod_merge-2.py \
  --mode dedup \
  --dedup-threshold 0.75 \
  --dedup-live \
  --dedup-cleanup \
  --debug
```

**4.2 Document and Validate Results:**
- Compare to first run
- Verify duplicates removed
- Verify best items kept
- Verify library integrity
- Validate performance

**4.3 Create Validation Report:**
- Second run execution results
- Comparison to first run
- Validation findings
- Remaining issues
- Recommendations

---

### 6. Phase 5: Iterative Execution Until Complete

**5.1 Check for Remaining Duplicates:**
After each production run, check if duplicates remain.

**5.2 Analyze Remaining Duplicates:**
- Identify why they weren't detected
- Adjust similarity threshold if needed
- Review matching strategies
- Identify edge cases

**5.3 Repeat Phases 1-4:**
Continue iterating until no duplicates are found.

---

### 7. Phase 6: Completion & Documentation

**6.1 Final Verification:**
Execute final dry-run to confirm zero duplicates.

**6.2 Create Final Documentation:**
- Complete execution history
- All issues encountered and resolved
- Performance metrics
- Final library state
- Recommendations

**6.3 Update Workflow Documentation:**
- Update comprehensive reports
- Create execution report
- Update workflow status

---

## Deduplication Strategies

The production script uses three strategies:

### Strategy 1: Fingerprint Matching (Most Accurate)
- Matches items with identical audio fingerprints
- 100% accuracy
- Uses fingerprint tags or file metadata

### Strategy 2: Fuzzy Name Matching
- Advanced fuzzy matching on item names
- Configurable similarity threshold (default: 0.75)
- Handles variations in naming

### Strategy 3: N-Gram Matching
- Cross-cluster matching for edge cases
- Catches duplicates missed by other strategies
- Handles complex naming variations

---

## Quality Analysis

The script uses quality scoring to select best items:

| Factor | Weight | Condition |
|--------|--------|-----------|
| Has metadata tags | 40% | BPM, key, duration, artist, etc. |
| Is recent | 30% | Modified within 30 days |
| Large file | 30% | > 10MB file size |

---

## Execution Modes

### Dry-Run Mode (Default)
- Reports duplicates without making changes
- Safe for initial assessment
- Generates detailed markdown report

### Live Mode (`--dedup-live`)
- Actually removes duplicates
- Moves duplicates to trash
- Requires explicit flag

### Cleanup Mode (`--dedup-cleanup`)
- Automatically moves duplicates to trash
- Requires `--dedup-live` flag
- Permanent action (use with caution)

---

## Error Handling

| Error Type | Severity | Action |
|------------|----------|--------|
| Eagle API not accessible | CRITICAL | Launch Eagle, wait, retry |
| Library path not found | CRITICAL | Verify path, check volume |
| Function not found | CRITICAL | Verify script, check imports |
| Dry-run execution fails | HIGH | Review logs, fix, retry |
| Live execution fails | HIGH | Revert to dry-run, review |
| Cleanup fails | MEDIUM | Log failures, continue |
| Performance issues | MEDIUM | Document, optimize |
| False positives | HIGH | Adjust threshold, review logic |
| False negatives | HIGH | Review strategies, handoff |

---

## Completion Gates

All phases must pass for success:

- ✅ Pre-Execution: Eagle accessible, functions identified
- ✅ Phase 1: Functions reviewed and status documented
- ✅ Phase 2: Production run executed and analyzed
- ✅ Phase 3: Issues remediated (with handoff if needed)
- ✅ Phase 4: Second run executed and validated
- ✅ Phase 5: Iterative execution until no duplicates
- ✅ Phase 6: Final verification and documentation

---

## Expected Outcomes

### Immediate Benefits

1. **Complete Deduplication:** Zero duplicates in Eagle library
2. **Space Recovery:** Recover storage space from duplicates
3. **Library Integrity:** Best quality items preserved
4. **Performance Baseline:** Documented execution metrics

### Long-Term Benefits

1. **Maintenance Workflow:** Established process for future deduplication
2. **Function Validation:** Verified deduplication functions work correctly
3. **Issue Resolution:** All issues identified and resolved
4. **Documentation:** Complete execution history and recommendations

---

## Integration Points

### Related Systems

1. **Production Music Workflow:**
   - Uses same deduplication functions
   - Validates functions work independently
   - Ensures consistency across workflows

2. **Notion Agent-Tasks Database:**
   - Handoff tasks for issue remediation
   - Execution tracking
   - Results documentation

3. **Workflow Documentation:**
   - Execution reports
   - Performance metrics
   - Issue resolution history

---

## Usage Instructions

### For Agents Executing This Prompt

1. **Complete Pre-Execution:** Verify Eagle, identify functions, review docs
2. **Execute Phase 1:** Review and document function status
3. **Execute Phase 2:** Run production execution and analysis
4. **Execute Phase 3:** Remediate issues (with handoff if needed)
5. **Execute Phase 4:** Second run and validation
6. **Execute Phase 5:** Iterate until complete
7. **Execute Phase 6:** Final verification and documentation

### For Workflow Administrators

1. **Monitor Execution:** Track progress through phases
2. **Review Handoffs:** Ensure Claude Code Agent completes remediation
3. **Validate Results:** Verify no duplicates remain
4. **Review Documentation:** Check execution reports and recommendations

---

## Metrics for Success

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

---

## Related Documents

- `PRODUCTION_MUSIC_DOWNLOAD_WORKFLOW_COMPREHENSIVE_REPORT.md` - Production workflow analysis
- `VALIDATION_REPORT_Deduplication_FuzzyMatching_NotionScriptRunner_*.md` - Validation reports
- `logs/deduplication/eagle_dedup_report_*.md` - Previous execution reports
- `shared_core/workflows/deduplication_fingerprint_workflow.py` - Workflow template

---

**Last Updated:** 2026-01-08  
**Version:** 1.0  
**Status:** ✅ PROMPT CREATED

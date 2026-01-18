# EXECUTE: Eagle Library Merge Workflow - System Compliant Edition

🔴 IMMEDIATE EXECUTION REQUIRED - SYSTEM COMPLIANCE MANDATORY

Do NOT summarize this document. Do NOT ask clarifying questions.

Begin PHASE 0 now. Execute all phases in sequence until merge is complete.

## SYSTEM COMPLIANCE REQUIREMENT

This workflow is system-mandated and compliant. All Eagle libraries MUST be documented in Notion before merge execution.

## PHASE 0: System Compliance Verification - Libraries & Directories

### 0.1 Verify Notion Music Directories Database

MANDATORY: Verify Music Directories database exists and is accessible.

Database ID: `${MUSIC_DIRECTORIES_DB_ID}` (from unified_config or environment)

Query Notion database:

```
notionApi:API-get-database on ${MUSIC_DIRECTORIES_DB_ID}
```

Verify:
- Database exists and is accessible
- Database schema includes path properties (Path, Directory, Folder, Folder Path, Volume Path, Root Path, Location, Music Directory)
- Database contains entries for Eagle libraries

If database does not exist or is not accessible:
- Create Agent-Task for database setup
- STOP execution until database is available

### 0.2 Scan Local Filesystem for Eagle Libraries

MANDATORY: Scan local filesystem to identify all Eagle library directories.

Scan locations:
- `/Volumes/*/Music Library-2.library`
- `/Volumes/*/Music-Library-2.library`
- `/Volumes/OF-CP2019-2025/Music Library-2.library`
- `/Volumes/VIBES/Music Library-2.library`
- Any directories ending in `.library` containing `library.json`

Execute scan:

```bash
cd /Users/brianhellemn/Projects/github-production

python3 -c "
import os
from pathlib import Path

def find_eagle_libraries():
    libraries = []
    scan_paths = [
        Path('/Volumes'),
        Path('/Users/brianhellemn/Music'),
    ]
    
    for base_path in scan_paths:
        if not base_path.exists():
            continue
        for root, dirs, files in os.walk(base_path):
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            # Check if this is an Eagle library
            library_json = Path(root) / 'library.json'
            if library_json.exists() or root.endswith('.library'):
                libraries.append(root)
    
    return sorted(libraries)

libs = find_eagle_libraries()
for lib in libs:
    print(f'LIBRARY: {lib}')
"
```

Document all found libraries with:
- Full path
- Volume mount status
- Item count (if accessible)
- Library name
- Library type (Previous/Current/Archive)

### 0.3 Load Documented Libraries from Notion

MANDATORY: Load all Eagle libraries documented in Notion.

Execute:

```bash
cd /Users/brianhellemn/Projects/github-production

python3 -c "
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

try:
    from unified_config import load_unified_env, get_unified_config
    from shared_core.notion.token_manager import get_notion_client
    
    load_unified_env()
    config = get_unified_config()
    db_id = config.get('music_directories_db_id') or os.getenv('MUSIC_DIRECTORIES_DB_ID', '')
    
    notion = get_notion_client()
    
    # Query for Eagle libraries
    response = notion.databases.query(
        database_id=db_id,
        filter={
            'or': [
                {'property': 'Type', 'select': {'equals': 'Eagle Library'}},
                {'property': 'Name', 'title': {'contains': 'Eagle'}},
                {'property': 'Path', 'rich_text': {'contains': '.library'}}
            ]
        }
    )
    
    print('DOCUMENTED_LIBRARIES_START')
    for page in response.get('results', []):
        props = page.get('properties', {})
        name = props.get('Name', {}).get('title', [{}])[0].get('plain_text', 'Unknown')
        path = props.get('Path', {}).get('rich_text', [{}])[0].get('plain_text', '')
        print(f'DOCUMENTED: {name} - {path}')
    print('DOCUMENTED_LIBRARIES_END')

except Exception as e:
    print(f'ERROR: {e}', file=sys.stderr)
    sys.exit(1)
"
```

Document all documented libraries with:
- Full path
- Notion page ID
- Property name used
- Status (active/inactive)
- Library role (Previous/Current)

### 0.4 Compare Local Libraries vs Notion Documentation

MANDATORY: Verify all local Eagle libraries are documented in Notion.

Create comparison matrix:

| Local Library | Found in Notion | Notion Page ID | Status | Role | Action Required |
|---------------|-----------------|----------------|--------|------|-----------------|
| /path/to/lib1 | Yes/No          | ID or N/A      | Active/Inactive | Previous/Current | Document/Update/None |

For each local library NOT found in Notion:

A. Create Notion entry:

```
notionApi:API-post-page on ${MUSIC_DIRECTORIES_DB_ID}

properties: {
  Name: {title: [{text: {content: "{library_name}"}}]},
  Path: {url: "{full_path}"} OR {rich_text: [{text: {content: "{full_path}"}}]},
  Status: {select: {name: "Active"}},
  Type: {select: {name: "Eagle Library"}},
  Volume: {rich_text: [{text: {content: "{volume_name}"}}]},
  Last Verified: {date: {start: today}},
  Role: {select: {name: "{Previous/Current/Archive}"}}
}
```

B. Document creation:
- Notion page ID created
- Properties set
- Verification timestamp

For each local library found in Notion but with incorrect path:

A. Update Notion entry:

```
notionApi:API-patch-page on {notion_page_id}

properties: {
  Path: {url: "{corrected_path}"} OR {rich_text: [{text: {content: "{corrected_path}"}}]},
  Last Verified: {date: {start: today}},
  Status: {select: {name: "Active"}}
}
```

### 0.5 Verify Both Libraries Are Documented

MANDATORY: Verify both previous and current libraries are documented in Notion.

Previous Library:
- Default: `/Volumes/OF-CP2019-2025/Music Library-2.library`
- Must be documented in Notion
- Must have valid path and be accessible
- Must have `library.json` file

Current Library:
- Default: `/Volumes/VIBES/Music Library-2.library`
- From EAGLE_LIBRARY_PATH in unified_config or environment
- Must be documented in Notion
- Must have valid path and be accessible
- Must have `library.json` file

Query Notion Music Directories database for both libraries:

```
notionApi:API-post-database-query on ${MUSIC_DIRECTORIES_DB_ID}

filter: {
  "or": [
    {"property": "Path", "rich_text": {"contains": "OF-CP2019-2025"}},
    {"property": "Path", "rich_text": {"contains": "VIBES"}},
    {"property": "Path", "rich_text": {"contains": "Music Library-2.library"}},
    {"property": "Type", "select": {"equals": "Eagle Library"}}
  ]
}
```

If either library NOT found in Notion:

Create Notion entry for missing library:

```
notionApi:API-post-page on ${MUSIC_DIRECTORIES_DB_ID}

properties: {
  Name: {title: [{text: {content: "Eagle Music Library - {Previous/Current}"}}]},
  Path: {url: "{EAGLE_LIBRARY_PATH}"} OR {rich_text: [{text: {content: "{EAGLE_LIBRARY_PATH}"}}]},
  Type: {select: {name: "Eagle Library"}},
  Status: {select: {name: "Active"}},
  Library Name: {rich_text: [{text: {content: "Music Library-2"}}]},
  Role: {select: {name: "{Previous/Current}"}},
  Last Verified: {date: {start: today}}
}
```

### 0.6 Document Compliance Status

Create compliance report:

- Total local libraries found: {count}
- Total libraries documented in Notion: {count}
- Libraries missing from Notion: {list}
- Libraries with incorrect paths: {list}
- Previous library documented: Yes/No
- Current library documented: Yes/No
- Compliance status: COMPLIANT / NON-COMPLIANT

If NON-COMPLIANT:
- Document all missing libraries
- Create Notion entries for missing libraries
- Update incorrect paths
- Re-verify compliance

**DO NOT proceed to Phase 1 until compliance is verified.**

## PRE-EXECUTION PHASE: Workflow Intelligence & Preparation

After compliance verification, complete the following:

### 0.7 Verify Eagle Application Status

MANDATORY: Ensure Eagle application is running and both libraries are accessible.

```bash
osascript -e 'tell application "Eagle" to activate'
```

Verify Eagle API is accessible:

```bash
curl -s http://localhost:41595/api/item/list?token=${EAGLE_TOKEN} | head -20
```

If Eagle is not running or API is not accessible:
- Launch Eagle application
- Wait for API to become available (up to 45 seconds)
- Verify both library paths match documented paths in Notion

### 0.8 Identify Production Merge Functions

MANDATORY: Review and identify status of implemented merge functions.

**Primary Production Script:**
`/Users/brianhellemn/Projects/github-production/monolithic-scripts/soundcloud_download_prod_merge-2.py`

**Key Merge Functions:**

1. **eagle_merge_library()**
   - Location: soundcloud_download_prod_merge-2.py (line ~5710)
   - Purpose: Library merge orchestration
   - Modes: Dry-run and Live execution
   - Features: Library switching, item fetching, import with duplicate management, post-merge deduplication, report generation
   - Output: Comprehensive markdown report

2. **eagle_switch_library()**
   - Location: soundcloud_download_prod_merge-2.py (line ~4213)
   - Purpose: Switch between Eagle libraries
   - Method: Eagle API `/library/switch` endpoint

3. **eagle_fetch_all_items()**
   - Location: soundcloud_download_prod_merge-2.py (line ~4344)
   - Purpose: Fetch all items from library
   - Limit: Up to 50,000 items

4. **eagle_import_with_duplicate_management()**
   - Location: soundcloud_download_prod_merge-2.py (line ~5174)
   - Purpose: Import with pre-check duplicate detection
   - Features: Filename matching, fingerprint matching, quality analysis

5. **eagle_library_deduplication()**
   - Location: soundcloud_download_prod_merge-2.py (line ~5361)
   - Purpose: Post-merge deduplication
   - Method: Full library deduplication scan

6. **_generate_merge_report()**
   - Location: soundcloud_download_prod_merge-2.py (line ~6049)
   - Purpose: Generate merge report
   - Format: Markdown report

**Standalone Execution Capability:**

The production script supports independent merge execution:

```bash
python3 monolithic-scripts/soundcloud_download_prod_merge-2.py --mode merge [OPTIONS]
```

Options:
- `--merge-previous-library PATH`: Path to previous library (required)
- `--merge-current-library PATH`: Path to current library (optional, defaults to EAGLE_LIBRARY_PATH)
- `--merge-live`: Execute in LIVE mode (default is dry-run)
- `--dedup-threshold N`: Minimum similarity threshold (0.0-1.0, default: 0.75)
- `--dedup-cleanup`: Enable automatic cleanup (requires --merge-live)

### 0.9 Review Related Documentation

Search and review:
- `logs/deduplication/library_merge_*.md` (previous execution reports)
- `EAGLE_LIBRARY_DEDUPLICATION_EXECUTION_REPORT.md`
- `shared_core/workflows/deduplication_fingerprint_workflow.py`
- Music Directories database entries in Notion

### 0.10 Review Plans Directory and Take Direct Action

MANDATORY: Review the Cursor "plans" directory to understand expected outcomes, then TAKE DIRECT ACTION to complete any missing work.

Locate and review most recent plan files:

```bash
cd /Users/brianhellemn/Projects/github-production

find plans/ -type f \( -name "*.md" -o -name "*.txt" \) -exec ls -lt {} + 2>/dev/null | head -5
```

For each relevant plan file found:
- Extract expected deliverables and success criteria
- Identify missing deliverables and ACTUALLY CREATE THEM (code, config, docs, Notion entries)
- Identify incomplete tasks and ACTUALLY COMPLETE THEM
- Identify communication failures and RECONCILE THEM (retry APIs, fix permissions, create missing handoffs)
- Identify task completion failures and RESOLVE THEM (complete code, finish config, write docs)
- Create issues in Issues+Questions database (229e73616c27808ebf06c202b10b5166) for any gaps that cannot be immediately resolved
- Use plan expectations to guide execution and validate that all expected outputs are produced

**DO NOT just document gaps - ACTUALLY COMPLETE THE WORK.**

### 0.11 Document Current State

Before execution, document:
- Previous library path (from Notion documentation)
- Current library path (from Notion documentation)
- Previous library item count
- Current library item count
- Previous merge execution history
- Known issues or limitations
- Configuration settings (similarity threshold, cleanup mode)
- Compliance status (from Phase 0)

## PHASE 1: Review & Status Identification

### 1.1 Review Merge Function Implementation

Execute comprehensive code review:

A. Function Availability:
- [ ] Verify eagle_merge_library() exists and is callable
- [ ] Verify eagle_switch_library() exists
- [ ] Verify eagle_fetch_all_items() exists
- [ ] Verify eagle_import_with_duplicate_management() exists
- [ ] Verify eagle_library_deduplication() exists
- [ ] Verify _generate_merge_report() exists
- [ ] Verify standalone execution mode (--mode merge) works

B. Function Capabilities:
- [ ] Review library switching implementation
- [ ] Review item fetching implementation
- [ ] Review import with duplicate management implementation
- [ ] Review post-merge deduplication integration
- [ ] Review report generation capabilities
- [ ] Review previous library cleanup functionality

C. Independent Execution:
- [ ] Verify functions can run independently from main workflow
- [ ] Test --mode merge execution
- [ ] Verify dry-run mode works
- [ ] Verify live execution mode works
- [ ] Verify cleanup mode works

D. System Compliance:
- [ ] Verify functions use documented library paths from Notion
- [ ] Verify functions respect system-mandated paths
- [ ] Verify compliance with Music Directories database

### 1.2 Document Function Status

Create comprehensive status document:
- Function availability matrix
- Capability assessment
- Independent execution verification
- Known limitations or issues
- Configuration requirements
- System compliance verification

## PHASE 2: Production Run Execution & Analysis

### 2.1 Execute First Production Run (Dry-Run)

MANDATORY: Always start with dry-run to assess scope.

```bash
cd /Users/brianhellemn/Projects/github-production

python3 monolithic-scripts/soundcloud_download_prod_merge-2.py \
  --mode merge \
  --merge-previous-library "/Volumes/OF-CP2019-2025/Music Library-2.library" \
  --merge-current-library "/Volumes/VIBES/Music Library-2.library" \
  --dedup-threshold 0.75 \
  --debug
```

**Expected Output:**
- Previous library item count
- Items that would be imported
- Items that would be skipped (duplicates)
- Estimated import duration
- Detailed markdown report path

### 2.2 Comprehensive Technical Output Audit

Review execution output and report:

A. Performance Metrics:
- Scan duration
- Items processed per second
- Memory usage
- API call count and rate
- Library switch duration

B. Import Accuracy:
- Items that would be imported
- Items that would be skipped (duplicates)
- False positive rate (if verifiable)
- False negative rate (if verifiable)

C. Duplicate Detection:
- Duplicate detection during import
- Post-merge deduplication preview
- Quality of duplicate matching

D. Report Analysis:
- Review generated markdown report
- Verify merge summary is accurate
- Verify duplicate detection is correct
- Verify space calculations are accurate

E. System Compliance:
- Verify execution used documented library paths
- Verify no undocumented libraries accessed
- Verify compliance with Music Directories database

### 2.3 Complete Gap Analysis

Identify:

A. Functional Gaps:
- Missing merge capabilities
- Incomplete library switching
- Missing import features
- Missing cleanup capabilities
- Report generation limitations

B. Performance Gaps:
- Slow execution times
- High memory usage
- API rate limiting issues
- Inefficient algorithms

C. Accuracy Gaps:
- False positives in duplicate detection
- False negatives in duplicate detection
- Incorrect item import decisions
- Incomplete merge results

D. Documentation Gaps:
- Missing function documentation
- Incomplete usage examples
- Missing error handling documentation
- Incomplete configuration documentation

E. Compliance Gaps:
- Undocumented libraries accessed
- Non-compliant paths used
- Missing Notion documentation updates

### 2.4 Document Results & Issues

Create comprehensive documentation:
- Execution results summary
- Performance analysis
- Gap analysis report
- Issues encountered
- Recommendations for improvement
- Compliance status

## PHASE 3: Issue Remediation & Handoff

### 3.1 Categorize Issues

Group issues by:
- Severity (Critical, High, Medium, Low)
- Type (Functional, Performance, Accuracy, Documentation, Compliance)
- Remediation Complexity (Simple, Moderate, Complex)

### 3.2 Attempt Immediate Remediation

For issues that can be fixed immediately:
- Fix code bugs
- Update configuration
- Improve error handling
- Add missing documentation
- Optimize performance
- Fix compliance issues (document missing libraries)

### 3.3 Create Handoff to Claude Code Agent

For issues requiring code agent expertise:

Create Notion task in Agent-Tasks database:

```
notionApi:API-post-page on 284e73616c278018872aeb14e82e0392

properties: {
  Name: {title: [{text: {content: "Eagle Library Merge: Issue Remediation - {issue_summary}"}}]},
  Status: {status: {name: "Not Started"}},
  Priority: {select: {name: "{priority}"}},
  Description: {rich_text: [{text: {content: "{detailed_issue_description}\n\nExecution Results:\n{execution_results}\n\nGap Analysis:\n{gap_analysis}\n\nCompliance Status:\n{compliance_status}\n\nRemediation Requirements:\n{remediation_requirements}\n\nAcceptance Criteria:\n{acceptance_criteria}"}}]},
  Assigned Agent: {relation: [{id: "Claude Code Agent ID"}]},
  Source Agent: {rich_text: [{text: {content: "Claude MM1 Agent"}}]}
}
```

### 3.4 Wait for Remediation Response

MANDATORY: Wait for Claude Code Agent to complete remediation before proceeding.

- Monitor Notion task status
- Review code changes made
- Verify fixes are complete
- Test remediated functions
- Verify compliance maintained

**DO NOT proceed to Phase 4 until remediation is complete and verified.**

## PHASE 4: Second Production Run & Validation

### 4.1 Execute Second Production Run

Only proceed if Phase 3 remediation allows for effective execution:

```bash
cd /Users/brianhellemn/Projects/github-production

python3 monolithic-scripts/soundcloud_download_prod_merge-2.py \
  --mode merge \
  --merge-previous-library "/Volumes/OF-CP2019-2025/Music Library-2.library" \
  --merge-current-library "/Volumes/VIBES/Music Library-2.library" \
  --merge-live \
  --dedup-threshold 0.75 \
  --dedup-cleanup \
  --debug
```

**Note:** Use `--merge-live` and `--dedup-cleanup` only after verifying dry-run results.

### 4.2 Document and Validate Results

Compare second run to first run:

A. Results Comparison:
- Items imported (should match dry-run predictions)
- Items skipped (should match dry-run predictions)
- Execution time (should be similar or better)
- Accuracy (should be same or better)

B. Validation:
- Verify items were actually imported
- Verify duplicates were properly skipped
- Verify post-merge deduplication ran successfully
- Verify duplicates were moved to trash (if cleanup enabled)
- Verify library integrity maintained
- Verify previous library cleanup (if performed)

C. Performance Validation:
- Execution time acceptable
- Memory usage acceptable
- API calls within limits
- No errors or warnings

D. Compliance Validation:
- Verify execution used documented paths
- Verify no undocumented libraries accessed
- Verify Notion documentation updated if needed

### 4.3 Create Validation Report

Document:
- Second run execution results
- Comparison to first run
- Validation findings
- Remaining issues (if any)
- Recommendations
- Compliance status

## PHASE 5: Iterative Execution Until Complete

### 5.1 Check for Remaining Issues

After each production run:

```bash
python3 monolithic-scripts/soundcloud_download_prod_merge-2.py \
  --mode merge \
  --merge-previous-library "/Volumes/OF-CP2019-2025/Music Library-2.library" \
  --dedup-threshold 0.75 \
  --debug
```

Review results:
- If items remain to be imported: Proceed to Phase 5.2
- If all items processed: Proceed to Phase 6 (Completion)

### 5.2 Analyze Remaining Issues

For remaining items:
- Identify why they weren't imported
- Review duplicate detection results
- Adjust similarity threshold if needed
- Review matching strategies
- Identify edge cases

### 5.3 Repeat Phases 1-4

If items remain:
- Return to Phase 1 (Review & Status)
- Execute Phase 2 (Production Run)
- Execute Phase 3 (Issue Remediation)
- Execute Phase 4 (Second Production Run)
- Return to Phase 5.1 (Check for Remaining)

**Continue iterating until merge is complete.**

## PHASE 6: Completion & Documentation

### 6.1 Final Verification

Execute final dry-run to confirm:

```bash
python3 monolithic-scripts/soundcloud_download_prod_merge-2.py \
  --mode merge \
  --merge-previous-library "/Volumes/OF-CP2019-2025/Music Library-2.library" \
  --dedup-threshold 0.75 \
  --debug
```

Verify:
- All items processed (imported or skipped)
- No remaining items to import
- Library integrity maintained
- All best items preserved
- System compliance maintained

### 6.2 Update Notion Documentation

MANDATORY: Update Music Directories database with final status:

For both libraries:

```
notionApi:API-patch-page on {library_page_id}

properties: {
  Last Merge: {date: {start: today}},
  Items Merged: {number: {total_items_merged}},
  Items Imported: {number: {items_imported}},
  Items Skipped: {number: {items_skipped}},
  Duplicates Removed: {number: {total_duplicates_removed}},
  Space Recovered: {number: {space_recovered_bytes}},
  Status: {select: {name: "Merged"}}
}
```

### 6.3 Create Final Documentation

Document:
- Complete execution history
- All issues encountered and resolved
- Performance metrics
- Final library state
- Recommendations for future merges
- Compliance verification
- Notion documentation updates

### 6.4 Update Workflow Documentation

Update:
- Create `EAGLE_LIBRARY_MERGE_EXECUTION_REPORT.md`
- Update any relevant workflow status documents
- Document compliance verification process

## Error Handling

| Error Type | Severity | Action |
|------------|----------|--------|
| Music Directories DB not found | CRITICAL | Create Agent-Task, STOP execution |
| Previous library not found | CRITICAL | Verify path, check volume mount, STOP execution |
| Current library not found | CRITICAL | Verify EAGLE_LIBRARY_PATH, STOP execution |
| Library not documented in Notion | HIGH | Document in Notion, continue |
| Compliance verification fails | CRITICAL | Fix compliance issues, re-verify |
| Eagle API not accessible | CRITICAL | Launch Eagle, wait for API, retry |
| Library path not found | CRITICAL | Verify library path, check volume mount |
| Library switch fails | CRITICAL | Verify Eagle API, check library paths, retry |
| Function not found | CRITICAL | Verify script location, check imports |
| Dry-run execution fails | HIGH | Review error logs, fix issues, retry |
| Live execution fails | HIGH | Revert to dry-run, review errors, create handoff |
| Import fails | HIGH | Review error logs, fix issues, retry |
| Deduplication fails | MEDIUM | Log failures, continue with remaining items |
| Previous library cleanup fails | LOW | Log warning, manual cleanup required |
| Performance issues | MEDIUM | Document, optimize if possible, create handoff |
| False positives detected | HIGH | Adjust threshold, review matching logic |
| False negatives detected | HIGH | Review matching strategies, create handoff |

## Completion Gates

All must pass for "Success":

**Phase 0 (Compliance):**
- Music Directories database accessible
- All local libraries scanned
- All local libraries documented in Notion
- Both previous and current libraries documented in Notion
- Compliance status: COMPLIANT

**Pre-Execution:**
- Eagle application running and accessible
- Production merge functions identified
- Function status documented
- Related documentation reviewed
- Compliance verified

**Phase 1:**
- All merge functions reviewed
- Function capabilities assessed
- Independent execution verified
- Status documented
- System compliance verified

**Phase 2:**
- Production run executed successfully
- Technical output audited
- Gap analysis completed
- Results and issues documented
- Compliance maintained

**Phase 3:**
- Issues categorized
- Immediate remediation attempted
- Handoff created for complex issues
- Remediation completed and verified
- Compliance maintained

**Phase 4:**
- Second production run executed
- Results validated
- Validation report created
- Compliance validated

**Phase 5:**
- Iterative execution completed
- All items processed

**Phase 6:**
- Final verification passed
- Complete documentation created
- Workflow documentation updated
- Notion documentation updated
- Compliance maintained

Report: "Merge Complete - Success" if ALL pass. Otherwise "Merge Complete - Partial" with remaining issues.

## Value-Adding Actions Checklist

Phase 0 (Compliance):
- [ ] Verified Music Directories database exists
- [ ] Scanned local filesystem for Eagle libraries
- [ ] Loaded documented libraries from Notion
- [ ] Compared local vs Notion libraries
- [ ] Created Notion entries for missing libraries
- [ ] Updated incorrect paths in Notion
- [ ] Verified both previous and current libraries documented
- [ ] Documented compliance status
- [ ] Achieved COMPLIANT status

Before execution:
- [ ] Verified Eagle application is running
- [ ] Identified all merge functions
- [ ] Reviewed related documentation
- [ ] Documented current state
- [ ] Verified compliance

Phase 1:
- [ ] Reviewed function implementation
- [ ] Verified function availability
- [ ] Assessed function capabilities
- [ ] Verified independent execution
- [ ] Verified system compliance
- [ ] Documented function status

Phase 2:
- [ ] Executed first production run (dry-run)
- [ ] Audited technical output
- [ ] Analyzed performance metrics
- [ ] Completed gap analysis
- [ ] Verified compliance
- [ ] Documented results and issues

Phase 3:
- [ ] Categorized issues
- [ ] Attempted immediate remediation
- [ ] Created handoff to Claude Code Agent
- [ ] Waited for remediation response
- [ ] Verified remediation completion
- [ ] Verified compliance maintained

Phase 4:
- [ ] Executed second production run
- [ ] Documented and validated results
- [ ] Validated compliance
- [ ] Created validation report

Phase 5:
- [ ] Checked for remaining items
- [ ] Analyzed remaining items (if any)
- [ ] Repeated phases 1-4 as needed
- [ ] Confirmed all items processed

Phase 6:
- [ ] Performed final verification
- [ ] Updated Notion documentation
- [ ] Created final documentation
- [ ] Updated workflow documentation
- [ ] Verified final compliance

---

<details>
<summary>📄 Document Metadata</summary>

**Doc Key:** DOC_PROMPT_EAGLE_MERGE_V1_SYSTEM_COMPLIANT

**Version:** 1.0

**Doc Level:** L2

**Category:** Pipelines

**Primary Owner:** Claude MM1 Agent

**Last Updated:** 2026-01-10

## Changelog

**v1.0 (2026-01-10)**
- Initial creation - System Compliant Edition
- Added Phase 0: System Compliance Verification for Libraries
- Requires both previous and current libraries documented in Notion
- Mandatory compliance verification before execution
- Updates Notion documentation throughout workflow
- System-mandated and compliant execution
- Adapted from deduplication workflow structure

</details>

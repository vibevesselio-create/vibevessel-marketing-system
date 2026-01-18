#!/usr/bin/env python3
"""
Create handoff trigger file for VIBES reorganization issue
"""

import sys
from pathlib import Path
from datetime import datetime, timezone
import json

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from main import create_trigger_file, normalize_agent_folder_name

# Issue details
ISSUE_ID = "2e4e7361-6c27-814c-b185-e57749b1dc47"
ISSUE_URL = "https://www.notion.so/VIBES-Volume-Comprehensive-Music-Reorganization-Indexing-Deduplication-Cleanup-2e4e73616c27814cb185e57749b1dc47"
ISSUE_TITLE = "VIBES Volume Comprehensive Music Reorganization: Indexing, Deduplication & Cleanup"

# Agent details (Cursor MM1 for implementation)
AGENT_NAME = "Cursor MM1 Agent"
AGENT_ID = "249e7361-6c27-8100-8a74-de7eabb9fc8d"  # Cursor MM1 Agent ID
AGENT_TYPE = "MM1"

# Read handoff document
handoff_doc_path = Path(__file__).parent / "VIBES_REORGANIZATION_HANDOFF.md"
handoff_description = ""
if handoff_doc_path.exists():
    with open(handoff_doc_path, "r") as f:
        handoff_description = f.read()

# Build task details
task_details = {
    "task_id": ISSUE_ID,  # Using issue ID as task ID
    "task_title": f"Continue VIBES Volume Reorganization - Phase 1 Completion & Phases 2-6",
    "task_url": ISSUE_URL,
    "project_id": None,
    "project_title": None,
    "description": f"""## Task: Continue VIBES Volume Reorganization

**Issue:** {ISSUE_TITLE}
**Issue ID:** {ISSUE_ID}
**Issue URL:** {ISSUE_URL}

## Current Status

Phase 1 (Analysis & Indexing) is partially complete:
- ✅ Volume scan completed (20,148 files cataloged)
- ✅ Directory structure analysis complete
- ✅ Reorganization script framework created
- ⏳ Metadata extraction pending (20,148 files)
- ⏳ Audio fingerprint generation pending
- ⏳ Comprehensive file index database pending
- ⏳ Duplicate detection pending

## Required Work

### Immediate Priority: Complete Phase 1
1. **Enhance Script:**
   - Add resume capability (checkpoint/restore)
   - Add batch processing with progress tracking
   - Add error recovery and retry logic
   - Add ETA calculation

2. **Execute Metadata Extraction:**
   - Process 20,148 files in batches (recommended: 1000 files per batch)
   - Extract Artist, Album, Title, BPM, Key metadata
   - Generate audio fingerprints for deduplication
   - Create comprehensive file index database

3. **Identify Duplicates:**
   - Use fingerprint matching (95%+ similarity threshold)
   - Use file hash comparison for exact duplicates
   - Group duplicates by fingerprint

### Subsequent Phases (2-6)
See `VIBES_VOLUME_REORGANIZATION_IMPLEMENTATION_PLAN.md` for detailed phase breakdown.

## Key Files

- **Script:** `reorganize_vibes_volume.py`
- **Implementation Plan:** `VIBES_VOLUME_REORGANIZATION_IMPLEMENTATION_PLAN.md`
- **Handoff Document:** `VIBES_REORGANIZATION_HANDOFF.md`
- **Analysis Report:** `logs/vibes_volume_analysis_report.json`

## Scale Considerations

- **20,148 files** to process
- **670.24 GB** total size
- Estimated processing time: 4-8 hours for full metadata extraction
- **Recommendation:** Process in batches with resume capability

## Critical Directories

1. `/Volumes/VIBES/Apple-Music-Auto-Add` (143.31 GB, 2,396 files)
2. `/Volumes/VIBES/Playlists/Unassigned` (67.06 GB, 1,380 files)
3. `/Volumes/VIBES/Djay-Pro-Auto-Import` (61.82 GB, 2,410 files)

## Success Criteria

- All 20,148 files successfully indexed and cataloged
- Duplicate files identified and archived (not deleted)
- Metadata extracted and validated for all files
- Zero data loss (all files preserved)
- Directory structure matches production workflow specifications

## Handoff Instructions

Upon completion of your work:
1. **MOVE TRIGGER FILE (MANUAL)**: You MUST manually call `mark_trigger_file_processed()` to move the trigger file from 01_inbox to 02_processed. This cannot be automated - you are responsible for moving it.
2. Update issue status in Notion
3. Document progress and findings
4. Create next handoff trigger file if work continues to Phase 2-6
5. Create validation task for work review
6. Run `python3 main.py` to generate task handoff flow

## Next Handoff Requirements

When Phase 1 is complete, create handoff trigger for:
- **Agent:** Claude MM1 Agent (for Phase 2 planning/review)
- **Task:** "Review Phase 1 Results and Plan Phase 2 Deduplication"

When Phase 2-6 are complete, create handoff trigger for:
- **Agent:** Claude MM1 Agent (for validation)
- **Task:** "Agent Work Validation Task - VIBES Reorganization"

**MANDATORY:** Task is NOT complete until trigger file is manually moved and next handoff file is created (if applicable).

## Questions or Issues

Direct all questions and issues to the "Issues+Questions" database in Notion.
""",
    "status": "Ready",
    "agent_name": AGENT_NAME,
    "agent_id": AGENT_ID,
    "priority": "High",
    "handoff_instructions": f"""
**CRITICAL HANDOFF REQUIREMENTS:**

1. **MOVE TRIGGER FILE (MANUAL)**: Upon reading this trigger file, you MUST manually call `mark_trigger_file_processed()` from main.py to move this file from 01_inbox to 02_processed. This cannot be automated.

2. **Review Handoff Document**: Read `VIBES_REORGANIZATION_HANDOFF.md` for complete context.

3. **Review Implementation Plan**: Read `VIBES_VOLUME_REORGANIZATION_IMPLEMENTATION_PLAN.md` for detailed phase breakdown.

4. **Execute Phase 1 Completion**: Complete metadata extraction, fingerprinting, and duplicate detection for all 20,148 files.

5. **Create Next Handoff**: Upon completion, create handoff trigger file for Claude MM1 Agent to review Phase 1 results and plan Phase 2.

6. **Update Notion**: Update issue status and document progress.

7. **Run main.py**: After creating handoff files, run `python3 main.py` to generate task handoff flow.

**NO EXCEPTIONS. TASK IS NOT COMPLETE UNTIL TRIGGER FILE IS MANUALLY MOVED AND HANDOFF FILE IS CREATED.**
"""
}

# Create trigger file
trigger_file = create_trigger_file(AGENT_TYPE, AGENT_NAME, task_details)

if trigger_file:
    print(f"✅ Created trigger file: {trigger_file}")
    print(f"   Agent: {AGENT_NAME}")
    print(f"   Task: {task_details['task_title']}")
    print(f"   Issue: {ISSUE_TITLE}")
else:
    print("❌ Failed to create trigger file")
    sys.exit(1)

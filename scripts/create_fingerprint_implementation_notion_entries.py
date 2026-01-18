#!/usr/bin/env python3
"""
Create Comprehensive Notion Entries for Eagle Library Fingerprint Implementation

This script creates all necessary Notion entries for the complete fingerprinting
system implementation across all Eagle library workflows:

1. Master Issue in Issues+Questions database
2. Agent-Projects entry for the implementation project
3. Agent-Tasks entries for each implementation phase
4. Updates to existing related entries

Database IDs:
- Agent-Tasks: 284e73616c278018872aeb14e82e0392
- Issues+Questions: 229e73616c27808ebf06c202b10b5166
- Agent-Projects: 286e73616c2781ffa450db2ecad4b0ba
"""

import os
import sys
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

try:
    from unified_config import load_unified_env, get_unified_config
    load_unified_env()
except ImportError:
    pass

try:
    from notion_client import Client
except ImportError:
    print("ERROR: notion_client not installed. Run: pip install notion-client")
    sys.exit(1)

# Database IDs
AGENT_TASKS_DB_ID = "284e73616c278018872aeb14e82e0392"
ISSUES_QUESTIONS_DB_ID = "229e73616c27808ebf06c202b10b5166"
AGENT_PROJECTS_DB_ID = "286e73616c2781ffa450db2ecad4b0ba"

# Existing related page IDs (from conversation)
EXISTING_FINGERPRINT_ISSUE_ID = "2e5e7361-6c27-8186-94a9-f80a3ac01074"
EXISTING_FINGERPRINT_TASK_ID = "2e5e7361-6c27-81e9-8efa-e7957e897819"
CRITICAL_DEDUP_FALSE_POSITIVE_ID = "2e4e73616c27818aa76aedb285502427"


def get_notion_client() -> Client:
    """Get Notion client from shared_core token manager."""
    # Use centralized token manager (MANDATORY per CLAUDE.md)
    try:
        from shared_core.notion.token_manager import get_notion_token
        api_key = get_notion_token()
        if api_key:
            return Client(auth=api_key)
    except ImportError:
        pass

    # Fallback for backwards compatibility
    api_key = (
        os.getenv("NOTION_API_KEY") or
        os.getenv("NOTION_TOKEN") or
        os.getenv("NOTION_API_TOKEN")
    )

    if not api_key:
        raise ValueError("NOTION_TOKEN not found in token_manager or environment")

    return Client(auth=api_key)


def create_master_issue(client: Client) -> str:
    """Create the master issue in Issues+Questions database."""

    issue_name = "CRITICAL: Complete Fingerprinting System Implementation Across ALL Eagle Library Workflows"

    description = """## Executive Summary

A comprehensive audit of the Cursor MM1 Agent's Eagle Library deduplication work has revealed critical gaps in the fingerprinting system implementation. The deduplication workflow was executed prematurely without proper fingerprint validation, resulting in **7,374 files incorrectly moved to trash** (false positives).

## Root Cause Analysis

1. **Fingerprints Not Embedded in Existing Files**: 0 out of 12,323 files have fingerprints embedded
2. **Fingerprint Strategy Found 0 Groups**: Deduplication relied entirely on error-prone name-based fuzzy matching
3. **Transitive Closure Bug**: Items incorrectly grouped without pairwise similarity verification
4. **No Safeguards**: Live execution proceeded despite fingerprint matching returning 0 groups

## Scope

This issue covers fingerprinting implementation across ALL Eagle library workflows:
- Music/Audio workflows (primary focus)
- Image/Photo workflows (eagle_to_notion_sync.py)
- Video/Design asset workflows (future)
- All 67+ Eagle-related functions in the codebase

## Required Implementation

### Phase 1: Batch Fingerprint Embedding for Existing Files
- Create batch processing script for 12,323+ existing files
- Compute SHA-256 fingerprints for all audio files
- Embed fingerprints in file metadata (M4A, MP3, FLAC, AIFF)
- Sync fingerprints to Eagle tags

### Phase 2: Fix Deduplication Logic
- Fix transitive closure bug in fuzzy matching
- Add safeguards to prevent execution with 0 fingerprint groups
- Require pairwise similarity for group membership
- Make fingerprints PRIMARY matching strategy

### Phase 3: Integrate Across All Eagle Functions
- Audit all 67+ Eagle functions for fingerprint gaps
- Ensure fingerprint computation in all import workflows
- Add automatic fingerprint sync after imports
- Update EagleClient and EagleDeduplicator modules

### Phase 4: Asset Type Expansion
- Extend fingerprinting to images (imagehash integration)
- Plan for video fingerprinting
- Document fingerprinting strategy per asset type

## Related Documentation

- CRITICAL_DEDUP_ISSUE_ANALYSIS.md
- FINGERPRINT_SYSTEM_IMPLEMENTATION_GAP.md
- FINGERPRINT_ANALYSIS_RESULTS.md
- Cursor MM1 Agent conversation export

## Impact Assessment

- **Critical**: Data loss occurred (7,374 files to trash)
- **High**: Fingerprint infrastructure exists but unused
- **High**: All Eagle workflows affected
- **Medium**: Recovery possible via Eagle Trash"""

    properties = {
        "Name": {"title": [{"text": {"content": issue_name}}]},
        "Status": {"status": {"name": "Troubleshooting"}},  # Valid: Unreported, Troubleshooting, Waiting on Client, Reported + Waiting For Response, Solution In Progress, Resolved
        "Priority": {"select": {"name": "High"}},  # Valid: -, Lowest, Low, Medium, High
        "Type": {"multi_select": [
            {"name": "Bug"},
            {"name": "Internal Issue"},
        ]},
        "Tags": {"multi_select": [
            {"name": "Scripts"},
        ]},
        "Description": {"rich_text": [{"text": {"content": description[:2000]}}]},
    }

    # Check if already exists
    existing = client.databases.query(
        database_id=ISSUES_QUESTIONS_DB_ID,
        filter={"property": "Name", "title": {"contains": "Complete Fingerprinting System Implementation"}}
    )

    if existing.get("results"):
        page_id = existing["results"][0]["id"]
        print(f"Master issue already exists: {page_id}")
        return page_id

    response = client.pages.create(
        parent={"database_id": ISSUES_QUESTIONS_DB_ID},
        properties=properties
    )

    page_id = response.get("id")
    print(f"Created master issue: {page_id}")
    return page_id


def create_agent_project(client: Client, master_issue_id: str) -> str:
    """Create Agent-Projects entry for the implementation project."""

    project_name = "Eagle Library Fingerprinting System - Complete Implementation"

    description = """## Project Overview

Complete implementation of fingerprinting system across ALL Eagle library workflows to enable accurate duplicate detection and prevent false positives.

## Background

The existing fingerprinting infrastructure in the codebase is functional but not fully deployed:
- Fingerprint computation: compute_file_fingerprint() - WORKS
- Fingerprint embedding: embed_fingerprint_in_metadata() - WORKS
- Fingerprint extraction: extract_fingerprint_from_metadata() - WORKS
- Eagle tag sync: sync_fingerprints_to_eagle_tags() - WORKS (manual mode)
- Fingerprint matching in dedup: eagle_library_deduplication() - EXISTS but found 0 groups

## Problem Statement

12,323+ files in the Eagle library have NO fingerprints embedded, causing:
- Deduplication to rely on error-prone name-based matching
- 7,374 false positives (non-duplicate files moved to trash)
- Inaccurate duplicate detection across all workflows

## Deliverables

1. Batch fingerprint embedding script for existing files
2. Fixed deduplication logic with safeguards
3. Automatic fingerprint sync in all import workflows
4. Updated EagleClient and EagleDeduplicator modules
5. Asset type expansion (images, videos)
6. Comprehensive documentation and tests

## Success Criteria

- 100% fingerprint coverage for existing files
- Zero false positives in deduplication
- Automatic fingerprint handling in all workflows
- Documentation and testing complete

## Timeline

- Phase 1: 2-3 days (batch embedding)
- Phase 2: 1-2 days (fix dedup logic)
- Phase 3: 2-3 days (integrate all functions)
- Phase 4: 1-2 days (asset expansion)

## Assigned Agents

- Claude Code Agent (primary)
- Cursor MM1 Agent (support)"""

    properties = {
        "Project Name": {"title": [{"text": {"content": project_name}}]},  # Changed from Name to Project Name
        "Status": {"status": {"name": "In Progress"}},  # Valid: Completed, In Progress, Planning, On Hold
        "Priority": {"select": {"name": "High"}},  # Need to verify
        "Summary": {"rich_text": [{"text": {"content": description[:2000]}}]},  # Changed from Description to Summary
        "Issues": {"relation": [{"id": master_issue_id}]},  # Changed from Issues+Questions to Issues
    }

    # Check if exists
    existing = client.databases.query(
        database_id=AGENT_PROJECTS_DB_ID,
        filter={"property": "Project Name", "title": {"contains": "Eagle Library Fingerprinting System"}}
    )

    if existing.get("results"):
        page_id = existing["results"][0]["id"]
        print(f"Agent project already exists: {page_id}")
        return page_id

    response = client.pages.create(
        parent={"database_id": AGENT_PROJECTS_DB_ID},
        properties=properties
    )

    page_id = response.get("id")
    print(f"Created agent project: {page_id}")
    return page_id


def create_agent_tasks(client: Client, project_id: str, master_issue_id: str) -> List[str]:
    """Create Agent-Tasks entries for each implementation phase."""

    tasks = [
        {
            "name": "Phase 1: Batch Fingerprint Embedding for Existing Files",
            "status": "Ready",
            "priority": "Critical",
            "description": """## Objective

Create and execute batch fingerprint embedding for all 12,323+ existing files in the Eagle library.

## Tasks

1. Create batch processing script:
   - Scan all files in Eagle library via API
   - For each file: compute SHA-256 fingerprint
   - Embed fingerprint in file metadata (M4A, MP3, FLAC, AIFF)
   - Handle WAV files separately (limited metadata support)

2. Execute batch processing:
   - Run in batches of 100-500 files
   - Log progress and errors
   - Generate completion report

3. Sync fingerprints to Eagle tags:
   - Run fp-sync mode after embedding
   - Verify all items have fingerprint tags
   - Report coverage statistics

## Success Criteria

- [ ] Batch script created and tested
- [ ] All 12,323+ files processed
- [ ] Fingerprints embedded in file metadata
- [ ] Fingerprints synced to Eagle tags
- [ ] Coverage report shows >95% success

## Files to Modify

- NEW: scripts/batch_fingerprint_embedding.py
- Use: monolithic-scripts/soundcloud_download_prod_merge-2.py (functions)

## Technical Notes

- Use compute_file_fingerprint() for hash computation
- Use embed_fingerprint_in_metadata() for embedding
- Use sync_fingerprints_to_eagle_tags() for Eagle sync
- Handle errors gracefully (corrupted files, permissions)""",
        },
        {
            "name": "Phase 2: Fix Deduplication Logic and Add Safeguards",
            "status": "Ready",
            "priority": "Critical",
            "description": """## Objective

Fix the transitive closure bug and add safeguards to prevent false positives in deduplication.

## Tasks

1. Fix transitive closure bug:
   - Require pairwise similarity for ALL group members
   - Items must match each other, not just seed item
   - Implement proper connected components algorithm

2. Add safeguards:
   - Block live execution if fingerprint groups = 0 and library > 1000 items
   - Require minimum fingerprint coverage before live dedup
   - Add confirmation prompt for large operations

3. Improve matching logic:
   - Make fingerprint matching PRIMARY (not optional)
   - Increase fuzzy threshold for name-only matching (0.90+)
   - Add metadata verification (duration, file size, BPM)

## Success Criteria

- [ ] Transitive closure bug fixed
- [ ] Safeguards prevent premature execution
- [ ] Fingerprints are primary matching strategy
- [ ] Test cases pass (known duplicates, known non-duplicates)

## Files to Modify

- monolithic-scripts/soundcloud_download_prod_merge-2.py
  - eagle_library_deduplication() (line 5701)
  - Fuzzy matching logic (lines 5852-5896)

## Code Changes Required

```python
# Add safeguard (in eagle_library_deduplication):
if cleanup_duplicates and len(fp_groups) == 0 and len(all_items) > 1000:
    workspace_logger.error("BLOCKED: Cannot run live cleanup with 0 fingerprint groups")
    return {"error": "No fingerprint groups found - run fp-sync first"}
```""",
        },
        {
            "name": "Phase 3: Integrate Fingerprinting Across All Eagle Functions",
            "status": "Ready",
            "priority": "High",
            "description": """## Objective

Audit and update all 67+ Eagle functions to properly use fingerprinting.

## Functions to Review

### Core Client (music_workflow/integrations/eagle/client.py)
- [ ] EagleClient.import_file() - Add fingerprint parameter
- [ ] EagleClient.import_url() - Add fingerprint support
- [ ] EagleClient.add_tags() - Support fingerprint tags

### Deduplication Module (music_workflow/deduplication/eagle_dedup.py)
- [ ] EagleDeduplicator.check_duplicate() - Add fingerprint check
- [ ] check_eagle_duplicate() - Add fingerprint parameter

### Main Script Functions
- [ ] eagle_add_item() - Ensure fingerprint tag added
- [ ] eagle_add_item_adapter() - Already has fingerprint support (verify)
- [ ] eagle_import_with_duplicate_management() - Already has fingerprint (verify)
- [ ] eagle_find_best_matching_item() - Already has fingerprint (verify)

### Workflow Scripts
- [ ] eagle_to_notion_sync.py - Add audio fingerprint support
- [ ] eagle_realtime_sync.py - Add fingerprint handling
- [ ] mcp_eagle_integration.py - Add fingerprint tracking

## Success Criteria

- [ ] All Eagle functions audited
- [ ] Fingerprint gaps identified and fixed
- [ ] Automatic fingerprint sync after imports
- [ ] Integration tests pass""",
        },
        {
            "name": "Phase 4: Asset Type Expansion and Documentation",
            "status": "Ready",
            "priority": "Medium",
            "description": """## Objective

Extend fingerprinting support to other asset types and create comprehensive documentation.

## Tasks

### Asset Type Expansion

1. Images:
   - eagle_to_notion_sync.py already uses imagehash
   - Integrate imagehash into main Eagle workflows
   - Support: pHash, dHash, aHash, wHash

2. Videos (future):
   - Research video fingerprinting approaches
   - Document recommended libraries (videohash, etc.)
   - Create implementation plan

3. Design Files (future):
   - Evaluate fingerprinting options
   - Document approach

### Documentation

1. Update README with fingerprinting section
2. Create FINGERPRINTING_GUIDE.md:
   - How fingerprinting works
   - Supported formats
   - CLI commands (fp-sync, dedup)
   - Troubleshooting

3. Create API documentation:
   - Document all fingerprint functions
   - Usage examples
   - Error handling

### Testing

1. Create test suite:
   - Test fingerprint computation
   - Test fingerprint embedding
   - Test fingerprint extraction
   - Test deduplication accuracy

## Success Criteria

- [ ] Image fingerprinting integrated
- [ ] Video fingerprinting documented
- [ ] FINGERPRINTING_GUIDE.md created
- [ ] Test suite passes""",
        },
        {
            "name": "Phase 5: Restore Falsely Trashed Files and Verify",
            "status": "Ready",
            "priority": "Critical",
            "description": """## Objective

Review and restore files incorrectly moved to Eagle Trash during the premature deduplication.

## Tasks

1. Audit Eagle Trash:
   - List all 7,374 items in trash
   - Identify items moved on 2026-01-11
   - Categorize by match type (fuzzy vs fingerprint)

2. Identify false positives:
   - Items with match_type = "fuzzy" are suspect
   - Items with match_type = "ngram" are suspect
   - Items with match_type = "fingerprint" are likely true duplicates

3. Restore false positives:
   - Move non-duplicate items back from trash
   - Verify files restored correctly
   - Document restoration count

4. Verification:
   - Re-run deduplication (dry-run) with fixed logic
   - Compare results to original run
   - Verify no false positives

## Success Criteria

- [ ] Trash audit completed
- [ ] False positives identified
- [ ] Non-duplicate files restored
- [ ] Verification dry-run shows improvement
- [ ] Documentation of restored items""",
        },
    ]

    created_ids = []

    for task_data in tasks:
        # Check if exists
        existing = client.databases.query(
            database_id=AGENT_TASKS_DB_ID,
            filter={"property": "Task Name", "title": {"equals": task_data["name"]}}
        )

        if existing.get("results"):
            page_id = existing["results"][0]["id"]
            print(f"Task already exists: {task_data['name'][:50]}... ({page_id})")
            created_ids.append(page_id)
            continue

        properties = {
            "Task Name": {"title": [{"text": {"content": task_data["name"]}}]},
            "Status": {"status": {"name": task_data["status"]}},  # Valid: Archived, Completed, Ready, Draft, Planning, Ready To Publish, In Progress, Review, Blocked, Failed
            "Priority": {"select": {"name": task_data["priority"]}},  # Need to verify valid values
            "Description": {"rich_text": [{"text": {"content": task_data["description"][:2000]}}]},
            "🤖 Agent-Projects": {"relation": [{"id": project_id}]},  # Changed from Agent-Projects
            "Issues+Questions": {"relation": [{"id": master_issue_id}]},  # Keep as is
        }

        response = client.pages.create(
            parent={"database_id": AGENT_TASKS_DB_ID},
            properties=properties
        )

        page_id = response.get("id")
        print(f"Created task: {task_data['name'][:50]}... ({page_id})")
        created_ids.append(page_id)

    return created_ids


def update_existing_entries(client: Client, project_id: str, master_issue_id: str):
    """Update existing related Notion entries to link to the new project."""

    # Update existing fingerprint issue (from Cursor MM1 Agent) - Issues+Questions database
    if EXISTING_FINGERPRINT_ISSUE_ID:
        try:
            client.pages.update(
                page_id=EXISTING_FINGERPRINT_ISSUE_ID,
                properties={
                    "Status": {"status": {"name": "Solution In Progress"}},
                    "Agent-Projects": {"relation": [{"id": project_id}]},
                }
            )
            print(f"Updated existing fingerprint issue: {EXISTING_FINGERPRINT_ISSUE_ID}")
        except Exception as e:
            print(f"Warning: Could not update existing issue: {e}")

    # Update existing fingerprint task (from Cursor MM1 Agent) - Agent-Tasks database
    if EXISTING_FINGERPRINT_TASK_ID:
        try:
            client.pages.update(
                page_id=EXISTING_FINGERPRINT_TASK_ID,
                properties={
                    "Status": {"status": {"name": "In Progress"}},
                    "🤖 Agent-Projects": {"relation": [{"id": project_id}]},
                    "Issues+Questions": {"relation": [{"id": master_issue_id}]},
                }
            )
            print(f"Updated existing fingerprint task: {EXISTING_FINGERPRINT_TASK_ID}")
        except Exception as e:
            print(f"Warning: Could not update existing task: {e}")

    # Update critical dedup false positive issue - Issues+Questions database
    if CRITICAL_DEDUP_FALSE_POSITIVE_ID:
        try:
            client.pages.update(
                page_id=CRITICAL_DEDUP_FALSE_POSITIVE_ID,
                properties={
                    "Agent-Projects": {"relation": [{"id": project_id}]},
                }
            )
            print(f"Updated critical dedup issue: {CRITICAL_DEDUP_FALSE_POSITIVE_ID}")
        except Exception as e:
            print(f"Warning: Could not update critical issue: {e}")


def main():
    """Create all Notion entries for fingerprint implementation project."""

    print("=" * 80)
    print("EAGLE LIBRARY FINGERPRINT IMPLEMENTATION - NOTION ENTRIES CREATION")
    print("=" * 80)
    print()

    # Get Notion client
    try:
        client = get_notion_client()
        print("Notion client initialized successfully")
    except Exception as e:
        print(f"ERROR: Failed to initialize Notion client: {e}")
        sys.exit(1)

    print()
    print("Creating Notion entries...")
    print("-" * 40)

    # 1. Create master issue
    print("\n1. Creating master issue in Issues+Questions...")
    master_issue_id = create_master_issue(client)

    # 2. Create agent project
    print("\n2. Creating agent project...")
    project_id = create_agent_project(client, master_issue_id)

    # 3. Create agent tasks
    print("\n3. Creating agent tasks...")
    task_ids = create_agent_tasks(client, project_id, master_issue_id)

    # 4. Update existing entries
    print("\n4. Updating existing related entries...")
    update_existing_entries(client, project_id, master_issue_id)

    # Summary
    print()
    print("=" * 80)
    print("CREATION COMPLETE")
    print("=" * 80)
    print()
    print("Created/Updated:")
    print(f"  - Master Issue: {master_issue_id}")
    print(f"  - Agent Project: {project_id}")
    print(f"  - Agent Tasks: {len(task_ids)} tasks")
    print()
    print("Notion URLs:")
    print(f"  - Master Issue: https://www.notion.so/{master_issue_id.replace('-', '')}")
    print(f"  - Agent Project: https://www.notion.so/{project_id.replace('-', '')}")
    print()
    print("Next Steps:")
    print("  1. Review created entries in Notion")
    print("  2. Begin Phase 1: Batch Fingerprint Embedding")
    print("  3. Assign tasks to appropriate agents")
    print("  4. Track progress in Agent-Tasks database")


if __name__ == "__main__":
    main()

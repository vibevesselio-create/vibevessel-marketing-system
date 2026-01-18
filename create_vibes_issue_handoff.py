#!/usr/bin/env python3
"""
Create handoff for VIBES Volume Reorganization Issue
Documents blocking point and creates handoff trigger file
"""

import os
import sys
import json
from pathlib import Path
from datetime import datetime, timezone

# Add project root to path
project_root = Path(__file__).parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

try:
    from notion_client import Client
    NOTION_AVAILABLE = True
except ImportError:
    print("ERROR: notion-client not available")
    NOTION_AVAILABLE = False
    sys.exit(1)

try:
    from shared_core.notion.token_manager import get_notion_token
    token = get_notion_token()
except ImportError:
    token = os.getenv("NOTION_TOKEN") or os.getenv("NOTION_API_TOKEN") or os.getenv("NOTION_API_KEY")

if not token:
    print("ERROR: No Notion token found")
    sys.exit(1)

# Import main.py functions
from main import (
    NotionManager,
    safe_get_property,
    create_trigger_file,
    normalize_agent_folder_name,
    determine_agent_type,
    add_mandatory_next_handoff_instructions
)
from shared_core.notion.folder_resolver import get_agent_inbox_path

# Database IDs
ISSUES_QUESTIONS_DB_ID = "229e73616c27808ebf06c202b10b5166"
AGENT_TASKS_DB_ID = "284e73616c278018872aeb14e82e0392"
PROJECTS_DB_ID = "286e73616c2781ffa450db2ecad4b0ba"

# Agent IDs
CLAUDE_MM1_AGENT_ID = "fa54f05c-e184-403a-ac28-87dd8ce9855b"
CURSOR_MM1_AGENT_ID = "249e7361-6c27-8100-8a74-de7eabb9fc8d"

client = Client(auth=token)
notion = NotionManager(token)

def get_database_status_options(database_id):
    """Get available status options for a database."""
    try:
        db = client.databases.retrieve(database_id=database_id)
        status_prop = db.get("properties", {}).get("Status", {})
        if status_prop.get("type") == "status":
            status_options = status_prop.get("status", {}).get("options", [])
            return [opt.get("name") for opt in status_options if opt.get("name")]
    except Exception:
        pass
    return []

def main():
    """Main execution."""
    print("=" * 80)
    print("VIBES Volume Reorganization Issue - Handoff Creation")
    print("=" * 80)
    
    issue_id = "2e4e7361-6c27-814c-b185-e57749b1dc47"
    
    # Get issue details
    try:
        issue_page = client.pages.retrieve(page_id=issue_id)
        issue_title = safe_get_property(issue_page, "Name", "title") or "Untitled Issue"
        issue_description = safe_get_property(issue_page, "Description", "rich_text") or ""
        issue_url = issue_page.get("url", "")
        
        print(f"\nIssue: {issue_title}")
        print(f"URL: {issue_url}")
    except Exception as e:
        print(f"❌ Failed to retrieve issue: {e}")
        return
    
    # Create implementation task
    task_description = f"""## Context
This task addresses the VIBES Volume Comprehensive Music Reorganization issue. Previous work has created an implementation plan and script framework, but execution is blocked by volume access permissions.

## Issue Details
- **Issue Title:** {issue_title}
- **Issue ID:** {issue_id}
- **Issue URL:** {issue_url}
- **Priority:** High
- **Current Status:** Unreported (work in progress)

## Work Completed So Far
1. ✅ Issue analysis completed (670.24 GB, 20,148 files, 7,578 directories)
2. ✅ Implementation plan created (`VIBES_VOLUME_REORGANIZATION_IMPLEMENTATION_PLAN.md`)
3. ✅ Reorganization script framework created (`reorganize_vibes_volume.py`)
4. ✅ Phase 1 script structure implemented (scanning, metadata extraction, fingerprinting)
5. ✅ Planning task created and linked to issue

## Current Blocking Point
**Volume Access Permission Issue:**
- Attempted to access `/Volumes/VIBES/` to begin Phase 1 execution
- Encountered "Permission denied" error when attempting to list directory contents
- Cannot proceed with file scanning, metadata extraction, or reorganization without volume access

## Required Actions
1. **Resolve Volume Access:**
   - Verify VIBES volume is mounted and accessible
   - Check file system permissions for `/Volumes/VIBES/`
   - Ensure script has necessary permissions to read/write
   - Test access with: `ls -la /Volumes/VIBES/`

2. **Execute Phase 1 - Analysis & Indexing:**
   - Run volume scan: `python3 reorganize_vibes_volume.py --phase 1`
   - Extract metadata from all 20,148 files
   - Generate audio fingerprints for deduplication
   - Create comprehensive file index database
   - Identify duplicate files using fingerprint matching
   - Generate Phase 1 report

3. **Execute Phase 2 - Deduplication Planning:**
   - Analyze duplicate groups from Phase 1
   - Determine best version to keep (prefer highest quality, most complete metadata)
   - Create deduplication mapping
   - Validate deduplication plan (dry-run)

4. **Execute Phase 3 - Directory Structure Creation:**
   - Create target directory structure:
     - `/Volumes/VIBES/Music/Automatically Add to Music.localized/`
     - `/Volumes/VIBES/Music-Backup/`
     - `/Volumes/VIBES/Music-Archive/`

5. **Execute Phase 4 - File Migration (Dry Run):**
   - Simulate file moves based on metadata
   - Verify target paths
   - Generate migration plan report

6. **Execute Phase 5 - File Migration (Live):**
   - Execute file migration with monitoring
   - Handle edge cases and errors
   - Verify file integrity after moves

7. **Execute Phase 6 - Cleanup & Verification:**
   - Verify migration success
   - Clean up empty directories
   - Generate final report
   - Update issue status to "Resolved"

## Key Files & Resources
- **Implementation Plan:** `VIBES_VOLUME_REORGANIZATION_IMPLEMENTATION_PLAN.md`
- **Reorganization Script:** `reorganize_vibes_volume.py`
- **Issue Work Summary:** `VIBES_ISSUE_RESOLUTION_WORK_SUMMARY.md`
- **Volume Path:** `/Volumes/VIBES/`

## Success Criteria
- [ ] Volume access resolved
- [ ] Phase 1 complete (all files indexed and fingerprinted)
- [ ] Phase 2 complete (deduplication plan created)
- [ ] Phase 3 complete (target structure created)
- [ ] Phase 4 complete (dry-run migration validated)
- [ ] Phase 5 complete (live migration executed)
- [ ] Phase 6 complete (cleanup and verification)
- [ ] Issue status updated to "Resolved"
- [ ] All work documented and synchronized to Notion

## Next Handoff
Upon completion, create a validation task for **Claude MM1 Agent** to review and validate the reorganization work.
"""
    
    # Get valid status options
    status_options = get_database_status_options(AGENT_TASKS_DB_ID)
    default_status = None
    for status in ["Ready", "Not Started", "Draft", "Proposed"]:
        if status in status_options:
            default_status = status
            break
    if not default_status and status_options:
        default_status = status_options[0]
    
    # Create task properties
    task_properties = {
        "Task Name": {
            "title": [{"text": {"content": "Execute: VIBES Volume Reorganization - Phase 1-6"}}]
        },
        "Description": {
            "rich_text": [{"text": {"content": task_description[:1997]}}]  # Notion limit
        },
        "Priority": {
            "select": {"name": "High"}
        },
        "Assigned-Agent": {
            "relation": [{"id": CURSOR_MM1_AGENT_ID}]
        }
    }
    
    if default_status:
        task_properties["Status"] = {
            "status": {"name": default_status}
        }
    
    # Create task
    try:
        response = client.pages.create(
            parent={"database_id": AGENT_TASKS_DB_ID},
            properties=task_properties
        )
        task_id = response.get("id")
        task_url = response.get("url", "")
        print(f"✅ Created Agent-Task: {task_url}")
        
        # Link issue to task
        try:
            client.pages.update(
                page_id=issue_id,
                properties={
                    "Agent-Tasks": {
                        "relation": [{"id": task_id}]
                    }
                }
            )
            print(f"✅ Linked issue to task")
        except Exception as e:
            print(f"⚠️  Could not link issue to task: {e}")
        
        # Create trigger file
        cursor_inbox_path = str(get_agent_inbox_path("Cursor MM1 Agent")) + "/"
        
        # Add mandatory next handoff instructions
        try:
            from shared_core.notion.task_creation import add_mandatory_next_handoff_instructions
            enhanced_description = add_mandatory_next_handoff_instructions(
                description=task_description,
                next_task_name="Validate: VIBES Volume Reorganization",
                target_agent="Claude MM1 Agent",
                next_task_id="TO_BE_CREATED",
                inbox_path=cursor_inbox_path,
                project_name="VIBES-Volume-Reorganization",
                detailed_instructions=(
                    "Create validation task to review reorganization work, verify file integrity, "
                    "confirm deduplication success, and validate final directory structure. "
                    "Include link to issue and all execution tasks."
                )
            )
        except ImportError:
            enhanced_description = task_description + f"""

## 🚨 MANDATORY HANDOFF REQUIREMENT

**CRITICAL:** Upon completion of this task, you MUST create a handoff trigger file for **Validate: VIBES Volume Reorganization** assigned to **Claude MM1 Agent**.

**Handoff File Location:** `{cursor_inbox_path}`

**Required Content:**
- Complete execution report
- Phase completion verification
- File integrity validation results
- Link to issue ({issue_url})
- All context needed for validation to begin

**NO EXCEPTIONS. TASK IS NOT COMPLETE UNTIL HANDOFF FILE IS CREATED.**
"""
        
        task_details = {
            "task_id": task_id,
            "task_title": "Execute: VIBES Volume Reorganization - Phase 1-6",
            "task_url": task_url,
            "project_id": None,
            "project_title": None,
            "description": enhanced_description,
            "status": default_status or "Ready",
            "agent_name": "Cursor MM1 Agent",
            "agent_id": CURSOR_MM1_AGENT_ID,
            "priority": "High",
            "handoff_instructions": (
                "Execute the VIBES Volume Reorganization according to the implementation plan. "
                "Start by resolving volume access permissions, then proceed through all 6 phases. "
                "Upon completion, you MUST:\n"
                "1. **MOVE TRIGGER FILE (MANUAL)**: Call mark_trigger_file_processed() to move the trigger file from 01_inbox to 02_processed.\n"
                "2. Update the task status in Notion\n"
                "3. Create a handoff trigger file for validation task (see task description for details)\n"
                "4. Document all deliverables and artifacts\n"
                "5. Update issue status to 'Resolved' if all phases complete\n"
                "6. Provide all context needed for validation to begin\n\n"
                "**MANDATORY:** Task is NOT complete until trigger file is manually moved and handoff file is created."
            )
        }
        
        trigger_file = create_trigger_file("MM1", "Cursor MM1 Agent", task_details)
        if trigger_file:
            print(f"✅ Created trigger file: {trigger_file}")
        else:
            print(f"⚠️  Failed to create trigger file")
        
    except Exception as e:
        print(f"❌ Failed to create Agent-Task: {e}")
        import traceback
        traceback.print_exc()
        return
    
    print("\n" + "=" * 80)
    print("Handoff Creation Complete")
    print("=" * 80)
    print(f"✅ Created implementation task")
    print(f"✅ Created trigger file for Cursor MM1 Agent")
    print(f"✅ Documented blocking point and next steps")

if __name__ == "__main__":
    main()

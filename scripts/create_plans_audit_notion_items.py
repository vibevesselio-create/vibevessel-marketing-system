#!/usr/bin/env python3
"""
Create Notion Items for Plans Directory Audit Session

Creates Issues, Tasks, and Project items in Notion for the
Plans Directory Audit completed on 2026-01-08.

ENVIRONMENT MANAGEMENT: Uses shared_core.notion.token_manager (MANDATORY)
"""

import sys
from pathlib import Path
from datetime import datetime, timezone

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

try:
    from notion_client import Client
except ImportError:
    print("ERROR: notion-client not installed. Run: pip install notion-client", file=sys.stderr)
    sys.exit(1)

# MANDATORY: Use centralized token manager
from shared_core.notion.token_manager import get_notion_token

# Database IDs
ISSUES_QUESTIONS_DB_ID = "229e73616c27808ebf06c202b10b5166"
AGENT_TASKS_DB_ID = "284e7361-6c27-8018-872a-eb14e82e0392"


def create_audit_issue(client: Client) -> str:
    """Create Issues+Questions entry for audit scripts requiring testing."""

    title = "[AUDIT] Dropbox Music Cleanup Scripts Created - Require Testing"
    description = """**Audit Session:** Plans Directory Audit 2026-01-08

**Summary:**
Claude Code Agent (Opus 4.5) executed a comprehensive Plans Directory Audit and created 3 new Dropbox Music cleanup scripts. These scripts need to be tested before production use.

**Scripts Created:**
1. `scripts/create_dropbox_music_structure.py` - Directory structure creation
2. `scripts/dropbox_music_deduplication.py` - File deduplication (MD5 hash)
3. `scripts/dropbox_music_migration.py` - File migration to new structure

**Safety Features Implemented:**
- Default `--dry-run` mode (no changes without explicit flags)
- `--execute --confirm` required for actual changes
- NEVER permanently deletes files (archive/move only)
- Atomic dry-run + execute workflow
- Full audit trail logging
- Checksum verification for file moves

**Testing Required:**
1. Run each script with `--dry-run` to verify output
2. Verify safety mechanisms work correctly
3. Test on small subset before full execution
4. Document any issues found

**Related Files:**
- `/scripts/create_dropbox_music_structure.py`
- `/scripts/dropbox_music_deduplication.py`
- `/scripts/dropbox_music_migration.py`
- `/reports/PLANS_AUDIT_SESSION_REPORT_20260108.md`
- `/reports/PLANS_AUDIT_REPORT_20260108_v2.md`

**Evidence:**
- Session Report: `reports/PLANS_AUDIT_SESSION_REPORT_20260108.md`
- Audit Agent: Claude Opus 4.5 (Claude Code)
- Audit Date: 2026-01-08
"""

    try:
        properties = {
            "Name": {"title": [{"text": {"content": title}}]},
            "Description": {"rich_text": [{"text": {"content": description[:2000]}}]},  # Notion limit
            "Type": {"multi_select": [{"name": "Internal Issue"}]},
            "Status": {"status": {"name": "Unreported"}},
            "Priority": {"select": {"name": "High"}},
        }

        response = client.pages.create(
            parent={"database_id": ISSUES_QUESTIONS_DB_ID},
            properties=properties
        )

        issue_id = response.get("id")
        print(f"Created Issues+Questions entry: {issue_id}")
        print(f"   Title: {title}")
        print(f"   URL: https://www.notion.so/{issue_id.replace('-', '')}")
        return issue_id

    except Exception as e:
        print(f"Failed to create Issues+Questions entry: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return None


def create_design_review_issue(client: Client) -> str:
    """Create Issues+Questions entry for modular design review."""

    title = "[AUDIT] Modularized Implementation Design Created - Require Review"
    description = """**Audit Session:** Plans Directory Audit 2026-01-08

**Summary:**
Claude Code Agent (Opus 4.5) created the missing MODULARIZED_IMPLEMENTATION_DESIGN.md document during the Plans Directory Audit. This architecture design document needs review before implementation begins.

**Document Created:**
- `MODULARIZED_IMPLEMENTATION_DESIGN.md` (~12KB)

**Contents:**
- Module structure diagram for music_workflow package
- Interface contracts (TrackInfo dataclass)
- Error class hierarchy
- Migration strategy (6 phases)
- Testing strategy
- Configuration management
- Dependencies list
- Success metrics

**Target Architecture:**
```
music_workflow/
├── config/
├── core/ (downloader, processor, organizer)
├── integrations/ (notion, eagle, spotify, soundcloud)
├── deduplication/ (fingerprint, matcher)
├── metadata/ (extraction, enrichment, embedding)
├── cli/
├── utils/
└── tests/
```

**Review Required:**
1. Review module structure for completeness
2. Verify interface contracts are appropriate
3. Validate migration strategy phases
4. Confirm testing approach
5. Approve before Phase 1 implementation

**Evidence:**
- Design Document: `MODULARIZED_IMPLEMENTATION_DESIGN.md`
- Audit Agent: Claude Opus 4.5 (Claude Code)
- Audit Date: 2026-01-08
"""

    try:
        properties = {
            "Name": {"title": [{"text": {"content": title}}]},
            "Description": {"rich_text": [{"text": {"content": description[:2000]}}]},
            "Type": {"multi_select": [{"name": "Internal Issue"}]},
            "Status": {"status": {"name": "Unreported"}},
            "Priority": {"select": {"name": "Medium"}},
        }

        response = client.pages.create(
            parent={"database_id": ISSUES_QUESTIONS_DB_ID},
            properties=properties
        )

        issue_id = response.get("id")
        print(f"Created Issues+Questions entry: {issue_id}")
        print(f"   Title: {title}")
        print(f"   URL: https://www.notion.so/{issue_id.replace('-', '')}")
        return issue_id

    except Exception as e:
        print(f"Failed to create Issues+Questions entry: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return None


def create_test_task(client: Client, script_name: str, priority: str = "High") -> str:
    """Create Agent-Tasks entry for testing a script."""

    title = f"Test Dropbox Music {script_name.replace('_', ' ').title()} Script"
    description = f"""**Task:** Test `scripts/dropbox_music_{script_name}.py`

**Instructions:**
1. Ensure SYSTEM_SSD volume is mounted at `/Volumes/SYSTEM_SSD/Dropbox/Music/`
2. Run script with dry-run mode:
   ```bash
   python3 /Users/brianhellemn/Projects/github-production/scripts/dropbox_music_{script_name}.py
   ```
3. Review dry-run output for accuracy
4. Verify safety mechanisms work correctly
5. Document test results

**DO NOT:**
- Run with `--execute --confirm` without explicit user approval
- Make any actual file changes during testing

**Expected Output:**
- Dry-run report showing what would happen
- No actual file modifications

**Created By:** Plans Directory Audit (Claude Code Agent)
**Date:** 2026-01-08
"""

    try:
        properties = {
            "Task Name": {"title": [{"text": {"content": title}}]},
            "Description": {"rich_text": [{"text": {"content": description}}]},
            "Status": {"status": {"name": "Ready"}},
            "Priority": {"select": {"name": priority}},
        }

        response = client.pages.create(
            parent={"database_id": AGENT_TASKS_DB_ID},
            properties=properties
        )

        task_id = response.get("id")
        print(f"Created Agent-Tasks entry: {task_id}")
        print(f"   Title: {title}")
        print(f"   URL: https://www.notion.so/{task_id.replace('-', '')}")
        return task_id

    except Exception as e:
        print(f"Failed to create Agent-Tasks entry: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return None


def create_review_design_task(client: Client) -> str:
    """Create Agent-Tasks entry for reviewing modular design."""

    title = "Review Modularized Implementation Design Document"
    description = """**Task:** Review `MODULARIZED_IMPLEMENTATION_DESIGN.md`

**Instructions:**
1. Read the design document thoroughly
2. Review module structure for completeness
3. Validate interface contracts (TrackInfo dataclass)
4. Verify error class hierarchy is appropriate
5. Confirm migration strategy phases are realistic
6. Review testing strategy
7. Provide feedback or approval

**Key Sections to Review:**
- Module Structure (music_workflow package)
- Interface Contracts
- Migration Strategy (6 phases)
- Testing Strategy
- Configuration Management
- Dependencies

**Deliverables:**
- Design review feedback
- Approval or requested changes
- Next steps recommendation

**Created By:** Plans Directory Audit (Claude Code Agent)
**Date:** 2026-01-08
"""

    try:
        properties = {
            "Task Name": {"title": [{"text": {"content": title}}]},
            "Description": {"rich_text": [{"text": {"content": description}}]},
            "Status": {"status": {"name": "Ready"}},
            "Priority": {"select": {"name": "Medium"}},
        }

        response = client.pages.create(
            parent={"database_id": AGENT_TASKS_DB_ID},
            properties=properties
        )

        task_id = response.get("id")
        print(f"Created Agent-Tasks entry: {task_id}")
        print(f"   Title: {title}")
        print(f"   URL: https://www.notion.so/{task_id.replace('-', '')}")
        return task_id

    except Exception as e:
        print(f"Failed to create Agent-Tasks entry: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return None


def create_migrate_plans_task(client: Client) -> str:
    """Create Agent-Tasks entry for migrating plan files."""

    title = "Migrate Plan Files to /plans/ Directory"
    description = """**Task:** Move plan/strategy documents to the new `/plans/` directory

**Background:**
The Plans Directory Audit created a new `/plans/` directory for organizing plan files.
Currently, plan files are scattered in the root directory.

**Files to Move:**
1. `MUSIC_WORKFLOW_IMPLEMENTATION_STATUS.md`
2. `MUSIC_WORKFLOW_IMPLEMENTATION_HANDOFF_INSTRUCTIONS.md`
3. `MUSIC_WORKFLOW_BIFURCATION_STRATEGY.md`
4. `MONOLITHIC_MAINTENANCE_PLAN.md`
5. `DROPBOX_MUSIC_CLEANUP_AND_REORGANIZATION_STRATEGY.md`
6. `DROPBOX_MUSIC_MIGRATION_GUIDE.md`
7. `CODE_REVIEW_FINDINGS.md`

**Instructions:**
1. Review each file to confirm it should be moved
2. Move files to `/plans/` directory
3. Update any documentation references
4. Verify no broken links

**Destination:** `/Users/brianhellemn/Projects/github-production/plans/`

**Created By:** Plans Directory Audit (Claude Code Agent)
**Date:** 2026-01-08
"""

    try:
        properties = {
            "Task Name": {"title": [{"text": {"content": title}}]},
            "Description": {"rich_text": [{"text": {"content": description}}]},
            "Status": {"status": {"name": "Ready"}},
            "Priority": {"select": {"name": "Low"}},
        }

        response = client.pages.create(
            parent={"database_id": AGENT_TASKS_DB_ID},
            properties=properties
        )

        task_id = response.get("id")
        print(f"Created Agent-Tasks entry: {task_id}")
        print(f"   Title: {title}")
        print(f"   URL: https://www.notion.so/{task_id.replace('-', '')}")
        return task_id

    except Exception as e:
        print(f"Failed to create Agent-Tasks entry: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return None


def main():
    """Main execution"""
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--tasks-only", action="store_true", help="Only create tasks (skip issues)")
    args = parser.parse_args()

    print("=" * 80)
    print("Creating Notion Items for Plans Directory Audit Session")
    print("=" * 80)
    print()

    token = get_notion_token()
    if not token:
        print("ERROR: NOTION_TOKEN not set", file=sys.stderr)
        return 1

    client = Client(auth=token)

    created_items = []

    # Create Issues (unless --tasks-only)
    if not args.tasks_only:
        print("\n--- Creating Issues+Questions Entries ---\n")

        issue1 = create_audit_issue(client)
        if issue1:
            created_items.append(("Issue", "Scripts Testing", issue1))

        issue2 = create_design_review_issue(client)
        if issue2:
            created_items.append(("Issue", "Design Review", issue2))

    # Create Tasks
    print("\n--- Creating Agent-Tasks Entries ---\n")

    for script in ["structure", "deduplication", "migration"]:
        task = create_test_task(client, script)
        if task:
            created_items.append(("Task", f"Test {script}", task))

    design_task = create_review_design_task(client)
    if design_task:
        created_items.append(("Task", "Review Design", design_task))

    migrate_task = create_migrate_plans_task(client)
    if migrate_task:
        created_items.append(("Task", "Migrate Plans", migrate_task))

    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY: Notion Items Created")
    print("=" * 80)

    for item_type, name, item_id in created_items:
        url = f"https://www.notion.so/{item_id.replace('-', '')}"
        print(f"  [{item_type}] {name}: {url}")

    print(f"\nTotal items created: {len(created_items)}")
    print("=" * 80)

    return 0 if len(created_items) > 0 else 1


if __name__ == "__main__":
    sys.exit(main())

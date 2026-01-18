#!/usr/bin/env python3
"""
Create Database Refinement Implementation Project
=================================================

Creates a complete project structure in Notion for implementing database refinement
strategies to remove blockers, consolidate items, and enhance non-compliant items.

This script creates:
1. Project in Agent-Projects database
2. Tasks for implementation phases
3. Handoff trigger file for Claude Code Agent
"""

import os
import sys
import json
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
from dotenv import load_dotenv

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

load_dotenv()

try:
    from notion_client import Client
    NOTION_AVAILABLE = True
except ImportError:
    NOTION_AVAILABLE = False
    Client = None

# Import task creation helpers
try:
    from shared_core.notion.task_creation import (
        add_mandatory_next_handoff_instructions,
        create_task_description_with_next_handoff
    )
    TASK_CREATION_HELPERS_AVAILABLE = True
except ImportError:
    TASK_CREATION_HELPERS_AVAILABLE = False

# Import folder_resolver for dynamic path resolution
try:
    from shared_core.notion.folder_resolver import get_agent_inbox_path
    FOLDER_RESOLVER_AVAILABLE = True
except ImportError:
    FOLDER_RESOLVER_AVAILABLE = False
    get_agent_inbox_path = None

# Database IDs
PROJECTS_DB_ID = "286e7361-6c27-81ff-a450-db2ecad4b0ba"  # Agent-Projects
AGENT_TASKS_DB_ID = "284e73616c278018872aeb14e82e0392"  # Agent-Tasks

# Agent IDs
CLAUDE_CODE_AGENT_ID = "2b1e7361-6c27-80fb-8ce9-fd3cf78a5cad"  # Claude Code Agent
CURSOR_MM1_AGENT_ID = "249e7361-6c27-8100-8a74-de7eabb9fc8d"  # Cursor MM1 Agent
CLAUDE_MM1_AGENT_ID = "fa54f05c-e184-403a-ac28-87dd8ce9855b"  # Claude MM1 Agent

def get_notion_token() -> Optional[str]:
    """Get Notion API token from shared_core token manager"""
    # Use centralized token manager (MANDATORY per CLAUDE.md)
    try:
        from shared_core.notion.token_manager import get_notion_token as _get_notion_token
        token = _get_notion_token()
        if token:
            return token
    except ImportError:
        pass

    # Fallback for backwards compatibility
    return os.getenv("NOTION_TOKEN") or os.getenv("NOTION_API_TOKEN") or os.getenv("VV_AUTOMATIONS_WS_TOKEN")


def create_project(client: Client) -> Optional[str]:
    """Create Database Refinement Implementation Project."""
    try:
        project_properties = {
            "Project Name": {
                "title": [{"text": {"content": "Database Refinement Implementation - Remove Blockers & Enhance Compliance"}}]
            },
            "Summary": {
                "rich_text": [{
                    "text": {
                        "content": "Implement comprehensive database refinement strategies to remove blockers, consolidate duplicate items, and enhance non-compliant database entries. Based on DATABASE_REFINEMENT_STRATEGY.md recommendations."
                    }
                }]
            },
            "Status": {
                "status": {"name": "In Progress"}
            },
            "Priority": {
                "select": {"name": "High"}
            },
            "Owner": {
                "relation": [{"id": CURSOR_MM1_AGENT_ID}]
            }
        }
        
        page = client.pages.create(
            parent={"database_id": PROJECTS_DB_ID},
            properties=project_properties
        )
        
        project_id = page.get("id")
        print(f"✅ Created Project: Database Refinement Implementation")
        print(f"   ID: {project_id}")
        print(f"   URL: {page.get('url', 'N/A')}")
        return project_id
        
    except Exception as e:
        print(f"❌ Error creating project: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return None


def create_task(
    client: Client,
    project_id: str,
    task_name: str,
    description: str,
    assigned_agent_id: str,
    priority: str = "High",
    dependency_status: str = "Ready",
    prerequisite_task_ids: Optional[List[str]] = None,
    next_task_name: Optional[str] = None,
    next_target_agent: Optional[str] = None,
    next_task_id: Optional[str] = None
) -> Optional[str]:
    """Create a Task in Agent-Tasks database."""
    try:
        # Add mandatory next handoff instructions if provided
        if TASK_CREATION_HELPERS_AVAILABLE and next_task_name and next_target_agent:
            description = add_mandatory_next_handoff_instructions(
                description=description,
                next_task_name=next_task_name,
                target_agent=next_target_agent,
                next_task_id=next_task_id or "TO_BE_CREATED",
                project_name="Database Refinement Implementation",
                inbox_path=str(get_agent_inbox_path(next_target_agent)) + "/" if FOLDER_RESOLVER_AVAILABLE else f"/Users/brianhellemn/Documents/Agents/Agent-Triggers/{next_target_agent.replace(' ', '-')}/01_inbox/"
            )
        elif next_task_name and next_target_agent:
            description += f"\n\n## 🚨 MANDATORY HANDOFF REQUIREMENT\n\nUpon completion, you MUST create a handoff trigger file for {next_task_name} assigned to {next_target_agent}."
        
        properties = {
            "Task Name": {
                "title": [{"text": {"content": task_name}}]
            },
            "Description": {
                "rich_text": [{"text": {"content": description[:1995]}}]  # Leave room for safety
            },
            "Priority": {
                "select": {"name": priority}
            },
            "Status": {
                "status": {"name": "Ready"}
            },
            "Dependency Status": {
                "select": {"name": dependency_status}
            },
            "Task Type": {
                "select": {"name": "Implementation"}
            },
            "Assigned-Agent": {
                "relation": [{"id": assigned_agent_id}]
            },
            "Projects": {
                "relation": [{"id": project_id}]
            }
        }
        
        # Add prerequisite tasks if provided
        if prerequisite_task_ids:
            try:
                properties["Prerequisite Tasks"] = {
                    "relation": [{"id": tid} for tid in prerequisite_task_ids]
                }
            except:
                pass
        
        page = client.pages.create(
            parent={"database_id": AGENT_TASKS_DB_ID},
            properties=properties
        )
        
        task_id = page.get("id")
        print(f"✅ Created Task: {task_name}")
        print(f"   ID: {task_id}")
        print(f"   URL: {page.get('url', 'N/A')}")
        return task_id
        
    except Exception as e:
        print(f"❌ Error creating task '{task_name}': {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return None


def create_handoff_trigger_file(
    agent_name: str,
    task_id: str,
    task_title: str,
    task_url: str,
    project_id: str,
    project_url: str,
    description: str
) -> Optional[Path]:
    """Create handoff trigger file for Claude Code Agent."""
    try:
        from main import normalize_agent_folder_name, MM1_AGENT_TRIGGER_BASE
        
        # Normalize agent folder name
        agent_folder = normalize_agent_folder_name(agent_name)
        trigger_folder = MM1_AGENT_TRIGGER_BASE / agent_folder / "01_inbox"
        trigger_folder.mkdir(parents=True, exist_ok=True)
        
        # Create timestamp
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        
        # Create filename
        safe_title = task_title.replace(" ", "-").replace(":", "").replace("/", "-")[:50]
        filename = f"{timestamp}__HANDOFF__{safe_title}__{task_id[:8]}.json"
        
        # Create trigger file data
        trigger_data = {
            "task_id": task_id,
            "task_title": task_title,
            "task_url": task_url,
            "project_id": project_id,
            "project_url": project_url,
            "description": description,
            "status": "Ready",
            "agent_name": agent_name,
            "agent_type": "MM1",
            "priority": "High",
            "created_at": timestamp,
            "handoff_instructions": description
        }
        
        # Write trigger file
        trigger_file_path = trigger_folder / filename
        with open(trigger_file_path, 'w', encoding='utf-8') as f:
            json.dump(trigger_data, f, indent=2, ensure_ascii=False)
        
        print(f"✅ Created trigger file: {trigger_file_path}")
        return trigger_file_path
        
    except Exception as e:
        print(f"❌ Error creating trigger file: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return None


def main():
    """Create complete Database Refinement project structure."""
    if not NOTION_AVAILABLE:
        print("❌ notion-client not available. Install with: pip install notion-client")
        sys.exit(1)
    
    token = get_notion_token()
    if not token:
        print("❌ NOTION_TOKEN not found in environment or unified_config")
        sys.exit(1)
    
    client = Client(auth=token)
    
    print("🚀 Creating Database Refinement Implementation Project...\n")
    print("="*80)
    
    # Step 1: Create Project
    project_id = create_project(client)
    if not project_id:
        print("❌ Failed to create project. Exiting.")
        sys.exit(1)
    
    project_url = f"https://www.notion.so/{project_id.replace('-', '')}"
    
    print("\n" + "="*80)
    print("Creating Implementation Tasks")
    print("="*80 + "\n")
    
    # Task 1: Phase 1 - Blocker Detection Implementation
    task1_description = """## Context
Database refinement strategy documented in DATABASE_REFINEMENT_STRATEGY.md. Implementation needed to remove blockers, consolidate duplicates, and enhance non-compliant items.

## Objective
Implement automated blocker identification system detecting stale tasks, broken dependencies, orphaned relations, and missing required properties.

## Implementation Requirements
1. Create `scripts/identify_blockers.py` script
2. Scan Agent-Tasks database for:
   - Tasks with Status = "Blocked" or "In Progress" > 30 days
   - Tasks with missing required dependencies
   - Tasks with "Blocking Reason" property populated
   - Items with broken relations (orphaned references)
   - Tasks with validation errors
   - Items with required properties missing
3. Generate blocker report with prioritization
4. Integrate with continuous handoff processor to skip blocked items
5. Create blocker resolution tasks for manual review

## Deliverables
- `scripts/identify_blockers.py` script
- Blocker identification logic
- Integration with continuous handoff processor
- Blocker report generation
- Documentation

## Success Criteria
- [ ] Blocker identification script created and tested
- [ ] Can detect all blocker types listed above
- [ ] Generates comprehensive blocker reports
- [ ] Integration with continuous handoff processor working
- [ ] Documentation complete

## Reference
- Strategy: DATABASE_REFINEMENT_STRATEGY.md
- Existing: consolidate_and_cleanup_remaining_tasks.py, refactor_notion_tasks_and_cleanup_triggers.py
"""
    
    task1_id = create_task(
        client=client,
        project_id=project_id,
        task_name="Phase 1: Blocker Detection Implementation",
        description=task1_description,
        assigned_agent_id=CLAUDE_CODE_AGENT_ID,
        priority="High",
        dependency_status="Ready",
        next_task_name="Phase 2: Compliance Auto-Enhancement Implementation",
        next_target_agent="Claude Code Agent",
        next_task_id="TO_BE_CREATED"
    )
    
    # Task 2: Phase 2 - Compliance Auto-Enhancement
    task2_description = """## Context
Compliance baseline shows 29 non-compliant items (46% of 63 total). Automated compliance enhancement needed.

## Objective
Implement automated compliance enhancement fixing missing Policy Compliance Checklists, populating missing invariant references, fixing schema violations, and filling missing required properties.

## Implementation Requirements
1. Create `scripts/enhance_non_compliant_items.py` script
2. Based on `docs_compliance_baseline.json` patterns
3. Auto-add missing Policy Compliance Checklists
4. Populate missing invariant references
5. Fix schema violations automatically
6. Fill missing required properties from defaults
7. Validate and repair property schemas

## Deliverables
- `scripts/enhance_non_compliant_items.py` script
- Compliance auto-fix capabilities
- Schema validation integration
- Property population logic
- Compliance enhancement reports

## Success Criteria
- [ ] Compliance enhancement script created
- [ ] Can auto-fix missing Policy Compliance Checklists
- [ ] Can populate missing invariant references
- [ ] Can fix schema violations
- [ ] Can populate missing required properties
- [ ] Reduces non-compliant items from 29 to < 5

## Reference
- Compliance Baseline: docs_compliance_baseline.json
- Strategy: DATABASE_REFINEMENT_STRATEGY.md
"""
    
    task2_id = create_task(
        client=client,
        project_id=project_id,
        task_name="Phase 2: Compliance Auto-Enhancement Implementation",
        description=task2_description,
        assigned_agent_id=CLAUDE_CODE_AGENT_ID,
        priority="High",
        dependency_status="Dependencies Met" if task1_id else "Ready",
        prerequisite_task_ids=[task1_id] if task1_id else None,
        next_task_name="Phase 3: Duplicate Detection & Consolidation",
        next_target_agent="Claude Code Agent",
        next_task_id="TO_BE_CREATED"
    )
    
    # Task 3: Phase 3 - Duplicate Detection & Consolidation
    task3_description = """## Context
Duplicate and related items need consolidation to improve database organization and workflow efficiency.

## Objective
Implement intelligent duplicate detection and consolidation system merging duplicates, grouping related items, and archiving redundant entries.

## Implementation Requirements
1. Create `scripts/detect_and_consolidate_duplicates.py` script
2. Implement duplicate detection using:
   - Title similarity (fuzzy matching)
   - Content similarity
   - Relation overlap
   - Property matching
   - Temporal proximity
3. Create consolidation rules:
   - Keep most recent item
   - Merge properties (prefer non-empty values)
   - Combine relations
   - Archive older duplicates
4. Group related items by project, agent, type, or temporal patterns

## Deliverables
- `scripts/detect_and_consolidate_duplicates.py` script
- `scripts/group_related_items.py` script
- Duplicate detection algorithms
- Consolidation automation
- Consolidation reports

## Success Criteria
- [ ] Duplicate detection script created
- [ ] Can identify duplicates using all methods listed
- [ ] Consolidation rules work correctly
- [ ] Related items can be grouped
- [ ] Reduces duplicate items to < 5%

## Reference
- Strategy: DATABASE_REFINEMENT_STRATEGY.md
- Existing: consolidate_and_cleanup_remaining_tasks.py, issues_cleanup.py
"""
    
    task3_id = create_task(
        client=client,
        project_id=project_id,
        task_name="Phase 3: Duplicate Detection & Consolidation",
        description=task3_description,
        assigned_agent_id=CLAUDE_CODE_AGENT_ID,
        priority="Medium",
        dependency_status="Dependencies Met" if task2_id else "Ready",
        prerequisite_task_ids=[task2_id] if task2_id else None,
        next_task_name="Phase 4: Integration & Pipeline",
        next_target_agent="Claude Code Agent",
        next_task_id="TO_BE_CREATED"
    )
    
    # Task 4: Phase 4 - Integration & Pipeline
    task4_description = """## Context
All refinement components need integration into a unified pipeline runnable automatically or on-demand.

## Objective
Create automated refinement pipeline orchestrating blocker detection, compliance enhancement, and consolidation in a single workflow.

## Implementation Requirements
1. Create `scripts/database_refinement_pipeline.py` script
2. Implement workflow:
   - Scan databases for blockers → Generate blocker report
   - Identify duplicate items → Generate consolidation plan
   - Validate compliance → Generate enhancement plan
   - Execute safe auto-fixes (user-approved)
   - Generate manual review tasks for complex cases
   - Update compliance baseline
   - Report refinement results
3. Integrate with existing systems:
   - Continuous handoff processor
   - Task creation scripts
   - Compliance monitoring
   - Schema validation

## Deliverables
- `scripts/database_refinement_pipeline.py` script
- Unified refinement workflow
- Integration with existing systems
- Automated reporting
- Manual review task creation

## Success Criteria
- [ ] Refinement pipeline created
- [ ] Can orchestrate all refinement steps
- [ ] Generates comprehensive reports
- [ ] Integrates with existing systems
- [ ] Can run automatically or on-demand

## Reference
- Strategy: DATABASE_REFINEMENT_STRATEGY.md
- All previous phase implementations
"""
    
    task4_id = create_task(
        client=client,
        project_id=project_id,
        task_name="Phase 4: Integration & Pipeline",
        description=task4_description,
        assigned_agent_id=CLAUDE_CODE_AGENT_ID,
        priority="High",
        dependency_status="Dependencies Met" if task3_id else "Ready",
        prerequisite_task_ids=[task3_id] if task3_id else None
    )
    
    print("\n" + "="*80)
    print("Creating Handoff Trigger File")
    print("="*80 + "\n")
    
    # Create handoff trigger file for Claude Code Agent (first task)
    if task1_id:
        try:
            task1_page = client.pages.retrieve(page_id=task1_id)
            task1_url = task1_page.get("url", "")
            
            trigger_file = create_handoff_trigger_file(
                agent_name="Claude Code Agent",
                task_id=task1_id,
                task_title="Phase 1: Blocker Detection Implementation",
                task_url=task1_url,
                project_id=project_id,
                project_url=project_url,
                description=task1_description
            )
            
            if trigger_file:
                print(f"✅ Handoff trigger file created successfully")
            else:
                print(f"⚠️  Warning: Could not create trigger file, but project and tasks created")
        except Exception as e:
            print(f"⚠️  Warning: Could not create trigger file: {e}")
            print(f"   Project and tasks created successfully")
    
    print("\n" + "="*80)
    print("Project Structure Created Successfully!")
    print("="*80)
    print(f"\nProject ID: {project_id}")
    print(f"Project URL: {project_url}")
    print(f"\nTasks Created:")
    if task1_id:
        print(f"  1. Phase 1: Blocker Detection Implementation (Claude Code Agent)")
    if task2_id:
        print(f"  2. Phase 2: Compliance Auto-Enhancement Implementation (Claude Code Agent)")
    if task3_id:
        print(f"  3. Phase 3: Duplicate Detection & Consolidation (Claude Code Agent)")
    if task4_id:
        print(f"  4. Phase 4: Integration & Pipeline (Claude Code Agent)")
    print(f"\n✅ All tasks linked to project")
    print(f"✅ Dependencies configured")
    print(f"✅ Handoff trigger file created for Claude Code Agent")


if __name__ == "__main__":
    main()


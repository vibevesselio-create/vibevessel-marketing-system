#!/usr/bin/env python3
"""
Create Notion AI Research Agent Handoff
=========================================

Creates a handoff trigger file for Notion AI Research Agent to review and analyze
Notion documentation for task handoff instruction logic updates, identifying gaps,
conflicts, and integration points.
"""

import os
import sys
import json
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime, timezone
from dotenv import load_dotenv

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

load_dotenv()

# MANDATORY: Import task creation helpers
try:
    from shared_core.notion.task_creation import create_handoff_json_data
    TASK_CREATION_HELPERS_AVAILABLE = True
except ImportError:
    TASK_CREATION_HELPERS_AVAILABLE = False
    print("⚠️  WARNING: Task creation helpers not available!", file=sys.stderr)

# Notion AI Research Agent trigger path - use unified normalization
from main import normalize_agent_folder_name, MM2_AGENT_TRIGGER_BASE

agent_folder = normalize_agent_folder_name("Notion AI Research Agent")
NOTION_AI_RESEARCH_INBOX = MM2_AGENT_TRIGGER_BASE / f"{agent_folder}-gd" / "01_inbox"

# Related items (will be populated from script execution or manual entry)
UNIFIED_ENV_PROJECT_ID = "2dae7361-6c27-8105-9aa3-d89689127c7d"
RELATED_ISSUE_ID = "TO_BE_DETERMINED"  # Will be created by create_handoff_review_tasks.py


def create_notion_ai_research_handoff(
    issue_id: Optional[str] = None,
    project_id: Optional[str] = None
) -> Path:
    """Create handoff trigger file for Notion AI Research Agent."""
    
    # Use provided IDs or defaults
    issue_url = f"https://www.notion.so/{issue_id.replace('-', '')}" if issue_id else "TO_BE_DETERMINED"
    project_url = f"https://www.notion.so/{project_id.replace('-', '')}" if project_id else f"https://www.notion.so/{UNIFIED_ENV_PROJECT_ID.replace('-', '')}"
    
    # Create handoff data with mandatory next handoff
    handoff_data = create_handoff_json_data(
        source_agent="Cursor MM1 Agent",
        target_agent="Notion AI Research Agent",
        task_url=issue_url,
        project_url=project_url,
        related_issue_url=issue_url if issue_id else None,
        handoff_reason="Review and analyze Notion documentation for task handoff instruction logic updates, identify gaps, conflicts, and integration points",
        context={
            "current_step": "Task handoff instruction logic has been updated with system enforcement. Notion documentation review required.",
            "work_completed": [
            "Created mandatory helper module: shared_core/notion/task_creation.py",
            "Updated documentation: AGENT_HANDOFF_TASK_GENERATOR_V3.0.md",
            "Updated task creation scripts to use helpers",
            "Created comprehensive documentation (MANDATORY_NEXT_HANDOFF_REQUIREMENT.md, SYSTEM_ENFORCEMENT_NEXT_HANDOFF.md, CRITICAL_SYSTEM_REQUIREMENTS.md)",
            "Created Issues+Questions entry and Agent-Tasks for agent review"
            ],
            "blocking_issue": None,
            "project_goals": "Ensure all Notion documentation reflects mandatory next handoff requirement and identify all integration points"
        },
        required_action=f"""**Review and Analyze Notion Documentation for Task Handoff Instruction Logic Updates**

**PRIMARY OBJECTIVE:**
Review all Notion documentation, agent profiles, workflows, and related context to identify gaps, conflicts, and integration points for the mandatory next handoff requirement.

**REVIEW REQUIREMENTS:**

1. **Documentation Review:**
   - Review Universal Four-Agent Coordination Workflow documentation in Notion
   - Review all agent profile pages in Notion
   - Review all workflow documentation pages
   - Review any task templates or guides in Notion
   - Identify where next handoff requirement is missing
   - Identify conflicting documentation that contradicts the requirement

2. **Gap Analysis:**
   - Identify all Notion pages that reference task creation but don't mention next handoff
   - Identify all agent profiles that don't include next handoff in their capabilities
   - Identify all workflow documentation that doesn't include next handoff steps
   - Identify all templates that don't include next handoff sections
   - Document all gaps with specific page URLs and locations

3. **Conflict Analysis:**
   - Identify documentation that contradicts the mandatory next handoff requirement
   - Identify workflows that don't account for next handoff creation
   - Identify agent instructions that conflict with the requirement
   - Document all conflicts with specific examples

4. **Integration Points:**
   - Identify all Notion pages that need to be updated
   - Identify all agent profiles that need updates
   - Identify all workflow documentation that needs updates
   - Identify all templates that need updates
   - Create prioritized list of integration points

5. **Documentation Updates Required:**
   - Update Universal Four-Agent Coordination Workflow to include next handoff requirement
   - Update all agent profile pages to reflect next handoff capability
   - Update all workflow documentation to include next handoff steps
   - Update all task templates to include next handoff sections
   - Create or update Notion documentation index

**ANALYSIS DELIVERABLES:**

1. **Gap Analysis Report:**
   - List of all Notion pages missing next handoff requirement
   - Specific locations within pages where requirement should be added
   - Priority ranking for updates

2. **Conflict Analysis Report:**
   - List of all conflicting documentation
   - Specific examples of conflicts
   - Recommendations for resolution

3. **Integration Plan:**
   - Prioritized list of Notion pages to update
   - Specific updates needed for each page
   - Dependencies between updates
   - Timeline recommendations

4. **Updated Documentation:**
   - Updated Universal Four-Agent Coordination Workflow
   - Updated agent profile pages
   - Updated workflow documentation
   - Updated task templates

**FILES TO REVIEW (Local):**
- `/Users/brianhellemn/Projects/github-production/shared_core/notion/task_creation.py`
- `/Users/brianhellemn/Projects/github-production/docs/agents/AGENT_HANDOFF_TASK_GENERATOR_V3.0.md`
- `/Users/brianhellemn/Projects/github-production/docs/MANDATORY_NEXT_HANDOFF_REQUIREMENT.md`
- `/Users/brianhellemn/Projects/github-production/docs/SYSTEM_ENFORCEMENT_NEXT_HANDOFF.md`
- `/Users/brianhellemn/Projects/github-production/docs/CRITICAL_SYSTEM_REQUIREMENTS.md`

**NOTION PAGES TO REVIEW:**
- Universal Four-Agent Coordination Workflow page
- All agent profile pages in Agents database
- All workflow documentation pages
- All task templates in Notion
- All related documentation pages

**MANDATORY HANDOFF REQUIREMENT:** Upon completion, create handoff trigger file for next agent (if applicable) or document completion in Notion.""",
        success_criteria=[
            "All Notion documentation reviewed for gaps and conflicts",
            "Gap analysis report created with specific page URLs and locations",
            "Conflict analysis report created with specific examples",
            "Integration plan created with prioritized list of updates",
            "Universal Four-Agent Coordination Workflow updated",
            "All agent profile pages updated",
            "All workflow documentation updated",
            "All task templates updated",
            "Documentation index created or updated",
            "**MANDATORY:** All updates documented in Notion with links to related items"
        ],
        deliverables={
            "files_to_review": [
                "/Users/brianhellemn/Projects/github-production/shared_core/notion/task_creation.py",
                "/Users/brianhellemn/Projects/github-production/docs/agents/AGENT_HANDOFF_TASK_GENERATOR_V3.0.md",
                "/Users/brianhellemn/Projects/github-production/docs/MANDATORY_NEXT_HANDOFF_REQUIREMENT.md",
                "/Users/brianhellemn/Projects/github-production/docs/SYSTEM_ENFORCEMENT_NEXT_HANDOFF.md",
                "/Users/brianhellemn/Projects/github-production/docs/CRITICAL_SYSTEM_REQUIREMENTS.md"
            ],
            "notion_pages_to_review": [
                "Universal Four-Agent Coordination Workflow",
                "All agent profile pages in Agents database",
                "All workflow documentation pages",
                "All task templates",
                "All related documentation pages"
            ],
            "artifacts": [
                "Gap analysis report in Notion",
                "Conflict analysis report in Notion",
                "Integration plan in Notion",
                "Updated Universal Four-Agent Coordination Workflow",
                "Updated agent profile pages",
                "Updated workflow documentation",
                "Updated task templates",
                "Documentation index"
            ],
            "next_handoff": {
                "target_agent": "TO_BE_DETERMINED",
                "task_id": "TO_BE_DETERMINED",
                "task_name": "Documentation Integration & Final Validation",
                "inbox_path": "TO_BE_DETERMINED",
                "required": True,
                "instructions": "Create handoff trigger file or document completion in Notion with all analysis findings and updates completed."
            }
        },
        priority="Critical",
        urgency="Critical"
    )
    
    # Ensure directory exists
    NOTION_AI_RESEARCH_INBOX.mkdir(parents=True, exist_ok=True)
    
    # CRITICAL: Check for existing trigger file to prevent duplicates
    task_id = handoff_data.get("task_url", "").split("/")[-1] if handoff_data.get("task_url") else None
    if task_id:
        task_id_short = task_id.replace("-", "")[:8] if len(task_id) > 8 else task_id
        # Check for existing trigger files with this task ID (in inbox, processed, or failed)
        base_folder = NOTION_AI_RESEARCH_INBOX.parent
        for subfolder in ["01_inbox", "02_processed", "03_failed"]:
            check_folder = base_folder / subfolder
            if check_folder.exists():
                existing_files = list(check_folder.glob(f"*{task_id_short}*.json"))
                if existing_files:
                    existing_file = existing_files[0]
                    print(f"⚠️  Trigger file already exists for task {task_id_short} in {subfolder}: {existing_file.name}. Skipping duplicate creation.", file=sys.stderr)
                    return existing_file  # Return existing file instead of creating duplicate
    
    # Create trigger file
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    filename = f"{timestamp}__HANDOFF__Handoff-Review-Notion-Documentation__Notion-AI-Research-Agent.json"
    file_path = NOTION_AI_RESEARCH_INBOX / filename
    
    # Write handoff file
    with open(file_path, 'w') as f:
        json.dump(handoff_data, f, indent=2)
    
    return file_path


def main():
    """Create Notion AI Research Agent handoff trigger file."""
    print("🚀 Creating Notion AI Research Agent Handoff...\n")
    print("="*80)
    
    # Get issue ID and project ID from command line or use defaults
    import sys
    issue_id = sys.argv[1] if len(sys.argv) > 1 else None
    project_id = sys.argv[2] if len(sys.argv) > 2 else UNIFIED_ENV_PROJECT_ID
    
    handoff_file = create_notion_ai_research_handoff(
        issue_id=issue_id,
        project_id=project_id
    )
    
    print(f"✅ Created Notion AI Research Agent handoff trigger file:")
    print(f"   Path: {handoff_file}")
    print(f"   Name: {handoff_file.name}")
    print(f"\n📋 Handoff includes:")
    print(f"   - Comprehensive Notion documentation review requirements")
    print(f"   - Gap analysis requirements")
    print(f"   - Conflict analysis requirements")
    print(f"   - Integration plan requirements")
    print(f"   - Mandatory next handoff requirement")
    print(f"\n🔗 Related Items:")
    if issue_id:
        print(f"   Issue: https://www.notion.so/{issue_id.replace('-', '')}")
    print(f"   Project: https://www.notion.so/{project_id.replace('-', '')}")


if __name__ == "__main__":
    main()


























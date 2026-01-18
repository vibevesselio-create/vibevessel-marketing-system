#!/usr/bin/env python3
"""
Create Unified Environment Management Project
=============================================

Creates a comprehensive project with ALL agents reviewing and approving a unified,
system-mandated, and enforced environment management solution.

This project includes:
1. Audit of existing implementation
2. Coordinated review by all agents
3. Approval process requiring all agents to agree
4. Implementation of unified solution
5. Enforcement mechanisms
"""

import os
import sys
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
from dotenv import load_dotenv

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

load_dotenv()

# MANDATORY: Import task creation helpers that enforce next handoff requirement
try:
    from shared_core.notion.task_creation import (
        add_mandatory_next_handoff_instructions,
        create_task_description_with_next_handoff
    )
    TASK_CREATION_HELPERS_AVAILABLE = True
except ImportError:
    TASK_CREATION_HELPERS_AVAILABLE = False
    print("⚠️  WARNING: Task creation helpers not available. Next handoff requirement may be missing!", file=sys.stderr)

try:
    from notion_client import Client
    NOTION_AVAILABLE = True
except ImportError:
    NOTION_AVAILABLE = False
    Client = None

# Database IDs
PROJECTS_DB_ID = "286e73616c2781ffa450db2ecad4b0ba"  # Agent-Projects (corrected)
AGENT_TASKS_DB_ID = "284e73616c278018872aeb14e82e0392"  # Agent-Tasks
ISSUES_QUESTIONS_DB_ID = "229e73616c27808ebf06c202b10b5166"  # Issues+Questions

# All Agent IDs
CURSOR_MM1_AGENT_ID = "249e7361-6c27-8100-8a74-de7eabb9fc8d"  # Cursor MM1 Agent
CLAUDE_MM1_AGENT_ID = "fa54f05c-e184-403a-ac28-87dd8ce9855b"  # Claude MM1 Agent
CHATGPT_AGENT_ID = "9c4b6040-5e0f-4d31-ae1b-d4a43743b224"  # ChatGPT
NOTION_AI_DATAOPS_ID = "2d9e7361-6c27-80c5-ba24-c6f847789d77"  # Notion AI Data Operations
NOTION_AI_RESEARCH_ID = "2d9e7361-6c27-80c5-ba24-c6f847789d77"  # Notion AI Research (using DataOps for now)

# Workflow ID
UNIVERSAL_WORKFLOW_ID = "462a2e85-6118-4399-bcb9-85caa786977e"  # Universal Four-Agent Coordination Workflow

# Related Issue ID (from report_environment_management_issue.py)
RELATED_ISSUE_ID = "2dae7361-6c27-8101-aa42-e875bf8e033b"  # Will be updated after issue creation


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


def create_project(client: Client, issue_id: str) -> Optional[str]:
    """Create Unified Environment Management Project."""
    try:
        project_properties = {
            "Project Name": {
                "title": [{"text": {"content": "Unified Environment Management Implementation & Enforcement"}}]
            },
            "Summary": {
                "rich_text": [{
                    "text": {
                        "content": "Comprehensive project to audit existing environment management implementation, create unified solution with coordinated review from ALL agents, and implement system-mandated enforcement mechanisms. Requires approval from all agents before implementation."
                    }
                }]
            },
            "Status": {
                "status": {"name": "In Progress"}
            },
            "Priority": {
                "select": {"name": "Critical"}
            },
            "Owner": {
                "relation": [{"id": CURSOR_MM1_AGENT_ID}]
            }
        }
        
        # Try to add Issues relation if property exists
        if "Issues" in project_properties or True:  # Try anyway
            try:
                project_properties["Issues"] = {
                    "relation": [{"id": issue_id}]
                }
            except:
                pass
        
        page = client.pages.create(
            parent={"database_id": PROJECTS_DB_ID},
            properties=project_properties
        )
        
        project_id = page.get("id")
        print(f"✅ Created Project: Unified Environment Management Implementation & Enforcement")
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
    priority: str = "Critical",
    dependency_status: str = "Ready",
    prerequisite_task_ids: Optional[List[str]] = None,
    review_agent_ids: Optional[List[str]] = None,
    # MANDATORY: Next handoff parameters
    next_task_name: Optional[str] = None,
    next_target_agent: Optional[str] = None,
    next_task_id: Optional[str] = None,
    project_name: Optional[str] = None
) -> Optional[str]:
    """
    Create a Task in Agent-Tasks database.
    
    **MANDATORY:** If next_task_name and next_target_agent are provided, description
    will automatically include mandatory next handoff instructions.
    """
    try:
        # MANDATORY: Add next handoff instructions if next task info provided
        if TASK_CREATION_HELPERS_AVAILABLE and next_task_name and next_target_agent:
            description = add_mandatory_next_handoff_instructions(
                description=description,
                next_task_name=next_task_name,
                target_agent=next_target_agent,
                next_task_id=next_task_id or "TO_BE_CREATED",
                project_name=project_name or "Project"
            )
        elif next_task_name and next_target_agent:
            # Fallback if helpers not available - add basic requirement
            description += f"\n\n## 🚨 MANDATORY HANDOFF REQUIREMENT\n\nUpon completion, you MUST create a handoff trigger file for {next_task_name} assigned to {next_target_agent}."
        
        properties = {
            "Task Name": {
                "title": [{"text": {"content": task_name}}]
            },
            "Description": {
                "rich_text": [{"text": {"content": description[:2000]}}]
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
        
        # Add review agents if provided
        if review_agent_ids:
            try:
                # Try Review-Agent property (single)
                if len(review_agent_ids) == 1:
                    properties["Review-Agent"] = {
                        "relation": [{"id": review_agent_ids[0]}]
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
        return task_id
        
    except Exception as e:
        print(f"❌ Error creating task '{task_name}': {e}", file=sys.stderr)
        return None


def main():
    """Create complete Unified Environment Management project structure."""
    if not NOTION_AVAILABLE:
        print("❌ notion-client not available. Install with: pip install notion-client")
        sys.exit(1)
    
    token = get_notion_token()
    if not token:
        print("❌ NOTION_TOKEN not found in environment or unified_config")
        sys.exit(1)
    
    client = Client(auth=token)
    
    print("🚀 Creating Unified Environment Management Project...\n")
    print("="*80)
    
    # Step 1: Create Project
    project_id = create_project(client, RELATED_ISSUE_ID)
    if not project_id:
        print("❌ Failed to create project. Exiting.")
        sys.exit(1)
    
    print("\n" + "="*80)
    print("Creating Coordinated Review Tasks for ALL Agents")
    print("="*80 + "\n")
    
    # Phase 1: Audit Existing Implementation
    phase1_description = f"""**PRIMARY DELIVERABLE:** Audit existing environment management implementation and determine if it should be replaced or updated.

**Existing Implementation Location:**
- `shared_core/notion/execution_logs.py` - `_get_notion_client()` function (lines 58-78)
- Missing: `load_dotenv()` call
- Missing: `VV_AUTOMATIONS_WS_TOKEN` check
- Has: `NOTION_API_KEY`, `NOTION_TOKEN`, `NOTION_API_TOKEN` checks
- Has: `unified_config` fallback

**Audit Requirements:**
1. Review `shared_core/notion/execution_logs.py` implementation
2. Compare with documented pattern in `docs/ENVIRONMENT_MANAGEMENT_PATTERN.md`
3. Identify all gaps and deviations
4. Review all other implementations across codebase
5. Document findings in Notion

**Deliverables:**
- Audit report in Notion
- Gap analysis document
- Recommendation: Replace or Update existing implementation
- List of all files using incorrect pattern

**Related Issue:** https://www.notion.so/{RELATED_ISSUE_ID.replace('-', '')}
"""
    
    phase1_id = create_task(
        client=client,
        project_id=project_id,
        task_name="Phase 1: Audit Existing Environment Management Implementation",
        description=phase1_description,
        assigned_agent_id=CLAUDE_MM1_AGENT_ID,  # Validation/Review Agent
        priority="Critical",
        dependency_status="Ready",
        # MANDATORY: Next handoff info
        next_task_name="Phase 2: Technical Review & Shared Utility Design",
        next_target_agent="Cursor MM1 Agent",
        next_task_id="TO_BE_CREATED",
        project_name="Unified Environment Management Implementation"
    )
    
    # Phase 2: Cursor MM1 - Technical Review & Shared Utility Design
    phase2_description = f"""**Technical Review & Shared Utility Design**

**Requirements:**
1. Review audit findings from Phase 1
2. Design `shared_core/notion/token_manager.py` with standardized `get_notion_token()` function
3. Ensure compatibility with existing codebase
4. Design migration path for existing implementations
5. Create technical specification document

**Design Requirements:**
- Must follow exact pattern from `docs/ENVIRONMENT_MANAGEMENT_PATTERN.md`
- Must check: NOTION_TOKEN, NOTION_API_TOKEN, VV_AUTOMATIONS_WS_TOKEN
- Must include unified_config fallback
- Must handle all exceptions gracefully
- Must be importable from any script location
- Must be backward compatible

**Deliverables:**
- Technical specification document
- `shared_core/notion/token_manager.py` design document
- Migration plan for existing code
- Compatibility analysis

**Prerequisite:** Phase 1 (Audit) must be completed
**Related Issue:** https://www.notion.so/{RELATED_ISSUE_ID.replace('-', '')}
"""
    
    phase2_id = create_task(
        client=client,
        project_id=project_id,
        task_name="Phase 2: Technical Review & Shared Utility Design",
        description=phase2_description,
        assigned_agent_id=CURSOR_MM1_AGENT_ID,  # Technical Implementation Agent
        priority="Critical",
        dependency_status="Blocked",
        prerequisite_task_ids=[phase1_id] if phase1_id else None,
        review_agent_ids=[CLAUDE_MM1_AGENT_ID],
        # MANDATORY: Next handoff info
        next_task_name="Phase 3: Strategic Review & Coordination Protocol Design",
        next_target_agent="ChatGPT",
        next_task_id=phase3_id if 'phase3_id' in locals() else "TO_BE_CREATED",
        project_name="Unified Environment Management Implementation"
    )
    
    # Phase 3: ChatGPT - Strategic Review & Coordination Protocol
    phase3_description = f"""**Strategic Review & Coordination Protocol Design**

**Requirements:**
1. Review technical design from Phase 2
2. Design agent coordination protocol for pattern enforcement
3. Update Universal Four-Agent Coordination Workflow
4. Create agent prompt updates
5. Design approval process requiring all agents

**Strategic Requirements:**
- Protocol must prevent future violations
- Must integrate with existing workflow
- Must include validation checkpoints
- Must require explicit agent approval
- Must be enforceable system-wide

**Deliverables:**
- Agent coordination protocol document
- Updated workflow documentation
- Agent prompt update specifications
- Approval process design
- Enforcement strategy

**Prerequisite:** Phase 2 (Technical Design) must be completed
**Related Issue:** https://www.notion.so/{RELATED_ISSUE_ID.replace('-', '')}
"""
    
    phase3_id = create_task(
        client=client,
        project_id=project_id,
        task_name="Phase 3: Strategic Review & Coordination Protocol Design",
        description=phase3_description,
        assigned_agent_id=CHATGPT_AGENT_ID,  # Strategic Planning Agent
        priority="Critical",
        dependency_status="Blocked",
        prerequisite_task_ids=[phase2_id] if phase2_id else None,
        review_agent_ids=[CLAUDE_MM1_AGENT_ID, CURSOR_MM1_AGENT_ID],
        # MANDATORY: Next handoff info
        next_task_name="Phase 4: Data Review & Documentation",
        next_target_agent="Notion AI Data Operations",
        next_task_id="TO_BE_CREATED",
        project_name="Unified Environment Management Implementation"
    )
    
    # Phase 4: Notion AI DataOps - Data Review & Documentation
    phase4_description = f"""**Data Review & Documentation**

**Requirements:**
1. Review all documentation from Phases 1-3
2. Create comprehensive documentation
3. Update all agent system prompts
4. Create visual checklists and templates
5. Ensure all documentation is linked and accessible

**Documentation Requirements:**
- Update `docs/ENVIRONMENT_MANAGEMENT_PATTERN.md`
- Create script templates with correct pattern
- Create agent onboarding guide
- Create visual compliance checklist
- Link all related documentation

**Deliverables:**
- Updated pattern documentation
- Script template files
- Agent onboarding documentation
- Visual compliance checklist
- Documentation index

**Prerequisite:** Phase 3 (Strategic Design) must be completed
**Related Issue:** https://www.notion.so/{RELATED_ISSUE_ID.replace('-', '')}
"""
    
    phase4_id = create_task(
        client=client,
        project_id=project_id,
        task_name="Phase 4: Data Review & Documentation",
        description=phase4_description,
        assigned_agent_id=NOTION_AI_DATAOPS_ID,  # Data Operations Agent
        priority="Critical",
        dependency_status="Blocked",
        prerequisite_task_ids=[phase3_id] if phase3_id else None,
        review_agent_ids=[CLAUDE_MM1_AGENT_ID],
        # MANDATORY: Next handoff info
        next_task_name="Phase 5: Coordinated Review & Approval (ALL AGENTS REQUIRED)",
        next_target_agent="Claude MM1 Agent",
        next_task_id="TO_BE_CREATED",
        project_name="Unified Environment Management Implementation"
    )
    
    # Phase 5: Coordinated Review & Approval (ALL AGENTS)
    phase5_description = f"""**COORDINATED REVIEW & APPROVAL - REQUIRES ALL AGENTS**

**CRITICAL:** This phase requires explicit approval from ALL agents before proceeding.

**Review Process:**
1. **Claude MM1** reviews audit findings and validates completeness
2. **Cursor MM1** reviews technical design and validates implementation approach
3. **ChatGPT** reviews strategic design and validates coordination protocol
4. **Notion AI DataOps** reviews documentation and validates accessibility
5. **ALL AGENTS** must explicitly approve before Phase 6

**Approval Criteria:**
- All agents must agree on technical soundness
- All agents must agree on unified approach
- All agents must agree on enforcement mechanisms
- All agents must agree on migration strategy
- All agents must confirm no gaps or concerns

**Deliverables:**
- Coordinated review document
- Approval signatures from all agents
- Finalized implementation plan
- Risk assessment and mitigation plan

**Prerequisite:** Phases 1-4 must be completed
**Related Issue:** https://www.notion.so/{RELATED_ISSUE_ID.replace('-', '')}
"""
    
    phase5_id = create_task(
        client=client,
        project_id=project_id,
        task_name="Phase 5: Coordinated Review & Approval (ALL AGENTS REQUIRED)",
        description=phase5_description,
        assigned_agent_id=CLAUDE_MM1_AGENT_ID,  # Coordination Agent
        priority="Critical",
        dependency_status="Blocked",
        prerequisite_task_ids=[phase1_id, phase2_id, phase3_id, phase4_id] if all([phase1_id, phase2_id, phase3_id, phase4_id]) else None,
        review_agent_ids=[CURSOR_MM1_AGENT_ID, CHATGPT_AGENT_ID, NOTION_AI_DATAOPS_ID],
        # MANDATORY: Next handoff info
        next_task_name="Phase 6: Implementation (After ALL Agents Approve)",
        next_target_agent="Cursor MM1 Agent",
        next_task_id="TO_BE_CREATED",
        project_name="Unified Environment Management Implementation"
    )
    
    # Phase 6: Implementation (Cursor MM1)
    phase6_description = f"""**IMPLEMENTATION - Only after ALL agents approve**

**Implementation Steps:**
1. Create `shared_core/notion/token_manager.py` with approved design
2. Update existing implementation in `shared_core/notion/execution_logs.py`
3. Migrate all scripts to use shared utility
4. Update all agent prompts
5. Implement enforcement mechanisms (pre-commit hooks, linting, CI/CD)

**Implementation Requirements:**
- Follow approved technical design exactly
- Maintain backward compatibility
- Update all existing scripts
- Implement automated validation
- Create enforcement mechanisms

**Deliverables:**
- `shared_core/notion/token_manager.py` implementation
- Updated `shared_core/notion/execution_logs.py`
- All scripts migrated to use shared utility
- Pre-commit hooks implemented
- Linting rules implemented
- CI/CD checks implemented
- All tests passing

**Prerequisite:** Phase 5 (Coordinated Approval) must be completed with ALL agents approving
**Related Issue:** https://www.notion.so/{RELATED_ISSUE_ID.replace('-', '')}
"""
    
    phase6_id = create_task(
        client=client,
        project_id=project_id,
        task_name="Phase 6: Implementation (After ALL Agents Approve)",
        description=phase6_description,
        assigned_agent_id=CURSOR_MM1_AGENT_ID,  # Implementation Agent
        priority="Critical",
        dependency_status="Blocked",
        prerequisite_task_ids=[phase5_id] if phase5_id else None,
        review_agent_ids=[CLAUDE_MM1_AGENT_ID, CHATGPT_AGENT_ID],
        # MANDATORY: Next handoff info
        next_task_name="Phase 7: Final Validation & Enforcement Verification",
        next_target_agent="Claude MM1 Agent",
        next_task_id="TO_BE_CREATED",
        project_name="Unified Environment Management Implementation"
    )
    
    # Phase 7: Final Validation & Enforcement (Claude MM1)
    phase7_description = f"""**Final Validation & Enforcement Verification**

**Validation Requirements:**
1. Verify all implementations follow approved design
2. Verify all scripts use shared utility
3. Verify enforcement mechanisms work correctly
4. Verify no violations exist
5. Create final validation report

**Enforcement Verification:**
- Pre-commit hooks prevent violations
- Linting rules flag violations
- CI/CD checks fail on violations
- All existing scripts compliant
- Documentation complete and accessible

**Deliverables:**
- Final validation report
- Enforcement mechanism verification
- Compliance audit results
- Project completion documentation
- Lessons learned document

**Prerequisite:** Phase 6 (Implementation) must be completed
**Related Issue:** https://www.notion.so/{RELATED_ISSUE_ID.replace('-', '')}
"""
    
    phase7_id = create_task(
        client=client,
        project_id=project_id,
        task_name="Phase 7: Final Validation & Enforcement Verification",
        description=phase7_description,
        assigned_agent_id=CLAUDE_MM1_AGENT_ID,  # Validation Agent
        priority="Critical",
        dependency_status="Blocked",
        prerequisite_task_ids=[phase6_id] if phase6_id else None,
        review_agent_ids=[CURSOR_MM1_AGENT_ID, CHATGPT_AGENT_ID, NOTION_AI_DATAOPS_ID],
        # MANDATORY: Next handoff info (project completion/follow-up)
        next_task_name="Project Completion & Follow-up Tasks",
        next_target_agent="Claude MM1 Agent",
        next_task_id="TO_BE_DETERMINED",
        project_name="Unified Environment Management Implementation"
    )
    
    print("\n" + "="*80)
    print("PROJECT CREATED WITH COORDINATED AGENT REVIEW PROCESS")
    print("="*80)
    print(f"\nProject ID: {project_id}")
    print(f"Project URL: https://www.notion.so/{project_id.replace('-', '')}")
    print(f"\nPhases Created:")
    print(f"  1. Phase 1: Audit Existing Implementation (Claude MM1)")
    print(f"  2. Phase 2: Technical Review & Design (Cursor MM1)")
    print(f"  3. Phase 3: Strategic Review & Protocol (ChatGPT)")
    print(f"  4. Phase 4: Data Review & Documentation (Notion AI DataOps)")
    print(f"  5. Phase 5: Coordinated Review & Approval (ALL AGENTS REQUIRED)")
    print(f"  6. Phase 6: Implementation (Cursor MM1 - After Approval)")
    print(f"  7. Phase 7: Final Validation & Enforcement (Claude MM1)")
    print(f"\n✅ All tasks linked to project and related issue")
    print(f"✅ Dependencies configured")
    print(f"✅ Review agents assigned")
    print(f"\n⚠️  CRITICAL: Phase 5 requires explicit approval from ALL agents before Phase 6")


if __name__ == "__main__":
    main()


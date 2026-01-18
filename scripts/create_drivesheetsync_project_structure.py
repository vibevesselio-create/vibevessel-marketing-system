#!/usr/bin/env python3
"""
Create DriveSheetsSync Project Structure
=========================================

Creates a complete project structure in Notion following the Universal Four-Agent
Coordination Workflow for DriveSheetsSync production readiness and testing.

This script creates:
1. Project in Projects database
2. Tasks for each workflow phase
3. Sub-tasks with proper agent assignments
4. All required properties, relations, and documentation links
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

try:
    from notion_client import Client
    NOTION_AVAILABLE = True
except ImportError:
    NOTION_AVAILABLE = False
    Client = None

# Database IDs
PROJECTS_DB_ID = "286e7361-6c27-8114-af56-000bb586ef5b"  # Agent-Projects
AGENT_TASKS_DB_ID = "284e73616c278018872aeb14e82e0392"  # Agent-Tasks (secondary)
DATABASE_PARENT_PAGE_ID = "26ce73616c278141af54dd115915445c"  # database-parent-page

# Agent IDs
CURSOR_MM1_AGENT_ID = "249e7361-6c27-8100-8a74-de7eabb9fc8d"  # Cursor MM1 Agent
CLAUDE_MM1_AGENT_ID = "fa54f05c-e184-403a-ac28-87dd8ce9855b"  # Claude MM1 Agent
CHATGPT_AGENT_ID = "9c4b6040-5e0f-4d31-ae1b-d4a43743b224"  # ChatGPT (from workflow page)
NOTION_AI_DATAOPS_ID = "2d9e7361-6c27-80c5-ba24-c6f847789d77"  # Notion AI Data Operations

# Workflow ID
UNIVERSAL_WORKFLOW_ID = "462a2e85-6118-4399-bcb9-85caa786977e"  # Universal Four-Agent Coordination Workflow

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
    """Create DriveSheetsSync Project in Projects database."""
    try:
        project_properties = {
            "Name": {
                "title": [{"text": {"content": "DriveSheetsSync Production Readiness & Testing"}}]
            },
            "Description": {
                "rich_text": [{
                    "text": {
                        "content": "Complete DriveSheetsSync script production readiness review, critical fixes, comprehensive testing, and production deployment following Universal Four-Agent Coordination Workflow."
                    }
                }]
            },
            "Status": {
                "select": {"name": "In Progress"}
            },
            "Priority": {
                "select": {"name": "Critical"}
            },
            "Execution-Agent": {
                "relation": [{"id": CURSOR_MM1_AGENT_ID}]
            },
            "Validation-Agent": {
                "relation": [{"id": CLAUDE_MM1_AGENT_ID}]
            },
            "Workflow": {
                "relation": [{"id": UNIVERSAL_WORKFLOW_ID}]
            }
        }
        
        page = client.pages.create(
            parent={"database_id": PROJECTS_DB_ID},
            properties=project_properties
        )
        
        project_id = page.get("id")
        print(f"✅ Created Project: {project_id}")
        print(f"   URL: {page.get('url', 'N/A')}")
        return project_id
        
    except Exception as e:
        print(f"❌ Error creating project: {e}", file=sys.stderr)
        return None


def create_task(
    client: Client,
    project_id: str,
    task_name: str,
    description: str,
    phase: str,
    assigned_agent_id: str,
    priority: str = "Critical",
    dependency_status: str = "Ready",
    prerequisite_task_id: Optional[str] = None
) -> Optional[str]:
    """Create a Task in Agent-Tasks database."""
    try:
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
                "status": {"name": "Not Started"}
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
        
        # Add prerequisite task if provided
        if prerequisite_task_id:
            try:
                properties["Prerequisite Tasks"] = {
                    "relation": [{"id": prerequisite_task_id}]
                }
            except:
                pass  # Property may not exist
        
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
        return None


def update_task_with_steps(
    client: Client,
    task_id: str,
    steps: List[str],
    success_criteria: List[str],
    next_required_step: str
):
    """Update task with Steps, Success Criteria, and Next Required Step."""
    try:
        # Format steps as numbered list
        steps_text = "\n".join([f"{i+1}. {step}" for i, step in enumerate(steps)])
        success_text = "\n".join([f"- {criterion}" for criterion in success_criteria])
        
        properties = {
            "Steps": {
                "rich_text": [{"text": {"content": steps_text}}]
            },
            "Success Criteria": {
                "rich_text": [{"text": {"content": success_text}}]
            },
            "Next Required Step": {
                "rich_text": [{"text": {"content": next_required_step}}]
            }
        }
        
        client.pages.update(page_id=task_id, properties=properties)
        print(f"   ✅ Updated task with steps and success criteria")
        
    except Exception as e:
        print(f"   ⚠️  Warning: Could not update task properties: {e}", file=sys.stderr)


def main():
    """Create complete DriveSheetsSync project structure."""
    if not NOTION_AVAILABLE:
        print("❌ notion-client not available. Install with: pip install notion-client")
        sys.exit(1)
    
    token = get_notion_token()
    if not token:
        print("❌ NOTION_TOKEN not found in environment or unified_config")
        sys.exit(1)
    
    client = Client(auth=token)
    
    print("🚀 Creating DriveSheetsSync Project Structure...\n")
    
    # Step 1: Create Project
    project_id = create_project(client)
    if not project_id:
        print("❌ Failed to create project. Exiting.")
        sys.exit(1)
    
    print("\n" + "="*80)
    print("Creating Tasks for Each Phase")
    print("="*80 + "\n")
    
    # Phase 0: Pre-flight validation and context loading
    phase0_id = create_task(
        client=client,
        project_id=project_id,
        task_name="Phase 0: Pre-flight Validation & Context Loading",
        description="""Validate setup, load context, and ensure all components are ready for execution.

**Key Activities:**
- Validate Notion database access and permissions
- Verify script properties and configuration
- Load current state documentation
- Confirm agent assignments and workflow linkage
- Validate all required relations populated

**Deliverables:**
- Validation Report
- Context Summary
- Pre-flight Checklist Completion""",
        phase="Phase 0",
        assigned_agent_id=CLAUDE_MM1_AGENT_ID,  # Validation Agent
        priority="Critical",
        dependency_status="Ready"
    )
    
    if phase0_id:
        update_task_with_steps(
            client, phase0_id,
            steps=[
                "Load and validate DriveSheetsSync current state documentation",
                "Verify Notion database access (Projects, Agent-Tasks, Execution-Logs)",
                "Validate script properties and GAS configuration",
                "Confirm agent assignments (Cursor MM1, Claude MM1, ChatGPT, Notion AI)",
                "Verify workflow linkage to Universal Four-Agent Coordination Workflow",
                "Check all required relations populated (Clients, Workspace-Areas, Owner)",
                "Validate documentation links accessible"
            ],
            success_criteria=[
                "All databases accessible and permissions verified",
                "Script configuration validated",
                "All required relations populated",
                "Agent assignments confirmed",
                "Workflow linkage verified",
                "Pre-flight checklist 100% complete"
            ],
            next_required_step="Proceed to Phase 1: Discovery and Audit"
        )
    
    # Phase 1: Discovery and audit
    phase1_id = create_task(
        client=client,
        project_id=project_id,
        task_name="Phase 1: Discovery & Audit",
        description="""Analyze current state, identify all issues, and create comprehensive audit report.

**Key Activities:**
- Review production readiness summary
- Audit current implementation state
- Identify all critical, high, and medium priority issues
- Document testing requirements
- Create comprehensive testing methodology

**Deliverables:**
- Current State Summary
- Issue Inventory
- Testing Methodology Document
- Audit Report""",
        phase="Phase 1",
        assigned_agent_id=CHATGPT_AGENT_ID,  # Strategic Planning
        priority="Critical",
        dependency_status="Dependencies Met" if phase0_id else "Ready",
        prerequisite_task_id=phase0_id
    )
    
    if phase1_id:
        update_task_with_steps(
            client, phase1_id,
            steps=[
                "Review DRIVESHEETSSYNC_PRODUCTION_READINESS_AND_TESTING.md",
                "Review DRIVESHEETSSYNC_CURRENT_STATE_SUMMARY.md",
                "Analyze all identified issues (token handling, diagnostic functions, archive folders)",
                "Review audit findings from drive_sheets_issues_for_linear.json",
                "Document comprehensive testing requirements",
                "Create test database structure plan",
                "Document all file types and property types to test",
                "Create issue inventory with priorities"
            ],
            success_criteria=[
                "All issues identified and documented",
                "Testing methodology complete",
                "Test requirements fully specified",
                "Audit report created with evidence",
                "Issue inventory prioritized"
            ],
            next_required_step="Proceed to Phase 2: Execution and Implementation"
        )
    
    # Phase 2: Execution and implementation (Critical Fixes)
    phase2_id = create_task(
        client=client,
        project_id=project_id,
        task_name="Phase 2: Critical Fixes Implementation",
        description="""Implement all critical fixes required for production readiness.

**Key Activities:**
- Fix token handling to accept both 'secret_' and 'ntn_' prefixes
- Create/deploy diagnostic functions
- Audit and create missing archive folders
- Test multi-script compatibility
- Update documentation

**Deliverables:**
- Fixed Code.gs with updated token handling
- Diagnostic Functions deployed to GAS
- Archive folders created and verified
- Multi-script compatibility test results
- Updated documentation""",
        phase="Phase 2",
        assigned_agent_id=CURSOR_MM1_AGENT_ID,  # Execution Agent
        priority="Critical",
        dependency_status="Dependencies Met" if phase1_id else "Ready",
        prerequisite_task_id=phase1_id
    )
    
    if phase2_id:
        update_task_with_steps(
            client, phase2_id,
            steps=[
                "Fix token handling in setupScriptProperties() to accept both 'secret_' and 'ntn_' prefixes",
                "Create DIAGNOSTIC_FUNCTIONS.gs file with all required functions",
                "Deploy diagnostic functions to GAS using clasp push",
                "Test diagnostic functions in GAS editor",
                "Audit workspace-databases directory for missing .archive folders",
                "Create missing archive folders (automated or manual)",
                "Verify archive functionality works correctly",
                "Test multi-script compatibility with Project Manager Bot",
                "Update documentation with fixes"
            ],
            success_criteria=[
                "Token handling accepts both token formats",
                "Diagnostic functions created and deployed",
                "All missing archive folders created",
                "Multi-script compatibility verified",
                "All fixes tested and documented",
                "Code changes deployed to GAS"
            ],
            next_required_step="Proceed to Phase 3: Testing and Validation"
        )
    
    # Phase 3: Testing and validation
    phase3_id = create_task(
        client=client,
        project_id=project_id,
        task_name="Phase 3: Comprehensive Testing & Validation",
        description="""Execute comprehensive testing methodology covering all functions, file types, and properties.

**Key Activities:**
- Create test databases and test files
- Execute all property type tests (14 types)
- Execute all synchronization function tests
- Execute all file type tests
- Execute error handling and edge case tests
- Execute multi-script compatibility tests
- Execute performance and data integrity tests

**Deliverables:**
- Test execution results
- Test database with all test cases
- Test files for all supported types
- Test report with pass/fail status
- Performance metrics
- Data integrity validation results""",
        phase="Phase 3",
        assigned_agent_id=CURSOR_MM1_AGENT_ID,  # Execution Agent
        priority="Critical",
        dependency_status="Dependencies Met" if phase2_id else "Ready",
        prerequisite_task_id=phase2_id
    )
    
    if phase3_id:
        update_task_with_steps(
            client, phase3_id,
            steps=[
                "Create test databases (Basic Properties, Advanced Properties, File Types, Schema Sync, Multi-Script)",
                "Create test files for all supported types (text, documents, images, videos, audio, archives, code, spreadsheets)",
                "Execute property type tests (PT-1 through PT-14)",
                "Execute schema synchronization tests (SC-1 through SC-4)",
                "Execute data synchronization tests (DS-1 through DS-4)",
                "Execute file synchronization tests (FS-1 through FS-5)",
                "Execute error handling tests (EH-1 through EH-7)",
                "Execute multi-script compatibility tests (MS-1 through MS-5)",
                "Execute performance tests (PF-1 through PF-4)",
                "Execute data integrity tests (DI-1 through DI-3)",
                "Document all test results",
                "Create test report with evidence"
            ],
            success_criteria=[
                "All 46 test cases executed",
                "Test coverage >90% for all functions",
                "All file types tested",
                "All property types tested",
                "All error scenarios tested",
                "Performance within acceptable limits",
                "Data integrity verified",
                "Test report complete with evidence"
            ],
            next_required_step="Proceed to Phase 4: Production Deployment"
        )
    
    # Phase 4: Production deployment
    phase4_id = create_task(
        client=client,
        project_id=project_id,
        task_name="Phase 4: Production Deployment & Monitoring",
        description="""Deploy to production and monitor initial runs.

**Key Activities:**
- Complete pre-deployment checklist
- Deploy updated script to GAS
- Configure script properties
- Set up monitoring
- Monitor initial production runs
- Document deployment

**Deliverables:**
- Production deployment complete
- Monitoring dashboard/configuration
- Initial production run results
- Deployment documentation
- Post-deployment report""",
        phase="Phase 4",
        assigned_agent_id=CLAUDE_MM1_AGENT_ID,  # Validation Agent
        priority="Critical",
        dependency_status="Dependencies Met" if phase3_id else "Ready",
        prerequisite_task_id=phase3_id
    )
    
    if phase4_id:
        update_task_with_steps(
            client, phase4_id,
            steps=[
                "Review all test results and verify all critical fixes completed",
                "Complete pre-deployment checklist",
                "Deploy updated script to GAS using clasp push",
                "Verify script properties configured correctly",
                "Set up monitoring and alerting",
                "Test in production environment",
                "Monitor initial production runs (first 48 hours critical)",
                "Check for errors or warnings in execution logs",
                "Verify data integrity maintained",
                "Monitor performance metrics",
                "Document deployment and results",
                "Update team on deployment status"
            ],
            success_criteria=[
                "Script deployed successfully to production",
                "Initial production runs successful",
                "No critical errors in first 48 hours",
                "Performance within acceptable limits",
                "Data integrity maintained",
                "Monitoring in place and functioning",
                "Deployment documented",
                "Team notified"
            ],
            next_required_step="Project Complete - All phases executed successfully"
        )
    
    print("\n" + "="*80)
    print("Project Structure Created Successfully!")
    print("="*80)
    print(f"\nProject ID: {project_id}")
    print(f"Project URL: https://www.notion.so/{project_id.replace('-', '')}")
    print(f"\nTasks Created:")
    if phase0_id:
        print(f"  - Phase 0: Pre-flight Validation")
    if phase1_id:
        print(f"  - Phase 1: Discovery & Audit")
    if phase2_id:
        print(f"  - Phase 2: Critical Fixes Implementation")
    if phase3_id:
        print(f"  - Phase 3: Comprehensive Testing & Validation")
    if phase4_id:
        print(f"  - Phase 4: Production Deployment & Monitoring")
    print("\n✅ All tasks follow Universal Four-Agent Coordination Workflow")
    print("✅ Agent assignments configured (ChatGPT → Cursor → Claude → Notion AI)")
    print("✅ Dependencies and prerequisites set up")
    print("✅ Steps, success criteria, and next required steps populated")


if __name__ == "__main__":
    main()



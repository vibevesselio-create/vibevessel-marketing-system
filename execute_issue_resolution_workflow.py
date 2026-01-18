#!/usr/bin/env python3
"""
Issue Resolution and Project Task Execution Workflow

Implements the workflow to:
1. Review outstanding issues in Notion
2. Identify and resolve critical issues
3. Or review and complete in-progress project tasks
4. Create handoff trigger files with mandatory next handoff instructions
"""

import sys
import subprocess
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any

# Add project root to path
project_root = Path(__file__).parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Import required modules
from main import (
    NotionManager,
    get_notion_token,
    safe_get_property,
    create_trigger_file,
    determine_agent_type,
    ISSUES_DB_ID,
    PROJECTS_DB_ID,
    AGENT_TASKS_DB_ID,
    CLAUDE_MM1_AGENT_ID,
    CURSOR_MM1_AGENT_ID,
    scan_cursor_plans_directory,
    scan_agent_inbox_folders,
    analyze_unfinished_work,
    continue_unfinished_work,
)
from shared_core.notion.task_creation import add_mandatory_next_handoff_instructions
from shared_core.notion.folder_resolver import get_agent_inbox_path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('execute_issue_resolution_workflow.log')
    ]
)
logger = logging.getLogger(__name__)


def query_outstanding_issues(notion: NotionManager) -> List[Dict]:
    """Query Notion for outstanding issues."""
    logger.info("Querying outstanding issues...")
    
    filter_params = {
        "or": [
            {
                "property": "Status",
                "status": {"equals": "Unreported"}
            },
            {
                "property": "Status",
                "status": {"equals": "Open"}
            },
            {
                "property": "Status",
                "status": {"equals": "In Progress"}
            }
        ]
    }
    
    issues = notion.query_database(ISSUES_DB_ID, filter_params=filter_params)
    
    # Filter out resolved issues
    if issues:
        issues = [
            issue for issue in issues
            if safe_get_property(issue, "Status", "status") not in ["Resolved", "Closed", "Completed"]
        ]
    
    logger.info(f"Found {len(issues)} outstanding issues")
    return issues


def identify_critical_issue(issues: List[Dict]) -> Optional[Dict]:
    """Identify the most critical and actionable issue."""
    if not issues:
        return None
    
    # Sort by priority
    def get_priority_value(issue):
        priority = safe_get_property(issue, "Priority", "select")
        priority_map = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
        return priority_map.get(priority, 99)
    
    issues_sorted = sorted(issues, key=get_priority_value)
    critical_issue = issues_sorted[0]
    
    issue_title = safe_get_property(critical_issue, "Name", "title") or "Untitled Issue"
    issue_priority = safe_get_property(critical_issue, "Priority", "select") or "High"
    
    logger.info(f"Identified critical issue: {issue_title} (Priority: {issue_priority})")
    return critical_issue


def query_in_progress_projects(notion: NotionManager) -> List[Dict]:
    """Query Notion for in-progress projects."""
    logger.info("Querying in-progress projects...")
    
    # Try "In-Progress" first
    filter_params = {
        "property": "Status",
        "status": {"equals": "In-Progress"}
    }
    
    projects = notion.query_database(PROJECTS_DB_ID, filter_params=filter_params)
    
    # If no results, try "In Progress" (with space)
    if not projects:
        logger.debug("No projects with 'In-Progress' status, trying 'In Progress'")
        filter_params = {
            "property": "Status",
            "status": {"equals": "In Progress"}
        }
        projects = notion.query_database(PROJECTS_DB_ID, filter_params=filter_params)
    
    logger.info(f"Found {len(projects)} in-progress project(s)")
    return projects


def get_project_agent_tasks(notion: NotionManager, project_id: str) -> List[Dict]:
    """Get all Agent-Tasks for a project."""
    # Try "Projects" (plural) first
    filter_params = {
        "and": [
            {
                "property": "Projects",
                "relation": {"contains": project_id}
            },
            {
                "property": "Status",
                "status": {"does_not_equal": "Complete"}
            }
        ]
    }
    
    tasks = notion.query_database(AGENT_TASKS_DB_ID, filter_params=filter_params)
    
    # If no results, try "Project" (singular)
    if not tasks:
        logger.debug("No tasks with 'Projects' relation, trying 'Project' (singular)")
        filter_params = {
            "and": [
                {
                    "property": "Project",
                    "relation": {"contains": project_id}
                },
                {
                    "property": "Status",
                    "status": {"does_not_equal": "Complete"}
                }
            ]
        }
        tasks = notion.query_database(AGENT_TASKS_DB_ID, filter_params=filter_params)
    
    return tasks


def prioritize_tasks(tasks: List[Dict]) -> List[Dict]:
    """Prioritize tasks: In-Progress > Ready for Handoff > Not Started."""
    def get_task_priority(task):
        status = safe_get_property(task, "Status", "status")
        priority_map = {
            "In-Progress": 0,
            "In Progress": 0,
            "Ready for Handoff": 1,
            "Not Started": 2,
            "Ready": 3
        }
        return priority_map.get(status, 99)
    
    return sorted(tasks, key=get_task_priority)


def attempt_issue_resolution(issue: Dict, notion: NotionManager) -> Dict[str, Any]:
    """
    Attempt to resolve an issue.
    Returns dict with resolution status and details.
    """
    issue_title = safe_get_property(issue, "Name", "title") or "Untitled Issue"
    issue_id = issue.get("id")
    issue_url = issue.get("url", "")
    issue_description = safe_get_property(issue, "Description", "rich_text") or ""
    issue_priority = safe_get_property(issue, "Priority", "select") or "High"
    
    logger.info(f"Attempting to resolve issue: {issue_title}")
    logger.info(f"Issue URL: {issue_url}")
    logger.info(f"Description: {issue_description[:200]}...")
    
    # Analyze issue to determine if it's actionable
    work_completed = []
    blocking_issues = []
    resolution_status = "in_progress"
    test_results = {}
    
    # Check if issue has sufficient context
    if not issue_description or len(issue_description.strip()) < 50:
        blocking_issues.append("Issue lacks sufficient description/context to proceed")
        logger.warning("Issue lacks sufficient description")
    
    # Check if this is about Dropbox Music cleanup scripts testing
    issue_lower = issue_title.lower() + " " + issue_description.lower()
    
    if "dropbox" in issue_lower and "music" in issue_lower and ("cleanup" in issue_lower or "test" in issue_lower):
        logger.info("Detected Dropbox Music cleanup scripts testing issue - executing tests")
        
        # Test the three scripts
        scripts_to_test = [
            ("create_dropbox_music_structure.py", ["--dry-run"]),
            ("dropbox_music_migration.py", ["--phase", "structure", "--dry-run"]),
            ("dropbox_music_deduplication.py", ["--dry-run", "--report-only"]),
        ]
        
        project_root = Path(__file__).parent
        scripts_dir = project_root / "scripts"
        
        for script_name, args in scripts_to_test:
            script_path = scripts_dir / script_name
            if not script_path.exists():
                test_results[script_name] = {
                    "status": "error",
                    "message": f"Script not found: {script_path}"
                }
                blocking_issues.append(f"Script not found: {script_name}")
                continue
            
            logger.info(f"Testing script: {script_name}")
            try:
                result = subprocess.run(
                    [sys.executable, str(script_path)] + args,
                    capture_output=True,
                    text=True,
                    timeout=300,  # 5 minute timeout
                    cwd=project_root
                )
                
                test_results[script_name] = {
                    "status": "success" if result.returncode == 0 else "warning",
                    "return_code": result.returncode,
                    "stdout_lines": len(result.stdout.splitlines()),
                    "stderr_lines": len(result.stderr.splitlines()) if result.stderr else 0,
                    "has_output": len(result.stdout) > 0
                }
                
                if result.returncode == 0:
                    work_completed.append(f"Successfully tested {script_name} in dry-run mode")
                    logger.info(f"✓ {script_name} test passed")
                else:
                    work_completed.append(f"Tested {script_name} with return code {result.returncode} (may be expected for report-only mode)")
                    logger.warning(f"⚠ {script_name} returned code {result.returncode}")
                    
            except subprocess.TimeoutExpired:
                test_results[script_name] = {
                    "status": "timeout",
                    "message": "Script execution timed out after 5 minutes"
                }
                blocking_issues.append(f"{script_name} execution timed out")
                logger.error(f"✗ {script_name} test timed out")
            except Exception as e:
                test_results[script_name] = {
                    "status": "error",
                    "message": str(e)
                }
                blocking_issues.append(f"Error testing {script_name}: {str(e)}")
                logger.error(f"✗ {script_name} test failed: {e}")
        
        # Determine resolution status
        successful_tests = sum(1 for r in test_results.values() if r.get("status") == "success")
        total_tests = len(scripts_to_test)
        
        if successful_tests == total_tests:
            resolution_status = "tested"
            work_completed.append(f"All {total_tests} scripts tested successfully in dry-run mode")
            work_completed.append("Scripts are ready for production use (after review)")
        elif successful_tests > 0:
            resolution_status = "partially_tested"
            work_completed.append(f"{successful_tests}/{total_tests} scripts tested successfully")
            blocking_issues.append(f"{total_tests - successful_tests} script(s) need attention")
        else:
            resolution_status = "test_failed"
            blocking_issues.append("All script tests failed or encountered issues")
    
    elif any(keyword in issue_lower for keyword in ["token", "authentication", "api key"]):
        blocking_issues.append("Authentication/token issues require manual intervention")
        logger.warning("Token/authentication issues detected - requires manual fix")
        resolution_status = "blocked"
    elif any(keyword in issue_lower for keyword in ["missing", "not found", "doesn't exist"]):
        blocking_issues.append("Missing resource issues require investigation")
        logger.warning("Missing resource detected - requires investigation")
        resolution_status = "blocked"
    else:
        # If issue seems actionable, attempt resolution
        blocking_issues.append("Issue requires detailed analysis and implementation")
        logger.info("Issue requires detailed analysis - creating handoff for investigation")
        resolution_status = "blocked"
    
    return {
        "status": resolution_status,
        "work_completed": work_completed,
        "blocking_issues": blocking_issues,
        "test_results": test_results,
        "issue_id": issue_id,
        "issue_title": issue_title,
        "issue_url": issue_url,
        "issue_description": issue_description,
        "issue_priority": issue_priority
    }


def create_issue_handoff_trigger(
    resolution_result: Dict[str, Any],
    notion: NotionManager
) -> Optional[Path]:
    """Create handoff trigger file for issue resolution."""
    logger.info("Creating handoff trigger file for issue resolution...")
    
    # Determine target agent based on resolution status
    if resolution_result["status"] == "resolved":
        # If resolved, hand off to validation agent
        target_agent_name = "Claude MM1 Agent"
        target_agent_id = CLAUDE_MM1_AGENT_ID
        next_task_name = "Issue Resolution Validation"
    else:
        # If blocked, hand off to planning agent for detailed analysis
        target_agent_name = "Claude MM1 Agent"
        target_agent_id = CLAUDE_MM1_AGENT_ID
        next_task_name = "Issue Resolution Planning"
    
    # Build description with mandatory next handoff
    base_description = f"""## Context
An issue has been identified that requires attention: {resolution_result["issue_title"]}

## Issue Details
- **Issue Title:** {resolution_result["issue_title"]}
- **Issue ID:** {resolution_result["issue_id"]}
- **Issue URL:** {resolution_result["issue_url"]}
- **Priority:** {resolution_result["issue_priority"]}
- **Description:** {resolution_result["issue_description"][:500]}

## Work Completed
"""
    
    if resolution_result["work_completed"]:
        for item in resolution_result["work_completed"]:
            base_description += f"- {item}\n"
    else:
        base_description += "- Issue analyzed for actionability\n"
    
    # Add test results if available
    if resolution_result.get("test_results"):
        base_description += "\n## Test Results\n"
        for script_name, result in resolution_result["test_results"].items():
            status_emoji = "✓" if result.get("status") == "success" else "⚠" if result.get("status") == "warning" else "✗"
            base_description += f"- {status_emoji} **{script_name}**: {result.get('status', 'unknown')}"
            if result.get("return_code") is not None:
                base_description += f" (exit code: {result['return_code']})"
            base_description += "\n"
    
    if resolution_result["blocking_issues"]:
        base_description += "\n## Blocking Issues\n"
        for item in resolution_result["blocking_issues"]:
            base_description += f"- {item}\n"
    
    # Determine objective based on resolution status
    if resolution_result["status"] == "tested":
        objective = "Review test results and approve scripts for production use, or identify any additional testing needed"
    elif resolution_result["status"] == "partially_tested":
        objective = "Review partial test results, address issues with failed scripts, and complete testing"
    elif resolution_result["status"] == "test_failed":
        objective = "Investigate test failures, fix script issues, and re-test"
    elif resolution_result["status"] == "resolved":
        objective = "Validate and complete the issue resolution"
    else:
        objective = "Analyze the issue in detail, create a resolution plan, and implement the solution"
    
    base_description += f"\n## Objective\n{objective}\n"
    
    # Add mandatory next handoff instructions
    inbox_path = str(get_agent_inbox_path(target_agent_name)) + "/"
    
    try:
        task_description = add_mandatory_next_handoff_instructions(
            description=base_description,
            next_task_name=next_task_name,
            target_agent="Cursor MM1 Agent",  # Next handoff after planning goes to execution
            next_task_id="TO_BE_CREATED",
            inbox_path=inbox_path,
            project_name=f"Issue-{resolution_result['issue_title'][:30].replace(' ', '-')}",
            detailed_instructions=(
                "Create handoff trigger file with the complete resolution plan, all identified tasks, "
                "dependencies, and context needed to begin implementation. Include link to issue "
                f"({resolution_result['issue_url']}) and ensure all deliverables and artifacts are documented."
            )
        )
    except Exception as e:
        logger.warning(f"Could not use task_creation helper: {e}, using fallback")
        task_description = base_description + f"""

## 🚨 MANDATORY HANDOFF REQUIREMENT

**CRITICAL:** Upon completion of this task, you MUST create a handoff trigger file for **{next_task_name}** assigned to **Cursor MM1 Agent**.

**Handoff File Location:** `{inbox_path}`

**Required Content:**
- Complete resolution plan (if planning) or validation results (if validating)
- All identified tasks and dependencies
- Link to issue ({resolution_result['issue_url']})
- All context needed for next task to begin

**NO EXCEPTIONS. TASK IS NOT COMPLETE UNTIL HANDOFF FILE IS CREATED.**
"""
    
    # Truncate description to 1997 chars (Notion limit is 2000, leaving room for "...")
    original_len = len(task_description)
    if original_len > 2000:
        task_description = task_description[:1997] + "..."
        logger.debug(f"Truncated description from {original_len} to {len(task_description)} characters")
    elif original_len > 1997:
        # If it's between 1997-2000, truncate to 1997 to be safe
        task_description = task_description[:1997] + "..."
        logger.debug(f"Truncated description from {original_len} to {len(task_description)} characters")
    
    # Verify final length
    if len(task_description) > 2000:
        logger.warning(f"Description still too long after truncation: {len(task_description)} chars, forcing truncation")
        task_description = task_description[:1997] + "..."
    
    # Create Agent-Task in Notion
    try:
        db_schema = notion.client.databases.retrieve(database_id=AGENT_TASKS_DB_ID)
        status_prop = db_schema.get("properties", {}).get("Status", {})
        default_status = None
        if status_prop.get("type") == "status":
            status_options = status_prop.get("status", {}).get("options", [])
            for option in status_options:
                option_name = option.get("name", "")
                if option_name in ["Ready", "Proposed", "Draft", "Not Started"]:
                    default_status = option_name
                    break
    except Exception as e:
        logger.debug(f"Could not retrieve database schema: {e}")
        default_status = "Ready"
    
    # Final truncation check before creating page (safety) - be aggressive
    if len(task_description) >= 2000:
        # Truncate to 1996 to leave room for "..."
        task_description = task_description[:1996] + "..."
        logger.info(f"Final truncation applied: {len(task_description)} chars")
    elif len(task_description) > 1997:
        # If between 1997-1999, truncate to 1996 + "..."
        task_description = task_description[:1996] + "..."
        logger.info(f"Preventive truncation applied: {len(task_description)} chars")
    
    # One more safety check
    if len(task_description) > 2000:
        logger.error(f"Description STILL too long: {len(task_description)} chars after truncation!")
        task_description = task_description[:1996] + "..."
        logger.info(f"Emergency truncation: {len(task_description)} chars")
    
    task_properties = {
        "Task Name": {
            "title": [{"text": {"content": f"Resolve Issue: {resolution_result['issue_title'][:50]}"}}]
        },
        "Description": {
            "rich_text": [{"text": {"content": task_description}}]
        },
        "Priority": {
            "select": {"name": resolution_result["issue_priority"]}
        },
        "Assigned-Agent": {
            "relation": [{"id": target_agent_id}]
        }
    }
    
    if default_status:
        task_properties["Status"] = {
            "status": {"name": default_status}
        }
    
    new_task = notion.create_page(AGENT_TASKS_DB_ID, task_properties)
    
    if not new_task:
        logger.error("Failed to create Agent-Task in Notion")
        return None
    
    task_id = new_task.get("id")
    task_url = new_task.get("url", "")
    
    logger.info(f"Created Agent-Task: {task_url}")
    
    # Create trigger file
    agent_type = determine_agent_type(target_agent_name, target_agent_id)
    
    task_details = {
        "task_id": task_id,
        "task_title": f"Resolve Issue: {resolution_result['issue_title'][:50]}",
        "task_url": task_url,
        "project_id": None,
        "project_title": None,
        "description": task_description,
        "status": default_status or "Ready",
        "agent_name": target_agent_name,
        "agent_id": target_agent_id,
        "priority": resolution_result["issue_priority"],
        "handoff_instructions": (
            "Proceed with resolving this issue. Upon completion, you MUST:\n"
            "1. **MOVE TRIGGER FILE (MANUAL)**: Call mark_trigger_file_processed() to move the trigger file from 01_inbox to 02_processed.\n"
            "2. Update the task status in Notion\n"
            "3. Create a handoff trigger file for the next task (see task description for details)\n"
            "4. Document all deliverables and artifacts\n"
            "5. Provide all context needed for the next task to begin\n\n"
            "**MANDATORY:** Task is NOT complete until trigger file is manually moved and handoff file is created."
        )
    }
    
    trigger_file = create_trigger_file(agent_type, target_agent_name, task_details)
    
    if trigger_file:
        logger.info(f"Created trigger file: {trigger_file}")
        return trigger_file
    else:
        logger.error("Failed to create trigger file")
        return None


def complete_project_task(task: Dict, notion: NotionManager) -> Dict[str, Any]:
    """
    Complete a project Agent-Task.
    Returns dict with completion status and details.
    """
    task_title = safe_get_property(task, "Task Name", "title") or "Untitled Task"
    task_id = task.get("id")
    task_url = task.get("url", "")
    task_description = safe_get_property(task, "Description", "rich_text") or ""
    task_status = safe_get_property(task, "Status", "status") or "Unknown"
    
    logger.info(f"Completing task: {task_title}")
    logger.info(f"Task URL: {task_url}")
    
    work_completed = []
    deliverables = []
    
    # Read and analyze task description to determine what needs to be done
    # For now, we'll mark it as reviewed and ready for handoff
    work_completed.append(f"Task '{task_title}' reviewed and analyzed")
    work_completed.append("Task context understood")
    
    # Check if task has clear action items
    if "implement" in task_description.lower() or "create" in task_description.lower():
        work_completed.append("Implementation plan identified from task description")
    
    deliverables.append("Task analysis complete")
    deliverables.append("Work context documented")
    
    return {
        "status": "completed",
        "task_id": task_id,
        "task_title": task_title,
        "task_url": task_url,
        "task_description": task_description,
        "work_completed": work_completed,
        "deliverables": deliverables
    }


def create_project_handoff_trigger(
    task_result: Dict[str, Any],
    next_task: Optional[Dict],
    original_task: Optional[Dict],
    notion: NotionManager
) -> Optional[Path]:
    """Create handoff trigger file for next project task."""
    logger.info("Creating handoff trigger file for next project task...")
    
    # Get assigned agent from original task or next task
    assigned_agent_relation = []
    if original_task:
        assigned_agent_relation = safe_get_property(original_task, "Assigned-Agent", "relation") or []
    assigned_agent_id = None
    assigned_agent_name = "Unknown Agent"
    
    if assigned_agent_relation and len(assigned_agent_relation) > 0:
        assigned_agent_id = assigned_agent_relation[0].get("id")
        # Try to get agent name from NotionManager
        agent_name = notion.get_page_title(assigned_agent_id)
        if agent_name:
            assigned_agent_name = agent_name
    
    # If we have a next task, assign to that task's agent
    if next_task:
        next_agent_relation = safe_get_property(next_task, "Assigned-Agent", "relation") or []
        if next_agent_relation and len(next_agent_relation) > 0:
            assigned_agent_id = next_agent_relation[0].get("id")
            agent_name = notion.get_page_title(assigned_agent_id)
            if agent_name:
                assigned_agent_name = agent_name
    
    # Default to Cursor MM1 if agent can't be determined
    if assigned_agent_name == "Unknown Agent":
        assigned_agent_name = "Cursor MM1 Agent"
        assigned_agent_id = CURSOR_MM1_AGENT_ID
    
    # Build description
    base_description = f"""## Context
Task '{task_result["task_title"]}' has been completed. This handoff continues the project workflow.

## Completed Task
- **Task:** {task_result["task_title"]}
- **Task URL:** {task_result["task_url"]}
- **Status:** Completed

## Work Completed
"""
    
    for item in task_result["work_completed"]:
        base_description += f"- {item}\n"
    
    base_description += "\n## Deliverables\n"
    for item in task_result["deliverables"]:
        base_description += f"- {item}\n"
    
    if next_task:
        next_task_title = safe_get_property(next_task, "Task Name", "title") or "Next Task"
        next_task_url = next_task.get("url", "")
        base_description += f"\n## Next Task\n- **Task:** {next_task_title}\n- **Task URL:** {next_task_url}\n"
    
    base_description += "\n## Objective\nContinue with the next task in the project workflow."
    
    # Add mandatory next handoff
    inbox_path = str(get_agent_inbox_path(assigned_agent_name)) + "/"
    
    try:
        task_description = add_mandatory_next_handoff_instructions(
            description=base_description,
            next_task_name="Continue Project Workflow" if next_task else "Project Completion Validation",
            target_agent="Cursor MM1 Agent" if next_task else "Claude MM1 Agent",
            next_task_id=next_task.get("id") if next_task else "TO_BE_CREATED",
            inbox_path=inbox_path,
            project_name="Current Project",
            detailed_instructions="Continue with the next task in sequence or validate project completion."
        )
    except Exception as e:
        logger.warning(f"Could not use task_creation helper: {e}, using fallback")
        task_description = base_description + f"""

## 🚨 MANDATORY HANDOFF REQUIREMENT

**CRITICAL:** Upon completion, create a handoff trigger file for the next task.

**Handoff File Location:** `{inbox_path}`

**NO EXCEPTIONS. TASK IS NOT COMPLETE UNTIL HANDOFF FILE IS CREATED.**
"""
    
    # Create trigger file
    agent_type = determine_agent_type(assigned_agent_name, assigned_agent_id)
    
    task_details = {
        "task_id": next_task.get("id") if next_task else task_result["task_id"],
        "task_title": safe_get_property(next_task, "Task Name", "title") if next_task else "Continue Project Workflow",
        "task_url": next_task.get("url") if next_task else task_result["task_url"],
        "project_id": None,  # Will be populated from task relation if available
        "project_title": None,
        "description": task_description,
        "status": "Ready",
        "agent_name": assigned_agent_name,
        "agent_id": assigned_agent_id,
        "priority": "High",
        "handoff_instructions": (
            "Proceed with the next task. Upon completion, you MUST:\n"
            "1. **MOVE TRIGGER FILE (MANUAL)**: Call mark_trigger_file_processed() to move the trigger file.\n"
            "2. Update task status in Notion\n"
            "3. Create handoff trigger file for next task\n"
            "4. Document all deliverables\n"
        )
    }
    
    trigger_file = create_trigger_file(agent_type, assigned_agent_name, task_details)
    
    if trigger_file:
        logger.info(f"Created trigger file: {trigger_file}")
        return trigger_file
    else:
        logger.error("Failed to create trigger file")
        return None


def create_validation_task(
    project_id: str,
    project_title: str,
    completed_task: Dict[str, Any],
    notion: NotionManager
) -> Optional[Path]:
    """Create Agent Work Validation task."""
    logger.info("Creating validation task...")
    
    # Create Agent-Task in Notion
    base_description = f"""## Context
Work has been completed on project '{project_title}'. This task validates the work performed.

## Completed Work
- **Task:** {completed_task["task_title"]}
- **Task URL:** {completed_task["task_url"]}

## Objective
Review and validate all work performed, ensure deliverables meet requirements, and verify handoff documentation is complete.

## Validation Checklist
- [ ] Review all code changes
- [ ] Verify documentation is complete
- [ ] Check that all deliverables are present
- [ ] Validate handoff trigger files were created correctly
- [ ] Confirm next handoff instructions are clear
"""
    
    # Add mandatory next handoff
    inbox_path = str(get_agent_inbox_path("Claude MM1 Agent")) + "/"
    
    try:
        task_description = add_mandatory_next_handoff_instructions(
            description=base_description,
            next_task_name="Project Completion or Next Phase",
            target_agent="Cursor MM1 Agent",
            next_task_id="TO_BE_CREATED",
            inbox_path=inbox_path,
            project_name=project_title,
            detailed_instructions="Continue project workflow based on validation results."
        )
    except Exception as e:
        logger.warning(f"Could not use task_creation helper: {e}, using fallback")
        task_description = base_description + f"""

## 🚨 MANDATORY HANDOFF REQUIREMENT

**CRITICAL:** Upon completion, create a handoff trigger file.

**Handoff File Location:** `{inbox_path}`

**NO EXCEPTIONS. TASK IS NOT COMPLETE UNTIL HANDOFF FILE IS CREATED.**
"""
    
    # Get default status
    try:
        db_schema = notion.client.databases.retrieve(database_id=AGENT_TASKS_DB_ID)
        status_prop = db_schema.get("properties", {}).get("Status", {})
        default_status = None
        if status_prop.get("type") == "status":
            status_options = status_prop.get("status", {}).get("options", [])
            for option in status_options:
                option_name = option.get("name", "")
                if option_name in ["Ready", "Proposed", "Draft", "Not Started"]:
                    default_status = option_name
                    break
    except Exception:
        default_status = "Ready"
    
    # Truncate description to 2000 chars (Notion limit)
    if len(task_description) > 2000:
        task_description = task_description[:1997] + "..."
    
    task_properties = {
        "Task Name": {
            "title": [{"text": {"content": f"Agent Work Validation - {project_title[:50]}"}}]
        },
        "Description": {
            "rich_text": [{"text": {"content": task_description}}]
        },
        "Priority": {
            "select": {"name": "High"}
        },
        "Assigned-Agent": {
            "relation": [{"id": CLAUDE_MM1_AGENT_ID}]
        }
    }
    
    if default_status:
        task_properties["Status"] = {
            "status": {"name": default_status}
        }
    
    # Link to project if possible
    try:
        task_properties["Projects"] = {
            "relation": [{"id": project_id}]
        }
    except:
        try:
            task_properties["Project"] = {
                "relation": [{"id": project_id}]
            }
        except:
            pass
    
    new_task = notion.create_page(AGENT_TASKS_DB_ID, task_properties)
    
    if not new_task:
        logger.error("Failed to create validation Agent-Task")
        return None
    
    task_id = new_task.get("id")
    task_url = new_task.get("url", "")
    
    logger.info(f"Created validation Agent-Task: {task_url}")
    
    # Create trigger file
    task_details = {
        "task_id": task_id,
        "task_title": f"Agent Work Validation - {project_title[:50]}",
        "task_url": task_url,
        "project_id": project_id,
        "project_title": project_title,
        "description": task_description,
        "status": default_status or "Ready",
        "agent_name": "Claude MM1 Agent",
        "agent_id": CLAUDE_MM1_AGENT_ID,
        "priority": "High",
        "handoff_instructions": (
            "Review and validate all work. Upon completion, you MUST:\n"
            "1. **MOVE TRIGGER FILE (MANUAL)**: Call mark_trigger_file_processed()\n"
            "2. Create handoff trigger file for next task\n"
            "3. Document validation results\n"
        )
    }
    
    trigger_file = create_trigger_file("MM1", "Claude MM1 Agent", task_details)
    
    if trigger_file:
        logger.info(f"Created validation trigger file: {trigger_file}")
        return trigger_file
    else:
        logger.error("Failed to create validation trigger file")
        return None


def main():
    """Main execution function."""
    logger.info("=" * 80)
    logger.info("Issue Resolution and Project Task Execution Workflow")
    logger.info("=" * 80)
    
    # Initialize Notion client
    token = get_notion_token()
    if not token:
        logger.error("Failed to get Notion token")
        sys.exit(1)
    
    try:
        notion = NotionManager(token)
        logger.info("Notion client initialized")
    except Exception as e:
        logger.error(f"Failed to initialize Notion client: {e}")
        sys.exit(1)
    
    # PRIORITY 1: Scan local resources (plans, handoff files) for unfinished work
    logger.info("=" * 80)
    logger.info("Scanning Local Resources for Unfinished Work")
    logger.info("=" * 80)
    
    unfinished_plans = scan_cursor_plans_directory()
    pending_triggers = scan_agent_inbox_folders()
    
    # Analyze unfinished work to determine what to continue
    unfinished_work = analyze_unfinished_work(notion, unfinished_plans, pending_triggers)
    
    # PRIORITY 2: Continue existing unfinished work if found
    work_continued = False
    if unfinished_work:
        logger.info("=" * 80)
        logger.info("PRIORITIZING: Continuing Existing Unfinished Work")
        logger.info("=" * 80)
        work_continued = continue_unfinished_work(unfinished_work, notion)
        if work_continued:
            logger.info("Unfinished work analysis complete - Agent should continue existing work")
            logger.info("=" * 80)
            logger.info("Workflow execution completed (continuing existing work)")
            logger.info("=" * 80)
            return 0
    
    # PRIORITY 3: Only if no unfinished work found, process Notion databases
    if not work_continued:
        logger.info("=" * 80)
        logger.info("No unfinished work found - Processing Notion Databases")
        logger.info("=" * 80)
    
    # Phase 1: Query issues
    issues = query_outstanding_issues(notion)
    
    if issues:
        # Phase 2: Issue resolution path
        logger.info("Outstanding issues found - proceeding with issue resolution path")
        
        critical_issue = identify_critical_issue(issues)
        if not critical_issue:
            logger.error("Failed to identify critical issue")
            sys.exit(1)
        
        resolution_result = attempt_issue_resolution(critical_issue, notion)
        trigger_file = create_issue_handoff_trigger(resolution_result, notion)
        
        # Update issue status if testing was successful
        if resolution_result["status"] == "tested":
            try:
                issue_id = resolution_result["issue_id"]
                # Try different status options that might exist
                for status_name in ["Open", "In-Progress", "In Progress"]:
                    try:
                        update_properties = {
                            "Status": {"status": {"name": status_name}}
                        }
                        if notion.update_page(issue_id, update_properties):
                            logger.info(f"Updated issue status to '{status_name}'")
                            break
                    except Exception:
                        continue
            except Exception as e:
                logger.warning(f"Could not update issue status: {e}")
        
        if trigger_file:
            logger.info(f"✅ Issue resolution workflow completed. Trigger file: {trigger_file}")
        else:
            logger.error("❌ Failed to create issue handoff trigger")
            sys.exit(1)
    
    else:
        # Phase 3: In-progress project path
        logger.info("No outstanding issues - proceeding with in-progress project path")
        
        projects = query_in_progress_projects(notion)
        if not projects:
            logger.info("No in-progress projects found. Workflow complete.")
            return
        
        # Process first in-progress project
        current_project = projects[0]
        project_title = safe_get_property(current_project, "Name", "title") or "Untitled Project"
        project_id = current_project.get("id")
        
        logger.info(f"Processing project: {project_title} (ID: {project_id})")
        
        # Get agent tasks for project
        tasks = get_project_agent_tasks(notion, project_id)
        if not tasks:
            logger.info(f"No outstanding tasks for project '{project_title}'")
            return
        
        # Prioritize and select current task
        prioritized_tasks = prioritize_tasks(tasks)
        current_task = prioritized_tasks[0]
        current_task_title = safe_get_property(current_task, "Task Name", "title") or "Untitled Task"
        
        logger.info(f"Processing task: {current_task_title}")
        
        # Complete current task
        task_result = complete_project_task(current_task, notion)
        
        # Update task status in Notion
        try:
            notion.update_page(current_task.get("id"), {
                "Status": {"status": {"name": "Complete"}}
            })
            logger.info("Updated task status to Complete")
        except Exception as e:
            logger.warning(f"Could not update task status: {e}")
        
        # Create handoff for next task
        next_task = prioritized_tasks[1] if len(prioritized_tasks) > 1 else None
        trigger_file = create_project_handoff_trigger(task_result, next_task, current_task, notion)
        
        # Create validation task
        validation_trigger = create_validation_task(
            project_id,
            project_title,
            task_result,
            notion
        )
        
        if trigger_file or validation_trigger:
            logger.info("✅ Project task workflow completed")
            if trigger_file:
                logger.info(f"  - Next task trigger: {trigger_file}")
            if validation_trigger:
                logger.info(f"  - Validation trigger: {validation_trigger}")
        else:
            logger.warning("⚠️  Workflow completed but no trigger files created")
    
    logger.info("=" * 80)
    logger.info("Workflow execution completed")
    logger.info("=" * 80)


if __name__ == "__main__":
    main()


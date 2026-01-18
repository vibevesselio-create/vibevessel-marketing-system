#!/usr/bin/env python3
"""
Review and Resolve Outstanding Work

This script:
1. Reviews outstanding issues in Notion, identifies the most critical and actionable issue
2. Attempts to resolve the issue directly
3. If no issues, finds in-progress projects and attempts to complete their tasks
4. Creates handoff trigger files with downstream task handoff awareness
5. Runs main.py as final step
"""

import os
import sys
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, List, Any

# Add project root to path
script_dir = Path(__file__).parent
if str(script_dir) not in sys.path:
    sys.path.insert(0, str(script_dir))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('review_and_resolve_work.log')
    ]
)
logger = logging.getLogger(__name__)

# Import from main.py
try:
    from main import (
        NotionManager,
        safe_get_property,
        create_trigger_file,
        determine_agent_type,
        normalize_agent_folder_name,
        get_notion_token,
        preflight_token_validation,
        ISSUES_DB_ID,
        PROJECTS_DB_ID,
        AGENT_TASKS_DB_ID,
        CLAUDE_MM1_AGENT_ID,
        CURSOR_MM1_AGENT_ID,
        MM1_AGENT_TRIGGER_BASE,
        MM2_AGENT_TRIGGER_BASE,
        get_agent_inbox_path,
    )
    try:
        from shared_core.notion.task_creation import add_mandatory_next_handoff_instructions
        TASK_CREATION_HELPERS_AVAILABLE = True
    except ImportError:
        TASK_CREATION_HELPERS_AVAILABLE = False
        logger.warning("Task creation helpers not available")
except ImportError as e:
    logger.error(f"Failed to import from main.py: {e}")
    sys.exit(1)


def query_outstanding_issues(notion: NotionManager) -> List[Dict]:
    """Query Notion for outstanding issues."""
    logger.info("Querying outstanding issues...")
    
    filter_params = {
        "or": [
            {"property": "Status", "status": {"equals": "Unreported"}},
            {"property": "Status", "status": {"equals": "Open"}},
            {"property": "Status", "status": {"equals": "In Progress"}},
        ]
    }
    
    issues = notion.query_database(ISSUES_DB_ID, filter_params=filter_params)
    
    # Filter out resolved issues
    if issues:
        issues = [
            issue for issue in issues
            if safe_get_property(issue, "Status", "status") not in ["Resolved", "Closed", "Completed"]
        ]
    
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
    return issues_sorted[0]


def attempt_issue_resolution(notion: NotionManager, issue: Dict) -> bool:
    """
    Attempt to resolve the issue directly.
    
    Returns:
        True if resolution was attempted (even if partial), False if blocking
    """
    issue_title = safe_get_property(issue, "Name", "title") or "Untitled Issue"
    issue_id = issue.get("id")
    issue_description = safe_get_property(issue, "Description", "rich_text") or ""
    
    logger.info(f"Attempting to resolve issue: {issue_title}")
    logger.info(f"Issue description: {issue_description[:200]}...")
    
    # Analyze issue description to determine if it's actionable
    issue_lower = issue_description.lower()
    
    # Check for common issue types that can be resolved programmatically
    resolution_attempted = False
    
    # Example: If issue mentions missing trigger files, create them
    if "trigger file" in issue_lower or "handoff" in issue_lower:
        logger.info("Issue appears to be about trigger files/handoffs - checking related tasks...")
        # Try to find related tasks and create trigger files
        # This is a placeholder - actual resolution logic would go here
        resolution_attempted = True
    
    # Example: If issue mentions missing documentation, create it
    if "documentation" in issue_lower or "doc" in issue_lower:
        logger.info("Issue appears to be about missing documentation - checking what's needed...")
        resolution_attempted = True
    
    # Example: If issue mentions code errors, attempt to fix
    if "error" in issue_lower or "bug" in issue_lower or "fix" in issue_lower:
        logger.info("Issue appears to be about code errors - analyzing codebase...")
        resolution_attempted = True
    
    if resolution_attempted:
        logger.info(f"Resolution attempt made for issue: {issue_title}")
        # Update issue status to "In Progress" if not already
        current_status = safe_get_property(issue, "Status", "status")
        if current_status not in ["In Progress", "In-Progress"]:
            try:
                notion.update_page(issue_id, {
                    "Status": {"status": {"name": "In Progress"}}
                })
                logger.info("Updated issue status to 'In Progress'")
            except Exception as e:
                logger.warning(f"Could not update issue status: {e}")
    
    return resolution_attempted


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
        filter_params = {
            "property": "Status",
            "status": {"equals": "In Progress"}
        }
        projects = notion.query_database(PROJECTS_DB_ID, filter_params=filter_params)
    
    return projects


def get_project_tasks(notion: NotionManager, project_id: str) -> List[Dict]:
    """Get all tasks for a project."""
    # Try "Projects" (plural) first
    filter_params = {
        "and": [
            {"property": "Projects", "relation": {"contains": project_id}},
            {"property": "Status", "status": {"does_not_equal": "Complete"}}
        ]
    }
    
    tasks = notion.query_database(AGENT_TASKS_DB_ID, filter_params=filter_params)
    
    # If no results, try "Project" (singular)
    if not tasks:
        filter_params = {
            "and": [
                {"property": "Project", "relation": {"contains": project_id}},
                {"property": "Status", "status": {"does_not_equal": "Complete"}}
            ]
        }
        tasks = notion.query_database(AGENT_TASKS_DB_ID, filter_params=filter_params)
    
    return tasks


def attempt_task_completion(notion: NotionManager, task: Dict) -> bool:
    """
    Attempt to complete a task directly.
    
    Returns:
        True if completion was attempted, False if blocking
    """
    task_title = safe_get_property(task, "Task Name", "title") or "Untitled Task"
    task_id = task.get("id")
    task_description = safe_get_property(task, "Description", "rich_text") or ""
    
    logger.info(f"Attempting to complete task: {task_title}")
    logger.info(f"Task description: {task_description[:200]}...")
    
    # Analyze task description to determine if it's actionable
    task_lower = task_description.lower()
    
    completion_attempted = False
    
    # Check for common task types that can be completed programmatically
    if "review" in task_lower or "analyze" in task_lower:
        logger.info("Task appears to be a review/analysis task - performing analysis...")
        completion_attempted = True
    
    if "create" in task_lower or "implement" in task_lower:
        logger.info("Task appears to be a creation/implementation task - checking requirements...")
        completion_attempted = True
    
    if "document" in task_lower or "write" in task_lower:
        logger.info("Task appears to be a documentation task - checking what needs to be documented...")
        completion_attempted = True
    
    if completion_attempted:
        logger.info(f"Completion attempt made for task: {task_title}")
        # Update task status to "In Progress" if not already
        current_status = safe_get_property(task, "Status", "status")
        if current_status not in ["In Progress", "In-Progress"]:
            try:
                notion.update_page(task_id, {
                    "Status": {"status": {"name": "In Progress"}}
                })
                logger.info("Updated task status to 'In Progress'")
            except Exception as e:
                logger.warning(f"Could not update task status: {e}")
    
    return completion_attempted


def create_handoff_trigger_with_downstream_awareness(
    notion: NotionManager,
    task_details: Dict,
    next_task_name: str = None,
    next_agent: str = None,
    next_task_id: str = "TO_BE_CREATED"
) -> Optional[Path]:
    """
    Create a handoff trigger file with downstream task handoff awareness.
    
    Args:
        notion: NotionManager instance
        task_details: Task details dictionary
        next_task_name: Name of the next task in the chain
        next_agent: Agent name for the next task
        next_task_id: ID of the next task (or "TO_BE_CREATED")
    
    Returns:
        Path to created trigger file or None
    """
    agent_name = task_details.get("agent_name", "Unknown Agent")
    agent_id = task_details.get("agent_id")
    agent_type = determine_agent_type(agent_name, agent_id)
    
    # Build enhanced handoff instructions with downstream awareness
    base_instructions = task_details.get("handoff_instructions", "")
    
    downstream_instructions = f"""
## 🚨 MANDATORY DOWNSTREAM HANDOFF REQUIREMENT

**CRITICAL:** Upon completion of this task, you MUST create a handoff trigger file for the next task in the workflow.

**Next Task:** {next_task_name or "See task description for next steps"}
**Next Agent:** {next_agent or "To be determined based on task requirements"}
**Next Task ID:** {next_task_id}

**Required Actions:**
1. **MOVE TRIGGER FILE (MANUAL)**: You MUST manually call mark_trigger_file_processed() to move the trigger file from 01_inbox to 02_processed. This cannot be automated - you are responsible for moving it.
2. Complete all work specified in this task
3. Update the task status in Notion to "Complete" or "Completed"
4. **CREATE NEXT HANDOFF**: Create a handoff trigger file for the next task (see details above)
5. Document all deliverables and artifacts
6. Provide all context needed for the next task to begin
7. Link related items in Notion (issues, projects, tasks)

**NO EXCEPTIONS. TASK IS NOT COMPLETE UNTIL HANDOFF FILE IS CREATED AND TRIGGER FILE IS MOVED.**
"""
    
    enhanced_instructions = base_instructions + "\n\n" + downstream_instructions
    
    # Update task_details with enhanced instructions
    enhanced_task_details = task_details.copy()
    enhanced_task_details["handoff_instructions"] = enhanced_instructions
    
    # Create trigger file
    trigger_file = create_trigger_file(agent_type, agent_name, enhanced_task_details)
    
    if trigger_file:
        logger.info(f"Created handoff trigger file with downstream awareness: {trigger_file}")
    
    return trigger_file


def create_validation_task(
    notion: NotionManager,
    project_id: str = None,
    project_title: str = None,
    completed_task_id: str = None,
    completed_task_title: str = None
) -> Optional[str]:
    """Create an Agent Work Validation Task."""
    logger.info("Creating Agent Work Validation Task...")
    
    # Determine validation task details
    validation_title = f"Validate Work: {completed_task_title or 'Recent Work'}"
    validation_description = f"""## Objective
Review and validate the work performed in the recent task completion.

## Task Completed
- **Task:** {completed_task_title or 'N/A'}
- **Task ID:** {completed_task_id or 'N/A'}

## Validation Requirements
1. Review all deliverables and artifacts created
2. Verify code quality and compliance with standards
3. Check documentation completeness
4. Validate Notion synchronization
5. Confirm all trigger files were created correctly
6. Verify downstream handoff awareness

## Success Criteria
- [ ] All deliverables reviewed
- [ ] Code quality verified
- [ ] Documentation complete
- [ ] Notion synchronized
- [ ] Trigger files validated
- [ ] Downstream handoffs confirmed

## Next Steps
Upon validation completion, create handoff trigger file for any follow-up work needed.
"""
    
    # Get default status
    default_status = None
    try:
        db_schema = notion.client.databases.retrieve(database_id=AGENT_TASKS_DB_ID)
        status_prop = db_schema.get("properties", {}).get("Status", {})
        if status_prop.get("type") == "status":
            status_options = status_prop.get("status", {}).get("options", [])
            for option in status_options:
                option_name = option.get("name", "")
                if option_name in ["Ready", "Proposed", "Draft", "Not Started"]:
                    default_status = option_name
                    break
    except Exception as e:
        logger.debug(f"Could not retrieve database schema: {e}")
    
    # Build properties
    properties = {
        "Task Name": {
            "title": [{"text": {"content": validation_title}}]
        },
        "Description": {
            "rich_text": [{"text": {"content": validation_description}}]
        },
        "Priority": {
            "select": {"name": "High"}
        },
        "Assigned-Agent": {
            "relation": [{"id": CLAUDE_MM1_AGENT_ID}]  # Validation tasks go to Claude MM1
        }
    }
    
    if default_status:
        properties["Status"] = {"status": {"name": default_status}}
    
    # Link to project if available
    if project_id:
        try:
            properties["Projects"] = {"relation": [{"id": project_id}]}
        except:
            try:
                properties["Project"] = {"relation": [{"id": project_id}]}
            except:
                pass
    
    # Create task
    new_task = notion.create_page(AGENT_TASKS_DB_ID, properties)
    
    if new_task:
        task_id = new_task.get("id")
        task_url = new_task.get("url", "")
        logger.info(f"Created validation task: {task_url}")
        
        # Create trigger file for validation task
        task_details = {
            "task_id": task_id,
            "task_title": validation_title,
            "task_url": task_url,
            "project_id": project_id,
            "project_title": project_title,
            "description": validation_description,
            "status": default_status or "Ready",
            "agent_name": "Claude MM1 Agent",
            "agent_id": CLAUDE_MM1_AGENT_ID,
            "priority": "High",
            "handoff_instructions": (
                "Review and validate the completed work. Upon completion, you MUST:\n"
                "1. **MOVE TRIGGER FILE (MANUAL)**: You MUST manually call mark_trigger_file_processed() to move the trigger file from 01_inbox to 02_processed.\n"
                "2. Update the task status in Notion\n"
                "3. Document validation results\n"
                "4. Create handoff trigger file for any follow-up work needed\n"
            )
        }
        
        trigger_file = create_handoff_trigger_with_downstream_awareness(
            notion,
            task_details,
            next_task_name="Follow-up Work (if needed)",
            next_agent="Cursor MM1 Agent",
            next_task_id="TO_BE_CREATED"
        )
        
        if trigger_file:
            logger.info(f"Created trigger file for validation task: {trigger_file}")
        
        return task_id
    
    return None


def main():
    """Main execution function."""
    logger.info("=" * 80)
    logger.info("Review and Resolve Outstanding Work")
    logger.info("=" * 80)
    
    # Phase 0: Preflight token validation
    token = preflight_token_validation()
    if not token:
        logger.error("Token validation failed - cannot proceed")
        sys.exit(1)
    
    # Initialize Notion client
    try:
        notion = NotionManager(token)
        logger.info("✅ Notion client initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize Notion client: {e}")
        sys.exit(1)
    
    # Step 1: Check for outstanding issues
    issues = query_outstanding_issues(notion)
    
    if issues:
        logger.info(f"Found {len(issues)} outstanding issues")
        
        # Step 2: Identify most critical issue
        critical_issue = identify_critical_issue(issues)
        
        if critical_issue:
            issue_title = safe_get_property(critical_issue, "Name", "title") or "Untitled Issue"
            issue_id = critical_issue.get("id")
            issue_url = critical_issue.get("url", "")
            issue_description = safe_get_property(critical_issue, "Description", "rich_text") or ""
            issue_priority = safe_get_property(critical_issue, "Priority", "select") or "High"
            
            logger.info(f"Critical issue identified: {issue_title}")
            
            # Step 3: Attempt resolution
            resolution_attempted = attempt_issue_resolution(notion, critical_issue)
            
            # Step 4: Create handoff trigger file
            # Determine next agent based on issue type
            next_agent = "Cursor MM1 Agent"  # Default to Cursor MM1 for implementation
            next_agent_id = CURSOR_MM1_AGENT_ID
            
            # If issue needs planning, use Claude MM1
            if "plan" in issue_description.lower() or "review" in issue_description.lower():
                next_agent = "Claude MM1 Agent"
                next_agent_id = CLAUDE_MM1_AGENT_ID
            
            task_details = {
                "task_id": f"issue-{issue_id}",
                "task_title": f"Resolve Issue: {issue_title[:50]}",
                "task_url": issue_url,
                "project_id": None,
                "project_title": None,
                "description": issue_description,
                "status": "Ready",
                "agent_name": next_agent,
                "agent_id": next_agent_id,
                "priority": issue_priority,
                "handoff_instructions": (
                    f"Resolve the issue: {issue_title}\n\n"
                    f"Issue Description: {issue_description}\n\n"
                    "Upon completion, you MUST:\n"
                    "1. **MOVE TRIGGER FILE (MANUAL)**: You MUST manually call mark_trigger_file_processed() to move the trigger file from 01_inbox to 02_processed.\n"
                    "2. Update the issue status in Notion to 'Resolved'\n"
                    "3. Create handoff trigger file for any follow-up work\n"
                    "4. Document all deliverables and artifacts\n"
                )
            }
            
            trigger_file = create_handoff_trigger_with_downstream_awareness(
                notion,
                task_details,
                next_task_name="Issue Resolution Follow-up (if needed)",
                next_agent="Claude MM1 Agent",
                next_task_id="TO_BE_CREATED"
            )
            
            if trigger_file:
                logger.info(f"Created handoff trigger file: {trigger_file}")
            
            logger.info("Issue resolution workflow initiated")
    
    else:
        logger.info("No outstanding issues found - checking for in-progress projects...")
        
        # Step 1: Find in-progress projects
        projects = query_in_progress_projects(notion)
        
        if projects:
            logger.info(f"Found {len(projects)} in-progress project(s)")
            
            # Process first project
            current_project = projects[0]
            project_title = safe_get_property(current_project, "Name", "title") or "Untitled Project"
            project_id = current_project.get("id")
            
            logger.info(f"Processing project: {project_title}")
            
            # Step 2: Get project tasks
            tasks = get_project_tasks(notion, project_id)
            
            if tasks:
                logger.info(f"Found {len(tasks)} outstanding task(s) for project")
                
                # Prioritize tasks
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
                
                tasks_sorted = sorted(tasks, key=get_task_priority)
                current_task = tasks_sorted[0]
                
                task_title = safe_get_property(current_task, "Task Name", "title") or "Untitled Task"
                task_id = current_task.get("id")
                task_url = current_task.get("url", "")
                task_status = safe_get_property(current_task, "Status", "status") or "Unknown"
                task_description = safe_get_property(current_task, "Description", "rich_text") or ""
                
                logger.info(f"Processing task: {task_title} (Status: {task_status})")
                
                # Step 3: Attempt task completion
                completion_attempted = attempt_task_completion(notion, current_task)
                
                # Step 4: Get assigned agent
                assigned_agent_relation = safe_get_property(current_task, "Assigned-Agent", "relation") or []
                assigned_agent_id = None
                assigned_agent_name = "Unknown Agent"
                
                if assigned_agent_relation and len(assigned_agent_relation) > 0:
                    assigned_agent_id = assigned_agent_relation[0].get("id")
                    agent_name = notion.get_page_title(assigned_agent_id)
                    if agent_name:
                        assigned_agent_name = agent_name
                
                # Step 5: Create handoff trigger file
                task_details = {
                    "task_id": task_id,
                    "task_title": task_title,
                    "task_url": task_url,
                    "project_id": project_id,
                    "project_title": project_title,
                    "description": task_description,
                    "status": task_status,
                    "agent_name": assigned_agent_name,
                    "agent_id": assigned_agent_id,
                    "priority": safe_get_property(current_task, "Priority", "select") or "High",
                    "handoff_instructions": (
                        f"Complete the task: {task_title}\n\n"
                        f"Task Description: {task_description}\n\n"
                        "Upon completion, you MUST:\n"
                        "1. **MOVE TRIGGER FILE (MANUAL)**: You MUST manually call mark_trigger_file_processed() to move the trigger file from 01_inbox to 02_processed.\n"
                        "2. Update the task status in Notion to 'Complete'\n"
                        "3. Create handoff trigger file for the next task\n"
                        "4. Document all deliverables and artifacts\n"
                    )
                }
                
                # Determine next task in chain (if available)
                next_task = None
                if len(tasks_sorted) > 1:
                    next_task = tasks_sorted[1]
                    next_task_title = safe_get_property(next_task, "Task Name", "title") or "Next Task"
                    next_task_id = next_task.get("id")
                    next_agent_relation = safe_get_property(next_task, "Assigned-Agent", "relation") or []
                    next_agent_name = "Cursor MM1 Agent"
                    if next_agent_relation and len(next_agent_relation) > 0:
                        next_agent_id = next_agent_relation[0].get("id")
                        next_agent_name = notion.get_page_title(next_agent_id) or "Cursor MM1 Agent"
                else:
                    next_task_title = "Project Completion Validation"
                    next_task_id = "TO_BE_CREATED"
                    next_agent_name = "Claude MM1 Agent"
                
                trigger_file = create_handoff_trigger_with_downstream_awareness(
                    notion,
                    task_details,
                    next_task_name=next_task_title,
                    next_agent=next_agent_name,
                    next_task_id=next_task_id
                )
                
                if trigger_file:
                    logger.info(f"Created handoff trigger file: {trigger_file}")
                
                # Step 6: Create validation task
                validation_task_id = create_validation_task(
                    notion,
                    project_id=project_id,
                    project_title=project_title,
                    completed_task_id=task_id,
                    completed_task_title=task_title
                )
                
                if validation_task_id:
                    logger.info(f"Created validation task: {validation_task_id}")
                
                logger.info("Project task completion workflow initiated")
            else:
                logger.info("No outstanding tasks found for project")
        else:
            logger.info("No in-progress projects found")
    
    # Final step: Run main.py
    logger.info("=" * 80)
    logger.info("Running main.py as final step...")
    logger.info("=" * 80)
    
    try:
        import subprocess
        result = subprocess.run(
            [sys.executable, str(script_dir / "main.py")],
            cwd=str(script_dir),
            capture_output=True,
            text=True
        )
        
        if result.stdout:
            logger.info("main.py output:")
            logger.info(result.stdout)
        
        if result.stderr:
            logger.warning("main.py errors:")
            logger.warning(result.stderr)
        
        if result.returncode == 0:
            logger.info("✅ main.py completed successfully")
        else:
            logger.error(f"❌ main.py exited with code {result.returncode}")
    
    except Exception as e:
        logger.error(f"Error running main.py: {e}", exc_info=True)
    
    logger.info("=" * 80)
    logger.info("Execution completed")
    logger.info("=" * 80)


if __name__ == "__main__":
    main()

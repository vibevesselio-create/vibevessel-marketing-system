#!/usr/bin/env python3
"""
Execute Workflow Script
=======================

This script performs the following workflow:
1. Review all outstanding issues in Notion, identify the most critical and actionable issue
2. If issues exist: Attempt to resolve the issue, then create handoff trigger file
3. If no issues: Find In-Progress project, review Agent-Tasks, attempt completion, create handoff
4. Create validation task trigger if needed
5. Run main.py as final step

Author: Cursor MM1 Agent
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
        logging.FileHandler('execute_workflow.log')
    ]
)
logger = logging.getLogger(__name__)

# Import from main.py
try:
    from main import (
        NotionManager,
        get_notion_token,
        safe_get_property,
        create_trigger_file,
        normalize_agent_folder_name,
        ISSUES_QUESTIONS_DB_ID,
        PROJECTS_DB_ID,
        AGENT_TASKS_DB_ID,
        CLAUDE_MM1_AGENT_ID,
        CURSOR_MM1_AGENT_ID,
        MM1_AGENT_TRIGGER_BASE,
        MM2_AGENT_TRIGGER_BASE,
    )
except ImportError as e:
    logger.error(f"Failed to import from main.py: {e}")
    sys.exit(1)

# Try to import task creation helpers
try:
    from shared_core.notion.task_creation import add_mandatory_next_handoff_instructions
    TASK_CREATION_HELPERS_AVAILABLE = True
except ImportError:
    TASK_CREATION_HELPERS_AVAILABLE = False
    logger.warning("Task creation helpers not available")


def query_outstanding_issues(notion: NotionManager) -> List[Dict]:
    """Query Notion Issues+Questions database for outstanding issues."""
    logger.info("Querying Issues+Questions database for outstanding issues...")
    
    # Filter for outstanding issues
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
    
    issues = notion.query_database(ISSUES_QUESTIONS_DB_ID, filter_params=filter_params)
    
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
    return issues_sorted[0]


def attempt_issue_resolution(notion: NotionManager, issue: Dict) -> bool:
    """
    Attempt to resolve the issue.
    Returns True if resolved, False if blocking point reached.
    """
    issue_title = safe_get_property(issue, "Name", "title") or "Untitled Issue"
    issue_id = issue.get("id")
    issue_url = issue.get("url", "")
    issue_description = safe_get_property(issue, "Description", "rich_text") or ""
    issue_priority = safe_get_property(issue, "Priority", "select") or "High"
    
    logger.info(f"Attempting to resolve issue: {issue_title}")
    logger.info(f"Issue URL: {issue_url}")
    logger.info(f"Issue Description: {issue_description[:200]}...")
    
    # TODO: Implement actual resolution logic based on issue type/description
    # For now, we'll mark this as a blocking point and create handoff
    
    logger.info("Issue resolution requires further investigation - creating handoff")
    return False


def query_in_progress_projects(notion: NotionManager) -> List[Dict]:
    """Query Notion Projects database for In-Progress projects."""
    logger.info("Querying Projects database for In-Progress projects...")
    
    # Try "In-Progress" first
    filter_params = {
        "property": "Status",
        "status": {"equals": "In-Progress"}
    }
    
    projects = notion.query_database(PROJECTS_DB_ID, filter_params=filter_params)
    
    # If no results, try "In Progress" (with space)
    if not projects:
        logger.debug("No projects found with 'In-Progress' status, trying 'In Progress'")
        filter_params = {
            "property": "Status",
            "status": {"equals": "In Progress"}
        }
        projects = notion.query_database(PROJECTS_DB_ID, filter_params=filter_params)
    
    logger.info(f"Found {len(projects)} In-Progress project(s)")
    return projects


def query_project_agent_tasks(notion: NotionManager, project_id: str) -> List[Dict]:
    """Query Agent-Tasks database for tasks related to a project."""
    logger.info(f"Querying Agent-Tasks for project {project_id}...")
    
    # Try "Projects" (plural) first
    filter_params = {
        "and": [
            {
                "property": "Projects",
                "relation": {"contains": project_id}
            }
        ]
    }
    
    tasks = notion.query_database(AGENT_TASKS_DB_ID, filter_params=filter_params)
    
    # If no results, try "Project" (singular)
    if not tasks:
        logger.debug("No tasks found with 'Projects' relation, trying 'Project' (singular)")
        filter_params = {
            "and": [
                {
                    "property": "Project",
                    "relation": {"contains": project_id}
                }
            ]
        }
        tasks = notion.query_database(AGENT_TASKS_DB_ID, filter_params=filter_params)
    
    # Filter out completed tasks
    if tasks:
        tasks = [
            task for task in tasks
            if safe_get_property(task, "Status", "status") not in ["Complete", "Completed", "Done"]
        ]
    
    logger.info(f"Found {len(tasks)} outstanding agent task(s) for project")
    return tasks


def attempt_task_completion(notion: NotionManager, task: Dict, project: Dict) -> bool:
    """
    Attempt to complete the task.
    Returns True if completed, False if blocking point reached.
    """
    task_title = safe_get_property(task, "Task Name", "title") or "Untitled Task"
    task_id = task.get("id")
    task_url = task.get("url", "")
    task_description = safe_get_property(task, "Description", "rich_text") or ""
    task_status = safe_get_property(task, "Status", "status")
    
    logger.info(f"Attempting to complete task: {task_title}")
    logger.info(f"Task URL: {task_url}")
    logger.info(f"Task Status: {task_status}")
    logger.info(f"Task Description: {task_description[:200]}...")
    
    # TODO: Implement actual task completion logic based on task type/description
    # For now, we'll mark this as a blocking point and create handoff
    
    logger.info("Task completion requires further investigation - creating handoff")
    return False


def create_handoff_trigger(
    notion: NotionManager,
    task_or_issue: Dict,
    is_issue: bool,
    project: Optional[Dict] = None,
    target_agent: str = "Claude MM1 Agent",
    target_agent_id: str = None,
    handoff_instructions: str = ""
) -> Optional[Path]:
    """Create a handoff trigger file with downstream awareness."""
    if is_issue:
        title = safe_get_property(task_or_issue, "Name", "title") or "Untitled Issue"
        item_id = task_or_issue.get("id")
        item_url = task_or_issue.get("url", "")
        description = safe_get_property(task_or_issue, "Description", "rich_text") or ""
        priority = safe_get_property(task_or_issue, "Priority", "select") or "High"
    else:
        title = safe_get_property(task_or_issue, "Task Name", "title") or "Untitled Task"
        item_id = task_or_issue.get("id")
        item_url = task_or_issue.get("url", "")
        description = safe_get_property(task_or_issue, "Description", "rich_text") or ""
        priority = safe_get_property(task_or_issue, "Priority", "select") or "High"
    
    project_id = project.get("id") if project else None
    project_title = safe_get_property(project, "Name", "title") if project else None
    
    # Determine agent type
    agent_type = "MM1"  # Default to MM1
    
    # Default handoff instructions if not provided
    if not handoff_instructions:
        if is_issue:
            handoff_instructions = f"""
## Issue Resolution Task

**Issue:** {title}
**Issue URL:** {item_url}

**Description:**
{description}

**Required Actions:**
1. Review the issue in detail
2. Investigate root cause
3. Implement solution
4. Test and verify resolution
5. Update issue status in Notion
6. Document resolution steps

**MANDATORY HANDOFF REQUIREMENTS:**
Upon completion or reaching a blocking point, you MUST:
1. **MOVE TRIGGER FILE (MANUAL)**: You MUST manually call mark_trigger_file_processed() to move the trigger file from 01_inbox to 02_processed
2. Create the next handoff trigger file for the appropriate agent to continue the work
3. Update Notion with progress and status
4. Document all deliverables and artifacts
5. Provide complete context for the next agent

**Task is NOT complete until trigger file is manually moved and next handoff is created.**
"""
        else:
            handoff_instructions = f"""
## Task Completion

**Task:** {title}
**Task URL:** {item_url}
{f"**Project:** {project_title}" if project_title else ""}

**Description:**
{description}

**Required Actions:**
1. Review task requirements
2. Complete all task deliverables
3. Perform documentation and synchronization
4. Execute cleanup procedures
5. Update task status in Notion

**MANDATORY HANDOFF REQUIREMENTS:**
Upon completion or reaching a blocking point, you MUST:
1. **MOVE TRIGGER FILE (MANUAL)**: You MUST manually call mark_trigger_file_processed() to move the trigger file from 01_inbox to 02_processed
2. Create the next handoff trigger file for the appropriate agent to continue the work
3. Update Notion with progress and status
4. Document all deliverables and artifacts
5. Provide complete context for the next agent

**Task is NOT complete until trigger file is manually moved and next handoff is created.**
"""
    
    task_details = {
        "task_id": item_id,
        "task_title": title,
        "task_url": item_url,
        "project_id": project_id,
        "project_title": project_title,
        "description": description,
        "status": "Ready",
        "agent_name": target_agent,
        "agent_id": target_agent_id,
        "priority": priority,
        "handoff_instructions": handoff_instructions
    }
    
    trigger_file = create_trigger_file(agent_type, target_agent, task_details)
    if trigger_file:
        logger.info(f"Created handoff trigger file: {trigger_file}")
    else:
        logger.error(f"Failed to create handoff trigger file for {target_agent}")
    
    return trigger_file


def create_validation_task_trigger(
    notion: NotionManager,
    project: Dict,
    completed_task: Dict
) -> Optional[Path]:
    """Create a validation task trigger for work review."""
    project_title = safe_get_property(project, "Name", "title") or "Untitled Project"
    project_id = project.get("id")
    task_title = safe_get_property(completed_task, "Task Name", "title") or "Untitled Task"
    task_id = completed_task.get("id")
    
    validation_instructions = f"""
## Agent Work Validation Task

**Project:** {project_title}
**Completed Task:** {task_title}

**Required Actions:**
1. Review all work performed for the completed task
2. Verify all deliverables are complete
3. Validate documentation and synchronization
4. Check cleanup procedures were executed
5. Confirm Notion updates are accurate
6. Identify any gaps or issues

**MANDATORY HANDOFF REQUIREMENTS:**
Upon completion, you MUST:
1. **MOVE TRIGGER FILE (MANUAL)**: You MUST manually call mark_trigger_file_processed() to move the trigger file from 01_inbox to 02_processed
2. Create validation report in Notion
3. Update project and task statuses as needed
4. Create next handoff if additional work is required

**Task is NOT complete until trigger file is manually moved and validation report is created.**
"""
    
    task_details = {
        "task_id": f"validation-{task_id}",
        "task_title": f"Validate Work: {task_title}",
        "task_url": "",
        "project_id": project_id,
        "project_title": project_title,
        "description": validation_instructions,
        "status": "Ready",
        "agent_name": "Claude MM1 Agent",
        "agent_id": CLAUDE_MM1_AGENT_ID,
        "priority": "High",
        "handoff_instructions": validation_instructions
    }
    
    trigger_file = create_trigger_file("MM1", "Claude MM1 Agent", task_details)
    if trigger_file:
        logger.info(f"Created validation task trigger file: {trigger_file}")
    else:
        logger.error("Failed to create validation task trigger file")
    
    return trigger_file


def main():
    """Main execution function"""
    logger.info("=" * 80)
    logger.info("Execute Workflow Script")
    logger.info("=" * 80)
    
    # Get Notion token
    token = get_notion_token()
    if not token:
        logger.error("Failed to get Notion token")
        sys.exit(1)
    
    # Initialize Notion client
    try:
        notion = NotionManager(token)
        logger.info("✅ Notion client initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize Notion client: {e}")
        sys.exit(1)
    
    # Step 1: Query outstanding issues
    issues = query_outstanding_issues(notion)
    
    if issues:
        # Step 2: Identify critical issue
        critical_issue = identify_critical_issue(issues)
        if critical_issue:
            issue_title = safe_get_property(critical_issue, "Name", "title") or "Untitled Issue"
            logger.info(f"Selected critical issue: {issue_title}")
            
            # Step 3: Attempt resolution
            resolved = attempt_issue_resolution(notion, critical_issue)
            
            if not resolved:
                # Create handoff trigger
                logger.info("Creating handoff trigger for issue resolution...")
                trigger_file = create_handoff_trigger(
                    notion=notion,
                    task_or_issue=critical_issue,
                    is_issue=True,
                    target_agent="Claude MM1 Agent",
                    target_agent_id=CLAUDE_MM1_AGENT_ID
                )
                
                if trigger_file:
                    logger.info(f"✅ Created handoff trigger: {trigger_file}")
                else:
                    logger.error("❌ Failed to create handoff trigger")
    else:
        # No outstanding issues - check for In-Progress projects
        logger.info("No outstanding issues found. Checking for In-Progress projects...")
        
        projects = query_in_progress_projects(notion)
        
        if projects:
            # Process first In-Progress project
            project = projects[0]
            project_title = safe_get_property(project, "Name", "title") or "Untitled Project"
            project_id = project.get("id")
            
            logger.info(f"Processing project: {project_title}")
            
            # Query Agent-Tasks for this project
            tasks = query_project_agent_tasks(notion, project_id)
            
            if tasks:
                # Prioritize tasks: In-Progress > Ready > Not Started
                def get_task_priority(task):
                    status = safe_get_property(task, "Status", "status")
                    priority_map = {
                        "In-Progress": 0,
                        "In Progress": 0,
                        "Ready": 1,
                        "Ready for Handoff": 1,
                        "Not Started": 2,
                    }
                    return priority_map.get(status, 99)
                
                tasks_sorted = sorted(tasks, key=get_task_priority)
                current_task = tasks_sorted[0]
                
                task_title = safe_get_property(current_task, "Task Name", "title") or "Untitled Task"
                logger.info(f"Selected task: {task_title}")
                
                # Attempt task completion
                completed = attempt_task_completion(notion, current_task, project)
                
                if not completed:
                    # Create handoff trigger
                    logger.info("Creating handoff trigger for task completion...")
                    
                    # Determine target agent from task assignment
                    assigned_agent_relation = safe_get_property(current_task, "Assigned-Agent", "relation")
                    target_agent = "Claude MM1 Agent"
                    target_agent_id = CLAUDE_MM1_AGENT_ID
                    
                    if assigned_agent_relation:
                        # Try to get agent name from relation (would need to query agent page)
                        # For now, default to Claude MM1
                        pass
                    
                    trigger_file = create_handoff_trigger(
                        notion=notion,
                        task_or_issue=current_task,
                        is_issue=False,
                        project=project,
                        target_agent=target_agent,
                        target_agent_id=target_agent_id
                    )
                    
                    if trigger_file:
                        logger.info(f"✅ Created handoff trigger: {trigger_file}")
                    else:
                        logger.error("❌ Failed to create handoff trigger")
                    
                    # Create validation task trigger
                    logger.info("Creating validation task trigger...")
                    validation_trigger = create_validation_task_trigger(
                        notion=notion,
                        project=project,
                        completed_task=current_task
                    )
                    
                    if validation_trigger:
                        logger.info(f"✅ Created validation trigger: {validation_trigger}")
                    else:
                        logger.error("❌ Failed to create validation trigger")
            else:
                logger.info(f"No outstanding tasks found for project '{project_title}'")
        else:
            logger.info("No In-Progress projects found")
    
    logger.info("=" * 80)
    logger.info("Workflow execution completed")
    logger.info("=" * 80)
    
    # Final step: Run main.py
    logger.info("Running main.py as final step...")
    try:
        import subprocess
        result = subprocess.run(
            [sys.executable, "main.py"],
            cwd=script_dir,
            capture_output=True,
            text=True
        )
        logger.info(f"main.py exit code: {result.returncode}")
        if result.stdout:
            logger.info(f"main.py stdout:\n{result.stdout}")
        if result.stderr:
            logger.error(f"main.py stderr:\n{result.stderr}")
    except Exception as e:
        logger.error(f"Failed to run main.py: {e}")


if __name__ == "__main__":
    main()


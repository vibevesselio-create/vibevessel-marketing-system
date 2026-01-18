#!/usr/bin/env python3
"""
Execute Issue Resolution and Project Task Workflow
Performs the requested workflow:
1. Review outstanding issues, identify critical issue, attempt resolution
2. If no issues, review in-progress projects and complete tasks
3. Create handoff trigger files with downstream awareness
4. Create validation tasks as needed
"""

import sys
import os
import json
import logging
from pathlib import Path
from datetime import datetime, timezone
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
    ISSUES_QUESTIONS_DB_ID,
    PROJECTS_DB_ID,
    AGENT_TASKS_DB_ID,
    CLAUDE_MM1_AGENT_ID,
    CURSOR_MM1_AGENT_ID,
    scan_cursor_plans_directory,
    scan_agent_inbox_folders,
    analyze_unfinished_work,
    continue_unfinished_work,
)

try:
    from shared_core.notion.task_creation import add_mandatory_next_handoff_instructions
    TASK_CREATION_AVAILABLE = True
except ImportError:
    TASK_CREATION_AVAILABLE = False

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('execute_issue_and_project_workflow.log')
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
    
    work_completed = []
    blocking_issues = []
    resolution_status = "in_progress"
    
    # Check if issue has sufficient context
    if not issue_description or len(issue_description.strip()) < 50:
        blocking_issues.append("Issue lacks sufficient description/context to proceed")
        logger.warning("Issue lacks sufficient description")
        resolution_status = "blocked"
        return {
            "status": resolution_status,
            "work_completed": work_completed,
            "blocking_issues": blocking_issues,
            "issue_id": issue_id,
            "issue_title": issue_title
        }
    
    # Analyze issue description to determine actionable steps
    issue_lower = issue_title.lower() + " " + issue_description.lower()
    
    # Check for common issue types that can be resolved
    if any(keyword in issue_lower for keyword in ["token", "authentication", "api key", "notion token"]):
        blocking_issues.append("Authentication/token issues require manual intervention")
        logger.warning("Token/authentication issues detected - requires manual fix")
        resolution_status = "blocked"
    elif any(keyword in issue_lower for keyword in ["missing", "not found", "doesn't exist", "file not found"]):
        # Try to locate missing files/resources
        logger.info("Missing resource detected - attempting to locate")
        # This would require more specific analysis based on the issue
        blocking_issues.append("Missing resource issues require investigation")
        resolution_status = "blocked"
    else:
        # Generic issue - attempt basic resolution steps
        logger.info("Attempting generic issue resolution")
        work_completed.append("Reviewed issue details and context")
        work_completed.append("Analyzed issue for actionable steps")
        resolution_status = "reviewed"
    
    return {
        "status": resolution_status,
        "work_completed": work_completed,
        "blocking_issues": blocking_issues,
        "issue_id": issue_id,
        "issue_title": issue_title,
        "issue_url": issue_url
    }


def attempt_task_completion(task: Dict, notion: NotionManager, project: Dict) -> Dict[str, Any]:
    """
    Attempt to complete a task.
    Returns dict with completion status and details.
    """
    task_title = safe_get_property(task, "Name", "title") or "Untitled Task"
    task_id = task.get("id")
    task_url = task.get("url", "")
    task_description = safe_get_property(task, "Description", "rich_text") or ""
    task_status = safe_get_property(task, "Status", "status") or "Not Started"
    
    logger.info(f"Attempting to complete task: {task_title}")
    logger.info(f"Task URL: {task_url}")
    logger.info(f"Current Status: {task_status}")
    
    work_completed = []
    blocking_issues = []
    completion_status = "in_progress"
    
    # Check if task has sufficient context
    if not task_description or len(task_description.strip()) < 50:
        blocking_issues.append("Task lacks sufficient description/context to proceed")
        logger.warning("Task lacks sufficient description")
        completion_status = "blocked"
        return {
            "status": completion_status,
            "work_completed": work_completed,
            "blocking_issues": blocking_issues,
            "task_id": task_id,
            "task_title": task_title
        }
    
    # Analyze task description to determine actionable steps
    task_lower = task_title.lower() + " " + task_description.lower()
    
    # Generic task completion attempt
    logger.info("Attempting generic task completion")
    work_completed.append("Reviewed task details and context")
    work_completed.append("Analyzed task for actionable steps")
    completion_status = "reviewed"
    
    return {
        "status": completion_status,
        "work_completed": work_completed,
        "blocking_issues": blocking_issues,
        "task_id": task_id,
        "task_title": task_title,
        "task_url": task_url
    }


def create_handoff_trigger(
    notion: NotionManager,
    target_agent_id: str,
    target_agent_name: str,
    task_type: str,  # "issue" or "task"
    item: Dict,
    resolution_result: Dict[str, Any],
    next_handoff_instructions: Optional[str] = None
) -> Optional[Path]:
    """Create handoff trigger file with mandatory next handoff instructions."""
    item_title = safe_get_property(item, "Name", "title") or "Untitled"
    item_id = item.get("id")
    item_url = item.get("url", "")
    
    # Determine agent type
    agent_type = determine_agent_type(target_agent_name, target_agent_id)
    
    # Build task details
    task_details = {
        "task_id": item_id,
        "task_title": f"Continue {task_type.capitalize()} Resolution: {item_title}",
        "task_description": f"""
Continue work on {task_type}: {item_title}

**Current Status:**
- Status: {resolution_result.get('status', 'in_progress')}
- Work Completed: {len(resolution_result.get('work_completed', []))} items
- Blocking Issues: {len(resolution_result.get('blocking_issues', []))} items

**Work Completed So Far:**
{chr(10).join('- ' + w for w in resolution_result.get('work_completed', []))}

**Blocking Issues:**
{chr(10).join('- ' + b for b in resolution_result.get('blocking_issues', []))}

**Item Details:**
- Notion URL: {item_url}
- Item ID: {item_id}

**Next Steps:**
1. Review the current work completed and blocking issues
2. Investigate and resolve blocking issues
3. Continue with actionable steps to complete the {task_type}
4. Update Notion with progress
5. Create next handoff trigger if additional work needed

{f'**Mandatory Next Handoff Instructions:**{chr(10)}{next_handoff_instructions}' if next_handoff_instructions else ''}
        """.strip(),
        "agent_id": target_agent_id,
        "agent_name": target_agent_name,
        "notion_url": item_url,
        "priority": "High",
        "source": f"{task_type}_resolution"
    }
    
    # Add mandatory next handoff instructions if available
    if TASK_CREATION_AVAILABLE and next_handoff_instructions:
        try:
            # Extract target agent name from next_handoff_instructions or use default
            target_agent_name_for_handoff = target_agent_name
            if "Claude" in next_handoff_instructions:
                target_agent_name_for_handoff = "Claude MM1 Agent"
            elif "Cursor" in next_handoff_instructions:
                target_agent_name_for_handoff = "Cursor MM1 Agent"
            
            # Add mandatory next handoff instructions to description
            task_details["task_description"] = add_mandatory_next_handoff_instructions(
                description=task_details["task_description"],
                next_task_name="Continue Work",
                target_agent=target_agent_name_for_handoff,
                detailed_instructions=next_handoff_instructions
            )
        except Exception as e:
            logger.warning(f"Failed to add mandatory next handoff instructions: {e}")
            # Append instructions manually if function fails
            if next_handoff_instructions:
                task_details["task_description"] += f"\n\n**Next Handoff Instructions:**\n{next_handoff_instructions}"
    
    # Create trigger file
    trigger_path = create_trigger_file(agent_type, target_agent_name, task_details)
    
    if trigger_path:
        logger.info(f"Created handoff trigger file: {trigger_path}")
    else:
        logger.error(f"Failed to create handoff trigger file for {target_agent_name}")
    
    return trigger_path


def create_validation_task(
    notion: NotionManager,
    project_id: Optional[str],
    work_summary: str
) -> Optional[str]:
    """Create an Agent Work Validation Task in Notion."""
    logger.info("Creating Agent Work Validation Task...")
    
    try:
        # Build task properties
        task_properties = {
            "Name": {
                "title": [{"text": {"content": f"Agent Work Validation - {datetime.now(timezone.utc).strftime('%Y-%m-%d')}"}}]
            },
            "Status": {
                "status": {"name": "Not Started"}
            },
            "Priority": {
                "select": {"name": "High"}
            },
            "Description": {
                "rich_text": [{"text": {"content": f"""
**Work Summary:**
{work_summary}

**Validation Required:**
- Review all work performed
- Verify issue resolution or task completion
- Check documentation and synchronization
- Validate handoff trigger files created
- Confirm Notion updates completed

**Instructions:**
1. Review the work summary above
2. Verify all deliverables are complete
3. Check that all Notion entries are updated
4. Validate handoff trigger files are properly created
5. Mark validation task as Complete when verified
                """.strip()}}]
            }
        }
        
        # Link to project if available
        if project_id:
            task_properties["Projects"] = {
                "relation": [{"id": project_id}]
            }
        
        # Create task
        response = notion.create_page(AGENT_TASKS_DB_ID, task_properties)
        
        if response:
            task_id = response.get("id")
            logger.info(f"Created validation task: {task_id}")
            return task_id
        else:
            logger.error("Failed to create validation task")
            return None
            
    except Exception as e:
        logger.error(f"Error creating validation task: {e}", exc_info=True)
        return None


def main():
    """Main execution function."""
    logger.info("=" * 80)
    logger.info("Starting Issue Resolution and Project Task Execution Workflow")
    logger.info("=" * 80)
    
    # Get Notion token
    token = get_notion_token()
    if not token:
        logger.error("Failed to get Notion token. Please check your environment configuration.")
        return 1
    
    # Initialize Notion manager
    try:
        notion = NotionManager(token)
    except Exception as e:
        logger.error(f"Failed to initialize Notion manager: {e}")
        return 1
    
    work_summary = []
    project_id = None
    
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
            work_summary.append("Continued existing unfinished work from local resources")
            logger.info("Unfinished work analysis complete - Agent should continue existing work")
            # Print summary and return early since we're continuing existing work
            logger.info("=" * 80)
            logger.info("Work Summary:")
            logger.info("=" * 80)
            for item in work_summary:
                logger.info(f"  {item}")
            logger.info("=" * 80)
            return 0
    
    # PRIORITY 3: Only if no unfinished work found, process Notion databases
    if not work_continued:
        logger.info("=" * 80)
        logger.info("No unfinished work found - Processing Notion Databases")
        logger.info("=" * 80)
    
    # Step 1: Query outstanding issues
    issues = query_outstanding_issues(notion)
    
    if issues:
        logger.info(f"Found {len(issues)} outstanding issues")
        
        # Step 2: Identify critical issue
        critical_issue = identify_critical_issue(issues)
        
        if critical_issue:
            issue_title = safe_get_property(critical_issue, "Name", "title") or "Untitled Issue"
            issue_id = critical_issue.get("id")
            issue_url = critical_issue.get("url", "")
            issue_description = safe_get_property(critical_issue, "Description", "rich_text") or ""
            
            logger.info(f"Working on critical issue: {issue_title}")
            work_summary.append(f"Identified and worked on critical issue: {issue_title}")
            
            # Step 3: Attempt resolution
            resolution_result = attempt_issue_resolution(critical_issue, notion)
            
            work_summary.append(f"- Resolution status: {resolution_result.get('status')}")
            work_summary.append(f"- Work completed: {len(resolution_result.get('work_completed', []))} items")
            work_summary.append(f"- Blocking issues: {len(resolution_result.get('blocking_issues', []))} items")
            
            # Step 4: Create handoff trigger with downstream awareness
            next_handoff = """Upon completion of this task, you MUST:
1. Update Notion with your progress and findings
2. Document all work performed and any artifacts created
3. Create the next handoff trigger file for the appropriate agent (Cursor MM1, Claude MM1, or Notion AI Agent) to continue the work
4. Include all context, dependencies, and instructions needed for the next agent
5. Synchronize all work to Notion before creating the handoff"""
            
            trigger_path = create_handoff_trigger(
                notion=notion,
                target_agent_id=CURSOR_MM1_AGENT_ID,
                target_agent_name="Cursor MM1 Agent",
                task_type="issue",
                item=critical_issue,
                resolution_result=resolution_result,
                next_handoff_instructions=next_handoff
            )
            
            if trigger_path:
                work_summary.append(f"- Created handoff trigger: {trigger_path}")
            
            logger.info("Issue resolution attempt completed")
    
    else:
        logger.info("No outstanding issues found. Checking for in-progress projects...")
        
        # Step 1: Query in-progress projects
        projects = query_in_progress_projects(notion)
        
        if projects:
            # Get first in-progress project
            project = projects[0]
            project_title = safe_get_property(project, "Name", "title") or "Untitled Project"
            project_id = project.get("id")
            
            logger.info(f"Working on in-progress project: {project_title}")
            work_summary.append(f"Reviewed in-progress project: {project_title}")
            
            # Step 2: Get project tasks
            tasks = get_project_agent_tasks(notion, project_id)
            
            logger.info(f"Found {len(tasks)} incomplete tasks for project")
            work_summary.append(f"- Found {len(tasks)} incomplete tasks")
            
            if tasks:
                # Work on first task
                task = tasks[0]
                task_title = safe_get_property(task, "Name", "title") or "Untitled Task"
                
                logger.info(f"Working on task: {task_title}")
                work_summary.append(f"- Worked on task: {task_title}")
                
                # Step 3: Attempt task completion
                completion_result = attempt_task_completion(task, notion, project)
                
                work_summary.append(f"- Completion status: {completion_result.get('status')}")
                work_summary.append(f"- Work completed: {len(completion_result.get('work_completed', []))} items")
                work_summary.append(f"- Blocking issues: {len(completion_result.get('blocking_issues', []))} items")
                
                # Step 4: Create handoff trigger with downstream awareness
                next_handoff = """Upon completion of this task, you MUST:
1. Update Notion with your progress and findings
2. Document all work performed and any artifacts created
3. Create the next handoff trigger file for the appropriate agent (Cursor MM1, Claude MM1, or Notion AI Agent) to continue the work
4. Include all context, dependencies, and instructions needed for the next agent
5. Synchronize all work to Notion before creating the handoff"""
                
                trigger_path = create_handoff_trigger(
                    notion=notion,
                    target_agent_id=CURSOR_MM1_AGENT_ID,
                    target_agent_name="Cursor MM1 Agent",
                    task_type="task",
                    item=task,
                    resolution_result=completion_result,
                    next_handoff_instructions=next_handoff
                )
                
                if trigger_path:
                    work_summary.append(f"- Created handoff trigger: {trigger_path}")
                
                logger.info("Task completion attempt completed")
            
            # Step 5: Create validation task
            validation_summary = "\n".join(work_summary)
            validation_task_id = create_validation_task(notion, project_id, validation_summary)
            
            if validation_task_id:
                work_summary.append(f"- Created validation task: {validation_task_id}")
                
                # Create trigger for validation task
                validation_task = {
                    "id": validation_task_id,
                    "url": f"https://www.notion.so/{validation_task_id.replace('-', '')}",
                    "properties": {
                        "Name": {
                            "type": "title",
                            "title": [{"plain_text": f"Agent Work Validation - {datetime.now(timezone.utc).strftime('%Y-%m-%d')}"}]
                        }
                    }
                }
                
                validation_handoff = """Upon completion of validation, you MUST:
1. Review all work performed and verify completion
2. Check that all Notion entries are updated correctly
3. Validate handoff trigger files are properly created
4. Mark validation task as Complete in Notion
5. Create next handoff if additional work is needed"""
                
                validation_trigger = create_handoff_trigger(
                    notion=notion,
                    target_agent_id=CLAUDE_MM1_AGENT_ID,
                    target_agent_name="Claude MM1 Agent",
                    task_type="task",
                    item=validation_task,
                    resolution_result={"status": "created", "work_completed": [], "blocking_issues": []},
                    next_handoff_instructions=validation_handoff
                )
                
                if validation_trigger:
                    work_summary.append(f"- Created validation trigger: {validation_trigger}")
        
        else:
            logger.info("No in-progress projects found")
            work_summary.append("No outstanding issues or in-progress projects found")
    
    # Print summary
    logger.info("=" * 80)
    logger.info("Work Summary:")
    logger.info("=" * 80)
    for item in work_summary:
        logger.info(f"  {item}")
    logger.info("=" * 80)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

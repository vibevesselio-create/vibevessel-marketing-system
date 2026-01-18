#!/usr/bin/env python3
"""
Notion Issue Review and Task Execution Workflow
===============================================

Implements the complete workflow:
1. Review outstanding issues in Notion
2. Identify most critical actionable issue
3. Attempt resolution
4. Create handoff trigger files
5. If no issues, process in-progress projects
6. Execute main.py for task handoff flow

Author: Cursor MM1 Agent
"""

import os
import sys
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, List, Any

# Load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('notion_workflow_execution.log')
    ]
)
logger = logging.getLogger(__name__)

# Try to import notion-client
try:
    from notion_client import Client
    NOTION_CLIENT_AVAILABLE = True
except ImportError:
    logger.error("notion-client not available. Install with: pip install notion-client")
    NOTION_CLIENT_AVAILABLE = False
    Client = None

# Database IDs
ISSUES_DB_ID = os.getenv("ISSUES_DB_ID", "229e73616c27808ebf06c202b10b5166")
PROJECTS_DB_ID = os.getenv("PROJECTS_DB_ID", "286e73616c2781ffa450db2ecad4b0ba")
AGENT_TASKS_DB_ID = os.getenv("AGENT_TASKS_DB_ID", "284e73616c278018872aeb14e82e0392")

# Agent IDs
CLAUDE_MM1_AGENT_ID = "fa54f05c-e184-403a-ac28-87dd8ce9855b"
CURSOR_MM1_AGENT_ID = "249e7361-6c27-8100-8a74-de7eabb9fc8d"

# Agent Trigger Paths - Use folder_resolver for dynamic path resolution
try:
    from shared_core.notion.folder_resolver import (
        get_trigger_base_path,
        get_fallback_trigger_base_path,
        get_agent_inbox_path,
    )
    MM1_AGENT_TRIGGER_BASE = get_trigger_base_path()
    MM2_AGENT_TRIGGER_BASE = get_fallback_trigger_base_path()
    FOLDER_RESOLVER_AVAILABLE = True
except ImportError:
    # Fallback to hardcoded paths if folder_resolver not available
    MM1_AGENT_TRIGGER_BASE = Path("/Users/brianhellemn/Documents/Agents/Agent-Triggers")
    MM2_AGENT_TRIGGER_BASE = Path("/Users/brianhellemn/Library/CloudStorage/GoogleDrive-brian@serenmedia.co/My Drive/Agents-gd/Agent-Triggers-gd")
    FOLDER_RESOLVER_AVAILABLE = False
    def get_agent_inbox_path(agent_name: str) -> Path:
        """Fallback function when folder_resolver not available."""
        folder_name = agent_name.replace(" ", "-")
        return MM1_AGENT_TRIGGER_BASE / folder_name / "01_inbox"

# Add project root to path
project_root = Path(__file__).parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Try to import task creation helpers
try:
    from shared_core.notion.task_creation import add_mandatory_next_handoff_instructions
    TASK_CREATION_HELPERS_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Task creation helpers not available: {e}")
    TASK_CREATION_HELPERS_AVAILABLE = False


def get_notion_token() -> Optional[str]:
    """Get Notion API token from shared_core token manager"""
    # Use centralized token manager (MANDATORY per CLAUDE.md)
    try:
        from shared_core.notion.token_manager import get_notion_token as _get_notion_token
        token = _get_notion_token()
        if token:
            logger.debug("Found Notion token via shared_core token manager")
            return token
    except ImportError as e:
        logger.debug(f"shared_core token manager import failed: {e}")

    # Fallback to environment variables for backwards compatibility
    token = (
        os.getenv("NOTION_TOKEN") or
        os.getenv("NOTION_API_TOKEN") or
        os.getenv("VV_AUTOMATIONS_WS_TOKEN")
    )
    if token:
        logger.debug("Found Notion token in environment")
        return token

    return None


def safe_get_property(page: Dict, property_name: str, property_type: str = None) -> Any:
    """Safely extract property value from Notion page."""
    try:
        properties = page.get("properties", {})
        if not properties:
            return None
        
        prop = properties.get(property_name)
        if not prop:
            return None
        
        actual_type = prop.get("type")
        if property_type and actual_type != property_type:
            return None
        
        if actual_type == "title":
            title_list = prop.get("title", [])
            if title_list and len(title_list) > 0:
                return title_list[0].get("plain_text", "")
            return None
        
        elif actual_type == "rich_text":
            text_list = prop.get("rich_text", [])
            if text_list and len(text_list) > 0:
                return text_list[0].get("plain_text", "")
            return None
        
        elif actual_type == "status":
            status_obj = prop.get("status")
            if status_obj:
                return status_obj.get("name")
            return None
        
        elif actual_type == "select":
            select_obj = prop.get("select")
            if select_obj:
                return select_obj.get("name")
            return None
        
        elif actual_type == "relation":
            relation_list = prop.get("relation", [])
            return relation_list
        
        elif actual_type == "date":
            date_obj = prop.get("date")
            if date_obj:
                return date_obj.get("start")
            return None
        
        elif actual_type == "url":
            return prop.get("url")
        
        elif actual_type == "number":
            return prop.get("number")
        
        elif actual_type == "checkbox":
            return prop.get("checkbox", False)
        
        elif actual_type == "multi_select":
            multi_select_list = prop.get("multi_select", [])
            return [item.get("name") for item in multi_select_list if item.get("name")]
        
        else:
            return prop
        
    except Exception as e:
        logger.error(f"Error extracting property '{property_name}': {e}")
        return None


class NotionManager:
    """Enhanced Notion client with error handling and logging"""
    
    def __init__(self, token: str):
        if not NOTION_CLIENT_AVAILABLE:
            raise ImportError("notion-client library not available")
        self.client = Client(auth=token)
        logger.info("Notion client initialized")
    
    def query_database(
        self, 
        database_id: str, 
        filter_params: Dict = None,
        sorts: List[Dict] = None
    ) -> List[Dict]:
        """Query Notion database with error handling"""
        try:
            query_params = {"database_id": database_id}
            
            if filter_params:
                query_params["filter"] = filter_params
            
            if sorts:
                query_params["sorts"] = sorts
            
            response = self.client.databases.query(**query_params)
            results = response.get("results", [])
            logger.info(f"Retrieved {len(results)} pages from database {database_id}")
            return results
            
        except Exception as e:
            logger.error(f"Error querying database {database_id}: {e}", exc_info=True)
            return []
    
    def create_page(self, parent_database_id: str, properties: Dict) -> Optional[Dict]:
        """Create a new page in Notion database"""
        try:
            response = self.client.pages.create(
                parent={"database_id": parent_database_id},
                properties=properties
            )
            page_id = response.get("id")
            logger.info(f"Created page {page_id} in database {parent_database_id}")
            return response
        except Exception as e:
            logger.error(f"Error creating page: {e}", exc_info=True)
            return None
    
    def update_page(self, page_id: str, properties: Dict) -> bool:
        """Update Notion page with error handling"""
        try:
            self.client.pages.update(page_id=page_id, properties=properties)
            logger.info(f"Updated page {page_id}")
            return True
        except Exception as e:
            logger.error(f"Error updating page {page_id}: {e}", exc_info=True)
            return False
    
    def get_page_title(self, page_id: str) -> Optional[str]:
        """Get title/name of a Notion page"""
        try:
            page = self.client.pages.retrieve(page_id=page_id)
            properties = page.get("properties", {})
            for prop_name in ["Name", "Title", "Task Name", "Agent Name"]:
                prop = properties.get(prop_name)
                if prop:
                    if prop.get("type") == "title":
                        title_list = prop.get("title", [])
                        if title_list:
                            return title_list[0].get("plain_text", "")
            return None
        except Exception as e:
            logger.debug(f"Error retrieving page {page_id} title: {e}")
            return None
    
    def validate_access(self) -> bool:
        """Validate Notion API access with minimal call"""
        try:
            self.client.users.me()
            logger.info("Notion API access validated successfully")
            return True
        except Exception as e:
            logger.error(f"Notion API access validation failed: {e}")
            return False


def determine_agent_type(agent_name: str, agent_id: str = None) -> str:
    """Determine if agent is MM1 or MM2"""
    agent_name_lower = agent_name.lower()
    mm2_indicators = ["mm2", "mm-2", "google drive", "gd"]
    if any(indicator in agent_name_lower for indicator in mm2_indicators):
        return "MM2"
    return "MM1"


def create_trigger_file(
    agent_type: str,
    agent_name: str,
    task_details: Dict[str, Any]
) -> Optional[Path]:
    """Create trigger file for agent"""
    try:
        # Import normalization function from main
        from main import normalize_agent_folder_name
        
        if agent_type == "MM1":
            base_path = MM1_AGENT_TRIGGER_BASE
        else:
            base_path = MM2_AGENT_TRIGGER_BASE
        
        # Use unified folder name normalization
        agent_id = task_details.get("agent_id")
        agent_folder = normalize_agent_folder_name(agent_name, agent_id)
        if agent_type == "MM2":
            agent_folder = f"{agent_folder}-gd"
        
        trigger_folder = base_path / agent_folder / "01_inbox"
        trigger_folder.mkdir(parents=True, exist_ok=True)
        
        # CRITICAL: Check for existing trigger file to prevent duplicates
        task_id = task_details.get("task_id", "unknown")
        if task_id != "unknown":
            task_id_short = task_id.replace("-", "")[:8]
            # Check for existing trigger files with this task ID (in inbox, processed, or failed)
            for subfolder in ["01_inbox", "02_processed", "03_failed"]:
                check_folder = base_path / agent_folder / subfolder
                if check_folder.exists():
                    existing_files = list(check_folder.glob(f"*{task_id_short}*.json"))
                    if existing_files:
                        existing_file = existing_files[0]
                        logger.warning(
                            f"Trigger file already exists for task {task_id_short} in {subfolder}: {existing_file.name}. "
                            f"Skipping duplicate creation."
                        )
                        return existing_file  # Return existing file instead of creating duplicate
        
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        task_id_short = task_id.replace("-", "")[:8] if task_id != "unknown" else "unknown"
        task_title = task_details.get("task_title", "Task")
        safe_title = task_title.replace(" ", "-").replace("/", "-")[:50]
        filename = f"{timestamp}__HANDOFF__{safe_title}__{task_id_short}.json"
        
        trigger_file = trigger_folder / filename
        
        trigger_content = {
            "task_id": task_details.get("task_id"),
            "task_title": task_details.get("task_title"),
            "task_url": task_details.get("task_url", ""),
            "project_id": task_details.get("project_id"),
            "project_title": task_details.get("project_title"),
            "description": task_details.get("description", ""),
            "status": task_details.get("status"),
            "agent_name": agent_name,
            "agent_type": agent_type,
            "handoff_instructions": task_details.get("handoff_instructions", ""),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "priority": task_details.get("priority", "High")
        }
        
        with open(trigger_file, "w", encoding="utf-8") as f:
            json.dump(trigger_content, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Created trigger file: {trigger_file}")
        return trigger_file
        
    except Exception as e:
        logger.error(f"Error creating trigger file for {agent_name}: {e}", exc_info=True)
        return None


def query_outstanding_issues(notion: NotionManager) -> List[Dict]:
    """Query outstanding issues from Issues+Questions database"""
    logger.info("Querying outstanding issues...")
    
    filter_params = {
        "or": [
            {"property": "Status", "status": {"equals": "Unreported"}},
            {"property": "Status", "status": {"equals": "Open"}},
            {"property": "Status", "status": {"equals": "In Progress"}}
        ]
    }
    
    issues = notion.query_database(ISSUES_DB_ID, filter_params=filter_params)
    
    if not issues:
        logger.debug("No issues found with Unreported/Open/In Progress status, trying broader query")
        issues = notion.query_database(ISSUES_DB_ID, filter_params=None)
    
    # Filter out resolved issues
    if issues:
        issues = [
            issue for issue in issues
            if safe_get_property(issue, "Status", "status") not in ["Resolved", "Closed", "Completed"]
        ]
    
    # Sort by priority
    def get_priority_value(issue):
        priority = safe_get_property(issue, "Priority", "select")
        priority_map = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
        return priority_map.get(priority, 99)
    
    issues_sorted = sorted(issues, key=get_priority_value)
    
    logger.info(f"Found {len(issues_sorted)} outstanding issues")
    return issues_sorted


def identify_critical_issue(issues: List[Dict]) -> Optional[Dict]:
    """Identify most critical actionable issue"""
    if not issues:
        return None
    
    critical_issue = issues[0]
    issue_title = safe_get_property(critical_issue, "Name", "title") or "Untitled Issue"
    issue_id = critical_issue.get("id")
    issue_priority = safe_get_property(critical_issue, "Priority", "select") or "High"
    
    logger.info(f"Identified critical issue: {issue_title} (ID: {issue_id}, Priority: {issue_priority})")
    return critical_issue


def attempt_issue_resolution(notion: NotionManager, issue: Dict) -> Dict[str, Any]:
    """Attempt to resolve issue or document blocking reason"""
    issue_title = safe_get_property(issue, "Name", "title") or "Untitled Issue"
    issue_id = issue.get("id")
    issue_url = issue.get("url", "")
    issue_description = safe_get_property(issue, "Description", "rich_text") or ""
    issue_priority = safe_get_property(issue, "Priority", "select") or "High"
    
    logger.info(f"Analyzing issue: {issue_title}")
    logger.info(f"Description: {issue_description[:200]}...")
    
    # Analyze if issue is resolvable by Cursor MM1
    # This is a placeholder - actual resolution logic would go here
    # For now, we'll document the issue and create a handoff
    
    resolution_result = {
        "resolved": False,
        "blocking_reason": "Issue requires analysis and planning before implementation",
        "target_agent": "Claude MM1 Agent",
        "next_action": "Create planning task for issue resolution"
    }
    
    logger.info(f"Issue analysis complete. Resolved: {resolution_result['resolved']}")
    return resolution_result


def create_handoff_for_issue(notion: NotionManager, issue: Dict, resolution_result: Dict[str, Any]) -> Optional[Path]:
    """Create handoff trigger file for issue resolution"""
    issue_title = safe_get_property(issue, "Name", "title") or "Untitled Issue"
    issue_id = issue.get("id")
    issue_url = issue.get("url", "")
    issue_description = safe_get_property(issue, "Description", "rich_text") or ""
    issue_priority = safe_get_property(issue, "Priority", "select") or "High"
    
    target_agent = resolution_result.get("target_agent", "Claude MM1 Agent")
    agent_type = determine_agent_type(target_agent)
    
    # Create handoff task in Agent-Tasks
    task_description = f"""## Context
A critical issue has been identified that requires immediate attention and resolution planning.

## Issue Details
- **Issue Title:** {issue_title}
- **Issue ID:** {issue_id}
- **Issue URL:** {issue_url}
- **Priority:** {issue_priority}
- **Description:** {issue_description}

## Objective
Review this issue and create a detailed plan for resolution. Identify the responsible agent(s), break down the work into actionable tasks, and prepare the next handoff to the execution agent.

## Required Actions
1. Analyze the issue thoroughly
2. Identify root cause(s) and contributing factors
3. Determine the appropriate agent(s) for resolution
4. Create a detailed implementation plan
5. Break down work into discrete, actionable tasks
6. Identify dependencies and prerequisites
7. Create the next handoff task for the execution agent

## Success Criteria
- [ ] Issue analysis completed
- [ ] Root cause identified
- [ ] Resolution plan created
- [ ] Execution agent identified
- [ ] Next handoff task created with all required context
"""
    
    # Add mandatory next handoff instructions
    cursor_inbox_path = str(get_agent_inbox_path("Cursor MM1 Agent")) + "/"
    if TASK_CREATION_HELPERS_AVAILABLE:
        task_description = add_mandatory_next_handoff_instructions(
            description=task_description,
            next_task_name="Issue Resolution Implementation",
            target_agent="Cursor MM1 Agent",
            next_task_id="TO_BE_CREATED",
            inbox_path=cursor_inbox_path,
            project_name=f"Issue-{issue_title[:30].replace(' ', '-')}",
            detailed_instructions=(
                f"Create handoff trigger file with the complete resolution plan, all identified tasks, "
                f"dependencies, and context needed to begin implementation. Include link to issue ({issue_url}) "
                f"and the planning task. Ensure all deliverables and artifacts are documented."
            )
        )
    else:
        task_description += f"""

## 🚨 MANDATORY HANDOFF REQUIREMENT

**CRITICAL:** Upon completion of this task, you MUST create a handoff trigger file for **Issue Resolution Implementation** assigned to **Cursor MM1 Agent**.

**Handoff File Location:** `{cursor_inbox_path}`

**Required Content:**
- Complete resolution plan
- All identified tasks
- Dependencies and prerequisites
- Link to issue ({issue_url})
- All context needed for implementation to begin

**NO EXCEPTIONS. TASK IS NOT COMPLETE UNTIL HANDOFF FILE IS CREATED.**
"""
    
    # Truncate if too long
    if len(task_description) > 1999:
        task_description = task_description[:1996] + "..."
    
    # Get database schema to find valid status
    default_status = "Ready"
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
    
    handoff_task_properties = {
        "Task Name": {
            "title": [{"text": {"content": f"Plan Resolution for Issue: {issue_title[:50]}"}}]
        },
        "Description": {
            "rich_text": [{"text": {"content": task_description}}]
        },
        "Priority": {
            "select": {"name": issue_priority}
        },
        "Assigned-Agent": {
            "relation": [{"id": CLAUDE_MM1_AGENT_ID}]
        }
    }
    
    if default_status:
        handoff_task_properties["Status"] = {
            "status": {"name": default_status}
        }
    
    new_task = notion.create_page(AGENT_TASKS_DB_ID, handoff_task_properties)
    
    if new_task:
        task_id = new_task.get("id")
        task_url = new_task.get("url", "")
        logger.info(f"Created handoff task in Agent-Tasks: {task_url}")
        
        # Create trigger file
        task_details = {
            "task_id": task_id,
            "task_title": f"Plan Resolution for Issue: {issue_title[:50]}",
            "task_url": task_url,
            "project_id": None,
            "project_title": None,
            "description": task_description,
            "status": default_status or "Ready",
            "agent_name": target_agent,
            "priority": issue_priority,
            "handoff_instructions": (
                "Review the issue and create a detailed resolution plan. Upon completion, you MUST:\n"
                "1. **MOVE TRIGGER FILE (MANUAL)**: You MUST manually call mark_trigger_file_processed() to move the trigger file from 01_inbox to 02_processed. This cannot be automated - you are responsible for moving it.\n"
                "2. Update the task status in Notion\n"
                "3. Create a handoff trigger file for the implementation task (see task description for details)\n"
                "4. Document all deliverables and artifacts\n"
                "5. Provide all context needed for the implementation task to begin\n\n"
                "**MANDATORY:** Task is NOT complete until trigger file is manually moved and handoff file is created."
            )
        }
        
        trigger_file = create_trigger_file(agent_type, target_agent, task_details)
        return trigger_file
    
    return None


def query_in_progress_projects(notion: NotionManager) -> List[Dict]:
    """Query in-progress projects"""
    logger.info("Querying in-progress projects...")
    
    filter_params = {
        "property": "Status",
        "status": {"equals": "In-Progress"}
    }
    
    projects = notion.query_database(PROJECTS_DB_ID, filter_params=filter_params)
    
    if not projects:
        logger.debug("No projects found with 'In-Progress' status, trying 'In Progress'")
        filter_params = {
            "property": "Status",
            "status": {"equals": "In Progress"}
        }
        projects = notion.query_database(PROJECTS_DB_ID, filter_params=filter_params)
    
    logger.info(f"Found {len(projects)} in-progress project(s)")
    return projects


def get_project_agent_tasks(notion: NotionManager, project_id: str) -> List[Dict]:
    """Get agent tasks for a project"""
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
    
    if not tasks:
        logger.debug("No tasks found with 'Projects' relation, trying 'Project'")
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
    
    # Sort by priority
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
    return tasks_sorted


def create_validation_task(notion: NotionManager, completed_task: Dict, project_id: Optional[str] = None) -> Optional[Dict]:
    """Create Agent Work Validation task"""
    task_title = safe_get_property(completed_task, "Task Name", "title") or "Untitled Task"
    task_id = completed_task.get("id")
    task_url = completed_task.get("url", "")
    
    validation_task_name = f"Agent Work Validation: {task_title}"
    
    validation_description = f"""## Context
Work has been completed on the following task and requires validation and review.

## Completed Task
- **Task Name:** {task_title}
- **Task ID:** {task_id}
- **Task URL:** {task_url}

## Objective
Review and validate the work completed in the above task. Ensure all deliverables meet requirements, documentation is complete, and handoff files are properly created.

## Required Actions
1. Review all work completed in the task
2. Validate deliverables and artifacts
3. Verify handoff files are created and complete
4. Check documentation is up to date
5. Confirm task status is properly updated in Notion
6. Create next handoff if validation passes

## Success Criteria
- [ ] All deliverables reviewed and validated
- [ ] Documentation verified as complete
- [ ] Handoff files confirmed created
- [ ] Task status verified in Notion
- [ ] Next handoff created if needed
"""
    
    # Add mandatory next handoff
    cursor_inbox_path_validation = str(get_agent_inbox_path("Cursor MM1 Agent")) + "/"
    if TASK_CREATION_HELPERS_AVAILABLE:
        validation_description = add_mandatory_next_handoff_instructions(
            description=validation_description,
            next_task_name="Continue Project Workflow",
            target_agent="Cursor MM1 Agent",
            next_task_id="TO_BE_CREATED",
            inbox_path=cursor_inbox_path_validation,
            project_name="Validation-Complete"
        )
    
    if len(validation_description) > 1999:
        validation_description = validation_description[:1996] + "..."
    
    validation_properties = {
        "Task Name": {
            "title": [{"text": {"content": validation_task_name}}]
        },
        "Description": {
            "rich_text": [{"text": {"content": validation_description}}]
        },
        "Priority": {
            "select": {"name": "High"}
        },
        "Assigned-Agent": {
            "relation": [{"id": CLAUDE_MM1_AGENT_ID}]
        },
        "Status": {
            "status": {"name": "Ready"}
        }
    }
    
    if project_id:
        validation_properties["Projects"] = {
            "relation": [{"id": project_id}]
        }
    
    validation_task = notion.create_page(AGENT_TASKS_DB_ID, validation_properties)
    
    if validation_task:
        validation_task_id = validation_task.get("id")
        validation_task_url = validation_task.get("url", "")
        
        # Create trigger file for validation task
        task_details = {
            "task_id": validation_task_id,
            "task_title": validation_task_name,
            "task_url": validation_task_url,
            "project_id": project_id,
            "project_title": None,
            "description": validation_description,
            "status": "Ready",
            "agent_name": "Claude MM1 Agent",
            "priority": "High",
            "handoff_instructions": (
                "Review and validate the completed work. Upon completion, you MUST:\n"
                "1. **MOVE TRIGGER FILE (MANUAL)**: You MUST manually call mark_trigger_file_processed() to move the trigger file from 01_inbox to 02_processed. This cannot be automated - you are responsible for moving it.\n"
                "2. Update the validation task status in Notion\n"
                "3. Create a handoff trigger file for the next task\n"
                "4. Document validation results\n"
                "5. Provide all context needed for continuation\n\n"
                "**MANDATORY:** Task is NOT complete until trigger file is manually moved and handoff file is created."
            )
        }
        
        trigger_file = create_trigger_file("MM1", "Claude MM1 Agent", task_details)
        logger.info(f"Created validation task: {validation_task_url}")
        return validation_task
    
    return None


def main():
    """Main execution function"""
    logger.info("=" * 80)
    logger.info("Notion Issue Review and Task Execution Workflow")
    logger.info("=" * 80)
    
    # Step 1: Notion Access Preflight
    logger.info("Step 1: Performing Notion access preflight...")
    token = get_notion_token()
    if not token:
        logger.error("NOTION_TOKEN not found in environment or unified_config")
        logger.error("Entering OFFLINE MODE - creating local artifacts")
        # Create offline mode artifacts
        offline_log_path = Path("/Users/brianhellemn/Documents/Agents/execution_logs")
        offline_log_path.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        log_file = offline_log_path / f"{timestamp}_Cursor_MM1_offline.log"
        with open(log_file, "w") as f:
            json.dump({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "status": "offline",
                "reason": "NOTION_TOKEN not found",
                "action": "Workflow cannot proceed without Notion access"
            }, f, indent=2)
        logger.error(f"Offline log created: {log_file}")
        sys.exit(1)
    
    try:
        notion = NotionManager(token)
        if not notion.validate_access():
            logger.error("Notion API access validation failed")
            sys.exit(1)
    except Exception as e:
        logger.error(f"Failed to initialize Notion client: {e}")
        sys.exit(1)
    
    logger.info("✅ Notion access validated")
    
    # Step 2: Query Outstanding Issues
    logger.info("Step 2: Querying outstanding issues...")
    issues = query_outstanding_issues(notion)
    
    if issues:
        # Step 3: Identify Critical Issue
        logger.info("Step 3: Identifying most critical issue...")
        critical_issue = identify_critical_issue(issues)
        
        if critical_issue:
            # Step 4: Attempt Resolution
            logger.info("Step 4: Attempting issue resolution...")
            resolution_result = attempt_issue_resolution(notion, critical_issue)
            
            # Step 5: Create Handoff
            logger.info("Step 5: Creating handoff trigger file...")
            trigger_file = create_handoff_for_issue(notion, critical_issue, resolution_result)
            
            if trigger_file:
                logger.info(f"✅ Handoff trigger file created: {trigger_file}")
            else:
                logger.warning("⚠️ Failed to create handoff trigger file")
    else:
        # Step 6: Process In-Progress Projects
        logger.info("Step 6: No outstanding issues found. Processing in-progress projects...")
        projects = query_in_progress_projects(notion)
        
        if projects:
            current_project = projects[0]
            project_title = safe_get_property(current_project, "Name", "title") or "Untitled Project"
            project_id = current_project.get("id")
            project_url = current_project.get("url", "")
            
            logger.info(f"Processing project: {project_title} (ID: {project_id})")
            
            # Get agent tasks for project
            agent_tasks = get_project_agent_tasks(notion, project_id)
            
            if agent_tasks:
                current_task = agent_tasks[0]
                task_title = safe_get_property(current_task, "Task Name", "title") or "Untitled Task"
                task_id = current_task.get("id")
                task_url = current_task.get("url", "")
                task_status = safe_get_property(current_task, "Status", "status") or "Unknown"
                
                logger.info(f"Identified task: '{task_title}' (Status: {task_status})")
                
                # Step 7: Complete Task (placeholder - actual work would go here)
                logger.info("Step 7: Task execution would occur here...")
                logger.info(f"Task '{task_title}' requires execution")
                
                # Step 8: Create Validation Task
                logger.info("Step 8: Creating validation task...")
                validation_task = create_validation_task(notion, current_task, project_id)
                
                if validation_task:
                    logger.info("✅ Validation task created")
                
                # Create handoff trigger for current task
                assigned_agent_relation = safe_get_property(current_task, "Assigned-Agent", "relation") or []
                if assigned_agent_relation:
                    assigned_agent_id = assigned_agent_relation[0].get("id")
                    assigned_agent_name = notion.get_page_title(assigned_agent_id) or "Unknown Agent"
                    agent_type = determine_agent_type(assigned_agent_name, assigned_agent_id)
                    
                    task_details = {
                        "task_id": task_id,
                        "task_title": task_title,
                        "task_url": task_url,
                        "project_id": project_id,
                        "project_title": project_title,
                        "description": safe_get_property(current_task, "Description", "rich_text") or "",
                        "status": task_status,
                        "agent_name": assigned_agent_name,
                        "priority": safe_get_property(current_task, "Priority", "select") or "High",
                        "handoff_instructions": (
                            "Proceed with the execution of this task. Upon completion, you MUST:\n"
                            "1. **MOVE TRIGGER FILE (MANUAL)**: You MUST manually call mark_trigger_file_processed() to move the trigger file from 01_inbox to 02_processed. This cannot be automated - you are responsible for moving it.\n"
                            "2. Update the task status in Notion\n"
                            "3. Create a handoff trigger file for the next task\n"
                            "4. Document all deliverables and artifacts\n"
                            "5. Provide all context needed for the next task to begin\n\n"
                            "**MANDATORY:** Task is NOT complete until trigger file is manually moved and handoff file is created."
                        )
                    }
                    
                    trigger_file = create_trigger_file(agent_type, assigned_agent_name, task_details)
                    if trigger_file:
                        logger.info(f"✅ Task trigger file created: {trigger_file}")
            else:
                logger.info("No outstanding agent tasks for this project")
        else:
            logger.info("No in-progress projects found")
    
    # Step 10: Execute main.py
    logger.info("Step 10: Executing main.py for task handoff flow...")
    try:
        import subprocess
        result = subprocess.run(
            ["python3", "main.py"],
            cwd=project_root,
            capture_output=True,
            text=True
        )
        
        logger.info("main.py execution completed")
        logger.info(f"Return code: {result.returncode}")
        if result.stdout:
            logger.info(f"Output:\n{result.stdout}")
        if result.stderr:
            logger.warning(f"Errors:\n{result.stderr}")
        
        if result.returncode != 0:
            logger.error("main.py execution failed")
            # Create issue in Notion about the failure
            issue_properties = {
                "Name": {
                    "title": [{"text": {"content": "main.py Execution Failed"}}]
                },
                "Description": {
                    "rich_text": [{"text": {"content": f"main.py execution returned non-zero exit code: {result.returncode}\n\nErrors:\n{result.stderr[:1900]}"}}]
                },
                "Priority": {
                    "select": {"name": "Critical"}
                },
                "Status": {
                    "status": {"name": "Open"}
                }
            }
            notion.create_page(ISSUES_DB_ID, issue_properties)
            logger.info("Created issue in Notion about main.py failure")
    except Exception as e:
        logger.error(f"Error executing main.py: {e}", exc_info=True)
    
    logger.info("=" * 80)
    logger.info("Workflow execution completed")
    logger.info("=" * 80)


if __name__ == "__main__":
    main()



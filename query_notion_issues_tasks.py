#!/usr/bin/env python3
"""
Query Notion for outstanding issues and in-progress projects/tasks.
Identifies the most critical and actionable item to work on.
"""

import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

try:
    from notion_client import Client
    NOTION_AVAILABLE = True
except ImportError:
    print("ERROR: notion-client not available. Install with: pip install notion-client")
    NOTION_AVAILABLE = False
    sys.exit(1)

# Import token manager
try:
    from shared_core.notion.token_manager import get_notion_token
    token = get_notion_token()
except ImportError:
    token = os.getenv("NOTION_TOKEN") or os.getenv("NOTION_API_TOKEN") or os.getenv("NOTION_API_KEY")

if not token:
    print("ERROR: No Notion token found")
    sys.exit(1)

# Database IDs
ISSUES_QUESTIONS_DB_ID = "229e73616c27808ebf06c202b10b5166"
PROJECTS_DB_ID = "286e73616c2781ffa450db2ecad4b0ba"
AGENT_TASKS_DB_ID = "284e73616c278018872aeb14e82e0392"

client = Client(auth=token)

def safe_get_property(page, property_name, property_type=None):
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
        
        return None
    except Exception as e:
        print(f"Error extracting property '{property_name}': {e}")
        return None

def query_outstanding_issues():
    """Query for outstanding issues."""
    print("\n=== Querying Outstanding Issues ===")
    
    filter_params = {
        "or": [
            {"property": "Status", "status": {"equals": "Unreported"}},
            {"property": "Status", "status": {"equals": "Open"}},
            {"property": "Status", "status": {"equals": "In Progress"}},
        ]
    }
    
    try:
        results = client.databases.query(
            database_id=ISSUES_QUESTIONS_DB_ID,
            filter=filter_params,
            sorts=[{"property": "Priority", "direction": "descending"}]
        )
        
        issues = results.get("results", [])
        
        # Filter out resolved issues
        issues = [
            issue for issue in issues
            if safe_get_property(issue, "Status", "status") not in ["Resolved", "Closed", "Completed"]
        ]
        
        if not issues:
            print("No outstanding issues found.")
            return None
        
        print(f"Found {len(issues)} outstanding issue(s).")
        
        # Get the most critical issue
        critical_issue = issues[0]
        issue_title = safe_get_property(critical_issue, "Name", "title") or "Untitled Issue"
        issue_id = critical_issue.get("id")
        issue_url = critical_issue.get("url", "")
        issue_priority = safe_get_property(critical_issue, "Priority", "select") or "Medium"
        issue_status = safe_get_property(critical_issue, "Status", "status") or "Unknown"
        issue_description = safe_get_property(critical_issue, "Description", "rich_text") or ""
        
        print(f"\nMost Critical Issue:")
        print(f"  Title: {issue_title}")
        print(f"  ID: {issue_id}")
        print(f"  Priority: {issue_priority}")
        print(f"  Status: {issue_status}")
        print(f"  URL: {issue_url}")
        print(f"  Description: {issue_description[:200]}...")
        
        return {
            "type": "issue",
            "id": issue_id,
            "title": issue_title,
            "url": issue_url,
            "priority": issue_priority,
            "status": issue_status,
            "description": issue_description,
            "page": critical_issue
        }
        
    except Exception as e:
        print(f"Error querying issues: {e}")
        return None

def query_in_progress_projects():
    """Query for in-progress projects and their tasks."""
    print("\n=== Querying In-Progress Projects ===")
    
    # Try "In-Progress" first
    filter_params = {
        "property": "Status",
        "status": {"equals": "In-Progress"}
    }
    
    try:
        results = client.databases.query(
            database_id=PROJECTS_DB_ID,
            filter=filter_params
        )
        
        projects = results.get("results", [])
        
        # If no results, try "In Progress" (with space)
        if not projects:
            filter_params = {
                "property": "Status",
                "status": {"equals": "In Progress"}
            }
            results = client.databases.query(
                database_id=PROJECTS_DB_ID,
                filter=filter_params
            )
            projects = results.get("results", [])
        
        if not projects:
            print("No in-progress projects found.")
            return None
        
        print(f"Found {len(projects)} in-progress project(s).")
        
        # Get the first project
        current_project = projects[0]
        project_title = safe_get_property(current_project, "Name", "title") or "Untitled Project"
        project_id = current_project.get("id")
        project_url = current_project.get("url", "")
        
        print(f"\nCurrent Project:")
        print(f"  Title: {project_title}")
        print(f"  ID: {project_id}")
        print(f"  URL: {project_url}")
        
        # Get agent tasks for this project
        print(f"\n=== Querying Agent-Tasks for Project ===")
        
        # Try "Projects" (plural) first
        filter_params = {
            "and": [
                {"property": "Projects", "relation": {"contains": project_id}},
                {"property": "Status", "status": {"does_not_equal": "Complete"}},
                {"property": "Status", "status": {"does_not_equal": "Completed"}},
            ]
        }
        
        try:
            task_results = client.databases.query(
                database_id=AGENT_TASKS_DB_ID,
                filter=filter_params,
                sorts=[{"property": "Priority", "direction": "descending"}]
            )
            agent_tasks = task_results.get("results", [])
        except Exception:
            # Try "Project" (singular) as fallback
            filter_params = {
                "and": [
                    {"property": "Project", "relation": {"contains": project_id}},
                    {"property": "Status", "status": {"does_not_equal": "Complete"}},
                    {"property": "Status", "status": {"does_not_equal": "Completed"}},
                ]
            }
            task_results = client.databases.query(
                database_id=AGENT_TASKS_DB_ID,
                filter=filter_params,
                sorts=[{"property": "Priority", "direction": "descending"}]
            )
            agent_tasks = task_results.get("results", [])
        
        # Filter out completed tasks
        agent_tasks = [
            task for task in agent_tasks
            if safe_get_property(task, "Status", "status") not in ["Complete", "Completed", "Done", "Closed"]
        ]
        
        if not agent_tasks:
            print(f"No outstanding agent tasks for project '{project_title}'.")
            return None
        
        print(f"Found {len(agent_tasks)} outstanding agent task(s).")
        
        # Get the highest priority task
        current_task = agent_tasks[0]
        task_title = safe_get_property(current_task, "Task Name", "title") or "Untitled Task"
        task_id = current_task.get("id")
        task_url = current_task.get("url", "")
        task_status = safe_get_property(current_task, "Status", "status") or "Unknown"
        task_priority = safe_get_property(current_task, "Priority", "select") or "Medium"
        task_description = safe_get_property(current_task, "Description", "rich_text") or ""
        
        # Get assigned agent
        assigned_agent_relation = safe_get_property(current_task, "Assigned-Agent", "relation") or []
        assigned_agent_id = None
        assigned_agent_name = "Unknown Agent"
        
        if assigned_agent_relation and len(assigned_agent_relation) > 0:
            assigned_agent_id = assigned_agent_relation[0].get("id")
            try:
                agent_page = client.pages.retrieve(page_id=assigned_agent_id)
                # Try to get agent name
                agent_name = safe_get_property(agent_page, "Name", "title") or safe_get_property(agent_page, "Agent Name", "title")
                if agent_name:
                    assigned_agent_name = agent_name
            except Exception:
                pass
        
        print(f"\nHighest Priority Task:")
        print(f"  Title: {task_title}")
        print(f"  ID: {task_id}")
        print(f"  Priority: {task_priority}")
        print(f"  Status: {task_status}")
        print(f"  Assigned Agent: {assigned_agent_name} ({assigned_agent_id})")
        print(f"  URL: {task_url}")
        print(f"  Description: {task_description[:200]}...")
        
        return {
            "type": "task",
            "id": task_id,
            "title": task_title,
            "url": task_url,
            "priority": task_priority,
            "status": task_status,
            "description": task_description,
            "assigned_agent_id": assigned_agent_id,
            "assigned_agent_name": assigned_agent_name,
            "project_id": project_id,
            "project_title": project_title,
            "project_url": project_url,
            "page": current_task
        }
        
    except Exception as e:
        print(f"Error querying projects: {e}")
        import traceback
        traceback.print_exc()
        return None

def main():
    """Main execution."""
    print("=" * 80)
    print("Notion Issues & Tasks Query")
    print("=" * 80)
    
    # First, check for outstanding issues
    critical_item = query_outstanding_issues()
    
    # If no issues, check for in-progress projects
    if not critical_item:
        critical_item = query_in_progress_projects()
    
    if not critical_item:
        print("\n=== No Critical Items Found ===")
        print("No outstanding issues or in-progress projects/tasks found.")
        return None
    
    print("\n" + "=" * 80)
    print("SELECTED CRITICAL ITEM:")
    print("=" * 80)
    print(f"Type: {critical_item['type']}")
    print(f"Title: {critical_item['title']}")
    print(f"ID: {critical_item['id']}")
    print(f"Priority: {critical_item['priority']}")
    print(f"URL: {critical_item['url']}")
    print("=" * 80)
    
    return critical_item

if __name__ == "__main__":
    result = main()
    if result:
        # Output JSON for use by other scripts
        import json
        print("\n=== JSON Output ===")
        # Remove 'page' from output (too large)
        output = {k: v for k, v in result.items() if k != 'page'}
        print(json.dumps(output, indent=2))

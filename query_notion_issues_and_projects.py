#!/usr/bin/env python3
"""
Query Notion for outstanding issues and in-progress projects
"""

import os
import sys
import json
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

try:
    from notion_client import Client
    from shared_core.notion.token_manager import get_notion_token
    NOTION_AVAILABLE = True
except ImportError as e:
    print(f"Error importing dependencies: {e}")
    NOTION_AVAILABLE = False
    sys.exit(1)

# Database IDs
ISSUES_QUESTIONS_DB_ID = os.getenv("ISSUES_QUESTIONS_DB_ID", "229e73616c27808ebf06c202b10b5166")
AGENT_TASKS_DB_ID = os.getenv("AGENT_TASKS_DB_ID", "284e73616c278018872aeb14e82e0392")
PROJECTS_DB_ID = os.getenv("PROJECTS_DB_ID", "286e73616c2781ffa450db2ecad4b0ba")

def safe_get_property(page: dict, property_name: str, property_type: str = None):
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
        
        elif actual_type == "multi_select":
            multi_select_list = prop.get("multi_select", [])
            return [item.get("name") for item in multi_select_list if item.get("name")]
        
        return None
    except Exception as e:
        print(f"Error extracting property '{property_name}': {e}")
        return None

def query_outstanding_issues(client: Client):
    """Query for outstanding issues."""
    print("\n" + "="*80)
    print("Querying Outstanding Issues...")
    print("="*80)
    
    # Issues+Questions DB status options observed in workspace:
    # Resolved, Troubleshooting, Waiting on Client, Reported + Waiting For Response,
    # Solution In Progress, Unreported
    filter_params = {
        "or": [
            {"property": "Status", "status": {"equals": "Unreported"}},
            {"property": "Status", "status": {"equals": "Troubleshooting"}},
            {"property": "Status", "status": {"equals": "Solution In Progress"}},
            {"property": "Status", "status": {"equals": "Reported + Waiting For Response"}},
            {"property": "Status", "status": {"equals": "Waiting on Client"}},
        ]
    }
    
    try:
        response = client.databases.query(
            database_id=ISSUES_QUESTIONS_DB_ID,
            filter=filter_params,
            page_size=100
        )
        issues = response.get("results", [])
        
        # Filter out resolved issues (defensive in case query returns extras)
        issues = [
            issue for issue in issues
            if safe_get_property(issue, "Status", "status") not in ["Resolved", "Closed", "Completed"]
        ]
        
        print(f"Found {len(issues)} outstanding issues")
        
        # Sort by priority
        def get_priority_value(issue):
            priority = safe_get_property(issue, "Priority", "select")
            priority_map = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
            return priority_map.get(priority, 99)
        
        issues_sorted = sorted(issues, key=get_priority_value)
        
        if issues_sorted:
            critical_issue = issues_sorted[0]
            issue_title = safe_get_property(critical_issue, "Name", "title") or "Untitled Issue"
            issue_id = critical_issue.get("id")
            issue_url = critical_issue.get("url", "")
            issue_description = safe_get_property(critical_issue, "Description", "rich_text") or ""
            issue_priority = safe_get_property(critical_issue, "Priority", "select") or "High"
            issue_status = safe_get_property(critical_issue, "Status", "status") or "Unknown"
            
            print(f"\nMost Critical Issue:")
            print(f"  Title: {issue_title}")
            print(f"  ID: {issue_id}")
            print(f"  Priority: {issue_priority}")
            print(f"  Status: {issue_status}")
            print(f"  URL: {issue_url}")
            print(f"  Description: {issue_description[:200]}...")
            
            return {
                "found": True,
                "issue": critical_issue,
                "title": issue_title,
                "id": issue_id,
                "url": issue_url,
                "description": issue_description,
                "priority": issue_priority,
                "status": issue_status
            }
        else:
            print("No outstanding issues found")
            return {"found": False}
            
    except Exception as e:
        print(f"Error querying issues: {e}")
        import traceback
        traceback.print_exc()
        return {"found": False, "error": str(e)}

def query_in_progress_projects(client: Client):
    """Query for in-progress projects."""
    print("\n" + "="*80)
    print("Querying In-Progress Projects...")
    print("="*80)
    
    # Try "In-Progress" first
    filter_params = {
        "property": "Status",
        "status": {"equals": "In-Progress"}
    }
    
    try:
        response = client.databases.query(
            database_id=PROJECTS_DB_ID,
            filter=filter_params,
            page_size=100
        )
        projects = response.get("results", [])
        
        # If no results, try "In Progress" (with space)
        if not projects:
            filter_params = {
                "property": "Status",
                "status": {"equals": "In Progress"}
            }
            response = client.databases.query(
                database_id=PROJECTS_DB_ID,
                filter=filter_params,
                page_size=100
            )
            projects = response.get("results", [])
        
        if not projects:
            print("No in-progress projects found")
            return {"found": False}
        
        print(f"Found {len(projects)} in-progress project(s)")
        
        # Process first project
        current_project = projects[0]
        project_title = safe_get_property(current_project, "Name", "title") or "Untitled Project"
        project_id = current_project.get("id")
        project_url = current_project.get("url", "")
        
        print(f"\nCurrent Project:")
        print(f"  Title: {project_title}")
        print(f"  ID: {project_id}")
        print(f"  URL: {project_url}")
        
        # Get agent tasks for this project.
        #
        # NOTE: Agent-Tasks schema in this workspace uses a relation named "🤖 Agent-Projects".
        # Older scripts used "Projects"/"Project" which can 400 if the property doesn't exist.
        relation_props_to_try = ["🤖 Agent-Projects", "Projects", "Project"]
        agent_tasks = []
        last_error = None

        for rel_prop in relation_props_to_try:
            try:
                filter_params = {
                    "and": [
                        {"property": rel_prop, "relation": {"contains": project_id}},
                    ]
                }
                response = client.databases.query(
                    database_id=AGENT_TASKS_DB_ID,
                    filter=filter_params,
                    page_size=100
                )
                agent_tasks = response.get("results", [])
                if agent_tasks:
                    break
            except Exception as e:
                last_error = e
                continue

        if last_error and not agent_tasks:
            print(f"Error querying agent tasks: {last_error}")
            import traceback
            traceback.print_exc()
            return {
                "found": True,
                "project": current_project,
                "project_title": project_title,
                "project_id": project_id,
                "project_url": project_url,
                "error": str(last_error)
            }

        # Filter out completed/archived tasks (Agent-Tasks DB uses "Completed", not "Complete")
        agent_tasks = [
            task for task in agent_tasks
            if safe_get_property(task, "Status", "status") not in ["Completed", "Archived"]
        ]

        print(f"\nFound {len(agent_tasks)} outstanding agent task(s) for project")

        if agent_tasks:
            # Prioritize tasks
            def get_task_priority(task):
                status = safe_get_property(task, "Status", "status")
                priority_map = {
                    "In Progress": 0,
                    "Review": 1,
                    "Ready": 2,
                    "Planning": 3,
                    "Draft": 4,
                    "Blocked": 5,
                    "Failed": 6,
                    "Completed": 99,
                    "Archived": 100,
                }
                return priority_map.get(status or "", 98)
            
            agent_tasks_sorted = sorted(agent_tasks, key=get_task_priority)
            current_task = agent_tasks_sorted[0]
            
            task_title = safe_get_property(current_task, "Task Name", "title") or "Untitled Task"
            task_id = current_task.get("id")
            task_url = current_task.get("url", "")
            task_status = safe_get_property(current_task, "Status", "status") or "Unknown"
            task_description = safe_get_property(current_task, "Description", "rich_text") or ""
            
            print(f"\nCurrent Task:")
            print(f"  Title: {task_title}")
            print(f"  ID: {task_id}")
            print(f"  Status: {task_status}")
            print(f"  URL: {task_url}")
            print(f"  Description: {task_description[:200]}...")
            
            return {
                "found": True,
                "project": current_project,
                "project_title": project_title,
                "project_id": project_id,
                "project_url": project_url,
                "task": current_task,
                "task_title": task_title,
                "task_id": task_id,
                "task_url": task_url,
                "task_status": task_status,
                "task_description": task_description,
                "all_tasks": agent_tasks
            }
        else:
            return {
                "found": True,
                "project": current_project,
                "project_title": project_title,
                "project_id": project_id,
                "project_url": project_url,
                "task": None
            }
                
    except Exception as e:
        print(f"Error querying projects: {e}")
        import traceback
        traceback.print_exc()
        return {"found": False, "error": str(e)}

def main():
    """Main execution."""
    if not NOTION_AVAILABLE:
        print("Notion client not available")
        sys.exit(1)
    
    try:
        token = get_notion_token()
        if not token:
            print("❌ Error: Could not get Notion token")
            sys.exit(1)
        
        client = Client(auth=token)
    except Exception as e:
        print(f"❌ Error initializing Notion client: {e}")
        sys.exit(1)
    
    # Query outstanding issues
    issues_result = query_outstanding_issues(client)
    
    # Query in-progress projects
    projects_result = query_in_progress_projects(client)
    
    # Output results as JSON for use by other scripts
    output = {
        "issues": issues_result,
        "projects": projects_result
    }
    
    output_file = Path(__file__).parent / "notion_query_results.json"
    with open(output_file, "w") as f:
        json.dump(output, f, indent=2, default=str)
    
    print(f"\n{'='*80}")
    print("Results saved to notion_query_results.json")
    print(f"{'='*80}")
    
    return output

if __name__ == "__main__":
    main()

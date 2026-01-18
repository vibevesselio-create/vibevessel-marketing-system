#!/usr/bin/env python3
"""
Check Notion for outstanding issues and in-progress projects
"""

import os
import sys
import json
from pathlib import Path

# Add project root to path
script_dir = Path(__file__).parent
if str(script_dir) not in sys.path:
    sys.path.insert(0, str(script_dir))

try:
    from notion_client import Client
    from main import (
        NotionManager,
        safe_get_property,
        get_notion_token,
        ISSUES_QUESTIONS_DB_ID,
        PROJECTS_DB_ID,
        AGENT_TASKS_DB_ID
    )
except ImportError as e:
    print(f"Error importing required modules: {e}")
    sys.exit(1)

def check_outstanding_issues(notion: NotionManager):
    """Check for outstanding issues"""
    print("=" * 80)
    print("Checking for outstanding issues...")
    print("=" * 80)
    
    # Filter for outstanding issues
    filter_params = {
        "or": [
            {"property": "Status", "status": {"equals": "Unreported"}},
            {"property": "Status", "status": {"equals": "Open"}},
            {"property": "Status", "status": {"equals": "In Progress"}}
        ]
    }
    
    issues = notion.query_database(ISSUES_QUESTIONS_DB_ID, filter_params=filter_params)
    
    # Filter out resolved issues
    if issues:
        issues = [
            issue for issue in issues
            if safe_get_property(issue, "Status", "status") not in ["Resolved", "Closed", "Completed"]
        ]
    
    if not issues:
        print("No outstanding issues found.")
        return None
    
    print(f"Found {len(issues)} outstanding issue(s).")
    
    # Sort by priority
    def get_priority_value(issue):
        priority = safe_get_property(issue, "Priority", "select")
        priority_map = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
        return priority_map.get(priority, 99)
    
    issues_sorted = sorted(issues, key=get_priority_value)
    
    # Display all issues
    for idx, issue in enumerate(issues_sorted, 1):
        title = safe_get_property(issue, "Name", "title") or "Untitled Issue"
        priority = safe_get_property(issue, "Priority", "select") or "Unknown"
        status = safe_get_property(issue, "Status", "status") or "Unknown"
        issue_id = issue.get("id")
        issue_url = issue.get("url", "")
        description = safe_get_property(issue, "Description", "rich_text") or ""
        
        print(f"\n{idx}. [{priority}] {title}")
        print(f"   Status: {status}")
        print(f"   ID: {issue_id}")
        print(f"   URL: {issue_url}")
        if description:
            print(f"   Description: {description[:200]}...")
    
    # Return the most critical issue
    critical_issue = issues_sorted[0]
    return {
        "issue": critical_issue,
        "title": safe_get_property(critical_issue, "Name", "title") or "Untitled Issue",
        "id": critical_issue.get("id"),
        "url": critical_issue.get("url", ""),
        "priority": safe_get_property(critical_issue, "Priority", "select") or "High",
        "status": safe_get_property(critical_issue, "Status", "status") or "Unknown",
        "description": safe_get_property(critical_issue, "Description", "rich_text") or ""
    }

def check_in_progress_projects(notion: NotionManager):
    """Check for in-progress projects"""
    print("\n" + "=" * 80)
    print("Checking for in-progress projects...")
    print("=" * 80)
    
    # Filter for in-progress projects
    filter_params = {
        "property": "Status",
        "status": {"equals": "In-Progress"}
    }
    
    projects = notion.query_database(PROJECTS_DB_ID, filter_params=filter_params)
    
    # Try "In Progress" (with space) if no results
    if not projects:
        filter_params = {
            "property": "Status",
            "status": {"equals": "In Progress"}
        }
        projects = notion.query_database(PROJECTS_DB_ID, filter_params=filter_params)
    
    if not projects:
        print("No in-progress projects found.")
        return None
    
    print(f"Found {len(projects)} in-progress project(s).")
    
    # Process first project
    current_project = projects[0]
    project_title = safe_get_property(current_project, "Name", "title") or "Untitled Project"
    project_id = current_project.get("id")
    project_url = current_project.get("url", "")
    
    print(f"\nCurrent Project: {project_title}")
    print(f"ID: {project_id}")
    print(f"URL: {project_url}")
    
    # Get agent tasks for this project
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
    
    agent_tasks = notion.query_database(AGENT_TASKS_DB_ID, filter_params=filter_params)
    
    # Try "Project" (singular) if no results
    if not agent_tasks:
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
        agent_tasks = notion.query_database(AGENT_TASKS_DB_ID, filter_params=filter_params)
    
    print(f"\nFound {len(agent_tasks)} outstanding agent task(s) for this project.")
    
    # Display all tasks
    for idx, task in enumerate(agent_tasks, 1):
        task_title = safe_get_property(task, "Task Name", "title") or "Untitled Task"
        task_status = safe_get_property(task, "Status", "status") or "Unknown"
        task_id = task.get("id")
        task_url = task.get("url", "")
        
        # Get assigned agent
        assigned_agent_relation = safe_get_property(task, "Assigned-Agent", "relation") or []
        assigned_agent_name = "Unassigned"
        if assigned_agent_relation:
            assigned_agent_id = assigned_agent_relation[0].get("id")
            assigned_agent_name = notion.get_page_title(assigned_agent_id) or f"Agent_{assigned_agent_id[:8]}"
        
        print(f"\n{idx}. [{task_status}] {task_title}")
        print(f"   Assigned to: {assigned_agent_name}")
        print(f"   ID: {task_id}")
        print(f"   URL: {task_url}")
    
    return {
        "project": current_project,
        "project_title": project_title,
        "project_id": project_id,
        "project_url": project_url,
        "agent_tasks": agent_tasks
    }

def main():
    """Main execution"""
    # Get token
    token = get_notion_token()
    if not token:
        print("ERROR: Could not get Notion token")
        sys.exit(1)
    
    # Initialize Notion client
    try:
        notion = NotionManager(token)
    except Exception as e:
        print(f"ERROR: Failed to initialize Notion client: {e}")
        sys.exit(1)
    
    # Check for issues first
    critical_issue = check_outstanding_issues(notion)
    
    if critical_issue:
        print("\n" + "=" * 80)
        print("CRITICAL ISSUE IDENTIFIED")
        print("=" * 80)
        print(f"Issue: {critical_issue['title']}")
        print(f"Priority: {critical_issue['priority']}")
        print(f"URL: {critical_issue['url']}")
        
        # Save to file for next step
        output_file = script_dir / "current_critical_issue.json"
        with open(output_file, "w") as f:
            json.dump(critical_issue, f, indent=2, default=str)
        print(f"\nIssue details saved to: {output_file}")
        return "issue"
    else:
        # Check for in-progress projects
        project_info = check_in_progress_projects(notion)
        
        if project_info:
            print("\n" + "=" * 80)
            print("IN-PROGRESS PROJECT IDENTIFIED")
            print("=" * 80)
            print(f"Project: {project_info['project_title']}")
            print(f"Outstanding Tasks: {len(project_info['agent_tasks'])}")
            
            # Save to file for next step
            output_file = script_dir / "current_project_info.json"
            with open(output_file, "w") as f:
                json.dump(project_info, f, indent=2, default=str)
            print(f"\nProject details saved to: {output_file}")
            return "project"
        else:
            print("\n" + "=" * 80)
            print("NO OUTSTANDING WORK FOUND")
            print("=" * 80)
            return "none"

if __name__ == "__main__":
    result = main()
    print(f"\nResult: {result}")

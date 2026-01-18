#!/usr/bin/env python3
"""Temporary script to query Notion issues"""

import sys
import os
from pathlib import Path

# Add project root to path
script_dir = Path(__file__).parent
if str(script_dir) not in sys.path:
    sys.path.insert(0, str(script_dir))

# Import from main.py
from main import (
    get_notion_token,
    NotionManager,
    safe_get_property,
    ISSUES_DB_ID,
    PROJECTS_DB_ID,
    AGENT_TASKS_DB_ID
)

def query_outstanding_issues():
    """Query for outstanding issues"""
    token = get_notion_token()
    if not token:
        print("ERROR: Could not get Notion token")
        return None
    
    notion = NotionManager(token)
    
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
    
    issues = notion.query_database(ISSUES_DB_ID, filter_params=filter_params)
    
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
    
    return issues_sorted

def query_in_progress_projects():
    """Query for in-progress projects"""
    token = get_notion_token()
    if not token:
        print("ERROR: Could not get Notion token")
        return None
    
    notion = NotionManager(token)
    
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

if __name__ == "__main__":
    print("Querying outstanding issues...")
    issues = query_outstanding_issues()
    
    if issues:
        print(f"\nFound {len(issues)} outstanding issues:")
        for i, issue in enumerate(issues[:5], 1):
            title = safe_get_property(issue, "Name", "title") or "Untitled"
            priority = safe_get_property(issue, "Priority", "select") or "Unknown"
            status = safe_get_property(issue, "Status", "status") or "Unknown"
            issue_id = issue.get("id")
            issue_url = issue.get("url", "")
            print(f"\n{i}. {title}")
            print(f"   Priority: {priority}, Status: {status}")
            print(f"   ID: {issue_id}")
            print(f"   URL: {issue_url}")
        
        # Return the most critical issue
        critical_issue = issues[0]
        print(f"\n=== MOST CRITICAL ISSUE ===")
        print(f"Title: {safe_get_property(critical_issue, 'Name', 'title')}")
        print(f"Priority: {safe_get_property(critical_issue, 'Priority', 'select')}")
        print(f"Status: {safe_get_property(critical_issue, 'Status', 'status')}")
        print(f"ID: {critical_issue.get('id')}")
        print(f"URL: {critical_issue.get('url')}")
    else:
        print("\nNo outstanding issues found. Querying in-progress projects...")
        projects = query_in_progress_projects()
        
        if projects:
            print(f"\nFound {len(projects)} in-progress project(s):")
            for i, project in enumerate(projects, 1):
                title = safe_get_property(project, "Name", "title") or "Untitled"
                project_id = project.get("id")
                project_url = project.get("url", "")
                print(f"\n{i}. {title}")
                print(f"   ID: {project_id}")
                print(f"   URL: {project_url}")
        else:
            print("\nNo in-progress projects found.")

#!/usr/bin/env python3
"""Helper script to query Notion for outstanding issues"""
import os
import sys
from pathlib import Path

# Add project root to path
script_dir = Path(__file__).parent
if str(script_dir) not in sys.path:
    sys.path.insert(0, str(script_dir))

try:
    from notion_client import Client
except ImportError:
    print("ERROR: notion-client not available")
    sys.exit(1)

# Get token
def get_notion_token():
    try:
        from shared_core.notion.token_manager import get_notion_token as _get_token
        return _get_token()
    except ImportError:
        pass
    
    return (
        os.getenv("NOTION_TOKEN") or
        os.getenv("NOTION_API_TOKEN") or
        os.getenv("VV_AUTOMATIONS_WS_TOKEN")
    )

ISSUES_DB_ID = "229e73616c27808ebf06c202b10b5166"

token = get_notion_token()
if not token:
    print("ERROR: No Notion token found")
    sys.exit(1)

client = Client(auth=token)

# Query for outstanding issues
try:
    # Try to get data source ID first
    db = client.databases.retrieve(database_id=ISSUES_DB_ID)
    data_sources = db.get("data_sources", [])
    
    if data_sources:
        data_source_id = data_sources[0].get("id")
        # Query using data_sources API
        filter_params = {
            "or": [
                {"property": "Status", "status": {"equals": "Unreported"}},
                {"property": "Status", "status": {"equals": "Troubleshooting"}},
                {"property": "Status", "status": {"equals": "Solution In Progress"}},
            ]
        }
        
        try:
            response = client.data_sources.query(
                data_source_id=data_source_id,
                filter=filter_params
            )
            issues = response.get("results", [])
        except Exception as e:
            print(f"data_sources.query failed: {e}, trying legacy API")
            # Fallback to legacy API
            response = client.databases.query(
                database_id=ISSUES_DB_ID,
                filter=filter_params
            )
            issues = response.get("results", [])
    else:
        # Fallback to legacy API
        filter_params = {
            "or": [
                {"property": "Status", "status": {"equals": "Unreported"}},
                {"property": "Status", "status": {"equals": "Troubleshooting"}},
                {"property": "Status", "status": {"equals": "Solution In Progress"}},
            ]
        }
        response = client.databases.query(
            database_id=ISSUES_DB_ID,
            filter=filter_params
        )
        issues = response.get("results", [])
    
    # Filter out resolved issues
    outstanding_issues = []
    for issue in issues:
        props = issue.get("properties", {})
        status_prop = props.get("Status", {})
        if status_prop.get("type") == "status":
            status = status_prop.get("status", {})
            status_name = status.get("name", "")
            if status_name not in ["Resolved"]:
                outstanding_issues.append(issue)
    
    # Sort by priority
    def get_priority_value(issue):
        props = issue.get("properties", {})
        priority_prop = props.get("Priority", {})
        if priority_prop.get("type") == "select":
            priority = priority_prop.get("select")
            if priority:
                priority_name = priority.get("name", "")
                priority_map = {"Critical": 0, "Highest": 1, "High": 2, "Medium": 3, "Low": 4, "Lowest": 5}
                return priority_map.get(priority_name, 99)
        return 99
    
    outstanding_issues.sort(key=get_priority_value)
    
    # Print results as JSON
    import json
    results = []
    for issue in outstanding_issues:
        props = issue.get("properties", {})
        
        # Get title
        name_prop = props.get("Name", {})
        title = ""
        if name_prop.get("type") == "title":
            title_list = name_prop.get("title", [])
            if title_list:
                title = title_list[0].get("plain_text", "")
        
        # Get status
        status_prop = props.get("Status", {})
        status = ""
        if status_prop.get("type") == "status":
            status = status_prop.get("status", {}).get("name", "")
        
        # Get priority
        priority_prop = props.get("Priority", {})
        priority = ""
        if priority_prop.get("type") == "select":
            select_obj = priority_prop.get("select")
            if select_obj:
                priority = select_obj.get("name", "")
        
        # Get description
        desc_prop = props.get("Description", {})
        description = ""
        if desc_prop.get("type") == "rich_text":
            desc_list = desc_prop.get("rich_text", [])
            if desc_list:
                description = desc_list[0].get("plain_text", "")
        
        results.append({
            "id": issue.get("id"),
            "url": issue.get("url", ""),
            "title": title,
            "status": status,
            "priority": priority,
            "description": description
        })
    
    print(json.dumps(results, indent=2))
    
except Exception as e:
    print(f"ERROR: {e}", file=sys.stderr)
    import traceback
    traceback.print_exc()
    sys.exit(1)

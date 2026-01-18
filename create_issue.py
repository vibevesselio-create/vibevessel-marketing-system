#!/usr/bin/env python3
"""Create an issue in Notion Issues+Questions database."""
import requests

NOTION_TOKEN = "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"
ISSUES_DB_ID = "229e7361-6c27-808e-bf06-c202b10b5166"

HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28"
}

def create_issue(title, description, priority="High"):
    """Create an issue in Notion."""
    url = "https://api.notion.com/v1/pages"
    
    payload = {
        "parent": {"database_id": ISSUES_DB_ID},
        "properties": {
            "Name": {
                "title": [{"text": {"content": title}}]
            },
            "Description": {
                "rich_text": [{"text": {"content": description[:2000]}}]
            },
            "Priority": {
                "select": {"name": priority}
            },
            "Type": {
                "multi_select": [{"name": "Script Issue"}, {"name": "Bug"}]
            },
            "Tags": {
                "multi_select": [
                    {"name": "orchestrator"},
                    {"name": "critical-bug"},
                    {"name": "resolved"}
                ]
            },
            "Status": {
                "status": {"name": "Resolved"}
            }
        }
    }
    
    response = requests.post(url, headers=HEADERS, json=payload)
    if response.status_code == 200:
        data = response.json()
        print(f"Created issue: {data.get('url')}")
        return data
    else:
        print(f"Error creating issue: {response.status_code}")
        print(response.text)
        return None

if __name__ == "__main__":
    title = "[RESOLVED] Runaway continuous_handoff_orchestrator.py Creating Duplicate Trigger Files"
    description = """## Issue Summary
A runaway continuous_handoff_orchestrator.py process (PID 61770) was continuously creating duplicate trigger files in agent inbox folders.

## Root Cause
Script running with --interval 60 since Tuesday, creating new handoff files every 60 seconds for the same tasks.

## Impact
- 42+ duplicate trigger files for task 2e3e7361
- 3098+ total files with "continuous_handoff" content
- 10MB+ stderr log file
- Agent inbox flooding

## Resolution (2026-01-09)
1. Killed process: kill 61770
2. Archived 42 duplicates to 04_archived_duplicates_20260109/
3. Reduced inbox from 46 to 4 legitimate files

## Recommendations
1. Add deduplication at file creation
2. Add max iteration limit
3. Add inbox monitoring/alerting

Resolved by: Claude Code Agent - 2026-01-09T01:45Z"""
    
    result = create_issue(title, description, priority="High")
    if result:
        print(f"\nIssue ID: {result.get('id')}")

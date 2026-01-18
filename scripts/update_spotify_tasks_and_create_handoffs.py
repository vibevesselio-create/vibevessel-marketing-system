#!/usr/bin/env python3
"""
Update Spotify review tasks to Ready status, assign agents, and create handoff files.
"""
import os
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from shared_core.notion.token_manager import get_notion_token
from notion_client import Client
import requests
import json
from datetime import datetime, timezone

# Agent IDs
CURSOR_MM1_AGENT_ID = "249e7361-6c27-8100-8a74-de7eabb9fc8d"
CLAUDE_CODE_AGENT_ID = None  # Will need to look up or use a different identifier

# Task assignments - based on our review task creation
TASK_ASSIGNMENTS = {
    "Review Query Filter Implementation - Spotify Track Inclusion": "Cursor MM1 Agent",
    "Review build_eligibility_filter() - Spotify Track Support": "Cursor MM1 Agent",
    "Review DL Property Setting for Spotify Tracks": "Cursor MM1 Agent",
    "Review YouTube Search & Matching Functionality": "Claude Code Agent",
    "Review Spotify Track Processing Flow - End-to-End": "Claude Code Agent",
    "Review Database ID Configuration & Environment Setup": "Cursor MM1 Agent",
    "End-to-End Testing - Spotify Playlist Download Workflow": "Claude Code Agent",
    "Error Handling & Edge Cases Review": "Claude Code Agent",
    "Performance & Optimization Review": "Cursor MM1 Agent",
    "Code Review & Documentation": "Claude Code Agent",
}

def get_agent_id(agent_name):
    """Get agent page ID from agent name"""
    if agent_name == "Cursor MM1 Agent":
        return CURSOR_MM1_AGENT_ID
    # For other agents, we'd need to look them up
    return None

def update_task_and_create_handoff(task, agent_name, token):
    """Update task status to Ready, assign agent, and create handoff file"""
    
    task_id = task.get('id')
    props = task.get('properties', {})
    task_name = props.get('Task Name', {}).get('title', [{}])[0].get('text', {}).get('content', 'Unknown')
    
    headers = {
        'Authorization': f'Bearer {token}',
        'Notion-Version': '2022-06-28',
        'Content-Type': 'application/json'
    }
    
    # Update task: set status to "Ready" and assign agent
    agent_id = get_agent_id(agent_name)
    
    update_properties = {
        "Status": {"status": {"name": "Ready"}}
    }
    
    if agent_id:
        update_properties["Assigned-Agent"] = {
            "relation": [{"id": agent_id}]
        }
    
    try:
        response = requests.patch(
            f'https://api.notion.com/v1/pages/{task_id}',
            headers=headers,
            json={"properties": update_properties}
        )
        
        if response.status_code == 200:
            print(f"✅ Updated task: {task_name[:60]}...")
            print(f"   Status: Planning → Ready")
            if agent_id:
                print(f"   Assigned to: {agent_name}")
            return True
        else:
            print(f"⚠️  Failed to update task {task_name[:40]}: {response.status_code}")
            print(response.text[:300])
            return False
            
    except Exception as e:
        print(f"❌ Error updating task {task_name[:40]}: {e}")
        return False

def main():
    token = get_notion_token()
    if not token:
        print("❌ NOTION_TOKEN not found")
        sys.exit(1)
    
    issue_id = '2e3e7361-6c27-818d-9a9b-c5508f52d916'
    db_id = '284e7361-6c27-8018-872a-eb14e82e0392'
    
    headers = {
        'Authorization': f'Bearer {token}',
        'Notion-Version': '2022-06-28',
        'Content-Type': 'application/json'
    }
    
    # Query for tasks related to our issue
    response = requests.post(
        f'https://api.notion.com/v1/databases/{db_id}/query',
        headers=headers,
        json={
            "filter": {
                "or": [
                    {"property": "Issues+Questions", "relation": {"contains": issue_id}},
                    {"property": "Issues+Questions 1", "relation": {"contains": issue_id}}
                ]
            }
        }
    )
    
    if response.status_code != 200:
        print(f"❌ Error querying tasks: {response.status_code}")
        print(response.text[:500])
        sys.exit(1)
    
    tasks = response.json().get('results', [])
    print(f"Found {len(tasks)} tasks related to Spotify issue")
    print("=" * 80)
    
    updated_count = 0
    
    for task in tasks:
        props = task.get('properties', {})
        task_name = props.get('Task Name', {}).get('title', [{}])[0].get('text', {}).get('content', 'Unknown')
        
        # Find assignment for this task
        agent_name = TASK_ASSIGNMENTS.get(task_name)
        
        if agent_name:
            print(f"\nProcessing: {task_name[:60]}...")
            if update_task_and_create_handoff(task, agent_name, token):
                updated_count += 1
        else:
            print(f"\n⚠️  No assignment found for: {task_name[:60]}...")
    
    print("\n" + "=" * 80)
    print(f"✅ Updated {updated_count} tasks to Ready status with agent assignments")
    print("=" * 80)
    
    if updated_count > 0:
        print("\nNow creating handoff files...")
        print("Run: python3 create_handoff_from_notion_task.py --once (multiple times)")
        print("Or use the continuous handoff processor to automatically process all tasks")

if __name__ == "__main__":
    main()

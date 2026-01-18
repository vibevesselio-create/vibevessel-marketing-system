#!/usr/bin/env python3
"""Quick script to get next task from Notion"""
import os
import sys
import json
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from main import get_notion_token, safe_get_property, AGENT_TASKS_DB_ID
from notion_client import Client

token = get_notion_token()
if not token:
    print('ERROR: No Notion token', file=sys.stderr)
    sys.exit(1)

client = Client(auth=token)

# Query for incomplete tasks
INCOMPLETE_STATUSES = ['Ready', 'Not Started', 'In Progress', 'In-Progress', 'Ready for Handoff', 'Proposed', 'Draft', 'Blocked']
filter_params = {'or': [{'property': 'Status', 'status': {'equals': status}} for status in INCOMPLETE_STATUSES]}

sorts = [
    {'property': 'Priority', 'direction': 'ascending'},
    {'timestamp': 'last_edited_time', 'direction': 'descending'}
]

response = client.databases.query(
    database_id=AGENT_TASKS_DB_ID,
    filter=filter_params,
    sorts=sorts,
    page_size=5
)

tasks = response.get('results', [])
if not tasks:
    print('No incomplete tasks found')
    sys.exit(0)

task = tasks[0]
task_id = task.get('id')
task_title = safe_get_property(task, 'Task Name', 'title') or 'Untitled Task'
task_priority = safe_get_property(task, 'Priority', 'select') or 'Medium'
task_status = safe_get_property(task, 'Status', 'status') or 'Ready'
task_description = safe_get_property(task, 'Description', 'rich_text') or ''
task_url = task.get('url', '')
assigned_agent = safe_get_property(task, 'Assigned-Agent', 'relation') or []
next_step = safe_get_property(task, 'Next Required Step', 'rich_text') or safe_get_property(task, 'Next Step', 'rich_text') or ''
success_criteria = safe_get_property(task, 'Success Criteria', 'rich_text') or ''

# Get agent name if assigned
agent_name = None
agent_id = None
if assigned_agent and len(assigned_agent) > 0:
    agent_id = assigned_agent[0].get('id')
    try:
        agent_page = client.pages.retrieve(agent_id)
        agent_name = safe_get_property(agent_page, 'Name', 'title') or safe_get_property(agent_page, 'Agent Name', 'title')
    except:
        pass

print(json.dumps({
    'task_id': task_id,
    'task_title': task_title,
    'task_priority': task_priority,
    'task_status': task_status,
    'task_description': task_description,
    'task_url': task_url,
    'assigned_agent_name': agent_name,
    'assigned_agent_id': agent_id,
    'next_step': next_step,
    'success_criteria': success_criteria
}, indent=2))






















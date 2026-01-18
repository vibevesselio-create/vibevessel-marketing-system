#!/usr/bin/env python3
"""Update Notion databases with Continuous Handoff Processor documentation"""

import os
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from main import get_notion_token, NotionManager

def main():
    token = get_notion_token()
    if not token:
        print('ERROR: No Notion token')
        return
    
    notion = NotionManager(token)
    
    # Update workflow with detailed information
    workflow_id = '2dfe7361-6c27-814a-9365-d47872da2af9'
    workflow_update = {
        'Description': {
            'rich_text': [{'text': {'content': '''Automated workflow that continuously monitors Agent-Tasks database, intelligently assigns tasks to appropriate agents based on capabilities, creates handoff trigger files, and manages complete task lifecycle from initiation through completion and review.

**Key Features:**
- Automatic task discovery and priority sorting
- Intelligent agent assignment based on capabilities
- Handoff file creation in agent inbox folders
- Review task generation for completed work
- Continuous operation until all tasks are processed
- Built-in rate limiting to prevent API throttling

**Script:** scripts/continuous_handoff_processor.py
**Documentation:** docs/workflows/CONTINUOUS_HANDOFF_PROCESSOR_WORKFLOW.md'''}}]
        },
        'Workflow Requirements': {
            'rich_text': [{'text': {'content': '''**Requirements:**
1. Notion API token configured
2. Access to Agent-Triggers folder structure
3. Python 3.x with notion-client package
4. Agent-Tasks database access

**Execution:**
- Single task mode: python3 scripts/continuous_handoff_processor.py --once
- Continuous mode: python3 scripts/continuous_handoff_processor.py
- Custom interval: python3 scripts/continuous_handoff_processor.py --interval 300'''}}]
        },
        'Frequency': {
            'multi_select': [{'name': 'Every 10 Minutes'}]
        }
    }
    
    try:
        notion.update_page(workflow_id, workflow_update)
        print(f'Updated workflow: {workflow_id}')
    except Exception as e:
        print(f'Error updating workflow: {e}')
    
    # Update function entries
    functions = [
        {
            'id': '2dfe7361-6c27-81a5-8616-c39dbe342f97',
            'name': 'Determine Best Agent for Task',
            'description': '''Determines the most appropriate agent for a task using a three-tier decision logic:

1. **Pre-assigned Agent Check**: If task already has an assigned agent, uses that agent
2. **Keyword Matching**: Matches task content (title, description, type, next step) against agent capabilities
3. **Default Fallback**: Defaults to Claude MM1 Agent for planning/coordination tasks

**Input:** Task dictionary from Notion
**Output:** Tuple of (agent_name, agent_id)
**Agent Capabilities:** Uses AGENT_CAPABILITIES mapping to score matches'''
        },
        {
            'id': '2dfe7361-6c27-81b0-9f72-cca7e7a9c75d',
            'name': 'Create Review Handoff Task',
            'description': '''Creates a review handoff task back to Cursor MM1 Agent when a task is marked as complete.

**Process:**
1. Detects completed tasks (Status = "Complete" or "Completed")
2. Checks if review task already exists
3. Creates new review task with:
   - Title: "Review: {Original Task Title}"
   - Priority: High
   - Task Type: Review Task
   - Assigned Agent: Cursor MM1 Agent
   - Description: Includes original task details and review requirements

**Review Requirements:**
- Validate completion of all task requirements
- Check documentation is comprehensive
- Verify production execution was successful
- Validate workspace requirements are met
- Determine if follow-up work is needed'''
        },
        {
            'id': '2dfe7361-6c27-8100-ac71-d740d8db963e',
            'name': 'Query Incomplete Tasks from Notion',
            'description': '''Queries Notion Agent-Tasks database for incomplete tasks, sorted by priority.

**Filter Criteria:**
- Status ≠ "Complete" AND Status ≠ "Completed"
- Archive = False

**Sorting:**
- Priority order: Critical > High > Medium > Low
- Manual priority sorting ensures correct order

**Output:** List of task pages sorted by priority
**Rate Limiting:** Includes 1.0 second pause after query'''
        }
    ]
    
    for func in functions:
        func_update = {
            'Description': {
                'rich_text': [{'text': {'content': func['description']}}]
            }
        }
        try:
            notion.update_page(func['id'], func_update)
            print(f'Updated function: {func["name"]}')
        except Exception as e:
            print(f'Error updating function {func["name"]}: {e}')
    
    # Create script entry with correct File Path format (URL)
    SCRIPTS_DB_ID = '26ce7361-6c27-8178-bc77-f43aff00eddf'
    script_props = {
        'Script Name': {
            'title': [{'text': {'content': 'continuous_handoff_processor'}}]
        },
        'File Path': {
            'url': 'https://github.com/serenmedia/github-production/blob/main/scripts/continuous_handoff_processor.py'
        },
        'Language': {
            'select': {'name': 'Python'}
        }
    }
    
    try:
        script_page = notion.create_page(SCRIPTS_DB_ID, script_props)
        if script_page:
            print(f'Created script: {script_page.get("url", "")}')
    except Exception as e:
        print(f'Error creating script: {e}')

if __name__ == '__main__':
    main()
































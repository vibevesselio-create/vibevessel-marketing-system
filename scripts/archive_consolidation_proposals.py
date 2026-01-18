#!/usr/bin/env python3
"""Archive the 5 consolidation proposals we identified earlier"""

import os
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from notion_client import Client
from dotenv import load_dotenv

env_file = project_root / '.env'
if env_file.exists():
    load_dotenv(env_file)
else:
    load_dotenv(project_root / 'shared' / 'api.env')

notion = Client(auth=os.getenv('NOTION_API_KEY'))

# The 5 consolidation proposals we identified
consolidation_proposals = [
    {
        'id': '273e7361-6c27-81e9-afdc-cb95f14b5f53',
        'title': '🌟 Ultimate Music Workflow - Complete Integration System'
    },
    {
        'id': '276e7361-6c27-8107-a9b2-df06fde0307d',
        'title': 'unified_validation_functions.py'
    },
    {
        'id': '276e7361-6c27-8196-b3dd-ca663cd532ae',
        'title': 'unified_venv_validation.py'
    },
    {
        'id': '276e7361-6c27-819d-84fd-e7170d71b19c',
        'title': 'unified_workflow_mapping.py'
    },
    {
        'id': '276e7361-6c27-81aa-98de-efc37f509c7d',
        'title': 'execute_available_task.py'
    }
]

print("Checking and archiving 5 consolidation proposals...")
print("=" * 80)

archived_count = 0
already_archived = 0
failed = 0

for proposal in consolidation_proposals:
    page_id = proposal['id']
    title = proposal['title']
    
    try:
        page = notion.pages.retrieve(page_id)
        is_archived = page.get('archived', False)
        
        if is_archived:
            print(f"✅ {title} - Already archived")
            already_archived += 1
        else:
            # Archive it
            notion.pages.update(page_id=page_id, archived=True)
            print(f"✅ {title} - Archived")
            archived_count += 1
    except Exception as e:
        print(f"❌ {title} - Failed: {e}")
        failed += 1

print("\n" + "=" * 80)
print(f"Summary: {archived_count} archived, {already_archived} already archived, {failed} failed")
print("=" * 80)
















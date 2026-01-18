#!/usr/bin/env python3
"""Clear Eagle File ID from a Notion page"""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
load_dotenv()

try:
    from unified_config import load_unified_env, get_unified_config
    load_unified_env()
    unified_config = get_unified_config()
except:
    unified_config = {}

def get_notion_token():
    # Use centralized token manager (MANDATORY per CLAUDE.md)
    try:
        from shared_core.notion.token_manager import get_notion_token as _get_notion_token
        token = _get_notion_token()
        if token:
            return token
    except ImportError:
        pass
    # Fallback for backwards compatibility
    return (os.getenv('NOTION_TOKEN') or os.getenv('NOTION_API_TOKEN') or
            os.getenv('VV_AUTOMATIONS_WS_TOKEN') or unified_config.get('notion_token'))

import requests

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python clear_eagle_id.py <page_id>")
        sys.exit(1)
    
    token = get_notion_token()
    page_id = sys.argv[1]
    
    headers = {
        'Authorization': f'Bearer {token}',
        'Notion-Version': '2022-06-28',
        'Content-Type': 'application/json'
    }
    
    # Get database to find property name
    db_id = os.getenv('TRACKS_DB_ID') or unified_config.get('tracks_db_id', '').strip()
    if len(db_id) == 32:
        db_id = f'{db_id[:8]}-{db_id[8:12]}-{db_id[12:16]}-{db_id[16:20]}-{db_id[20:]}'
    
    resp = requests.get(f'https://api.notion.com/v1/databases/{db_id}', headers=headers)
    props = resp.json().get('properties', {})
    eagle_prop = None
    for name, prop in props.items():
        if 'eagle' in name.lower() and 'id' in name.lower():
            eagle_prop = name
            break
    
    if eagle_prop:
        # Clear the property by setting it to empty
        update_data = {eagle_prop: {'rich_text': []}}
        resp = requests.patch(f'https://api.notion.com/v1/pages/{page_id}', headers=headers, json={'properties': update_data})
        if resp.status_code == 200:
            print(f'✅ Cleared Eagle File ID from Notion page {page_id}')
        else:
            print(f'❌ Failed to clear: {resp.status_code} - {resp.text}')
    else:
        print('⚠️  Could not find Eagle File ID property')



































































































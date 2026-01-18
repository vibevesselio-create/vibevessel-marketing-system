#!/usr/bin/env python3
"""Check Notion Tracks database schema for library-related properties."""

import os
import sys
from pathlib import Path

# Add project root to path
script_dir = Path(__file__).parent
project_root = script_dir.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from notion_client import Client
from shared_core.notion.token_manager import get_notion_token

TRACKS_DB_ID = os.getenv("TRACKS_DB_ID") or "27ce7361-6c27-80fb-b40e-fefdd47d6640"

def main():
    token = get_notion_token()
    if not token:
        print("❌ Notion token not available")
        return 1
    
    client = Client(auth=token)
    
    # Get database schema
    db = client.databases.retrieve(database_id=TRACKS_DB_ID)
    props = db.get('properties', {})
    
    print('Notion Tracks Database Properties:')
    print('=' * 80)
    
    library_props = []
    relation_props = []
    
    for prop_name, prop_data in sorted(props.items()):
        prop_type = prop_data.get('type', 'unknown')
        print(f'\n{prop_name}: {prop_type}')
        
        if 'library' in prop_name.lower() or 'ipad' in prop_name.lower() or 'mac' in prop_name.lower() or 'djay' in prop_name.lower():
            library_props.append((prop_name, prop_type, prop_data))
        
        if prop_type == 'relation':
            relation_props.append((prop_name, prop_data))
            relation_info = prop_data.get('relation', {})
            print(f'  -> Related DB: {relation_info.get("database_id", "N/A")}')
        
        if prop_type == 'select':
            options = prop_data.get('select', {}).get('options', [])
            if options:
                print(f'  -> Options: {[o.get("name") for o in options]}')
    
    print('\n' + '=' * 80)
    print('Library-Related Properties:')
    print('=' * 80)
    for prop_name, prop_type, prop_data in library_props:
        print(f'{prop_name} ({prop_type}): {prop_data}')
    
    print('\n' + '=' * 80)
    print('Relation Properties:')
    print('=' * 80)
    for prop_name, prop_data in relation_props:
        relation_info = prop_data.get('relation', {})
        print(f'{prop_name}: {relation_info.get("database_id", "N/A")}')
    
    return 0

if __name__ == "__main__":
    sys.exit(main())

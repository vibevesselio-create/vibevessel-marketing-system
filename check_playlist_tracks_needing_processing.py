#!/usr/bin/env python3
"""Quick script to check for tracks with playlist relations that need processing."""
import os
import sys
from pathlib import Path

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from unified_config import load_unified_env, get_unified_config
from music_workflow_common import NotionClient
from shared_core.notion.token_manager import get_notion_token

load_unified_env()
config = get_unified_config()

notion_token = get_notion_token() or config.get('notion_token')
tracks_db_id = config.get('tracks_db_id') or os.getenv('TRACKS_DB_ID', '27ce7361-6c27-80fb-b40e-fefdd47d6640')

def format_database_id(db_id: str) -> str:
    if not db_id or len(db_id) != 32:
        return db_id
    if '-' in db_id:
        return db_id
    return f"{db_id[:8]}-{db_id[8:12]}-{db_id[12:16]}-{db_id[16:20]}-{db_id[20:]}"

tracks_db_id = format_database_id(tracks_db_id)

client = NotionClient(notion_token, '2022-06-28', logger=None)
db_info = client.get_database(tracks_db_id)
props = db_info.get('properties', {})
prop_types = {name: p.get('type') for name, p in props.items()}

# Check for tracks with playlist relations and not downloaded
filters = []
if 'Playlist' in prop_types and prop_types['Playlist'] == 'relation':
    filters.append({'property': 'Playlist', 'relation': {'is_not_empty': True}})
if 'Downloaded' in prop_types:
    filters.append({'property': 'Downloaded', 'checkbox': {'equals': False}})
elif 'DL' in prop_types:
    filters.append({'property': 'DL', 'checkbox': {'equals': False}})

if not filters:
    print("No suitable filters found. Checking all tracks with playlist relations...")
    if 'Playlist' in prop_types and prop_types['Playlist'] == 'relation':
        query = {'filter': {'property': 'Playlist', 'relation': {'is_not_empty': True}}, 'page_size': 10}
    else:
        print("Playlist property not found in database schema")
        sys.exit(1)
else:
    query = {'filter': {'and': filters} if len(filters) > 1 else filters[0], 'page_size': 10}

result = client.query_database(tracks_db_id, query)
tracks = result.get('results', [])
print(f'Found {len(tracks)} tracks with playlist relations that need processing')
for page in tracks[:5]:
    title_prop = page.get('properties', {}).get('Title', {})
    if title_prop.get('type') == 'title':
        title = title_prop.get('title', [{}])[0].get('plain_text', 'Unknown')
    else:
        title = 'Unknown'
    print(f'  - {title}')

if len(tracks) > 0:
    print(f"\n✅ Found {len(tracks)} tracks to process. Execute: python3 monolithic-scripts/soundcloud_download_prod_merge-2.py --mode batch --limit {min(len(tracks), 100)}")
else:
    print("\n⚠️  No tracks found. Need playlist URL to sync.")

#!/usr/bin/env python3
"""
Test query to verify Spotify tracks are found by the fixed query filter.
"""
import os
import sys
import json
from pathlib import Path
from dotenv import load_dotenv

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
load_dotenv()

try:
    from shared_core.notion.token_manager import get_notion_token
    token = get_notion_token()
    if not token:
        token = os.getenv('NOTION_TOKEN')
    
    import requests
    db_id = os.getenv('TRACKS_DB_ID', '27ce7361-6c27-80fb-b40e-fefdd47d6640')
    headers = {
        'Authorization': f'Bearer {token}',
        'Notion-Version': '2022-06-28',
        'Content-Type': 'application/json'
    }
    
    print(f"Testing query with database ID: {db_id}")
    
    # Simplified query: Get tracks with DL=False and no files
    # Filter for Spotify tracks in application code (Notion doesn't support complex nested AND/OR)
    # Strategy: Query for (SoundCloud URL OR Spotify ID) AND DL=False AND no files
    query = {
        'filter': {
            'and': [
                # Has either SoundCloud URL or Spotify ID (or both)
                {
                    'or': [
                        {'property': 'SoundCloud URL', 'rich_text': {'is_not_empty': True}},
                        {'property': 'SoundCloud URL', 'url': {'is_not_empty': True}},
                        {'property': 'Spotify ID', 'rich_text': {'is_not_empty': True}}
                    ]
                },
                # DL/Downloaded = False
                {'property': 'Downloaded', 'checkbox': {'equals': False}},
                # No file paths
                {'property': 'M4A File Path', 'rich_text': {'is_empty': True}},
                {'property': 'AIFF File Path', 'rich_text': {'is_empty': True}}
            ]
        },
        'page_size': 10
    }
    
    print("\nTesting query...")
    response = requests.post(
        f'https://api.notion.com/v1/databases/{db_id}/query',
        headers=headers,
        json=query
    )
    
    if response.status_code == 200:
        results = response.json().get('results', [])
        print(f"✅ Query successful! Found {len(results)} tracks")
        
        for i, track in enumerate(results[:5], 1):
            props = track.get('properties', {})
            title = props.get('Title', {}).get('title', [{}])[0].get('plain_text', 'Unknown') if props.get('Title', {}).get('title') else 'Unknown'
            spotify_id = props.get('Spotify ID', {}).get('rich_text', [{}])[0].get('plain_text', '') if props.get('Spotify ID', {}).get('rich_text') else ''
            sc_url = props.get('SoundCloud URL', {}).get('rich_text', [{}])[0].get('plain_text', '') if props.get('SoundCloud URL', {}).get('rich_text') else props.get('SoundCloud URL', {}).get('url', '')
            downloaded = props.get('Downloaded', {}).get('checkbox', None)
            
            print(f"\n{i}. {title}")
            print(f"   Spotify ID: {spotify_id[:40] if spotify_id else 'None'}")
            print(f"   SoundCloud URL: {'Yes' if sc_url else 'No'}")
            print(f"   Downloaded: {downloaded}")
            
            if spotify_id and not sc_url:
                print(f"   ✅ This is a Spotify track that should be processed for YouTube download")
    else:
        print(f"❌ Query failed: {response.status_code}")
        try:
            error_data = response.json()
            print(f"Error: {json.dumps(error_data, indent=2)}")
        except:
            print(f"Response: {response.text[:500]}")
            
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()

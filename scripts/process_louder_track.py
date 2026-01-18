#!/usr/bin/env python3
"""
Process the LOUDER track directly using the production script.
"""

import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "monolithic-scripts"))

# Set environment before importing
os.chdir(project_root)

# Import the production script module directly
import importlib.util
import sys
spec = importlib.util.spec_from_file_location(
    "soundcloud_download_prod_merge_2",
    project_root / "monolithic-scripts" / "soundcloud_download_prod_merge-2.py"
)
module = importlib.util.module_from_spec(spec)
# Fix Python 3.13 @dataclass compatibility - register module before exec
sys.modules[spec.name] = module
spec.loader.exec_module(module)

def main():
    page_id = '2e6e7361-6c27-8007-b3f6-e8f46b9e8233'
    print(f'📄 Fetching Notion page: {page_id}')
    
    try:
        page = module.notion_manager._req('get', f'/pages/{page_id}')
        
        if not page:
            print('❌ Failed to fetch Notion page')
            return 1
        
        title = page.get('properties', {}).get('Title', {}).get('title', [{}])[0].get('plain_text', 'Unknown')
        print(f'✅ Found track: {title}')
        
        # Check if it's a Spotify track
        props = page.get('properties', {})
        spotify_id = props.get('Spotify ID', {}).get('rich_text', [{}])[0].get('plain_text', '')
        soundcloud_url = props.get('SoundCloud URL', {}).get('url', '')
        
        print(f'   Spotify ID: {spotify_id}')
        print(f'   SoundCloud URL: {soundcloud_url or "None"}')
        
        print('\n🔄 Processing track through production pipeline...')
        print('   (This will search YouTube and download the audio)\n')
        
        result = module.process_track(page)
        
        if result:
            print('\n✅ SUCCESS: Track processed and downloaded!')
            return 0
        else:
            print('\n❌ FAILED: Track processing failed')
            return 1
            
    except Exception as e:
        print(f'\n❌ Error: {e}')
        import traceback
        traceback.print_exc()
        return 1

if __name__ == '__main__':
    sys.exit(main())

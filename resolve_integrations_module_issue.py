#!/usr/bin/env python3
"""
Update Notion issue status to Resolved for the integrations module issue.
"""

import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

try:
    from notion_client import Client
    from shared_core.notion.token_manager import get_notion_token
    NOTION_AVAILABLE = True
except ImportError as e:
    print(f"Error importing dependencies: {e}")
    NOTION_AVAILABLE = False
    sys.exit(1)

# Issue ID from the query results
ISSUE_ID = "2e6e7361-6c27-8113-a9ee-c15f2a486ca9"
ISSUES_DB_ID = os.getenv("ISSUES_QUESTIONS_DB_ID", "229e73616c27808ebf06c202b10b5166")

def update_issue_status():
    """Update the issue status to Resolved."""
    try:
        token = get_notion_token()
        if not token:
            print("❌ Error: Could not get Notion token")
            return False
        
        client = Client(auth=token)
        
        # Update issue status to Resolved
        resolution_note = """
## Resolution Summary

The `music_workflow/integrations/` module has been completed and properly configured.

### What Was Done:
1. ✅ Verified the integrations module structure exists with all required submodules:
   - `notion/` - Notion API wrapper with client, tracks_db, and playlists_db
   - `spotify/` - Spotify API integration with OAuth and metadata enrichment
   - `eagle/` - Eagle library integration for asset management
   - `soundcloud/` - SoundCloud integration via yt-dlp

2. ✅ Updated `integrations/__init__.py` to properly expose all integration clients:
   - NotionClient, TracksDatabase, PlaylistsDatabase
   - SpotifyClient, SpotifyTrack, SpotifyPlaylist
   - EagleClient, EagleItem
   - SoundCloudClient, SoundCloudTrack, SoundCloudPlaylist

3. ✅ Verified imports work correctly:
   ```python
   from music_workflow.integrations import (
       NotionClient,
       SpotifyClient,
       EagleClient,
       SoundCloudClient,
   )
   ```

### Module Structure:
The module uses a nested structure (better organized than flat):
```
integrations/
├── __init__.py (properly exposes all clients)
├── notion/
│   ├── client.py
│   ├── tracks_db.py
│   └── playlists_db.py
├── spotify/
│   └── client.py
├── eagle/
│   └── client.py
└── soundcloud/
    └── client.py
```

### Status:
✅ **COMPLETE** - The integrations module is fully functional and ready for use.

### Next Steps:
- The module can now be used in the music workflow system
- All integrations are properly exposed and importable
- Ready for Phase 2 completion verification
"""
        
        # Update the issue
        client.pages.update(
            page_id=ISSUE_ID,
            properties={
                "Status": {
                    "status": {"name": "Resolved"}
                },
                "Description": {
                    "rich_text": [
                        {
                            "text": {
                                "content": resolution_note[:1997] + "..." if len(resolution_note) > 2000 else resolution_note
                            }
                        }
                    ]
                }
            }
        )
        
        print(f"✅ Successfully updated issue {ISSUE_ID} to Resolved")
        return True
        
    except Exception as e:
        print(f"❌ Error updating issue: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = update_issue_status()
    sys.exit(0 if success else 1)

#!/usr/bin/env python3
"""
Document all issues encountered during track workflow execution in Notion.
"""
import os
import sys
from pathlib import Path
from datetime import datetime, timezone

# Add project root to path
project_root = Path(__file__).parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Load environment
from dotenv import load_dotenv
load_dotenv()

# Import Notion client
try:
    from notion_client import Client
    from shared_core.notion.token_manager import get_notion_token
    NOTION_AVAILABLE = True
except ImportError:
    NOTION_AVAILABLE = False
    print("Notion client not available")

# Database IDs
ISSUES_DB_ID = os.getenv("ISSUES_DB_ID", "229e73616c27808ebf06c202b10b5166")
TRACKS_DB_ID = os.getenv("TRACKS_DB_ID", "27ce7361-6c27-80fb-b40e-fefdd47d6640")

# Track page ID
TRACK_PAGE_ID = "285e7361-6c27-81b2-83ca-e6e74829677d"
TRACK_TITLE = "I Took A Pill In Ibiza (Seeb Remix)"

def create_issue(
    client: Client,
    name: str,
    description: str,
    priority: str = "Medium",
    component: str = None,
    type: list = None,
    related_track_id: str = None
) -> str:
    """Create an issue in Notion Issues database."""
    try:
        # Get database schema to determine available properties
        db_schema = client.databases.retrieve(database_id=ISSUES_DB_ID)
        properties_schema = db_schema.get("properties", {})
        
        # Build properties
        properties = {
            "Name": {
                "title": [{"text": {"content": name}}]
            },
            "Description": {
                "rich_text": [{"text": {"content": description[:2000]}}]  # Notion limit
            },
            "Priority": {
                "select": {"name": priority}
            }
        }
        
        # Add Status if available
        if "Status" in properties_schema:
            status_prop = properties_schema["Status"]
            if status_prop.get("type") == "status":
                status_options = status_prop.get("status", {}).get("options", [])
                if status_options:
                    # Use "Unreported" or first available option
                    status_name = "Unreported"
                    available_statuses = [opt.get("name") for opt in status_options]
                    if status_name not in available_statuses and available_statuses:
                        status_name = available_statuses[0]
                    properties["Status"] = {
                        "status": {"name": status_name}
                    }
        
        # Add Type if available
        if type and "Type" in properties_schema:
            type_prop = properties_schema["Type"]
            if type_prop.get("type") == "multi_select":
                properties["Type"] = {
                    "multi_select": [{"name": t} for t in type]
                }
        
        # Add Component if available
        if component and "Component" in properties_schema:
            component_prop = properties_schema["Component"]
            if component_prop.get("type") == "select":
                properties["Component"] = {
                    "select": {"name": component}
                }
        
        # Add relation to track if available
        if related_track_id and "Related Track" in properties_schema:
            rel_prop = properties_schema["Related Track"]
            if rel_prop.get("type") == "relation":
                properties["Related Track"] = {
                    "relation": [{"id": related_track_id}]
                }
        
        # Create the issue
        page = client.pages.create(
            parent={"database_id": ISSUES_DB_ID},
            properties=properties
        )
        
        return page.get("id")
    except Exception as e:
        print(f"Error creating issue '{name}': {e}")
        import traceback
        traceback.print_exc()
        return None

def main():
    if not NOTION_AVAILABLE:
        print("Notion client not available. Cannot create issues.")
        return 1
    
    try:
        notion_token = get_notion_token()
        if not notion_token:
            print("Notion token not available")
            return 1
        
        client = Client(auth=notion_token)
        
        timestamp = datetime.now(timezone.utc).isoformat()
        
        # Issue 1: Wrong Database ID Used in URL Mode Processing
        issue1_id = create_issue(
            client,
            name=f"Music Workflow: Wrong Database ID Used in URL Mode Processing",
            description=f"""**Issue:** The production workflow script (`soundcloud_download_prod_merge-2.py`) attempts to use an incorrect database ID when processing tracks via URL mode.

**Details:**
- Script tried to use database ID: `23de7361-6c27-80a9-a867-f78317b32d22`
- Correct database ID should be: `27ce7361-6c27-80fb-b40e-fefdd47d6640`
- Error occurred in URL mode when checking if track exists in Notion
- Location: `monolithic-scripts/soundcloud_download_prod_merge-2.py` around line 11064

**Impact:**
- Prevents track processing via URL mode
- Causes 404 errors when querying Notion database
- Workflow fails before track can be downloaded and processed

**Evidence:**
- Error log shows: "Could not find database with ID: 23de7361-6c27-80a9-a867-f78317b32d22"
- Track page ID: {TRACK_PAGE_ID}
- Track: {TRACK_TITLE}
- Timestamp: {timestamp}

**Resolution:**
- Verify database ID configuration in environment variables
- Check if hardcoded database ID exists in codebase
- Ensure `TRACKS_DB_ID` environment variable is correctly set
- Update URL mode processing to use correct database ID from configuration""",
            priority="High",
            component="Music Workflow",
            type=["Bug", "Configuration"],
            related_track_id=TRACK_PAGE_ID
        )
        print(f"✅ Created Issue 1: {issue1_id}")
        
        # Issue 2: URL Mode Only Checks SoundCloud URL Property, Not YouTube URL
        issue2_id = create_issue(
            client,
            name=f"Music Workflow: URL Mode Search Missing YouTube URL Property Check",
            description=f"""**Issue:** When processing tracks via URL mode, the script only searches for existing tracks using the SoundCloud URL property, ignoring the YouTube URL property.

**Details:**
- Location: `monolithic-scripts/soundcloud_download_prod_merge-2.py` around line 11068
- Code only checks: `url_prop = resolve_property_name(prop_types, ["SoundCloud URL", "SoundCloud"])`
- Does not check: "YouTube URL" property
- Result: Script finds wrong track or creates duplicate when track exists with YouTube URL

**Impact:**
- Tracks with YouTube URLs are not found when searching by URL
- May create duplicate entries in Notion database
- Processing may target wrong track (as observed: found "RAISE YOUR WEAPON" instead of "{TRACK_TITLE}")

**Evidence:**
- Track has YouTube URL: `https://www.youtube.com/watch?v=Ah0srVZq9ac`
- Track page ID: {TRACK_PAGE_ID}
- Script found different track (ID: 2e4e7361-6c27-81a3-a03c-dc511784d7af) when searching
- Timestamp: {timestamp}

**Resolution:**
- Update URL search logic to check both SoundCloud URL and YouTube URL properties
- Add YouTube URL property to search filters in URL mode
- Ensure proper track matching before processing""",
            priority="High",
            component="Music Workflow",
            type=["Bug", "Logic Error"],
            related_track_id=TRACK_PAGE_ID
        )
        print(f"✅ Created Issue 2: {issue2_id}")
        
        # Issue 3: Track Processing Incomplete - Files Not Created
        issue3_id = create_issue(
            client,
            name=f"Music Workflow: Track Processing Incomplete - Files Not Created",
            description=f"""**Issue:** Track processing workflow did not complete successfully. Expected files were not created in output directories.

**Details:**
- Track: {TRACK_TITLE}
- Track Page ID: {TRACK_PAGE_ID}
- Expected outputs:
  - AIFF file in `/Volumes/VIBES/Playlists/[playlist_name]/`
  - M4A file in `/Volumes/VIBES/Playlists/[playlist_name]/`
  - M4A backup in `/Volumes/VIBES/Djay-Pro-Auto-Import/`
  - WAV backup in `/Volumes/VIBES/Apple-Music-Auto-Add/`
  - Eagle import to `/Volumes/VIBES/Music-Library-2.library`

**Current Status:**
- Notion page shows: Downloaded = False
- M4A File Path: Empty
- AIFF File Path: Empty
- WAV File Path: Empty
- Eagle File ID: Empty
- Files not found in expected directories

**Possible Causes:**
1. Workflow failed during download phase
2. Workflow failed during conversion phase
3. Workflow failed during file save phase
4. Workflow failed during Eagle import phase
5. Duplicate detection prevented processing (track has existing file URL in Eagle library)

**Evidence:**
- Track URL property shows: `file:///Volumes/VIBES/Music-Library-2.library/images/MBX3H01YL917S.info/I Took A Pill In Ibiza (Seeb Remix).m4a`
- This suggests a file may already exist in Eagle library
- Deduplication logic may have prevented new file creation
- Timestamp: {timestamp}

**Resolution:**
- Review workflow execution logs for errors
- Verify duplicate detection logic is working correctly
- Check if existing Eagle file should be linked or if new processing is needed
- Ensure all workflow phases complete successfully""",
            priority="Medium",
            component="Music Workflow",
            type=["Bug", "Workflow"],
            related_track_id=TRACK_PAGE_ID
        )
        print(f"✅ Created Issue 3: {issue3_id}")
        
        # Issue 4: Duplicate Detection May Prevent Processing When File Exists in Eagle
        issue4_id = create_issue(
            client,
            name=f"Music Workflow: Duplicate Detection Logic May Prevent Processing When File Exists",
            description=f"""**Issue:** Track has an existing file URL pointing to Eagle library, which may cause duplicate detection to prevent processing even when Notion page shows incomplete status.

**Details:**
- Track: {TRACK_TITLE}
- Track Page ID: {TRACK_PAGE_ID}
- Notion URL property shows: `file:///Volumes/VIBES/Music-Library-2.library/images/MBX3H01YL917S.info/I Took A Pill In Ibiza (Seeb Remix).m4a`
- Notion page shows: Downloaded = False, file paths empty
- This creates a conflict: file exists but Notion doesn't reflect it

**Impact:**
- Workflow may skip processing thinking file already exists
- Notion database becomes out of sync with actual file system
- Track remains in "unprocessed" state despite file existing

**Possible Scenarios:**
1. File was manually added to Eagle library but Notion wasn't updated
2. Previous workflow run created file but Notion update failed
3. Duplicate detection found existing file but didn't update Notion properly
4. File exists but needs reprocessing (e.g., for normalization or metadata updates)

**Evidence:**
- Track URL property: `file:///Volumes/VIBES/Music-Library-2.library/images/MBX3H01YL917S.info/I Took A Pill In Ibiza (Seeb Remix).m4a`
- Notion status: Downloaded = False
- All file path properties empty
- Timestamp: {timestamp}

**Resolution:**
- Review duplicate detection logic to ensure Notion is updated when existing files are found
- Add logic to sync Notion with existing Eagle library files
- Consider adding "reprocess" flag to force processing even when file exists
- Verify Eagle File ID is properly stored in Notion when duplicate is detected""",
            priority="Medium",
            component="Music Workflow",
            type=["Bug", "Data Sync"],
            related_track_id=TRACK_PAGE_ID
        )
        print(f"✅ Created Issue 4: {issue4_id}")
        
        # Issue 5: Workflow Execution Script Uses Wrong Database ID
        issue5_id = create_issue(
            client,
            name=f"Music Workflow: execute_music_track_sync_workflow.py May Use Wrong Database ID",
            description=f"""**Issue:** The workflow execution script may be using incorrect database IDs or not properly loading environment variables.

**Details:**
- Script: `execute_music_track_sync_workflow.py`
- May not be properly loading `TRACKS_DB_ID` from environment
- Could be using hardcoded or default database IDs that don't match current workspace

**Impact:**
- Workflow orchestration fails
- Cannot properly query or update Notion database
- Prevents automated track processing

**Evidence:**
- Workflow execution encountered database ID errors
- Script may need to verify environment variable loading
- Timestamp: {timestamp}

**Resolution:**
- Verify environment variable loading in execution script
- Ensure correct database IDs are used throughout workflow
- Add validation to check database IDs before processing""",
            priority="Medium",
            component="Music Workflow",
            type=["Configuration", "Bug"],
            related_track_id=TRACK_PAGE_ID
        )
        print(f"✅ Created Issue 5: {issue5_id}")
        
        print(f"\n✅ Successfully created {5} issues in Notion")
        print(f"   Issues Database ID: {ISSUES_DB_ID}")
        print(f"   Related Track: {TRACK_TITLE} ({TRACK_PAGE_ID})")
        
        return 0
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())

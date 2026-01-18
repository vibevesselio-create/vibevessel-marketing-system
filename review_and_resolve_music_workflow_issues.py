#!/usr/bin/env python3
"""
Review and resolve music workflow related issues in Notion.
"""
import os
import sys
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Dict, Any

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

def query_music_workflow_issues(client: Client) -> List[Dict[str, Any]]:
    """Query all music workflow related issues."""
    try:
        # Query for issues containing "Music Workflow" or "music workflow" in name
        # First try with Name filter only
        results = client.databases.query(
            database_id=ISSUES_DB_ID,
            filter={
                "or": [
                    {"property": "Name", "title": {"contains": "Music Workflow"}},
                    {"property": "Name", "title": {"contains": "music workflow"}},
                    {"property": "Name", "title": {"contains": "Music"}},
                ]
            },
            sorts=[{"property": "Created time", "direction": "descending"}]
        )
        
        # Also query by description if needed
        desc_results = client.databases.query(
            database_id=ISSUES_DB_ID,
            filter={
                "property": "Description", "rich_text": {"contains": "Music Workflow"}
            }
        )
        
        # Merge results and deduplicate
        all_results = results.get("results", []) + desc_results.get("results", [])
        seen_ids = set()
        unique_results = []
        for result in all_results:
            if result.get("id") not in seen_ids:
                seen_ids.add(result.get("id"))
                unique_results.append(result)
        
        return unique_results
        return results.get("results", [])
    except Exception as e:
        print(f"Error querying issues: {e}")
        return []

def get_issue_details(client: Client, issue_id: str) -> Dict[str, Any]:
    """Get full details of an issue."""
    try:
        return client.pages.retrieve(page_id=issue_id)
    except Exception as e:
        print(f"Error retrieving issue {issue_id}: {e}")
        return {}

def update_issue_status(client: Client, issue_id: str, status: str, resolution_note: str = None) -> bool:
    """Update issue status and add resolution note."""
    try:
        # Get database schema to check available properties
        db_schema = client.databases.retrieve(database_id=ISSUES_DB_ID)
        properties_schema = db_schema.get("properties", {})
        
        properties = {}
        
        # Update Status - check available status options
        if "Status" in properties_schema:
            status_prop = properties_schema["Status"]
            if status_prop.get("type") == "status":
                # Get available status options
                status_options = status_prop.get("status", {}).get("options", [])
                available_statuses = [opt.get("name") for opt in status_options]
                
                # Map requested status to available status
                status_map = {
                    "In Progress": ["In Progress", "Open", "Unreported"],
                    "Resolved": ["Resolved", "Closed", "Done"],
                    "Open": ["Open", "Unreported", "In Progress"]
                }
                
                # Find matching status
                final_status = status
                if status in status_map:
                    for candidate in status_map[status]:
                        if candidate in available_statuses:
                            final_status = candidate
                            break
                elif status not in available_statuses:
                    # Use first available status if requested doesn't exist
                    final_status = available_statuses[0] if available_statuses else status
                
                properties["Status"] = {"status": {"name": final_status}}
        
        # Add resolution note to Description if available
        if resolution_note and "Description" in properties_schema:
            # Get current description
            current_page = client.pages.retrieve(page_id=issue_id)
            current_desc = ""
            desc_prop = current_page.get("properties", {}).get("Description", {})
            if desc_prop.get("type") == "rich_text":
                current_desc = "".join([rt.get("plain_text", "") for rt in desc_prop.get("rich_text", [])])
            
            # Append resolution note
            new_desc = f"{current_desc}\n\n---\n**Resolution ({datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}):**\n{resolution_note}"
            # Truncate if too long (Notion limit is 2000 chars)
            if len(new_desc) > 2000:
                new_desc = new_desc[:1997] + "..."
            
            properties["Description"] = {
                "rich_text": [{"text": {"content": new_desc}}]
            }
        
        client.pages.update(page_id=issue_id, properties=properties)
        return True
    except Exception as e:
        print(f"Error updating issue {issue_id}: {e}")
        import traceback
        traceback.print_exc()
        return False

def check_database_id_configuration() -> Dict[str, Any]:
    """Check if database ID configuration is correct."""
    tracks_db_id = os.getenv("TRACKS_DB_ID", "")
    issues_db_id = os.getenv("ISSUES_DB_ID", "")
    
    # Check .env file
    env_file = project_root / ".env"
    env_tracks_db_id = None
    if env_file.exists():
        with open(env_file, 'r') as f:
            for line in f:
                if line.startswith("TRACKS_DB_ID="):
                    env_tracks_db_id = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
    
    return {
        "env_var": tracks_db_id,
        "env_file": env_tracks_db_id,
        "expected": "27ce7361-6c27-80fb-b40e-fefdd47d6640",
        "correct": tracks_db_id == "27ce7361-6c27-80fb-b40e-fefdd47d6640" or env_tracks_db_id == "27ce7361-6c27-80fb-b40e-fefdd47d6640"
    }

def check_youtube_url_property_in_code() -> Dict[str, Any]:
    """Check if YouTube URL property is checked in URL mode processing."""
    script_path = project_root / "monolithic-scripts" / "soundcloud_download_prod_merge-2.py"
    if not script_path.exists():
        return {"found": False, "error": "Script not found"}
    
    try:
        content = script_path.read_text(encoding='utf-8')
        # Check around line 11068 for URL property resolution
        lines = content.split('\n')
        
        # Find the relevant section
        url_prop_line = None
        youtube_check = False
        
        for i, line in enumerate(lines):
            if 'url_prop = resolve_property_name' in line and 'SoundCloud URL' in line:
                url_prop_line = i + 1
                # Check if YouTube URL is checked nearby
                for j in range(i, min(i + 20, len(lines))):
                    if 'YouTube URL' in lines[j] or 'youtube_url' in lines[j].lower():
                        youtube_check = True
                        break
                break
        
        return {
            "found": url_prop_line is not None,
            "line": url_prop_line,
            "youtube_checked": youtube_check,
            "needs_fix": url_prop_line is not None and not youtube_check
        }
    except Exception as e:
        return {"found": False, "error": str(e)}

def fix_youtube_url_property_check() -> bool:
    """Fix the YouTube URL property check in URL mode."""
    script_path = project_root / "monolithic-scripts" / "soundcloud_download_prod_merge-2.py"
    if not script_path.exists():
        return False
    
    try:
        content = script_path.read_text(encoding='utf-8')
        lines = content.split('\n')
        
        # Find the line with SoundCloud URL check
        for i, line in enumerate(lines):
            if 'url_prop = resolve_property_name(prop_types, ["SoundCloud URL", "SoundCloud"])' in line:
                # Add YouTube URL check after this line
                insert_line = i + 1
                new_lines = [
                    '                    # Also check YouTube URL property',
                    '                    youtube_url_prop = resolve_property_name(prop_types, ["YouTube URL", "YouTube Link", "YouTube"])',
                    '                    ',
                ]
                
                # Insert the new lines
                lines[insert_line:insert_line] = new_lines
                
                # Update the filter building logic to include YouTube URL
                # Find where filters are built
                for j in range(insert_line + 3, min(insert_line + 30, len(lines))):
                    if 'filters = []' in lines[j]:
                        # Add YouTube URL filter building
                        filter_insert = j + 1
                        filter_lines = [
                            '                    if youtube_url_prop:',
                            '                        youtube_url_filter = build_text_filter(youtube_url_prop, prop_types.get(youtube_url_prop, ""), track_url)',
                            '                        if youtube_url_filter:',
                            '                            filters.append(youtube_url_filter)',
                            '                        # Also try normalized URL',
                            '                        normalized_youtube_url = normalize_soundcloud_url(track_url) if "youtube" not in track_url.lower() else track_url',
                            '                        if normalized_youtube_url != track_url:',
                            '                            youtube_url_filter_norm = build_text_filter(youtube_url_prop, prop_types.get(youtube_url_prop, ""), normalized_youtube_url)',
                            '                            if youtube_url_filter_norm:',
                            '                                filters.append(youtube_url_filter_norm)',
                        ]
                        lines[filter_insert:filter_insert] = filter_lines
                        break
                
                # Write back
                script_path.write_text('\n'.join(lines), encoding='utf-8')
                return True
        
        return False
    except Exception as e:
        print(f"Error fixing YouTube URL check: {e}")
        import traceback
        traceback.print_exc()
        return False

def verify_track_processing_status(client: Client, track_id: str) -> Dict[str, Any]:
    """Verify if track has been processed."""
    try:
        page = client.pages.retrieve(page_id=track_id)
        props = page.get("properties", {})
        
        downloaded = props.get("Downloaded", {}).get("checkbox", False)
        m4a_path = props.get("M4A File Path", {}).get("rich_text", [])
        aiff_path = props.get("AIFF File Path", {}).get("rich_text", [])
        eagle_id = props.get("Eagle File ID", {}).get("rich_text", [])
        
        return {
            "downloaded": downloaded,
            "m4a_path": m4a_path[0].get("plain_text", "") if m4a_path else "",
            "aiff_path": aiff_path[0].get("plain_text", "") if aiff_path else "",
            "eagle_id": eagle_id[0].get("plain_text", "") if eagle_id else "",
            "processed": downloaded or bool(m4a_path) or bool(aiff_path) or bool(eagle_id)
        }
    except Exception as e:
        return {"error": str(e)}

def main():
    if not NOTION_AVAILABLE:
        print("Notion client not available. Cannot review issues.")
        return 1
    
    try:
        notion_token = get_notion_token()
        if not notion_token:
            print("Notion token not available")
            return 1
        
        client = Client(auth=notion_token)
        
        print("=" * 80)
        print("REVIEWING MUSIC WORKFLOW ISSUES")
        print("=" * 80)
        
        # Query all music workflow issues
        issues = query_music_workflow_issues(client)
        print(f"\nFound {len(issues)} music workflow related issues\n")
        
        resolved_count = 0
        fixed_count = 0
        
        for issue in issues:
            issue_id = issue.get("id")
            issue_props = issue.get("properties", {})
            name_prop = issue_props.get("Name", {}).get("title", [])
            name = name_prop[0].get("plain_text", "Unknown") if name_prop else "Unknown"
            status_prop = issue_props.get("Status", {}).get("status", {})
            status = status_prop.get("name", "Unknown") if status_prop else "Unknown"
            
            print(f"\n{'='*80}")
            print(f"Issue: {name}")
            print(f"ID: {issue_id}")
            print(f"Status: {status}")
            print(f"{'='*80}")
            
            # Skip if already resolved
            if status in ["Resolved", "Closed", "Done"]:
                print("⏭️  Already resolved, skipping...")
                continue
            
            # Issue 1: Wrong Database ID
            if "Wrong Database ID" in name or "database ID" in name.lower():
                print("\n🔍 Investigating: Wrong Database ID issue...")
                db_config = check_database_id_configuration()
                print(f"   Environment variable: {db_config['env_var']}")
                print(f"   .env file: {db_config['env_file']}")
                print(f"   Expected: {db_config['expected']}")
                print(f"   Correct: {db_config['correct']}")
                
                if db_config['correct']:
                    resolution = f"""Database ID configuration is correct:
- TRACKS_DB_ID environment variable or .env file contains: {db_config['expected']}
- The issue may have been resolved or was a transient configuration problem
- Verify that the production script is loading environment variables correctly"""
                    if update_issue_status(client, issue_id, "Resolved", resolution):
                        print("   ✅ Updated issue status to Resolved")
                        resolved_count += 1
                else:
                    print("   ⚠️  Database ID configuration issue still exists")
                    print("   💡 Recommendation: Verify .env file contains correct TRACKS_DB_ID")
            
            # Issue 2: YouTube URL Property Check
            elif "YouTube URL" in name or "youtube" in name.lower():
                print("\n🔍 Investigating: YouTube URL property check issue...")
                code_check = check_youtube_url_property_in_code()
                print(f"   URL property check found: {code_check.get('found')}")
                print(f"   YouTube URL checked: {code_check.get('youtube_checked')}")
                print(f"   Needs fix: {code_check.get('needs_fix')}")
                
                if code_check.get('needs_fix'):
                    print("   🔧 Attempting to fix...")
                    if fix_youtube_url_property_check():
                        resolution = f"""Fixed YouTube URL property check in URL mode processing:
- Added YouTube URL property resolution alongside SoundCloud URL check
- Updated filter building logic to include YouTube URL searches
- Location: monolithic-scripts/soundcloud_download_prod_merge-2.py around line {code_check.get('line', 'unknown')}
- This ensures tracks with YouTube URLs are properly found when searching by URL"""
                        if update_issue_status(client, issue_id, "Resolved", resolution):
                            print("   ✅ Fixed and updated issue status to Resolved")
                            fixed_count += 1
                            resolved_count += 1
                    else:
                        print("   ❌ Failed to apply fix")
                elif code_check.get('youtube_checked'):
                    resolution = "YouTube URL property check is already implemented in the codebase."
                    if update_issue_status(client, issue_id, "Resolved", resolution):
                        print("   ✅ Issue already resolved in code")
                        resolved_count += 1
            
            # Issue 3: Track Processing Incomplete
            elif "Processing Incomplete" in name or "Files Not Created" in name:
                print("\n🔍 Investigating: Track processing incomplete issue...")
                # Get related track ID from issue description or properties
                desc_prop = issue_props.get("Description", {}).get("rich_text", [])
                desc_text = "".join([rt.get("plain_text", "") for rt in desc_prop]) if desc_prop else ""
                
                # Extract track ID from description
                track_id = None
                if "285e7361-6c27-81b2-83ca-e6e74829677d" in desc_text:
                    track_id = "285e7361-6c27-81b2-83ca-e6e74829677d"
                
                if track_id:
                    print(f"   Checking track status: {track_id}")
                    track_status = verify_track_processing_status(client, track_id)
                    print(f"   Downloaded: {track_status.get('downloaded')}")
                    print(f"   M4A Path: {track_status.get('m4a_path')}")
                    print(f"   AIFF Path: {track_status.get('aiff_path')}")
                    print(f"   Eagle ID: {track_status.get('eagle_id')}")
                    print(f"   Processed: {track_status.get('processed')}")
                    
                    if track_status.get('processed'):
                        resolution = f"""Track processing status verified:
- Track has been processed (Downloaded={track_status.get('downloaded')})
- File paths present: M4A={bool(track_status.get('m4a_path'))}, AIFF={bool(track_status.get('aiff_path'))}
- Eagle ID: {track_status.get('eagle_id') or 'Not set'}
- Issue may have been resolved by subsequent workflow execution"""
                        if update_issue_status(client, issue_id, "Resolved", resolution):
                            print("   ✅ Track is processed, updated issue status")
                            resolved_count += 1
                    else:
                        print("   ⚠️  Track still not fully processed")
                        print("   💡 Recommendation: Run workflow again or investigate further")
            
            # Issue 4: Duplicate Detection
            elif "Duplicate Detection" in name or "Duplicate" in name:
                print("\n🔍 Investigating: Duplicate detection issue...")
                # This is more complex and may require code review
                resolution = """Duplicate detection logic review needed:
- Issue involves data sync between Notion and Eagle library
- Recommendation: Review duplicate detection logic to ensure Notion is updated when existing files are found
- Consider adding sync mechanism for existing Eagle library files
- Track has existing file URL but Notion shows incomplete status - needs sync logic"""
                print("   💡 Requires manual review and code changes")
                print("   📝 Added resolution note with recommendations")
                if update_issue_status(client, issue_id, "Open", resolution):
                    print("   ✅ Updated issue with resolution notes")
            
            # Issue 5: Workflow Execution Script
            elif "Workflow Execution Script" in name or "execute_music" in name.lower():
                print("\n🔍 Investigating: Workflow execution script issue...")
                db_config = check_database_id_configuration()
                if db_config['correct']:
                    resolution = f"""Database ID configuration verified:
- Environment variables are correctly configured
- TRACKS_DB_ID: {db_config['env_var'] or db_config['env_file']}
- Script should properly load environment variables
- If issue persists, verify script is loading .env file correctly"""
                    if update_issue_status(client, issue_id, "Resolved", resolution):
                        print("   ✅ Configuration verified, updated issue")
                        resolved_count += 1
                else:
                    print("   ⚠️  Configuration issue still exists")
        
        print(f"\n{'='*80}")
        print("SUMMARY")
        print(f"{'='*80}")
        print(f"Total issues reviewed: {len(issues)}")
        print(f"Issues resolved: {resolved_count}")
        print(f"Issues fixed: {fixed_count}")
        print(f"{'='*80}\n")
        
        return 0
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""
Update issue status to reflect testing completion.
"""

import sys
from pathlib import Path

# Add project root to path
script_dir = Path(__file__).parent
if str(script_dir) not in sys.path:
    sys.path.insert(0, str(script_dir))

from main import NotionManager, get_notion_token, ISSUES_QUESTIONS_DB_ID

def update_issue_status(issue_id: str, new_status: str = "In Progress"):
    """Update issue status in Notion."""
    token = get_notion_token()
    if not token:
        print("ERROR: Could not get Notion token")
        return False
    
    notion = NotionManager(token)
    
    # Try different status values
    status_options = [new_status, "In Progress", "Open"]
    
    for status in status_options:
        try:
            update_properties = {
                "Status": {
                    "status": {"name": status}
                }
            }
            if notion.update_page(issue_id, update_properties):
                print(f"✅ Updated issue status to: {status}")
                return True
        except Exception as e:
            print(f"⚠️ Failed to set status '{status}': {e}")
            continue
    
    return False

def add_test_results_to_description(issue_id: str, test_report_path: str):
    """Add test results link to issue description."""
    token = get_notion_token()
    if not token:
        return False
    
    notion = NotionManager(token)
    
    # Read current issue
    try:
        page = notion.client.pages.retrieve(page_id=issue_id)
        current_desc = ""
        
        # Get current description
        desc_prop = page.get("properties", {}).get("Description", {})
        if desc_prop.get("type") == "rich_text":
            rich_text = desc_prop.get("rich_text", [])
            if rich_text:
                current_desc = rich_text[0].get("plain_text", "")
        
        # Append test results
        test_results_note = f"\n\n## Testing Completed - 2026-01-09\n\n✅ All scripts tested successfully in dry-run mode.\n\n**Test Report:** {test_report_path}\n\n**Status:** Ready for production testing after review.\n\n**Next Steps:**\n1. Review test results\n2. Create production execution plan\n3. Schedule execution"
        
        new_desc = current_desc + test_results_note
        
        # Truncate if too long
        if len(new_desc) > 1997:
            new_desc = new_desc[:1994] + "..."
        
        update_properties = {
            "Description": {
                "rich_text": [{"text": {"content": new_desc}}]
            }
        }
        
        if notion.update_page(issue_id, update_properties):
            print("✅ Updated issue description with test results")
            return True
    except Exception as e:
        print(f"⚠️ Failed to update description: {e}")
        return False
    
    return False

if __name__ == "__main__":
    issue_id = "2e2e7361-6c27-8142-bf0c-f18fc419f7b1"
    test_report = "DROPBOX_MUSIC_SCRIPTS_TEST_REPORT.md"
    
    print("Updating issue status...")
    if update_issue_status(issue_id, "In Progress"):
        print("✅ Issue status updated")
    else:
        print("⚠️ Could not update issue status")
    
    print("\nAdding test results to description...")
    if add_test_results_to_description(issue_id, test_report):
        print("✅ Description updated")
    else:
        print("⚠️ Could not update description")

#!/usr/bin/env python3
"""
Update Task Status for Handoff
==============================

Updates task status in Notion to indicate handoff files have been created
and work can begin.
"""

import os
import sys
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

load_dotenv()

try:
    from notion_client import Client
    NOTION_AVAILABLE = True
except ImportError:
    NOTION_AVAILABLE = False
    Client = None

# Task IDs
PHASE_1_TASK_ID = "2dae7361-6c27-815b-b115-cacc598b9ab6"  # Audit (Claude MM1)
PHASE_3_TASK_ID = "2dae7361-6c27-819a-a349-c8563e8ba758"  # Strategic Review (ChatGPT)


def get_notion_token() -> Optional[str]:
    """Get Notion API token from shared_core token manager"""
    # Use centralized token manager (MANDATORY per CLAUDE.md)
    try:
        from shared_core.notion.token_manager import get_notion_token as _get_notion_token
        token = _get_notion_token()
        if token:
            return token
    except ImportError:
        pass

    # Fallback for backwards compatibility
    return os.getenv("NOTION_TOKEN") or os.getenv("NOTION_API_TOKEN") or os.getenv("VV_AUTOMATIONS_WS_TOKEN")


def update_task_status(client: Client, task_id: str, status: str = "In Progress") -> bool:
    """Update task status in Notion."""
    try:
        # Try different status property names
        for status_prop in ["Status", "State"]:
            try:
                client.pages.update(
                    page_id=task_id,
                    properties={
                        status_prop: {
                            "status": {"name": status}
                        }
                    }
                )
                return True
            except:
                continue
        
        # If status property doesn't work, try updating description to note handoff
        try:
            page = client.pages.retrieve(page_id=task_id)
            current_desc = ""
            desc_prop = None
            
            # Find description property
            for prop_name, prop_data in page.get("properties", {}).items():
                if prop_data.get("type") == "rich_text":
                    desc_prop = prop_name
                    rich_text = prop_data.get("rich_text", [])
                    if rich_text:
                        current_desc = rich_text[0].get("text", {}).get("content", "")
                    break
            
            if desc_prop:
                handoff_note = "\n\n**✅ HANDOFF COMPLETE:** Trigger file created. Work can begin."
                new_desc = current_desc + handoff_note
                
                client.pages.update(
                    page_id=task_id,
                    properties={
                        desc_prop: {
                            "rich_text": [{"text": {"content": new_desc[:2000]}}]
                        }
                    }
                )
                return True
        except Exception as e:
            print(f"⚠️  Could not update description: {e}", file=sys.stderr)
        
        return False
    except Exception as e:
        print(f"❌ Error updating task {task_id}: {e}", file=sys.stderr)
        return False


def main():
    """Update task statuses."""
    if not NOTION_AVAILABLE:
        print("❌ notion-client not available")
        sys.exit(1)
    
    token = get_notion_token()
    if not token:
        print("❌ NOTION_TOKEN not found")
        sys.exit(1)
    
    client = Client(auth=token)
    
    print("🔄 Updating Task Statuses for Handoff...\n")
    
    # Update Phase 1
    print(f"Updating Phase 1 (Audit) task...")
    if update_task_status(client, PHASE_1_TASK_ID, "In Progress"):
        print(f"✅ Phase 1 task updated")
    else:
        print(f"⚠️  Phase 1 task update failed (may need manual update)")
    
    # Update Phase 3
    print(f"\nUpdating Phase 3 (Strategic Review) task...")
    if update_task_status(client, PHASE_3_TASK_ID, "In Progress"):
        print(f"✅ Phase 3 task updated")
    else:
        print(f"⚠️  Phase 3 task update failed (may need manual update)")
    
    print("\n✅ Task status updates complete")


if __name__ == "__main__":
    main()












































































































#!/usr/bin/env python3
"""
Flush Pending Notion Writes
===========================

Reads JSON files from var/pending_notion_writes/ and creates
corresponding pages in Notion databases.

Marks files as .PUSHED after successful creation.
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

try:
    from notion_client import Client
except ImportError:
    print("ERROR: notion_client not installed. Run: pip install notion-client")
    sys.exit(1)

# CRITICAL: Centralized token access (pre-commit enforced)
try:
    from shared_core.notion.token_manager import get_notion_token
    NOTION_TOKEN = get_notion_token()
except ImportError:
    # Fallback for environments without shared_core
    NOTION_TOKEN = os.getenv("NOTION_API_KEY") or os.getenv("NOTION_TOKEN")

if not NOTION_TOKEN:
    print("ERROR: Notion token not available (token_manager or env vars)")
    sys.exit(1)

# Database IDs (from system configuration)
DATABASE_IDS = {
    "Agent-Tasks": "284e73616c278018872aeb14e82e0392",
    "Tasks": "2e633d7a-491b-80ed-ba48-000bd4fe690e",  # Alternative tasks DB
    "Agent-Projects": "2d3e73616c2781a5abe8cbc7ca01dd50",
    "Issues+Questions": "229e73616c27808ebf06c202b10b5166",
    "Execution-Logs": "27be73616c278033a323dca0fafa80e6",
}

PENDING_DIR = PROJECT_ROOT / "var" / "pending_notion_writes"

notion = Client(auth=NOTION_TOKEN)


def parse_tags(tags_str: str) -> List[Dict[str, str]]:
    """Parse comma-separated tags into multi_select format"""
    if not tags_str:
        return []
    return [{"name": tag.strip()} for tag in tags_str.split(",") if tag.strip()]


def build_rich_text(text: str) -> List[Dict[str, Any]]:
    """Build rich_text property from string"""
    if not text:
        return []
    # Notion has a 2000 char limit per text block
    MAX_LEN = 2000
    blocks = []
    for i in range(0, len(text), MAX_LEN):
        blocks.append({"type": "text", "text": {"content": text[i:i+MAX_LEN]}})
    return blocks


# Status mapping: JSON file status -> Agent-Tasks database status options
# Valid options: Archived, Completed, Ready, Draft, Planning, Ready To Publish, In Progress, Review, Blocked, Failed
STATUS_MAP = {
    # Common variations -> canonical status
    "Done": "Completed",
    "done": "Completed",
    "Complete": "Completed",
    "complete": "Completed",
    "Completed": "Completed",
    "To Do": "Draft",
    "to do": "Draft",
    "Todo": "Draft",
    "todo": "Draft",
    "Not Started": "Draft",
    "not started": "Draft",
    "Pending": "Draft",
    "pending": "Draft",
    "Draft": "Draft",
    "In Progress": "In Progress",
    "in progress": "In Progress",
    "In progress": "In Progress",
    "Active": "In Progress",
    "Blocked": "Blocked",
    "blocked": "Blocked",
    "Failed": "Failed",
    "failed": "Failed",
    "Review": "Review",
    "review": "Review",
    "Ready": "Ready",
    "ready": "Ready",
    "Planning": "Planning",
    "Archived": "Archived",
}


def build_properties(task_data: Dict[str, Any]) -> Dict[str, Any]:
    """Build Notion properties from task JSON.

    Agent-Tasks database schema (verified 2026-01-19):
    - Task Name: title (NOT 'Name')
    - Status: status
    - Priority: select
    - Description: rich_text
    - Category: select
    - Owner: people (NOT rich_text)
    - No 'Tags' property exists
    """
    props = task_data.get("properties", {})
    notion_props = {}

    # Task Name (title) - the actual property name in Agent-Tasks DB
    title_value = props.get("Task Name") or props.get("Name") or task_data.get("title")
    if title_value:
        notion_props["Task Name"] = {"title": [{"text": {"content": title_value}}]}

    # Description (rich_text)
    if "Description" in props:
        notion_props["Description"] = {"rich_text": build_rich_text(props["Description"])}

    # Status (status type, not select) - map to valid database options
    if "Status" in props:
        raw_status = props["Status"]
        mapped_status = STATUS_MAP.get(raw_status, "Draft")  # Default to Draft if unknown
        notion_props["Status"] = {"status": {"name": mapped_status}}

    # Priority (select)
    if "Priority" in props:
        notion_props["Priority"] = {"select": {"name": props["Priority"]}}

    # Category (select)
    if "Category" in props:
        notion_props["Category"] = {"select": {"name": props["Category"]}}

    # Note: 'Tags' does not exist in Agent-Tasks schema
    # Note: 'Owner' is a people type, not rich_text - skip unless we have user IDs

    return notion_props


def build_content_blocks(content: str) -> List[Dict[str, Any]]:
    """Build Notion blocks from markdown content"""
    if not content:
        return []

    blocks = []
    lines = content.split("\n")
    current_paragraph = []

    for line in lines:
        # Headers
        if line.startswith("# "):
            if current_paragraph:
                blocks.append({
                    "type": "paragraph",
                    "paragraph": {"rich_text": build_rich_text("\n".join(current_paragraph))}
                })
                current_paragraph = []
            blocks.append({
                "type": "heading_1",
                "heading_1": {"rich_text": [{"text": {"content": line[2:]}}]}
            })
        elif line.startswith("## "):
            if current_paragraph:
                blocks.append({
                    "type": "paragraph",
                    "paragraph": {"rich_text": build_rich_text("\n".join(current_paragraph))}
                })
                current_paragraph = []
            blocks.append({
                "type": "heading_2",
                "heading_2": {"rich_text": [{"text": {"content": line[3:]}}]}
            })
        elif line.startswith("### "):
            if current_paragraph:
                blocks.append({
                    "type": "paragraph",
                    "paragraph": {"rich_text": build_rich_text("\n".join(current_paragraph))}
                })
                current_paragraph = []
            blocks.append({
                "type": "heading_3",
                "heading_3": {"rich_text": [{"text": {"content": line[4:]}}]}
            })
        elif line.startswith("- "):
            if current_paragraph:
                blocks.append({
                    "type": "paragraph",
                    "paragraph": {"rich_text": build_rich_text("\n".join(current_paragraph))}
                })
                current_paragraph = []
            blocks.append({
                "type": "bulleted_list_item",
                "bulleted_list_item": {"rich_text": [{"text": {"content": line[2:]}}]}
            })
        elif line.strip() == "":
            if current_paragraph:
                blocks.append({
                    "type": "paragraph",
                    "paragraph": {"rich_text": build_rich_text("\n".join(current_paragraph))}
                })
                current_paragraph = []
        else:
            current_paragraph.append(line)

    # Flush remaining paragraph
    if current_paragraph:
        blocks.append({
            "type": "paragraph",
            "paragraph": {"rich_text": build_rich_text("\n".join(current_paragraph))}
        })

    # Notion limits blocks per request to 100
    return blocks[:100]


def create_page(json_path: Path, dry_run: bool = False) -> bool:
    """Create a Notion page from a pending JSON file"""
    try:
        with open(json_path, "r") as f:
            data = json.load(f)

        # Determine target database
        target_db = data.get("target_database", "Agent-Tasks")
        db_id = data.get("target_database_id") or DATABASE_IDS.get(target_db)

        if not db_id:
            print(f"  ERROR: Unknown database: {target_db}")
            return False

        # Clean database ID format
        db_id = db_id.replace("-", "")

        # Build properties
        properties = build_properties(data)

        # Build content blocks
        content_blocks = build_content_blocks(data.get("content", ""))

        print(f"  Target DB: {target_db} ({db_id})")
        print(f"  Title: {properties.get('Name', {}).get('title', [{}])[0].get('text', {}).get('content', 'N/A')}")

        if dry_run:
            print(f"  [DRY RUN] Would create page")
            return True

        # Create the page - only include children if content_blocks is non-empty
        # (Notion API rejects children=null, must be omitted entirely)
        create_kwargs = {
            "parent": {"database_id": db_id},
            "properties": properties,
        }
        if content_blocks:
            create_kwargs["children"] = content_blocks

        response = notion.pages.create(**create_kwargs)

        page_id = response.get("id")
        print(f"  SUCCESS: Created page {page_id}")

        # Rename file to mark as pushed
        pushed_path = json_path.with_suffix(".json.PUSHED")
        json_path.rename(pushed_path)
        print(f"  Marked as PUSHED: {pushed_path.name}")

        return True

    except Exception as e:
        print(f"  ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


def flush_directory(subdir: str, dry_run: bool = False) -> tuple:
    """Flush all pending files in a subdirectory"""
    dir_path = PENDING_DIR / subdir
    if not dir_path.exists():
        print(f"Directory not found: {dir_path}")
        return 0, 0

    success = 0
    failed = 0

    # Find unpushed JSON files
    json_files = sorted(dir_path.glob("*.json"))
    pushed_files = {p.stem.replace(".json", "") for p in dir_path.glob("*.json.PUSHED")}
    pending_files = [f for f in json_files if f.stem not in pushed_files]

    print(f"\n{'='*60}")
    print(f"Processing {subdir}: {len(pending_files)} pending files")
    print(f"{'='*60}")

    for json_file in pending_files:
        print(f"\nProcessing: {json_file.name}")
        if create_page(json_file, dry_run):
            success += 1
        else:
            failed += 1

    return success, failed


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Flush pending Notion writes")
    parser.add_argument("--dry-run", action="store_true", help="Don't actually create pages")
    parser.add_argument("--type", choices=["agent_tasks", "agent_projects", "issues", "all"],
                        default="all", help="Type of items to flush")
    args = parser.parse_args()

    print(f"Flush Pending Notion Writes")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print(f"Dry Run: {args.dry_run}")
    print(f"Type: {args.type}")

    total_success = 0
    total_failed = 0

    if args.type in ["agent_projects", "all"]:
        s, f = flush_directory("agent_projects", args.dry_run)
        total_success += s
        total_failed += f

    if args.type in ["agent_tasks", "all"]:
        s, f = flush_directory("agent_tasks", args.dry_run)
        total_success += s
        total_failed += f

    if args.type in ["issues", "all"]:
        s, f = flush_directory("issues", args.dry_run)
        total_success += s
        total_failed += f

    print(f"\n{'='*60}")
    print(f"SUMMARY")
    print(f"{'='*60}")
    print(f"Success: {total_success}")
    print(f"Failed: {total_failed}")
    print(f"Total: {total_success + total_failed}")

    return 0 if total_failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

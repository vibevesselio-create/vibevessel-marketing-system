#!/usr/bin/env python3
"""
Push Agent Functions Registry to Notion Database.

This script reads the generated Agent Functions entries and pushes them
to the Notion Agent-Functions database.

Each function entry includes:
- Properties (name, module, signature, metadata)
- Page body with docstring and full source code in a code block

Usage:
    python3 scripts/push_agent_functions_to_notion.py [--dry-run] [--limit N] [--batch-size N]

Environment:
    NOTION_TOKEN or NOTION_API_KEY - Notion API token
    AGENT_FUNCTIONS_DB_ID - Notion Agent Functions database ID
"""

import json
import os
import sys
import time
import argparse
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional

# Add project root to path
script_dir = Path(__file__).parent
project_root = script_dir.parent
sys.path.insert(0, str(project_root))

# CRITICAL: Centralized token access
try:
    from shared_core.notion.token_manager import get_notion_token
    NOTION_TOKEN = get_notion_token()
except ImportError:
    NOTION_TOKEN = os.getenv("NOTION_API_KEY") or os.getenv("NOTION_TOKEN")

AGENT_FUNCTIONS_DB_ID = os.getenv("AGENT_FUNCTIONS_DB_ID")

INPUT_DIR = Path("var/pending_notion_writes/agent_functions")
PUSHED_SUFFIX = ".PUSHED"


def get_notion_client():
    """Get Notion client."""
    try:
        from notion_client import Client
        return Client(auth=NOTION_TOKEN)
    except ImportError:
        print("ERROR: notion_client not installed. Run: pip install notion-client")
        sys.exit(1)


def build_page_body(entry: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Build Notion page body blocks with docstring and source code."""
    blocks = []
    page_body = entry.get("page_body", {})

    # Docstring section
    docstring = page_body.get("docstring", "")
    if docstring:
        blocks.append({
            "type": "heading_2",
            "heading_2": {
                "rich_text": [{"type": "text", "text": {"content": "Documentation"}}]
            }
        })
        # Split docstring into paragraphs (Notion limit is 2000 chars per block)
        for para in docstring.split("\n\n"):
            if para.strip():
                blocks.append({
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{"type": "text", "text": {"content": para[:2000]}}]
                    }
                })

    # Decorators section
    decorators = page_body.get("decorators", [])
    if decorators:
        blocks.append({
            "type": "heading_2",
            "heading_2": {
                "rich_text": [{"type": "text", "text": {"content": "Decorators"}}]
            }
        })
        decorator_text = "\n".join(f"@{d}" for d in decorators)
        blocks.append({
            "type": "code",
            "code": {
                "rich_text": [{"type": "text", "text": {"content": decorator_text[:2000]}}],
                "language": "python"
            }
        })

    # Source code section (CRITICAL - full source code in single code block)
    source_code = page_body.get("source_code", "")
    if source_code:
        blocks.append({
            "type": "heading_2",
            "heading_2": {
                "rich_text": [{"type": "text", "text": {"content": "Source Code"}}]
            }
        })

        # Notion code block limit is 2000 chars per rich_text element
        # Split source code into chunks if needed
        chunk_size = 2000
        code_chunks = [source_code[i:i+chunk_size] for i in range(0, len(source_code), chunk_size)]

        if len(code_chunks) == 1:
            # Single code block
            blocks.append({
                "type": "code",
                "code": {
                    "rich_text": [{"type": "text", "text": {"content": source_code}}],
                    "language": "python"
                }
            })
        else:
            # Multiple code blocks for long functions
            for i, chunk in enumerate(code_chunks):
                if i == 0:
                    blocks.append({
                        "type": "code",
                        "code": {
                            "rich_text": [{"type": "text", "text": {"content": chunk}}],
                            "language": "python",
                            "caption": [{"type": "text", "text": {"content": f"Part {i+1} of {len(code_chunks)}"}}]
                        }
                    })
                else:
                    blocks.append({
                        "type": "code",
                        "code": {
                            "rich_text": [{"type": "text", "text": {"content": chunk}}],
                            "language": "python",
                            "caption": [{"type": "text", "text": {"content": f"Part {i+1} of {len(code_chunks)} (continued)"}}]
                        }
                    })

    # Metadata section
    props = entry.get("properties", {})
    blocks.append({
        "type": "heading_2",
        "heading_2": {
            "rich_text": [{"type": "text", "text": {"content": "Metadata"}}]
        }
    })

    metadata_text = f"""Module: {props.get('Module', 'N/A')}
File: {props.get('File Path', 'N/A')}
Lines: {props.get('Line Start', 'N/A')} - {props.get('Line End', 'N/A')}
Arguments: {props.get('Num Args', 0)}
Async: {props.get('Is Async', False)}
Private: {props.get('Is Private', False)}
Generated: {entry.get('created_at', 'N/A')}"""

    blocks.append({
        "type": "paragraph",
        "paragraph": {
            "rich_text": [{"type": "text", "text": {"content": metadata_text}}]
        }
    })

    return blocks


def build_properties(entry: Dict[str, Any], database_id: str) -> Dict[str, Any]:
    """Build Notion page properties from entry."""
    props = entry.get("properties", {})

    # Build Notion properties format
    notion_props = {
        "Name": {
            "title": [{"text": {"content": props.get("Name", "Unnamed")[:100]}}]
        },
    }

    # Rich text properties
    text_fields = ["Module", "Signature", "File Path", "Tags", "Category"]
    for field in text_fields:
        if field in props and props[field]:
            notion_props[field] = {
                "rich_text": [{"text": {"content": str(props[field])[:2000]}}]
            }

    # Number properties
    number_fields = ["Num Args", "Line Start", "Line End"]
    for field in number_fields:
        if field in props and props[field] is not None:
            notion_props[field] = {"number": props[field]}

    # Checkbox properties
    checkbox_fields = ["Is Async", "Is Private"]
    for field in checkbox_fields:
        if field in props:
            notion_props[field] = {"checkbox": bool(props[field])}

    # Select properties
    if "Status" in props:
        notion_props["Status"] = {"select": {"name": props["Status"]}}

    return notion_props


def push_entry(client, database_id: str, entry: Dict[str, Any], dry_run: bool = False) -> bool:
    """Push a single entry to Notion."""
    try:
        props = build_properties(entry, database_id)
        body_blocks = build_page_body(entry)

        if dry_run:
            print(f"  [DRY RUN] Would create: {entry['properties']['Name']}")
            return True

        # Create page
        response = client.pages.create(
            parent={"database_id": database_id},
            properties=props
        )

        page_id = response.get("id")

        # Add body blocks
        if body_blocks and page_id:
            # Notion limits to 100 blocks per request
            for i in range(0, len(body_blocks), 100):
                chunk = body_blocks[i:i+100]
                client.blocks.children.append(
                    block_id=page_id,
                    children=chunk
                )

        return True

    except Exception as e:
        print(f"  ERROR: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Push Agent Functions to Notion")
    parser.add_argument("--dry-run", action="store_true", help="Don't actually push to Notion")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of entries to push")
    parser.add_argument("--batch-size", type=int, default=10, help="Batch size for progress reporting")
    parser.add_argument("--database-id", type=str, help="Override Agent Functions database ID")
    args = parser.parse_args()

    print("=" * 60)
    print("PUSH AGENT FUNCTIONS TO NOTION")
    print("=" * 60)
    print()

    # Check configuration
    database_id = args.database_id or AGENT_FUNCTIONS_DB_ID
    if not database_id:
        print("ERROR: AGENT_FUNCTIONS_DB_ID not set")
        print("Set environment variable or use --database-id")
        sys.exit(1)

    if not NOTION_TOKEN:
        print("ERROR: NOTION_TOKEN not set")
        sys.exit(1)

    # Get Notion client
    if not args.dry_run:
        client = get_notion_client()
    else:
        client = None

    # Load entries
    if not INPUT_DIR.exists():
        print(f"ERROR: Input directory not found: {INPUT_DIR}")
        print("Run scripts/generate_agent_functions_registry.py first")
        sys.exit(1)

    entries = []
    for json_file in INPUT_DIR.glob("*.json"):
        if json_file.name.startswith("_"):
            continue  # Skip manifest
        if json_file.name.endswith(PUSHED_SUFFIX):
            continue  # Already pushed

        with open(json_file) as f:
            entry = json.load(f)
            entry["_file"] = json_file
            entries.append(entry)

    print(f"Found {len(entries)} entries to push")
    print(f"Database ID: {database_id}")
    print(f"Dry run: {args.dry_run}")
    print()

    if args.limit:
        entries = entries[:args.limit]
        print(f"Limited to {args.limit} entries")

    # Push entries
    success = 0
    failed = 0

    for i, entry in enumerate(entries):
        if i > 0 and i % args.batch_size == 0:
            print(f"Progress: {i}/{len(entries)} ({success} success, {failed} failed)")

        result = push_entry(client, database_id, entry, args.dry_run)

        if result:
            success += 1
            # Mark as pushed
            if not args.dry_run:
                pushed_path = entry["_file"].with_suffix(entry["_file"].suffix + PUSHED_SUFFIX)
                entry["_file"].rename(pushed_path)
        else:
            failed += 1

        # Rate limiting
        if not args.dry_run and i > 0 and i % 3 == 0:
            time.sleep(0.5)  # Notion rate limit

    print()
    print("=" * 60)
    print(f"COMPLETE: {success} success, {failed} failed")
    print("=" * 60)


if __name__ == "__main__":
    main()

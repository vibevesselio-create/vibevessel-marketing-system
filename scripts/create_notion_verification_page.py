#!/usr/bin/env python3
"""
Create Notion Documentation Page for Verification Report
"""

import os
import sys
from pathlib import Path
from datetime import datetime, timezone
from dotenv import load_dotenv

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
load_dotenv()

try:
    from notion_client import Client
    from notion_client.errors import APIResponseError
except ImportError:
    print("ERROR: notion_client not installed. Install with: pip install notion-client")
    sys.exit(1)

# Documents database ID
DOCUMENTS_DATABASE_ID = "284e7361-6c27-808d-a10b-c027c2eb11ff"

def get_notion_token():
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
    token = os.getenv("NOTION_TOKEN") or os.getenv("NOTION_API_TOKEN") or os.getenv("VV_AUTOMATIONS_WS_TOKEN")
    if not token:
        raise ValueError("No Notion token found in token_manager or environment variables")
    return token

def read_verification_report():
    """Read the verification report content"""
    report_path = project_root / "FINAL_COMPLETION_VERIFICATION_REPORT.md"
    if not report_path.exists():
        raise FileNotFoundError(f"Verification report not found: {report_path}")
    return report_path.read_text()

def create_notion_page():
    """Create Notion documentation page"""
    token = get_notion_token()
    client = Client(auth=token)
    
    # Read report content
    content = read_verification_report()
    
    # Create page with minimal properties (just Name/title)
    title = f"Final Completion Verification Report - {datetime.now(timezone.utc).strftime('%Y-%m-%d')}"
    
    try:
        # Create page with just the title property
        response = client.pages.create(
            parent={"database_id": DOCUMENTS_DATABASE_ID},
            properties={
                "Name": {
                    "title": [{"text": {"content": title}}]
                }
            }
        )
        
        page_id = response["id"]
        print(f"✅ Created Notion page: {page_id}")
        print(f"   URL: https://www.notion.so/{page_id.replace('-', '')}")
        
        # Convert markdown content to Notion blocks
        blocks = []
        lines = content.split('\n')
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Handle headers
            if line.startswith('# '):
                blocks.append({
                    "object": "block",
                    "type": "heading_1",
                    "heading_1": {
                        "rich_text": [{"type": "text", "text": {"content": line[2:].strip()}}]
                    }
                })
            elif line.startswith('## '):
                blocks.append({
                    "object": "block",
                    "type": "heading_2",
                    "heading_2": {
                        "rich_text": [{"type": "text", "text": {"content": line[3:].strip()}}]
                    }
                })
            elif line.startswith('### '):
                blocks.append({
                    "object": "block",
                    "type": "heading_3",
                    "heading_3": {
                        "rich_text": [{"type": "text", "text": {"content": line[4:].strip()}}]
                    }
                })
            elif line.startswith('- [x]') or line.startswith('- [X]'):
                # Checkbox item
                blocks.append({
                    "object": "block",
                    "type": "to_do",
                    "to_do": {
                        "rich_text": [{"type": "text", "text": {"content": line[6:].strip()}}],
                        "checked": True
                    }
                })
            elif line.startswith('- '):
                # Bullet point
                blocks.append({
                    "object": "block",
                    "type": "bulleted_list_item",
                    "bulleted_list_item": {
                        "rich_text": [{"type": "text", "text": {"content": line[2:].strip()}}]
                    }
                })
            else:
                # Regular paragraph
                if line and len(line) > 0:
                    # Split long lines
                    if len(line) > 2000:
                        chunks = [line[i:i+2000] for i in range(0, len(line), 2000)]
                        for chunk in chunks:
                            blocks.append({
                                "object": "block",
                                "type": "paragraph",
                                "paragraph": {
                                    "rich_text": [{"type": "text", "text": {"content": chunk}}]
                                }
                            })
                    else:
                        blocks.append({
                            "object": "block",
                            "type": "paragraph",
                            "paragraph": {
                                "rich_text": [{"type": "text", "text": {"content": line}}]
                            }
                        })
        
        # Add blocks in batches of 100 (Notion limit)
        for i in range(0, len(blocks), 100):
            batch = blocks[i:i+100]
            client.blocks.children.append(
                block_id=page_id,
                children=batch
            )
        
        print(f"✅ Added {len(blocks)} content blocks to page")
        print(f"✅ Successfully created Notion documentation page")
        return page_id
        
    except APIResponseError as e:
        print(f"❌ Notion API error: {e}")
        return None
    except Exception as e:
        print(f"❌ Error creating Notion page: {e}")
        return None

if __name__ == "__main__":
    create_notion_page()






















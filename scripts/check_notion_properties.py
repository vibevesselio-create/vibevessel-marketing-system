#!/usr/bin/env python3
"""Quick script to check Notion page properties"""
import os
import sys
import json
from pathlib import Path
from dotenv import load_dotenv

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
load_dotenv()

try:
    from unified_config import load_unified_env, get_unified_config
    load_unified_env()
    unified_config = get_unified_config()
except:
    unified_config = {}

import requests

def get_notion_token():
    # Use centralized token manager (MANDATORY per CLAUDE.md)
    try:
        from shared_core.notion.token_manager import get_notion_token as _get_notion_token
        token = _get_notion_token()
        if token:
            return token
    except ImportError:
        pass
    # Fallback for backwards compatibility
    return (
        os.getenv("NOTION_TOKEN") or
        os.getenv("NOTION_API_TOKEN") or
        os.getenv("VV_AUTOMATIONS_WS_TOKEN")
    )

NOTION_TOKEN = get_notion_token()
NOTION_VERSION = unified_config.get("notion_version") or os.getenv("NOTION_VERSION", "2022-06-28")

if not NOTION_TOKEN:
    print("❌ NOTION_TOKEN not found")
    sys.exit(1)

def get_page_properties(page_id: str):
    url = f"https://api.notion.com/v1/pages/{page_id}"
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Notion-Version": NOTION_VERSION,
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=30)
        if response.status_code >= 400:
            print(f"❌ Failed: {response.status_code} - {response.text}")
            return None
        
        page = response.json()
        props = page.get("properties", {})
        
        print("Available properties:")
        for prop_name, prop_data in props.items():
            prop_type = prop_data.get("type", "unknown")
            print(f"  - {prop_name} ({prop_type})")
        
        return props
    except Exception as e:
        print(f"❌ Error: {e}")
        return None

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python check_notion_properties.py <page_id>")
        sys.exit(1)
    
    page_id = sys.argv[1]
    get_page_properties(page_id)



















































































#!/usr/bin/env python3
"""
Verify Agent IDs in AGENT_MAPPING

Queries the Agents database in Notion and verifies all 11 agent IDs
in AGENT_MAPPING match the actual agent pages.
"""

import os
import sys
from pathlib import Path
from typing import Dict, List, Optional

# Add project root to path
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from main import NotionManager, get_notion_token
from scripts.continuous_handoff_processor import AGENT_MAPPING

# Agents Database ID (from documentation)
AGENTS_DB_ID = "257e7361-6c27-802a-93dd-cb88d1c4607b"

def safe_get_property(page: Dict, prop_name: str, prop_type: str):
    """Safely get a property value from a Notion page"""
    properties = page.get("properties", {})
    prop = properties.get(prop_name)
    if not prop or prop.get("type") != prop_type:
        return None
    
    if prop_type == "title":
        title_list = prop.get("title", [])
        if title_list:
            return title_list[0].get("plain_text", "")
        return ""
    elif prop_type == "rich_text":
        rich_text_list = prop.get("rich_text", [])
        if rich_text_list:
            return rich_text_list[0].get("plain_text", "")
        return ""
    elif prop_type == "select":
        select_obj = prop.get("select")
        if select_obj:
            return select_obj.get("name")
        return None
    return None

def verify_agent_ids():
    """Verify all agent IDs in AGENT_MAPPING"""
    print("🔍 Verifying Agent IDs in AGENT_MAPPING...")
    print(f"📋 Checking {len(AGENT_MAPPING)} agents\n")
    
    # Initialize Notion client
    token = get_notion_token()
    if not token:
        print("❌ Failed to get Notion token")
        return 1
    
    notion = NotionManager(token)
    
    try:
        # Query all agents from the database
        print("📊 Querying Agents database...")
        all_agents = notion.query_database(AGENTS_DB_ID)
        print(f"✅ Found {len(all_agents)} agents in database\n")
        
        # Create a mapping of agent ID to agent name from Notion
        notion_agent_map: Dict[str, str] = {}
        for agent_page in all_agents:
            agent_id = agent_page.get("id")
            agent_name = safe_get_property(agent_page, "Name", "title") or safe_get_property(agent_page, "Title", "title") or "Unknown"
            notion_agent_map[agent_id] = agent_name
        
        # Verify each agent in AGENT_MAPPING
        discrepancies = []
        verified_count = 0
        
        print("🔍 Verifying each agent in AGENT_MAPPING:\n")
        for agent_name, expected_id in AGENT_MAPPING.items():
            if expected_id in notion_agent_map:
                notion_name = notion_agent_map[expected_id]
                print(f"✅ {agent_name}")
                print(f"   ID: {expected_id}")
                print(f"   Notion Name: {notion_name}")
                if agent_name.lower() not in notion_name.lower() and notion_name.lower() not in agent_name.lower():
                    print(f"   ⚠️  Name mismatch: Expected '{agent_name}', Found '{notion_name}'")
                verified_count += 1
            else:
                print(f"❌ {agent_name}")
                print(f"   ID: {expected_id}")
                print(f"   ❌ NOT FOUND in Agents database")
                discrepancies.append({
                    "agent_name": agent_name,
                    "expected_id": expected_id,
                    "issue": "Agent ID not found in Agents database"
                })
            print()
        
        # Check for agents in Notion that aren't in AGENT_MAPPING
        print("\n🔍 Checking for agents in Notion not in AGENT_MAPPING:\n")
        notion_ids = set(notion_agent_map.keys())
        mapping_ids = set(AGENT_MAPPING.values())
        extra_agents = notion_ids - mapping_ids
        
        if extra_agents:
            print(f"⚠️  Found {len(extra_agents)} agents in Notion not in AGENT_MAPPING:")
            for agent_id in extra_agents:
                agent_name = notion_agent_map[agent_id]
                print(f"   - {agent_name} (ID: {agent_id})")
        else:
            print("✅ All agents in Notion are in AGENT_MAPPING")
        
        # Summary
        print("\n" + "="*60)
        print("📊 VERIFICATION SUMMARY")
        print("="*60)
        print(f"✅ Verified: {verified_count}/{len(AGENT_MAPPING)} agents")
        print(f"❌ Discrepancies: {len(discrepancies)}")
        
        if discrepancies:
            print("\n❌ DISCREPANCIES FOUND:")
            for disc in discrepancies:
                print(f"   - {disc['agent_name']}: {disc['issue']}")
            print("\n⚠️  Please report these discrepancies to Issues+Questions database")
            return 1
        else:
            print("\n🎉 All agent IDs verified successfully!")
            return 0
            
    except Exception as e:
        print(f"❌ Error verifying agent IDs: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(verify_agent_ids())


























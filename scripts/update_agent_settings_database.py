#!/usr/bin/env python3
"""
Update Agent Settings Database with New Properties

Adds the following properties to the Agents database:
- Agent Mode (Select: MM1, MM2, Notion-Integrated)
- Routing Priority (Number)
- Capability Tags (Multi-select: Research, Implementation, Review, Operations)
- Active Status (Checkbox)
"""

import os
import sys
import time
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from main import NotionManager, get_notion_token

# Agents Database ID (from documentation)
AGENTS_DB_ID = "257e7361-6c27-802a-93dd-cb88d1c4607b"

def update_agent_settings_database():
    """Update the Agents database with new properties"""
    print("🔧 Updating Agent Settings Database...")
    
    # Initialize Notion client
    token = get_notion_token()
    if not token:
        print("❌ Failed to get Notion token")
        return 1
    
    notion = NotionManager(token)
    
    try:
        # Get current database schema
        print("📊 Retrieving current database schema...")
        database = notion.client.databases.retrieve(database_id=AGENTS_DB_ID)
        existing_props = set(database.get("properties", {}).keys())
        
        print(f"✅ Found {len(existing_props)} existing properties")
        
        # Define new properties to add
        new_properties = {
            "Agent Mode": {
                "select": {
                    "options": [
                        {"name": "MM1", "color": "blue"},
                        {"name": "MM2", "color": "green"},
                        {"name": "Notion-Integrated", "color": "purple"}
                    ]
                }
            },
            "Routing Priority": {
                "number": {
                    "format": "number"
                }
            },
            "Capability Tags": {
                "multi_select": {
                    "options": [
                        {"name": "Research", "color": "blue"},
                        {"name": "Implementation", "color": "green"},
                        {"name": "Review", "color": "yellow"},
                        {"name": "Operations", "color": "orange"}
                    ]
                }
            },
            "Active Status": {
                "checkbox": {}
            }
        }
        
        # Check which properties need to be added
        properties_to_add = {}
        for prop_name, prop_config in new_properties.items():
            if prop_name not in existing_props:
                properties_to_add[prop_name] = prop_config
                print(f"➕ Will add: {prop_name} ({prop_config.get('select') and 'Select' or prop_config.get('multi_select') and 'Multi-select' or prop_config.get('number') and 'Number' or 'Checkbox'})")
            else:
                print(f"✅ Already exists: {prop_name}")
        
        if not properties_to_add:
            print("🎉 All properties already exist!")
            return 0
        
        # Update database with new properties
        print(f"\n🔧 Adding {len(properties_to_add)} new properties...")
        notion.client.databases.update(
            database_id=AGENTS_DB_ID,
            properties=properties_to_add
        )
        
        # Wait a bit to avoid rate limits
        time.sleep(1.0)
        
        # Verify the update
        print("✅ Verifying update...")
        updated_database = notion.client.databases.retrieve(database_id=AGENTS_DB_ID)
        updated_props = set(updated_database.get("properties", {}).keys())
        
        all_added = True
        for prop_name in properties_to_add.keys():
            if prop_name in updated_props:
                print(f"✅ Verified: {prop_name} added successfully")
            else:
                print(f"❌ Warning: {prop_name} not found after update")
                all_added = False
        
        if all_added:
            print(f"\n🎉 Successfully added {len(properties_to_add)} properties to Agents database!")
            print(f"📊 Total properties now: {len(updated_props)}")
            return 0
        else:
            print("\n⚠️  Some properties may not have been added correctly")
            return 1
            
    except Exception as e:
        print(f"❌ Error updating database: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(update_agent_settings_database())


























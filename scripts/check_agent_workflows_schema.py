#!/usr/bin/env python3
"""
Script to check Agent-Workflows database schema and identify duplicate Sub-workflows columns.
"""

import os
import sys
import json
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

try:
    from notion_client import Client
except ImportError:
    print("❌ notion-client not installed. Install with: pip install notion-client")
    sys.exit(1)

# Try to get Notion token
def get_notion_token():
    """Get Notion token from shared_core token manager"""
    # Use centralized token manager (MANDATORY per CLAUDE.md)
    try:
        from shared_core.notion.token_manager import get_notion_token as _get_token
        token = _get_token()
        if token:
            return token
    except ImportError:
        pass

    # Fallback for backwards compatibility
    return (
        os.getenv("NOTION_TOKEN") or
        os.getenv("NOTION_API_TOKEN") or
        os.getenv("NOTION_API_KEY")
    )

# Agent-Workflows Database ID
AGENT_WORKFLOWS_DB_ID = "259e7361-6c27-8192-ae2e-e6d54b4198e1"

def check_schema():
    """Check the Agent-Workflows database schema for duplicate Sub-workflows columns"""
    token = get_notion_token()
    if not token:
        print("❌ Notion token not found")
        sys.exit(1)
    
    client = Client(auth=token)
    
    try:
        # Retrieve database schema
        print("🔍 Retrieving Agent-Workflows database schema...")
        database = client.databases.retrieve(database_id=AGENT_WORKFLOWS_DB_ID)
        
        print(f"\n📊 Database: {database.get('title', [{}])[0].get('plain_text', 'Unknown')}")
        print(f"Database ID: {AGENT_WORKFLOWS_DB_ID}")
        
        properties = database.get('properties', {})
        print(f"\n📋 Total Properties: {len(properties)}")
        
        # Look for Sub-workflows related properties
        print("\n🔍 Searching for Sub-workflows properties...")
        sub_workflow_props = []
        
        for prop_name, prop_details in properties.items():
            prop_name_lower = prop_name.lower()
            if 'sub' in prop_name_lower and 'workflow' in prop_name_lower:
                prop_type = prop_details.get('type', 'unknown')
                prop_id = prop_details.get('id', 'unknown')
                sub_workflow_props.append({
                    'name': prop_name,
                    'type': prop_type,
                    'id': prop_id,
                    'details': prop_details
                })
                print(f"\n  ⚠️  Found: '{prop_name}'")
                print(f"     Type: {prop_type}")
                print(f"     ID: {prop_id}")
        
        if len(sub_workflow_props) > 1:
            print(f"\n❌ DUPLICATE DETECTED: Found {len(sub_workflow_props)} Sub-workflows properties!")
            print("\n📝 Analysis:")
            
            relation_prop = None
            text_prop = None
            
            for prop in sub_workflow_props:
                if prop['type'] == 'relation':
                    relation_prop = prop
                    print(f"\n  ✅ KEEP: '{prop['name']}' (relation property)")
                    print(f"     This is the correct property type for linking to Sub-workflows")
                elif prop['type'] == 'rich_text' or prop['type'] == 'title':
                    text_prop = prop
                    print(f"\n  ❌ REMOVE: '{prop['name']}' ({prop['type']} property)")
                    print(f"     This is the duplicate that should be deleted")
            
            print("\n📋 Recommended Action:")
            if text_prop:
                print(f"  1. Open Agent-Workflows database in Notion UI")
                print(f"  2. Find the property '{text_prop['name']}'")
                print(f"  3. Delete this property (keep the relation property '{relation_prop['name'] if relation_prop else 'Sub-workflows'}')")
                print(f"  4. Verify SQL queries work after removal")
            else:
                print("  ⚠️  Could not identify which property to remove. Manual inspection needed.")
            
            # Save findings to JSON
            findings = {
                'database_id': AGENT_WORKFLOWS_DB_ID,
                'duplicate_found': True,
                'properties': sub_workflow_props,
                'recommendation': {
                    'keep': relation_prop['name'] if relation_prop else None,
                    'remove': text_prop['name'] if text_prop else None
                }
            }
            
            output_file = project_root / 'agent_workflows_schema_findings.json'
            with open(output_file, 'w') as f:
                json.dump(findings, f, indent=2)
            print(f"\n💾 Findings saved to: {output_file}")
            
        elif len(sub_workflow_props) == 1:
            print(f"\n✅ Only one Sub-workflows property found: '{sub_workflow_props[0]['name']}' ({sub_workflow_props[0]['type']})")
            print("   No duplicates detected. Issue may have been resolved.")
        else:
            print("\n⚠️  No Sub-workflows properties found. Database schema may have changed.")
        
        # List all properties for reference
        print("\n📋 All Properties in Database:")
        print("-" * 60)
        for prop_name, prop_details in sorted(properties.items()):
            prop_type = prop_details.get('type', 'unknown')
            print(f"  • {prop_name} ({prop_type})")
        
        return len(sub_workflow_props) > 1
        
    except Exception as e:
        print(f"❌ Error checking schema: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    check_schema()

#!/usr/bin/env python3
"""
Populate Music Workflow Agent-Functions
========================================

This script:
1. Identifies all functions/steps in the Music Track Sync Workflow
2. Creates Agent-Functions items in Notion for each workflow step
3. Updates the Music Workflow page with all missing information

Usage:
    python3 populate_music_workflow_agent_functions.py
"""

import os
import sys
import re
import ast
import inspect
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone

# Add project root to path
project_root = Path(__file__).parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Import Notion client
try:
    from main import get_notion_token, safe_get_property
    from notion_client import Client
    NOTION_AVAILABLE = True
except ImportError as e:
    print(f"Failed to import Notion modules: {e}")
    NOTION_AVAILABLE = False
    Client = None

# Database IDs
AGENT_FUNCTIONS_DB_ID = "256e73616c2780c783facd029ff49d2d"
MUSIC_WORKFLOW_PAGE_ID = "9f228119-be11-43f8-8cfe-f28429e5748c"
TRACKS_DB_ID = os.getenv("TRACKS_DB_ID", "27ce7361-6c27-80fb-b40e-fefdd47d6640")
ARTISTS_DB_ID = os.getenv("ARTISTS_DB_ID", "20ee7361-6c27-816d-9817-d4348f6de07c")

# Workflow scripts
EXECUTION_SCRIPT = project_root / "execute_music_track_sync_workflow.py"
PRODUCTION_SCRIPT = project_root / "monolithic-scripts" / "soundcloud_download_prod_merge-2.py"


def format_database_id(db_id: str) -> str:
    """Convert 32-char hex to UUID format."""
    if not db_id or len(db_id) != 32:
        return db_id
    if '-' in db_id:
        return db_id
    return f"{db_id[:8]}-{db_id[8:12]}-{db_id[12:16]}-{db_id[16:20]}-{db_id[20:]}"


def extract_functions_from_script(script_path: Path) -> List[Dict[str, Any]]:
    """Extract all function definitions from a Python script."""
    functions = []
    
    if not script_path.exists():
        print(f"Warning: Script not found: {script_path}")
        return functions
    
    try:
        content = script_path.read_text(encoding='utf-8')
        tree = ast.parse(content, filename=str(script_path))
        
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                # Extract function name
                func_name = node.name
                
                # Skip private/helper functions that start with underscore
                if func_name.startswith('_'):
                    continue
                
                # Skip main function
                if func_name == 'main':
                    continue
                
                # Extract docstring
                docstring = ast.get_docstring(node) or ""
                
                # Extract function signature
                args = [arg.arg for arg in node.args.args]
                if 'self' in args:
                    args.remove('self')
                
                # Get line numbers
                lineno = node.lineno
                
                # Determine phase/category based on function name and docstring
                phase = "Unknown"
                if "pre" in func_name.lower() or "intelligence" in func_name.lower() or "plan" in func_name.lower():
                    phase = "Pre-Execution"
                elif "post" in func_name.lower() or "automation" in func_name.lower() or "verify" in func_name.lower():
                    phase = "Post-Execution"
                elif "fallback" in func_name.lower() or "spotify" in func_name.lower() or "soundcloud" in func_name.lower():
                    phase = "Source Detection"
                elif "execute" in func_name.lower() or "workflow" in func_name.lower():
                    phase = "Execution"
                elif "error" in func_name.lower() or "critical" in func_name.lower():
                    phase = "Error Handling"
                
                functions.append({
                    "name": func_name,
                    "docstring": docstring,
                    "args": args,
                    "lineno": lineno,
                    "phase": phase,
                    "script": script_path.name
                })
    except Exception as e:
        print(f"Error parsing {script_path}: {e}")
    
    return functions


def create_agent_function(
    notion_client: Client,
    function_info: Dict[str, Any],
    workflow_page_id: str
) -> Optional[str]:
    """Create an Agent-Function item in Notion."""
    try:
        func_name = function_info["name"]
        docstring = function_info.get("docstring", "")
        phase = function_info.get("phase", "Unknown")
        script = function_info.get("script", "")
        args = function_info.get("args", [])
        
        # Create description
        description = f"**Function:** `{func_name}`\n\n"
        description += f"**Phase:** {phase}\n\n"
        description += f"**Script:** `{script}`\n\n"
        
        if args:
            description += f"**Parameters:** `{', '.join(args)}`\n\n"
        
        if docstring:
            # Clean up docstring
            docstring_lines = docstring.split('\n')
            cleaned_doc = '\n'.join(line.strip() for line in docstring_lines if line.strip())
            description += f"**Description:**\n{cleaned_doc[:1000]}\n\n"  # Limit to 1000 chars
        
        description += f"**Role in Workflow:**\n"
        
        # Add role description based on function name
        if "verify" in func_name.lower():
            description += "Verifies workflow execution results and file creation.\n"
        elif "execute" in func_name.lower():
            description += "Executes the main production workflow or sub-workflow step.\n"
        elif "identify" in func_name.lower():
            description += "Identifies related items, issues, or automation opportunities.\n"
        elif "create" in func_name.lower():
            description += "Creates Notion tasks, issues, or other artifacts.\n"
        elif "fetch" in func_name.lower() or "get" in func_name.lower():
            description += "Retrieves data from external sources or APIs.\n"
        elif "update" in func_name.lower():
            description += "Updates workflow documentation or Notion properties.\n"
        elif "review" in func_name.lower():
            description += "Reviews plans, logs, or other sources for intelligence gathering.\n"
        else:
            description += "Performs a workflow step as part of the music track sync process.\n"
        
        # Create properties
        properties = {
            "Function Name": {
                "title": [{"text": {"content": func_name}}]
            },
            "Description": {
                "rich_text": [{"text": {"content": description[:2000]}}]  # Notion limit
            }
        }
        
        # Try to add phase/category if property exists
        try:
            properties["Phase"] = {
                "select": {"name": phase}
            }
        except:
            pass
        
        # Try to add script reference if property exists
        try:
            properties["Script"] = {
                "rich_text": [{"text": {"content": script}}]
            }
        except:
            pass
        
        # Link to workflow
        try:
            properties["Workflow"] = {
                "relation": [{"id": workflow_page_id}]
            }
        except:
            pass
        
        # Try to get database schema to find valid status options
        try:
            db_schema = notion_client.databases.retrieve(database_id=format_database_id(AGENT_FUNCTIONS_DB_ID))
            
            # Try to set status if property exists
            status_prop = db_schema.get("properties", {}).get("Status", {})
            if status_prop.get("type") == "status":
                status_options = status_prop.get("status", {}).get("options", [])
                if status_options:
                    properties["Status"] = {
                        "status": {"name": status_options[0].get("name", "Active")}
                    }
        except Exception as e:
            print(f"Warning: Could not retrieve database schema: {e}")
        
        # Create the page
        page = notion_client.pages.create(
            parent={"database_id": format_database_id(AGENT_FUNCTIONS_DB_ID)},
            properties=properties
        )
        
        return page.get("id")
    except Exception as e:
        print(f"Error creating Agent-Function for {function_info.get('name', 'unknown')}: {e}")
        import traceback
        traceback.print_exc()
        return None


def update_music_workflow_page(
    notion_client: Client,
    functions: List[Dict[str, Any]],
    agent_function_ids: List[str]
) -> bool:
    """Update the Music Workflow page with all missing information."""
    try:
        # Get current page
        page = notion_client.pages.retrieve(page_id=MUSIC_WORKFLOW_PAGE_ID)
        
        # Prepare updates
        updates = {}
        
        # Update Workflow Steps (JSON) field if it exists
        workflow_steps = []
        for func in functions:
            step = {
                "name": func["name"],
                "phase": func["phase"],
                "script": func["script"],
                "description": func.get("docstring", "")[:200]
            }
            workflow_steps.append(step)
        
        # Try to update Agent-Functions relation if property exists
        try:
            db_schema = notion_client.databases.retrieve(database_id=format_database_id(AGENT_FUNCTIONS_DB_ID))
            
            # Get workflow page properties
            page_props = page.get("properties", {})
            
            # Try to find Agent-Functions property in workflow page
            workflow_page = notion_client.pages.retrieve(page_id=MUSIC_WORKFLOW_PAGE_ID)
            workflow_props = workflow_page.get("properties", {})
            
            # Look for relation property that might link to Agent-Functions
            for prop_name, prop_data in workflow_props.items():
                if prop_data.get("type") == "relation":
                    # Try to update if it's the Agent-Functions relation
                    if agent_function_ids:
                        try:
                            notion_client.pages.update(
                                page_id=MUSIC_WORKFLOW_PAGE_ID,
                                properties={
                                    prop_name: {
                                        "relation": [{"id": fid} for fid in agent_function_ids]
                                    }
                                }
                            )
                            print(f"Updated {prop_name} relation with {len(agent_function_ids)} functions")
                        except Exception as e:
                            print(f"Could not update {prop_name}: {e}")
        except Exception as e:
            print(f"Warning: Could not update relations: {e}")
        
        # Add workflow steps as blocks
        blocks_to_add = []
        
        # Add section header
        blocks_to_add.append({
            "object": "block",
            "type": "heading_2",
            "heading_2": {
                "rich_text": [{"type": "text", "text": {"content": "Workflow Functions"}}]
            }
        })
        
        # Group by phase
        phases = {}
        for func in functions:
            phase = func["phase"]
            if phase not in phases:
                phases[phase] = []
            phases[phase].append(func)
        
        # Add functions by phase
        for phase, phase_funcs in sorted(phases.items()):
            blocks_to_add.append({
                "object": "block",
                "type": "heading_3",
                "heading_3": {
                    "rich_text": [{"type": "text", "text": {"content": phase}}]
                }
            })
            
            for func in phase_funcs:
                func_text = f"**{func['name']}** ({func['script']})"
                if func.get("docstring"):
                    doc_preview = func["docstring"].split('\n')[0][:100]
                    func_text += f"\n{doc_preview}"
                
                blocks_to_add.append({
                    "object": "block",
                    "type": "bulleted_list_item",
                    "bulleted_list_item": {
                        "rich_text": [{"type": "text", "text": {"content": func_text}}]
                    }
                })
        
        # Append blocks to page
        if blocks_to_add:
            try:
                notion_client.blocks.children.append(
                    block_id=MUSIC_WORKFLOW_PAGE_ID,
                    children=blocks_to_add[:100]  # Notion limit
                )
                print(f"Added {len(blocks_to_add)} blocks to workflow page")
            except Exception as e:
                print(f"Warning: Could not add blocks: {e}")
        
        return True
    except Exception as e:
        print(f"Error updating Music Workflow page: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Main execution function."""
    print("=" * 80)
    print("MUSIC WORKFLOW AGENT-FUNCTIONS POPULATION")
    print("=" * 80)
    
    if not NOTION_AVAILABLE:
        print("Error: Notion client not available")
        return 1
    
    # Get Notion token
    notion_token = get_notion_token()
    if not notion_token:
        print("Error: Notion token not available")
        return 1
    
    notion_client = Client(auth=notion_token)
    
    # Extract functions from both scripts
    print("\n1. Extracting functions from workflow scripts...")
    execution_functions = extract_functions_from_script(EXECUTION_SCRIPT)
    production_functions = extract_functions_from_script(PRODUCTION_SCRIPT)
    
    # Filter production script functions to only key workflow functions
    key_production_functions = [
        f for f in production_functions 
        if any(keyword in f["name"].lower() for keyword in [
            "process_track", "download", "deduplicate", "eagle", "notion",
            "spotify", "audio", "fingerprint", "normalize", "convert"
        ])
    ]
    
    all_functions = execution_functions + key_production_functions
    print(f"   → Found {len(execution_functions)} functions in execution script")
    print(f"   → Found {len(key_production_functions)} key functions in production script")
    print(f"   → Total: {len(all_functions)} functions to create")
    
    # Create Agent-Functions items
    print("\n2. Creating Agent-Functions items...")
    created_ids = []
    for func in all_functions:
        func_id = create_agent_function(notion_client, func, MUSIC_WORKFLOW_PAGE_ID)
        if func_id:
            created_ids.append(func_id)
            print(f"   ✅ Created: {func['name']} ({func['phase']})")
        else:
            print(f"   ❌ Failed: {func['name']}")
    
    print(f"\n   → Created {len(created_ids)} Agent-Functions items")
    
    # Update Music Workflow page
    print("\n3. Updating Music Workflow page...")
    success = update_music_workflow_page(notion_client, all_functions, created_ids)
    
    if success:
        print("   ✅ Music Workflow page updated")
    else:
        print("   ⚠️  Some updates may have failed")
    
    print("\n" + "=" * 80)
    print("COMPLETE")
    print(f"   → {len(created_ids)} Agent-Functions items created")
    print("=" * 80)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

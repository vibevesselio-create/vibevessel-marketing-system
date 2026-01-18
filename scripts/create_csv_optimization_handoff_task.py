#!/usr/bin/env python3
"""
Create CSV Optimization Handoff Task for Claude Code Agent
==========================================================

Creates a Notion task and handoff trigger file for Claude Code Agent to implement
CSV backup optimizations across the music synchronization workflow.

Author: Cursor MM1 Agent
Date: 2026-01-13
"""

import os
import sys
import json
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

# Add project root to path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

try:
    from shared_core.notion.token_manager import get_notion_token
    from notion_client import Client
    NOTION_AVAILABLE = True
except ImportError:
    NOTION_AVAILABLE = False
    print("⚠️  notion-client not available. Install with: pip install notion-client")
    Client = None

# Configuration
AGENT_TASKS_DB_ID = os.getenv("AGENT_TASKS_DB_ID", "284e73616c278018872aeb14e82e0392")
CLAUDE_CODE_AGENT_ID = "2cfe7361-6c27-805f-857c-e90c3db6efb9"  # Claude Code Agent

# Try to import from main.py for trigger file creation
try:
    from main import normalize_agent_folder_name, MM1_AGENT_TRIGGER_BASE
    TRIGGER_BASE_AVAILABLE = True
except ImportError:
    TRIGGER_BASE_AVAILABLE = False
    MM1_AGENT_TRIGGER_BASE = Path("/Users/brianhellemn/Documents/Agents/Agent-Triggers")
    
    def normalize_agent_folder_name(agent_name: str) -> str:
        """Normalize agent name for folder."""
        return agent_name.replace(" ", "-")


def get_notion_token() -> Optional[str]:
    """Get Notion token from environment or unified_config."""
    try:
        from shared_core.notion.token_manager import get_notion_token as get_token
        return get_token()
    except ImportError:
        return os.getenv("NOTION_TOKEN")


def create_task_in_notion(client: Client) -> tuple[Optional[str], Optional[str]]:
    """Create the CSV optimization task in Notion Agent-Tasks database."""
    
    # Short description for property field (under 2000 chars)
    short_description = """Implement CSV backup optimizations across the music synchronization workflow.

Key Deliverables:
1. Rate Limit Fallback - Automatic CSV fallback on 429 errors
2. Liked Songs CSV Direct Access - Use Liked_Songs.csv directly  
3. Batch Playlist Sync - CSV-first sync mode
4. Batch Track Metadata - Batch CSV lookups
5. Performance Testing - Measure and validate improvements

Expected Impact: 70-85% API call reduction, 3-10x performance improvement, 100% reliability.

See task page for full details and reference documents."""
    
    # Full description for child blocks
    full_description_blocks = [
        {"type": "heading_2", "content": "Objective"},
        {"type": "paragraph", "content": "Implement CSV backup optimizations across the music synchronization workflow to achieve:\n- 70-85% reduction in API calls\n- 3-10x performance improvement for batch operations\n- 100% reliability improvement (no workflow stops on rate limits)\n- Full offline capability"},
        {"type": "heading_2", "content": "Key Deliverables"},
        {"type": "heading_3", "content": "1. Rate Limit Fallback"},
        {"type": "paragraph", "content": "Location: monolithic-scripts/spotify_integration_module.py\nTask: Modify _make_request() method to automatically fallback to CSV on 429 errors\n\nRequirements:\n- Detect rate limit (429 status code)\n- Automatically switch to CSV backup\n- Continue workflow without interruption\n- Log CSV usage for monitoring\n- Transparent to caller (API method returns data regardless of source)\n\nReference: monolithic-scripts/spotify_integration_module_csv_enhancement.py (enhancement code provided)"},
        {"type": "heading_3", "content": "2. Liked Songs CSV Direct Access"},
        {"type": "paragraph", "content": "Location: execute_music_track_sync_workflow.py\nTask: Modify fetch_spotify_liked_tracks() to use Liked_Songs.csv directly\n\nRequirements:\n- Read Liked_Songs.csv directly (no API calls)\n- Parse tracks from CSV file\n- Convert CSV format to expected format\n- Fallback to API only if CSV unavailable\n- Maintain existing function signature\n\nExpected Impact: 100% API call reduction for Liked Songs fetches"},
        {"type": "heading_3", "content": "3. Batch Playlist Sync"},
        {"type": "paragraph", "content": "Location: scripts/sync_spotify_playlist.py\nTask: Add CSV-first sync mode\n\nRequirements:\n- Load playlist CSV file first\n- Bulk create tracks in Notion from CSV data (no API calls)\n- Compare with API to find new/changed tracks\n- Update only changed tracks via API\n- Fallback to API-only sync if CSV unavailable\n\nExpected Impact: 90-95% API call reduction for initial syncs\n\nReference: SPOTIFY_CSV_BACKUP_INTEGRATION_PLAN.md for implementation details"},
        {"type": "heading_3", "content": "4. Batch Track Metadata"},
        {"type": "paragraph", "content": "Location: execute_music_track_sync_workflow.py\nTask: Modify add_spotify_track_to_notion() to batch CSV lookups\n\nRequirements:\n- Check CSV first for track metadata\n- Batch lookup multiple tracks in CSV simultaneously\n- Use API only for tracks not in CSV\n- Cache CSV lookups for repeated access\n- Maintain existing function signature\n\nExpected Impact: 70-80% API call reduction for tracks in CSV"},
        {"type": "heading_3", "content": "5. Performance Testing"},
        {"type": "paragraph", "content": "Task: Measure and validate optimization improvements\n\nRequirements:\n- Measure API call reduction (target: 70-85%)\n- Measure performance improvements (target: 3-10x faster)\n- Validate reliability gains (no workflow stops on rate limits)\n- Test with real CSV files and API responses\n- Generate performance report"},
        {"type": "heading_2", "content": "Implementation Priority"},
        {"type": "heading_3", "content": "Phase 1: Core Optimizations (High Impact, Low Risk)"},
        {"type": "bulleted_list_item", "content": "Rate Limit Fallback - Critical for reliability"},
        {"type": "bulleted_list_item", "content": "Liked Songs CSV - High impact, low risk, quick win"},
        {"type": "heading_3", "content": "Phase 2: Batch Optimizations (High Impact, Medium Risk)"},
        {"type": "bulleted_list_item", "content": "Batch Playlist Sync - High impact, requires careful implementation"},
        {"type": "bulleted_list_item", "content": "Batch Track Metadata - High impact, complements playlist sync"},
        {"type": "heading_2", "content": "Reference Documents"},
        {"type": "bulleted_list_item", "content": "SPOTIFY_CSV_WORKFLOW_OPTIMIZATION_ANALYSIS.md - Primary analysis"},
        {"type": "bulleted_list_item", "content": "SPOTIFY_CSV_OPTIMIZATION_SECONDARY_ANALYSIS.md - Secondary validation"},
        {"type": "bulleted_list_item", "content": "SPOTIFY_CSV_BACKUP_INTEGRATION_PLAN.md - Integration plan"},
        {"type": "bulleted_list_item", "content": "SPOTIFY_CSV_INTEGRATION_IMPLEMENTATION_GUIDE.md - Implementation guide"},
        {"type": "bulleted_list_item", "content": "monolithic-scripts/spotify_csv_backup.py - CSV backup module (already implemented)"},
        {"type": "bulleted_list_item", "content": "monolithic-scripts/spotify_integration_module_csv_enhancement.py - Enhancement code snippets"},
        {"type": "heading_2", "content": "Acceptance Criteria"},
        {"type": "bulleted_list_item", "content": "All optimizations implemented and tested"},
        {"type": "bulleted_list_item", "content": "API call reduction verified (70-85% target)"},
        {"type": "bulleted_list_item", "content": "Performance improvements measured (3-10x target)"},
        {"type": "bulleted_list_item", "content": "Reliability improvements validated (no workflow stops)"},
        {"type": "bulleted_list_item", "content": "Feature flags implemented for enable/disable"},
        {"type": "bulleted_list_item", "content": "Comprehensive error handling and logging"},
        {"type": "bulleted_list_item", "content": "Documentation updated"},
        {"type": "bulleted_list_item", "content": "Performance report generated"},
        {"type": "heading_2", "content": "Success Metrics"},
        {"type": "paragraph", "content": "API Call Reduction: 70-85% overall\nPerformance Improvement: 3-10x faster for batch operations\nReliability: 100% (no workflow stops on rate limits)\nOffline Capability: Full workflow functionality without API"},
        {"type": "heading_2", "content": "Notes"},
        {"type": "paragraph", "content": "- CSV files are less-frequently-updated backups (acceptable for optimization use case)\n- Always maintain API fallback for CSV failures\n- Use feature flags to enable/disable optimizations\n- Comprehensive logging of CSV usage for monitoring\n- Test with real CSV files and API responses"}
    ]

    try:
        # Get database schema to understand properties
        db = client.databases.retrieve(database_id=AGENT_TASKS_DB_ID)
        db_schema = db.get("properties", {})
        
        # Build task properties
        properties = {
            "Task Name": {
                "title": [{"text": {"content": "Optimize Music Synchronization Workflow with CSV Backup Integration"}}]
            },
            "Status": {
                "status": {"name": "Ready"}
            },
            "Priority": {
                "select": {"name": "High"}
            },
            "Description": {
                "rich_text": [{"text": {"content": short_description}}]
            }
        }
        
        # Add Task Type if it exists
        if "Task Type" in db_schema:
            properties["Task Type"] = {
                "select": {"name": "Implementation"}
            }
        
        # Note: Assignee will be set manually in Notion or via handoff trigger
        
        # Create task
        response = client.pages.create(
            parent={"database_id": AGENT_TASKS_DB_ID},
            properties=properties
        )
        
        task_id = response.get("id")
        task_url = f"https://www.notion.so/{task_id.replace('-', '')}"
        
        # Add full description as child blocks
        children = []
        for block_data in full_description_blocks:
            block_type = block_data["type"]
            content = block_data["content"]
            
            if block_type == "heading_2":
                children.append({
                    "object": "block",
                    "type": "heading_2",
                    "heading_2": {
                        "rich_text": [{"type": "text", "text": {"content": content}}]
                    }
                })
            elif block_type == "heading_3":
                children.append({
                    "object": "block",
                    "type": "heading_3",
                    "heading_3": {
                        "rich_text": [{"type": "text", "text": {"content": content}}]
                    }
                })
            elif block_type == "paragraph":
                children.append({
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{"type": "text", "text": {"content": content}}]
                    }
                })
            elif block_type == "bulleted_list_item":
                children.append({
                    "object": "block",
                    "type": "bulleted_list_item",
                    "bulleted_list_item": {
                        "rich_text": [{"type": "text", "text": {"content": content}}]
                    }
                })
        
        # Append children blocks
        if children:
            try:
                client.blocks.children.append(block_id=task_id, children=children)
                print(f"✅ Added detailed description blocks to task")
            except Exception as e:
                print(f"⚠️  Could not add description blocks: {e}")
        
        print(f"✅ Created Notion task: {task_id}")
        print(f"   URL: {task_url}")
        
        return task_id, task_url
        
    except Exception as e:
        print(f"❌ Error creating Notion task: {e}")
        import traceback
        traceback.print_exc()
        return None, None


def create_handoff_trigger_file(task_id: str, task_url: str) -> Optional[Path]:
    """Create handoff trigger file for Claude Code Agent."""
    try:
        agent_name = "Claude Code Agent"
        agent_folder = normalize_agent_folder_name(agent_name)
        trigger_folder = MM1_AGENT_TRIGGER_BASE / agent_folder / "01_inbox"
        trigger_folder.mkdir(parents=True, exist_ok=True)
        
        # Create timestamp
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        
        # Create filename
        task_title = "Optimize-Music-Synchronization-Workflow-CSV-Backup-Integration"
        filename = f"{timestamp}__HANDOFF__{task_title}__{task_id[:8]}.json"
        
        # Create trigger file data
        trigger_data = {
            "task_id": task_id,
            "task_title": "Optimize Music Synchronization Workflow with CSV Backup Integration",
            "task_url": task_url,
            "description": """Implement CSV backup optimizations across the music synchronization workflow.

Key Deliverables:
1. Rate Limit Fallback - Automatic CSV fallback on 429 errors
2. Liked Songs CSV Direct Access - Use Liked_Songs.csv directly
3. Batch Playlist Sync - CSV-first sync mode
4. Batch Track Metadata - Batch CSV lookups
5. Performance Testing - Measure and validate improvements

Expected Impact:
- 70-85% API call reduction
- 3-10x performance improvement
- 100% reliability improvement (no workflow stops)
- Full offline capability

See reference documents for detailed implementation requirements.""",
            "status": "Ready",
            "agent_name": agent_name,
            "agent_type": "MM1",
            "priority": "High",
            "created_at": timestamp,
            "handoff_instructions": "Implement CSV backup optimizations as specified in the Notion task and reference documents.",
            "reference_documents": [
                "SPOTIFY_CSV_WORKFLOW_OPTIMIZATION_ANALYSIS.md",
                "SPOTIFY_CSV_OPTIMIZATION_SECONDARY_ANALYSIS.md",
                "SPOTIFY_CSV_BACKUP_INTEGRATION_PLAN.md",
                "SPOTIFY_CSV_INTEGRATION_IMPLEMENTATION_GUIDE.md",
                "monolithic-scripts/spotify_csv_backup.py",
                "monolithic-scripts/spotify_integration_module_csv_enhancement.py"
            ]
        }
        
        # Write trigger file
        trigger_file_path = trigger_folder / filename
        with open(trigger_file_path, 'w', encoding='utf-8') as f:
            json.dump(trigger_data, f, indent=2, ensure_ascii=False)
        
        print(f"✅ Created trigger file: {trigger_file_path}")
        return trigger_file_path
        
    except Exception as e:
        print(f"❌ Error creating trigger file: {e}")
        import traceback
        traceback.print_exc()
        return None


def main():
    """Main function to create task and handoff file."""
    if not NOTION_AVAILABLE:
        print("❌ notion-client not available. Install with: pip install notion-client")
        sys.exit(1)
    
    token = get_notion_token()
    if not token:
        print("❌ NOTION_TOKEN not found in environment or unified_config")
        sys.exit(1)
    
    client = Client(auth=token)
    
    print("🚀 Creating CSV Optimization Handoff Task for Claude Code Agent...\n")
    print("="*80)
    
    # Step 1: Create Notion task
    print("\n📋 Step 1: Creating Notion task...")
    task_id, task_url = create_task_in_notion(client)
    
    if not task_id:
        print("❌ Failed to create Notion task. Exiting.")
        sys.exit(1)
    
    # Step 2: Create handoff trigger file
    print("\n📁 Step 2: Creating handoff trigger file...")
    trigger_file = create_handoff_trigger_file(task_id, task_url)
    
    if not trigger_file:
        print("⚠️  Failed to create trigger file, but task was created.")
        print(f"   Task URL: {task_url}")
        sys.exit(1)
    
    # Summary
    print("\n" + "="*80)
    print("✅ HANDOFF TASK CREATION COMPLETE")
    print("="*80)
    print(f"\n📋 Notion Task:")
    print(f"   ID: {task_id}")
    print(f"   URL: {task_url}")
    print(f"\n📁 Trigger File:")
    print(f"   Path: {trigger_file}")
    print(f"\n🎯 Next Steps:")
    print(f"   1. Claude Code Agent will process the trigger file")
    print(f"   2. Review the Notion task for detailed requirements")
    print(f"   3. Reference documents are listed in the task description")
    print(f"   4. Begin implementation with Phase 1 optimizations")


if __name__ == "__main__":
    main()

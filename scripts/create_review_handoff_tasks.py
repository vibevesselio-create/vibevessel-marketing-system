#!/usr/bin/env python3
"""
Create handoff tasks for Claude Code Agent and ChatGPT Strategic Agent
to review the DriveSheetsSync multi-file type sync implementation.
"""

import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

try:
    from notion_client import Client
except ImportError:
    print("ERROR: notion-client not available. Install with: pip install notion-client", file=sys.stderr)
    sys.exit(1)

# Database IDs
AGENT_TASKS_DB_ID = "284e73616c278018872aeb14e82e0392"

# Agent IDs
CLAUDE_CODE_AGENT_ID = "2cfe7361-6c27-805f-857c-e90c3db6efb9"
CHATGPT_STRATEGIC_AGENT_ID = "fa54f05c-e184-403a-ac28-87dd8ce9855b"

def get_notion_token() -> Optional[str]:
    """Get Notion API token from environment or unified_config"""
    # Check environment first
    token = os.getenv("NOTION_TOKEN") or os.getenv("NOTION_API_TOKEN") or os.getenv("VV_AUTOMATIONS_WS_TOKEN")
    if token:
        return token
    
    # Fallback to unified_config
    try:
        # Add parent directory to path for imports
        script_dir = Path(__file__).parent
        project_root = script_dir.parent
        if str(project_root) not in sys.path:
            sys.path.insert(0, str(project_root))
        
        from unified_config import get_notion_token as unified_get_token
        token = unified_get_token()
        return token
    except Exception as e:
        # Debug: print error if needed
        if os.getenv("DEBUG_HANDOFF"):
            print(f"DEBUG: unified_config import failed: {e}", file=sys.stderr)
        return None

def create_agent_task(
    client: Client,
    title: str,
    description: str,
    assigned_agent_id: str,
    priority: str = "High",
    dependency_status: str = "Ready",
    task_type: str = "Review"
) -> Optional[str]:
    """Create an Agent-Task in Notion"""
    try:
        properties = {
            "Task Name": {
                "title": [{"text": {"content": title}}]
            },
            "Description": {
                "rich_text": [{"text": {"content": description}}]
            },
            "Priority": {
                "select": {"name": priority}
            },
            "Dependency Status": {
                "select": {"name": dependency_status}
            },
            "Task Type": {
                "select": {"name": task_type}
            },
            "Assigned-Agent": {
                "relation": [{"id": assigned_agent_id}]
            }
        }
        
        response = client.pages.create(
            parent={"database_id": AGENT_TASKS_DB_ID},
            properties=properties
        )
        
        task_id = response.get("id")
        task_url = response.get("url", "")
        return task_id, task_url
    except Exception as e:
        print(f"ERROR creating Agent-Task '{title}': {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return None, None

def create_trigger_file(
    agent_name: str,
    task_id: str,
    task_url: str,
    task_title: str,
    task_description: str,
    from_agent: str = "Cursor MM1 Agent",
    priority: str = "High"
) -> Optional[Path]:
    """Create trigger file for agent"""
    try:
        # Agent trigger folder paths
        DOCUMENT_TRIGGER_BASE = Path("/Users/brianhellemn/Documents/Agents/Agent-Triggers")
        DRIVE_TRIGGER_BASE = Path("/Users/brianhellemn/Library/CloudStorage/GoogleDrive-brian@serenmedia.co/My Drive/Agents/Agent-Triggers-gd")
        
        AGENT_TRIGGER_PATHS = {
            'Claude Code Agent': DOCUMENT_TRIGGER_BASE / 'Claude-Code-Agent-Trigger' / '01_inbox',
            'ChatGPT Strategic Agent': DRIVE_TRIGGER_BASE / 'ChatGPT-Strategic-Agent-Trigger-gd' / '01_inbox',
            'Claude Code Review Agent': DOCUMENT_TRIGGER_BASE / 'Claude-Code-Agent-Trigger' / '01_inbox',
        }
        
        inbox_path = AGENT_TRIGGER_PATHS.get(agent_name)
        if not inbox_path:
            # Try fallback
            AGENT_TRIGGER_PATHS_FALLBACK = {
                'Claude Code Agent': DRIVE_TRIGGER_BASE / 'Claude-Code-Agent-Trigger-gd' / '01_inbox',
                'ChatGPT Strategic Agent': DRIVE_TRIGGER_BASE / 'ChatGPT-Strategic-Agent-Trigger-gd' / '01_inbox',
            }
            inbox_path = AGENT_TRIGGER_PATHS_FALLBACK.get(agent_name)
        
        if not inbox_path:
            # Fallback to local temp
            inbox_path = Path.home() / "Documents" / "Agents" / "execution_logs" / "handoff_triggers"
            print(f"   ⚠️  Using fallback trigger path: {inbox_path}", file=sys.stderr)
        
        inbox_path.mkdir(parents=True, exist_ok=True)
        
        # Generate filename
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        task_id_short = task_id.replace("-", "")[:8]
        safe_title = task_title.replace(" ", "-").replace("/", "-")[:50]
        filename = f"{timestamp}__HANDOFF__{safe_title}__{task_id_short}.md"
        
        trigger_file = inbox_path / filename
        
        # Build trigger file content
        trigger_content = f"""# HANDOFF: {task_title}

**From:** {from_agent}
**Date:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC
**Priority:** {priority}
**Agent-Task ID:** {task_id}

## Action Required
{task_description[:500]}{'...' if len(task_description) > 500 else ''}

## Notion Link
{task_url}

## Start Immediately
{'Yes' if priority in ['Critical', 'High'] else 'No'} — based on priority

## Full Task Description
{task_description}
"""
        
        trigger_file.write_text(trigger_content, encoding='utf-8')
        return trigger_file
        
    except Exception as e:
        print(f"   ⚠️  Failed to create trigger file for {agent_name}: {e}", file=sys.stderr)
        return None

def main():
    token = get_notion_token()
    if not token:
        print("ERROR: NOTION_TOKEN not found in environment", file=sys.stderr)
        sys.exit(1)
    
    client = Client(auth=token)
    
    # Task 1: Claude Code Agent - Code Review
    task_title_1 = "Review DriveSheetsSync Multi-File Type Sync Implementation"
    task_desc_1 = """Review the new multi-file type synchronization functionality in DriveSheetsSync (Code.gs) that extends beyond markdown files to support photos, videos, and other file types.

**Scope:**
- Review new functions: extractFileMetadata_, calculateFileHash_, mapFileMetadataToProperties_, syncFilesToNotion_
- Review Item-Type relation implementation and integration
- Review overall implementation architecture and patterns
- Validate against Eagle Application sync patterns for photos/videos
- Identify critical issues, optimizations, and gaps

**MANDATORY REQUIREMENTS:**
1. Perform web searches to validate against CURRENT Notion API documentation
2. Perform web searches to validate against CURRENT Google Apps Script documentation
3. Identify all gaps, issues, or enhancements needed
4. Return comprehensive report detailing:
   - Critical issues (blocking, security, data integrity)
   - Performance optimizations
   - Code quality improvements
   - Missing functionality or edge cases
   - Documentation gaps
   - Best practices alignment

**Files to Review:**
- gas-scripts/drive-sheets-sync/Code.gs (new functions and integration)
- Reference: monolithic-scripts/eagle_sync_to_GD_and_Notion-fingerprint-cursor-2.py (for photo/video patterns)
- Reference: seren-media-workflows/python-scripts/davinci_resolve_sync.py (for Item-Type relation patterns)

**Deliverable:**
Comprehensive review report with prioritized findings and recommendations."""
    
    # Task 2: ChatGPT Strategic Agent - Strategic Review
    task_title_2 = "Strategic Review: DriveSheetsSync Multi-File Type Sync Implementation"
    task_desc_2 = """Perform strategic review of the DriveSheetsSync multi-file type synchronization implementation, focusing on architecture, scalability, and alignment with system requirements.

**Scope:**
- Strategic architecture review
- Scalability and performance considerations
- Integration patterns with existing systems
- Alignment with Universal Agent Handoff Model requirements
- Documentation and process alignment

**MANDATORY REQUIREMENTS:**
1. Perform web searches to validate against CURRENT best practices for:
   - Google Apps Script file synchronization patterns
   - Notion API file handling best practices
   - Multi-file type sync architectures
2. Identify strategic gaps, issues, or enhancements
3. Return comprehensive strategic report detailing:
   - Architecture recommendations
   - Scalability concerns
   - Integration improvements
   - Process alignment issues
   - Strategic enhancements

**Files to Review:**
- gas-scripts/drive-sheets-sync/Code.gs (overall implementation)
- System documentation and requirements
- Integration points with other sync scripts

**Deliverable:**
Strategic review report with high-level recommendations and architectural guidance."""
    
    print("Creating handoff tasks...")
    
    # Create Task 1
    print(f"\n1. Creating task for Claude Code Agent...")
    task_id_1, task_url_1 = create_agent_task(
        client=client,
        title=task_title_1,
        description=task_desc_1,
        assigned_agent_id=CLAUDE_CODE_AGENT_ID,
        priority="High",
        task_type="Review"
    )
    
    if task_id_1:
        print(f"   ✅ Created task: {task_id_1}")
        print(f"   URL: {task_url_1}")
        
        # Create trigger file
        trigger_file_1 = create_trigger_file(
            agent_name="Claude Code Agent",
            task_id=task_id_1,
            task_url=task_url_1,
            task_title=task_title_1,
            task_description=task_desc_1,
            priority="High"
        )
        if trigger_file_1:
            print(f"   ✅ Created trigger file: {trigger_file_1}")
    else:
        print(f"   ❌ Failed to create task 1")
    
    # Create Task 2
    print(f"\n2. Creating task for ChatGPT Strategic Agent...")
    task_id_2, task_url_2 = create_agent_task(
        client=client,
        title=task_title_2,
        description=task_desc_2,
        assigned_agent_id=CHATGPT_STRATEGIC_AGENT_ID,
        priority="High",
        task_type="Review"
    )
    
    if task_id_2:
        print(f"   ✅ Created task: {task_id_2}")
        print(f"   URL: {task_url_2}")
        
        # Create trigger file
        trigger_file_2 = create_trigger_file(
            agent_name="ChatGPT Strategic Agent",
            task_id=task_id_2,
            task_url=task_url_2,
            task_title=task_title_2,
            task_description=task_desc_2,
            priority="High"
        )
        if trigger_file_2:
            print(f"   ✅ Created trigger file: {trigger_file_2}")
    else:
        print(f"   ❌ Failed to create task 2")
    
    print("\n✅ Handoff task creation complete!")

if __name__ == "__main__":
    main()


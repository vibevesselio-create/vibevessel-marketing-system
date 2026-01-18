#!/usr/bin/env python3
"""
Create Handoff Task for Eagle Library Merge Completion
=======================================================

Creates a Notion task and return handoff trigger file requesting completion of:
1. Any remaining remediations needed
2. Production run of the Eagle library merge and deduplication workflow

Success Criteria: Error-free execution on a successful Eagle library merge 
and deduplication in the target (active) library.
"""

import os
import sys
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict

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

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('create_eagle_merge_completion_handoff.log')
    ]
)
logger = logging.getLogger(__name__)

# Try to import notion-client
try:
    from notion_client import Client
    NOTION_CLIENT_AVAILABLE = True
except ImportError:
    logger.error("notion-client not available. Install with: pip install notion-client")
    NOTION_CLIENT_AVAILABLE = False
    Client = None

# Import from main.py
try:
    from main import (
        get_notion_token, safe_get_property,
        MM1_AGENT_TRIGGER_BASE, AGENT_TASKS_DB_ID
    )
except ImportError as e:
    logger.warning(f"Could not import from main.py: {e}")
    # Fallback values
    MM1_AGENT_TRIGGER_BASE = Path("/Users/brianhellemn/Documents/Agents/Agent-Triggers")
    AGENT_TASKS_DB_ID = "284e73616c278018872aeb14e82e0392"
    
    def get_notion_token():
        return os.getenv("NOTION_TOKEN")


def get_agent_inbox_path(agent_name: str) -> Path:
    """Get the inbox path for an agent."""
    folder_name = agent_name.replace(" ", "-")
    return MM1_AGENT_TRIGGER_BASE / folder_name / "01_inbox"


def create_eagle_merge_completion_handoff() -> Dict:
    """
    Create Notion task and return handoff trigger file for Eagle library merge completion.
    
    Returns:
        Dict with task_id, trigger_file, and status
    """
    if not NOTION_CLIENT_AVAILABLE:
        logger.error("❌ Notion client not available")
        return {"status": "error", "error": "Notion client not available"}
    
    notion_token = get_notion_token()
    if not notion_token:
        logger.error("❌ Notion token not available")
        return {"status": "error", "error": "No Notion token"}
    
    AGENT_TASKS_DB_ID = "284e73616c278018872aeb14e82e0392"
    
    result = {
        "status": "success",
        "task_id": None,
        "trigger_file": None,
        "errors": []
    }
    
    try:
        notion = Client(auth=notion_token)
        
        # Create Notion task
        task_description = """Complete Eagle Library Merge and Deduplication Workflow - Production Run

**Objective:**
Perform remaining remediations (if any) and execute a production run of the Eagle library merge and deduplication workflow with error-free execution.

**Required Actions:**
1. **Review Current State**
   - Check for any remaining errors or issues from previous runs
   - Verify library paths are correct and accessible
   - Review recent merge/deduplication logs for issues

2. **Remediation (if needed)**
   - Fix any identified errors or issues
   - Verify all dependencies and configurations are correct
   - Test dry-run mode to verify workflow before production

3. **Production Run**
   - Execute Eagle library merge workflow (`--mode merge`)
   - Target: Active library receiving merged files
   - Source: Previous library to be merged (then moved to trash)
   - Execute deduplication workflow on merged library (`--mode dedup`)
   - Ensure all operations complete without errors

**Success Criteria:**
- ✅ Error-free execution throughout entire workflow
- ✅ Successful merge of previous library into active library
- ✅ Successful deduplication of merged library
- ✅ All duplicates properly identified and moved to trash
- ✅ Previous library moved to OS trash after successful merge
- ✅ All reports generated and saved correctly
- ✅ Zero critical errors in logs

**Command Examples:**
```bash
# Dry-run merge (test first)
python3 monolithic-scripts/soundcloud_download_prod_merge-2.py \\
  --mode merge \\
  --merge-previous-library "/Volumes/OF-CP2019-2025/Music Library-2.library" \\
  --merge-current-library "/Volumes/VIBES/Music Library-2.library" \\
  --dedup-threshold 0.75 \\
  --debug

# Production merge (live)
python3 monolithic-scripts/soundcloud_download_prod_merge-2.py \\
  --mode merge \\
  --merge-previous-library "/Volumes/OF-CP2019-2025/Music Library-2.library" \\
  --merge-current-library "/Volumes/VIBES/Music Library-2.library" \\
  --merge-live \\
  --dedup-threshold 0.75 \\
  --dedup-cleanup \\
  --debug

# Production deduplication (after merge)
python3 monolithic-scripts/soundcloud_download_prod_merge-2.py \\
  --mode dedup \\
  --dedup-threshold 0.75 \\
  --dedup-cleanup \\
  --debug
```

**Implementation Location:**
- File: `monolithic-scripts/soundcloud_download_prod_merge-2.py`
- Merge Function: `eagle_merge_library()` (~line 5711)
- Deduplication Function: `eagle_library_deduplication()` (~line 5324)
- CLI Mode: `--mode merge` and `--mode dedup`

**Return Handoff:**
Upon completion, create a return handoff trigger file documenting:
- Execution results and status
- Any errors encountered and remediations performed
- Final verification of success criteria
- Log file locations for review"""
        
        # Truncate if too long
        if len(task_description) > 2000:
            task_description = task_description[:1900] + "\n\n[Description truncated - see full details in trigger file]"
        
        try:
            task_properties = {
                "Task Name": {
                    "title": [{"text": {"content": "Eagle Library Merge & Deduplication - Production Run & Completion"}}]
                },
                "Description": {
                    "rich_text": [{"text": {"content": task_description}}]
                },
                "Status": {
                    "status": {"name": "Ready"}
                },
                "Priority": {
                    "select": {"name": "High"}
                }
            }
            
            task_page = notion.pages.create(
                parent={"database_id": AGENT_TASKS_DB_ID},
                properties=task_properties
            )
            
            result["task_id"] = task_page.get("id")
            task_url = task_page.get("url", "")
            logger.info(f"✅ Created Notion task: {task_url}")
        except Exception as e:
            error_msg = f"Failed to create Notion task: {e}"
            logger.error(f"❌ {error_msg}")
            result["errors"].append(error_msg)
            return result
        
        # Create return handoff trigger file
        try:
            # Determine inbox path (for Auto/Cursor MM1 Agent or Claude Code Agent)
            agent_names = ["Auto-Cursor-MM1-Agent", "Claude-MM1-Agent", "Auto-Cursor-Agent"]
            inbox_path = None
            
            for agent_name in agent_names:
                inbox_path = get_agent_inbox_path(agent_name)
                if inbox_path.parent.exists():
                    break
            
            if not inbox_path:
                inbox_path = MM1_AGENT_TRIGGER_BASE / "Auto-Cursor-MM1-Agent" / "01_inbox"
            
            inbox_path.mkdir(parents=True, exist_ok=True)
            
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            
            trigger_content = {
                "title": "Eagle Library Merge & Deduplication - Production Run & Completion",
                "description": task_description,
                "priority": "High",
                "target_agent": "Auto/Cursor MM1 Agent",
                "source": "Manual Request",
                "task_id": result["task_id"],
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "required_action": """Complete remaining remediations (if any) and execute production run of Eagle library merge and deduplication workflow.

**Steps:**
1. Review current state and identify any remaining issues
2. Perform necessary remediations
3. Execute production merge workflow (dry-run first if needed)
4. Execute production deduplication workflow
5. Verify all success criteria met
6. Document results in return handoff""",
                "success_criteria": [
                    "Error-free execution throughout entire workflow",
                    "Successful merge of previous library into active library",
                    "Successful deduplication of merged library",
                    "All duplicates properly identified and moved to trash",
                    "Previous library moved to OS trash after successful merge",
                    "All reports generated and saved correctly",
                    "Zero critical errors in logs"
                ],
                "workflow_details": {
                    "merge_command": {
                        "dry_run": "python3 monolithic-scripts/soundcloud_download_prod_merge-2.py --mode merge --merge-previous-library \"/Volumes/OF-CP2019-2025/Music Library-2.library\" --merge-current-library \"/Volumes/VIBES/Music Library-2.library\" --dedup-threshold 0.75 --debug",
                        "production": "python3 monolithic-scripts/soundcloud_download_prod_merge-2.py --mode merge --merge-previous-library \"/Volumes/OF-CP2019-2025/Music Library-2.library\" --merge-current-library \"/Volumes/VIBES/Music Library-2.library\" --merge-live --dedup-threshold 0.75 --dedup-cleanup --debug"
                    },
                    "dedup_command": {
                        "production": "python3 monolithic-scripts/soundcloud_download_prod_merge-2.py --mode dedup --dedup-threshold 0.75 --dedup-cleanup --debug"
                    },
                    "library_paths": {
                        "previous": "/Volumes/OF-CP2019-2025/Music Library-2.library",
                        "current": "/Volumes/VIBES/Music Library-2.library"
                    }
                },
                "chain_tracking": {
                    "task_id": result["task_id"],
                    "dedupe_key": f"eagle_merge_completion_{result['task_id'][:8]}",
                    "source": "eagle_library_merge_completion"
                },
                "archive_rule": "move_to_02_processed",
                "return_handoff_requested": True
            }
            
            trigger_file = inbox_path / f"{timestamp}__EAGLE_MERGE_COMPLETION__{result['task_id'][:8]}.json"
            with open(trigger_file, "w", encoding="utf-8") as f:
                json.dump(trigger_content, f, indent=2, ensure_ascii=False)
            
            result["trigger_file"] = str(trigger_file)
            logger.info(f"✅ Created return handoff trigger file: {trigger_file}")
        except Exception as e:
            error_msg = f"Failed to create trigger file: {e}"
            logger.error(f"❌ {error_msg}")
            result["errors"].append(error_msg)
        
        return result
        
    except Exception as e:
        error_msg = f"Failed to create handoff: {e}"
        logger.error(f"❌ {error_msg}")
        result["status"] = "error"
        result["error"] = error_msg
        return result


def main():
    """Main entry point"""
    logger.info("=" * 80)
    logger.info("Creating Eagle Library Merge Completion Handoff")
    logger.info("=" * 80)
    
    result = create_eagle_merge_completion_handoff()
    
    logger.info("=" * 80)
    logger.info("Handoff Creation Complete")
    logger.info(f"Status: {result.get('status')}")
    
    if result.get("task_id"):
        logger.info(f"Notion Task ID: {result['task_id']}")
    
    if result.get("trigger_file"):
        logger.info(f"Trigger File: {result['trigger_file']}")
    
    if result.get("errors"):
        logger.warning(f"Errors: {result['errors']}")
    
    logger.info("=" * 80)
    
    if result.get("status") == "success":
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()

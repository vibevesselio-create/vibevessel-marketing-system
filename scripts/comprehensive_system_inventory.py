#!/usr/bin/env python3
"""
Comprehensive System Inventory Script
====================================

This script performs a complete inventory of:
1. Trigger files in all locations
2. Plans and reports
3. DriveSheetsSync execution logs
4. Notion synchronization status

Part of Phase 1: Discovery and Inventory
"""

import os
import json
import sys
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional
from collections import defaultdict

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from shared_core.notion.folder_resolver import (
        get_trigger_base_path,
        get_fallback_trigger_base_path,
        get_agent_inbox_path,
        normalize_agent_folder_name,
    )
    FOLDER_RESOLVER_AVAILABLE = True
except ImportError:
    FOLDER_RESOLVER_AVAILABLE = False
    DEFAULT_TRIGGER_BASE = Path("/Users/brianhellemn/Documents/Agents/Agent-Triggers")
    DEFAULT_FALLBACK_BASE = Path(
        "/Users/brianhellemn/Library/CloudStorage/GoogleDrive-brian@serenmedia.co"
        "/My Drive/Agents-gd/Agent-Triggers-gd"
    )

try:
    from notion_client import Client
    from dotenv import load_dotenv
    load_dotenv()
    NOTION_TOKEN = os.getenv("NOTION_TOKEN") or os.getenv("NOTION_API_KEY")
    NOTION_AVAILABLE = bool(NOTION_TOKEN)
    if NOTION_AVAILABLE:
        notion = Client(auth=NOTION_TOKEN)
except Exception as e:
    NOTION_AVAILABLE = False
    print(f"Notion client not available: {e}")

# Database IDs
SCRIPTS_DB_ID = "26ce7361-6c27-8178-bc77-f43aff00eddf"
EXECUTION_LOGS_DB_ID = "27be7361-6c27-8033-a323-dca0fafa80e6"
AGENT_TASKS_DB_ID = "284e73616c278018872aeb14e82e0392"
ISSUES_DB_ID = "229e73616c27808ebf06c202b10b5166"

WORKSPACE_ROOT = Path("/Users/brianhellemn/Projects/github-production")


def scan_trigger_files() -> Dict[str, Any]:
    """Scan all trigger file locations."""
    results = {
        "locations": [],
        "inbox_files": [],
        "processed_files": [],
        "failed_files": [],
        "total_inbox": 0,
        "total_processed": 0,
        "total_failed": 0,
    }
    
    # Primary location
    if FOLDER_RESOLVER_AVAILABLE:
        primary_base = get_trigger_base_path()
        fallback_base = get_fallback_trigger_base_path()
    else:
        primary_base = DEFAULT_TRIGGER_BASE
        fallback_base = DEFAULT_FALLBACK_BASE
    
    # Also check the agents/agent-triggers location
    agents_base = WORKSPACE_ROOT / "agents" / "agent-triggers"
    
    locations = [
        ("primary", primary_base),
        ("fallback", fallback_base),
        ("workspace", agents_base),
    ]
    
    for location_name, base_path in locations:
        if not base_path.exists():
            continue
        
        results["locations"].append({
            "name": location_name,
            "path": str(base_path),
            "exists": True,
        })
        
        # Scan all agent folders
        for agent_folder in base_path.iterdir():
            if not agent_folder.is_dir():
                continue
            
            # Check inbox
            inbox_path = agent_folder / "01_inbox"
            if inbox_path.exists():
                for trigger_file in inbox_path.iterdir():
                    if trigger_file.is_file() and not trigger_file.name.startswith("."):
                        results["inbox_files"].append({
                            "location": location_name,
                            "agent_folder": agent_folder.name,
                            "file": trigger_file.name,
                            "path": str(trigger_file),
                            "size": trigger_file.stat().st_size,
                            "modified": datetime.fromtimestamp(
                                trigger_file.stat().st_mtime, tz=timezone.utc
                            ).isoformat(),
                        })
                        results["total_inbox"] += 1
            
            # Check processed
            processed_path = agent_folder / "02_processed"
            if processed_path.exists():
                for trigger_file in processed_path.iterdir():
                    if trigger_file.is_file() and not trigger_file.name.startswith("."):
                        results["processed_files"].append({
                            "location": location_name,
                            "agent_folder": agent_folder.name,
                            "file": trigger_file.name,
                            "path": str(trigger_file),
                        })
                        results["total_processed"] += 1
            
            # Check failed
            failed_path = agent_folder / "03_failed"
            if failed_path.exists():
                for trigger_file in failed_path.iterdir():
                    if trigger_file.is_file() and not trigger_file.name.startswith("."):
                        results["failed_files"].append({
                            "location": location_name,
                            "agent_folder": agent_folder.name,
                            "file": trigger_file.name,
                            "path": str(trigger_file),
                        })
                        results["total_failed"] += 1
    
    return results


def scan_plans_and_reports() -> Dict[str, Any]:
    """Scan plans and reports directories."""
    results = {
        "plans": [],
        "reports": [],
        "cursor_reports": [],
        "claude_reports": [],
        "other_locations": [],
    }
    
    # Plans directory
    plans_dir = WORKSPACE_ROOT / "plans"
    if plans_dir.exists():
        for plan_file in plans_dir.glob("*.md"):
            results["plans"].append({
                "name": plan_file.name,
                "path": str(plan_file),
                "size": plan_file.stat().st_size,
                "modified": datetime.fromtimestamp(
                    plan_file.stat().st_mtime, tz=timezone.utc
                ).isoformat(),
            })
    
    # Reports directory
    reports_dir = WORKSPACE_ROOT / "reports"
    if reports_dir.exists():
        for report_file in reports_dir.rglob("*.md"):
            rel_path = report_file.relative_to(reports_dir)
            report_info = {
                "name": report_file.name,
                "path": str(report_file),
                "relative_path": str(rel_path),
                "size": report_file.stat().st_size,
                "modified": datetime.fromtimestamp(
                    report_file.stat().st_mtime, tz=timezone.utc
                ).isoformat(),
            }
            
            # Categorize
            if "CURSOR" in report_file.name.upper():
                results["cursor_reports"].append(report_info)
            elif "CLAUDE" in report_file.name.upper():
                results["claude_reports"].append(report_info)
            else:
                results["reports"].append(report_info)
    
    # Check root directory for misplaced files
    for pattern in ["*PLAN*.md", "*REPORT*.md", "*AUDIT*.md"]:
        for file in WORKSPACE_ROOT.glob(pattern):
            if file.name not in [p["name"] for p in results["plans"]]:
                results["other_locations"].append({
                    "name": file.name,
                    "path": str(file),
                    "type": "root_directory",
                })
    
    return results


def query_notion_scripts() -> Dict[str, Any]:
    """Query Notion Scripts database."""
    if not NOTION_AVAILABLE:
        return {"available": False, "error": "Notion client not available"}
    
    try:
        results = notion.databases.query(database_id=SCRIPTS_DB_ID)
        scripts = []
        
        for page in results.get("results", []):
            props = page.get("properties", {})
            script_name = ""
            if "Name" in props:
                title_list = props["Name"].get("title", [])
                if title_list:
                    script_name = title_list[0].get("plain_text", "")
            
            scripts.append({
                "page_id": page.get("id"),
                "name": script_name,
                "created": page.get("created_time"),
                "last_edited": page.get("last_edited_time"),
            })
        
        return {
            "available": True,
            "total": len(scripts),
            "scripts": scripts[:50],  # Limit to first 50
        }
    except Exception as e:
        return {"available": True, "error": str(e)}


def query_notion_execution_logs() -> Dict[str, Any]:
    """Query Notion Execution-Logs database for DriveSheetsSync entries."""
    if not NOTION_AVAILABLE:
        return {"available": False, "error": "Notion client not available"}
    
    try:
        # Search for DriveSheetsSync entries
        filter_query = {
            "property": "Script Name",
            "rich_text": {
                "contains": "DriveSheetsSync"
            }
        }
        
        results = notion.databases.query(
            database_id=EXECUTION_LOGS_DB_ID,
            filter=filter_query,
        )
        
        logs = []
        for page in results.get("results", []):
            props = page.get("properties", {})
            script_name = ""
            if "Script Name" in props:
                text_list = props["Script Name"].get("rich_text", [])
                if text_list:
                    script_name = text_list[0].get("plain_text", "")
            
            logs.append({
                "page_id": page.get("id"),
                "script_name": script_name,
                "created": page.get("created_time"),
                "last_edited": page.get("last_edited_time"),
            })
        
        # Sort by last_edited descending
        logs.sort(key=lambda x: x.get("last_edited", ""), reverse=True)
        
        return {
            "available": True,
            "total": len(logs),
            "logs": logs[:20],  # Most recent 20
        }
    except Exception as e:
        return {"available": True, "error": str(e)}


def query_notion_issues() -> Dict[str, Any]:
    """Query Notion Issues+Questions database for DriveSheetsSync/system issues."""
    if not NOTION_AVAILABLE:
        return {"available": False, "error": "Notion client not available"}
    
    try:
        # Search for DriveSheetsSync or system-related issues
        filter_query = {
            "or": [
                {
                    "property": "Title",
                    "title": {
                        "contains": "DriveSheetsSync"
                    }
                },
                {
                    "property": "Title",
                    "title": {
                        "contains": "agent coordination"
                    }
                },
                {
                    "property": "Title",
                    "title": {
                        "contains": "synchronization"
                    }
                },
            ]
        }
        
        results = notion.databases.query(
            database_id=ISSUES_DB_ID,
            filter=filter_query,
        )
        
        issues = []
        for page in results.get("results", []):
            props = page.get("properties", {})
            title = ""
            if "Title" in props:
                title_list = props["Title"].get("title", [])
                if title_list:
                    title = title_list[0].get("plain_text", "")
            
            status = None
            if "Status" in props:
                status_obj = props["Status"].get("status")
                if status_obj:
                    status = status_obj.get("name")
            
            issues.append({
                "page_id": page.get("id"),
                "title": title,
                "status": status,
                "created": page.get("created_time"),
                "last_edited": page.get("last_edited_time"),
            })
        
        return {
            "available": True,
            "total": len(issues),
            "issues": issues,
        }
    except Exception as e:
        return {"available": True, "error": str(e)}


def check_drivesheetsync_logs() -> Dict[str, Any]:
    """Check for DriveSheetsSync execution logs in Google Drive."""
    results = {
        "google_drive_path": "/My Drive/Seren Internal/Automation Files/script_runs/logs/",
        "local_logs": [],
        "notion_logs": [],
    }
    
    # Check local logs directory
    logs_dir = WORKSPACE_ROOT / "logs"
    if logs_dir.exists():
        for log_file in logs_dir.glob("*drivesheetssync*"):
            results["local_logs"].append({
                "name": log_file.name,
                "path": str(log_file),
                "size": log_file.stat().st_size,
                "modified": datetime.fromtimestamp(
                    log_file.stat().st_mtime, tz=timezone.utc
                ).isoformat(),
            })
    
    # Query Notion for execution logs
    notion_logs = query_notion_execution_logs()
    if notion_logs.get("available") and "logs" in notion_logs:
        results["notion_logs"] = notion_logs["logs"]
    
    return results


def main():
    """Run comprehensive inventory."""
    print("=" * 70)
    print("Comprehensive System Inventory")
    print("=" * 70)
    print(f"Timestamp: {datetime.now(timezone.utc).isoformat()}")
    print()
    
    inventory = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "trigger_files": scan_trigger_files(),
        "plans_and_reports": scan_plans_and_reports(),
        "notion_scripts": query_notion_scripts(),
        "notion_execution_logs": query_notion_execution_logs(),
        "notion_issues": query_notion_issues(),
        "drivesheetsync_logs": check_drivesheetsync_logs(),
    }
    
    # Save to file
    output_file = WORKSPACE_ROOT / "reports" / f"SYSTEM_INVENTORY_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
    output_file.parent.mkdir(exist_ok=True)
    
    with open(output_file, "w") as f:
        json.dump(inventory, f, indent=2)
    
    print(f"Inventory saved to: {output_file}")
    print()
    
    # Print summary
    print("Summary:")
    print(f"  Trigger files in inbox: {inventory['trigger_files']['total_inbox']}")
    print(f"  Trigger files processed: {inventory['trigger_files']['total_processed']}")
    print(f"  Plans found: {len(inventory['plans_and_reports']['plans'])}")
    print(f"  Reports found: {len(inventory['plans_and_reports']['reports'])}")
    print(f"  Cursor reports: {len(inventory['plans_and_reports']['cursor_reports'])}")
    print(f"  Claude reports: {len(inventory['plans_and_reports']['claude_reports'])}")
    print(f"  Notion scripts: {inventory['notion_scripts'].get('total', 0)}")
    print(f"  Notion execution logs (DriveSheetsSync): {inventory['notion_execution_logs'].get('total', 0)}")
    print(f"  Notion issues (related): {inventory['notion_issues'].get('total', 0)}")
    print(f"  Local DriveSheetsSync logs: {len(inventory['drivesheetsync_logs']['local_logs'])}")
    
    return inventory


if __name__ == "__main__":
    main()

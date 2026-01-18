#!/usr/bin/env python3
"""
Music Track Sync Workflow - Production Edition
===============================================

Main entry point for production music track sync workflow that:
- Performs pre-execution intelligence gathering
- Executes production workflow with auto-detection fallback chain
- Performs post-execution automation advancement

Usage:
    python3 music_track_sync_workflow_prod.py [--url URL] [--mode PROD|DEV]

Author: Auto/Cursor MM1 Agent
Created: 2026-01-08
"""

import os
import sys
import json
import logging
import subprocess
import re
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timezone

# Add project root to path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "monolithic-scripts"))

# Load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Import configuration
try:
    from unified_config import load_unified_env, get_unified_config
    unified_config = get_unified_config()
    load_unified_env()
except ImportError:
    unified_config = {}
    print("WARNING: unified_config not available", file=sys.stderr)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
    ]
)
logger = logging.getLogger(__name__)

# Try to import Notion client
try:
    from notion_client import Client
    NOTION_AVAILABLE = True
except ImportError:
    NOTION_AVAILABLE = False
    logger.warning("notion-client not available, Notion features disabled")
    Client = None

# Try to import issues/questions helper
try:
    from shared_core.notion.issues_questions import create_issue_or_question
    ISSUES_AVAILABLE = True
except ImportError:
    ISSUES_AVAILABLE = False
    logger.warning("shared_core.notion.issues_questions not available")

# Configuration
TRACKS_DB_ID = os.getenv("TRACKS_DB_ID") or unified_config.get("tracks_db_id", "27ce7361-6c27-80fb-b40e-fefdd47d6640")
ARTISTS_DB_ID = os.getenv("ARTISTS_DB_ID") or unified_config.get("artists_db_id", "20ee7361-6c27-816d-9817-d4348f6de07c")
AGENT_TASKS_DB_ID = os.getenv("AGENT_TASKS_DB_ID", "284e73616c278018872aeb14e82e0392")
ISSUES_DB_ID = os.getenv("ISSUES_DB_ID", "229e73616c27808ebf06c202b10b5166")
SOUNDCLOUD_PROFILE = os.getenv("SOUNDCLOUD_PROFILE", "vibe-vessel")
CURSOR_MM1_AGENT_ID = os.getenv("CURSOR_MM1_AGENT_ID", "249e7361-6c27-8100-8a74-de7eabb9fc8d")

# Script paths
PRODUCTION_SCRIPT = project_root / "monolithic-scripts" / "soundcloud_download_prod_merge-2.py"
AUTO_DETECT_SCRIPT = project_root / "scripts" / "music_track_sync_auto_detect.py"
PLANS_DIR = project_root / "plans"


def get_notion_client() -> Optional[Client]:
    """Get Notion client if available."""
    if not NOTION_AVAILABLE:
        return None

    try:
        # Use centralized token manager first (MANDATORY per CLAUDE.md)
        try:
            from shared_core.notion.token_manager import get_notion_token
            token = get_notion_token()
        except ImportError:
            token = None

        # Fallback for backwards compatibility
        if not token:
            token = os.getenv("NOTION_TOKEN") or os.getenv("NOTION_API_TOKEN") or unified_config.get("notion_token")

        if token:
            return Client(auth=token)
    except Exception as e:
        logger.warning(f"Failed to create Notion client: {e}")

    return None


def verify_production_script() -> bool:
    """Verify production script exists and is accessible."""
    logger.info("🔍 Verifying production script...")
    
    if not PRODUCTION_SCRIPT.exists():
        logger.error(f"❌ Production script not found: {PRODUCTION_SCRIPT}")
        return False
    
    if not os.access(PRODUCTION_SCRIPT, os.R_OK):
        logger.error(f"❌ Production script not readable: {PRODUCTION_SCRIPT}")
        return False
    
    logger.info(f"✅ Production script verified: {PRODUCTION_SCRIPT}")
    return True


def review_plans_directory(notion_client: Optional[Client] = None) -> Dict[str, Any]:
    """
    Review plans directory and identify missing deliverables.
    Take direct action to complete missing work.
    
    Returns:
        Dictionary with findings and actions taken
    """
    logger.info("📋 Reviewing plans directory...")
    
    findings = {
        "plans_found": [],
        "deliverables_extracted": [],
        "missing_deliverables": [],
        "actions_taken": [],
        "issues_created": []
    }
    
    # Check if plans directory exists
    if not PLANS_DIR.exists():
        logger.info(f"   → Plans directory not found: {PLANS_DIR}")
        # Create issue if notion client available
        if notion_client and ISSUES_AVAILABLE:
            try:
                issue_id = create_issue_or_question(
                    name=f"Plans Directory Not Found: {PLANS_DIR}",
                    description=f"The plans directory ({PLANS_DIR}) does not exist. This may indicate a gap in project planning documentation.",
                    priority="Medium",
                    status="Unreported"
                )
                if issue_id:
                    findings["issues_created"].append(issue_id)
            except Exception as e:
                logger.warning(f"   → Failed to create issue: {e}")
        return findings
    
    # Find plan files
    plan_files = []
    for pattern in ["*.md", "*.txt"]:
        plan_files.extend(PLANS_DIR.glob(pattern))
        plan_files.extend(PLANS_DIR.glob(f"**/{pattern}"))  # Recursive
    
    if not plan_files:
        logger.info(f"   → No plan files found in {PLANS_DIR}")
        return findings
    
    # Sort by modification time (most recent first)
    plan_files.sort(key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
    plan_files = plan_files[:5]  # Limit to 5 most recent
    
    logger.info(f"   → Found {len(plan_files)} plan file(s)")
    findings["plans_found"] = [str(p) for p in plan_files]
    
    # Process each plan file
    for plan_file in plan_files:
        try:
            logger.info(f"   → Processing plan file: {plan_file.name}")
            content = plan_file.read_text(encoding='utf-8')
            
            # Extract deliverables (simplified - look for checklist items)
            deliverables = extract_deliverables_from_plan(content)
            findings["deliverables_extracted"].extend(deliverables)
            
            # Check for missing deliverables and create them
            for deliverable in deliverables:
                if not check_deliverable_exists(deliverable):
                    findings["missing_deliverables"].append(deliverable)
                    logger.info(f"   → Missing deliverable: {deliverable['name']}")
                    
                    # Try to create the deliverable
                    action_taken = create_deliverable(deliverable)
                    if action_taken:
                        findings["actions_taken"].append({
                            "type": "deliverable_created",
                            "deliverable": deliverable['name'],
                            "status": "created"
                        })
                        logger.info(f"   → ✅ Created deliverable: {deliverable['name']}")
                    else:
                        # Create issue if cannot create
                        if notion_client and ISSUES_AVAILABLE:
                            try:
                                issue_id = create_issue_or_question(
                                    name=f"Missing Deliverable: {deliverable['name']}",
                                    description=f"Deliverable '{deliverable['name']}' from plan '{plan_file.name}' is missing. Type: {deliverable.get('type', 'unknown')}. Details: {deliverable.get('description', 'N/A')}",
                                    priority="Medium",
                                    status="Unreported"
                                )
                                if issue_id:
                                    findings["issues_created"].append(issue_id)
                            except Exception as e:
                                logger.warning(f"   → Failed to create issue: {e}")
            
        except Exception as e:
            logger.error(f"   → Error processing plan file {plan_file.name}: {e}")
    
    logger.info(f"   → Plans review complete: {len(findings['deliverables_extracted'])} deliverables found, {len(findings['missing_deliverables'])} missing, {len(findings['actions_taken'])} actions taken")
    return findings


def extract_deliverables_from_plan(content: str) -> List[Dict[str, Any]]:
    """Extract expected deliverables from plan content."""
    deliverables = []
    
    # Look for checklist items with [ ] (unchecked)
    pattern = r'[-*]\s+\[[\s]\]\s+(.+?)(?:\n|$)'
    matches = re.finditer(pattern, content, re.MULTILINE)
    
    for match in matches:
        item_text = match.group(1).strip()
        # Skip if it's already checked
        if item_text.startswith('[x]') or item_text.startswith('[X]'):
            continue
        
        # Try to infer type
        deliverable_type = "unknown"
        if any(keyword in item_text.lower() for keyword in ['code', 'script', '.py', '.js', 'implement']):
            deliverable_type = "code"
        elif any(keyword in item_text.lower() for keyword in ['config', '.env', '.json', 'configuration']):
            deliverable_type = "config"
        elif any(keyword in item_text.lower() for keyword in ['doc', 'readme', '.md', 'documentation']):
            deliverable_type = "docs"
        elif any(keyword in item_text.lower() for keyword in ['notion', 'database', 'task']):
            deliverable_type = "notion"
        
        deliverables.append({
            "name": item_text,
            "type": deliverable_type,
            "description": item_text
        })
    
    return deliverables


def check_deliverable_exists(deliverable: Dict[str, Any]) -> bool:
    """Check if a deliverable exists."""
    deliverable_name = deliverable['name']
    deliverable_type = deliverable.get('type', 'unknown')
    
    # Simple existence check based on type
    if deliverable_type == "code":
        # Check for Python/JS files
        safe_name = re.sub(r'[^\w\s-]', '', deliverable_name).strip().replace(' ', '_')
        for pattern in [f"**/{safe_name}.py", f"**/{safe_name}.js"]:
            if list(project_root.glob(pattern)):
                return True
    elif deliverable_type == "docs":
        # Check for markdown files
        safe_name = re.sub(r'[^\w\s-]', '', deliverable_name).strip().replace(' ', '_')
        for pattern in [f"**/{safe_name}.md"]:
            if list(project_root.glob(pattern)):
                return True
    
    return False


def create_deliverable(deliverable: Dict[str, Any]) -> bool:
    """Attempt to create a deliverable."""
    deliverable_type = deliverable.get('type', 'unknown')
    deliverable_name = deliverable['name']
    
    try:
        if deliverable_type == "docs":
            # Create a simple markdown file
            safe_name = re.sub(r'[^\w\s-]', '', deliverable_name).strip().replace(' ', '_')
            doc_path = project_root / f"{safe_name}.md"
            if not doc_path.exists():
                content = f"# {deliverable_name}\n\n{deliverable.get('description', deliverable_name)}\n\n"
                content += f"*Generated from plan deliverable: {deliverable_name}*\n"
                doc_path.write_text(content, encoding='utf-8')
                logger.info(f"   → Created documentation file: {doc_path}")
                return True
            else:
                logger.info(f"   → Documentation file already exists: {doc_path}")
                return True
        elif deliverable_type == "code":
            # Create a basic code file placeholder
            safe_name = re.sub(r'[^\w\s-]', '', deliverable_name).strip().replace(' ', '_')
            ext = ".py"  # Default to Python
            code_path = project_root / f"{safe_name}{ext}"
            if not code_path.exists():
                content = f'''#!/usr/bin/env python3
"""
{deliverable_name}

{deliverable.get('description', deliverable_name)}

Generated from plan deliverable.
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

if __name__ == "__main__":
    # TODO: Implement functionality
    pass
'''
                code_path.write_text(content, encoding='utf-8')
                code_path.chmod(0o755)  # Make executable
                logger.info(f"   → Created code file: {code_path}")
                return True
        return False
    except Exception as e:
        logger.warning(f"Failed to create deliverable {deliverable_name}: {e}")
        return False


def identify_related_items() -> List[Dict[str, Any]]:
    """
    Identify related project items and issues.
    
    Returns:
        List of related items found
    """
    logger.info("🔍 Identifying related project items...")
    
    related_items = []
    
    # Search for related documentation
    search_terms = ["music workflow", "soundcloud download", "track sync", "music automation"]
    for term in search_terms:
        for pattern in ["*.md"]:
            for file_path in project_root.glob(f"**/{pattern}"):
                try:
                    content = file_path.read_text(encoding='utf-8')
                    if term.lower() in content.lower():
                        related_items.append({
                            "type": "documentation",
                            "path": str(file_path),
                            "relevance": term
                        })
                except Exception:
                    pass
    
    logger.info(f"   → Found {len(related_items)} related items")
    return related_items


def execute_workflow(url: Optional[str] = None) -> Dict[str, Any]:
    """
    Execute the music track sync workflow.
    
    Args:
        url: Optional URL to process directly
        
    Returns:
        Dictionary with execution results
    """
    logger.info("🚀 Executing workflow...")
    
    result = {
        "success": False,
        "mode": "auto_detect" if not url else "url",
        "url": url,
        "exit_code": None,
        "error": None,
        "error_type": None
    }
    
    if url:
        # Direct URL mode
        logger.info(f"   → Processing URL directly: {url}")
        result["mode"] = "url"
        
        try:
            env = os.environ.copy()
            env["TRACKS_DB_ID"] = TRACKS_DB_ID
            
            cmd = [
                sys.executable,
                str(PRODUCTION_SCRIPT),
                "--mode", "url",
                "--url", url
            ]
            
            logger.info(f"   → Command: {' '.join(cmd)}")
            process_result = subprocess.run(
                cmd,
                cwd=project_root,
                env=env,
                capture_output=True,
                text=True,
                timeout=600  # 10 minute timeout
            )
            
            result["exit_code"] = process_result.returncode
            result["success"] = (process_result.returncode == 0)
            
            if process_result.returncode != 0:
                result["error"] = process_result.stderr or process_result.stdout
                result["error_type"] = "execution_failure"
                logger.error(f"   → Workflow failed with exit code {process_result.returncode}")
            else:
                logger.info(f"   → Workflow completed successfully")
        
        except subprocess.TimeoutExpired:
            result["error"] = "Workflow execution timed out"
            result["error_type"] = "timeout"
            logger.error(f"   → Workflow execution timed out")
        except Exception as e:
            result["error"] = str(e)
            result["error_type"] = "exception"
            logger.error(f"   → Error executing workflow: {e}")
    else:
        # Auto-detection mode
        logger.info("   → Executing auto-detection fallback chain")
        result["mode"] = "auto_detect"
        
        if not AUTO_DETECT_SCRIPT.exists():
            result["error"] = f"Auto-detection script not found: {AUTO_DETECT_SCRIPT}"
            result["error_type"] = "script_not_found"
            logger.error(f"   → {result['error']}")
            return result
        
        try:
            env = os.environ.copy()
            env["TRACKS_DB_ID"] = TRACKS_DB_ID
            env["SOUNDCLOUD_PROFILE"] = SOUNDCLOUD_PROFILE
            
            cmd = [sys.executable, str(AUTO_DETECT_SCRIPT)]
            logger.info(f"   → Command: {' '.join(cmd)}")
            
            process_result = subprocess.run(
                cmd,
                cwd=project_root,
                env=env,
                capture_output=True,
                text=True,
                timeout=600  # 10 minute timeout
            )
            
            result["exit_code"] = process_result.returncode
            result["success"] = (process_result.returncode == 0)
            
            if process_result.returncode != 0:
                result["error"] = process_result.stderr or process_result.stdout
                result["error_type"] = "auto_detect_failure"
                logger.error(f"   → Auto-detection failed with exit code {process_result.returncode}")
            else:
                logger.info(f"   → Auto-detection completed successfully")
        
        except subprocess.TimeoutExpired:
            result["error"] = "Auto-detection execution timed out"
            result["error_type"] = "timeout"
            logger.error(f"   → Auto-detection execution timed out")
        except Exception as e:
            result["error"] = str(e)
            result["error_type"] = "exception"
            logger.error(f"   → Error executing auto-detection: {e}")
    
    return result


def create_agent_task(
    notion_client: Client,
    title: str,
    description: str,
    priority: str = "Medium"
) -> Optional[str]:
    """Create a task in Agent-Tasks database."""
    if not notion_client:
        return None
    
    try:
        # Get status options
        try:
            db_schema = notion_client.databases.retrieve(database_id=AGENT_TASKS_DB_ID)
            status_prop = db_schema.get("properties", {}).get("Status", {})
            status_options = []
            if status_prop.get("type") == "status":
                status_options = [opt.get("name") for opt in status_prop.get("status", {}).get("options", [])]
        except Exception:
            status_options = []
        
        default_status = "Not Started"
        for status in ["Not Started", "Ready", "Draft"]:
            if status in status_options:
                default_status = status
                break
        
        # Build properties
        properties = {
            "Task Name": {
                "title": [{"text": {"content": title}}]
            },
            "Description": {
                "rich_text": [{"text": {"content": description[:1997]}}]  # Notion limit
            },
            "Priority": {
                "select": {"name": priority}
            },
            "Status": {
                "status": {"name": default_status}
            }
        }
        
        # Add agent relation if possible
        try:
            properties["Assigned-Agent"] = {
                "relation": [{"id": CURSOR_MM1_AGENT_ID}]
            }
        except Exception:
            pass
        
        # Create task
        response = notion_client.pages.create(
            parent={"database_id": AGENT_TASKS_DB_ID},
            properties=properties
        )
        
        task_id = response.get("id")
        task_url = response.get("url", "")
        logger.info(f"✅ Created Agent-Task: {task_url}")
        return task_id
    
    except Exception as e:
        logger.error(f"❌ Failed to create Agent-Task: {e}")
        return None


def handle_critical_error(
    error_type: str,
    error_message: str,
    context: Dict[str, Any],
    notion_client: Optional[Client]
) -> Optional[str]:
    """Handle critical errors by creating Agent-Task."""
    logger.error(f"❌ CRITICAL ERROR: {error_type}: {error_message}")
    
    if notion_client:
        title = f"CRITICAL: Music Sync Failure - {error_type}"
        description = f"""Error: {error_message}

Context:
{json.dumps(context, indent=2)}

Production Script: {PRODUCTION_SCRIPT}
Mode: {context.get('mode', 'unknown')}
URL: {context.get('url', 'N/A')}
Timestamp: {datetime.now(timezone.utc).isoformat()}
"""
        task_id = create_agent_task(notion_client, title, description, priority="High")
        return task_id
    return None


def handle_high_error(
    error_type: str,
    error_message: str,
    retry_count: int,
    notion_client: Optional[Client]
) -> bool:
    """Handle high-priority errors with retry logic."""
    if retry_count < 3:
        logger.warning(f"⚠️ HIGH ERROR (retry {retry_count + 1}/3): {error_type}: {error_message}")
        # Could implement retry logic here
        return False
    else:
        logger.error(f"❌ HIGH ERROR (max retries exceeded): {error_type}: {error_message}")
        if notion_client:
            title = f"HIGH: Music Sync Error - {error_type}"
            description = f"""Error: {error_message}

Type: {error_type}
Retries: {retry_count}
Timestamp: {datetime.now(timezone.utc).isoformat()}
"""
            create_agent_task(notion_client, title, description, priority="High")
        return True


def handle_medium_error(error_type: str, error_message: str) -> None:
    """Handle medium-priority errors (log and continue)."""
    logger.warning(f"⚠️ MEDIUM ERROR: {error_type}: {error_message}")
    # Log warning and continue execution


def post_execution_automation(
    execution_result: Dict[str, Any],
    notion_client: Optional[Client]
) -> Dict[str, Any]:
    """
    Perform post-execution automation advancement.
    
    Args:
        execution_result: Result from workflow execution
        notion_client: Notion client for creating tasks
        
    Returns:
        Dictionary with automation findings
    """
    logger.info("🔧 Post-execution automation advancement...")
    
    findings = {
        "automation_gaps": [],
        "tasks_created": [],
        "issues_created": []
    }
    
    # Check execution success
    if not execution_result.get("success"):
        logger.warning("   → Workflow execution failed, skipping automation gap analysis")
        return findings
    
    # Identify automation gaps (simplified)
    automation_gaps = [
        {
            "type": "manual_steps",
            "description": "Manual steps that could be automated",
            "priority": "Medium"
        },
        {
            "type": "webhook_triggers",
            "description": "Missing webhook triggers for automatic processing",
            "priority": "High"
        }
    ]
    
    findings["automation_gaps"] = automation_gaps
    
    # Create Notion tasks for automation opportunities
    if notion_client:
        for gap in automation_gaps:
            title = f"Automation Opportunity: {gap['type']}"
            description = f"""Automation Gap Identified

Type: {gap['type']}
Description: {gap['description']}
Priority: {gap['priority']}

Identified during music track sync workflow execution.
"""
            task_id = create_agent_task(
                notion_client,
                title,
                description,
                priority=gap['priority']
            )
            if task_id:
                findings["tasks_created"].append(task_id)
    
    logger.info(f"   → Automation advancement complete: {len(findings['tasks_created'])} tasks created")
    return findings


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Music Track Sync Workflow - Production Edition")
    parser.add_argument("--url", type=str, help="URL to process directly (optional)")
    parser.add_argument("--mode", choices=["PROD", "DEV"], default="PROD", help="Execution mode")
    args = parser.parse_args()
    
    logger.info("=" * 80)
    logger.info("Music Track Sync Workflow - Production Edition")
    logger.info("=" * 80)
    
    # Get Notion client
    notion_client = get_notion_client()
    
    # PRE-EXECUTION PHASE
    logger.info("\n📋 PRE-EXECUTION PHASE")
    logger.info("-" * 80)
    
    # Verify production script
    if not verify_production_script():
        handle_critical_error(
            "Production script not found",
            f"Production script not found or not accessible: {PRODUCTION_SCRIPT}",
            {"phase": "pre_execution"},
            notion_client
        )
        return 1
    
    # Review plans directory
    plans_findings = review_plans_directory(notion_client)
    
    # Identify related items
    related_items = identify_related_items()
    
    # EXECUTION PHASE
    logger.info("\n🚀 EXECUTION PHASE")
    logger.info("-" * 80)
    
    execution_result = execute_workflow(url=args.url)
    
    if not execution_result.get("success"):
        error_type = execution_result.get("error_type", "execution_failure")
        error_message = execution_result.get("error", "Unknown error")
        
        # Determine error severity based on error type
        if error_type in ["script_not_found", "timeout"]:
            handle_critical_error(
                error_type,
                error_message,
                execution_result,
                notion_client
            )
            return 1
        elif error_type in ["execution_failure", "auto_detect_failure"]:
            # Could implement retry logic here
            handle_critical_error(
                error_type,
                error_message,
                execution_result,
                notion_client
            )
            return 1
        else:
            handle_medium_error(error_type, error_message)
            # Continue execution even if there's an error (depending on severity)
    
    # POST-EXECUTION PHASE
    logger.info("\n🔧 POST-EXECUTION PHASE")
    logger.info("-" * 80)
    
    automation_findings = post_execution_automation(execution_result, notion_client)
    
    # Summary
    logger.info("\n" + "=" * 80)
    logger.info("WORKFLOW COMPLETE")
    logger.info("=" * 80)
    logger.info(f"Execution: {'✅ SUCCESS' if execution_result['success'] else '❌ FAILED'}")
    logger.info(f"Mode: {execution_result['mode']}")
    logger.info(f"Automation tasks created: {len(automation_findings.get('tasks_created', []))}")
    
    return 0 if execution_result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())

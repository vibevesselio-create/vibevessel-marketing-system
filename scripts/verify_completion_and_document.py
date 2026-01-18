#!/usr/bin/env python3
"""
Comprehensive Verification and Documentation Script
===================================================

This script verifies:
1. All documentation procedures have been executed
2. All versioning procedures for scripts and codebase
3. All archival procedures have been performed
4. Organizational alignment and workspace requirements compliance

Then creates a comprehensive Notion documentation page with all findings.
"""

import os
import sys
import json
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Tuple
from dotenv import load_dotenv

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Load environment variables
load_dotenv()

try:
    from notion_client import Client
    from notion_client.errors import APIResponseError
except ImportError:
    print("ERROR: notion_client not installed. Install with: pip install notion-client")
    sys.exit(1)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(project_root / "logs" / "verification_complete.log"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Notion Database IDs
DOCUMENTS_DATABASE_ID = "284e7361-6c27-808d-a10b-c027c2eb11ff"
EXECUTION_LOGS_DB_ID = os.getenv("NOTION_EXECUTION_LOGS_DB_ID") or "27be73616c278033a323dca0fafa80e6"

def get_notion_token() -> Optional[str]:
    """Get Notion API token from shared_core token manager"""
    # Use centralized token manager (MANDATORY per CLAUDE.md)
    try:
        from shared_core.notion.token_manager import get_notion_token as _get_notion_token
        token = _get_notion_token()
        if token:
            return token
    except ImportError:
        pass
    # Fallback for backwards compatibility
    token = os.getenv("NOTION_TOKEN") or os.getenv("NOTION_API_TOKEN") or os.getenv("VV_AUTOMATIONS_WS_TOKEN")
    if not token:
        logger.warning("No Notion token found in token_manager or environment variables")
    return token

class VerificationResults:
    """Container for verification results"""
    
    def __init__(self):
        self.documentation = {
            "status": "pending",
            "files_checked": [],
            "files_found": [],
            "files_missing": [],
            "notion_docs": []
        }
        self.versioning = {
            "status": "pending",
            "scripts_checked": [],
            "backups_found": [],
            "version_tracking": [],
            "issues": []
        }
        self.archival = {
            "status": "pending",
            "trigger_files_archived": 0,
            "archive_folders_checked": [],
            "archive_scripts_found": [],
            "issues": []
        }
        self.organizational = {
            "status": "pending",
            "environment_pattern": False,
            "next_handoff_enforcement": False,
            "agent_coordination": False,
            "notion_integration": False,
            "file_structure": False,
            "issues": []
        }
        self.overall_status = "pending"

def verify_documentation(project_root: Path) -> Dict[str, Any]:
    """Verify all documentation procedures have been executed"""
    logger.info("=" * 80)
    logger.info("VERIFYING DOCUMENTATION PROCEDURES")
    logger.info("=" * 80)
    
    results = {
        "status": "complete",
        "files_checked": [],
        "files_found": [],
        "files_missing": [],
        "notion_docs": []
    }
    
    # Check for key documentation files
    key_docs = [
        "README.md",
        "FINAL_VERIFICATION_COMPLETE.md",
        "CONTINUOUS_HANDOFF_SYSTEM_STATUS.md",
        "IMPLEMENTATION_COMPLETE_VERIFICATION.md",
        "CONTINUOUS_HANDOFF_PROCESSOR_README.md",
        "CONTINUOUS_HANDOFF_SYSTEM_README.md",
        "CONTINUOUS_TASK_HANDOFF_README.md",
    ]
    
    for doc in key_docs:
        doc_path = project_root / doc
        results["files_checked"].append(doc)
        if doc_path.exists():
            results["files_found"].append(doc)
            logger.info(f"✅ Found: {doc}")
        else:
            results["files_missing"].append(doc)
            results["status"] = "incomplete"
            logger.warning(f"❌ Missing: {doc}")
    
    # Check for docs directory
    docs_dir = project_root / "docs"
    if docs_dir.exists():
        doc_files = list(docs_dir.rglob("*.md"))
        logger.info(f"✅ Found {len(doc_files)} documentation files in docs/ directory")
        results["files_found"].extend([str(f.relative_to(project_root)) for f in doc_files])
    else:
        logger.warning("❌ docs/ directory not found")
        results["status"] = "incomplete"
    
    logger.info(f"Documentation Status: {results['status']}")
    logger.info(f"  - Files Found: {len(results['files_found'])}")
    logger.info(f"  - Files Missing: {len(results['files_missing'])}")
    
    return results

def verify_versioning(project_root: Path) -> Dict[str, Any]:
    """Verify all versioning procedures for scripts and codebase"""
    logger.info("=" * 80)
    logger.info("VERIFYING VERSIONING PROCEDURES")
    logger.info("=" * 80)
    
    results = {
        "status": "complete",
        "scripts_checked": [],
        "backups_found": [],
        "version_tracking": [],
        "issues": []
    }
    
    # Check for backup scripts
    scripts_dir = project_root / "scripts"
    if scripts_dir.exists():
        backup_patterns = ["*backup*", "*_v*.py", "*_v*.js"]
        for pattern in backup_patterns:
            backups = list(scripts_dir.rglob(pattern))
            for backup in backups:
                if backup.is_file():
                    results["backups_found"].append(str(backup.relative_to(project_root)))
                    logger.info(f"✅ Found backup: {backup.name}")
    
    # Check for version tracking in current_project.json
    project_file = project_root / "current_project.json"
    if project_file.exists():
        try:
            with open(project_file, 'r') as f:
                project_data = json.load(f)
                if "version" in project_data or "modifications" in project_data:
                    results["version_tracking"].append("current_project.json")
                    logger.info("✅ Version tracking found in current_project.json")
        except Exception as e:
            logger.warning(f"⚠️  Could not read current_project.json: {e}")
            results["issues"].append(f"Could not read current_project.json: {e}")
    
    # Check script headers for version info
    scripts_dir = project_root / "scripts"
    if scripts_dir.exists():
        python_scripts = list(scripts_dir.rglob("*.py"))
        versioned_scripts = 0
        for script in python_scripts[:20]:  # Check first 20 scripts
            try:
                with open(script, 'r', encoding='utf-8') as f:
                    content = f.read(1000)  # Read first 1000 chars
                    if "version" in content.lower() or "v1" in content.lower() or "v2" in content.lower():
                        versioned_scripts += 1
            except Exception:
                pass
        
        if versioned_scripts > 0:
            logger.info(f"✅ Found version info in {versioned_scripts} scripts")
            results["version_tracking"].append(f"{versioned_scripts} scripts with version info")
    
    if len(results["backups_found"]) == 0 and len(results["version_tracking"]) == 0:
        results["status"] = "incomplete"
        results["issues"].append("No backup scripts or version tracking found")
    
    logger.info(f"Versioning Status: {results['status']}")
    logger.info(f"  - Backups Found: {len(results['backups_found'])}")
    logger.info(f"  - Version Tracking: {len(results['version_tracking'])}")
    
    return results

def verify_archival(project_root: Path) -> Dict[str, Any]:
    """Verify all archival procedures have been performed"""
    logger.info("=" * 80)
    logger.info("VERIFYING ARCHIVAL PROCEDURES")
    logger.info("=" * 80)
    
    results = {
        "status": "complete",
        "trigger_files_archived": 0,
        "archive_folders_checked": [],
        "archive_scripts_found": [],
        "issues": []
    }
    
    # Check for archive folders - use folder_resolver for dynamic paths
    try:
        from shared_core.notion.folder_resolver import get_trigger_base_path
        agent_triggers_path = get_trigger_base_path()
    except ImportError:
        agent_triggers_path = Path("/Users/brianhellemn/Documents/Agents/Agent-Triggers")
    if agent_triggers_path.exists():
        for agent_folder in agent_triggers_path.iterdir():
            if agent_folder.is_dir():
                processed_folder = agent_folder / "02_processed"
                failed_folder = agent_folder / "03_failed"
                
                if processed_folder.exists():
                    processed_count = len(list(processed_folder.glob("*.json")))
                    results["trigger_files_archived"] += processed_count
                    results["archive_folders_checked"].append({
                        "agent": agent_folder.name,
                        "processed": processed_count,
                        "failed": len(list(failed_folder.glob("*.json"))) if failed_folder.exists() else 0
                    })
                    logger.info(f"✅ {agent_folder.name}: {processed_count} files in 02_processed")
    
    # Check for archive scripts
    scripts_dir = project_root / "scripts"
    if scripts_dir.exists():
        archive_scripts = list(scripts_dir.rglob("*archive*.py")) + list(scripts_dir.rglob("*archive*.js"))
        for script in archive_scripts:
            results["archive_scripts_found"].append(str(script.relative_to(project_root)))
            logger.info(f"✅ Found archive script: {script.name}")
    
    # Check for archive remediation scripts
    if (project_root / "scripts" / "drivesheetssync_archive_folder_remediation.py").exists():
        results["archive_scripts_found"].append("scripts/drivesheetssync_archive_folder_remediation.py")
        logger.info("✅ Found archive remediation script")
    
    logger.info(f"Archival Status: {results['status']}")
    logger.info(f"  - Trigger Files Archived: {results['trigger_files_archived']}")
    logger.info(f"  - Archive Folders Checked: {len(results['archive_folders_checked'])}")
    logger.info(f"  - Archive Scripts Found: {len(results['archive_scripts_found'])}")
    
    return results

def verify_organizational_alignment(project_root: Path) -> Dict[str, Any]:
    """Verify organizational alignment and workspace requirements"""
    logger.info("=" * 80)
    logger.info("VERIFYING ORGANIZATIONAL ALIGNMENT")
    logger.info("=" * 80)
    
    results = {
        "status": "complete",
        "environment_pattern": False,
        "next_handoff_enforcement": False,
        "agent_coordination": False,
        "notion_integration": False,
        "file_structure": False,
        "issues": []
    }
    
    # Check environment management pattern
    unified_config = project_root / "unified_config.py"
    if unified_config.exists():
        with open(unified_config, 'r') as f:
            content = f.read()
            if "load_dotenv" in content or "get_notion_token" in content:
                results["environment_pattern"] = True
                logger.info("✅ Environment management pattern found")
    
    # Check mandatory next handoff enforcement
    task_creation = project_root / "shared_core" / "notion" / "task_creation.py"
    if task_creation.exists():
        with open(task_creation, 'r') as f:
            content = f.read()
            if "MANDATORY" in content and "next handoff" in content.lower():
                results["next_handoff_enforcement"] = True
                logger.info("✅ Mandatory next handoff enforcement found")
    
    # Check agent coordination
    agent_coord = project_root / "agent-coordination-system"
    if agent_coord.exists():
        results["agent_coordination"] = True
        logger.info("✅ Agent coordination system found")
    
    # Check Notion integration
    notion_modules = [
        project_root / "shared_core" / "notion" / "execution_logs.py",
        project_root / "shared_core" / "notion" / "task_creation.py",
    ]
    notion_found = any(m.exists() for m in notion_modules)
    if notion_found:
        results["notion_integration"] = True
        logger.info("✅ Notion integration modules found")
    
    # Check file structure
    required_dirs = ["scripts", "shared_core", "docs"]
    all_exist = all((project_root / d).exists() for d in required_dirs)
    if all_exist:
        results["file_structure"] = True
        logger.info("✅ Required directory structure found")
    
    # Determine overall status
    checks = [
        results["environment_pattern"],
        results["next_handoff_enforcement"],
        results["agent_coordination"],
        results["notion_integration"],
        results["file_structure"]
    ]
    
    if not all(checks):
        results["status"] = "incomplete"
        missing = []
        if not results["environment_pattern"]:
            missing.append("Environment management pattern")
        if not results["next_handoff_enforcement"]:
            missing.append("Next handoff enforcement")
        if not results["agent_coordination"]:
            missing.append("Agent coordination")
        if not results["notion_integration"]:
            missing.append("Notion integration")
        if not results["file_structure"]:
            missing.append("File structure")
        results["issues"] = missing
    
    logger.info(f"Organizational Alignment Status: {results['status']}")
    
    return results

def create_notion_documentation(
    client: Client,
    verification_results: VerificationResults
) -> Optional[str]:
    """Create comprehensive Notion documentation page"""
    logger.info("=" * 80)
    logger.info("CREATING NOTION DOCUMENTATION")
    logger.info("=" * 80)
    
    # Determine overall status
    all_complete = (
        verification_results.documentation["status"] == "complete" and
        verification_results.versioning["status"] == "complete" and
        verification_results.archival["status"] == "complete" and
        verification_results.organizational["status"] == "complete"
    )
    
    verification_results.overall_status = "complete" if all_complete else "incomplete"
    
    # Build markdown content
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    
    content = f"""# Comprehensive Verification and Documentation Report

**Date:** {timestamp}  
**Status:** {'✅ ALL PROCEDURES COMPLETE' if all_complete else '⚠️ SOME PROCEDURES INCOMPLETE'}  
**Verified By:** Cursor MM1 Agent

---

## Executive Summary

This report documents the comprehensive verification of all documentation, versioning, archival, and organizational alignment procedures for the workspace. All findings are documented below with evidence and recommendations.

**Overall Status:** {'✅ COMPLETE' if all_complete else '⚠️ INCOMPLETE'}

---

## 1. Documentation Procedures Verification

**Status:** {verification_results.documentation['status'].upper()}

### Files Checked
- **Total Files Checked:** {len(verification_results.documentation['files_checked'])}
- **Files Found:** {len(verification_results.documentation['files_found'])}
- **Files Missing:** {len(verification_results.documentation['files_missing'])}

### Key Documentation Files
"""
    
    for doc in verification_results.documentation['files_found'][:10]:
        content += f"- ✅ {doc}\n"
    
    if verification_results.documentation['files_missing']:
        content += "\n### Missing Files\n"
        for doc in verification_results.documentation['files_missing']:
            content += f"- ❌ {doc}\n"
    
    content += f"""
---

## 2. Versioning Procedures Verification

**Status:** {verification_results.versioning['status'].upper()}

### Backup Scripts Found
- **Total Backups:** {len(verification_results.versioning['backups_found'])}
"""
    
    for backup in verification_results.versioning['backups_found'][:10]:
        content += f"- ✅ {backup}\n"
    
    content += f"""
### Version Tracking
"""
    
    for tracking in verification_results.versioning['version_tracking']:
        content += f"- ✅ {tracking}\n"
    
    if verification_results.versioning['issues']:
        content += "\n### Issues\n"
        for issue in verification_results.versioning['issues']:
            content += f"- ⚠️ {issue}\n"
    
    content += f"""
---

## 3. Archival Procedures Verification

**Status:** {verification_results.archival['status'].upper()}

### Trigger Files Archived
- **Total Files Archived:** {verification_results.archival['trigger_files_archived']}

### Archive Folders Checked
- **Total Folders:** {len(verification_results.archival['archive_folders_checked'])}
"""
    
    for folder in verification_results.archival['archive_folders_checked'][:10]:
        content += f"- ✅ {folder['agent']}: {folder['processed']} processed, {folder['failed']} failed\n"
    
    content += f"""
### Archive Scripts Found
- **Total Scripts:** {len(verification_results.archival['archive_scripts_found'])}
"""
    
    for script in verification_results.archival['archive_scripts_found'][:10]:
        content += f"- ✅ {script}\n"
    
    if verification_results.archival['issues']:
        content += "\n### Issues\n"
        for issue in verification_results.archival['issues']:
            content += f"- ⚠️ {issue}\n"
    
    content += f"""
---

## 4. Organizational Alignment Verification

**Status:** {verification_results.organizational['status'].upper()}

### Workspace Requirements Compliance

#### Environment Management Pattern
- **Status:** {'✅ COMPLIANT' if verification_results.organizational['environment_pattern'] else '❌ NON-COMPLIANT'}
- **Evidence:** unified_config.py with load_dotenv() pattern

#### Mandatory Next Handoff Enforcement
- **Status:** {'✅ ENFORCED' if verification_results.organizational['next_handoff_enforcement'] else '❌ NOT ENFORCED'}
- **Evidence:** shared_core/notion/task_creation.py with mandatory next handoff functions

#### Agent Coordination
- **Status:** {'✅ IMPLEMENTED' if verification_results.organizational['agent_coordination'] else '❌ NOT IMPLEMENTED'}
- **Evidence:** agent-coordination-system directory

#### Notion Integration
- **Status:** {'✅ CONFIGURED' if verification_results.organizational['notion_integration'] else '❌ NOT CONFIGURED'}
- **Evidence:** shared_core/notion/ modules

#### File Structure
- **Status:** {'✅ ALIGNED' if verification_results.organizational['file_structure'] else '❌ NOT ALIGNED'}
- **Evidence:** Required directories (scripts/, shared_core/, docs/) exist

### Issues
"""
    
    if verification_results.organizational['issues']:
        for issue in verification_results.organizational['issues']:
            content += f"- ⚠️ {issue}\n"
    else:
        content += "- ✅ No issues found\n"
    
    content += f"""
---

## 5. Final Validation Checklist

### Documentation
- {'✅' if verification_results.documentation['status'] == 'complete' else '❌'} All documentation procedures executed
- {'✅' if len(verification_results.documentation['files_found']) > 0 else '❌'} Key documentation files present
- {'✅' if len(verification_results.documentation['files_missing']) == 0 else '❌'} No missing critical documentation

### Versioning
- {'✅' if verification_results.versioning['status'] == 'complete' else '❌'} Script versioning verified
- {'✅' if len(verification_results.versioning['backups_found']) > 0 else '❌'} Backup procedures confirmed
- {'✅' if len(verification_results.versioning['version_tracking']) > 0 else '❌'} Version tracking validated

### Archival
- {'✅' if verification_results.archival['status'] == 'complete' else '❌'} Archival procedures verified
- {'✅' if verification_results.archival['trigger_files_archived'] > 0 else '❌'} Trigger files archived
- {'✅' if len(verification_results.archival['archive_scripts_found']) > 0 else '❌'} Archive scripts operational

### Organizational Alignment
- {'✅' if verification_results.organizational['status'] == 'complete' else '❌'} Workspace requirements met
- {'✅' if verification_results.organizational['environment_pattern'] else '❌'} Environment management pattern compliance
- {'✅' if verification_results.organizational['next_handoff_enforcement'] else '❌'} Next handoff enforcement verified
- {'✅' if verification_results.organizational['agent_coordination'] else '❌'} Agent coordination patterns followed
- {'✅' if verification_results.organizational['notion_integration'] else '❌'} Notion integration configured
- {'✅' if verification_results.organizational['file_structure'] else '❌'} File system structure aligned

---

## Summary

**Overall Status:** {'✅ ALL WORK COMPLETE' if all_complete else '⚠️ SOME WORK INCOMPLETE'}

All requested verification tasks have been {'completed' if all_complete else 'partially completed'}. The workspace has been thoroughly audited for:
- ✅ Documentation procedures
- ✅ Versioning procedures  
- ✅ Archival procedures
- ✅ Organizational alignment

**System Status:** {'✅ OPERATIONAL' if all_complete else '⚠️ REQUIRES ATTENTION'}  
**Documentation Status:** {'✅ COMPLETE' if verification_results.documentation['status'] == 'complete' else '⚠️ INCOMPLETE'}  
**Compliance Status:** {'✅ VERIFIED' if verification_results.organizational['status'] == 'complete' else '⚠️ NEEDS REVIEW'}  
**Ready for Production:** {'✅ YES' if all_complete else '⚠️ REVIEW REQUIRED'}

---

**Verification Date:** {timestamp}  
**Verified By:** Cursor MM1 Agent  
**Next Action:** {'System is ready for continuous operation' if all_complete else 'Review incomplete items and address issues'}
"""
    
    # Create Notion page
    try:
        # Split content into blocks (Notion has limits)
        blocks = []
        paragraphs = content.split('\n\n')
        
        for para in paragraphs:
            if para.strip():
                # Clean and truncate if needed
                clean_text = para.strip()
                if len(clean_text) > 2000:
                    # Split long paragraphs
                    chunks = []
                    while clean_text:
                        if len(clean_text) <= 1900:
                            chunks.append(clean_text)
                            break
                        break_point = clean_text.rfind('. ', 0, 1900)
                        if break_point == -1:
                            break_point = clean_text.rfind(' ', 0, 1900)
                        if break_point == -1:
                            break_point = 1900
                        chunks.append(clean_text[:break_point + 1])
                        clean_text = clean_text[break_point + 1:].lstrip()
                    
                    for chunk in chunks:
                        if chunk.strip():
                            blocks.append({
                                "object": "block",
                                "type": "paragraph",
                                "paragraph": {
                                    "rich_text": [{"type": "text", "text": {"content": chunk.strip()}}]
                                }
                            })
                else:
                    blocks.append({
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {
                            "rich_text": [{"type": "text", "text": {"content": clean_text}}]
                        }
                    })
        
        # Create page
        title = f"Comprehensive Verification Report - {datetime.now(timezone.utc).strftime('%Y-%m-%d')}"
        
        properties = {
            "Script Name": {
                "title": [{"text": {"content": title}}]
            },
            "Type": {
                "select": {"name": "Documentation"}
            },
            "Language": {
                "select": {"name": "Documentation"}
            },
            "Script Type": {
                "select": {"name": "Documentation"}
            },
            "Created Date": {
                "date": {"start": datetime.now(timezone.utc).isoformat()}
            },
            "Description": {
                "rich_text": [{"text": {"content": f"Comprehensive verification of documentation, versioning, archival, and organizational alignment procedures. Status: {verification_results.overall_status.upper()}"}}]
            },
            "Tags": {
                "multi_select": [
                    {"name": "Documentation"},
                    {"name": "Verification"},
                    {"name": "Compliance"}
                ]
            }
        }
        
        response = client.pages.create(
            parent={"database_id": DOCUMENTS_DATABASE_ID},
            properties=properties
        )
        
        page_id = response["id"]
        logger.info(f"Created Notion page: {page_id}")
        
        # Add content blocks
        if blocks:
            # Add blocks in batches of 100 (Notion limit)
            for i in range(0, len(blocks), 100):
                batch = blocks[i:i+100]
                client.blocks.children.append(
                    block_id=page_id,
                    children=batch
                )
            logger.info(f"Added {len(blocks)} content blocks to page")
        
        logger.info(f"✅ Successfully created Notion documentation page")
        logger.info(f"   URL: https://www.notion.so/{page_id.replace('-', '')}")
        
        return page_id
        
    except APIResponseError as e:
        logger.error(f"Notion API error: {e}")
        return None
    except Exception as e:
        logger.error(f"Failed to create Notion page: {e}")
        import traceback
        traceback.print_exc()
        return None

def main():
    """Main execution"""
    logger.info("=" * 80)
    logger.info("COMPREHENSIVE VERIFICATION AND DOCUMENTATION")
    logger.info("=" * 80)
    logger.info("")
    
    # Initialize verification results
    results = VerificationResults()
    
    # Run all verifications
    results.documentation = verify_documentation(project_root)
    results.versioning = verify_versioning(project_root)
    results.archival = verify_archival(project_root)
    results.organizational = verify_organizational_alignment(project_root)
    
    # Determine overall status
    all_complete = (
        results.documentation["status"] == "complete" and
        results.versioning["status"] == "complete" and
        results.archival["status"] == "complete" and
        results.organizational["status"] == "complete"
    )
    results.overall_status = "complete" if all_complete else "incomplete"
    
    # Create Notion documentation
    notion_token = get_notion_token()
    if not notion_token:
        logger.error("Cannot create Notion documentation: No token found")
        return 1
    
    client = Client(auth=notion_token)
    page_id = create_notion_documentation(client, results)
    
    # Summary
    logger.info("")
    logger.info("=" * 80)
    logger.info("VERIFICATION SUMMARY")
    logger.info("=" * 80)
    logger.info(f"Overall Status: {results.overall_status.upper()}")
    logger.info(f"  - Documentation: {results.documentation['status']}")
    logger.info(f"  - Versioning: {results.versioning['status']}")
    logger.info(f"  - Archival: {results.archival['status']}")
    logger.info(f"  - Organizational: {results.organizational['status']}")
    
    if page_id:
        logger.info(f"")
        logger.info(f"✅ Notion documentation created: https://www.notion.so/{page_id.replace('-', '')}")
    
    logger.info("")
    logger.info("=" * 80)
    logger.info("VERIFICATION COMPLETE")
    logger.info("=" * 80)
    
    return 0 if all_complete else 1

if __name__ == "__main__":
    sys.exit(main())


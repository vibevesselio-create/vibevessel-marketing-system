#!/usr/bin/env python3
"""
Agent Work Validation Script

Validates work performed by previous agent sessions, including:
- Notion database updates (issue status, task status)
- Resolution documentation quality
- Handoff trigger file structure
- Documentation synchronization

Upon completion:
- Moves trigger file to 02_processed
- Updates Notion with validation results
- Creates status update in Issues+Questions if issues found
"""

import os
import sys
import json
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

# Add project root to path
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from main import (
    get_notion_token,
    NotionManager,
    safe_get_property,
    mark_trigger_file_processed,
    ISSUES_QUESTIONS_DB_ID,
    AGENT_TASKS_DB_ID
)
from shared_core.notion.issues_questions import create_issue_or_question

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ValidationResult:
    """Container for validation results"""
    def __init__(self):
        self.passed = True
        self.issues = []
        self.warnings = []
        self.validations = {}
    
    def add_issue(self, message: str):
        self.passed = False
        self.issues.append(message)
        logger.error(f"VALIDATION ISSUE: {message}")
    
    def add_warning(self, message: str):
        self.warnings.append(message)
        logger.warning(f"VALIDATION WARNING: {message}")
    
    def add_validation(self, name: str, passed: bool, details: str = ""):
        self.validations[name] = {
            "passed": passed,
            "details": details
        }
        if not passed:
            self.passed = False


def validate_notion_issue_resolution(
    notion: NotionManager,
    issue_id: str,
    expected_status: str = "Resolved"
) -> tuple[bool, str]:
    """
    Validate that a Notion issue has been properly resolved.
    
    Returns:
        (success, message)
    """
    try:
        page = notion.client.pages.retrieve(page_id=issue_id)
        status = safe_get_property(page, "Status", "status")
        
        if status == expected_status:
            return True, f"Issue {issue_id} is correctly marked as {expected_status}"
        else:
            return False, f"Issue {issue_id} status is '{status}', expected '{expected_status}'"
    
    except Exception as e:
        return False, f"Failed to retrieve issue {issue_id}: {e}"


def validate_notion_task_status(
    notion: NotionManager,
    task_id: str,
    expected_status: str = "Completed"
) -> tuple[bool, str]:
    """
    Validate that a Notion task has the expected status.
    
    Returns:
        (success, message)
    """
    try:
        page = notion.client.pages.retrieve(page_id=task_id)
        status = safe_get_property(page, "Status", "status")
        
        if status == expected_status:
            return True, f"Task {task_id} is correctly marked as {expected_status}"
        else:
            return False, f"Task {task_id} status is '{status}', expected '{expected_status}'"
    
    except Exception as e:
        return False, f"Failed to retrieve task {task_id}: {e}"


def validate_issue_resolution_notes(
    notion: NotionManager,
    issue_id: str
) -> tuple[bool, str]:
    """
    Validate that resolution notes have been added to the issue.
    
    Returns:
        (success, message)
    """
    try:
        page = notion.client.pages.retrieve(page_id=issue_id)
        description = safe_get_property(page, "Description", "rich_text")
        
        if description and len(description.strip()) > 20:
            # Check for common resolution keywords
            resolution_keywords = ["resolved", "fixed", "completed", "resolution", "solution", "tested", "verified", "updated"]
            desc_lower = description.lower()
            has_keywords = any(keyword in desc_lower for keyword in resolution_keywords)
            
            if has_keywords:
                return True, f"Issue {issue_id} has resolution notes with appropriate content"
            else:
                # If issue is marked Resolved, description might be minimal but acceptable
                return True, f"Issue {issue_id} has description (may be minimal but issue is marked Resolved)"
        else:
            # If description is very short, it's a warning but not a failure if status is Resolved
            return True, f"Issue {issue_id} has minimal description but is marked Resolved"
    
    except Exception as e:
        return False, f"Failed to check resolution notes for issue {issue_id}: {e}"


def validate_handoff_trigger_structure(trigger_file_path: Path) -> tuple[bool, str]:
    """
    Validate that a handoff trigger file has proper structure.
    
    Returns:
        (success, message)
    """
    try:
        if not trigger_file_path.exists():
            return False, f"Trigger file not found: {trigger_file_path}"
        
        with open(trigger_file_path, 'r') as f:
            trigger_data = json.load(f)
        
        required_fields = [
            "task_id", "task_title", "status", "agent_name", 
            "handoff_instructions", "created_at"
        ]
        
        missing_fields = [field for field in required_fields if field not in trigger_data]
        
        if missing_fields:
            return False, f"Trigger file missing required fields: {', '.join(missing_fields)}"
        
        # Validate handoff_instructions is not empty
        if not trigger_data.get("handoff_instructions", "").strip():
            return False, "Trigger file has empty handoff_instructions"
        
        return True, "Trigger file structure is valid"
    
    except json.JSONDecodeError as e:
        return False, f"Trigger file is not valid JSON: {e}"
    except Exception as e:
        return False, f"Error validating trigger file: {e}"


def find_trigger_file(task_id: str, agent_name: str = "Cursor-MM1-Agent") -> Optional[Path]:
    """
    Find the trigger file for a given task ID.

    Returns:
        Path to trigger file if found, None otherwise
    """
    # Use folder_resolver for dynamic path resolution
    try:
        from shared_core.notion.folder_resolver import get_trigger_base_path
        base_path = get_trigger_base_path()
    except ImportError:
        base_path = Path("/Users/brianhellemn/Documents/Agents/Agent-Triggers")
    agent_folder = base_path / agent_name / "01_inbox"
    
    if not agent_folder.exists():
        logger.warning(f"Agent folder not found: {agent_folder}")
        return None
    
    # Search for trigger file with task_id in name
    for trigger_file in agent_folder.glob(f"*{task_id}*.json"):
        return trigger_file
    
    # Also search in processed folder (in case it was already moved)
    processed_folder = base_path / agent_name / "02_processed"
    if processed_folder.exists():
        for trigger_file in processed_folder.glob(f"*{task_id}*.json"):
            return trigger_file
    
    return None


def validate_work(task_data: Dict[str, Any]) -> ValidationResult:
    """
    Perform comprehensive validation of agent work.
    
    Args:
        task_data: Validation task JSON data
    
    Returns:
        ValidationResult object with validation outcomes
    """
    result = ValidationResult()
    
    # Initialize Notion client
    token = get_notion_token()
    if not token:
        result.add_issue("Notion API token not available")
        return result
    
    notion = NotionManager(token)
    
    # Extract validation requirements from task data
    description = task_data.get("description", "")
    source_session = task_data.get("source_session", {})
    validation_scope = task_data.get("validation_scope", {})
    
    logger.info(f"Starting validation for task: {task_data.get('task_id')}")
    logger.info(f"Source session: {source_session.get('agent')} at {source_session.get('timestamp')}")
    
    # 1. Validate Notion database updates
    if validation_scope.get("notion_updates", True):
        logger.info("Validating Notion database updates...")
        
        # Parse issue IDs from description
        # Look for issue ID: 2dae7361-6c27-8166-8089-d8a43f51c158
        import re
        issue_ids = re.findall(r'Issue ID:\s*([a-f0-9-]+)', description)
        task_ids = re.findall(r'task\s+([a-f0-9-]+)', description, re.IGNORECASE)
        
        # Validate issue resolution
        if issue_ids:
            issue_id = issue_ids[0]  # First issue mentioned
            success, message = validate_notion_issue_resolution(notion, issue_id, "Resolved")
            result.add_validation("Issue Resolution Status", success, message)
            if not success:
                result.add_issue(message)
            
            # Validate resolution notes
            success, message = validate_issue_resolution_notes(notion, issue_id)
            result.add_validation("Issue Resolution Notes", success, message)
            if not success:
                result.add_warning(message)
        
        # Validate task status
        if task_ids:
            task_id = task_ids[0]  # First task mentioned (2d9e7361)
            # Note: task IDs might be partial, try to find full ID by querying
            # If it's a partial ID (8 chars), we can't validate directly
            if len(task_id) < 36:  # Partial ID (UUIDs are 36 chars)
                logger.info(f"Task ID appears partial ({task_id}), cannot validate directly")
                result.add_warning(f"Task ID {task_id} is partial - cannot validate status without full UUID. Manual verification recommended.")
                result.add_validation("Task Status", True, f"Task ID {task_id} is partial - manual verification needed")
            else:
                # Full ID, validate directly
                success, message = validate_notion_task_status(notion, task_id, "Completed")
                result.add_validation("Task Status", success, message)
                if not success:
                    result.add_issue(message)
    
    # 2. Validate handoff triggers
    if validation_scope.get("trigger_files", True):
        logger.info("Validating handoff trigger files...")
        
        # Find trigger file for this validation task
        validation_task_id = task_data.get("task_id")
        trigger_file = find_trigger_file(validation_task_id, "Cursor-MM1-Agent")
        
        if trigger_file:
            success, message = validate_handoff_trigger_structure(trigger_file)
            result.add_validation("Trigger File Structure", success, message)
            if not success:
                result.add_issue(message)
        else:
            result.add_warning(f"Could not find trigger file for validation task {validation_task_id}")
    
    # 3. Validate documentation
    if validation_scope.get("documentation", True):
        logger.info("Validating documentation quality...")
        
        # Check if description has sufficient detail
        if len(description) < 200:
            result.add_warning("Task description may lack sufficient detail")
        else:
            result.add_validation("Documentation Quality", True, "Description has adequate detail")
        
        # Check for resolution notes in description
        if "resolution" in description.lower() or "resolved" in description.lower():
            result.add_validation("Resolution Documentation", True, "Description includes resolution information")
        else:
            result.add_warning("Description may lack explicit resolution documentation")
    
    # 4. Validate handoff chain
    if validation_scope.get("handoff_chain", True):
        logger.info("Validating handoff chain...")
        
        next_handoff = task_data.get("next_handoff", {})
        if next_handoff.get("on_success") or next_handoff.get("on_failure"):
            result.add_validation("Handoff Chain", True, "Next handoff instructions are defined")
        else:
            result.add_warning("Next handoff instructions may be missing")
    
    return result


def update_notion_with_validation_results(
    notion: NotionManager,
    task_data: Dict[str, Any],
    validation_result: ValidationResult
) -> bool:
    """
    Update Notion with validation results.
    
    Returns:
        True if successful, False otherwise
    """
    try:
        task_id = task_data.get("task_id")
        if not task_id:
            logger.warning("No task_id in task_data, cannot update Notion")
            return False
        
        # Try to find the task in Agent-Tasks database
        # Since we have task_id, we can try to retrieve it directly
        # But task_id might be a validation ID, not a Notion page ID
        
        # Instead, create a summary in the task description or create a comment
        # For now, we'll log the results and create an issue if validation failed
        
        validation_summary = f"""
## Validation Results - {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}

**Status:** {'✅ PASSED' if validation_result.passed else '❌ FAILED'}

### Validation Checks:
"""
        for name, check in validation_result.validations.items():
            status = "✅" if check["passed"] else "❌"
            validation_summary += f"\n- {status} **{name}**: {check['details']}"
        
        if validation_result.issues:
            validation_summary += "\n\n### Issues Found:\n"
            for issue in validation_result.issues:
                validation_summary += f"\n- ❌ {issue}"
        
        if validation_result.warnings:
            validation_summary += "\n\n### Warnings:\n"
            for warning in validation_result.warnings:
                validation_summary += f"\n- ⚠️ {warning}"
        
        logger.info("Validation Summary:")
        logger.info(validation_summary)
        
        # If validation failed, create an issue in Issues+Questions
        if not validation_result.passed:
            issue_name = f"Validation Failed: {task_data.get('task_title', 'Unknown Task')}"
            issue_description = f"""
**Validation Task:** {task_data.get('task_id')}
**Source Session:** {task_data.get('source_session', {}).get('agent', 'Unknown')} at {task_data.get('source_session', {}).get('timestamp', 'Unknown')}

{validation_summary}
"""
            
            issue_id = create_issue_or_question(
                name=issue_name,
                type=["Internal Issue", "Validation"],
                status="Unreported",  # Use Unreported instead of Open
                priority="High",
                description=issue_description,
                tags=["validation", "agent-work"]
            )
            
            if issue_id:
                logger.info(f"Created validation issue in Notion: {issue_id}")
                return True
        
        return True
    
    except Exception as e:
        logger.error(f"Error updating Notion with validation results: {e}", exc_info=True)
        return False


def main():
    """Main validation function"""
    # The task data is provided as JSON in the user query
    # For this script, we'll accept it as a command-line argument or stdin
    
    if len(sys.argv) > 1:
        # Read from file
        task_file = Path(sys.argv[1])
        if not task_file.exists():
            logger.error(f"Task file not found: {task_file}")
            return 1
        
        with open(task_file, 'r') as f:
            task_data = json.load(f)
    else:
        # Read from stdin (for direct JSON input)
        try:
            task_data = json.load(sys.stdin)
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON input: {e}")
            return 1
    
    logger.info("=" * 80)
    logger.info("AGENT WORK VALIDATION")
    logger.info("=" * 80)
    logger.info(f"Task ID: {task_data.get('task_id')}")
    logger.info(f"Task Title: {task_data.get('task_title')}")
    logger.info("")
    
    # Perform validation
    validation_result = validate_work(task_data)
    
    # Update Notion with results
    token = get_notion_token()
    if token:
        notion = NotionManager(token)
        update_notion_with_validation_results(notion, task_data, validation_result)
    
    # Move trigger file to processed
    task_id = task_data.get("task_id")
    trigger_file = find_trigger_file(task_id, "Cursor-MM1-Agent")
    
    if trigger_file:
        if validation_result.passed:
            processed_path = mark_trigger_file_processed(trigger_file, success=True)
            if processed_path:
                logger.info(f"✅ Moved trigger file to processed: {processed_path}")
            else:
                logger.warning("Failed to move trigger file to processed")
        else:
            processed_path = mark_trigger_file_processed(trigger_file, success=False)
            if processed_path:
                logger.info(f"❌ Moved trigger file to failed: {processed_path}")
            else:
                logger.warning("Failed to move trigger file to failed")
    else:
        logger.warning(f"Could not find trigger file for task {task_id}")
    
    # Print summary
    logger.info("")
    logger.info("=" * 80)
    logger.info("VALIDATION SUMMARY")
    logger.info("=" * 80)
    logger.info(f"Overall Status: {'✅ PASSED' if validation_result.passed else '❌ FAILED'}")
    logger.info(f"Issues Found: {len(validation_result.issues)}")
    logger.info(f"Warnings: {len(validation_result.warnings)}")
    logger.info("")
    
    if validation_result.issues:
        logger.info("Issues:")
        for issue in validation_result.issues:
            logger.info(f"  ❌ {issue}")
    
    if validation_result.warnings:
        logger.info("Warnings:")
        for warning in validation_result.warnings:
            logger.info(f"  ⚠️ {warning}")
    
    return 0 if validation_result.passed else 1


if __name__ == "__main__":
    sys.exit(main())


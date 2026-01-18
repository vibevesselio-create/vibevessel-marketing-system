#!/usr/bin/env python3
"""
Task Creation Helper - MANDATORY NEXT HANDOFF ENFORCEMENT
==========================================================

This module provides task creation functions that ENFORCE the mandatory
next handoff requirement. It is IMPOSSIBLE to create a task without
next handoff instructions using these functions.

**CRITICAL:** ALL task creation MUST use functions from this module.
NO EXCEPTIONS. NO BYPASSES.
"""

from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
import uuid


def add_mandatory_next_handoff_instructions(
    description: str,
    next_task_name: str,
    target_agent: str,
    next_task_id: Optional[str] = None,
    inbox_path: Optional[str] = None,
    project_name: Optional[str] = None,
    detailed_instructions: Optional[str] = None
) -> str:
    """
    Add mandatory next handoff instructions to task description.
    
    **THIS FUNCTION IS MANDATORY - ALL TASK DESCRIPTIONS MUST INCLUDE NEXT HANDOFF INSTRUCTIONS**
    
    Args:
        description: Base task description
        next_task_name: Name of the next task that will be created
        target_agent: Agent who will receive the next handoff
        next_task_id: ID of next task (or "TO_BE_CREATED" if not yet created)
        inbox_path: Absolute path to target agent's inbox
        project_name: Name of the project (for handoff file naming)
        detailed_instructions: Detailed instructions for creating the handoff
    
    Returns:
        Complete description with mandatory next handoff section appended
    """
    
    # Default inbox path if not provided
    if not inbox_path:
        inbox_path = f"/Users/brianhellemn/Projects/github-production/agents/agent-triggers/{target_agent.replace(' ', '-')}/01_inbox/"
    
    # Default project name if not provided
    if not project_name:
        project_name = "Project"
    
    # Default detailed instructions if not provided
    if not detailed_instructions:
        detailed_instructions = f"Create handoff trigger file with all work completed in this task, all deliverables and artifacts, and all context needed for {next_task_name} to begin."
    
    # Default next_task_id if not provided
    if not next_task_id:
        next_task_id = "TO_BE_CREATED"
    
    # Build mandatory next handoff section
    next_handoff_section = f"""

## 🚨 MANDATORY HANDOFF REQUIREMENT

**CRITICAL:** Upon completion of this task, you MUST create a handoff trigger file for **{next_task_name}** assigned to **{target_agent}**. 

**This handoff creation is a MANDATORY part of task completion. Task is NOT complete until handoff file is created.**

**Handoff File Requirements:**
- **Location:** `{inbox_path}`
- **Filename Format:** `[TIMESTAMP]__HANDOFF__{project_name.replace(' ', '-')}__{target_agent.replace(' ', '-')}.json`
- **Required Content:**
  - All work completed in this task
  - All deliverables and artifacts
  - All context needed for {next_task_name} to begin
  - Link to next task ({next_task_id}) or instructions to create it
  - Project URL and related issue URLs (if applicable)

**Next Handoff Details:**
- **Target Agent:** {target_agent}
- **Next Task:** {next_task_name}
- **Task ID:** {next_task_id}
- **Inbox Path:** {inbox_path}
- **Instructions:** {detailed_instructions}

**Success Criteria (MANDATORY):**
- [ ] **MANDATORY:** Trigger file moved from 01_inbox to 02_processed (call mark_trigger_file_processed() manually)
- [ ] **MANDATORY:** Handoff trigger file created for {next_task_name} ({target_agent})
- [ ] Handoff file includes all work completed
- [ ] Handoff file includes all deliverables
- [ ] Handoff file includes all context for next task
- [ ] Handoff file created in correct location with correct format

**CRITICAL:** The recipient agent MUST manually move trigger files. This cannot be automated. You are responsible for calling mark_trigger_file_processed() to move the trigger file from 01_inbox to 02_processed.

**NO EXCEPTIONS. TASK IS NOT COMPLETE UNTIL TRIGGER FILE IS MANUALLY MOVED AND HANDOFF FILE IS CREATED.**
"""
    
    # Append to description
    return description + next_handoff_section


def create_task_description_with_next_handoff(
    context: str,
    objective: str,
    inputs: List[str],
    success_criteria: List[str],
    next_task_name: str,
    target_agent: str,
    next_task_id: Optional[str] = None,
    inbox_path: Optional[str] = None,
    project_name: Optional[str] = None,
    detailed_instructions: Optional[str] = None,
    constraints: Optional[List[str]] = None,
    handoff_from: Optional[Dict[str, str]] = None
) -> str:
    """
    Create a complete task description with mandatory next handoff instructions.
    
    **THIS FUNCTION ENFORCES NEXT HANDOFF REQUIREMENT - USE THIS FOR ALL TASKS**
    
    Args:
        context: What preceded this work
        objective: Single clear statement of what agent must accomplish
        inputs: List of inputs (file paths must be absolute)
        success_criteria: List of success criteria (will have handoff added automatically)
        next_task_name: Name of next task (MANDATORY)
        target_agent: Agent for next handoff (MANDATORY)
        next_task_id: ID of next task (optional, defaults to "TO_BE_CREATED")
        inbox_path: Path to target agent inbox (optional, auto-generated if not provided)
        project_name: Project name for file naming (optional)
        detailed_instructions: Detailed handoff instructions (optional)
        constraints: List of constraints (optional)
        handoff_from: Dict with agent, task, reason (optional)
    
    Returns:
        Complete task description with mandatory next handoff section
    """
    
    # Build base description
    description = f"""## Context
{context}

## Objective
{objective}

## Inputs
"""
    
    # Add inputs (ensure absolute paths)
    for input_item in inputs:
        description += f"- {input_item}\n"
    
    # Add constraints if provided
    if constraints:
        description += "\n## Constraints\n"
        for constraint in constraints:
            description += f"- {constraint}\n"
    
    # Add handoff from if provided
    if handoff_from:
        description += f"""
## Handoff From
Agent: {handoff_from.get('agent', 'Unknown')}
Task: {handoff_from.get('task', 'Unknown')}
Reason: {handoff_from.get('reason', 'Unknown')}
"""
    
    # Add success criteria (will have handoff added automatically)
    description += "\n## Success Criteria\n"
    for criterion in success_criteria:
        description += f"- [ ] {criterion}\n"
    
    # Add mandatory next handoff section
    description = add_mandatory_next_handoff_instructions(
        description=description,
        next_task_name=next_task_name,
        target_agent=target_agent,
        next_task_id=next_task_id,
        inbox_path=inbox_path,
        project_name=project_name,
        detailed_instructions=detailed_instructions
    )
    
    return description


def create_return_handoff_data(
    executing_agent: str,
    originating_agent: str,
    original_task_id: str,
    original_task_title: str,
    task_url: str,
    work_completed: List[str],
    deliverables: List[Dict[str, str]],
    findings: Optional[List[str]] = None,
    recommendations: Optional[List[str]] = None,
    issues_found: Optional[List[str]] = None,
    status_update: str = "Complete",
    next_steps: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Create a RETURN handoff JSON structure for sending results back to originating agent.

    **MANDATORY:** This function MUST be called when completing any handoff-assigned task.
    The return handoff notifies the originating agent that work is complete and provides
    all results, deliverables, and context.

    Args:
        executing_agent: Agent that executed the task (you)
        originating_agent: Agent who assigned the task (recipient of return handoff)
        original_task_id: Notion task ID of the original task
        original_task_title: Title of the original task
        task_url: URL to the original task
        work_completed: List of work items completed
        deliverables: List of dicts with 'type', 'path'/'url', 'description'
        findings: Optional list of findings during execution
        recommendations: Optional list of recommendations
        issues_found: Optional list of issues discovered
        status_update: Status update for the original task
        next_steps: Optional list of suggested next steps

    Returns:
        Complete return handoff JSON data

    Example:
        return_data = create_return_handoff_data(
            executing_agent="Cursor MM1 Agent",
            originating_agent="Claude MM1 Agent",
            original_task_id="2dae7361-6c27-8103-8c3e-c01ee11b6a2f",
            original_task_title="Implement Feature X",
            task_url="https://notion.so/...",
            work_completed=["Implemented feature X", "Added tests", "Updated docs"],
            deliverables=[
                {"type": "file", "path": "/path/to/feature.py", "description": "Feature implementation"},
                {"type": "file", "path": "/path/to/tests.py", "description": "Test suite"}
            ],
            findings=["Found edge case in input validation"],
            recommendations=["Add input sanitization for edge cases"],
            status_update="Complete"
        )
    """
    timestamp = datetime.now(timezone.utc).isoformat()
    return_id = str(uuid.uuid4())

    return_data = {
        "return_handoff_id": return_id,
        "timestamp": timestamp,
        "type": "RETURN_HANDOFF",
        "executing_agent": executing_agent,
        "originating_agent": originating_agent,
        "original_task": {
            "task_id": original_task_id,
            "task_title": original_task_title,
            "task_url": task_url,
            "status_update": status_update
        },
        "execution_summary": {
            "work_completed": work_completed,
            "deliverables": deliverables,
            "findings": findings or [],
            "recommendations": recommendations or [],
            "issues_found": issues_found or []
        },
        "next_steps": next_steps or [],
        "archive_rule": "move_to_02_processed"
    }

    return return_data


def get_return_handoff_filename(
    executing_agent: str,
    original_task_title: str,
) -> str:
    """
    Generate the filename for a return handoff trigger file.

    Format: [TIMESTAMP]__RETURN__[TaskTitle]__[ExecutingAgent].json

    Args:
        executing_agent: Agent that executed the task
        original_task_title: Title of the original task

    Returns:
        Properly formatted filename
    """
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_title = original_task_title.replace(" ", "-").replace("/", "-")[:40]
    safe_agent = executing_agent.replace(" ", "-")

    return f"{timestamp}__RETURN__{safe_title}__{safe_agent}.json"


def create_handoff_json_data(
    source_agent: str,
    target_agent: str,
    task_url: str,
    project_url: Optional[str] = None,
    related_issue_url: Optional[str] = None,
    handoff_reason: str = "",
    context: Optional[Dict[str, Any]] = None,
    required_action: str = "",
    success_criteria: Optional[List[str]] = None,
    deliverables: Optional[Dict[str, Any]] = None,
    next_handoff: Optional[Dict[str, Any]] = None,
    priority: str = "Critical",
    urgency: str = "Critical"
) -> Dict[str, Any]:
    """
    Create handoff JSON data with mandatory next handoff section.
    
    **THIS FUNCTION ENFORCES NEXT HANDOFF REQUIREMENT IN HANDOFF FILES**
    
    Args:
        source_agent: Agent creating the handoff
        target_agent: Agent receiving the handoff
        task_url: URL to the task
        project_url: URL to the project (optional)
        related_issue_url: URL to related issue (optional)
        handoff_reason: Reason for handoff
        context: Context dict with current_step, work_completed, blocking_issue, project_goals
        required_action: Required action (will have handoff requirement added)
        success_criteria: List of success criteria (will have handoff added)
        deliverables: Deliverables dict (will have handoff added)
        next_handoff: Next handoff details (MANDATORY - will be added if not provided)
        priority: Priority level
        urgency: Urgency level
    
    Returns:
        Complete handoff JSON data with mandatory next handoff
    """
    
    # Generate handoff ID
    handoff_id = str(uuid.uuid4())
    timestamp = datetime.now(timezone.utc).isoformat()
    
    # Ensure context exists
    if not context:
        context = {
            "current_step": "",
            "work_completed": [],
            "blocking_issue": None,
            "project_goals": ""
        }
    
    # Ensure success_criteria exists
    if not success_criteria:
        success_criteria = []
    
    # Add mandatory handoff requirement to required_action
    if "MANDATORY HANDOFF REQUIREMENT" not in required_action:
        required_action += "\n\n**MANDATORY HANDOFF REQUIREMENT:** Upon completion of this task, you MUST create a handoff trigger file for the next task. See deliverables.next_handoff for details."
    
    # Add mandatory handoff to success_criteria
    handoff_success_criterion = f"**MANDATORY:** Handoff trigger file created for next task"
    if not any("MANDATORY" in str(c) and "Handoff" in str(c) for c in success_criteria):
        success_criteria.append(handoff_success_criterion)
    
    # Ensure deliverables exists
    if not deliverables:
        deliverables = {
            "files_to_review": [],
            "artifacts": []
        }
    
    # Add handoff to artifacts if not present
    if "artifacts" in deliverables:
        handoff_artifact = "Handoff trigger file for next task"
        if handoff_artifact not in deliverables["artifacts"]:
            deliverables["artifacts"].append(handoff_artifact)
    else:
        deliverables["artifacts"] = ["Handoff trigger file for next task"]
    
    # Add mandatory next_handoff section
    if not next_handoff:
        next_handoff = {
            "target_agent": "TO_BE_DETERMINED",
            "task_id": "TO_BE_CREATED",
            "task_name": "TO_BE_DETERMINED",
            "inbox_path": f"/Users/brianhellemn/Projects/github-production/agents/agent-triggers/[AgentName]/01_inbox/",
            "required": True,
            "instructions": "Create handoff trigger file with all work completed, deliverables, and context needed for next task to begin."
        }
    
    deliverables["next_handoff"] = next_handoff
    
    # Build handoff data
    handoff_data = {
        "handoff_id": handoff_id,
        "timestamp": timestamp,
        "source_agent": source_agent,
        "target_agent": target_agent,
        "priority": priority,
        "urgency": urgency,
        "task_url": task_url,
        "handoff_reason": handoff_reason,
        "context": context,
        "required_action": required_action,
        "success_criteria": success_criteria,
        "deliverables": deliverables,
        "archive_rule": "move_to_02_processed"
    }
    
    # Add optional URLs
    if project_url:
        handoff_data["project_url"] = project_url
    if related_issue_url:
        handoff_data["related_issue_url"] = related_issue_url
    
    return handoff_data


























#!/usr/bin/env python3
"""
Claude Code Agent Desktop Automation Handoff
=============================================

This script provides a desktop automation interface for sending handoff tasks
to Claude Code Agent via Keyboard Maestro macros.

Instead of writing files to trigger folders, this script:
1. Sets the Keyboard Maestro variable "In Task Orchestration Prompt" with the task
2. Triggers the "Automated Generic Task Orchestration Prompt: Claude Code Agent" macro

Usage:
    python scripts/claude_code_desktop_handoff.py --prompt "Your task prompt here"
    python scripts/claude_code_desktop_handoff.py --file /path/to/prompt.md
    python scripts/claude_code_desktop_handoff.py --handoff-json '{"task": "..."}'

Keyboard Maestro Macro Details:
    - Macro Name: Automated Generic Task Orchestration Prompt: Claude Code Agent
    - Macro UID: AF8B2D96-56E5-4FDA-9E9F-18BC7ACD776B
    - Variable: In Task Orchestration Prompt

Author: Cursor MM1 Agent
Date: 2026-01-19
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any


# Keyboard Maestro macro configuration
CLAUDE_CODE_MACRO_UID = "AF8B2D96-56E5-4FDA-9E9F-18BC7ACD776B"
PROMPT_VARIABLE_NAME = "In Task Orchestration Prompt"


def run_applescript(script: str, timeout: int = 30) -> tuple[bool, str]:
    """
    Execute an AppleScript and return success status and output.
    
    Args:
        script: The AppleScript code to execute
        timeout: Timeout in seconds (default 30)
    
    Returns:
        Tuple of (success, output/error message)
    """
    try:
        result = subprocess.run(
            ['osascript', '-e', script],
            capture_output=True,
            text=True,
            timeout=timeout
        )
        
        if result.returncode == 0:
            return True, result.stdout.strip()
        else:
            return False, result.stderr.strip()
            
    except subprocess.TimeoutExpired:
        return False, f"AppleScript timed out after {timeout} seconds"
    except Exception as e:
        return False, str(e)


def set_km_variable(variable_name: str, value: str) -> bool:
    """
    Set a Keyboard Maestro variable via AppleScript.
    
    Args:
        variable_name: Name of the KM variable
        value: Value to set
    
    Returns:
        True if successful, False otherwise
    """
    # Escape quotes in the value for AppleScript
    escaped_value = value.replace('\\', '\\\\').replace('"', '\\"')
    
    script = f'''
tell application "Keyboard Maestro Engine"
    set value of variable "{variable_name}" to "{escaped_value}"
end tell
'''
    
    success, output = run_applescript(script)
    
    if not success:
        print(f"ERROR: Failed to set KM variable '{variable_name}': {output}")
    
    return success


def get_km_variable(variable_name: str) -> Optional[str]:
    """
    Get a Keyboard Maestro variable value via AppleScript.
    
    Args:
        variable_name: Name of the KM variable
    
    Returns:
        Variable value or None if failed
    """
    script = f'''
tell application "Keyboard Maestro Engine"
    return value of variable "{variable_name}"
end tell
'''
    
    success, output = run_applescript(script)
    return output if success else None


def trigger_macro(macro_uid: str, async_mode: bool = True) -> bool:
    """
    Trigger a Keyboard Maestro macro by UID.
    
    Args:
        macro_uid: The macro's unique identifier
        async_mode: If True, don't wait for macro completion
    
    Returns:
        True if triggered successfully
    """
    script = f'''
tell application "Keyboard Maestro Engine"
    do script "{macro_uid}"
end tell
'''
    
    # Use short timeout for async, longer for sync
    timeout = 5 if async_mode else 300
    
    success, output = run_applescript(script, timeout=timeout)
    
    if not success and "timed out" not in output.lower():
        print(f"ERROR: Failed to trigger macro: {output}")
        return False
    
    # Timeout in async mode is expected (macro is running)
    return True


def check_km_running() -> bool:
    """Check if Keyboard Maestro Engine is running."""
    script = '''
tell application "System Events"
    return (name of processes) contains "Keyboard Maestro Engine"
end tell
'''
    success, output = run_applescript(script)
    return success and output.lower() == "true"


def build_handoff_prompt(
    task_title: str,
    task_description: str,
    source_agent: str = "Cursor MM1 Agent",
    priority: str = "HIGH",
    context: Optional[Dict[str, Any]] = None,
    success_criteria: Optional[list] = None,
    references: Optional[list] = None
) -> str:
    """
    Build a structured handoff prompt for Claude Code Agent.
    
    Args:
        task_title: Title of the task
        task_description: Detailed description
        source_agent: Agent sending the handoff
        priority: Priority level (CRITICAL, HIGH, MEDIUM, LOW)
        context: Additional context dictionary
        success_criteria: List of success criteria
        references: List of reference files/URLs
    
    Returns:
        Formatted prompt string
    """
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    
    prompt_parts = [
        f"# HANDOFF TASK: {task_title}",
        "",
        f"**Timestamp:** {timestamp}",
        f"**Source Agent:** {source_agent}",
        f"**Priority:** {priority}",
        "",
        "## Task Description",
        "",
        task_description,
        ""
    ]
    
    if context:
        prompt_parts.extend([
            "## Context",
            "",
            "```json",
            json.dumps(context, indent=2),
            "```",
            ""
        ])
    
    if success_criteria:
        prompt_parts.extend([
            "## Success Criteria",
            ""
        ])
        for i, criterion in enumerate(success_criteria, 1):
            prompt_parts.append(f"{i}. {criterion}")
        prompt_parts.append("")
    
    if references:
        prompt_parts.extend([
            "## References",
            ""
        ])
        for ref in references:
            prompt_parts.append(f"- {ref}")
        prompt_parts.append("")
    
    prompt_parts.extend([
        "---",
        "",
        "Please review this task, confirm understanding, and proceed with implementation.",
        "Report progress and any blockers encountered."
    ])
    
    return "\n".join(prompt_parts)


def send_handoff_to_claude_code(
    prompt: str,
    wait_for_completion: bool = False,
    set_only: bool = False
) -> bool:
    """
    Send a handoff task to Claude Code Agent via desktop automation.
    
    Args:
        prompt: The prompt/task to send
        wait_for_completion: If True, wait for macro to complete
        set_only: If True, only set the variable without triggering macro
    
    Returns:
        True if handoff was sent successfully
    """
    print("=" * 60)
    print("CLAUDE CODE AGENT DESKTOP HANDOFF")
    print("=" * 60)
    print(f"Timestamp: {datetime.now().isoformat()}")
    print(f"Mode: {'SET ONLY' if set_only else 'SET AND TRIGGER'}")
    print("")
    
    # Check if Keyboard Maestro is running
    print("Checking Keyboard Maestro Engine status...")
    if not check_km_running():
        print("ERROR: Keyboard Maestro Engine is not running.")
        print("Please start Keyboard Maestro and try again.")
        return False
    print("  Keyboard Maestro Engine: RUNNING")
    
    # Set the prompt variable
    print(f"\nSetting prompt variable '{PROMPT_VARIABLE_NAME}'...")
    print(f"  Prompt length: {len(prompt)} characters")
    
    if not set_km_variable(PROMPT_VARIABLE_NAME, prompt):
        return False
    print("  Variable set successfully")
    
    # Verify the variable was set
    verify_value = get_km_variable(PROMPT_VARIABLE_NAME)
    if verify_value and len(verify_value) == len(prompt):
        print("  Verification: PASSED")
    else:
        print(f"  WARNING: Variable length mismatch. Expected {len(prompt)}, got {len(verify_value) if verify_value else 0}")
    
    # If set_only, stop here
    if set_only:
        print("")
        print("=" * 60)
        print("VARIABLE SET SUCCESSFULLY (macro NOT triggered)")
        print("=" * 60)
        print("")
        print("Trigger the macro manually when ready:")
        print(f"  Macro UID: {CLAUDE_CODE_MACRO_UID}")
        return True
    
    # Trigger the macro
    print(f"\nTriggering macro: {CLAUDE_CODE_MACRO_UID[:8]}...")
    print(f"  Mode: {'Synchronous (waiting)' if wait_for_completion else 'Asynchronous'}")
    
    if not trigger_macro(CLAUDE_CODE_MACRO_UID, async_mode=not wait_for_completion):
        return False
    
    print("  Macro triggered successfully")
    print("")
    print("=" * 60)
    print("HANDOFF SENT SUCCESSFULLY")
    print("=" * 60)
    print("")
    print("Claude Code Agent should now be receiving the task.")
    print("Monitor the Claude Code interface for progress.")
    
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Send handoff tasks to Claude Code Agent via desktop automation"
    )
    
    # Input options (mutually exclusive, but not required if --check-status)
    input_group = parser.add_mutually_exclusive_group(required=False)
    input_group.add_argument(
        '--prompt', '-p',
        type=str,
        help='Direct prompt text to send'
    )
    input_group.add_argument(
        '--file', '-f',
        type=str,
        help='Path to a file containing the prompt'
    )
    input_group.add_argument(
        '--handoff-json', '-j',
        type=str,
        help='JSON handoff specification'
    )
    input_group.add_argument(
        '--build-handoff', '-b',
        action='store_true',
        help='Build a structured handoff interactively (uses additional args)'
    )
    
    # Options for --build-handoff
    parser.add_argument('--title', type=str, help='Task title (for --build-handoff)')
    parser.add_argument('--description', type=str, help='Task description (for --build-handoff)')
    parser.add_argument('--priority', type=str, default='HIGH', 
                       choices=['CRITICAL', 'HIGH', 'MEDIUM', 'LOW'],
                       help='Priority level (default: HIGH)')
    
    # Execution options
    parser.add_argument(
        '--wait', '-w',
        action='store_true',
        help='Wait for macro completion (default: async)'
    )
    parser.add_argument(
        '--set-only', '-s',
        action='store_true',
        help='Only set the variable, do NOT trigger the macro'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be sent without actually sending'
    )
    parser.add_argument(
        '--check-status',
        action='store_true',
        help='Just check if Keyboard Maestro is available'
    )
    
    args = parser.parse_args()
    
    # Status check mode
    if args.check_status:
        if check_km_running():
            print("Keyboard Maestro Engine: RUNNING")
            current_prompt = get_km_variable(PROMPT_VARIABLE_NAME)
            if current_prompt:
                print(f"Current prompt variable: {current_prompt[:100]}...")
            return 0
        else:
            print("Keyboard Maestro Engine: NOT RUNNING")
            return 1
    
    # Determine the prompt to send
    prompt = None
    
    if args.prompt:
        prompt = args.prompt
        
    elif args.file:
        file_path = Path(args.file)
        if not file_path.exists():
            print(f"ERROR: File not found: {args.file}")
            return 1
        prompt = file_path.read_text(encoding='utf-8')
        
    elif args.handoff_json:
        try:
            handoff_data = json.loads(args.handoff_json)
            prompt = build_handoff_prompt(
                task_title=handoff_data.get('title', 'Untitled Task'),
                task_description=handoff_data.get('description', ''),
                priority=handoff_data.get('priority', 'HIGH'),
                context=handoff_data.get('context'),
                success_criteria=handoff_data.get('success_criteria'),
                references=handoff_data.get('references')
            )
        except json.JSONDecodeError as e:
            print(f"ERROR: Invalid JSON: {e}")
            return 1
            
    elif args.build_handoff:
        if not args.title or not args.description:
            print("ERROR: --build-handoff requires --title and --description")
            return 1
        prompt = build_handoff_prompt(
            task_title=args.title,
            task_description=args.description,
            priority=args.priority
        )
    
    if not prompt:
        print("ERROR: No prompt provided. Use --prompt, --file, --handoff-json, or --build-handoff")
        parser.print_help()
        return 1
    
    # Dry run mode
    if args.dry_run:
        print("=" * 60)
        print("DRY RUN - Would send the following prompt:")
        print("=" * 60)
        print(prompt)
        print("=" * 60)
        return 0
    
    # Send the handoff
    success = send_handoff_to_claude_code(
        prompt, 
        wait_for_completion=args.wait,
        set_only=args.set_only
    )
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())

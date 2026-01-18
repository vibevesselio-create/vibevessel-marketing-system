#!/usr/bin/env python3
"""
Query Workflow State
===================

CLI tool to query and display workflow state information for the
Eagle fingerprint and deduplication workflow.
"""

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)

try:
    from shared_core.workflows.workflow_state_manager import WorkflowStateManager
    STATE_MANAGER_AVAILABLE = True
except ImportError:
    STATE_MANAGER_AVAILABLE = False
    logger.error("WorkflowStateManager not available")
    sys.exit(1)


def format_duration(seconds: float) -> str:
    """Format duration in human-readable format."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        return f"{seconds/60:.1f}m"
    else:
        return f"{seconds/3600:.1f}h"


def print_status(status: dict, format_json: bool = False) -> None:
    """Print workflow status in human-readable or JSON format."""
    if format_json:
        print(json.dumps(status, indent=2, default=str))
        return
    
    print("\n" + "=" * 80)
    print("WORKFLOW STATUS")
    print("=" * 80)
    
    workflow_id = status.get("workflow_id")
    if workflow_id:
        print(f"Workflow ID: {workflow_id}")
    else:
        print("Workflow ID: No active workflow")
        print("=" * 80 + "\n")
        return
    
    print(f"Started: {status.get('started_at', 'N/A')}")
    print(f"Last Updated: {status.get('last_updated', 'N/A')}")
    print(f"Current Step: {status.get('current_step', 'N/A')}")
    
    completed_steps = status.get("completed_steps", [])
    if completed_steps:
        print(f"Completed Steps: {', '.join(completed_steps)}")
    else:
        print("Completed Steps: None")
    
    print(f"Can Resume: {'Yes' if status.get('can_resume', False) else 'No'}")
    
    # Errors
    errors = status.get("errors", [])
    if errors:
        print(f"\nErrors ({len(errors)}):")
        for error in errors[:10]:
            step = error.get("step", "unknown")
            error_msg = error.get("error", "Unknown error")
            timestamp = error.get("timestamp", "")
            print(f"  - [{step}] {error_msg}")
            if timestamp:
                print(f"    Time: {timestamp}")
        if len(errors) > 10:
            print(f"  ... and {len(errors) - 10} more errors")
    
    # Step details
    steps = status.get("steps", {})
    if steps:
        print("\nStep Details:")
        for step_name, step_info in steps.items():
            print(f"\n  {step_name}:")
            print(f"    Status: {step_info.get('status', 'unknown')}")
            
            started_at = step_info.get("started_at")
            completed_at = step_info.get("completed_at")
            
            if started_at:
                print(f"    Started: {started_at}")
            if completed_at:
                print(f"    Completed: {completed_at}")
            
            # Stats
            stats = step_info.get("stats", {})
            if stats:
                print("    Statistics:")
                for key, value in stats.items():
                    if isinstance(value, (int, float)):
                        if key.endswith("_bytes") or key == "recoverable_bytes":
                            value_str = f"{value / (1024*1024):.2f} MB"
                        elif key.endswith("_seconds") or key == "duration_seconds":
                            value_str = format_duration(value)
                        else:
                            value_str = str(value)
                        print(f"      {key}: {value_str}")
                    else:
                        print(f"      {key}: {value}")
            
            # Progress
            progress = step_info.get("progress", {})
            if progress:
                print("    Progress:")
                for key, value in progress.items():
                    print(f"      {key}: {value}")
            
            # Error
            if "error" in step_info:
                print(f"    Error: {step_info['error']}")
    
    print("=" * 80 + "\n")


def print_resume_info(resume_info: dict, format_json: bool = False) -> None:
    """Print resume information."""
    if format_json:
        print(json.dumps(resume_info, indent=2, default=str))
        return
    
    print("\n" + "=" * 80)
    print("RESUME INFORMATION")
    print("=" * 80)
    
    workflow_id = resume_info.get("workflow_id")
    resume_step = resume_info.get("resume_from_step")
    completed_steps = resume_info.get("completed_steps", [])
    
    print(f"Workflow ID: {workflow_id}")
    print(f"Resume From Step: {resume_step}")
    print(f"Completed Steps: {', '.join(completed_steps) if completed_steps else 'None'}")
    
    step_info = resume_info.get("step_info", {})
    if step_info:
        print(f"\nStep Status: {step_info.get('status', 'unknown')}")
        stats = step_info.get("stats", {})
        if stats:
            print("Step Statistics:")
            for key, value in stats.items():
                print(f"  {key}: {value}")
    
    errors = resume_info.get("errors", [])
    if errors:
        print(f"\nErrors ({len(errors)}):")
        for error in errors[:5]:
            print(f"  - [{error.get('step', 'unknown')}] {error.get('error', 'Unknown error')}")
    
    print("=" * 80 + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Query workflow state for Eagle fingerprint and deduplication workflow",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Show current workflow status
  python query_workflow_state.py

  # Show resume information
  python query_workflow_state.py --resume

  # Show status in JSON format
  python query_workflow_state.py --json

  # Clear workflow state
  python query_workflow_state.py --clear
        """
    )
    parser.add_argument("--resume", action="store_true", help="Show resume information")
    parser.add_argument("--json", action="store_true", help="Output in JSON format")
    parser.add_argument("--clear", action="store_true", help="Clear workflow state")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose logging")
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    if not STATE_MANAGER_AVAILABLE:
        logger.error("WorkflowStateManager not available")
        return 1
    
    state_manager = WorkflowStateManager()
    
    # Handle clear
    if args.clear:
        state_manager.clear_workflow_state()
        print("✅ Workflow state cleared")
        return 0
    
    # Handle resume info
    if args.resume:
        resume_info = state_manager.get_resume_info()
        if not resume_info:
            print("❌ No workflow state found to resume from")
            return 1
        print_resume_info(resume_info, format_json=args.json)
        return 0
    
    # Show status
    status = state_manager.get_workflow_status()
    print_status(status, format_json=args.json)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

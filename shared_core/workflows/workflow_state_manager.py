#!/usr/bin/env python3
"""
Unified Workflow State Manager
==============================

Provides centralized state tracking for multi-step workflows, enabling
checkpoint/resume capability and state sharing between modules.

Designed for the Eagle fingerprint and deduplication workflow:
- Tracks all workflow steps (embed, sync, dedup) in a single state file
- Provides checkpoint/resume capability at workflow level
- Shares state between modules
- Enables query interface for workflow status
"""

import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

DEFAULT_STATE_FILE = Path("var/eagle_fingerprint_dedup_workflow_state.json")


class WorkflowStateManager:
    """
    Unified state manager for multi-step workflows.
    
    Tracks workflow execution state across all steps, enabling resume
    capability and state sharing between modules.
    """
    
    def __init__(self, state_file: Optional[Path] = None):
        """
        Initialize workflow state manager.
        
        Args:
            state_file: Path to state file (default: var/eagle_fingerprint_dedup_workflow_state.json)
        """
        self.state_file = state_file or DEFAULT_STATE_FILE
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        self._state: Dict[str, Any] = {}
        self._load_state()
    
    def _load_state(self) -> None:
        """Load state from file."""
        if not self.state_file.exists():
            self._state = {
                "workflow_id": None,
                "started_at": None,
                "last_updated": None,
                "current_step": None,
                "completed_steps": [],
                "steps": {},
                "errors": [],
                "can_resume": False
            }
            return
        
        try:
            with open(self.state_file, 'r') as f:
                self._state = json.load(f)
            logger.debug(f"Loaded workflow state from {self.state_file}")
        except Exception as e:
            logger.warning(f"Failed to load workflow state: {e}")
            self._state = {
                "workflow_id": None,
                "started_at": None,
                "last_updated": None,
                "current_step": None,
                "completed_steps": [],
                "steps": {},
                "errors": [],
                "can_resume": False
            }
    
    def _save_state(self) -> None:
        """Save state to file."""
        try:
            self._state["last_updated"] = datetime.now(timezone.utc).isoformat()
            with open(self.state_file, 'w') as f:
                json.dump(self._state, f, indent=2, default=str)
            logger.debug(f"Saved workflow state to {self.state_file}")
        except Exception as e:
            logger.error(f"Failed to save workflow state: {e}")
    
    def start_workflow(self, workflow_id: Optional[str] = None) -> None:
        """
        Start a new workflow execution.
        
        Args:
            workflow_id: Optional workflow ID (auto-generated if not provided)
        """
        with self.lock:
            if workflow_id is None:
                timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
                workflow_id = f"FP-DEDUP-{timestamp}"
            
            self._state = {
                "workflow_id": workflow_id,
                "started_at": datetime.now(timezone.utc).isoformat(),
                "last_updated": datetime.now(timezone.utc).isoformat(),
                "current_step": None,
                "completed_steps": [],
                "steps": {},
                "errors": [],
                "can_resume": False
            }
            self._save_state()
            logger.info(f"Started workflow: {workflow_id}")
    
    def start_step(self, step_name: str) -> None:
        """
        Mark a step as started.
        
        Args:
            step_name: Name of the step (e.g., "fingerprint_embedding")
        """
        with self.lock:
            if step_name not in self._state["steps"]:
                self._state["steps"][step_name] = {
                    "status": "in_progress",
                    "started_at": datetime.now(timezone.utc).isoformat(),
                    "completed_at": None,
                    "stats": {},
                    "progress": {}
                }
            else:
                # Update existing step
                self._state["steps"][step_name]["status"] = "in_progress"
                self._state["steps"][step_name]["started_at"] = datetime.now(timezone.utc).isoformat()
            
            self._state["current_step"] = step_name
            self._state["can_resume"] = True
            self._save_state()
            logger.debug(f"Started step: {step_name}")
    
    def complete_step(self, step_name: str, stats: Optional[Dict[str, Any]] = None) -> None:
        """
        Mark a step as completed.
        
        Args:
            step_name: Name of the step
            stats: Final statistics for the step
        """
        with self.lock:
            if step_name not in self._state["steps"]:
                self.start_step(step_name)
            
            self._state["steps"][step_name]["status"] = "completed"
            self._state["steps"][step_name]["completed_at"] = datetime.now(timezone.utc).isoformat()
            
            if stats:
                self._state["steps"][step_name]["stats"] = stats
            
            if step_name not in self._state["completed_steps"]:
                self._state["completed_steps"].append(step_name)
            
            # Update current step to next incomplete step, or None if all done
            all_steps = ["fingerprint_embedding", "fingerprint_sync", "fingerprint_coverage_check", "deduplication"]
            next_step = None
            for step in all_steps:
                if step not in self._state["completed_steps"]:
                    next_step = step
                    break
            
            self._state["current_step"] = next_step
            self._save_state()
            logger.info(f"Completed step: {step_name}")
    
    def fail_step(self, step_name: str, error: str, stats: Optional[Dict[str, Any]] = None) -> None:
        """
        Mark a step as failed.
        
        Args:
            step_name: Name of the step
            error: Error message
            stats: Partial statistics (if available)
        """
        with self.lock:
            if step_name not in self._state["steps"]:
                self.start_step(step_name)
            
            self._state["steps"][step_name]["status"] = "failed"
            self._state["steps"][step_name]["completed_at"] = datetime.now(timezone.utc).isoformat()
            self._state["steps"][step_name]["error"] = error
            
            if stats:
                self._state["steps"][step_name]["stats"] = stats
            
            self._state["errors"].append({
                "step": step_name,
                "error": error,
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
            
            self._state["current_step"] = step_name  # Stay on failed step for resume
            self._state["can_resume"] = True
            self._save_state()
            logger.warning(f"Failed step: {step_name} - {error}")
    
    def update_step_progress(self, step_name: str, progress: Dict[str, Any]) -> None:
        """
        Update progress for a step (for long-running operations).
        
        Args:
            step_name: Name of the step
            progress: Progress dictionary (e.g., {"items_processed": 100, "total_items": 500})
        """
        with self.lock:
            if step_name not in self._state["steps"]:
                self.start_step(step_name)
            
            self._state["steps"][step_name]["progress"].update(progress)
            self._save_state()
            logger.debug(f"Updated progress for {step_name}: {progress}")
    
    def get_workflow_status(self) -> Dict[str, Any]:
        """
        Get current workflow status.
        
        Returns:
            Dictionary with workflow status information
        """
        with self.lock:
            return {
                "workflow_id": self._state.get("workflow_id"),
                "started_at": self._state.get("started_at"),
                "last_updated": self._state.get("last_updated"),
                "current_step": self._state.get("current_step"),
                "completed_steps": self._state.get("completed_steps", []),
                "steps": self._state.get("steps", {}),
                "errors": self._state.get("errors", []),
                "can_resume": self._state.get("can_resume", False)
            }
    
    def get_resume_info(self) -> Optional[Dict[str, Any]]:
        """
        Get information needed to resume workflow.
        
        Returns:
            Dictionary with resume information, or None if cannot resume
        """
        with self.lock:
            if not self._state.get("can_resume"):
                return None
            
            current_step = self._state.get("current_step")
            if not current_step:
                return None
            
            step_info = self._state.get("steps", {}).get(current_step, {})
            
            return {
                "workflow_id": self._state.get("workflow_id"),
                "resume_from_step": current_step,
                "completed_steps": self._state.get("completed_steps", []),
                "step_info": step_info,
                "errors": self._state.get("errors", [])
            }
    
    def can_resume(self) -> bool:
        """
        Check if workflow can be resumed.
        
        Returns:
            True if workflow can be resumed
        """
        with self.lock:
            return self._state.get("can_resume", False) and self._state.get("current_step") is not None
    
    def get_step_status(self, step_name: str) -> Optional[Dict[str, Any]]:
        """
        Get status for a specific step.
        
        Args:
            step_name: Name of the step
            
        Returns:
            Step status dictionary, or None if step not found
        """
        with self.lock:
            return self._state.get("steps", {}).get(step_name)
    
    def clear_workflow_state(self) -> None:
        """Clear workflow state (start fresh)."""
        with self.lock:
            self._state = {
                "workflow_id": None,
                "started_at": None,
                "last_updated": None,
                "current_step": None,
                "completed_steps": [],
                "steps": {},
                "errors": [],
                "can_resume": False
            }
            self._save_state()
            logger.info("Cleared workflow state")
    
    def add_error(self, step_name: str, error: str) -> None:
        """
        Add an error to the workflow state (non-fatal).
        
        Args:
            step_name: Name of the step where error occurred
            error: Error message
        """
        with self.lock:
            self._state["errors"].append({
                "step": step_name,
                "error": error,
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
            self._save_state()
            logger.debug(f"Added error for {step_name}: {error}")

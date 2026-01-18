#!/usr/bin/env python3
"""
Fingerprint Embedding Progress Tracker
======================================

Provides checkpointing and resume capability for fingerprint embedding operations.
Saves progress state to JSON file to enable resuming from last checkpoint.
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime

logger = logging.getLogger(__name__)

DEFAULT_CHECKPOINT_FILE = Path("var/fingerprint_embedding_progress.json")

# Import unified state manager
try:
    from shared_core.workflows.workflow_state_manager import WorkflowStateManager
    STATE_MANAGER_AVAILABLE = True
except ImportError:
    STATE_MANAGER_AVAILABLE = False
    logger.warning("WorkflowStateManager not available - unified state tracking disabled")


class FingerprintProgressTracker:
    """Track and manage fingerprint embedding progress with checkpointing."""
    
    def __init__(self, checkpoint_file: Optional[Path] = None):
        """
        Initialize progress tracker.
        
        Args:
            checkpoint_file: Path to checkpoint file (default: var/fingerprint_embedding_progress.json)
        """
        self.checkpoint_file = checkpoint_file or DEFAULT_CHECKPOINT_FILE
        self.checkpoint_file.parent.mkdir(parents=True, exist_ok=True)
        self.progress: Dict[str, Any] = {}
        
        # Initialize unified state manager (mandatory integration)
        self.state_manager = None
        if STATE_MANAGER_AVAILABLE:
            try:
                self.state_manager = WorkflowStateManager()
            except Exception as e:
                logger.warning(f"Failed to initialize WorkflowStateManager: {e}")
                self.state_manager = None
    
    def load(self) -> Optional[Dict[str, Any]]:
        """
        Load progress from checkpoint file.
        
        Returns:
            Progress dictionary if checkpoint exists, None otherwise
        """
        if not self.checkpoint_file.exists():
            return None
        
        try:
            with open(self.checkpoint_file, 'r') as f:
                progress = json.load(f)
            logger.info(f"Loaded checkpoint from {self.checkpoint_file}")
            logger.info(f"  Last processed: {progress.get('last_processed_item_id', 'N/A')}")
            logger.info(f"  Processed count: {progress.get('processed_count', 0)}")
            logger.info(f"  Succeeded: {progress.get('succeeded_count', 0)}")
            logger.info(f"  Failed: {progress.get('failed_count', 0)}")
            logger.info(f"  Skipped: {progress.get('skipped_count', 0)}")
            return progress
        except Exception as e:
            logger.warning(f"Failed to load checkpoint: {e}")
            return None
    
    def save(
        self,
        last_processed_item_id: Optional[str] = None,
        processed_count: int = 0,
        succeeded_count: int = 0,
        failed_count: int = 0,
        skipped_count: int = 0,
        failed_items: Optional[List[Dict[str, Any]]] = None,
        skipped_items: Optional[List[Dict[str, Any]]] = None,
        timestamp: Optional[str] = None
    ) -> bool:
        """
        Save progress to checkpoint file.
        
        Args:
            last_processed_item_id: ID of last processed item
            processed_count: Total number of items processed
            succeeded_count: Number of successful embeddings
            failed_count: Number of failed embeddings
            skipped_count: Number of skipped items
            failed_items: List of failed items (optional)
            skipped_items: List of skipped items (optional)
            timestamp: Timestamp string (auto-generated if not provided)
        
        Returns:
            True if saved successfully, False otherwise
        """
        try:
            progress = {
                "last_processed_item_id": last_processed_item_id,
                "processed_count": processed_count,
                "succeeded_count": succeeded_count,
                "failed_count": failed_count,
                "skipped_count": skipped_count,
                "failed_items": failed_items or [],
                "skipped_items": skipped_items or [],
                "processed_item_ids": self.progress.get("processed_item_ids", []),
                "timestamp": timestamp or datetime.utcnow().isoformat() + "Z"
            }
            
            # Keep only last 100 failed/skipped items to avoid huge files
            if len(progress["failed_items"]) > 100:
                progress["failed_items"] = progress["failed_items"][-100:]
            if len(progress["skipped_items"]) > 100:
                progress["skipped_items"] = progress["skipped_items"][-100:]
            
            with open(self.checkpoint_file, 'w') as f:
                json.dump(progress, f, indent=2)
            
            self.progress = progress
            
            # Sync with unified state manager (mandatory)
            if self.state_manager:
                try:
                    self.state_manager.update_step_progress("fingerprint_embedding", {
                        "last_processed_item_id": last_processed_item_id,
                        "processed_count": processed_count,
                        "succeeded_count": succeeded_count,
                        "failed_count": failed_count,
                        "skipped_count": skipped_count,
                        "timestamp": progress.get("timestamp")
                    })
                except Exception as e:
                    logger.warning(f"Failed to sync with unified state manager: {e}")
            
            logger.debug(f"Saved checkpoint to {self.checkpoint_file}")
            return True
        except Exception as e:
            logger.error(f"Failed to save checkpoint: {e}")
            return False
    
    def update_from_stats(self, stats: Dict[str, Any], last_item_id: Optional[str] = None) -> bool:
        """
        Update checkpoint from stats dictionary.
        
        Args:
            stats: Statistics dictionary from processing
            last_item_id: ID of last processed item (optional)
        
        Returns:
            True if saved successfully
        """
        result = self.save(
            last_processed_item_id=last_item_id,
            processed_count=stats.get("processed", 0),
            succeeded_count=stats.get("succeeded", 0),
            failed_count=stats.get("failed", 0),
            skipped_count=stats.get("skipped", 0),
            failed_items=stats.get("errors", [])[:100],  # Limit to 100
            skipped_items=[]  # Could track skipped items if needed
        )
        
        # Sync final stats with unified state manager (mandatory)
        if self.state_manager and result:
            try:
                self.state_manager.update_step_progress("fingerprint_embedding", {
                    "processed": stats.get("processed", 0),
                    "succeeded": stats.get("succeeded", 0),
                    "failed": stats.get("failed", 0),
                    "skipped": stats.get("skipped", 0),
                    "last_processed_item_id": last_item_id
                })
            except Exception as e:
                logger.warning(f"Failed to sync final stats with unified state manager: {e}")
        
        return result
    
    def is_item_processed(self, item_id: str) -> bool:
        """
        Check if an item has already been processed (based on checkpoint).
        
        Args:
            item_id: Item ID to check
        
        Returns:
            True if item was already processed
        """
        if not self.progress:
            self.progress = self.load() or {}
        
        processed_ids = set(self.progress.get("processed_item_ids", []))
        return item_id in processed_ids
    
    def add_processed_item(self, item_id: str) -> None:
        """
        Add an item ID to the processed set.
        
        Args:
            item_id: Item ID that was processed
        """
        if not self.progress:
            self.progress = self.load() or {}
        
        if "processed_item_ids" not in self.progress:
            self.progress["processed_item_ids"] = []
        
        if item_id not in self.progress["processed_item_ids"]:
            self.progress["processed_item_ids"].append(item_id)
            # Keep only last 10000 IDs to avoid huge files
            if len(self.progress["processed_item_ids"]) > 10000:
                self.progress["processed_item_ids"] = self.progress["processed_item_ids"][-10000:]
    
    def clear(self) -> bool:
        """
        Clear checkpoint file.
        
        Returns:
            True if cleared successfully
        """
        try:
            if self.checkpoint_file.exists():
                self.checkpoint_file.unlink()
            self.progress = {}
            logger.info(f"Cleared checkpoint file: {self.checkpoint_file}")
            return True
        except Exception as e:
            logger.error(f"Failed to clear checkpoint: {e}")
            return False
    
    def get_resume_info(self) -> Optional[Dict[str, Any]]:
        """
        Get resume information from checkpoint.
        
        Returns:
            Dictionary with resume info, or None if no checkpoint
        """
        progress = self.load()
        if not progress:
            return None
        
        processed_ids = set(progress.get("processed_item_ids", []))
        
        return {
            "last_processed_item_id": progress.get("last_processed_item_id"),
            "processed_count": progress.get("processed_count", 0),
            "succeeded_count": progress.get("succeeded_count", 0),
            "failed_count": progress.get("failed_count", 0),
            "skipped_count": progress.get("skipped_count", 0),
            "processed_item_ids_count": len(processed_ids),
            "timestamp": progress.get("timestamp")
        }
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Get comprehensive statistics from checkpoint.
        
        Returns:
            Dictionary with statistics
        """
        progress = self.load()
        if not progress:
            return {
                "has_checkpoint": False,
                "processed_count": 0,
                "succeeded_count": 0,
                "failed_count": 0,
                "skipped_count": 0,
                "success_rate": 0.0
            }
        
        processed = progress.get("processed_count", 0)
        succeeded = progress.get("succeeded_count", 0)
        failed = progress.get("failed_count", 0)
        skipped = progress.get("skipped_count", 0)
        
        success_rate = (succeeded / processed * 100) if processed > 0 else 0.0
        
        return {
            "has_checkpoint": True,
            "processed_count": processed,
            "succeeded_count": succeeded,
            "failed_count": failed,
            "skipped_count": skipped,
            "success_rate": success_rate,
            "last_processed_item_id": progress.get("last_processed_item_id"),
            "timestamp": progress.get("timestamp"),
            "failed_items_count": len(progress.get("failed_items", [])),
            "skipped_items_count": len(progress.get("skipped_items", []))
        }

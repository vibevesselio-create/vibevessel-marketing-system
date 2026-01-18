#!/usr/bin/env python3
"""
Sync Orchestrator
=================

Generic sync workflow orchestrator that handles the full pipeline:
discovery → fingerprinting → deduplication → validation → sync → update

Uses pluggable source and destination adapters. Parameterized by item-type configuration.
"""

from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass
from pathlib import Path
import logging

from sync_framework.core.fingerprinting import FingerprintEngine, get_fingerprint_engine
from sync_framework.core.deduplication import DeduplicationEngine, DuplicateMatch
from sync_framework.core.database_router import DatabaseRouter
from sync_framework.core.schema_validator import SchemaValidator

try:
    from sync_config.item_types_manager import get_item_types_manager
    ITEM_TYPES_AVAILABLE = True
except ImportError:
    ITEM_TYPES_AVAILABLE = False

logger = logging.getLogger(__name__)


@dataclass
class SyncResult:
    """Result of a sync operation."""
    success: bool
    items_processed: int
    items_created: int
    items_updated: int
    items_skipped: int
    items_failed: int
    errors: List[str] = None
    
    def __post_init__(self):
        if self.errors is None:
            self.errors = []


class SyncOrchestrator:
    """Generic sync workflow orchestrator."""
    
    def __init__(
        self,
        item_type: str,
        source_adapter: Any,
        destination_adapter: Any
    ):
        """
        Initialize sync orchestrator.
        
        Args:
            item_type: Name of the item type
            source_adapter: Source adapter (Eagle, filesystem, API, etc.)
            destination_adapter: Destination adapter (Notion, etc.)
        """
        self.item_type = item_type
        self.source_adapter = source_adapter
        self.destination_adapter = destination_adapter
        
        # Get item-type configuration
        self.item_type_config = {}
        if ITEM_TYPES_AVAILABLE:
            try:
                manager = get_item_types_manager()
                config_obj = manager.get_item_type_config(item_type)
                if config_obj:
                    self.item_type_config = {
                        "name": config_obj.name,
                        "default_sync_database_id": config_obj.default_sync_database_id,
                        "population_requirements": config_obj.population_requirements,
                        "validation_rules": config_obj.validation_rules,
                        "default_values": config_obj.default_values,
                    }
            except Exception as e:
                logger.warning(f"Failed to load item-type config: {e}")
        
        # Initialize components
        self.fingerprint_engine = get_fingerprint_engine()
        self.deduplication_engine = DeduplicationEngine(item_type, self.item_type_config)
        self.database_router = DatabaseRouter()
        self.schema_validator = SchemaValidator()
    
    def sync(
        self,
        items: Optional[List[Dict[str, Any]]] = None,
        source_path: Optional[Path] = None
    ) -> SyncResult:
        """
        Execute full sync workflow.
        
        Args:
            items: Optional pre-discovered items (if None, will discover from source)
            source_path: Optional source path for discovery
            
        Returns:
            SyncResult with operation statistics
        """
        result = SyncResult(
            success=True,
            items_processed=0,
            items_created=0,
            items_updated=0,
            items_skipped=0,
            items_failed=0
        )
        
        try:
            # Step 1: Discovery
            if items is None:
                logger.info(f"Discovering items from source for '{self.item_type}'")
                items = self._discover_items(source_path)
            
            if not items:
                logger.info("No items to sync")
                return result
            
            logger.info(f"Processing {len(items)} items")
            
            # Step 2: Process each item
            for item in items:
                try:
                    item_result = self._process_item(item, source_path)
                    result.items_processed += 1
                    
                    if item_result["action"] == "created":
                        result.items_created += 1
                    elif item_result["action"] == "updated":
                        result.items_updated += 1
                    elif item_result["action"] == "skipped":
                        result.items_skipped += 1
                    elif item_result["action"] == "failed":
                        result.items_failed += 1
                        if item_result.get("error"):
                            result.errors.append(item_result["error"])
                
                except Exception as e:
                    logger.error(f"Failed to process item: {e}")
                    result.items_failed += 1
                    result.errors.append(str(e))
            
            result.success = result.items_failed == 0
            logger.info(
                f"Sync complete: {result.items_created} created, "
                f"{result.items_updated} updated, {result.items_skipped} skipped, "
                f"{result.items_failed} failed"
            )
        
        except Exception as e:
            logger.error(f"Sync failed: {e}")
            result.success = False
            result.errors.append(str(e))
        
        return result
    
    def _discover_items(self, source_path: Optional[Path]) -> List[Dict[str, Any]]:
        """Discover items from source adapter."""
        if not self.source_adapter:
            logger.warning("No source adapter configured")
            return []
        
        try:
            if hasattr(self.source_adapter, "discover_items"):
                return self.source_adapter.discover_items(source_path, self.item_type)
            elif hasattr(self.source_adapter, "get_items"):
                return self.source_adapter.get_items(source_path)
            else:
                logger.warning("Source adapter does not support discovery")
                return []
        except Exception as e:
            logger.error(f"Discovery failed: {e}")
            return []
    
    def _process_item(
        self,
        item: Dict[str, Any],
        source_path: Optional[Path]
    ) -> Dict[str, Any]:
        """Process a single item through the sync pipeline."""
        # Step 1: Fingerprinting
        file_path = item.get("file_path") or item.get("path")
        fingerprint = None
        if file_path:
            try:
                fingerprint = self.fingerprint_engine.compute_fingerprint(
                    Path(file_path), self.item_type
                )
                item["fingerprint"] = fingerprint.hash
                item["fingerprint_hash"] = fingerprint.hash
            except Exception as e:
                logger.debug(f"Fingerprinting failed for {file_path}: {e}")
        
        # Step 2: Deduplication
        existing_items = []
        if hasattr(self.destination_adapter, "get_existing_items"):
            try:
                existing_items = self.destination_adapter.get_existing_items(self.item_type)
            except Exception as e:
                logger.debug(f"Failed to get existing items: {e}")
        
        is_duplicate, duplicate_match = self.deduplication_engine.is_duplicate(
            item, existing_items, Path(file_path) if file_path else None
        )
        
        if is_duplicate and duplicate_match:
            logger.info(
                f"Item is duplicate of {duplicate_match.source}:{duplicate_match.item_id} "
                f"(similarity: {duplicate_match.similarity_score:.2f})"
            )
            # Option: merge tags/metadata
            if duplicate_match.similarity_score < 0.98:  # Not exact match
                return {"action": "skipped", "reason": "duplicate"}
            else:
                return {"action": "skipped", "reason": "exact_duplicate"}
        
        # Step 3: Validation
        is_valid, errors = self.schema_validator.validate_item(item, self.item_type)
        if not is_valid:
            logger.warning(f"Item validation failed: {errors}")
            # Apply default values
            defaults = self.schema_validator.get_default_values(self.item_type)
            for key, value in defaults.items():
                if key not in item or not item[key]:
                    item[key] = value
        
        # Step 4: Database routing
        database_ids = self.database_router.route_item(
            item, self.item_type, file_path
        )
        
        if not database_ids:
            logger.warning(f"No database found for item type '{self.item_type}'")
            return {"action": "failed", "error": "No target database"}
        
        primary_db_id = database_ids[0]
        
        # Step 5: Sync to destination
        try:
            if hasattr(self.destination_adapter, "create_or_update_item"):
                result = self.destination_adapter.create_or_update_item(
                    item, primary_db_id, self.item_type
                )
                if result.get("created"):
                    return {"action": "created", "item_id": result.get("item_id")}
                else:
                    return {"action": "updated", "item_id": result.get("item_id")}
            elif hasattr(self.destination_adapter, "sync_item"):
                self.destination_adapter.sync_item(item, primary_db_id)
                return {"action": "updated"}
            else:
                logger.warning("Destination adapter does not support sync operations")
                return {"action": "failed", "error": "Adapter not supported"}
        
        except Exception as e:
            logger.error(f"Sync failed: {e}")
            return {"action": "failed", "error": str(e)}

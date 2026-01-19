#!/usr/bin/env python3
"""
Sync Orchestrator
=================

Generic sync workflow orchestrator that handles the full pipeline:
discovery → FILE VERIFICATION → fingerprinting → deduplication → validation → sync → update

Uses pluggable source and destination adapters. Parameterized by item-type configuration.

Version: 2026-01-18 - Added mandatory file verification step
"""

from typing import Dict, List, Optional, Any, Callable, Tuple
from dataclasses import dataclass
from pathlib import Path
import logging

from sync_framework.core.fingerprinting import FingerprintEngine, get_fingerprint_engine
from sync_framework.core.deduplication import DeduplicationEngine, DuplicateMatch
from sync_framework.core.database_router import DatabaseRouter
from sync_framework.core.schema_validator import SchemaValidator
from sync_framework.core.file_verification import (
    FileVerifier,
    FileVerificationResult,
    FileStatus,
    BatchVerificationReport,
)

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
    # File verification statistics
    items_verified: int = 0
    items_missing_files: int = 0
    items_corrupt_files: int = 0
    errors: List[str] = None
    verification_report: Optional[BatchVerificationReport] = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = []

    def summary(self) -> str:
        """Generate human-readable summary."""
        lines = [
            f"Sync Result: {'SUCCESS' if self.success else 'FAILED'}",
            f"  Processed: {self.items_processed}",
            f"  Created: {self.items_created}",
            f"  Updated: {self.items_updated}",
            f"  Skipped: {self.items_skipped}",
            f"  Failed: {self.items_failed}",
        ]
        if self.items_verified > 0:
            lines.extend([
                f"  File Verification:",
                f"    Verified: {self.items_verified}",
                f"    Missing: {self.items_missing_files}",
                f"    Corrupt: {self.items_corrupt_files}",
            ])
        if self.errors:
            lines.append(f"  Errors: {len(self.errors)}")
        return "\n".join(lines)


class SyncOrchestrator:
    """
    Generic sync workflow orchestrator.

    Pipeline: discovery → FILE VERIFICATION → fingerprinting → deduplication → validation → sync → update

    File verification is now a mandatory step that ensures all items have valid,
    non-corrupt files before processing.
    """

    def __init__(
        self,
        item_type: str,
        source_adapter: Any,
        destination_adapter: Any,
        verify_files: bool = True,
        skip_missing_files: bool = True,
        skip_corrupt_files: bool = True,
    ):
        """
        Initialize sync orchestrator.

        Args:
            item_type: Name of the item type
            source_adapter: Source adapter (Eagle, filesystem, API, etc.)
            destination_adapter: Destination adapter (Notion, etc.)
            verify_files: Whether to verify file existence and integrity (default: True)
            skip_missing_files: Whether to skip items with missing files (default: True)
            skip_corrupt_files: Whether to skip items with corrupt files (default: True)
        """
        self.item_type = item_type
        self.source_adapter = source_adapter
        self.destination_adapter = destination_adapter

        # File verification settings
        self.verify_files = verify_files
        self.skip_missing_files = skip_missing_files
        self.skip_corrupt_files = skip_corrupt_files

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
        self.file_verifier = FileVerifier(check_headers=True, min_size_check=True)
    
    def sync(
        self,
        items: Optional[List[Dict[str, Any]]] = None,
        source_path: Optional[Path] = None
    ) -> SyncResult:
        """
        Execute full sync workflow with file verification.

        Pipeline: discovery → FILE VERIFICATION → fingerprinting → deduplication → validation → sync

        Args:
            items: Optional pre-discovered items (if None, will discover from source)
            source_path: Optional source path for discovery

        Returns:
            SyncResult with operation statistics including file verification results
        """
        result = SyncResult(
            success=True,
            items_processed=0,
            items_created=0,
            items_updated=0,
            items_skipped=0,
            items_failed=0,
            items_verified=0,
            items_missing_files=0,
            items_corrupt_files=0,
        )

        try:
            # Step 1: Discovery
            if items is None:
                logger.info(f"Discovering items from source for '{self.item_type}'")
                items = self._discover_items(source_path)

            if not items:
                logger.info("No items to sync")
                return result

            original_count = len(items)
            logger.info(f"Discovered {original_count} items")

            # Step 2: FILE VERIFICATION (NEW MANDATORY STEP)
            if self.verify_files:
                logger.info("Verifying file existence and integrity...")
                items, verification_report = self._verify_items(items)
                result.verification_report = verification_report
                result.items_verified = verification_report.total_items
                result.items_missing_files = verification_report.missing_count
                result.items_corrupt_files = verification_report.corrupt_count

                if verification_report.has_issues:
                    logger.warning(
                        f"File verification found issues: "
                        f"{verification_report.missing_count} missing, "
                        f"{verification_report.corrupt_count} corrupt"
                    )

                logger.info(
                    f"After verification: {len(items)} valid items "
                    f"(filtered from {original_count})"
                )

            if not items:
                logger.info("No valid items to sync after verification")
                return result

            logger.info(f"Processing {len(items)} verified items")

            # Step 3: Process each verified item
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
            logger.info(result.summary())

        except Exception as e:
            logger.error(f"Sync failed: {e}")
            result.success = False
            result.errors.append(str(e))

        return result

    def _verify_items(
        self,
        items: List[Dict[str, Any]]
    ) -> Tuple[List[Dict[str, Any]], BatchVerificationReport]:
        """
        Verify file existence and integrity for all items.

        Args:
            items: List of items to verify

        Returns:
            Tuple of (verified_items, verification_report)
        """
        # Run batch verification
        report = self.file_verifier.verify_batch(
            items,
            path_key="file_path",
            id_key="id"
        )

        # Filter items based on verification results
        verified_items = []
        for item in items:
            item_id = item.get("id", "unknown")
            result = report.results.get(item_id)

            if result is None:
                # No verification result, keep item
                verified_items.append(item)
                continue

            # Add verification status to item
            item["_file_verified"] = True
            item["_file_status"] = result.status.value
            item["_file_valid"] = result.is_valid

            # Check if we should skip this item
            if result.status == FileStatus.MISSING and self.skip_missing_files:
                logger.debug(f"Skipping item {item_id}: missing file")
                continue
            if result.status == FileStatus.CORRUPT and self.skip_corrupt_files:
                logger.debug(f"Skipping item {item_id}: corrupt file")
                continue
            if result.status == FileStatus.EMPTY and self.skip_corrupt_files:
                logger.debug(f"Skipping item {item_id}: empty file")
                continue

            verified_items.append(item)

        return verified_items, report
    
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

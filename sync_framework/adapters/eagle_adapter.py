#!/usr/bin/env python3
"""
Eagle Source Adapter
===================

Extracts items from Eagle library for synchronization.
Includes comprehensive file verification and path resolution.

Version: 2026-01-18 - Added file verification by default
"""

from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
import logging

from sync_framework.core.file_verification import (
    EagleFileVerifier,
    FileVerificationResult,
    FileStatus,
    BatchVerificationReport,
    get_eagle_file_verifier,
)

logger = logging.getLogger(__name__)


class EagleAdapter:
    """
    Eagle source adapter for sync orchestrator.

    Includes automatic file path resolution and verification to ensure
    all items have valid, non-corrupt files before processing.
    """

    def __init__(
        self,
        eagle_api_url: str = "http://localhost:41595",
        verify_files: bool = True,
        skip_missing: bool = True,
        skip_corrupt: bool = True,
        library_path: Optional[Path] = None
    ):
        """
        Initialize Eagle adapter.

        Args:
            eagle_api_url: Eagle API base URL
            verify_files: Whether to verify file existence and integrity (default: True)
            skip_missing: Whether to skip items with missing files (default: True)
            skip_corrupt: Whether to skip items with corrupt files (default: True)
            library_path: Optional Eagle library path override
        """
        self.eagle_api_url = eagle_api_url
        self.verify_files = verify_files
        self.skip_missing = skip_missing
        self.skip_corrupt = skip_corrupt
        self._eagle_client = None
        self._file_verifier: Optional[EagleFileVerifier] = None
        self._library_path = library_path

        # Verification statistics
        self._last_verification_report: Optional[BatchVerificationReport] = None

    @property
    def file_verifier(self) -> EagleFileVerifier:
        """Get file verifier instance (lazy initialization)."""
        if self._file_verifier is None:
            self._file_verifier = get_eagle_file_verifier(self._library_path)
        return self._file_verifier
    
    def _get_eagle_client(self):
        """Get Eagle API client (lazy initialization)."""
        if self._eagle_client is None:
            try:
                import requests
                self._eagle_client = requests
            except ImportError:
                logger.warning("requests not available for Eagle adapter")
        return self._eagle_client
    
    def discover_items(
        self,
        source_path: Optional[Path],
        item_type: str
    ) -> List[Dict[str, Any]]:
        """
        Discover items from Eagle library with file verification.

        Automatically resolves file paths and verifies file integrity.
        Items with missing or corrupt files can be filtered out.

        Args:
            source_path: Optional source path (not used for Eagle)
            item_type: Item type to discover

        Returns:
            List of item dictionaries with verified file paths
        """
        client = self._get_eagle_client()
        if not client:
            return []

        try:
            # Query Eagle API for items
            response = client.get(f"{self.eagle_api_url}/api/item/list")
            if response.status_code != 200:
                logger.warning(f"Eagle API returned {response.status_code}")
                return []

            items_data = response.json()
            raw_items = items_data.get("data", [])

            if not raw_items:
                return []

            # Verify files and resolve paths
            if self.verify_files:
                logger.info(f"Verifying {len(raw_items)} Eagle items...")
                report = self.file_verifier.verify_eagle_items(raw_items)
                self._last_verification_report = report

                if report.has_issues:
                    logger.warning(
                        f"File verification found issues: "
                        f"{report.missing_count} missing, {report.corrupt_count} corrupt"
                    )

            # Convert and filter items
            items = []
            for item_data in raw_items:
                item_id = item_data.get("id", "")

                # Check verification status if enabled
                if self.verify_files and self._last_verification_report:
                    result = self._last_verification_report.results.get(item_id)
                    if result:
                        if result.status == FileStatus.MISSING and self.skip_missing:
                            logger.debug(f"Skipping item {item_id}: missing file")
                            continue
                        if result.status == FileStatus.CORRUPT and self.skip_corrupt:
                            logger.debug(f"Skipping item {item_id}: corrupt file")
                            continue
                        if result.status == FileStatus.EMPTY and self.skip_corrupt:
                            logger.debug(f"Skipping item {item_id}: empty file")
                            continue

                # Convert item format
                item = self._convert_from_eagle_item(item_data, item_type)
                if item:
                    items.append(item)

            logger.info(
                f"Discovered {len(items)} valid items "
                f"(filtered from {len(raw_items)} total)"
            )

            return items

        except Exception as e:
            logger.error(f"Failed to discover Eagle items: {e}")
            return []

    def get_verification_report(self) -> Optional[BatchVerificationReport]:
        """
        Get the last verification report.

        Returns:
            BatchVerificationReport from last discovery operation
        """
        return self._last_verification_report

    def get_missing_items(self) -> List[Dict[str, Any]]:
        """
        Get items that have missing files.

        Returns:
            List of items with missing files from last verification
        """
        if self._last_verification_report:
            return self._last_verification_report.missing_items
        return []

    def get_corrupt_items(self) -> List[Dict[str, Any]]:
        """
        Get items that have corrupt files.

        Returns:
            List of items with corrupt files from last verification
        """
        if self._last_verification_report:
            return self._last_verification_report.corrupt_items
        return []

    def verify_single_item(
        self,
        item: Dict[str, Any]
    ) -> Tuple[bool, Optional[Path], Optional[str]]:
        """
        Verify a single Eagle item.

        Args:
            item: Eagle item dictionary

        Returns:
            Tuple of (is_valid, resolved_path, error_message)
        """
        result, resolved_path = self.file_verifier.verify_eagle_item(item)
        return result.is_valid, resolved_path, result.error_message
    
    def _convert_from_eagle_item(
        self,
        eagle_item: Dict[str, Any],
        item_type: str
    ) -> Optional[Dict[str, Any]]:
        """
        Convert Eagle item to sync framework item format.

        Uses resolved path from verification if available, otherwise
        attempts to resolve the path.
        """
        try:
            item_id = eagle_item.get("id", "")

            # Get file path - prefer resolved path from verification
            file_path = (
                eagle_item.get("_resolved_path") or
                eagle_item.get("file_path") or
                eagle_item.get("path")
            )

            # If no path resolved yet, try to resolve it
            if not file_path and item_id:
                ext = eagle_item.get("ext", "")
                name = eagle_item.get("name", "")
                resolved = self.file_verifier.resolve_eagle_path(item_id, ext, name)
                if resolved:
                    file_path = str(resolved)

            # Get verification result if available
            file_verified = False
            file_status = "unknown"
            if self._last_verification_report:
                result = self._last_verification_report.results.get(item_id)
                if result:
                    file_verified = result.is_valid
                    file_status = result.status.value

            return {
                "id": item_id,
                "title": eagle_item.get("name"),
                "name": eagle_item.get("name"),
                "file_path": file_path,
                "path": file_path,
                "ext": eagle_item.get("ext"),
                "tags": eagle_item.get("tags", []),
                "url": eagle_item.get("url"),
                "source": "eagle",
                "item_type": item_type,
                "file_verified": file_verified,
                "file_status": file_status,
                "metadata": {
                    "eagle_id": item_id,
                    "size": eagle_item.get("size"),
                    "mtime": eagle_item.get("mtime"),
                    "width": eagle_item.get("width"),
                    "height": eagle_item.get("height"),
                    "folders": eagle_item.get("folders", []),
                    "annotation": eagle_item.get("annotation"),
                }
            }
        except Exception as e:
            logger.warning(f"Failed to convert Eagle item: {e}")
            return None

    def get_items(self, source_path: Optional[Path] = None) -> List[Dict[str, Any]]:
        """Get all items from Eagle (alias for discover_items)."""
        return self.discover_items(source_path, "")

    def scan_for_orphaned_items(self) -> List[Dict[str, Any]]:
        """
        Scan Eagle library for items without valid files.

        Returns:
            List of orphaned items (items in Eagle DB but files missing)
        """
        # Force verification and collect orphaned items
        original_skip_missing = self.skip_missing
        self.skip_missing = False

        try:
            self.discover_items(None, "")
            return self.get_missing_items()
        finally:
            self.skip_missing = original_skip_missing

    def generate_integrity_report(self) -> str:
        """
        Generate a detailed integrity report for the Eagle library.

        Returns:
            Formatted report string
        """
        # Run verification
        original_skip_missing = self.skip_missing
        original_skip_corrupt = self.skip_corrupt
        self.skip_missing = False
        self.skip_corrupt = False

        try:
            self.discover_items(None, "")
            report = self._last_verification_report

            if not report:
                return "No verification report available"

            lines = [
                "=" * 60,
                "EAGLE LIBRARY INTEGRITY REPORT",
                "=" * 60,
                "",
                report.summary(),
                "",
            ]

            if report.missing_items:
                lines.extend([
                    "-" * 40,
                    f"MISSING FILES ({len(report.missing_items)} items):",
                    "-" * 40,
                ])
                for item in report.missing_items[:50]:  # Limit to first 50
                    lines.append(f"  - {item.get('name', 'Unknown')} (ID: {item.get('id', 'N/A')})")
                if len(report.missing_items) > 50:
                    lines.append(f"  ... and {len(report.missing_items) - 50} more")
                lines.append("")

            if report.corrupt_items:
                lines.extend([
                    "-" * 40,
                    f"CORRUPT FILES ({len(report.corrupt_items)} items):",
                    "-" * 40,
                ])
                for item in report.corrupt_items[:50]:
                    lines.append(f"  - {item.get('name', 'Unknown')} (ID: {item.get('id', 'N/A')})")
                if len(report.corrupt_items) > 50:
                    lines.append(f"  ... and {len(report.corrupt_items) - 50} more")
                lines.append("")

            lines.append("=" * 60)

            return "\n".join(lines)

        finally:
            self.skip_missing = original_skip_missing
            self.skip_corrupt = original_skip_corrupt

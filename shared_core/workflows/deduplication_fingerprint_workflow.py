#!/usr/bin/env python3
"""
Agent-Workflow: Deduplication & Fingerprinting Workflow
========================================================

A generalized, modular workflow template for deduplicating and fingerprinting
any collection (library, directory, dataset).

This workflow follows the standard 3-phase Agent-Workflow execution pattern:
- Phase 0: Preflight & Audit
- Phase 1: Plan Derivation & Analysis
- Phase 2: Remediation & Execution

Workflow ID: DEDUP-FP-WORKFLOW-v1.0
Database: Agent-Workflows (259e7361-6c27-8192-ae2e-e6d54b4198e1)

Usage:
    from shared_core.workflows.deduplication_fingerprint_workflow import (
        DeduplicationWorkflow,
        WorkflowConfig,
        DataSourceType
    )

    # Configure for Eagle library
    config = WorkflowConfig(
        source_type=DataSourceType.EAGLE_LIBRARY,
        source_path="/Volumes/VIBES/Music Library-2.library",
        fingerprint_method="audio_hash",
        similarity_threshold=0.75
    )

    workflow = DeduplicationWorkflow(config)
    result = workflow.execute(dry_run=True)
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, TypeVar, Generic

# Configure logging
logger = logging.getLogger(__name__)

# Import unified state manager
try:
    from shared_core.workflows.workflow_state_manager import WorkflowStateManager
    STATE_MANAGER_AVAILABLE = True
except ImportError:
    STATE_MANAGER_AVAILABLE = False
    logger.warning("WorkflowStateManager not available - unified state tracking disabled")


# ============================================================================
# ENUMS & TYPE DEFINITIONS
# ============================================================================

class DataSourceType(Enum):
    """Supported data source types for deduplication."""
    EAGLE_LIBRARY = "eagle_library"
    FILESYSTEM_DIRECTORY = "filesystem_directory"
    NOTION_DATABASE = "notion_database"
    GENERIC_DATASET = "generic_dataset"


class FingerprintMethod(Enum):
    """Available fingerprinting methods."""
    FILE_HASH_SHA256 = "sha256"           # Standard file hash
    FILE_HASH_MD5 = "md5"                 # Faster but less secure
    AUDIO_CONTENT_HASH = "audio_hash"     # Audio-specific (ignores metadata)
    FUZZY_NAME_MATCH = "fuzzy_name"       # String similarity on names
    COMPOSITE = "composite"               # Multiple methods combined


class MatchConfidence(Enum):
    """Confidence levels for duplicate matches."""
    EXACT = "exact"           # 100% match (fingerprint or exact string)
    HIGH = "high"             # 90%+ match
    MEDIUM = "medium"         # 75-90% match
    LOW = "low"               # 60-75% match
    UNCERTAIN = "uncertain"   # Below threshold but notable


class WorkflowPhase(Enum):
    """Standard 3-phase workflow execution."""
    PREFLIGHT = "phase_0_preflight"
    ANALYSIS = "phase_1_analysis"
    REMEDIATION = "phase_2_remediation"


# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class WorkflowConfig:
    """Configuration for deduplication workflow."""
    # Source configuration
    source_type: DataSourceType
    source_path: str
    source_name: str = ""

    # Fingerprinting configuration
    fingerprint_method: FingerprintMethod = FingerprintMethod.COMPOSITE
    similarity_threshold: float = 0.75

    # Dynamic thresholds based on content length
    short_content_threshold: float = 0.85   # For items <= 5 chars
    medium_content_threshold: float = 0.75  # For items 6-10 chars
    long_content_threshold: float = 0.65    # For items > 10 chars

    # Output configuration
    output_dir: str = ""
    generate_report: bool = True
    report_format: str = "markdown"

    # Execution options
    batch_size: int = 100
    max_workers: int = 4
    enable_caching: bool = True

    # Cleanup options
    cleanup_enabled: bool = False
    cleanup_method: str = "trash"  # "trash", "delete", "archive"
    preserve_best_quality: bool = True
    merge_metadata: bool = True

    def __post_init__(self):
        if not self.source_name:
            self.source_name = Path(self.source_path).name
        if not self.output_dir:
            self.output_dir = str(Path(self.source_path).parent / "dedup_reports")


@dataclass
class DataItem:
    """Generic data item that can be deduplicated."""
    id: str
    name: str
    path: str
    size: int = 0
    created_at: Optional[datetime] = None
    modified_at: Optional[datetime] = None
    fingerprint: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)
    quality_score: float = 0.0

    def __hash__(self):
        return hash(self.id)

    def __eq__(self, other):
        if isinstance(other, DataItem):
            return self.id == other.id
        return False


@dataclass
class DuplicateGroup:
    """A group of duplicate items."""
    group_id: str
    items: List[DataItem]
    match_confidence: MatchConfidence
    match_method: str
    best_item: Optional[DataItem] = None

    @property
    def duplicate_count(self) -> int:
        return len(self.items) - 1 if self.items else 0

    @property
    def total_size(self) -> int:
        return sum(item.size for item in self.items)

    @property
    def recoverable_size(self) -> int:
        if self.best_item:
            return self.total_size - self.best_item.size
        return 0


@dataclass
class WorkflowResult:
    """Result of workflow execution."""
    workflow_id: str
    source_type: DataSourceType
    source_path: str

    # Timing
    started_at: datetime
    completed_at: Optional[datetime] = None
    duration_seconds: float = 0.0

    # Statistics
    total_items_scanned: int = 0
    duplicate_groups_found: int = 0
    total_duplicates: int = 0
    recoverable_bytes: int = 0

    # Results
    duplicate_groups: List[DuplicateGroup] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    # Execution
    phase_completed: WorkflowPhase = WorkflowPhase.PREFLIGHT
    dry_run: bool = True
    items_cleaned: int = 0

    # Report
    report_path: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert result to dictionary for serialization."""
        return {
            "workflow_id": self.workflow_id,
            "source_type": self.source_type.value,
            "source_path": self.source_path,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_seconds": self.duration_seconds,
            "total_items_scanned": self.total_items_scanned,
            "duplicate_groups_found": self.duplicate_groups_found,
            "total_duplicates": self.total_duplicates,
            "recoverable_bytes": self.recoverable_bytes,
            "phase_completed": self.phase_completed.value,
            "dry_run": self.dry_run,
            "items_cleaned": self.items_cleaned,
            "report_path": self.report_path,
            "errors": self.errors,
            "warnings": self.warnings
        }


# ============================================================================
# ABSTRACT BASE CLASSES
# ============================================================================

class DataSourceAdapter(ABC):
    """Abstract adapter for different data sources."""

    @abstractmethod
    def connect(self) -> bool:
        """Establish connection to data source."""
        pass

    @abstractmethod
    def fetch_items(self, batch_size: int = 100) -> List[DataItem]:
        """Fetch items from data source."""
        pass

    @abstractmethod
    def get_item_content(self, item: DataItem) -> bytes:
        """Get raw content of item for fingerprinting."""
        pass

    @abstractmethod
    def update_item(self, item: DataItem, updates: Dict[str, Any]) -> bool:
        """Update item metadata."""
        pass

    @abstractmethod
    def delete_item(self, item: DataItem, method: str = "trash") -> bool:
        """Delete or archive item."""
        pass


class FingerprintStrategy(ABC):
    """Abstract strategy for generating fingerprints."""

    @abstractmethod
    def compute(self, item: DataItem, content: Optional[bytes] = None) -> str:
        """Compute fingerprint for item."""
        pass

    @abstractmethod
    def compare(self, fp1: str, fp2: str) -> float:
        """Compare two fingerprints, return similarity score 0.0-1.0."""
        pass


class SimilarityMatcher(ABC):
    """Abstract matcher for finding similar items."""

    @abstractmethod
    def find_matches(
        self,
        items: List[DataItem],
        threshold: float
    ) -> List[DuplicateGroup]:
        """Find groups of similar/duplicate items."""
        pass


# ============================================================================
# CONCRETE IMPLEMENTATIONS
# ============================================================================

class SHA256FingerprintStrategy(FingerprintStrategy):
    """SHA256 hash-based fingerprinting."""

    def compute(self, item: DataItem, content: Optional[bytes] = None) -> str:
        if content:
            return hashlib.sha256(content).hexdigest()
        if item.path and Path(item.path).exists():
            with open(item.path, 'rb') as f:
                return hashlib.sha256(f.read()).hexdigest()
        return ""

    def compare(self, fp1: str, fp2: str) -> float:
        return 1.0 if fp1 and fp2 and fp1 == fp2 else 0.0


class FuzzyNameMatcher(SimilarityMatcher):
    """Fuzzy string matching for names/titles."""

    def __init__(self, config: WorkflowConfig):
        self.config = config
        self._rapidfuzz_available = False
        try:
            from rapidfuzz import fuzz
            self._fuzz = fuzz
            self._rapidfuzz_available = True
        except ImportError:
            from difflib import SequenceMatcher
            self._sequence_matcher = SequenceMatcher

    def _normalize(self, text: str) -> str:
        """Normalize text for comparison."""
        text = text.lower()
        text = re.sub(r'[^a-z0-9\s]', '', text)
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    def _get_dynamic_threshold(self, text: str) -> float:
        """Get threshold based on text length."""
        length = len(self._normalize(text))
        if length <= 5:
            return self.config.short_content_threshold
        elif length <= 10:
            return self.config.medium_content_threshold
        else:
            return self.config.long_content_threshold

    def _compute_similarity(self, s1: str, s2: str) -> Tuple[float, str]:
        """Compute similarity score between two strings."""
        n1 = self._normalize(s1)
        n2 = self._normalize(s2)

        if n1 == n2:
            return 1.0, "exact"

        if self._rapidfuzz_available:
            ratio = self._fuzz.ratio(n1, n2) / 100.0
            partial = self._fuzz.partial_ratio(n1, n2) / 100.0
            token_sort = self._fuzz.token_sort_ratio(n1, n2) / 100.0
            token_set = self._fuzz.token_set_ratio(n1, n2) / 100.0

            # Weighted combination
            weighted = (ratio * 0.2 + partial * 0.3 +
                       token_sort * 0.3 + token_set * 0.2)
            return weighted, "rapidfuzz_weighted"
        else:
            ratio = self._sequence_matcher(None, n1, n2).ratio()
            return ratio, "sequence_matcher"

    def find_matches(
        self,
        items: List[DataItem],
        threshold: float
    ) -> List[DuplicateGroup]:
        """Find groups of similar items based on name matching."""
        groups: List[DuplicateGroup] = []
        processed: Set[str] = set()

        for i, item1 in enumerate(items):
            if item1.id in processed:
                continue

            # Use dynamic threshold for this item
            item_threshold = self._get_dynamic_threshold(item1.name)
            effective_threshold = max(threshold, item_threshold)

            group_items = [item1]
            processed.add(item1.id)

            for j, item2 in enumerate(items[i+1:], start=i+1):
                if item2.id in processed:
                    continue

                score, method = self._compute_similarity(item1.name, item2.name)

                if score >= effective_threshold:
                    group_items.append(item2)
                    processed.add(item2.id)

            if len(group_items) > 1:
                # Determine best item (highest quality score)
                best = max(group_items, key=lambda x: x.quality_score)

                # Determine confidence level
                if score >= 0.95:
                    confidence = MatchConfidence.EXACT
                elif score >= 0.85:
                    confidence = MatchConfidence.HIGH
                elif score >= 0.75:
                    confidence = MatchConfidence.MEDIUM
                else:
                    confidence = MatchConfidence.LOW

                groups.append(DuplicateGroup(
                    group_id=f"group_{len(groups)+1}",
                    items=group_items,
                    match_confidence=confidence,
                    match_method="fuzzy_name",
                    best_item=best
                ))

        return groups


# ============================================================================
# MAIN WORKFLOW CLASS
# ============================================================================

class DeduplicationWorkflow:
    """
    Main workflow orchestrator for deduplication and fingerprinting.

    Follows the 3-phase Agent-Workflow pattern:
    - Phase 0: Preflight - Validate configuration and access
    - Phase 1: Analysis - Scan, fingerprint, and identify duplicates
    - Phase 2: Remediation - Execute cleanup actions
    """

    def __init__(
        self,
        config: WorkflowConfig,
        adapter: Optional[DataSourceAdapter] = None,
        fingerprint_strategy: Optional[FingerprintStrategy] = None,
        matcher: Optional[SimilarityMatcher] = None,
        state_manager: Optional[WorkflowStateManager] = None
    ):
        self.config = config
        self.adapter = adapter
        self.fingerprint_strategy = fingerprint_strategy or SHA256FingerprintStrategy()
        self.matcher = matcher or FuzzyNameMatcher(config)

        self.workflow_id = f"DEDUP-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
        self.result: Optional[WorkflowResult] = None
        
        # Initialize unified state manager (mandatory integration)
        if state_manager is None and STATE_MANAGER_AVAILABLE:
            try:
                self.state_manager = WorkflowStateManager()
            except Exception as e:
                logger.warning(f"Failed to initialize WorkflowStateManager: {e}")
                self.state_manager = None
        else:
            self.state_manager = state_manager

        logger.info(f"Initialized DeduplicationWorkflow: {self.workflow_id}")

    def execute(self, dry_run: bool = True) -> WorkflowResult:
        """Execute the full workflow."""
        self.result = WorkflowResult(
            workflow_id=self.workflow_id,
            source_type=self.config.source_type,
            source_path=self.config.source_path,
            started_at=datetime.now(timezone.utc),
            dry_run=dry_run
        )
        
        # Start deduplication step in unified state manager
        if self.state_manager:
            try:
                self.state_manager.start_step("deduplication")
            except Exception as e:
                logger.warning(f"Failed to start deduplication step in state manager: {e}")

        try:
            # Phase 0: Preflight
            logger.info(f"[{self.workflow_id}] Phase 0: Preflight & Audit")
            if not self._phase_preflight():
                self.result.phase_completed = WorkflowPhase.PREFLIGHT
                return self.result

            # Phase 1: Analysis
            logger.info(f"[{self.workflow_id}] Phase 1: Analysis & Fingerprinting")
            if not self._phase_analysis():
                self.result.phase_completed = WorkflowPhase.ANALYSIS
                return self.result

            # Phase 2: Remediation (only if not dry run)
            logger.info(f"[{self.workflow_id}] Phase 2: Remediation")
            if not dry_run and self.config.cleanup_enabled:
                self._phase_remediation()
            else:
                logger.info(f"[{self.workflow_id}] Dry run mode - skipping remediation")

            self.result.phase_completed = WorkflowPhase.REMEDIATION

        except Exception as e:
            logger.error(f"[{self.workflow_id}] Workflow error: {e}")
            self.result.errors.append(str(e))

        finally:
            self.result.completed_at = datetime.now(timezone.utc)
            self.result.duration_seconds = (
                self.result.completed_at - self.result.started_at
            ).total_seconds()

            # Persist result to unified state manager
            if self.state_manager:
                try:
                    stats = {
                        "total_items_scanned": self.result.total_items_scanned,
                        "duplicate_groups_found": self.result.duplicate_groups_found,
                        "total_duplicates": self.result.total_duplicates,
                        "recoverable_bytes": self.result.recoverable_bytes,
                        "items_cleaned": self.result.items_cleaned,
                        "phase_completed": self.result.phase_completed.value,
                        "dry_run": self.result.dry_run,
                        "duration_seconds": self.result.duration_seconds
                    }
                    if self.result.errors:
                        self.state_manager.fail_step("deduplication", "; ".join(self.result.errors), stats)
                    else:
                        self.state_manager.complete_step("deduplication", stats)
                except Exception as e:
                    logger.warning(f"Failed to persist result to unified state manager: {e}")

            if self.config.generate_report:
                self._generate_report()

        return self.result

    def _phase_preflight(self) -> bool:
        """Phase 0: Validate configuration and connectivity."""
        logger.info("  Validating configuration...")

        # Validate source path
        if self.config.source_type == DataSourceType.FILESYSTEM_DIRECTORY:
            if not Path(self.config.source_path).exists():
                self.result.errors.append(f"Source path does not exist: {self.config.source_path}")
                return False

        # Validate output directory
        output_path = Path(self.config.output_dir)
        if not output_path.exists():
            try:
                output_path.mkdir(parents=True, exist_ok=True)
                logger.info(f"  Created output directory: {output_path}")
            except Exception as e:
                self.result.errors.append(f"Cannot create output directory: {e}")
                return False

        # Validate adapter connection if provided
        if self.adapter:
            if not self.adapter.connect():
                self.result.errors.append("Failed to connect to data source")
                return False

        logger.info("  ✓ Preflight checks passed")
        return True

    def _phase_analysis(self) -> bool:
        """Phase 1: Scan, fingerprint, and identify duplicates."""
        logger.info("  Scanning data source...")

        items: List[DataItem] = []

        # Use adapter if available, otherwise use filesystem scan
        if self.adapter:
            items = self.adapter.fetch_items(batch_size=self.config.batch_size)
        elif self.config.source_type == DataSourceType.FILESYSTEM_DIRECTORY:
            items = self._scan_filesystem()
        else:
            self.result.errors.append(f"No adapter for source type: {self.config.source_type}")
            return False

        self.result.total_items_scanned = len(items)
        logger.info(f"  Found {len(items)} items to analyze")

        if not items:
            self.result.warnings.append("No items found to analyze")
            return True

        # Compute fingerprints
        logger.info("  Computing fingerprints...")
        for item in items:
            if not item.fingerprint:
                try:
                    item.fingerprint = self.fingerprint_strategy.compute(item)
                except Exception as e:
                    logger.warning(f"  Failed to fingerprint {item.name}: {e}")

        # Find duplicates
        logger.info("  Finding duplicates...")
        duplicate_groups = self.matcher.find_matches(
            items,
            self.config.similarity_threshold
        )

        self.result.duplicate_groups = duplicate_groups
        self.result.duplicate_groups_found = len(duplicate_groups)
        self.result.total_duplicates = sum(g.duplicate_count for g in duplicate_groups)
        self.result.recoverable_bytes = sum(g.recoverable_size for g in duplicate_groups)

        logger.info(f"  ✓ Found {len(duplicate_groups)} duplicate groups")
        logger.info(f"  ✓ Total duplicates: {self.result.total_duplicates}")
        logger.info(f"  ✓ Recoverable: {self.result.recoverable_bytes / (1024*1024):.2f} MB")

        return True

    def _phase_remediation(self) -> bool:
        """Phase 2: Execute cleanup actions on duplicates."""
        if not self.adapter:
            self.result.warnings.append("No adapter - cannot execute remediation")
            return False

        logger.info("  Executing cleanup...")

        cleaned = 0
        for group in self.result.duplicate_groups:
            if not group.best_item:
                continue

            # Merge metadata to best item if configured
            if self.config.merge_metadata:
                merged_tags = set(group.best_item.tags)
                for item in group.items:
                    if item != group.best_item:
                        merged_tags.update(item.tags)

                self.adapter.update_item(
                    group.best_item,
                    {"tags": list(merged_tags)}
                )

            # Delete duplicates (keeping best)
            for item in group.items:
                if item != group.best_item:
                    if self.adapter.delete_item(item, self.config.cleanup_method):
                        cleaned += 1

        self.result.items_cleaned = cleaned
        logger.info(f"  ✓ Cleaned {cleaned} duplicate items")

        return True

    def _scan_filesystem(self) -> List[DataItem]:
        """Scan filesystem directory for items."""
        items = []
        source_path = Path(self.config.source_path)

        for file_path in source_path.rglob("*"):
            if file_path.is_file():
                stat = file_path.stat()
                items.append(DataItem(
                    id=str(file_path),
                    name=file_path.stem,
                    path=str(file_path),
                    size=stat.st_size,
                    created_at=datetime.fromtimestamp(stat.st_ctime, tz=timezone.utc),
                    modified_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
                    metadata={"extension": file_path.suffix}
                ))

        return items

    def _generate_report(self) -> None:
        """Generate workflow report."""
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        report_name = f"dedup_report_{timestamp}.md"
        report_path = Path(self.config.output_dir) / report_name

        report_lines = [
            f"# Deduplication Workflow Report",
            f"",
            f"**Workflow ID:** {self.workflow_id}",
            f"**Generated:** {datetime.now(timezone.utc).isoformat()}",
            f"**Source:** {self.config.source_name}",
            f"**Mode:** {'Dry Run' if self.result.dry_run else 'Live'}",
            f"",
            f"---",
            f"",
            f"## Summary",
            f"",
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| Items Scanned | {self.result.total_items_scanned} |",
            f"| Duplicate Groups | {self.result.duplicate_groups_found} |",
            f"| Total Duplicates | {self.result.total_duplicates} |",
            f"| Recoverable Space | {self.result.recoverable_bytes / (1024*1024):.2f} MB |",
            f"| Duration | {self.result.duration_seconds:.2f}s |",
            f"| Phase Completed | {self.result.phase_completed.value} |",
            f"",
        ]

        if self.result.duplicate_groups:
            report_lines.extend([
                f"---",
                f"",
                f"## Duplicate Groups",
                f"",
            ])

            for group in self.result.duplicate_groups:
                report_lines.extend([
                    f"### {group.group_id}: \"{group.items[0].name}\"",
                    f"",
                    f"- **Confidence:** {group.match_confidence.value}",
                    f"- **Method:** {group.match_method}",
                    f"- **Items:** {len(group.items)}",
                    f"- **Recoverable:** {group.recoverable_size / (1024*1024):.2f} MB",
                    f"",
                    f"| Item | Size | Quality | Keep |",
                    f"|------|------|---------|------|",
                ])

                for item in group.items:
                    is_best = "✓" if item == group.best_item else ""
                    report_lines.append(
                        f"| {item.name} | {item.size / (1024*1024):.2f} MB | "
                        f"{item.quality_score:.2f} | {is_best} |"
                    )

                report_lines.append("")

        if self.result.errors:
            report_lines.extend([
                f"---",
                f"",
                f"## Errors",
                f"",
            ])
            for error in self.result.errors:
                report_lines.append(f"- {error}")
            report_lines.append("")

        report_lines.extend([
            f"---",
            f"",
            f"*Report generated by DeduplicationWorkflow v1.0*",
        ])

        try:
            report_path.write_text("\n".join(report_lines), encoding="utf-8")
            self.result.report_path = str(report_path)
            logger.info(f"  ✓ Report saved: {report_path}")
        except Exception as e:
            logger.error(f"  Failed to save report: {e}")


# ============================================================================
# NOTION INTEGRATION
# ============================================================================

def create_or_update_notion_workflow(
    workflow_name: str = "Deduplication & Fingerprinting Workflow",
    workflow_id: str = "DEDUP-FP-WORKFLOW-v1.0"
) -> Optional[str]:
    """
    Create or update the Agent-Workflow entry in Notion.

    Returns the page ID if successful, None otherwise.
    """
    try:
        # Import Notion client
        import os
        import sys
        sys.path.insert(0, '/Users/brianhellemn/Projects/github-production')

        from notion_client import Client

        # Get token using the canonical token manager
        token = None
        try:
            from shared_core.notion.token_manager import get_notion_token
            token = get_notion_token()
        except ImportError:
            pass

        if not token:
            # Fallback to environment variables
            token = (
                os.getenv("NOTION_TOKEN") or
                os.getenv("NOTION_API_TOKEN") or
                os.getenv("VV_AUTOMATIONS_WS_TOKEN")
            )

        if not token:
            logger.error("No Notion token found - configure via token_manager or environment")
            return None

        client = Client(auth=token)

        # Agent-Workflows database ID
        WORKFLOWS_DB_ID = "259e73616c278192ae2ee6d54b4198e1"

        # Check if workflow already exists (title property is "Workflow" not "Name")
        existing = client.databases.query(
            database_id=WORKFLOWS_DB_ID,
            filter={
                "property": "Workflow",
                "title": {"equals": workflow_name}
            }
        )

        # Build properties matching actual Agent-Workflows database schema
        workflow_properties = {
            "Workflow": {
                "title": [{"text": {"content": workflow_name}}]
            },
            "Template ID": {
                "rich_text": [{"text": {"content": workflow_id}}]
            },
            "Description": {
                "rich_text": [{"text": {"content":
                    "Generalized workflow for deduplicating and fingerprinting "
                    "collections (libraries, directories, datasets). Supports "
                    "Eagle libraries, filesystem directories, and Notion databases. "
                    "Uses multi-algorithm fuzzy matching with dynamic thresholds."
                }}]
            },
            "Status": {
                "status": {"name": "Running"}
            },
            "Is Active": {
                "checkbox": True
            },
            "Type": {
                "select": {"name": "Automation"}
            },
            "Domain": {
                "select": {"name": "Data Management"}
            },
            "Tags": {
                "multi_select": [
                    {"name": "deduplication"},
                    {"name": "fingerprinting"},
                    {"name": "eagle"},
                    {"name": "automation"}
                ]
            },
            "Primary-Agent": {
                "rich_text": [{"text": {"content": "Claude Code Agent, Codex MM1 Agent"}}]
            },
            "Step #1": {
                "rich_text": [{"text": {"content": "Phase 0: Preflight - Validate config and connectivity"}}]
            },
            "Step #2": {
                "rich_text": [{"text": {"content": "Phase 1: Analysis - Scan, fingerprint, identify duplicates"}}]
            },
            "Step #3": {
                "rich_text": [{"text": {"content": "Phase 2: Remediation - Execute cleanup (if enabled)"}}]
            },
            "Workflow Requirements": {
                "rich_text": [{"text": {"content": "rapidfuzz>=3.0.0, mutagen>=1.47.0, notion-client>=2.2.1"}}]
            },
            "Python-Variant": {
                "rich_text": [{"text": {"content": "shared_core/workflows/deduplication_fingerprint_workflow.py"}}]
            },
            "Locations": {
                "rich_text": [{"text": {"content": "/Users/brianhellemn/Projects/github-production/shared_core/workflows/"}}]
            }
        }

        if existing.get("results"):
            # Update existing
            page_id = existing["results"][0]["id"]
            client.pages.update(page_id=page_id, properties=workflow_properties)
            logger.info(f"Updated existing workflow: {page_id}")
            return page_id
        else:
            # Create new
            response = client.pages.create(
                parent={"database_id": WORKFLOWS_DB_ID},
                properties=workflow_properties
            )
            page_id = response.get("id")
            logger.info(f"Created new workflow: {page_id}")
            return page_id

    except Exception as e:
        logger.error(f"Failed to create/update Notion workflow: {e}")
        return None


# ============================================================================
# CLI INTERFACE
# ============================================================================

def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Deduplication & Fingerprinting Workflow"
    )
    parser.add_argument(
        "--source", "-s", required=True,
        help="Path to source (directory or library)"
    )
    parser.add_argument(
        "--type", "-t",
        choices=["filesystem", "eagle", "notion"],
        default="filesystem",
        help="Source type"
    )
    parser.add_argument(
        "--threshold", type=float, default=0.75,
        help="Similarity threshold (0.0-1.0)"
    )
    parser.add_argument(
        "--live", action="store_true",
        help="Execute in live mode (not dry run)"
    )
    parser.add_argument(
        "--cleanup", action="store_true",
        help="Enable cleanup of duplicates"
    )
    parser.add_argument(
        "--update-notion", action="store_true",
        help="Create/update Notion workflow entry"
    )
    parser.add_argument(
        "--output", "-o",
        help="Output directory for reports"
    )

    args = parser.parse_args()

    # Update Notion if requested
    if args.update_notion:
        page_id = create_or_update_notion_workflow()
        if page_id:
            print(f"✓ Notion workflow updated: {page_id}")
        else:
            print("✗ Failed to update Notion workflow")
        return

    # Map source type
    source_type_map = {
        "filesystem": DataSourceType.FILESYSTEM_DIRECTORY,
        "eagle": DataSourceType.EAGLE_LIBRARY,
        "notion": DataSourceType.NOTION_DATABASE
    }

    config = WorkflowConfig(
        source_type=source_type_map[args.type],
        source_path=args.source,
        similarity_threshold=args.threshold,
        cleanup_enabled=args.cleanup,
        output_dir=args.output or ""
    )

    workflow = DeduplicationWorkflow(config)
    result = workflow.execute(dry_run=not args.live)

    print(f"\n{'='*60}")
    print(f"Workflow Complete: {result.workflow_id}")
    print(f"{'='*60}")
    print(f"Items Scanned: {result.total_items_scanned}")
    print(f"Duplicate Groups: {result.duplicate_groups_found}")
    print(f"Total Duplicates: {result.total_duplicates}")
    print(f"Recoverable: {result.recoverable_bytes / (1024*1024):.2f} MB")
    print(f"Duration: {result.duration_seconds:.2f}s")
    if result.report_path:
        print(f"Report: {result.report_path}")


if __name__ == "__main__":
    main()

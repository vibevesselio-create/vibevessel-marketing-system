"""
Shared Core Workflows Module
============================

Contains modular, reusable Agent-Workflow implementations.

Available Workflows:
- DeduplicationWorkflow: Generalized deduplication and fingerprinting
"""

from .deduplication_fingerprint_workflow import (
    DeduplicationWorkflow,
    WorkflowConfig,
    WorkflowResult,
    DataSourceType,
    FingerprintMethod,
    MatchConfidence,
    WorkflowPhase,
    DataItem,
    DuplicateGroup,
    DataSourceAdapter,
    FingerprintStrategy,
    SimilarityMatcher,
    create_or_update_notion_workflow,
)

from .workflow_state_manager import WorkflowStateManager

__all__ = [
    "DeduplicationWorkflow",
    "WorkflowConfig",
    "WorkflowResult",
    "DataSourceType",
    "FingerprintMethod",
    "MatchConfidence",
    "WorkflowPhase",
    "DataItem",
    "DuplicateGroup",
    "DataSourceAdapter",
    "FingerprintStrategy",
    "SimilarityMatcher",
    "create_or_update_notion_workflow",
    "WorkflowStateManager",
]

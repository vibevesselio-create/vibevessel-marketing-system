"""
Music Workflow Package - Modular Music Processing System

This package provides a modular architecture for music download, processing,
deduplication, and integration workflows. It is designed to replace the monolithic
soundcloud_download_prod_merge-2.py script with maintainable, testable components.

Package Structure:
- config/: Configuration management and settings
- core/: Core workflow logic (downloader, processor, organizer)
- integrations/: External service integrations (Notion, Eagle, Spotify, SoundCloud)
- deduplication/: Audio fingerprinting and duplicate detection
- metadata/: Metadata extraction, enrichment, and embedding
- cli/: Command-line interface
- utils/: Shared utilities (logging, errors, file operations)
- tests/: Unit and integration tests

Created: 2026-01-09
Version: 0.1.0
"""

__version__ = "0.2.0"
__author__ = "Seren Media Automation System"

# Main entry points for feature-flag-aware workflow execution
from music_workflow.dispatcher import (
    WorkflowDispatcher,
    dispatch_workflow,
    get_active_workflow,
)

from music_workflow.config import get_settings, Settings, FeatureFlags

__all__ = [
    # Dispatcher (feature-flag-aware entry points)
    "WorkflowDispatcher",
    "dispatch_workflow",
    "get_active_workflow",
    # Configuration
    "get_settings",
    "Settings",
    "FeatureFlags",
]

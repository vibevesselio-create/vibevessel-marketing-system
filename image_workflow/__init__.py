"""
Image Workflow - Multi-Environment Image Synchronization
=========================================================

A comprehensive image management system that synchronizes images across:
- Adobe Lightroom Classic (local catalog + cloud sync)
- Google Drive (cloud storage + backup)
- Eagle Library (local DAM with metadata)
- Notion Photo Library (metadata database + workflow integration)

Architecture aligned with music_workflow patterns for consistency.

Usage:
    from image_workflow import ImageWorkflow, WorkflowOptions

    workflow = ImageWorkflow()
    result = workflow.sync_from_lightroom(catalog_path)
"""

from image_workflow.core.workflow import ImageWorkflow, WorkflowOptions
from image_workflow.core.models import ImageInfo, ImageStatus, ImageMatch

__version__ = "1.0.0"
__all__ = [
    "ImageWorkflow",
    "WorkflowOptions",
    "ImageInfo",
    "ImageStatus",
    "ImageMatch",
]

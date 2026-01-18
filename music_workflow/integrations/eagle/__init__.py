"""Eagle library integration for music asset management.

This module provides integration with Eagle library for importing
and managing audio files as organized assets.
"""

from music_workflow.integrations.eagle.client import (
    EagleClient,
    EagleItem,
    get_eagle_client,
)

__all__ = [
    "EagleClient",
    "EagleItem",
    "get_eagle_client",
]

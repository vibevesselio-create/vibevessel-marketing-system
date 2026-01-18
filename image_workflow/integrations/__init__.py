"""Integration modules for external image sources.

Provides readers and writers for:
- Adobe Lightroom Classic catalogs (.lrcat SQLite databases)
- Eagle library databases
- Google Drive image storage
- Notion Photo Library database
"""

from image_workflow.integrations.eagle import (
    EagleImage,
    EagleLibraryReader,
)
from image_workflow.integrations.lightroom import (
    LightroomCatalogReader,
    LightroomImage,
)

__all__ = [
    # Eagle
    "EagleImage",
    "EagleLibraryReader",
    # Lightroom
    "LightroomCatalogReader",
    "LightroomImage",
]

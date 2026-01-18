#!/usr/bin/env python3
"""
Filesystem Source Adapter
=========================

Discovers files from local filesystem and extracts metadata.
"""

from pathlib import Path
from typing import Dict, List, Optional, Any
import logging
import os

logger = logging.getLogger(__name__)


class FilesystemAdapter:
    """Filesystem source adapter for sync orchestrator."""
    
    def __init__(self, supported_extensions: Optional[List[str]] = None):
        """
        Initialize filesystem adapter.
        
        Args:
            supported_extensions: List of supported file extensions (if None, all files)
        """
        self.supported_extensions = supported_extensions
    
    def discover_items(
        self,
        source_path: Optional[Path],
        item_type: str
    ) -> List[Dict[str, Any]]:
        """
        Discover items from filesystem.
        
        Args:
            source_path: Source directory path
            item_type: Item type to discover
            
        Returns:
            List of item dictionaries
        """
        if not source_path:
            logger.warning("No source path provided")
            return []
        
        source = Path(source_path)
        if not source.exists():
            logger.warning(f"Source path does not exist: {source_path}")
            return []
        
        if not source.is_dir():
            # Single file
            return [self._file_to_item(source, item_type)]
        
        # Directory - discover all files
        items = []
        for file_path in source.rglob("*"):
            if file_path.is_file():
                if self._should_include_file(file_path):
                    item = self._file_to_item(file_path, item_type)
                    if item:
                        items.append(item)
        
        return items
    
    def _should_include_file(self, file_path: Path) -> bool:
        """Check if file should be included."""
        if self.supported_extensions:
            return file_path.suffix.lower() in [ext.lower() for ext in self.supported_extensions]
        return True
    
    def _file_to_item(self, file_path: Path, item_type: str) -> Optional[Dict[str, Any]]:
        """Convert file to item dictionary."""
        try:
            stat = file_path.stat()
            
            return {
                "id": str(file_path),
                "title": file_path.stem,
                "name": file_path.name,
                "file_path": str(file_path),
                "path": str(file_path),
                "source": "filesystem",
                "item_type": item_type,
                "metadata": {
                    "size": stat.st_size,
                    "mtime": stat.st_mtime,
                    "extension": file_path.suffix,
                }
            }
        except Exception as e:
            logger.warning(f"Failed to convert file {file_path} to item: {e}")
            return None
    
    def get_items(self, source_path: Optional[Path] = None) -> List[Dict[str, Any]]:
        """Get all items from filesystem (alias for discover_items)."""
        return self.discover_items(source_path, "")

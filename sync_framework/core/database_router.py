#!/usr/bin/env python3
"""
Database Router
===============

Routes items to correct Notion database based on item type, source folder, and category.
Uses item-types manager for lookups. Supports multi-database routing.
"""

import re
from pathlib import Path
from typing import Dict, List, Optional, Any
import logging

try:
    from sync_config.item_types_manager import get_item_types_manager
    ITEM_TYPES_AVAILABLE = True
except ImportError:
    ITEM_TYPES_AVAILABLE = False

logger = logging.getLogger(__name__)


class DatabaseRouter:
    """Routes items to appropriate Notion databases."""
    
    def __init__(self):
        """Initialize the database router."""
        self.item_types_manager = None
        if ITEM_TYPES_AVAILABLE:
            try:
                self.item_types_manager = get_item_types_manager()
            except Exception as e:
                logger.warning(f"Failed to initialize item-types manager: {e}")
        
        # Pattern-based routing rules (can be extended)
        self.path_patterns: Dict[str, str] = {}
        self._load_path_patterns()
    
    def _load_path_patterns(self) -> None:
        """Load path pattern routing rules."""
        # Common patterns
        self.path_patterns = {
            r".*\/Music\/.*": "Music Track",
            r".*\/Playlists\/.*": "Music Playlist",
            r".*\/Photos?\/.*": "PNG Format Image",  # Will try image types
            r".*\/Images?\/.*": "PNG Format Image",
            r".*\/Videos?\/.*": "Video Clip",
            r".*\/Documents?\/.*": "Document",
            r".*\/Scripts?\/.*": "Python Script",
        }
    
    def route_item(
        self,
        item: Dict[str, Any],
        item_type: str,
        source_path: Optional[str] = None,
        category: Optional[str] = None
    ) -> List[str]:
        """
        Return list of target database IDs for item.
        
        Args:
            item: Item dictionary
            item_type: Type of item
            source_path: Optional source file/folder path
            category: Optional category name
            
        Returns:
            List of target database IDs (may be empty)
        """
        database_ids = []
        
        # Priority 1: Item-type Default-Synchronization-Database
        if self.item_types_manager:
            db_id = self.item_types_manager.get_database_for_item_type(item_type)
            if db_id:
                database_ids.append(db_id)
                logger.debug(f"Routed '{item_type}' to database {db_id} via item-type")
        
        # Priority 2: Category-based routing
        if category and self.item_types_manager:
            item_types = self.item_types_manager.get_item_types_by_category(category)
            for it_type in item_types:
                db_id = self.item_types_manager.get_database_for_item_type(it_type)
                if db_id and db_id not in database_ids:
                    database_ids.append(db_id)
                    logger.debug(f"Routed via category '{category}' to database {db_id}")
        
        # Priority 3: Source path pattern matching
        if source_path:
            path_db_ids = self._route_by_path_pattern(source_path, item_type)
            for db_id in path_db_ids:
                if db_id not in database_ids:
                    database_ids.append(db_id)
        
        # Priority 4: Related databases from item-type
        if self.item_types_manager:
            related_dbs = self.item_types_manager.get_related_databases(item_type)
            for db_id in related_dbs:
                if db_id not in database_ids:
                    database_ids.append(db_id)
                    logger.debug(f"Added related database {db_id} for '{item_type}'")
        
        return database_ids
    
    def _route_by_path_pattern(
        self,
        source_path: str,
        item_type: str
    ) -> List[str]:
        """Route based on source path patterns."""
        database_ids = []
        
        path_lower = source_path.lower()
        
        # Check against pattern rules
        for pattern, pattern_item_type in self.path_patterns.items():
            if re.match(pattern, path_lower, re.IGNORECASE):
                if self.item_types_manager:
                    db_id = self.item_types_manager.get_database_for_item_type(pattern_item_type)
                    if db_id:
                        database_ids.append(db_id)
                        logger.debug(f"Routed via path pattern '{pattern}' to database {db_id}")
                break
        
        # File extension-based routing
        path_obj = Path(source_path)
        ext = path_obj.suffix.lower()
        
        ext_to_type = {
            ".mp3": "Music Track",
            ".m4a": "Music Track",
            ".aiff": "Music Track",
            ".wav": "Music Track",
            ".flac": "Music Track",
            ".png": "PNG Format Image",
            ".jpg": "JPEG Format Image",
            ".jpeg": "JPEG Format Image",
            ".tiff": "TIFF Format Image",
            ".tif": "TIFF Format Image",
            ".mp4": "Video Clip",
            ".mov": "Video Clip",
            ".avi": "Video Clip",
            ".mkv": "Video Clip",
            ".py": "Python Script",
            ".js": "JavaScript",
            ".gs": "Google Apps Script",
            ".md": "Document",
            ".pdf": "Document",
        }
        
        if ext in ext_to_type and self.item_types_manager:
            inferred_type = ext_to_type[ext]
            db_id = self.item_types_manager.get_database_for_item_type(inferred_type)
            if db_id and db_id not in database_ids:
                database_ids.append(db_id)
                logger.debug(f"Routed via file extension '{ext}' to database {db_id}")
        
        return database_ids
    
    def get_primary_database(
        self,
        item_type: str,
        source_path: Optional[str] = None
    ) -> Optional[str]:
        """
        Get primary (first) database ID for an item type.
        
        Args:
            item_type: Type of item
            source_path: Optional source path
            
        Returns:
            Primary database ID or None
        """
        # Create dummy item for routing
        item = {"item_type": item_type}
        database_ids = self.route_item(item, item_type, source_path)
        
        if database_ids:
            return database_ids[0]
        
        return None

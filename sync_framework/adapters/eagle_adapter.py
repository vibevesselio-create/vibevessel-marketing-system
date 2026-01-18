#!/usr/bin/env python3
"""
Eagle Source Adapter
===================

Extracts items from Eagle library for synchronization.
"""

from pathlib import Path
from typing import Dict, List, Optional, Any
import logging

logger = logging.getLogger(__name__)


class EagleAdapter:
    """Eagle source adapter for sync orchestrator."""
    
    def __init__(self, eagle_api_url: str = "http://localhost:41595"):
        """
        Initialize Eagle adapter.
        
        Args:
            eagle_api_url: Eagle API base URL
        """
        self.eagle_api_url = eagle_api_url
        self._eagle_client = None
    
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
        Discover items from Eagle library.
        
        Args:
            source_path: Optional source path (not used for Eagle)
            item_type: Item type to discover
            
        Returns:
            List of item dictionaries
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
            items = []
            
            for item_data in items_data.get("data", []):
                # Filter by item type if needed
                item = self._convert_from_eagle_item(item_data, item_type)
                if item:
                    items.append(item)
            
            return items
        
        except Exception as e:
            logger.error(f"Failed to discover Eagle items: {e}")
            return []
    
    def _convert_from_eagle_item(
        self,
        eagle_item: Dict[str, Any],
        item_type: str
    ) -> Optional[Dict[str, Any]]:
        """Convert Eagle item to sync framework item format."""
        try:
            return {
                "id": eagle_item.get("id"),
                "title": eagle_item.get("name"),
                "name": eagle_item.get("name"),
                "file_path": eagle_item.get("path"),
                "path": eagle_item.get("path"),
                "tags": eagle_item.get("tags", []),
                "url": eagle_item.get("ext", {}).get("webUrl"),
                "source": "eagle",
                "item_type": item_type,
                "metadata": {
                    "eagle_id": eagle_item.get("id"),
                    "size": eagle_item.get("size"),
                    "mtime": eagle_item.get("mtime"),
                }
            }
        except Exception as e:
            logger.warning(f"Failed to convert Eagle item: {e}")
            return None
    
    def get_items(self, source_path: Optional[Path] = None) -> List[Dict[str, Any]]:
        """Get all items from Eagle (alias for discover_items)."""
        return self.discover_items(source_path, "")

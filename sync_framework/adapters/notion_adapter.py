#!/usr/bin/env python3
"""
Notion Destination Adapter
==========================

Handles batch operations, rate limiting, and error handling for Notion API.
"""

import time
from typing import Dict, List, Optional, Any
import logging

try:
    from notion_client import Client
    NOTION_AVAILABLE = True
except ImportError:
    NOTION_AVAILABLE = False
    Client = None

logger = logging.getLogger(__name__)


class NotionAdapter:
    """Notion destination adapter for sync orchestrator."""
    
    def __init__(
        self,
        notion_token: Optional[str] = None,
        rate_limit_delay: float = 0.1
    ):
        """
        Initialize Notion adapter.
        
        Args:
            notion_token: Notion API token
            rate_limit_delay: Delay between requests in seconds
        """
        self.rate_limit_delay = rate_limit_delay
        self.notion_client = self._get_notion_client(notion_token)
        self._last_request_time = 0.0
    
    def _get_notion_client(self, token: Optional[str] = None) -> Optional[Client]:
        """Get Notion client."""
        if not NOTION_AVAILABLE:
            logger.warning("notion-client not available")
            return None
        
        if not token:
            try:
                from shared_core.notion.token_manager import get_notion_token
                token = get_notion_token()
            except ImportError:
                import os
                token = os.getenv("NOTION_TOKEN") or os.getenv("NOTION_API_TOKEN")
        
        if not token:
            logger.warning("No Notion token available")
            return None
        
        try:
            return Client(auth=token)
        except Exception as e:
            logger.error(f"Failed to create Notion client: {e}")
            return None
    
    def _rate_limit(self) -> None:
        """Apply rate limiting."""
        now = time.time()
        elapsed = now - self._last_request_time
        if elapsed < self.rate_limit_delay:
            time.sleep(self.rate_limit_delay - elapsed)
        self._last_request_time = time.time()
    
    def create_or_update_item(
        self,
        item: Dict[str, Any],
        database_id: str,
        item_type: str
    ) -> Dict[str, Any]:
        """
        Create or update item in Notion database.
        
        Args:
            item: Item dictionary
            database_id: Target Notion database ID
            item_type: Item type name
            
        Returns:
            Dictionary with 'created', 'item_id', etc.
        """
        if not self.notion_client:
            raise RuntimeError("Notion client not available")
        
        self._rate_limit()
        
        # Check if item already exists (by ID or unique field)
        existing_id = item.get("notion_page_id") or item.get("page_id")
        
        if existing_id:
            # Update existing
            try:
                properties = self._convert_to_notion_properties(item, item_type)
                self.notion_client.pages.update(
                    page_id=existing_id,
                    properties=properties
                )
                return {"created": False, "item_id": existing_id}
            except Exception as e:
                logger.warning(f"Update failed, trying create: {e}")
        
        # Create new
        try:
            properties = self._convert_to_notion_properties(item, item_type)
            response = self.notion_client.pages.create(
                parent={"database_id": database_id},
                properties=properties
            )
            return {"created": True, "item_id": response.get("id")}
        except Exception as e:
            logger.error(f"Failed to create item: {e}")
            raise
    
    def _convert_to_notion_properties(
        self,
        item: Dict[str, Any],
        item_type: str
    ) -> Dict[str, Any]:
        """Convert item dictionary to Notion properties format."""
        properties = {}
        
        # Title property (usually first)
        title_field = item.get("title") or item.get("name") or item.get("Title")
        if title_field:
            properties["Name"] = {
                "title": [{"text": {"content": str(title_field)}}]
            }
        
        # Map other fields
        for key, value in item.items():
            if key.lower() in ["title", "name", "id", "page_id", "notion_page_id"]:
                continue
            
            # Convert to Notion property format
            if isinstance(value, str):
                properties[key] = {"rich_text": [{"text": {"content": value}}]}
            elif isinstance(value, (int, float)):
                properties[key] = {"number": value}
            elif isinstance(value, bool):
                properties[key] = {"checkbox": value}
            elif isinstance(value, list):
                if value and isinstance(value[0], str):
                    properties[key] = {"multi_select": [{"name": v} for v in value]}
                else:
                    properties[key] = {"rich_text": [{"text": {"content": str(v)}} for v in value]}
            elif value is not None:
                properties[key] = {"rich_text": [{"text": {"content": str(value)}}]}
        
        return properties
    
    def get_existing_items(self, item_type: str) -> List[Dict[str, Any]]:
        """
        Get existing items from Notion (for deduplication).
        
        Args:
            item_type: Item type name
            
        Returns:
            List of existing items
        """
        if not self.notion_client:
            return []
        
        # Get database ID for item type
        try:
            from sync_config.item_types_manager import get_item_types_manager
            manager = get_item_types_manager()
            database_id = manager.get_database_for_item_type(item_type)
            
            if not database_id:
                return []
            
            self._rate_limit()
            response = self.notion_client.databases.query(database_id=database_id, page_size=100)
            
            items = []
            for page in response.get("results", []):
                item = self._convert_from_notion_page(page)
                items.append(item)
            
            return items
        
        except Exception as e:
            logger.warning(f"Failed to get existing items: {e}")
            return []
    
    def _convert_from_notion_page(self, page: Dict[str, Any]) -> Dict[str, Any]:
        """Convert Notion page to item dictionary."""
        item = {
            "id": page.get("id"),
            "page_id": page.get("id"),
            "notion_page_id": page.get("id"),
            "source": "notion"
        }
        
        properties = page.get("properties", {})
        for prop_name, prop_value in properties.items():
            prop_type = prop_value.get("type")
            
            if prop_type == "title":
                title_array = prop_value.get("title", [])
                if title_array:
                    item[prop_name] = "".join(t.get("plain_text", "") for t in title_array)
            elif prop_type == "rich_text":
                text_array = prop_value.get("rich_text", [])
                if text_array:
                    item[prop_name] = "".join(t.get("plain_text", "") for t in text_array)
            elif prop_type == "number":
                item[prop_name] = prop_value.get("number")
            elif prop_type == "checkbox":
                item[prop_name] = prop_value.get("checkbox")
            elif prop_type == "multi_select":
                item[prop_name] = [opt.get("name") for opt in prop_value.get("multi_select", [])]
        
        return item
    
    def sync_item(self, item: Dict[str, Any], database_id: str) -> None:
        """Sync item to Notion (alias for create_or_update_item)."""
        self.create_or_update_item(item, database_id, item.get("item_type", ""))

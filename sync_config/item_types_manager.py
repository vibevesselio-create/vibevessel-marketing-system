#!/usr/bin/env python3
"""
Item-Types Database Manager
===========================

Manages queries and caching for the item-types database, providing lookup functions
for database routing, validation rules, and related resources.

Database ID: 26ce7361-6c27-8163-b29e-000be7d41128
"""

import os
import json
import logging
import time
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass, field

try:
    from notion_client import Client
    NOTION_AVAILABLE = True
except ImportError:
    NOTION_AVAILABLE = False
    Client = None

logger = logging.getLogger(__name__)

# Item-Types Database ID
ITEM_TYPES_DATABASE_ID = "26ce7361-6c27-8163-b29e-000be7d41128"

# Default cache TTL (1 hour)
DEFAULT_CACHE_TTL_SECONDS = 3600


@dataclass
class ItemTypeConfig:
    """Configuration for a single item type."""
    name: str
    page_id: str
    default_sync_database_id: Optional[str] = None
    variable_namespace: Optional[str] = None
    population_requirements: Dict[str, Any] = field(default_factory=dict)
    validation_rules: Dict[str, Any] = field(default_factory=dict)
    template_schema: Dict[str, Any] = field(default_factory=dict)
    default_values: Dict[str, Any] = field(default_factory=dict)
    related_databases: List[str] = field(default_factory=list)
    related_functions: List[str] = field(default_factory=list)
    related_scripts: List[str] = field(default_factory=list)
    related_prompts: List[str] = field(default_factory=list)
    related_tasks: List[str] = field(default_factory=list)
    related_workflows: List[str] = field(default_factory=list)
    category: Optional[str] = None
    data_classification: Optional[str] = None
    environment: Optional[str] = None
    inheritance_mode: Optional[str] = None
    scope_level: Optional[str] = None
    description: Optional[str] = None
    version: Optional[str] = None
    status: Optional[str] = None
    owner: Optional[str] = None


class ItemTypesManager:
    """Manages item-types database queries and caching."""
    
    def __init__(
        self,
        notion_token: Optional[str] = None,
        cache_ttl: int = DEFAULT_CACHE_TTL_SECONDS,
        cache_file: Optional[Path] = None,
        force_refresh: bool = False
    ):
        """
        Initialize the Item-Types Manager.
        
        Args:
            notion_token: Notion API token (if None, will try to get from env/token manager)
            cache_ttl: Cache time-to-live in seconds (default: 3600)
            cache_file: Optional path to JSON cache file for fallback
            force_refresh: Force refresh cache even if valid
        """
        self.cache_ttl = cache_ttl
        self.cache_file = cache_file or Path.home() / ".cache" / "item_types_cache.json"
        self.force_refresh = force_refresh
        
        # Cache storage
        self._cache: Dict[str, ItemTypeConfig] = {}
        self._cache_timestamp: Optional[datetime] = None
        self._cache_by_name: Dict[str, ItemTypeConfig] = {}
        
        # Initialize Notion client
        self.notion_client = self._get_notion_client(notion_token)
        
        # Load cache
        self._load_cache()
    
    def _get_notion_client(self, token: Optional[str] = None) -> Optional[Client]:
        """Get Notion client, trying multiple sources for token."""
        if not NOTION_AVAILABLE:
            logger.warning("notion-client not available, item-types lookups will use cache only")
            return None
        
        # Try provided token first
        if token:
            try:
                return Client(auth=token)
            except Exception as e:
                logger.warning(f"Failed to create Notion client with provided token: {e}")
        
        # Try shared_core token manager
        try:
            from shared_core.notion.token_manager import get_notion_token
            token = get_notion_token()
            if token:
                return Client(auth=token)
        except ImportError:
            pass
        except Exception as e:
            logger.debug(f"Token manager not available: {e}")
        
        # Try environment variables
        token = os.getenv("NOTION_TOKEN") or os.getenv("NOTION_API_TOKEN") or os.getenv("NOTION_API_KEY")
        if token:
            try:
                return Client(auth=token)
            except Exception as e:
                logger.warning(f"Failed to create Notion client with env token: {e}")
        
        logger.warning("No Notion token available, item-types lookups will use cache only")
        return None
    
    def _load_cache(self) -> None:
        """Load cache from file if available and valid."""
        if self.force_refresh:
            logger.info("Force refresh requested, skipping cache load")
            return
        
        # Check if in-memory cache is still valid
        if self._cache_timestamp:
            age = (datetime.now() - self._cache_timestamp).total_seconds()
            if age < self.cache_ttl:
                logger.debug(f"Using in-memory cache (age: {age:.0f}s)")
                return
        
        # Try to load from file
        if self.cache_file and self.cache_file.exists():
            try:
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)
                    timestamp_str = cache_data.get('timestamp')
                    if timestamp_str:
                        timestamp = datetime.fromisoformat(timestamp_str)
                        age = (datetime.now() - timestamp).total_seconds()
                        if age < self.cache_ttl:
                            self._cache = {}
                            self._cache_by_name = {}
                            for page_id, config_dict in cache_data.get('items', {}).items():
                                config = self._dict_to_config(config_dict)
                                self._cache[page_id] = config
                                self._cache_by_name[config.name] = config
                            self._cache_timestamp = timestamp
                            logger.info(f"Loaded {len(self._cache)} item types from cache file")
                            return
            except Exception as e:
                logger.warning(f"Failed to load cache from file: {e}")
        
        # Cache invalid or missing, refresh from Notion
        if self.notion_client:
            self._refresh_from_notion()
        else:
            logger.warning("No Notion client available and cache invalid, cannot load item types")
    
    def _save_cache(self) -> None:
        """Save cache to file."""
        if not self.cache_file:
            return
        
        try:
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_data = {
                'timestamp': self._cache_timestamp.isoformat() if self._cache_timestamp else None,
                'items': {
                    page_id: self._config_to_dict(config)
                    for page_id, config in self._cache.items()
                }
            }
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, indent=2, default=str)
            logger.debug(f"Saved {len(self._cache)} item types to cache file")
        except Exception as e:
            logger.warning(f"Failed to save cache to file: {e}")
    
    def _refresh_from_notion(self) -> None:
        """Refresh cache from Notion API."""
        if not self.notion_client:
            logger.warning("Cannot refresh from Notion: no client available")
            return
        
        logger.info(f"Refreshing item-types cache from Notion database {ITEM_TYPES_DATABASE_ID}")
        
        try:
            # Query all pages from item-types database
            all_pages = []
            start_cursor = None
            
            while True:
                query_params = {
                    "database_id": ITEM_TYPES_DATABASE_ID,
                    "page_size": 100
                }
                if start_cursor:
                    query_params["start_cursor"] = start_cursor
                
                response = self.notion_client.databases.query(**query_params)
                pages = response.get("results", [])
                all_pages.extend(pages)
                
                if not response.get("has_more"):
                    break
                start_cursor = response.get("next_cursor")
            
            logger.info(f"Retrieved {len(all_pages)} item type pages from Notion")
            
            # Parse pages into ItemTypeConfig objects
            self._cache = {}
            self._cache_by_name = {}
            
            for page in all_pages:
                config = self._parse_page(page)
                if config:
                    self._cache[config.page_id] = config
                    self._cache_by_name[config.name] = config
            
            self._cache_timestamp = datetime.now()
            logger.info(f"Parsed {len(self._cache)} item type configurations")
            
            # Save to file
            self._save_cache()
            
        except Exception as e:
            logger.error(f"Failed to refresh from Notion: {e}")
            raise
    
    def _parse_page(self, page: Dict[str, Any]) -> Optional[ItemTypeConfig]:
        """Parse a Notion page into an ItemTypeConfig."""
        try:
            properties = page.get("properties", {})
            page_id = page.get("id", "")
            
            # Extract name (title property)
            name = ""
            name_prop = properties.get("Name", {})
            if name_prop.get("type") == "title":
                title_array = name_prop.get("title", [])
                if title_array:
                    name = "".join(t.get("plain_text", "") for t in title_array)
            
            if not name:
                logger.warning(f"Page {page_id} has no name, skipping")
                return None
            
            # Extract Default-Synchronization-Database (relation)
            default_sync_db_id = None
            sync_db_prop = properties.get("Default-Synchronization-Database", {})
            if sync_db_prop.get("type") == "relation":
                relations = sync_db_prop.get("relation", [])
                if relations:
                    default_sync_db_id = relations[0].get("id")
            
            # Extract Variable-Namespace (rich_text or text)
            variable_namespace = None
            namespace_prop = properties.get("Variable-Namespace", {})
            if namespace_prop.get("type") in ["rich_text", "text"]:
                text_array = namespace_prop.get("rich_text", namespace_prop.get("text", []))
                if text_array:
                    variable_namespace = "".join(t.get("plain_text", "") for t in text_array)
            
            # Extract Population-Requirements (rich_text or text, may be JSON)
            population_requirements = {}
            pop_req_prop = properties.get("Population-Requirements", {})
            if pop_req_prop.get("type") in ["rich_text", "text"]:
                text_array = pop_req_prop.get("rich_text", pop_req_prop.get("text", []))
                if text_array:
                    req_text = "".join(t.get("plain_text", "") for t in text_array)
                    if req_text:
                        try:
                            population_requirements = json.loads(req_text)
                        except json.JSONDecodeError:
                            population_requirements = {"raw": req_text}
            
            # Extract Validation-Rules (rich_text or text, may be JSON)
            validation_rules = {}
            val_rules_prop = properties.get("Validation-Rules", {})
            if val_rules_prop.get("type") in ["rich_text", "text"]:
                text_array = val_rules_prop.get("rich_text", val_rules_prop.get("text", []))
                if text_array:
                    rules_text = "".join(t.get("plain_text", "") for t in text_array)
                    if rules_text:
                        try:
                            validation_rules = json.loads(rules_text)
                        except json.JSONDecodeError:
                            validation_rules = {"raw": rules_text}
            
            # Extract Template-Schema (rich_text or text, may be JSON)
            template_schema = {}
            template_prop = properties.get("Template-Schema", {})
            if template_prop.get("type") in ["rich_text", "text"]:
                text_array = template_prop.get("rich_text", template_prop.get("text", []))
                if text_array:
                    schema_text = "".join(t.get("plain_text", "") for t in text_array)
                    if schema_text:
                        try:
                            template_schema = json.loads(schema_text)
                        except json.JSONDecodeError:
                            template_schema = {"raw": schema_text}
            
            # Extract Default-Values (rich_text or text, may be JSON)
            default_values = {}
            default_vals_prop = properties.get("Default-Values", {})
            if default_vals_prop.get("type") in ["rich_text", "text"]:
                text_array = default_vals_prop.get("rich_text", default_vals_prop.get("text", []))
                if text_array:
                    vals_text = "".join(t.get("plain_text", "") for t in text_array)
                    if vals_text:
                        try:
                            default_values = json.loads(vals_text)
                        except json.JSONDecodeError:
                            default_values = {"raw": vals_text}
            
            # Extract relation properties
            related_databases = self._extract_relations(properties, "DATABASES")
            related_functions = self._extract_relations(properties, "Functions")
            related_scripts = self._extract_relations(properties, "Scripts")
            related_prompts = self._extract_relations(properties, "Prompts")
            related_tasks = self._extract_relations(properties, "Tasks")
            related_workflows = self._extract_relations(properties, "Workflows")
            
            # Extract categorical properties
            category = self._extract_select(properties, "Category") or self._extract_select(properties, "Linked Primary Category")
            data_classification = self._extract_select(properties, "Data Classification")
            environment = self._extract_select(properties, "Environment")
            inheritance_mode = self._extract_select(properties, "Inheritance-Mode")
            scope_level = self._extract_select(properties, "Scope-Level")
            
            # Extract metadata
            description = self._extract_rich_text(properties, "Description")
            version = self._extract_rich_text(properties, "Version")
            status = self._extract_select(properties, "Status")
            owner = self._extract_rich_text(properties, "Owner")
            
            return ItemTypeConfig(
                name=name,
                page_id=page_id,
                default_sync_database_id=default_sync_db_id,
                variable_namespace=variable_namespace,
                population_requirements=population_requirements,
                validation_rules=validation_rules,
                template_schema=template_schema,
                default_values=default_values,
                related_databases=related_databases,
                related_functions=related_functions,
                related_scripts=related_scripts,
                related_prompts=related_prompts,
                related_tasks=related_tasks,
                related_workflows=related_workflows,
                category=category,
                data_classification=data_classification,
                environment=environment,
                inheritance_mode=inheritance_mode,
                scope_level=scope_level,
                description=description,
                version=version,
                status=status,
                owner=owner
            )
            
        except Exception as e:
            logger.error(f"Failed to parse page {page.get('id', 'unknown')}: {e}")
            return None
    
    def _extract_relations(self, properties: Dict[str, Any], prop_name: str) -> List[str]:
        """Extract relation property IDs."""
        prop = properties.get(prop_name, {})
        if prop.get("type") == "relation":
            return [rel.get("id") for rel in prop.get("relation", []) if rel.get("id")]
        return []
    
    def _extract_select(self, properties: Dict[str, Any], prop_name: str) -> Optional[str]:
        """Extract select property value."""
        prop = properties.get(prop_name, {})
        if prop.get("type") == "select":
            select_obj = prop.get("select")
            if select_obj:
                return select_obj.get("name")
        return None
    
    def _extract_rich_text(self, properties: Dict[str, Any], prop_name: str) -> Optional[str]:
        """Extract rich_text property value."""
        prop = properties.get(prop_name, {})
        if prop.get("type") == "rich_text":
            text_array = prop.get("rich_text", [])
            if text_array:
                return "".join(t.get("plain_text", "") for t in text_array)
        return None
    
    def _config_to_dict(self, config: ItemTypeConfig) -> Dict[str, Any]:
        """Convert ItemTypeConfig to dictionary for JSON serialization."""
        return {
            "name": config.name,
            "page_id": config.page_id,
            "default_sync_database_id": config.default_sync_database_id,
            "variable_namespace": config.variable_namespace,
            "population_requirements": config.population_requirements,
            "validation_rules": config.validation_rules,
            "template_schema": config.template_schema,
            "default_values": config.default_values,
            "related_databases": config.related_databases,
            "related_functions": config.related_functions,
            "related_scripts": config.related_scripts,
            "related_prompts": config.related_prompts,
            "related_tasks": config.related_tasks,
            "related_workflows": config.related_workflows,
            "category": config.category,
            "data_classification": config.data_classification,
            "environment": config.environment,
            "inheritance_mode": config.inheritance_mode,
            "scope_level": config.scope_level,
            "description": config.description,
            "version": config.version,
            "status": config.status,
            "owner": config.owner
        }
    
    def _dict_to_config(self, data: Dict[str, Any]) -> ItemTypeConfig:
        """Convert dictionary to ItemTypeConfig."""
        return ItemTypeConfig(**data)
    
    def refresh_cache(self) -> None:
        """Force refresh cache from Notion."""
        self.force_refresh = True
        if self.notion_client:
            self._refresh_from_notion()
        else:
            logger.warning("Cannot refresh: no Notion client available")
    
    def get_database_for_item_type(self, item_type_name: str) -> Optional[str]:
        """
        Get Default-Synchronization-Database ID for an item type.
        
        Args:
            item_type_name: Name of the item type
            
        Returns:
            Database ID if found, None otherwise
        """
        config = self.get_item_type_config(item_type_name)
        if config:
            return config.default_sync_database_id
        return None
    
    def get_item_type_config(self, item_type_name: str) -> Optional[ItemTypeConfig]:
        """
        Get full item-type configuration.
        
        Args:
            item_type_name: Name of the item type
            
        Returns:
            ItemTypeConfig if found, None otherwise
        """
        # Check cache
        if item_type_name in self._cache_by_name:
            return self._cache_by_name[item_type_name]
        
        # Try case-insensitive lookup
        for name, config in self._cache_by_name.items():
            if name.lower() == item_type_name.lower():
                return config
        
        logger.debug(f"Item type '{item_type_name}' not found in cache")
        return None
    
    def get_validation_rules(self, item_type_name: str) -> Dict[str, Any]:
        """
        Get Population-Requirements and Validation-Rules for an item type.
        
        Args:
            item_type_name: Name of the item type
            
        Returns:
            Dictionary with 'population_requirements' and 'validation_rules' keys
        """
        config = self.get_item_type_config(item_type_name)
        if config:
            return {
                "population_requirements": config.population_requirements,
                "validation_rules": config.validation_rules
            }
        return {"population_requirements": {}, "validation_rules": {}}
    
    def get_related_databases(self, item_type_name: str) -> List[str]:
        """Get all related DATABASES relation IDs for an item type."""
        config = self.get_item_type_config(item_type_name)
        if config:
            return config.related_databases
        return []
    
    def get_related_functions(self, item_type_name: str) -> List[str]:
        """Get all related Functions relation IDs for an item type."""
        config = self.get_item_type_config(item_type_name)
        if config:
            return config.related_functions
        return []
    
    def get_related_scripts(self, item_type_name: str) -> List[str]:
        """Get all related Scripts relation IDs for an item type."""
        config = self.get_item_type_config(item_type_name)
        if config:
            return config.related_scripts
        return []
    
    def get_related_prompts(self, item_type_name: str) -> List[str]:
        """Get all related Prompts relation IDs for an item type."""
        config = self.get_item_type_config(item_type_name)
        if config:
            return config.related_prompts
        return []
    
    def get_related_tasks(self, item_type_name: str) -> List[str]:
        """Get all related Tasks relation IDs for an item type."""
        config = self.get_item_type_config(item_type_name)
        if config:
            return config.related_tasks
        return []
    
    def get_related_workflows(self, item_type_name: str) -> List[str]:
        """Get all related Workflows relation IDs for an item type."""
        config = self.get_item_type_config(item_type_name)
        if config:
            return config.related_workflows
        return []
    
    def list_all_item_types(self) -> List[str]:
        """List all item type names in cache."""
        return list(self._cache_by_name.keys())
    
    def get_item_types_by_category(self, category: str) -> List[str]:
        """Get all item type names in a specific category."""
        result = []
        for name, config in self._cache_by_name.items():
            if config.category and config.category.lower() == category.lower():
                result.append(name)
        return result


# Global instance (lazy initialization)
_global_manager: Optional[ItemTypesManager] = None


def get_item_types_manager(
    notion_token: Optional[str] = None,
    cache_ttl: int = DEFAULT_CACHE_TTL_SECONDS,
    force_refresh: bool = False
) -> ItemTypesManager:
    """
    Get or create global ItemTypesManager instance.
    
    Args:
        notion_token: Optional Notion API token
        cache_ttl: Cache TTL in seconds
        force_refresh: Force refresh cache
        
    Returns:
        ItemTypesManager instance
    """
    global _global_manager
    
    if _global_manager is None or force_refresh:
        _global_manager = ItemTypesManager(
            notion_token=notion_token,
            cache_ttl=cache_ttl,
            force_refresh=force_refresh
        )
    elif force_refresh:
        _global_manager.refresh_cache()
    
    return _global_manager

#!/usr/bin/env python3
"""
Notion Property Auto-Creator
============================

Automatically creates missing properties in Notion databases when validation errors occur.
This utility should be used by all Notion functions to handle property creation automatically.

Usage:
    from shared_core.notion.property_auto_creator import ensure_properties_exist, create_page_with_auto_properties
    
    # Option 1: Ensure properties exist before operation
    ensure_properties_exist(database_id, {"Device": "rich_text", "Filesystem Type": "rich_text"})
    
    # Option 2: Auto-create on error (recommended)
    page = create_page_with_auto_properties(database_id, properties)
"""

import logging
import re
from typing import Dict, Any, Optional, List, Tuple
from notion_client.errors import APIResponseError

logger = logging.getLogger(__name__)

# Property type inference rules
PROPERTY_TYPE_HINTS = {
    "rich_text": ["text", "string", "str", "description", "summary", "path", "url", "device", "type"],
    "number": ["count", "size", "number", "num", "quantity", "amount", "duration", "score"],
    "date": ["date", "time", "timestamp", "created", "updated", "last", "end", "start"],
    "select": ["status", "type", "category", "priority", "mode", "state"],
    "multi_select": ["tags", "categories", "types", "labels"],
    "relation": ["relation", "link", "related", "parent", "child"],
    "title": ["name", "title"],
    "checkbox": ["is", "has", "enable", "disable", "active", "complete"],
    "url": ["url", "link", "href"],
    "email": ["email", "mail"],
    "phone_number": ["phone", "tel"],
    "people": ["user", "owner", "assignee", "author", "creator"],
    "files": ["file", "attachment", "document"],
    "formula": ["formula", "calc", "computed"],
    "rollup": ["rollup", "aggregate"],
}


def infer_property_type(property_name: str, value: Any) -> str:
    """
    Infer Notion property type from property name and value.
    
    Args:
        property_name: Name of the property
        value: Value being set (used for type inference)
    
    Returns:
        Inferred property type
    """
    name_lower = property_name.lower()
    
    # Check value type first
    if isinstance(value, bool):
        return "checkbox"
    elif isinstance(value, (int, float)):
        return "number"
    elif isinstance(value, dict):
        # Check if it's already a Notion property structure
        if "title" in value:
            return "title"
        elif "rich_text" in value:
            return "rich_text"
        elif "number" in value:
            return "number"
        elif "date" in value:
            return "date"
        elif "select" in value:
            return "select"
        elif "multi_select" in value:
            return "multi_select"
        elif "relation" in value:
            return "relation"
        elif "checkbox" in value:
            return "checkbox"
        elif "url" in value:
            return "url"
        elif "email" in value:
            return "email"
        elif "phone_number" in value:
            return "phone_number"
        elif "people" in value:
            return "people"
        elif "files" in value:
            return "files"
    
    # Check property name hints
    for prop_type, hints in PROPERTY_TYPE_HINTS.items():
        for hint in hints:
            if hint in name_lower:
                return prop_type
    
    # Default to rich_text
    return "rich_text"


def create_property_definition(property_type: str) -> Dict[str, Any]:
    """
    Create a Notion property definition for a given type.
    
    Args:
        property_type: Notion property type
    
    Returns:
        Property definition dictionary
    """
    definitions = {
        "title": {"type": "title", "title": {}},
        "rich_text": {"type": "rich_text", "rich_text": {}},
        "number": {"type": "number", "number": {"format": "number"}},
        "date": {"type": "date", "date": {}},
        "select": {"type": "select", "select": {"options": []}},
        "multi_select": {"type": "multi_select", "multi_select": {"options": []}},
        "relation": {"type": "relation", "relation": {"database_id": None}},
        "checkbox": {"type": "checkbox", "checkbox": {}},
        "url": {"type": "url", "url": {}},
        "email": {"type": "email", "email": {}},
        "phone_number": {"type": "phone_number", "phone_number": {}},
        "people": {"type": "people", "people": {}},
        "files": {"type": "files", "files": {}},
    }
    
    return definitions.get(property_type, {"type": "rich_text", "rich_text": {}})


def parse_missing_properties_error(error_message: str) -> List[str]:
    """
    Parse Notion API error message to extract missing property names.
    
    Args:
        error_message: Error message from Notion API
    
    Returns:
        List of missing property names
    """
    missing_properties = []
    
    # Pattern: "PropertyName is not a property that exists."
    pattern = r'"([^"]+)" is not a property that exists'
    matches = re.findall(pattern, error_message)
    missing_properties.extend(matches)
    
    # Pattern: "PropertyName1 is not a property that exists. PropertyName2 is not a property that exists."
    # The regex above should catch all instances
    
    return missing_properties


def ensure_properties_exist(
    client: Any,
    database_id: str,
    properties: Dict[str, Any],
    property_type_hints: Optional[Dict[str, str]] = None
) -> Tuple[bool, List[str]]:
    """
    Ensure all properties in the given dictionary exist in the database.
    Creates missing properties automatically.
    
    Args:
        client: Notion client instance
        database_id: Notion database ID
        properties: Dictionary of properties to ensure exist
        property_type_hints: Optional dict mapping property names to types
    
    Returns:
        Tuple of (success, list of created property names)
    """
    try:
        # Get current database schema
        database = client.databases.retrieve(database_id=database_id)
        existing_properties = set(database.get("properties", {}).keys())
        
        # Determine which properties need to be created
        properties_to_create = {}
        created_properties = []
        
        for prop_name, prop_value in properties.items():
            if prop_name not in existing_properties:
                # Determine property type
                if property_type_hints and prop_name in property_type_hints:
                    prop_type = property_type_hints[prop_name]
                else:
                    prop_type = infer_property_type(prop_name, prop_value)
                
                # Create property definition
                prop_def = create_property_definition(prop_type)
                properties_to_create[prop_name] = prop_def
                created_properties.append(prop_name)
                
                logger.info(f"➕ Will create property '{prop_name}' as type '{prop_type}'")
        
        # Create missing properties
        if properties_to_create:
            logger.info(f"🔧 Creating {len(properties_to_create)} missing properties in database {database_id[:8]}...")
            client.databases.update(
                database_id=database_id,
                properties=properties_to_create
            )
            logger.info(f"✅ Successfully created {len(properties_to_create)} properties: {', '.join(created_properties)}")
        
        return True, created_properties
        
    except Exception as e:
        logger.error(f"❌ Error ensuring properties exist: {e}")
        return False, []


def create_page_with_auto_properties(
    client: Any,
    database_id: str,
    properties: Dict[str, Any],
    property_type_hints: Optional[Dict[str, str]] = None,
    max_retries: int = 2
) -> Optional[Dict[str, Any]]:
    """
    Create a Notion page with automatic property creation on validation errors.
    
    This function will:
    1. Try to create the page
    2. If it fails with a "property doesn't exist" error, create the missing properties
    3. Retry the operation
    
    Args:
        client: Notion client instance
        database_id: Notion database ID
        properties: Dictionary of properties to set
        property_type_hints: Optional dict mapping property names to types
        max_retries: Maximum number of retries (default: 2)
    
    Returns:
        Created page object or None if failed
    """
    for attempt in range(max_retries + 1):
        try:
            # Try to create the page
            response = client.pages.create(
                parent={"database_id": database_id},
                properties=properties
            )
            return response
            
        except APIResponseError as e:
            error_message = str(e)
            
            # Check if it's a missing property error
            if "is not a property that exists" in error_message:
                if attempt < max_retries:
                    # Parse missing properties
                    missing_props = parse_missing_properties_error(error_message)
                    logger.warning(f"⚠️ Missing properties detected: {missing_props}")
                    
                    # Create missing properties
                    # Build property type hints from the properties dict
                    hints = property_type_hints or {}
                    for prop_name in missing_props:
                        if prop_name not in hints and prop_name in properties:
                            hints[prop_name] = infer_property_type(prop_name, properties[prop_name])
                    
                    success, created = ensure_properties_exist(
                        client, database_id, {k: v for k, v in properties.items() if k in missing_props}, hints
                    )
                    
                    if success:
                        logger.info(f"✅ Created missing properties, retrying page creation (attempt {attempt + 2}/{max_retries + 1})...")
                        continue  # Retry
                    else:
                        logger.error(f"❌ Failed to create missing properties, aborting")
                        return None
                else:
                    logger.error(f"❌ Max retries reached, still missing properties: {error_message}")
                    return None
            else:
                # Different error, don't retry
                logger.error(f"❌ Error creating page: {error_message}")
                return None
                
        except Exception as e:
            logger.error(f"❌ Unexpected error creating page: {e}")
            return None
    
    return None


def update_page_with_auto_properties(
    client: Any,
    page_id: str,
    properties: Dict[str, Any],
    property_type_hints: Optional[Dict[str, str]] = None,
    max_retries: int = 2
) -> bool:
    """
    Update a Notion page with automatic property creation on validation errors.
    
    Args:
        client: Notion client instance
        page_id: Notion page ID
        properties: Dictionary of properties to update
        property_type_hints: Optional dict mapping property names to types
        max_retries: Maximum number of retries (default: 2)
    
    Returns:
        True if successful, False otherwise
    """
    # First, get the database ID from the page
    try:
        page = client.pages.retrieve(page_id=page_id)
        parent = page.get("parent")
        if parent.get("type") != "database_id":
            logger.error("Page parent is not a database")
            return False
        
        database_id = parent.get("database_id")
        
    except Exception as e:
        logger.error(f"Error retrieving page to get database ID: {e}")
        return False
    
    for attempt in range(max_retries + 1):
        try:
            # Try to update the page
            client.pages.update(page_id=page_id, properties=properties)
            return True
            
        except APIResponseError as e:
            error_message = str(e)
            
            # Check if it's a missing property error
            if "is not a property that exists" in error_message:
                if attempt < max_retries:
                    # Parse missing properties
                    missing_props = parse_missing_properties_error(error_message)
                    logger.warning(f"⚠️ Missing properties detected: {missing_props}")
                    
                    # Create missing properties
                    hints = property_type_hints or {}
                    for prop_name in missing_props:
                        if prop_name not in hints and prop_name in properties:
                            hints[prop_name] = infer_property_type(prop_name, properties[prop_name])
                    
                    success, created = ensure_properties_exist(
                        client, database_id, {k: v for k, v in properties.items() if k in missing_props}, hints
                    )
                    
                    if success:
                        logger.info(f"✅ Created missing properties, retrying page update (attempt {attempt + 2}/{max_retries + 1})...")
                        continue  # Retry
                    else:
                        logger.error(f"❌ Failed to create missing properties, aborting")
                        return False
                else:
                    logger.error(f"❌ Max retries reached, still missing properties: {error_message}")
                    return False
            else:
                # Different error, don't retry
                logger.error(f"❌ Error updating page: {error_message}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Unexpected error updating page: {e}")
            return False
    
    return False

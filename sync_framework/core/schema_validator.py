#!/usr/bin/env python3
"""
Schema Validator
================

Dynamic schema validation using item-type Population-Requirements and Validation-Rules.
Auto-repair missing properties. Validate items against rules.
"""

from typing import Dict, List, Tuple, Any, Optional
import logging

try:
    from sync_config.item_types_manager import get_item_types_manager
    ITEM_TYPES_AVAILABLE = True
except ImportError:
    ITEM_TYPES_AVAILABLE = False

logger = logging.getLogger(__name__)


class SchemaValidator:
    """Validates database schemas and items against item-type requirements."""
    
    def __init__(self):
        """Initialize the schema validator."""
        self.item_types_manager = None
        if ITEM_TYPES_AVAILABLE:
            try:
                self.item_types_manager = get_item_types_manager()
            except Exception as e:
                logger.warning(f"Failed to initialize item-types manager: {e}")
    
    def validate_and_repair(
        self,
        database_id: str,
        item_type: str,
        notion_client: Any = None
    ) -> bool:
        """
        Validate database schema against item-type requirements and auto-repair.
        
        Args:
            database_id: Notion database ID
            item_type: Item type name
            notion_client: Notion API client (optional, for auto-repair)
            
        Returns:
            True if schema is valid (or was repaired), False otherwise
        """
        if not self.item_types_manager:
            logger.warning("Item-types manager not available, skipping schema validation")
            return True
        
        config = self.item_types_manager.get_item_type_config(item_type)
        if not config:
            logger.warning(f"Item type '{item_type}' not found, skipping validation")
            return True
        
        # Get population requirements
        pop_reqs = config.population_requirements
        if not isinstance(pop_reqs, dict):
            logger.debug(f"No population requirements for '{item_type}'")
            return True
        
        # Check required properties
        required_props = pop_reqs.get("required_properties", [])
        if not required_props:
            return True
        
        # If notion_client provided, check and repair schema
        if notion_client:
            try:
                # Get database schema
                db_schema = notion_client.databases.retrieve(database_id=database_id)
                existing_props = db_schema.get("properties", {})
                
                missing_props = []
                for prop_name in required_props:
                    if prop_name not in existing_props:
                        missing_props.append(prop_name)
                
                if missing_props:
                    logger.warning(
                        f"Database {database_id} missing required properties for '{item_type}': {missing_props}"
                    )
                    # Auto-repair would go here (requires Notion API update)
                    # For now, just log
                    return False
                
                return True
            except Exception as e:
                logger.error(f"Failed to validate schema: {e}")
                return False
        
        return True
    
    def validate_item(
        self,
        item: Dict[str, Any],
        item_type: str
    ) -> Tuple[bool, List[str]]:
        """
        Validate item properties against item-type rules.
        
        Args:
            item: Item dictionary to validate
            item_type: Item type name
            
        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        if not self.item_types_manager:
            return True, []
        
        config = self.item_types_manager.get_item_type_config(item_type)
        if not config:
            logger.warning(f"Item type '{item_type}' not found, skipping validation")
            return True, []
        
        errors = []
        
        # Check population requirements
        pop_reqs = config.population_requirements
        if isinstance(pop_reqs, dict):
            required_fields = pop_reqs.get("required_fields", [])
            for field in required_fields:
                if field not in item or not item[field]:
                    errors.append(f"Missing required field: {field}")
        
        # Check validation rules
        val_rules = config.validation_rules
        if isinstance(val_rules, dict):
            field_rules = val_rules.get("field_rules", {})
            for field, rules in field_rules.items():
                if field in item:
                    value = item[field]
                    field_errors = self._validate_field(value, rules, field)
                    errors.extend(field_errors)
                elif rules.get("required", False):
                    errors.append(f"Required field '{field}' is missing")
        
        is_valid = len(errors) == 0
        return is_valid, errors
    
    def _validate_field(
        self,
        value: Any,
        rules: Dict[str, Any],
        field_name: str
    ) -> List[str]:
        """Validate a single field against rules."""
        errors = []
        
        # Type validation
        if "type" in rules:
            expected_type = rules["type"]
            if expected_type == "string" and not isinstance(value, str):
                errors.append(f"Field '{field_name}' must be a string, got {type(value).__name__}")
            elif expected_type == "number" and not isinstance(value, (int, float)):
                errors.append(f"Field '{field_name}' must be a number, got {type(value).__name__}")
            elif expected_type == "boolean" and not isinstance(value, bool):
                errors.append(f"Field '{field_name}' must be a boolean, got {type(value).__name__}")
            elif expected_type == "array" and not isinstance(value, list):
                errors.append(f"Field '{field_name}' must be an array, got {type(value).__name__}")
        
        # String length validation
        if isinstance(value, str):
            if "min_length" in rules and len(value) < rules["min_length"]:
                errors.append(
                    f"Field '{field_name}' must be at least {rules['min_length']} characters "
                    f"(got {len(value)})"
                )
            if "max_length" in rules and len(value) > rules["max_length"]:
                errors.append(
                    f"Field '{field_name}' must be at most {rules['max_length']} characters "
                    f"(got {len(value)})"
                )
            
            # Pattern validation
            if "pattern" in rules:
                import re
                if not re.match(rules["pattern"], value):
                    errors.append(f"Field '{field_name}' does not match required pattern")
        
        # Number range validation
        if isinstance(value, (int, float)):
            if "min" in rules and value < rules["min"]:
                errors.append(f"Field '{field_name}' must be at least {rules['min']} (got {value})")
            if "max" in rules and value > rules["max"]:
                errors.append(f"Field '{field_name}' must be at most {rules['max']} (got {value})")
        
        # Enum validation
        if "enum" in rules:
            if value not in rules["enum"]:
                errors.append(
                    f"Field '{field_name}' must be one of {rules['enum']}, got {value}"
                )
        
        return errors
    
    def get_required_properties(self, item_type: str) -> List[str]:
        """
        Get list of required properties for an item type.
        
        Args:
            item_type: Item type name
            
        Returns:
            List of required property names
        """
        if not self.item_types_manager:
            return []
        
        config = self.item_types_manager.get_item_type_config(item_type)
        if not config:
            return []
        
        pop_reqs = config.population_requirements
        if isinstance(pop_reqs, dict):
            return pop_reqs.get("required_fields", [])
        
        return []
    
    def get_default_values(self, item_type: str) -> Dict[str, Any]:
        """
        Get default values for an item type.
        
        Args:
            item_type: Item type name
            
        Returns:
            Dictionary of default values
        """
        if not self.item_types_manager:
            return {}
        
        config = self.item_types_manager.get_item_type_config(item_type)
        if not config:
            return {}
        
        return config.default_values or {}

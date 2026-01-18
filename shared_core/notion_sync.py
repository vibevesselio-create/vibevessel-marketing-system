"""
Notion Sync Helpers (Shared Core)
=================================

This module provides lightweight, reusable helpers for Notion write operations,
especially for automation loop-guards and schema/property consistency.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from shared_core.notion.token_manager import get_notion_client


SEREN_AUTOMATION_SOURCE_PROPERTY_DEFAULT = "Seren Automation Source"
SEREN_AUTOMATION_EVENT_ID_PROPERTY_DEFAULT = "Seren Automation Event ID"
SEREN_AUTOMATION_NODE_ID_PROPERTY_DEFAULT = "Seren Automation Node"


def ensure_loop_guard_properties(
    *,
    notion: Any,
    database_id: str,
    source_property: str = SEREN_AUTOMATION_SOURCE_PROPERTY_DEFAULT,
    event_id_property: str = SEREN_AUTOMATION_EVENT_ID_PROPERTY_DEFAULT,
    node_id_property: str = SEREN_AUTOMATION_NODE_ID_PROPERTY_DEFAULT,
) -> bool:
    """
    Ensure the loop-guard properties exist in the database schema.
    Returns True if properties exist (or were created), False otherwise.
    """
    try:
        db = notion.databases.retrieve(database_id=database_id)
        props = db.get("properties") or {}
        to_add: Dict[str, Any] = {}
        if source_property not in props:
            to_add[source_property] = {"rich_text": {}}
        if event_id_property not in props:
            to_add[event_id_property] = {"rich_text": {}}
        if node_id_property not in props:
            to_add[node_id_property] = {"rich_text": {}}
        if to_add:
            notion.databases.update(database_id=database_id, properties=to_add)
        return True
    except Exception:
        return False


def apply_loop_guard_properties(
    *,
    properties: Dict[str, Any],
    source_value: str,
    node_id: str,
    event_id: Optional[str] = None,
    source_property: str = SEREN_AUTOMATION_SOURCE_PROPERTY_DEFAULT,
    event_id_property: str = SEREN_AUTOMATION_EVENT_ID_PROPERTY_DEFAULT,
    node_id_property: str = SEREN_AUTOMATION_NODE_ID_PROPERTY_DEFAULT,
) -> Dict[str, Any]:
    props = dict(properties or {})
    props[source_property] = {"rich_text": [{"text": {"content": source_value}}]}
    props[node_id_property] = {"rich_text": [{"text": {"content": node_id}}]}
    if event_id:
        props[event_id_property] = {"rich_text": [{"text": {"content": event_id}}]}
    return props


def get_default_notion() -> Any:
    return get_notion_client()


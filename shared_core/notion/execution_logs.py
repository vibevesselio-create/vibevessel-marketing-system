#!/usr/bin/env python3
"""
Execution-Logs Database Writer

Implements canonical Execution-Logs contract with schema validation and backward compatibility.
Handles Status (canonical) vs Final Status (legacy) reconciliation.

Database ID: 27be73616c278033a323dca0fafa80e6
Canonical Contract: docs/observability/logging_metrics_and_execution_logs_standard.md
"""

from __future__ import annotations

import os
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set
from pathlib import Path

try:
    from notion_client import Client  # type: ignore[import]
except ImportError:
    Client = None  # type: ignore[assignment]

# Database ID - resolved via environment or default
EXECUTION_LOGS_DB_ID = os.getenv("NOTION_EXECUTION_LOGS_DB_ID") or "27be73616c278033a323dca0fafa80e6"

# Notion API rich_text property character limit
NOTION_RICH_TEXT_MAX_CHARS = 2000


def _truncate_for_notion(content: str, max_chars: int = NOTION_RICH_TEXT_MAX_CHARS) -> str:
    """
    Truncate content to fit Notion's rich_text character limit.

    Notion API enforces a 2000 character limit on rich_text properties.
    This function safely truncates content and appends a truncation notice.

    Args:
        content: The string content to potentially truncate
        max_chars: Maximum allowed characters (default: 2000)

    Returns:
        Truncated string with notice if exceeds limit, original string otherwise
    """
    if not content or len(content) <= max_chars:
        return content

    # Reserve space for truncation notice
    truncation_notice = "\n\n[...truncated - exceeded Notion's 2000 char limit]"
    available_chars = max_chars - len(truncation_notice)

    return content[:available_chars] + truncation_notice

# Canonical Status values (per logging standard)
CANONICAL_STATUS_VALUES = [
    "Success",
    "Failed",
    "Partial",
    "Running",
    "Paused",
    "Cancelled",
]

# Legacy Final Status values (for migration mapping)
LEGACY_FINAL_STATUS_VALUES = [
    "Running",
    "Completed",  # Maps to "Success"
    "Failed",
    "Cancelled",
    "Success",
    "Partial",
]

# Canonical Environment values (per logging standard)
CANONICAL_ENVIRONMENT_VALUES = [
    "local",
    "gas",
    "production",
    "staging",
    "development",
]


def _get_notion_client() -> Optional[Any]:
    """Get Notion client from environment, if available."""
    if Client is None:
        return None
    
    # Try to get token from unified_config
    api_key = os.getenv("NOTION_API_KEY") or os.getenv("NOTION_TOKEN") or os.getenv("NOTION_API_TOKEN")
    if not api_key:
        try:
            from unified_config import get_notion_token
            api_key = get_notion_token()
        except ImportError:
            pass
    
    if not api_key:
        return None
    
    try:
        return Client(auth=api_key)
    except Exception:
        return None


def _validate_execution_logs_schema(
    client: Any,
    required_properties: Set[str],
) -> Dict[str, Any]:
    """
    Validate Execution-Logs database schema before write.
    
    Returns:
        Dictionary with:
        - valid: bool
        - missing_properties: List[str]
        - type_mismatches: Dict[str, str]  # property_name -> expected_type
        - warnings: List[str]
    """
    try:
        db = client.databases.retrieve(database_id=EXECUTION_LOGS_DB_ID)
        properties = db.get("properties", {})
        
        missing = []
        type_mismatches = {}
        warnings = []
        
        # Check required properties
        for prop_name in required_properties:
            if prop_name not in properties:
                missing.append(prop_name)
        
        # Check canonical Status property
        if "Status" in properties:
            status_prop = properties["Status"]
            if status_prop.get("type") != "select":
                type_mismatches["Status"] = "select (currently: {})".format(status_prop.get("type"))
                warnings.append(
                    "Status property exists but is {} instead of select. "
                    "Legacy 'Final Status' should be migrated to Status."
                    .format(status_prop.get("type"))
                )
        else:
            missing.append("Status")
        
        # Check legacy Final Status (for backward compatibility)
        if "Final Status" in properties:
            final_status_prop = properties["Final Status"]
            if final_status_prop.get("type") == "select":
                warnings.append(
                    "Legacy 'Final Status' property exists. "
                    "Writers should use canonical 'Status' property, "
                    "but Final Status will be set for backward compatibility."
                )
        
        # Check Environment property type
        if "Environment" in properties:
            env_prop = properties["Environment"]
            if env_prop.get("type") != "select":
                type_mismatches["Environment"] = "select (currently: {})".format(env_prop.get("type"))
                warnings.append(
                    "Environment property exists but is {} instead of select."
                    .format(env_prop.get("type"))
                )
        
        # Check core required properties
        core_required = {"Start Time", "End Time"}
        for prop_name in core_required:
            if prop_name not in properties:
                missing.append(prop_name)
            else:
                prop = properties[prop_name]
                if prop.get("type") != "date":
                    type_mismatches[prop_name] = "date (currently: {})".format(prop.get("type"))
        
        return {
            "valid": len(missing) == 0 and len(type_mismatches) == 0,
            "missing_properties": missing,
            "type_mismatches": type_mismatches,
            "warnings": warnings,
            "properties": properties,  # Include for reference
        }
    except Exception as e:
        return {
            "valid": False,
            "missing_properties": [],
            "type_mismatches": {},
            "warnings": [f"Schema validation failed: {e}"],
            "error": str(e),
        }


def _map_legacy_status(status: str) -> str:
    """Map legacy Final Status values to canonical Status values."""
    mapping = {
        "Completed": "Success",
        "Running": "Running",
        "Failed": "Failed",
        "Cancelled": "Cancelled",
        "Success": "Success",
        "Partial": "Partial",
    }
    return mapping.get(status, status)


def create_execution_log(
    name: str,
    start_time: datetime,
    status: str = "Running",
    end_time: Optional[datetime] = None,
    duration: Optional[float] = None,
    run_id: Optional[str] = None,
    script_id: Optional[str] = None,
    task_id: Optional[str] = None,
    agent_id: Optional[str] = None,
    environment: str = "local",
    error_count: int = 0,
    warning_count: int = 0,
    log_path: Optional[str] = None,
    metrics: Optional[Dict[str, Any]] = None,
    plain_english_summary: Optional[str] = None,
    # Legacy compatibility properties
    log_summary: Optional[str] = None,
    log_content: Optional[str] = None,
    errors_json: Optional[List[Dict[str, Any]]] = None,
    final_status: Optional[str] = None,  # Legacy - will be set if provided
    # Additional optional properties
    script_name: Optional[str] = None,
    script_path: Optional[str] = None,
    session_id: Optional[str] = None,
    type: Optional[str] = None,  # Script type
) -> Optional[str]:
    """
    Create an Execution-Logs entry in Notion.
    
    Implements canonical contract with backward compatibility shims.
    
    Args:
        name: Run identifier (title)
        start_time: Execution start timestamp (required)
        status: Canonical status (Success, Failed, Partial, Running, Paused, Cancelled)
        end_time: Execution end timestamp (optional, set when run completes)
        duration: Execution duration in seconds (optional, auto-calculated if end_time provided)
        run_id: Unique run identifier (correlation ID)
        script_id: Related script page ID
        task_id: Related Agent-Task page ID
        agent_id: Related agent page ID
        environment: Environment (local, gas, production, staging, development)
        error_count: Number of errors
        warning_count: Number of warnings
        log_path: Path to log file
        metrics: Structured metrics (JSON)
        plain_english_summary: Human-readable summary
        log_summary: Legacy Log Summary property (for backward compatibility)
        log_content: Legacy Log Content property (for backward compatibility)
        errors_json: Legacy Errors (JSON) property (for backward compatibility)
        final_status: Legacy Final Status (for backward compatibility, will map to Status)
        script_name: Script name
        script_path: Script filesystem path
        session_id: Session identifier
        type: Script type (Local Python Script, Google Apps Script, etc.)
    
    Returns:
        Page ID if successful, None otherwise
    """
    client = _get_notion_client()
    if not client:
        return None
    
    # Validate schema before write
    required_props = {"Start Time", "Status"}
    schema_check = _validate_execution_logs_schema(client, required_props)
    
    # Handle schema validation results
    missing = schema_check.get("missing_properties", [])
    mismatches = schema_check.get("type_mismatches", {})
    
    # Fail-fast only for truly missing required properties
    if missing:
        # Create I+Q item for missing properties
        from shared_core.notion.issues_questions import create_issue_or_question
        
        iq_description = "Execution-Logs schema validation failed: missing required properties.\n\n"
        iq_description += f"**Missing Properties:** {', '.join(missing)}\n\n"
        if mismatches:
            iq_description += f"**Type Mismatches (non-blocking):**\n"
            for prop, expected in mismatches.items():
                iq_description += f"- {prop}: Expected {expected}\n"
        
        create_issue_or_question(
            name="Execution-Logs Schema: Missing Required Properties",
            type=["Internal Issue"],
            status="Unreported",
            priority="Critical",
            component="Notion Schema",
            blocked=True,
            description=iq_description,
            related_task_id=task_id,
            evidence_links=[f"https://www.notion.so/{EXECUTION_LOGS_DB_ID}"],
            tags=["Schema Drift", "Execution-Logs"],
        )
        
        # Fail-fast only for missing properties
        raise ValueError(
            f"Execution-Logs schema validation failed: missing required properties {missing}. "
            f"I+Q item created. Fix schema before proceeding."
        )
    
    # For type mismatches, create I+Q but continue (backward compatibility)
    if mismatches:
        from shared_core.notion.issues_questions import create_issue_or_question
        
        iq_description = "Execution-Logs schema type mismatches detected (non-blocking, backward compatibility enabled).\n\n"
        iq_description += f"**Type Mismatches:**\n"
        for prop, expected in mismatches.items():
            iq_description += f"- {prop}: Expected {expected}\n"
        iq_description += "\n**Action:** Writer will use backward-compatible types. Schema should be migrated to canonical types."
        
        create_issue_or_question(
            name="Execution-Logs Schema: Type Mismatches (Non-Blocking)",
            type=["Internal Issue"],
            status="Unreported",
            priority="Medium",
            component="Notion Schema",
            blocked=False,  # Non-blocking - backward compatibility enabled
            description=iq_description,
            related_task_id=task_id,
            evidence_links=[f"https://www.notion.so/{EXECUTION_LOGS_DB_ID}"],
            tags=["Schema Drift", "Execution-Logs", "Backward Compatibility"],
        )
    
    # Log warnings if any
    if schema_check.get("warnings"):
        import logging
        for warning in schema_check["warnings"]:
            logging.warning(f"Execution-Logs schema warning: {warning}")
    
    # Calculate duration if not provided but end_time is
    if duration is None and end_time:
        duration = (end_time - start_time).total_seconds()
    
    # Normalize status to canonical value
    canonical_status = _map_legacy_status(status)
    if canonical_status not in CANONICAL_STATUS_VALUES:
        canonical_status = "Running"  # Default fallback
    
    # Use final_status if provided (legacy compatibility)
    if final_status:
        canonical_status = _map_legacy_status(final_status)
    
    # Build properties
    properties: Dict[str, Any] = {
        "Name": {
            "title": [{"text": {"content": name}}]
        },
        "Start Time": {
            "date": {"start": start_time.isoformat()}
        },
    }
    
    # Status property - try select first (canonical), fallback to rich_text (legacy)
    properties["Status"] = {
        "rich_text": [{"text": {"content": canonical_status}}]
    }
    # Also set Final Status for backward compatibility if it exists
    if "Final Status" in schema_check.get("properties", {}):
        properties["Final Status"] = {
            "select": {"name": final_status or canonical_status}
        }
    
    # End Time (if provided)
    if end_time:
        properties["End Time"] = {
            "date": {"start": end_time.isoformat()}
        }
    
    # Duration
    if duration is not None:
        properties["Duration (s)"] = {
            "number": duration
        }
    
    # Run ID
    if run_id:
        # Check if "Run ID" or "Execution ID" property exists
        props = schema_check.get("properties", {})
        if "Run ID" in props:
            properties["Run ID"] = {
                "rich_text": [{"text": {"content": run_id}}]
            }
        elif "Execution ID" in props:
            properties["Execution ID"] = {
                "rich_text": [{"text": {"content": run_id}}]
            }
    
    # Relations
    if script_id:
        props = schema_check.get("properties", {})
        if "scripts" in props:
            properties["scripts"] = {
                "relation": [{"id": script_id}]
            }
    
    if task_id:
        props = schema_check.get("properties", {})
        if "Agent-Tasks" in props:
            properties["Agent-Tasks"] = {
                "relation": [{"id": task_id}]
            }
    
    if agent_id:
        props = schema_check.get("properties", {})
        if "Agents" in props:
            properties["Agents"] = {
                "relation": [{"id": agent_id}]
            }
    
    # Environment - try select first (canonical), fallback to rich_text (legacy)
    if environment:
        props = schema_check.get("properties", {})
        env_prop = props.get("Environment", {})
        if env_prop.get("type") == "select":
            properties["Environment"] = {
                "select": {"name": environment}
            }
        else:
            properties["Environment"] = {
                "rich_text": [{"text": {"content": environment}}]
            }
    
    # Error/Warning counts
    if error_count is not None:
        properties["Error Count"] = {"number": error_count}
    
    if warning_count is not None:
        properties["Warning Count"] = {"number": warning_count}
    
    # Log Path
    if log_path:
        props = schema_check.get("properties", {})
        if "Log File Path" in props:
            properties["Log File Path"] = {
                "rich_text": [{"text": {"content": log_path}}]
            }
        elif "Log Path" in props:
            properties["Log Path"] = {
                "rich_text": [{"text": {"content": log_path}}]
            }
    
    # Metrics
    if metrics:
        props = schema_check.get("properties", {})
        metrics_content = _truncate_for_notion(json.dumps(metrics, ensure_ascii=False))
        if "Performance Data (JSON)" in props:
            properties["Performance Data (JSON)"] = {
                "rich_text": [{"text": {"content": metrics_content}}]
            }
        elif "Metrics" in props:
            properties["Metrics"] = {
                "rich_text": [{"text": {"content": metrics_content}}]
            }
    
    # Plain-English Summary
    if plain_english_summary:
        properties["Plain-English Summary"] = {
            "rich_text": [{"text": {"content": _truncate_for_notion(plain_english_summary)}}]
        }

    # Legacy compatibility properties
    if log_summary:
        properties["Log Summary"] = {
            "rich_text": [{"text": {"content": _truncate_for_notion(log_summary)}}]
        }

    if log_content:
        properties["Log Content"] = {
            "rich_text": [{"text": {"content": _truncate_for_notion(log_content)}}]
        }

    if errors_json:
        errors_content = json.dumps(errors_json, ensure_ascii=False)
        properties["Errors (JSON)"] = {
            "rich_text": [{"text": {"content": _truncate_for_notion(errors_content)}}]
        }
    
    # Additional optional properties
    if script_name:
        props = schema_check.get("properties", {})
        if "Script Name-AI" in props:
            properties["Script Name-AI"] = {
                "rich_text": [{"text": {"content": script_name}}]
            }
    
    if script_path:
        properties["Script Path"] = {
            "rich_text": [{"text": {"content": script_path}}]
        }
    
    if session_id:
        properties["Session ID"] = {
            "rich_text": [{"text": {"content": session_id}}]
        }
    
    if type:
        properties["Type"] = {
            "select": {"name": type}
        }
    
    try:
        response = client.pages.create(
            parent={"database_id": EXECUTION_LOGS_DB_ID},
            properties=properties
        )
        return response.get("id")
    except Exception as e:
        # Log error but don't fail (non-blocking)
        import logging
        logging.error(f"Failed to create Execution-Logs entry: {e}")
        return None


def update_execution_log(
    page_id: str,
    status: Optional[str] = None,
    end_time: Optional[datetime] = None,
    duration: Optional[float] = None,
    error_count: Optional[int] = None,
    warning_count: Optional[int] = None,
    metrics: Optional[Dict[str, Any]] = None,
    final_status: Optional[str] = None,  # Legacy compatibility
) -> bool:
    """
    Update an Execution-Logs entry.
    
    Args:
        page_id: Execution-Log page ID
        status: Canonical status value
        end_time: Execution end timestamp
        duration: Execution duration in seconds
        error_count: Number of errors
        warning_count: Number of warnings
        metrics: Structured metrics
        final_status: Legacy Final Status (for backward compatibility)
    
    Returns:
        True if successful, False otherwise
    """
    client = _get_notion_client()
    if not client:
        return False
    
    try:
        properties: Dict[str, Any] = {}
        
        # Status update
        if status:
            canonical_status = _map_legacy_status(status)
            properties["Status"] = {
                "rich_text": [{"text": {"content": canonical_status}}]
            }
        
        # Legacy Final Status
        if final_status:
            canonical_status = _map_legacy_status(final_status)
            properties["Final Status"] = {
                "select": {"name": canonical_status}
            }
            # Also update canonical Status if not already set
            if "Status" not in properties:
                properties["Status"] = {
                    "rich_text": [{"text": {"content": canonical_status}}]
                }
        
        # End Time
        if end_time:
            properties["End Time"] = {
                "date": {"start": end_time.isoformat()}
            }
        
        # Duration
        if duration is not None:
            properties["Duration (s)"] = {"number": duration}
        
        # Error/Warning counts
        if error_count is not None:
            properties["Error Count"] = {"number": error_count}
        
        if warning_count is not None:
            properties["Warning Count"] = {"number": warning_count}
        
        # Metrics
        if metrics:
            properties["Performance Data (JSON)"] = {
                "rich_text": [{"text": {"content": json.dumps(metrics, ensure_ascii=False)}}]
            }
        
        if not properties:
            return True  # Nothing to update
        
        client.pages.update(page_id=page_id, properties=properties)
        return True
    except Exception:
        return False


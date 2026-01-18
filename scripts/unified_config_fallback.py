#!/usr/bin/env python3
"""
Fallback implementation for unified_config when the main module is unavailable.
Uses dotenv and environment variables directly.
"""
import os
from pathlib import Path
from typing import Dict, Any, Optional
from dotenv import load_dotenv

def load_unified_env():
    """Load environment variables from .env files"""
    # Try to load from project root
    project_root = Path(__file__).parent.parent
    env_files = [
        project_root / ".env",
        project_root / ".env.local",
    ]
    for env_file in env_files:
        if env_file.exists():
            load_dotenv(env_file, override=False)

def get_unified_config() -> Dict[str, Any]:
    """Get unified configuration from environment variables"""
    config = {}
    
    # Map environment variables to config keys
    env_mappings = {
        "NOTION_TOKEN": "notion_token",
        "NOTION_API_TOKEN": "notion_token",
        "VV_AUTOMATIONS_WS_TOKEN": "notion_token",
        "NOTION_VERSION": "notion_version",
        "TRACKS_DB_ID": "tracks_db_id",
    }
    
    for env_key, config_key in env_mappings.items():
        value = os.getenv(env_key)
        if value and config_key not in config:
            config[config_key] = value
    
    return config

def get_notion_token() -> Optional[str]:
    """Get Notion API token from shared_core token manager"""
    # Use centralized token manager (MANDATORY per CLAUDE.md)
    try:
        from shared_core.notion.token_manager import get_notion_token as _get_notion_token
        token = _get_notion_token()
        if token:
            return token
    except ImportError:
        pass
    # Fallback for backwards compatibility
    return (
        os.getenv("NOTION_TOKEN") or
        os.getenv("NOTION_API_TOKEN") or
        os.getenv("VV_AUTOMATIONS_WS_TOKEN")
    )



































































































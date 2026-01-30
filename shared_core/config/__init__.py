"""
Unified Configuration Module
============================

Provides centralized environment variable management.

Usage:
    from shared_core.config import ENV, get_env, load_env

    # Get a variable
    notion_token = ENV.NOTION_TOKEN

    # Or via function
    notion_token = get_env("NOTION_TOKEN")
"""

from .env_loader import (
    ENV,
    EnvironmentConfig,
    get_env,
    get_all_env,
    load_env,
    require_env,
    load_dotenv,
    MASTER_ENV_PATH,
)

__all__ = [
    'ENV',
    'EnvironmentConfig',
    'get_env',
    'get_all_env',
    'load_env',
    'require_env',
    'load_dotenv',
    'MASTER_ENV_PATH',
]

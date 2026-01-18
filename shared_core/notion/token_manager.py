#!/usr/bin/env python3
"""
Notion Token Manager - CENTRALIZED TOKEN ACCESS
================================================

This module provides the CANONICAL way to get Notion API tokens.
ALL scripts in this workspace MUST use this module for token access.

**MANDATORY USAGE:**
```python
from shared_core.notion.token_manager import get_notion_token

token = get_notion_token()
if not token:
    raise RuntimeError("Notion token not found - see shared_core/notion/token_manager.py")
```

**TOKEN SOURCES (in priority order):**
1. Environment variable: NOTION_TOKEN
2. Environment variable: NOTION_API_TOKEN
3. Environment variable: VV_AUTOMATIONS_WS_TOKEN
4. Cache file: ~/.notion_token_cache
5. Config file: ~/.config/notion_script_runner/config.json

**NEVER:**
- Hardcode tokens in scripts
- Create custom token loading logic
- Bypass this module

Version: 1.0.0
Last Updated: 2025-01-01
"""

import os
import sys
import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any

# Setup logging
logger = logging.getLogger(__name__)

# Token source priority
TOKEN_ENV_VARS = [
    "NOTION_TOKEN",
    "NOTION_API_TOKEN",
    "VV_AUTOMATIONS_WS_TOKEN"
]

# Config file locations
TOKEN_CACHE_FILE = Path.home() / ".notion_token_cache"
CONFIG_FILE = Path.home() / ".config" / "notion_script_runner" / "config.json"


def _load_token_from_env() -> Optional[str]:
    """Load token from environment variables (priority order)."""
    for env_var in TOKEN_ENV_VARS:
        token = os.getenv(env_var)
        if token and token.strip():
            logger.debug(f"Found Notion token via environment variable: {env_var}")
            return token.strip()
    return None


def _load_token_from_cache() -> Optional[str]:
    """Load token from ~/.notion_token_cache file."""
    if TOKEN_CACHE_FILE.exists():
        try:
            content = TOKEN_CACHE_FILE.read_text().strip()
            # Handle format: NOTION_TOKEN=xxx or just xxx
            if content.startswith("NOTION_TOKEN="):
                token = content.split("=", 1)[1].strip()
            else:
                token = content

            if token:
                logger.debug(f"Found Notion token via cache file: {TOKEN_CACHE_FILE}")
                return token
        except Exception as e:
            logger.debug(f"Error reading token cache file: {e}")
    return None


def _load_token_from_config() -> Optional[str]:
    """Load token from config file (~/.config/notion_script_runner/config.json)."""
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE) as f:
                config = json.load(f)
                token = config.get("notion_token")
                if token and token.strip():
                    logger.debug(f"Found Notion token via config file: {CONFIG_FILE}")
                    return token.strip()
        except Exception as e:
            logger.debug(f"Error reading config file: {e}")
    return None


def _load_dotenv() -> None:
    """Try to load .env files if dotenv is available."""
    try:
        from dotenv import load_dotenv

        # Check multiple locations for .env files
        possible_locations = [
            Path.cwd() / ".env",
            Path(__file__).parent.parent.parent / ".env",  # project root
            Path.home() / ".env",
        ]

        for env_file in possible_locations:
            if env_file.exists():
                load_dotenv(env_file, override=False)
                logger.debug(f"Loaded environment from: {env_file}")
    except ImportError:
        pass  # dotenv not available


def get_notion_token() -> Optional[str]:
    """
    Get Notion API token from configured sources.

    This is the CANONICAL function for getting Notion tokens.
    All scripts in this workspace MUST use this function.

    **Token Source Priority:**
    1. Environment variable: NOTION_TOKEN
    2. Environment variable: NOTION_API_TOKEN
    3. Environment variable: VV_AUTOMATIONS_WS_TOKEN
    4. Cache file: ~/.notion_token_cache
    5. Config file: ~/.config/notion_script_runner/config.json

    Returns:
        Notion API token string, or None if not found

    Example:
        ```python
        from shared_core.notion.token_manager import get_notion_token

        token = get_notion_token()
        if not token:
            raise RuntimeError("Notion token not available")

        from notion_client import Client
        notion = Client(auth=token)
        ```
    """
    # Try to load .env first
    _load_dotenv()

    # 1. Check environment variables
    token = _load_token_from_env()
    if token:
        return token

    # 2. Check cache file
    token = _load_token_from_cache()
    if token:
        return token

    # 3. Check config file
    token = _load_token_from_config()
    if token:
        return token

    logger.warning(
        "Notion token not found in any source. "
        "Please set NOTION_TOKEN environment variable or create ~/.notion_token_cache"
    )
    return None


def get_notion_client():
    """
    Get a configured Notion client.

    This is a convenience function that creates a Notion client
    with the token from get_notion_token().

    Returns:
        notion_client.Client instance

    Raises:
        ImportError: If notion-client is not installed
        RuntimeError: If token is not available

    Example:
        ```python
        from shared_core.notion.token_manager import get_notion_client

        notion = get_notion_client()
        results = notion.databases.query(database_id="...")
        ```
    """
    try:
        from notion_client import Client
    except ImportError:
        raise ImportError(
            "notion-client package not installed. "
            "Install with: pip install notion-client"
        )

    token = get_notion_token()
    if not token:
        raise RuntimeError(
            "Notion token not available. "
            "Please set NOTION_TOKEN environment variable or create ~/.notion_token_cache"
        )

    return Client(auth=token)


def validate_token(token: Optional[str] = None) -> bool:
    """
    Validate that a Notion token works.

    Args:
        token: Token to validate (uses get_notion_token() if not provided)

    Returns:
        True if token is valid, False otherwise
    """
    if not token:
        token = get_notion_token()

    if not token:
        logger.warning("No token to validate")
        return False

    try:
        from notion_client import Client
        client = Client(auth=token)
        # Try a simple API call to verify token works
        client.users.me()
        logger.debug("Token validation successful")
        return True
    except ImportError:
        logger.warning("notion-client not installed, cannot validate token")
        return False
    except Exception as e:
        logger.warning(f"Token validation failed: {e}")
        return False


def multi_source_token_troubleshoot() -> Dict[str, Any]:
    """
    Perform multi-step troubleshooting process for Notion token validation.

    This implements the MANDATORY multi-step troubleshoot process required
    by workspace methodology when encountering 401/403 errors.

    **Process:**
    1. Detect token format validity (prefix, length)
    2. Enumerate ALL known token sources
    3. Test EACH token source independently
    4. If valid token found in alternate source, report for sync
    5. Only declare failure if ALL sources exhausted

    Returns:
        Dict with troubleshooting results:
        {
            "status": "valid" | "found_alternate" | "all_failed",
            "primary_token_source": str | None,
            "primary_token_valid": bool,
            "sources_checked": List[Dict],
            "valid_token": str | None,
            "valid_token_source": str | None,
            "recommendations": List[str],
            "sync_required": bool
        }
    """
    result = {
        "status": "all_failed",
        "primary_token_source": None,
        "primary_token_valid": False,
        "sources_checked": [],
        "valid_token": None,
        "valid_token_source": None,
        "recommendations": [],
        "sync_required": False
    }

    # Load .env files first
    _load_dotenv()

    # Define all token sources with their retrieval methods
    token_sources = []

    # 1. Environment variables
    for env_var in TOKEN_ENV_VARS:
        token = os.getenv(env_var)
        if token and token.strip():
            token_sources.append({
                "source": f"Environment variable: {env_var}",
                "token": token.strip(),
                "priority": TOKEN_ENV_VARS.index(env_var)
            })

    # 2. Cache file
    cache_token = _load_token_from_cache()
    if cache_token:
        token_sources.append({
            "source": f"Cache file: {TOKEN_CACHE_FILE}",
            "token": cache_token,
            "priority": 100
        })

    # 3. Config file
    config_token = _load_token_from_config()
    if config_token:
        token_sources.append({
            "source": f"Config file: {CONFIG_FILE}",
            "token": config_token,
            "priority": 101
        })

    # 4. Check for project-specific .env files
    project_env_files = [
        Path.cwd() / ".env",
        Path(__file__).parent.parent.parent / ".env",
    ]
    for env_file in project_env_files:
        if env_file.exists():
            try:
                content = env_file.read_text()
                for line in content.split("\n"):
                    line = line.strip()
                    if line.startswith("NOTION_TOKEN=") or line.startswith("NOTION_API_KEY="):
                        key, value = line.split("=", 1)
                        value = value.strip().strip('"').strip("'")
                        if value:
                            token_sources.append({
                                "source": f"Project .env: {env_file}",
                                "token": value,
                                "priority": 50
                            })
            except Exception as e:
                logger.debug(f"Error reading project .env {env_file}: {e}")

    # Identify primary token source (first valid source)
    primary_source = get_token_source()
    result["primary_token_source"] = primary_source

    # Test each token source
    for source_info in token_sources:
        source_name = source_info["source"]
        token = source_info["token"]

        # Check token format
        format_valid = _validate_token_format(token)

        # Test token against API
        api_valid = validate_token(token) if format_valid else False

        source_result = {
            "source": source_name,
            "token_prefix": token[:20] + "..." if len(token) > 20 else token,
            "format_valid": format_valid,
            "api_valid": api_valid
        }
        result["sources_checked"].append(source_result)

        # Track if this is the primary source
        if source_name == primary_source:
            result["primary_token_valid"] = api_valid

        # If we found a valid token, record it
        if api_valid and result["valid_token"] is None:
            result["valid_token"] = token
            result["valid_token_source"] = source_name
            result["status"] = "valid" if source_name == primary_source else "found_alternate"

    # Generate recommendations
    if result["status"] == "found_alternate":
        result["sync_required"] = True
        result["recommendations"].append(
            f"Valid token found in alternate source: {result['valid_token_source']}. "
            f"Sync this token to primary source ({result['primary_token_source']})."
        )
    elif result["status"] == "all_failed":
        result["recommendations"].append(
            "All token sources exhausted. Token regeneration required."
        )
        result["recommendations"].append(
            "Create Issues+Questions entry documenting token mismatch with full diagnostic details."
        )
        result["recommendations"].append(
            "Create Agent-Task for codebase-wide token scrub."
        )

    return result


def _validate_token_format(token: str) -> bool:
    """
    Validate token format (prefix, length, characters).

    Notion API tokens should:
    - Start with 'ntn_' or 'secret_'
    - Be of appropriate length (typically 50+ characters)
    - Contain only alphanumeric characters and underscores

    Returns:
        True if format appears valid, False otherwise
    """
    if not token:
        return False

    # Check prefix
    valid_prefixes = ["ntn_", "secret_"]
    has_valid_prefix = any(token.startswith(p) for p in valid_prefixes)

    # Check length (Notion tokens are typically 50+ characters)
    has_valid_length = len(token) >= 40

    # Check characters (alphanumeric + underscore + hyphen)
    import re
    has_valid_chars = bool(re.match(r'^[a-zA-Z0-9_-]+$', token))

    return has_valid_prefix and has_valid_length and has_valid_chars


def sync_token_to_primary(token: str, primary_source: str = "cache") -> bool:
    """
    Sync a valid token to the primary token storage location.

    Args:
        token: Valid token to sync
        primary_source: Target storage ("cache" or "config")

    Returns:
        True if sync successful, False otherwise
    """
    try:
        if primary_source == "cache":
            TOKEN_CACHE_FILE.write_text(f"NOTION_TOKEN={token}")
            logger.info(f"Token synced to cache file: {TOKEN_CACHE_FILE}")
            return True
        elif primary_source == "config":
            CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
            import json
            config = {}
            if CONFIG_FILE.exists():
                with open(CONFIG_FILE) as f:
                    config = json.load(f)
            config["notion_token"] = token
            with open(CONFIG_FILE, "w") as f:
                json.dump(config, f, indent=2)
            logger.info(f"Token synced to config file: {CONFIG_FILE}")
            return True
    except Exception as e:
        logger.error(f"Failed to sync token: {e}")
    return False


def get_token_source() -> Optional[str]:
    """
    Get the source of the current token (for debugging).

    Returns:
        String describing where token was found, or None if not found
    """
    _load_dotenv()

    for env_var in TOKEN_ENV_VARS:
        if os.getenv(env_var):
            return f"Environment variable: {env_var}"

    if TOKEN_CACHE_FILE.exists():
        try:
            content = TOKEN_CACHE_FILE.read_text().strip()
            if content:
                return f"Cache file: {TOKEN_CACHE_FILE}"
        except:
            pass

    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE) as f:
                config = json.load(f)
                if config.get("notion_token"):
                    return f"Config file: {CONFIG_FILE}"
        except:
            pass

    return None


# Export only what's needed
__all__ = [
    "get_notion_token",
    "get_notion_client",
    "validate_token",
    "get_token_source",
    "multi_source_token_troubleshoot",
    "sync_token_to_primary",
]


# Allow running as script for testing
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)

    print("=" * 60)
    print("Notion Token Manager - Diagnostic")
    print("=" * 60)

    source = get_token_source()
    print(f"\nToken Source: {source or 'NOT FOUND'}")

    token = get_notion_token()
    if token:
        print(f"Token: {token[:20]}...{token[-8:]}")

        print("\nValidating token...")
        if validate_token(token):
            print("Token is VALID")
        else:
            print("Token is INVALID or validation failed")
            print("\nRunning multi-source troubleshoot...")
            result = multi_source_token_troubleshoot()
            print(f"\nTroubleshoot Status: {result['status']}")
            print(f"Primary Source: {result['primary_token_source']}")
            print(f"Primary Valid: {result['primary_token_valid']}")
            print(f"Sync Required: {result['sync_required']}")
            print("\nSources Checked:")
            for src in result['sources_checked']:
                status = "VALID" if src['api_valid'] else ("FORMAT_INVALID" if not src['format_valid'] else "API_FAILED")
                print(f"  - {src['source']}: {status}")
            if result['recommendations']:
                print("\nRecommendations:")
                for rec in result['recommendations']:
                    print(f"  - {rec}")
    else:
        print("\nNo token found!")
        print("\nTo fix, do one of the following:")
        print("  1. Set NOTION_TOKEN environment variable")
        print("  2. Create ~/.notion_token_cache with your token")
        print("  3. Create ~/.config/notion_script_runner/config.json")

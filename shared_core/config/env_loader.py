#!/usr/bin/env python3
"""
Unified Environment Loader
==========================

SINGLE SOURCE OF TRUTH for all environment variables.

This module loads environment variables from the MASTER configuration file
and provides them to all scripts in the codebase.

Usage:
    from shared_core.config.env_loader import load_env, get_env, ENV

    # Option 1: Load and get individual variable
    load_env()
    notion_token = get_env("NOTION_TOKEN")

    # Option 2: Use the ENV object
    from shared_core.config.env_loader import ENV
    notion_token = ENV.NOTION_TOKEN

    # Option 3: Get all environment variables as dict
    all_vars = get_all_env()

Created: 2026-01-30
Author: Claude Code Agent
"""

import os
import sys
from pathlib import Path
from typing import Dict, Optional, Any
from dataclasses import dataclass, field

# Master env file location
MASTER_ENV_PATH = Path(__file__).parent.parent.parent / "config" / "master.env"

# Fallback paths for backward compatibility
FALLBACK_ENV_PATHS = [
    Path(__file__).parent.parent.parent / ".env",
    Path("/Users/brianhellemn/Scripts-MM1/api.env"),
]

_loaded = False
_env_cache: Dict[str, str] = {}


def _parse_env_file(path: Path) -> Dict[str, str]:
    """Parse an env file and return key-value pairs."""
    result = {}

    if not path.exists():
        return result

    try:
        with open(path, 'r') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()

                # Skip empty lines and comments
                if not line or line.startswith('#'):
                    continue

                # Find the first = sign
                if '=' not in line:
                    continue

                key, _, value = line.partition('=')
                key = key.strip()
                value = value.strip()

                # Remove quotes if present
                if (value.startswith('"') and value.endswith('"')) or \
                   (value.startswith("'") and value.endswith("'")):
                    value = value[1:-1]

                if key:
                    result[key] = value

    except Exception as e:
        print(f"Warning: Error parsing {path}: {e}", file=sys.stderr)

    return result


def load_env(force: bool = False) -> bool:
    """
    Load environment variables from the master env file.

    Args:
        force: If True, reload even if already loaded

    Returns:
        True if loaded successfully, False otherwise
    """
    global _loaded, _env_cache

    if _loaded and not force:
        return True

    # Try master env first
    if MASTER_ENV_PATH.exists():
        _env_cache = _parse_env_file(MASTER_ENV_PATH)
    else:
        # Fall back to other env files
        for fallback_path in FALLBACK_ENV_PATHS:
            if fallback_path.exists():
                _env_cache.update(_parse_env_file(fallback_path))

    # Apply to os.environ
    for key, value in _env_cache.items():
        if key not in os.environ:  # Don't override existing
            os.environ[key] = value

    _loaded = True
    return len(_env_cache) > 0


def get_env(key: str, default: Optional[str] = None) -> Optional[str]:
    """
    Get an environment variable.

    Args:
        key: Variable name
        default: Default value if not found

    Returns:
        Variable value or default
    """
    load_env()  # Ensure loaded
    return os.environ.get(key, _env_cache.get(key, default))


def get_all_env() -> Dict[str, str]:
    """Get all environment variables from master config."""
    load_env()
    return _env_cache.copy()


def require_env(key: str) -> str:
    """
    Get a required environment variable.

    Args:
        key: Variable name

    Returns:
        Variable value

    Raises:
        ValueError: If variable not found
    """
    value = get_env(key)
    if value is None:
        raise ValueError(f"Required environment variable {key} not found. "
                        f"Check {MASTER_ENV_PATH}")
    return value


@dataclass
class EnvironmentConfig:
    """
    Type-safe environment configuration.

    Access variables as attributes:
        ENV.NOTION_TOKEN
        ENV.SPOTIFY_CLIENT_ID
    """

    # Notion
    NOTION_TOKEN: str = field(default_factory=lambda: get_env("NOTION_TOKEN", ""))
    NOTION_VIBEVESSELCLIENT_TOKEN: str = field(default_factory=lambda: get_env("NOTION_VIBEVESSELCLIENT_TOKEN", ""))
    NOTION_VIBEVESSEL_AUTOMATIONS_TOKEN: str = field(default_factory=lambda: get_env("NOTION_VIBEVESSEL_AUTOMATIONS_TOKEN", ""))
    NOTION_VIBEVESSEL_MUSIC_TOKEN: str = field(default_factory=lambda: get_env("NOTION_VIBEVESSEL_MUSIC_TOKEN", ""))

    # Database IDs
    TRACKS_DB_ID: str = field(default_factory=lambda: get_env("TRACKS_DB_ID", ""))
    ARTISTS_DB_ID: str = field(default_factory=lambda: get_env("ARTISTS_DB_ID", ""))
    PLAYLISTS_DB_ID: str = field(default_factory=lambda: get_env("PLAYLISTS_DB_ID", ""))
    MUSIC_PLAYLISTS_DB_ID: str = field(default_factory=lambda: get_env("MUSIC_PLAYLISTS_DB_ID", ""))
    SCRIPT_DB_ID: str = field(default_factory=lambda: get_env("SCRIPT_DB_ID", ""))
    LOG_DB_ID: str = field(default_factory=lambda: get_env("LOG_DB_ID", ""))
    MESSAGES_DB_ID: str = field(default_factory=lambda: get_env("MESSAGES_DB_ID", ""))

    # Spotify
    SPOTIFY_CLIENT_ID: str = field(default_factory=lambda: get_env("SPOTIFY_CLIENT_ID", ""))
    SPOTIFY_CLIENT_SECRET: str = field(default_factory=lambda: get_env("SPOTIFY_CLIENT_SECRET", ""))

    # SoundCloud
    SOUNDCLOUD_PROFILE: str = field(default_factory=lambda: get_env("SOUNDCLOUD_PROFILE", ""))

    # File directories
    OUT_DIR: str = field(default_factory=lambda: get_env("OUT_DIR", "/Volumes/VIBES/Playlists"))
    BACKUP_DIR: str = field(default_factory=lambda: get_env("BACKUP_DIR", "/Volumes/VIBES/Djay-Pro-Auto-Import"))
    WAV_BACKUP_DIR: str = field(default_factory=lambda: get_env("WAV_BACKUP_DIR", "/Volumes/VIBES/Apple-Music-Auto-Add"))
    PLAYLIST_TRACKS_DIR: str = field(default_factory=lambda: get_env("PLAYLIST_TRACKS_DIR", "/Volumes/SYSTEM-SSD/Dropbox/Music-Dropbox/playlists/playlist-tracks"))

    # Eagle
    EAGLE_LIBRARY_PATH: str = field(default_factory=lambda: get_env("EAGLE_LIBRARY_PATH", ""))
    EAGLE_API_BASE: str = field(default_factory=lambda: get_env("EAGLE_API_BASE", "http://localhost:41595"))
    EAGLE_TOKEN: str = field(default_factory=lambda: get_env("EAGLE_TOKEN", ""))

    # Google
    GOOGLE_API_KEY: str = field(default_factory=lambda: get_env("GOOGLE_API_KEY", ""))
    GOOGLE_OAUTH_CLIENT_SECRETS_FILE: str = field(default_factory=lambda: get_env("GOOGLE_OAUTH_CLIENT_SECRETS_FILE", ""))
    GOOGLE_OAUTH_TOKEN_DIR: str = field(default_factory=lambda: get_env("GOOGLE_OAUTH_TOKEN_DIR", ""))
    GOOGLE_OAUTH_REDIRECT_URI: str = field(default_factory=lambda: get_env("GOOGLE_OAUTH_REDIRECT_URI", ""))

    # Linear
    LINEAR_API_KEY: str = field(default_factory=lambda: get_env("LINEAR_API_KEY", ""))
    LINEAR_TEAM_ID: str = field(default_factory=lambda: get_env("LINEAR_TEAM_ID", ""))

    # Slack
    SLACK_BOT_TOKEN: str = field(default_factory=lambda: get_env("SLACK_BOT_TOKEN", ""))
    SLACK_WEBHOOK_URL: str = field(default_factory=lambda: get_env("SLACK_WEBHOOK_URL", ""))

    # Compression
    SC_COMP_MODE: str = field(default_factory=lambda: get_env("SC_COMP_MODE", "LOSSLESS"))

    def reload(self):
        """Reload configuration from disk."""
        load_env(force=True)
        # Re-initialize all fields
        self.__init__()


# Global instance - auto-loads on import
load_env()
ENV = EnvironmentConfig()


# For backward compatibility with dotenv
def load_dotenv():
    """Backward compatible wrapper for python-dotenv."""
    return load_env()


__all__ = [
    'load_env',
    'get_env',
    'get_all_env',
    'require_env',
    'ENV',
    'EnvironmentConfig',
    'MASTER_ENV_PATH',
    'load_dotenv',
]

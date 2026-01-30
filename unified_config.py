"""
Local unified configuration utilities stored with the production repo so that
imports never hit iCloud-managed folders.

This module exposes the small helper surface the SoundCloud scripts expect:
loading .env files, returning a dictionary of configuration values, and basic
logging helpers.  It intentionally avoids any dependencies outside this repo.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from shared_core.secret_masking import mask_token

PROJECT_ROOT = Path(__file__).resolve().parent
CLIENTS_ENV_DIR = PROJECT_ROOT / "clients"


def _get_client_slug() -> str | None:
    """Detect current client context from environment or config.
    
    Returns:
        Client slug if detected, None otherwise
    """
    # Check environment variable
    client_slug = os.environ.get("CLIENT_SLUG") or os.environ.get("CLIENT_NAME")
    if client_slug:
        # Normalize to slug format
        import re
        slug = client_slug.lower()
        slug = re.sub(r'[^\w\s-]', '', slug)
        slug = re.sub(r'[-\s]+', '-', slug)
        return slug.strip('-')
    
    # Check for .client file
    client_file = PROJECT_ROOT / ".client"
    if client_file.exists():
        try:
            slug = client_file.read_text(encoding="utf-8").strip()
            if slug:
                return slug
        except Exception:
            pass
    
    return None


def _get_client_env_files() -> Tuple[Path, ...]:
    """Get client-specific env files based on detected context.
    
    Returns:
        Tuple of client env file paths (may be empty)
    """
    client_slug = _get_client_slug()
    if not client_slug:
        return ()
    
    client_env_file = CLIENTS_ENV_DIR / f".env.{client_slug}"
    if client_env_file.exists():
        return (client_env_file,)
    
    return ()


def _get_all_env_files() -> Tuple[Path, ...]:
    """Get all env files in loading order, including client-specific files.
    
    Returns:
        Tuple of env file paths in priority order (later files override earlier)
    """
    base_files: Tuple[Path, ...] = (
        PROJECT_ROOT / ".env",
        PROJECT_ROOT / ".env.local",
    )
    
    client_files = _get_client_env_files()
    
    script_files: Tuple[Path, ...] = (
        PROJECT_ROOT / "scripts" / ".env",
    )
    
    return base_files + client_files + script_files


# ENV_FILES is computed dynamically via _get_all_env_files()
# This allows client context to be detected at runtime
# Note: Do not use ENV_FILES directly - use _get_all_env_files() instead
def get_env_files() -> Tuple[Path, ...]:
    """Get all env files in loading order (including client-specific files)."""
    return _get_all_env_files()

# Legacy ENV_FILES for backward compatibility (deprecated - use get_env_files())
ENV_FILES: Tuple[Path, ...] = _get_all_env_files()

_ENV_CACHE: Dict[str, str] | None = None
_CONFIG_CACHE: Dict[str, Any] | None = None
_ITEM_TYPES_MANAGER: Any | None = None  # Lazy-loaded ItemTypesManager
_LOGGER = logging.getLogger("unified_config")


def _parse_env_file(path: Path) -> Dict[str, str]:
    values: Dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return values
    except OSError as exc:
        _LOGGER.warning("Unable to read %s (%s)", path, exc)
        return values

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            values[key] = value
    return values


def _flag(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _safe_int(value: str | None, default: int) -> int:
    try:
        return int(str(value)) if value not in (None, "") else default
    except (ValueError, TypeError):
        _LOGGER.warning("Invalid integer value %r; using default %s", value, default)
        return default


def load_unified_env(force_reload: bool = False, client_slug: str | None = None) -> Dict[str, str]:
    """Load unified environment variables from all configured env files.
    
    Args:
        force_reload: Force reload even if cache exists
        client_slug: Optional client slug to override auto-detection
    
    Returns:
        Dictionary of environment variables
    """
    global _ENV_CACHE
    if _ENV_CACHE is not None and not force_reload and not client_slug:
        return dict(_ENV_CACHE)

    # Get env files (may include client-specific if context detected)
    if client_slug:
        # Override client context
        import re
        slug = client_slug.lower()
        slug = re.sub(r'[^\w\s-]', '', slug)
        slug = re.sub(r'[-\s]+', '-', slug)
        slug = slug.strip('-')
        client_env_file = CLIENTS_ENV_DIR / f".env.{slug}"
        env_files = (
            PROJECT_ROOT / ".env",
            PROJECT_ROOT / ".env.local",
        )
        if client_env_file.exists():
            env_files = env_files + (client_env_file,)
        env_files = env_files + (PROJECT_ROOT / "scripts" / ".env",)
    else:
        env_files = _get_all_env_files()

    merged: Dict[str, str] = {}
    for candidate in env_files:
        parsed = _parse_env_file(candidate)
        if not parsed:
            continue
        merged.update(parsed)
        for key, value in parsed.items():
            os.environ.setdefault(key, value)

    _ENV_CACHE = merged
    return dict(merged)


def _build_config_from_env() -> Dict[str, Any]:
    """Build configuration dictionary from environment variables.
    
    Supports both uppercase env var names and lowercase config keys.
    Also checks unified env cache for values loaded from .env files.
    """
    # Check unified env cache first (includes .env file values)
    env_cache = _ENV_CACHE or {}
    # Then check os.environ (includes system env vars)
    env = os.environ
    
    # Helper to get value from either source
    def get_env_value(key: str, default: str = "") -> str:
        return env_cache.get(key) or env.get(key, default)
    
    config: Dict[str, Any] = {
        "log_level": get_env_value("LOG_LEVEL", "INFO"),
        "enable_debug": _flag(get_env_value("ENABLE_DEBUG"), default=False),
        "enable_notion_logging": _flag(get_env_value("ENABLE_NOTION_LOGGING"), default=False),
        "notion_token": get_env_value("NOTION_TOKEN") or get_env_value("NOTION_API_TOKEN") or get_env_value("NOTION_API_KEY", ""),
        "archive_workspace_token": get_env_value("ARCHIVE_WORKSPACE_TOKEN", ""),
        "tracks_db_id": (get_env_value("TRACKS_DB_ID") or get_env_value("DATABASE_ID") or get_env_value("MUSIC_TRACKS_DB_ID", "")).strip(),
        "music_directories_db_id": get_env_value("MUSIC_DIRECTORIES_DB_ID", "").strip(),
        "out_dir": get_env_value("OUT_DIR", "/Volumes/VIBES/Playlists"),
        "backup_dir": get_env_value("BACKUP_DIR", "/Volumes/VIBES/Djay-Pro-Auto-Import"),
        "wav_backup_dir": get_env_value("WAV_BACKUP_DIR", "/Volumes/VIBES/Apple-Music-Auto-Add"),
        # NEW 2026-01-16: Playlist tracks directory for new 3-file output structure
        "playlist_tracks_dir": get_env_value("PLAYLIST_TRACKS_DIR", "/Volumes/SYSTEM-SSD/Dropbox/Music-Dropbox/playlists/playlist-tracks"),
        "eagle_wav_temp_dir": get_env_value("EAGLE_WAV_TEMP_DIR", "/Volumes/PROJECTS-MM1/OTHER/TEMP"),
        "eagle_api_url": get_env_value("EAGLE_API_BASE") or get_env_value("EAGLE_BASE_URL", "http://localhost:41595"),
        "eagle_library_path": get_env_value("EAGLE_LIBRARY_PATH", ""),
        "eagle_token": get_env_value("EAGLE_TOKEN", ""),
        "eagle_app_path": get_env_value("EAGLE_APP_PATH", "/Applications/Eagle.app"),
        "eagle_app_name": get_env_value("EAGLE_APP_NAME", "Eagle"),
        "eagle_auto_launch": _flag(get_env_value("EAGLE_AUTO_LAUNCH"), default=True),
        "eagle_auto_launch_timeout": int(get_env_value("EAGLE_AUTO_LAUNCH_TIMEOUT", "45") or 45),
        "compression_mode": get_env_value("SC_COMP_MODE", "LOSSLESS"),
        "temp_dir": get_env_value("TEMP_DIR", "/Volumes/PROJECTS-MM1/OTHER/TEMP"),
        "enable_youtube_fallback": _flag(get_env_value("ENABLE_YOUTUBE_FALLBACK"), default=True),
        "enable_youtube_search": _flag(get_env_value("ENABLE_YOUTUBE_SEARCH"), default=True),
        "google_api_key": get_env_value("GOOGLE_API_KEY", ""),
        "google_oauth_credentials_path": get_env_value("GOOGLE_OAUTH_CREDENTIALS_PATH", ""),
        "google_oauth_token_dir": get_env_value("GOOGLE_OAUTH_TOKEN_DIR", ""),
        "default_youtube_channel": get_env_value("DEFAULT_YOUTUBE_CHANNEL", "VibeVessel"),
        # Agent Coordination Dashboard
        "dashboard_port": _safe_int(get_env_value("DASHBOARD_PORT", "5002"), 5002),
        "dashboard_history_db_path": get_env_value(
            "DASHBOARD_HISTORY_DB_PATH",
            str(Path.home() / ".agent_coordination" / "dashboard_history.db"),
        ),
        "dashboard_history_retention_days": _safe_int(
            get_env_value("DASHBOARD_HISTORY_RETENTION_DAYS", "30"),
            30,
        ),
    }
    
    # Initialize item-types manager cache (lazy, non-blocking)
    try:
        _get_item_types_manager()
    except Exception as e:
        _LOGGER.debug(f"Item-types manager initialization deferred or failed: {e}")
    
    return config


def validate_required_env_vars(required_vars: list[str], raise_on_missing: bool = False) -> dict[str, bool]:
    """
    Validate that required environment variables are set.
    
    Args:
        required_vars: List of required environment variable names
        raise_on_missing: If True, raise ValueError if any are missing
        
    Returns:
        Dictionary mapping variable names to whether they are set
        
    Raises:
        ValueError: If raise_on_missing is True and any variables are missing
    """
    # Ensure env is loaded
    load_unified_env()
    
    results: dict[str, bool] = {}
    missing: list[str] = []
    
    for var in required_vars:
        value = os.getenv(var) or (_ENV_CACHE or {}).get(var)
        is_set = value is not None and value.strip() != ""
        results[var] = is_set
        if not is_set:
            missing.append(var)
    
    if raise_on_missing and missing:
        raise ValueError(
            f"Missing required environment variables: {', '.join(missing)}. "
            f"Please set these in your .env file or environment."
        )
    
    return results


def get_unified_config(force_reload: bool = False) -> Dict[str, Any]:
    """Get unified configuration dictionary.
    
    Automatically loads environment variables from .env files if not already loaded.
    Returns cached config unless force_reload=True.
    
    Args:
        force_reload: Force reload of config even if cache exists
        
    Returns:
        Dictionary of configuration values
    """
    global _CONFIG_CACHE
    # Ensure env vars are loaded before building config
    if _ENV_CACHE is None:
        load_unified_env()
    if _CONFIG_CACHE is None or force_reload:
        _CONFIG_CACHE = _build_config_from_env()
    return dict(_CONFIG_CACHE)


def get_config_value(key: str, default: Any | None = None) -> Any:
    return get_unified_config().get(key, default)


def setup_unified_logging(
    session_id: str = "session",
    log_level: str | None = None,
    enable_notion_logging: bool | None = None,
) -> logging.Logger:
    cfg = get_unified_config()
    level_name = (log_level or cfg.get("log_level") or "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    root = logging.getLogger()
    if not root.handlers:
        formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
        handler = logging.StreamHandler()
        handler.setFormatter(formatter)
        root.addHandler(handler)
    root.setLevel(level)

    logger = logging.getLogger(session_id)
    logger.setLevel(level)
    if not logger.handlers:
        formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
        handler = logging.StreamHandler()
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    logger.propagate = False

    if enable_notion_logging is None:
        enable_notion_logging = cfg.get("enable_notion_logging", False)
    if enable_notion_logging:
        logger.debug("Notion logging requested (no-op in local unified_config).")

    return logger


def get_logger(name: str = "workspace", level: str | None = None) -> logging.Logger:
    logger = logging.getLogger(name)
    if level:
        logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    if not logger.handlers:
        formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
        handler = logging.StreamHandler()
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    logger.propagate = False
    return logger


def get_client_slug() -> str | None:
    """Public wrapper for _get_client_slug().
    
    Returns:
        Client slug if detected, None otherwise
    """
    return _get_client_slug()


def _get_notion_client(auth: Optional[str] = None):
    """Best-effort Notion client loader to avoid hard failures when missing deps."""
    try:
        from notion_client import Client  # type: ignore[import]
    except Exception:
        return None

    # Use centralized token manager (MANDATORY per CLAUDE.md)
    token = auth
    if not token:
        try:
            from shared_core.notion.token_manager import get_notion_token
            token = get_notion_token()
        except ImportError:
            # Fallback for backwards compatibility
            token = os.getenv("NOTION_API_KEY") or os.getenv("NOTION_TOKEN")
    if not token:
        return None
    try:
        return Client(auth=token)
    except Exception:
        return None


def _system_env_db_id() -> Optional[str]:
    """Resolve system-environments database ID with safe defaults."""
    return (
        os.getenv("NOTION_SYSTEM_ENVIRONMENTS_DB_ID")
        or os.getenv("SYSTEM_ENVIRONMENTS_DB_ID")
        or "26ce73616c2781958726f6aeb5b9cd95"
    )


def _build_system_env_properties(
    env_name: str,
    masked_token: str,
    file_path: str,
    env_type: str,
    status: str,
    last_sync_time: Optional[str] = None,
    client_id: Optional[str] = None,
    script_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Construct Notion properties payload for system-environments DB writes."""
    props: Dict[str, Any] = {
        "Name": {"title": [{"text": {"content": env_name}}]},  # Fixed: Use "Name" not "Environment Name"
        "Primary-Token": {"rich_text": [{"text": {"content": masked_token}}]} if masked_token else {"rich_text": []},
        "Token-Masked-Value": {"rich_text": [{"text": {"content": masked_token}}]} if masked_token else {"rich_text": []},
        "Credential-File-Path": {"rich_text": [{"text": {"content": file_path}}]} if file_path else {"rich_text": []},
        "Environment-Type": {"select": {"name": env_type}} if env_type else {"select": None},
        "Status": {"select": {"name": status}} if status else {"select": None},
        "Last-Sync-Time": {"date": {"start": last_sync_time or datetime.now(timezone.utc).isoformat()}},
    }

    if client_id:
        props["Related Client"] = {"relation": [{"id": client_id}]}

    if script_ids:
        props["Related Scripts"] = {"relation": [{"id": s} for s in script_ids if s]}

    return props


def sync_to_system_environments(
    env_name: str,
    token: str,
    file_path: str,
    *,
    env_type: str = "Global",
    status: str = "Active",
    client_id: Optional[str] = None,
    script_ids: Optional[List[str]] = None,
    dry_run: bool = False,
    force: bool = False,
    notion_token: Optional[str] = None,
) -> bool:
    """
    Sync a single environment entry to the system-environments database.

    Writes are masked by default; raw tokens are never persisted.
    """
    if not env_name:
        _LOGGER.error("Environment name is required for system-environment sync")
        return False

    masked = mask_token(token) if token else ""
    db_id = _system_env_db_id()
    props = _build_system_env_properties(
        env_name=env_name,
        masked_token=masked,
        file_path=file_path,
        env_type=env_type,
        status=status,
        client_id=client_id,
        script_ids=script_ids,
    )

    if dry_run:
        _LOGGER.info("Dry-run: would sync %s -> %s", env_name, file_path)
        return True

    client = _get_notion_client(notion_token)
    if not client or not db_id:
        _LOGGER.warning("Notion client or database ID unavailable; cannot sync %s", env_name)
        return False

    try:
        page_id = None
        if not force:
            resp = client.databases.query(
                database_id=db_id,
                filter={"property": "Name", "title": {"equals": env_name}},
                page_size=1,
            )
            if resp.get("results"):
                page_id = resp["results"][0].get("id")

        if page_id:
            client.pages.update(page_id=page_id, properties=props)
        else:
            client.pages.create(parent={"database_id": db_id}, properties=props)

        _LOGGER.info("Synced environment '%s' to system-environments DB", env_name)
        return True
    except Exception as exc:
        _LOGGER.warning("Failed to sync environment '%s': %s", env_name, exc)
        return False


def load_from_system_environments(env_name: str, *, notion_token: Optional[str] = None) -> Dict[str, Any]:
    """Load a single environment entry by name (masked values only)."""
    client = _get_notion_client(notion_token)
    db_id = _system_env_db_id()
    if not client or not db_id:
        _LOGGER.warning("Cannot load system environment; Notion client or DB ID missing")
        return {}

    try:
        resp = client.databases.query(
            database_id=db_id,
            filter={"property": "Name", "title": {"equals": env_name}},
            page_size=1,
        )
        results = resp.get("results") or []
        if not results:
            return {}
        page = results[0]
        props = page.get("properties", {})
        return {
            "env_name": env_name,
            "status": props.get("Status", {}).get("select", {}).get("name"),
            "env_type": props.get("Environment-Type", {}).get("select", {}).get("name"),
            "credential_file_path": props.get("Credential-File-Path", {}).get("rich_text", [{}])[0]
            .get("plain_text", ""),
            "token_masked": props.get("Token-Masked-Value", {}).get("rich_text", [{}])[0].get("plain_text", ""),
            "last_sync_time": props.get("Last-Sync-Time", {}).get("date", {}).get("start"),
            "page_id": page.get("id"),
        }
    except Exception as exc:
        _LOGGER.warning("Failed to load environment '%s': %s", env_name, exc)
        return {}


def list_environments(*, notion_token: Optional[str] = None) -> List[Dict[str, Any]]:
    """List environments from the system-environments database (masked values only)."""
    client = _get_notion_client(notion_token)
    db_id = _system_env_db_id()
    if not client or not db_id:
        _LOGGER.warning("Cannot list system environments; Notion client or DB ID missing")
        return []

    environments: List[Dict[str, Any]] = []
    start_cursor = None
    try:
        while True:
            kwargs = {"database_id": db_id, "page_size": 50}
            if start_cursor:
                kwargs["start_cursor"] = start_cursor
            resp = client.databases.query(**kwargs)
            for page in resp.get("results", []):
                props = page.get("properties", {})
                env_name = ""
                # Fixed: Use "Name" property (matches _build_system_env_properties which uses "Name")
                title_prop = props.get("Name", {}).get("title", [])
                if title_prop:
                    env_name = "".join(t.get("plain_text", "") for t in title_prop)
                environments.append(
                    {
                        "env_name": env_name,
                        "status": props.get("Status", {}).get("select", {}).get("name"),
                        "env_type": props.get("Environment-Type", {}).get("select", {}).get("name"),
                        "credential_file_path": props.get("Credential-File-Path", {}).get("rich_text", [{}])[0]
                        .get("plain_text", ""),
                        "token_masked": props.get("Token-Masked-Value", {}).get("rich_text", [{}])[0]
                        .get("plain_text", ""),
                        "last_sync_time": props.get("Last-Sync-Time", {}).get("date", {}).get("start"),
                        "page_id": page.get("id"),
                    }
                )
            if resp.get("has_more"):
                start_cursor = resp.get("next_cursor")
            else:
                break
    except Exception as exc:
        _LOGGER.warning("Failed to list system environments: %s", exc)
        return environments

    return environments


# Auto-load environment variables on module import
# This ensures env vars are available immediately without explicit load_unified_env() calls
try:
    _load_unified_env_on_import = load_unified_env(force_reload=False)
except Exception as e:
    _LOGGER.warning(f"Failed to auto-load unified env on import: {e}")
    _load_unified_env_on_import = {}

config = get_unified_config()

# Item-Types Database Integration
def _get_item_types_manager(force_refresh: bool = False):
    """Get or create ItemTypesManager instance (lazy-loaded)."""
    global _ITEM_TYPES_MANAGER
    
    if _ITEM_TYPES_MANAGER is None or force_refresh:
        try:
            from sync_config.item_types_manager import get_item_types_manager
            _ITEM_TYPES_MANAGER = get_item_types_manager(force_refresh=force_refresh)
        except ImportError as e:
            _LOGGER.warning(f"Item-types manager not available: {e}")
            _ITEM_TYPES_MANAGER = None
        except Exception as e:
            _LOGGER.warning(f"Failed to initialize item-types manager: {e}")
            _ITEM_TYPES_MANAGER = None
    
    return _ITEM_TYPES_MANAGER


class ConfigurationError(Exception):
    """Raised when configuration cannot be resolved."""
    pass


def get_database_id(
    item_type: str,
    source_path: Optional[str] = None,
    category: Optional[str] = None,
    fallback_db_id: Optional[str] = None
) -> str:
    """
    Get database ID from item-types database with fallback hierarchy.
    
    Priority:
    1. Item-type Default-Synchronization-Database
    2. Category-based lookup (if category provided)
    3. Source path pattern matching (if source_path provided)
    4. Fallback database ID (if provided)
    5. Environment variable lookup (ITEM_TYPE_{item_type}_DB_ID, etc.)
    6. Raise ConfigurationError if none found
    
    Args:
        item_type: Name of the item type (e.g., "Music Track", "PNG Format Image")
        source_path: Optional source file/folder path for pattern matching
        category: Optional category name for category-based lookup
        fallback_db_id: Optional fallback database ID
        
    Returns:
        Database ID string
        
    Raises:
        ConfigurationError: If no database ID can be resolved
    """
    manager = _get_item_types_manager()
    
    # Priority 1: Item-type Default-Synchronization-Database
    if manager:
        db_id = manager.get_database_for_item_type(item_type)
        if db_id:
            _LOGGER.debug(f"Found database ID for item type '{item_type}': {db_id}")
            return db_id
    
    # Priority 2: Category-based lookup
    if category and manager:
        item_types = manager.get_item_types_by_category(category)
        if item_types:
            # Try first item type in category
            db_id = manager.get_database_for_item_type(item_types[0])
            if db_id:
                _LOGGER.debug(f"Found database ID via category '{category}': {db_id}")
                return db_id
    
    # Priority 3: Source path pattern matching (basic implementation)
    # This could be enhanced with more sophisticated pattern matching
    if source_path:
        # Try to infer item type from file extension or path
        path_lower = source_path.lower()
        if path_lower.endswith(('.mp3', '.m4a', '.aiff', '.wav', '.flac')):
            if manager:
                db_id = manager.get_database_for_item_type("Music Track")
                if db_id:
                    _LOGGER.debug(f"Found database ID via source path pattern (audio): {db_id}")
                    return db_id
        elif path_lower.endswith(('.png', '.jpg', '.jpeg', '.tiff', '.tif', '.gif', '.webp')):
            if manager:
                # Try common image types
                for img_type in ["PNG Format Image", "JPEG Format Image", "TIFF Format Image"]:
                    db_id = manager.get_database_for_item_type(img_type)
                    if db_id:
                        _LOGGER.debug(f"Found database ID via source path pattern (image): {db_id}")
                        return db_id
        elif path_lower.endswith(('.mp4', '.mov', '.avi', '.mkv')):
            if manager:
                db_id = manager.get_database_for_item_type("Video Clip")
                if db_id:
                    _LOGGER.debug(f"Found database ID via source path pattern (video): {db_id}")
                    return db_id
    
    # Priority 4: Fallback database ID
    if fallback_db_id:
        _LOGGER.debug(f"Using fallback database ID: {fallback_db_id}")
        return fallback_db_id
    
    # Priority 5: Environment variable lookup
    # Try various env var patterns
    env_patterns = [
        f"ITEM_TYPE_{item_type.upper().replace(' ', '_')}_DB_ID",
        f"{item_type.upper().replace(' ', '_')}_DB_ID",
        f"{item_type.upper().replace(' ', '_')}_DATABASE_ID",
    ]
    
    for pattern in env_patterns:
        db_id = os.getenv(pattern) or (_ENV_CACHE or {}).get(pattern)
        if db_id and db_id.strip():
            _LOGGER.debug(f"Found database ID via env var '{pattern}': {db_id}")
            return db_id.strip()
    
    # Priority 6: Raise error
    raise ConfigurationError(
        f"Cannot resolve database ID for item type '{item_type}'. "
        f"Tried: item-types database, category '{category}', source path pattern, "
        f"fallback, and environment variables. Please set Default-Synchronization-Database "
        f"in item-types database or provide fallback_db_id."
    )


def get_item_type_config(item_type: str) -> Dict[str, Any]:
    """
    Get full item-type configuration including validation rules.
    
    Args:
        item_type: Name of the item type
        
    Returns:
        Dictionary with item-type configuration, or empty dict if not found
    """
    manager = _get_item_types_manager()
    if not manager:
        _LOGGER.warning("Item-types manager not available")
        return {}
    
    config = manager.get_item_type_config(item_type)
    if config:
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
    
    return {}


def get_validation_rules(item_type: str) -> Dict[str, Any]:
    """
    Get Population-Requirements and Validation-Rules for item type.
    
    Args:
        item_type: Name of the item type
        
    Returns:
        Dictionary with 'population_requirements' and 'validation_rules' keys
    """
    manager = _get_item_types_manager()
    if not manager:
        return {"population_requirements": {}, "validation_rules": {}}
    
    return manager.get_validation_rules(item_type)


def validate_item_properties(
    item_type: str,
    properties: Dict[str, Any]
) -> Tuple[bool, List[str]]:
    """
    Validate item properties against item-type requirements.
    
    Args:
        item_type: Name of the item type
        properties: Dictionary of item properties to validate
        
    Returns:
        Tuple of (is_valid, list_of_errors)
    """
    manager = _get_item_types_manager()
    if not manager:
        _LOGGER.warning("Item-types manager not available, skipping validation")
        return True, []
    
    config = manager.get_item_type_config(item_type)
    if not config:
        _LOGGER.warning(f"Item type '{item_type}' not found, skipping validation")
        return True, []
    
    errors = []
    
    # Check population requirements
    pop_reqs = config.population_requirements
    if isinstance(pop_reqs, dict):
        required_fields = pop_reqs.get("required_fields", [])
        for field in required_fields:
            if field not in properties or not properties[field]:
                errors.append(f"Missing required field: {field}")
    
    # Check validation rules
    val_rules = config.validation_rules
    if isinstance(val_rules, dict):
        # Basic validation - can be extended
        field_rules = val_rules.get("field_rules", {})
        for field, rules in field_rules.items():
            if field in properties:
                value = properties[field]
                # Check type
                if "type" in rules:
                    expected_type = rules["type"]
                    if expected_type == "string" and not isinstance(value, str):
                        errors.append(f"Field '{field}' must be a string")
                    elif expected_type == "number" and not isinstance(value, (int, float)):
                        errors.append(f"Field '{field}' must be a number")
                # Check required
                if rules.get("required") and (value is None or value == ""):
                    errors.append(f"Field '{field}' is required")
                # Check min/max length
                if isinstance(value, str):
                    if "min_length" in rules and len(value) < rules["min_length"]:
                        errors.append(f"Field '{field}' must be at least {rules['min_length']} characters")
                    if "max_length" in rules and len(value) > rules["max_length"]:
                        errors.append(f"Field '{field}' must be at most {rules['max_length']} characters")
    
    is_valid = len(errors) == 0
    if not is_valid:
        _LOGGER.warning(f"Validation failed for item type '{item_type}': {errors}")
    
    return is_valid, errors


def refresh_item_types_cache() -> None:
    """Force refresh item-types cache from Notion."""
    manager = _get_item_types_manager(force_refresh=True)
    if manager:
        manager.refresh_cache()




__all__ = [
    "ENV_FILES",
    "CLIENTS_ENV_DIR",
    "config",
    "get_client_slug",
    "get_config_value",
    "get_logger",
    "get_unified_config",
    "load_unified_env",
    "setup_unified_logging",
    "validate_required_env_vars",
    "get_env_files",
    "sync_to_system_environments",
    "load_from_system_environments",
    "list_environments",
    "get_database_id",
    "get_item_type_config",
    "get_validation_rules",
    "validate_item_properties",
    "refresh_item_types_cache",
    "ConfigurationError",
]

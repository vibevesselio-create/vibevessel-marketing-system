#!/usr/bin/env python3
"""
Eagle Library Path Resolution Utilities
========================================

This module provides centralized utilities for resolving file paths for Eagle library items.
Since the Eagle API doesn't return file paths, we construct them from the library structure.

Eagle stores files in: {library_path}/images/{item_id}.info/{filename}.{ext}

Version: 2026-01-12
"""

import logging
import os
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Cache for resolved paths to improve performance
_path_cache: Dict[str, Optional[Path]] = {}
_item_data_cache: Optional[List[dict]] = None


def get_eagle_library_path() -> Optional[Path]:
    """
    Get Eagle library path dynamically from the active Eagle instance.

    Priority order:
    1. Query Eagle API for active library path
    2. Fall back to environment variable / config

    Returns:
        Path to Eagle library if found, None otherwise
    """
    # Try querying Eagle API for active library
    try:
        import urllib.request
        import json
        url = 'http://localhost:41595/api/library/info'
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode('utf-8'))
            lib_data = data.get('data', {})
            if 'library' in lib_data and 'path' in lib_data['library']:
                lib_path = Path(lib_data['library']['path'])
                if lib_path.exists():
                    logger.debug(f"Active Eagle library: {lib_path}")
                    return lib_path
    except Exception as e:
        logger.debug(f"Could not get library path from Eagle API: {e}")

    # Fallback to config/environment
    try:
        from unified_config import get_unified_config
        config = get_unified_config()
        library_path_str = config.get("eagle_library_path") or os.getenv("EAGLE_LIBRARY_PATH", "")

        if library_path_str:
            library_path = Path(library_path_str)
            if library_path.exists():
                return library_path
    except Exception as e:
        logger.debug(f"Could not get Eagle library path from config: {e}")

    return None


def get_eagle_item_file_path(
    item_id: str, 
    ext: str, 
    library_path: Optional[Path] = None
) -> Optional[Path]:
    """
    Get file path for an Eagle item by constructing it from library structure.
    
    Eagle stores files in: {library_path}/images/{item_id}.info/{filename}.{ext}
    
    This is a workaround since the Eagle API doesn't return file paths.
    
    Args:
        item_id: Eagle item ID
        ext: File extension (e.g., 'wav', 'm4a', 'mp3')
        library_path: Path to Eagle library (default: from config)
    
    Returns:
        Path to the file if found, None otherwise
    """
    if not item_id or not ext:
        return None
    
    # Check cache first
    cache_key = f"{item_id}:{ext}"
    if cache_key in _path_cache:
        return _path_cache[cache_key]
    
    # Get library path if not provided
    if not library_path:
        library_path = get_eagle_library_path()
    
    if not library_path or not library_path.exists():
        _path_cache[cache_key] = None
        return None
    
    # Eagle stores files in: {library_path}/images/{item_id}.info/{filename}.{ext}
    info_dir = library_path / "images" / f"{item_id}.info"
    
    if not info_dir.exists() or not info_dir.is_dir():
        _path_cache[cache_key] = None
        return None
    
    # Look for file with matching extension
    # Files might have original names, so search by extension
    audio_extensions = {'.wav', '.m4a', '.mp3', '.flac', '.aiff', '.aif', '.alac', '.m4p'}
    ext_lower = f".{ext.lower()}" if not ext.startswith('.') else ext.lower()
    
    if ext_lower in audio_extensions:
        # Find file with matching extension
        for file_path in info_dir.iterdir():
            if file_path.is_file() and file_path.suffix.lower() == ext_lower:
                # Skip thumbnails and metadata files
                if 'thumbnail' not in file_path.name.lower() and file_path.name != 'metadata.json':
                    _path_cache[cache_key] = file_path
                    return file_path
    
    # Cache None result to avoid repeated filesystem operations
    _path_cache[cache_key] = None
    return None


def resolve_eagle_item_path(
    item: dict, 
    library_path: Optional[Path] = None
) -> Optional[Path]:
    """
    Resolve file path for an Eagle item.
    
    First tries to use the path from item data (if available),
    then falls back to constructing from library structure.
    
    Args:
        item: Eagle item dictionary with 'id', 'ext', and optionally 'path'
        library_path: Path to Eagle library (optional, will be fetched from config if not provided)
    
    Returns:
        Path to the file if found, None otherwise
    """
    if not isinstance(item, dict):
        return None
    
    # Try path from item data first (if API returns it)
    item_path = item.get("path", "")
    if item_path:
        path = Path(item_path)
        if path.exists():
            return path
    
    # Fallback: construct from library structure
    item_id = item.get("id", "")
    ext = item.get("ext", "")
    
    if item_id and ext:
        return get_eagle_item_file_path(item_id, ext, library_path)
    
    return None


def batch_resolve_eagle_item_paths(
    items: List[dict],
    library_path: Optional[Path] = None,
    use_cache: bool = True
) -> Dict[str, Optional[Path]]:
    """
    Batch resolve file paths for multiple Eagle items with caching.
    
    Args:
        items: List of Eagle item dictionaries
        library_path: Path to Eagle library (optional)
        use_cache: If True, use path resolution cache
    
    Returns:
        Dictionary mapping item IDs to resolved paths (or None if not found)
    """
    if not library_path:
        library_path = get_eagle_library_path()
    
    resolved_paths = {}
    
    for item in items:
        item_id = item.get("id", "")
        if not item_id:
            continue
        
        # Check cache first if enabled
        if use_cache:
            ext = item.get("ext", "")
            cache_key = f"{item_id}:{ext}"
            if cache_key in _path_cache:
                resolved_paths[item_id] = _path_cache[cache_key]
                continue
        
        # Resolve path
        path = resolve_eagle_item_path(item, library_path)
        resolved_paths[item_id] = path
        
        # Update cache if enabled
        if use_cache and path:
            ext = item.get("ext", "")
            cache_key = f"{item_id}:{ext}"
            _path_cache[cache_key] = path
    
    return resolved_paths


def clear_path_cache() -> None:
    """Clear the path resolution cache."""
    global _path_cache
    _path_cache.clear()
    logger.debug("Cleared Eagle path resolution cache")


def get_path_cache_stats() -> Dict[str, int]:
    """
    Get statistics about the path resolution cache.
    
    Returns:
        Dictionary with cache statistics
    """
    total = len(_path_cache)
    resolved = sum(1 for p in _path_cache.values() if p is not None)
    unresolved = total - resolved
    
    return {
        "total_cached": total,
        "resolved": resolved,
        "unresolved": unresolved,
        "hit_rate": (resolved / total * 100) if total > 0 else 0.0
    }

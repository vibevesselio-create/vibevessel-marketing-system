#!/usr/bin/env python3
"""
Batch Fingerprint Embedding Script
===================================

Processes existing audio files in the Eagle library and music directories
to compute and embed fingerprints in file metadata, then sync to Eagle tags.

By default, this script processes Eagle library items (not just scanned directories)
to ensure full coverage for fingerprint-dependent deduplication.

This script is designed for Phase 1 of the Eagle Library Fingerprinting System:
- Batch process existing files that don't have fingerprints
- Compute SHA-256 fingerprints
- Embed fingerprints in file metadata (M4A, MP3, FLAC, AIFF)
- Sync fingerprints to Eagle tags
- Update Notion track properties

Version: 2026-01-12
"""

import argparse
import json
import logging
import os
import sys
import time
import urllib.request
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)

try:
    from unified_config import load_unified_env, get_unified_config
except (OSError, ModuleNotFoundError, TimeoutError):
    def load_unified_env() -> None:
        return None
    def get_unified_config() -> Dict[str, Any]:
        return {}

try:
    from shared_core.notion.token_manager import get_notion_client, get_notion_token
except (ImportError, ModuleNotFoundError):
    get_notion_client = None
    get_notion_token = None

# Import fingerprint functions from music_library_remediation
try:
    from scripts.music_library_remediation import (
        compute_file_fingerprint,
        embed_fingerprint_in_metadata,
        extract_fingerprint_from_metadata,
        eagle_fetch_all_items,
        eagle_update_tags,
        update_notion_track_fingerprint,
        scan_directories,
        FileRecord
    )
except ImportError:
    logger.error("Failed to import fingerprint functions from music_library_remediation")
    sys.exit(1)

# Import Eagle path resolution utility (FIX: DEF-CRIT-001 - Path matching fix by Claude Code Audit)
try:
    from scripts.eagle_path_resolution import resolve_eagle_item_path
except ImportError:
    # Fallback if module not available
    def resolve_eagle_item_path(item: dict, library_path=None):
        """Fallback - returns path from item if available."""
        return item.get("path")

# Import Eagle client
try:
    from music_workflow.integrations.eagle.client import get_eagle_client
    EAGLE_CLIENT_AVAILABLE = True
except ImportError:
    EAGLE_CLIENT_AVAILABLE = False
    logger.warning("Eagle client module not available, Eagle integration disabled")


def get_active_eagle_library_path() -> Optional[Path]:
    """
    Get the path to the currently active Eagle library.

    Queries the Eagle API to get the active library path instead of
    relying on hardcoded paths or environment variables.

    Returns:
        Path to active Eagle library, or None if Eagle is not running
    """
    # Try using Eagle client first
    if EAGLE_CLIENT_AVAILABLE:
        try:
            eagle_client = get_eagle_client()
            if eagle_client.is_available():
                lib_info = eagle_client.get_library_info()
                # Library path is in lib_info['library']['path']
                if 'library' in lib_info and 'path' in lib_info['library']:
                    lib_path = Path(lib_info['library']['path'])
                    if lib_path.exists():
                        logger.info(f"Active Eagle library: {lib_path}")
                        return lib_path
        except Exception as e:
            logger.debug(f"Could not get library path via Eagle client: {e}")

    # Fallback: Try direct API call
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
                    logger.info(f"Active Eagle library (via API): {lib_path}")
                    return lib_path
    except Exception as e:
        logger.debug(f"Could not get library path via direct API: {e}")

    # Final fallback: Try environment variable or config
    try:
        config = get_unified_config()
        library_path_str = config.get("eagle_library_path") or os.getenv("EAGLE_LIBRARY_PATH", "")
        if library_path_str:
            lib_path = Path(library_path_str)
            if lib_path.exists():
                logger.info(f"Using configured Eagle library: {lib_path}")
                return lib_path
    except Exception:
        pass

    logger.warning("Could not determine active Eagle library path")
    return None


def sort_eagle_items_like_notion(items: List[Dict[str, Any]], order_mode: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Sort Eagle items to match Notion database sort order.
    
    Args:
        items: List of Eagle item dictionaries
        order_mode: Sort mode (defaults to ORDER_MODE from env/config)
    
    Returns:
        Sorted list of Eagle items matching Notion sort order
    """
    if not items:
        return items
    
    # Get ORDER_MODE from environment or config (default: priority_then_created)
    if order_mode is None:
        try:
            order_mode = os.getenv("SC_ORDER_MODE", "priority_then_created").lower()
        except:
            order_mode = "priority_then_created"
    
    # #region agent log
    import json
    try:
        with open('/Users/brianhellemn/Projects/github-production/.cursor/debug.log', 'a') as f:
            f.write(json.dumps({
                "sessionId": "debug-session",
                "runId": "sort-eagle-items",
                "hypothesisId": "A",
                "location": "batch_fingerprint_embedding.py:sort_eagle_items_like_notion",
                "message": "Sorting Eagle items",
                "data": {"item_count": len(items), "order_mode": order_mode},
                "timestamp": int(time.time() * 1000)
            }) + "\n")
    except:
        pass
    # #endregion
    
    # Sort based on order_mode
    if order_mode == "priority_then_created":
        # Sort by creation date (descending) - Eagle doesn't have priority, so use creation date
        # Eagle items have modificationDate or creationDate fields
        def sort_key(item):
            mod_date = item.get("modificationDate") or item.get("creationDate") or item.get("dateModified") or 0
            name = item.get("name", "").lower()
            return (-mod_date, name)  # Negative for descending
        
        sorted_items = sorted(items, key=sort_key)
    elif order_mode == "priority_then_title":
        # Sort by name (ascending) then creation date (descending)
        def sort_key(item):
            name = item.get("name", "").lower()
            mod_date = item.get("modificationDate") or item.get("creationDate") or item.get("dateModified") or 0
            return (name, -mod_date)
        
        sorted_items = sorted(items, key=sort_key)
    elif order_mode == "title_asc":
        # Sort by name (ascending)
        def sort_key(item):
            return item.get("name", "").lower()
        
        sorted_items = sorted(items, key=sort_key)
    elif order_mode == "created_only":
        # Sort by creation date (descending)
        def sort_key(item):
            mod_date = item.get("modificationDate") or item.get("creationDate") or item.get("dateModified") or 0
            return -mod_date
        
        sorted_items = sorted(items, key=sort_key)
    else:
        # Default: created_time descending
        def sort_key(item):
            mod_date = item.get("modificationDate") or item.get("creationDate") or item.get("dateModified") or 0
            return -mod_date
        
        sorted_items = sorted(items, key=sort_key)
    
    # #region agent log
    try:
        with open('/Users/brianhellemn/Projects/github-production/.cursor/debug.log', 'a') as f:
            f.write(json.dumps({
                "sessionId": "debug-session",
                "runId": "sort-eagle-items",
                "hypothesisId": "A",
                "location": "batch_fingerprint_embedding.py:sort_eagle_items_like_notion",
                "message": "Eagle items sorted",
                "data": {"sorted_count": len(sorted_items), "order_mode": order_mode, "first_item_name": sorted_items[0].get("name", "") if sorted_items else None},
                "timestamp": int(time.time() * 1000)
            }) + "\n")
    except:
        pass
    # #endregion
    
    return sorted_items


def get_configured_eagle_library_path() -> Optional[Path]:
    """Return the configured Eagle library path, if available."""
    try:
        config = get_unified_config()
    except Exception:
        config = {}

    library_path_str = config.get("eagle_library_path") or os.getenv("EAGLE_LIBRARY_PATH", "")
    if not library_path_str:
        return None

    lib_path = Path(library_path_str)
    if lib_path.exists():
        return lib_path

    logger.warning(f"Configured EAGLE_LIBRARY_PATH does not exist: {lib_path}")
    return None


def maybe_switch_eagle_library(target_path: Optional[Path]) -> None:
    """Switch Eagle to the configured library if needed."""
    if not target_path:
        return

    metadata_path = target_path / "metadata.json"
    images_path = target_path / "images"
    if not metadata_path.exists() or not images_path.exists():
        logger.warning(f"EAGLE_LIBRARY_PATH does not look like a library: {target_path}")
        return

    try:
        current_path = None
        try:
            req = urllib.request.Request("http://localhost:41595/api/library/info")
            with urllib.request.urlopen(req, timeout=5) as response:
                data = json.loads(response.read().decode("utf-8"))
                lib_data = data.get("data", {})
                current_path = lib_data.get("library", {}).get("path")
        except Exception:
            current_path = None

        if current_path and Path(current_path) == target_path:
            logger.info(f"Eagle already using configured library: {target_path}")
            return

        payload = json.dumps({"libraryPath": str(target_path)}).encode("utf-8")
        req = urllib.request.Request(
            "http://localhost:41595/api/library/switch",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))
        if data.get("status") != "success":
            logger.warning(f"Failed to switch Eagle library: {data}")
        else:
            logger.info(f"Switched Eagle library to: {target_path}")
    except Exception as e:
        logger.warning(f"Failed to switch Eagle library: {e}")


def sync_fingerprint_to_eagle(
    file_path: str,
    fingerprint: str,
    eagle_base: Optional[str] = None,
    eagle_token: Optional[str] = None,
    eagle_items_by_path: Optional[Dict[str, Dict]] = None,
    eagle_item_id: Optional[str] = None,
    max_retries: int = 3
) -> bool:
    """
    Sync fingerprint to Eagle tags for a file with retry logic.
    
    Optimized to use item ID directly when available, avoiding expensive searches.
    
    Args:
        file_path: Path to the audio file
        fingerprint: Fingerprint hash string
        eagle_base: Eagle API base URL (optional, for direct API)
        eagle_token: Eagle API token (optional, for direct API)
        eagle_items_by_path: Pre-fetched Eagle items indexed by path (optional)
        eagle_item_id: Direct Eagle item ID (optional, preferred for performance)
        max_retries: Maximum number of retry attempts (default: 3)
    
    Returns:
        True if successfully synced, False otherwise
    """
    retry_delays = [1, 2, 4]  # Exponential backoff: 1s, 2s, 4s
    fp_tag = f"fingerprint:{fingerprint.lower()}"
    
    # If we have item ID directly, use it (fastest path)
    if eagle_item_id:
        for attempt in range(max_retries):
            try:
                if EAGLE_CLIENT_AVAILABLE:
                    try:
                        eagle_client = get_eagle_client()
                        if eagle_client.is_available():
                            # Get item to check existing tags
                            item = eagle_client.get_item(eagle_item_id)
                            if item:
                                existing_tags = item.tags if hasattr(item, 'tags') else []
                                has_fp_tag = any(tag.lower().startswith("fingerprint:") for tag in existing_tags)
                                
                                if not has_fp_tag:
                                    if eagle_client.add_tags(eagle_item_id, [fp_tag]):
                                        logger.debug(f"✅ Synced fingerprint to Eagle tags via client (ID): {Path(file_path).name}")
                                        return True
                                else:
                                    # Already has fingerprint tag
                                    return True
                    except Exception as e:
                        if attempt < max_retries - 1:
                            delay = retry_delays[min(attempt, len(retry_delays) - 1)]
                            logger.debug(f"Eagle client sync failed (attempt {attempt + 1}/{max_retries}), retrying in {delay}s: {e}")
                            time.sleep(delay)
                            continue
                
                # Fallback to direct API
                if eagle_base and eagle_token:
                    # Fetch item to get current tags
                    import urllib.request
                    import json
                    url = f"{eagle_base}/api/item/info"
                    payload = json.dumps({"id": eagle_item_id}).encode("utf-8")
                    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
                    with urllib.request.urlopen(req, timeout=10) as response:
                        data = json.loads(response.read().decode("utf-8"))
                        item_data = data.get("data", {})
                        existing_tags = item_data.get("tags", [])
                        has_fp_tag = any(tag.lower().startswith("fingerprint:") for tag in existing_tags)
                        
                        if not has_fp_tag:
                            new_tags = existing_tags + [fp_tag]
                            if eagle_update_tags(eagle_base, eagle_token, eagle_item_id, new_tags):
                                logger.debug(f"✅ Synced fingerprint to Eagle tags via API (ID): {Path(file_path).name}")
                                return True
                        else:
                            return True
            except Exception as e:
                if attempt < max_retries - 1:
                    delay = retry_delays[min(attempt, len(retry_delays) - 1)]
                    logger.debug(f"Exception during Eagle sync (attempt {attempt + 1}/{max_retries}), retrying in {delay}s: {e}")
                    time.sleep(delay)
                else:
                    logger.warning(f"⚠️  Exception during Eagle tag update after {max_retries} attempts: {e}")
                    return False
        
        return False
    
    # Fallback: Use path-based lookup (slower)
    for attempt in range(max_retries):
        try:
            # Try using Eagle client first
            if EAGLE_CLIENT_AVAILABLE:
                try:
                    eagle_client = get_eagle_client()
                    if eagle_client.is_available():
                        # Use path-based lookup only if item_id not available
                        # Try to find item by path using search (less efficient)
                        items = eagle_client.search(limit=10000)
                        matching_item = None
                        for item in items:
                            # Check if path matches (EagleItem has path attribute)
                            item_path = item.path if hasattr(item, 'path') and item.path else None
                            if item_path and item_path == file_path:
                                matching_item = item
                                break
                            # Also handle dict format for backward compatibility
                            if isinstance(item, dict) and item.get('path') == file_path:
                                matching_item = item
                                break
                        
                        if matching_item:
                            item_id = matching_item.id if hasattr(matching_item, 'id') else matching_item.get('id')
                            
                            # Check if tag already exists
                            existing_tags = matching_item.tags if hasattr(matching_item, 'tags') else matching_item.get('tags', [])
                            has_fp_tag = any(tag.lower().startswith("fingerprint:") for tag in existing_tags)
                            
                            if not has_fp_tag:
                                if eagle_client.add_tags(item_id, [fp_tag]):
                                    logger.debug(f"✅ Synced fingerprint to Eagle tags via client: {Path(file_path).name}")
                                    return True
                except Exception as e:
                    if attempt < max_retries - 1:
                        delay = retry_delays[min(attempt, len(retry_delays) - 1)]
                        logger.debug(f"Eagle client sync failed (attempt {attempt + 1}/{max_retries}), retrying in {delay}s: {e}")
                        time.sleep(delay)
                        continue
                    else:
                        logger.debug(f"Eagle client sync failed after {max_retries} attempts, trying direct API: {e}")
            
            # Fallback to direct API
            if eagle_base and eagle_token and eagle_items_by_path:
                if file_path in eagle_items_by_path:
                    eagle_item = eagle_items_by_path[file_path]
                    eagle_item_id = eagle_item.get("id")
                    existing_tags = eagle_item.get("tags", [])
                    
                    # Check if fingerprint tag already exists
                    has_fp_tag = any(tag.lower().startswith("fingerprint:") for tag in existing_tags)
                    if not has_fp_tag:
                        new_tags = existing_tags + [fp_tag]
                        if eagle_update_tags(eagle_base, eagle_token, eagle_item_id, new_tags):
                            logger.debug(f"✅ Synced fingerprint to Eagle tags via API: {Path(file_path).name}")
                            return True
                elif attempt < max_retries - 1:
                    # Item not found in mapping, might be transient - retry
                    delay = retry_delays[min(attempt, len(retry_delays) - 1)]
                    logger.debug(f"Eagle item not found in mapping (attempt {attempt + 1}/{max_retries}), retrying in {delay}s")
                    time.sleep(delay)
                    continue
            
            # If we get here and it's not the last attempt, retry
            if attempt < max_retries - 1:
                delay = retry_delays[min(attempt, len(retry_delays) - 1)]
                logger.debug(f"Eagle sync failed (attempt {attempt + 1}/{max_retries}), retrying in {delay}s")
                time.sleep(delay)
            else:
                logger.warning(f"⚠️  Failed to sync fingerprint to Eagle after {max_retries} attempts: {Path(file_path).name}")
                return False
        
        except Exception as e:
            if attempt < max_retries - 1:
                delay = retry_delays[min(attempt, len(retry_delays) - 1)]
                logger.debug(f"Exception during Eagle sync (attempt {attempt + 1}/{max_retries}), retrying in {delay}s: {e}")
                time.sleep(delay)
            else:
                logger.warning(f"⚠️  Exception during Eagle tag update after {max_retries} attempts: {e}")
                return False
    
    return False


def batch_sync_fingerprints_to_eagle(
    fingerprint_updates: List[Dict[str, Any]],
    eagle_base: Optional[str] = None,
    eagle_token: Optional[str] = None,
    batch_size: int = 50,
    max_retries: int = 3
) -> Dict[str, Any]:
    """
    Batch sync fingerprints to Eagle tags for better performance.
    
    Args:
        fingerprint_updates: List of dicts with keys: file_path, fingerprint, eagle_item_id (optional)
        eagle_base: Eagle API base URL
        eagle_token: Eagle API token
        batch_size: Number of items to process per batch (default: 50)
        max_retries: Maximum retry attempts per batch (default: 3)
    
    Returns:
        Dictionary with statistics: succeeded, failed, skipped, errors
    """
    stats = {
        "succeeded": 0,
        "failed": 0,
        "skipped": 0,
        "errors": []
    }
    
    if not fingerprint_updates:
        return stats
    
    logger.info(f"Batch syncing {len(fingerprint_updates)} fingerprints to Eagle tags...")
    
    # Process in batches
    for batch_start in range(0, len(fingerprint_updates), batch_size):
        batch = fingerprint_updates[batch_start:batch_start + batch_size]
        batch_num = (batch_start // batch_size) + 1
        total_batches = (len(fingerprint_updates) + batch_size - 1) // batch_size
        
        logger.debug(f"Processing batch {batch_num}/{total_batches} ({len(batch)} items)...")
        
        for update in batch:
            file_path = update.get("file_path")
            fingerprint = update.get("fingerprint")
            eagle_item_id = update.get("eagle_item_id")
            
            if not file_path or not fingerprint:
                stats["skipped"] += 1
                continue
            
            # Check if already has fingerprint tag (skip if present)
            if eagle_item_id and EAGLE_CLIENT_AVAILABLE:
                try:
                    eagle_client = get_eagle_client()
                    if eagle_client.is_available():
                        item = eagle_client.get_item(eagle_item_id)
                        if item:
                            existing_tags = item.tags if hasattr(item, 'tags') else []
                            has_fp_tag = any(tag.lower().startswith("fingerprint:") for tag in existing_tags)
                            if has_fp_tag:
                                stats["skipped"] += 1
                                continue
                except Exception:
                    pass  # Continue with sync attempt
            
            # Sync fingerprint
            success = sync_fingerprint_to_eagle(
                file_path=file_path,
                fingerprint=fingerprint,
                eagle_base=eagle_base,
                eagle_token=eagle_token,
                eagle_item_id=eagle_item_id,
                max_retries=max_retries
            )
            
            if success:
                stats["succeeded"] += 1
            else:
                stats["failed"] += 1
                stats["errors"].append({
                    "file": file_path,
                    "error": "Failed to sync fingerprint"
                })
        
        # Small delay between batches to avoid overwhelming Eagle API
        if batch_start + batch_size < len(fingerprint_updates):
            time.sleep(0.1)
    
    logger.info(f"Batch sync complete: {stats['succeeded']} succeeded, {stats['failed']} failed, {stats['skipped']} skipped")
    return stats


# Import shared utility function
try:
    from scripts.eagle_path_resolution import get_eagle_item_file_path, resolve_eagle_item_path
except ImportError:
    # Fallback if import fails
    def get_eagle_item_file_path(item_id: str, ext: str, library_path: Optional[Path] = None) -> Optional[Path]:
        """Fallback implementation - should use shared utility from eagle_path_resolution."""
        from scripts.eagle_path_resolution import get_eagle_item_file_path as _get_path
        return _get_path(item_id, ext, library_path)
    
    def resolve_eagle_item_path(item: dict, library_path: Optional[Path] = None) -> Optional[Path]:
        """Fallback implementation - should use shared utility from eagle_path_resolution."""
        from scripts.eagle_path_resolution import resolve_eagle_item_path as _resolve
        return _resolve(item, library_path)


def _process_single_item(
    item: Dict[str, Any],
    execute: bool,
    library_path: Optional[Path],
    eagle_base: Optional[str],
    eagle_token: Optional[str],
    notion: Optional[Any],
    tracks_db_id: Optional[str],
    stats_lock: Lock,
    stats: Dict[str, Any],
    fix_missing_tags_mode: bool = False
) -> Dict[str, Any]:
    """
    Process a single Eagle item for fingerprint embedding (worker function for parallel processing).
    
    Args:
        fix_missing_tags_mode: If True, also process items that have metadata fingerprints but missing Eagle tags
    
    Returns:
        Dict with processing result for this item
    """
    from scripts.eagle_path_resolution import get_eagle_item_file_path
    
    result = {
        "item_id": item.get("id", ""),
        "status": "pending",
        "skipped_reason": None,
        "error": None
    }
    
    item_id = item.get("id", "")
    if not item_id:
        result["status"] = "skipped"
        result["skipped_reason"] = "no_id"
        with stats_lock:
            stats["total_scanned"] = stats.get("total_scanned", 0) + 1
        return result
    
    # Try to get file path
    item_path = item.get("path", "")
    ext = item.get("ext", "")
    
    if item_path:
        file_path = Path(item_path)
        if not file_path.exists():
            file_path = get_eagle_item_file_path(item_id, ext, library_path)
    else:
        file_path = get_eagle_item_file_path(item_id, ext, library_path)
    
    if not file_path or not file_path.exists():
        result["status"] = "skipped"
        result["skipped_reason"] = "file_not_found"
        with stats_lock:
            stats["total_scanned"] = stats.get("total_scanned", 0) + 1
        return result
    
    # Skip unsupported formats early (shouldn't reach here if filtering works, but double-check)
    SUPPORTED_FORMATS = {'.m4a', '.mp4', '.aac', '.alac', '.mp3', '.flac', '.aiff', '.aif', '.wav'}
    if file_path.suffix.lower() not in SUPPORTED_FORMATS:
        result["status"] = "skipped"
        result["skipped_reason"] = "unsupported_format"
        with stats_lock:
            stats["total_scanned"] = stats.get("total_scanned", 0) + 1
        return result
    
    # Check if WAV file (will process but skip file metadata embedding)
    is_wav = file_path.suffix.lower() == '.wav'
    
    # Check if fingerprint already exists in metadata (for non-WAV files)
    existing_fp = extract_fingerprint_from_metadata(str(file_path))
    
    # Check if Eagle tag exists
    item_tags = item.get("tags", [])
    has_eagle_fp_tag = any(tag.lower().startswith("fingerprint:") for tag in item_tags)
    
    # In fix_missing_tags_mode, process items that have metadata fingerprint but missing Eagle tag
    if fix_missing_tags_mode:
        if existing_fp and not has_eagle_fp_tag:
            # Has metadata fingerprint but missing Eagle tag - sync tag only
            with stats_lock:
                stats["total_scanned"] = stats.get("total_scanned", 0) + 1
                stats["missing_eagle_tag"] = stats.get("missing_eagle_tag", 0) + 1
            
            if not execute:
                result["status"] = "planned"
                result["action"] = "sync_tag_only"
                return result
            
            # Execute: sync fingerprint to Eagle tag
            try:
                with stats_lock:
                    stats["processed"] = stats.get("processed", 0) + 1
                    processed_count = stats["processed"]
                
                logger.info(f"[{processed_count}/∞] Syncing fingerprint tag for {file_path.name}...")
                
                # Sync to Eagle tags
                if sync_fingerprint_to_eagle(
                    str(file_path),
                    existing_fp,
                    eagle_base,
                    eagle_token,
                    {item_path: item} if item_path else None,
                    eagle_item_id=item_id
                ):
                    with stats_lock:
                        stats["eagle_synced"] = stats.get("eagle_synced", 0) + 1
                        stats["succeeded"] = stats.get("succeeded", 0) + 1
                    logger.info(f"  ✅ Synced fingerprint tag to Eagle")
                    result["status"] = "succeeded"
                    result["action"] = "sync_tag_only"
                else:
                    with stats_lock:
                        stats["failed"] = stats.get("failed", 0) + 1
                        error_msg = f"Failed to sync fingerprint tag for {file_path.name}"
                        stats["errors"] = stats.get("errors", [])
                        stats["errors"].append({"file": str(file_path), "error": error_msg})
                    logger.warning(f"  ⚠️  {error_msg}")
                    result["status"] = "failed"
                    result["error"] = error_msg
                
                return result
            except Exception as e:
                with stats_lock:
                    stats["failed"] = stats.get("failed", 0) + 1
                    error_msg = f"Error syncing fingerprint tag for {file_path.name}: {e}"
                    stats["errors"] = stats.get("errors", [])
                    stats["errors"].append({"file": str(file_path), "error": str(e)})
                logger.error(f"  ❌ {error_msg}")
                result["status"] = "failed"
                result["error"] = str(e)
                return result
        elif existing_fp and has_eagle_fp_tag:
            # Has both metadata fingerprint and Eagle tag - skip
            result["status"] = "skipped"
            result["skipped_reason"] = "already_complete"
            with stats_lock:
                stats["total_scanned"] = stats.get("total_scanned", 0) + 1
                stats["already_complete"] = stats.get("already_complete", 0) + 1
            return result
    
    # Standard mode: skip if fingerprint already exists in metadata
    if existing_fp:
        result["status"] = "skipped"
        result["skipped_reason"] = "already_has_fingerprint"
        with stats_lock:
            stats["total_scanned"] = stats.get("total_scanned", 0) + 1
            stats["already_has_fingerprint"] = stats.get("already_has_fingerprint", 0) + 1
        return result
    
    # Plan fingerprint computation
    with stats_lock:
        stats["total_scanned"] = stats.get("total_scanned", 0) + 1
        stats["planned"] = stats.get("planned", 0) + 1
    
    if not execute:
        result["status"] = "planned"
        return result
    
    # Execute: compute and embed fingerprint
    try:
        with stats_lock:
            stats["processed"] = stats.get("processed", 0) + 1
            processed_count = stats["processed"]
        
        logger.info(f"[{processed_count}/∞] Processing {file_path.name}...")
        fingerprint = compute_file_fingerprint(file_path)
        
        # Check if WAV file (will skip file metadata embedding but still sync to Eagle/Notion)
        is_wav = file_path.suffix.lower() == '.wav'
        
        # #region agent log
        import json
        try:
            with open('/Users/brianhellemn/Projects/github-production/.cursor/debug.log', 'a') as f:
                f.write(json.dumps({
                    "sessionId": "debug-session",
                    "runId": "verify-updates",
                    "hypothesisId": "A",
                    "location": "batch_fingerprint_embedding.py:_process_single_item",
                    "message": "Fingerprint computed",
                    "data": {"item_id": item_id, "file_path": str(file_path), "fingerprint": fingerprint[:16] + "..." if fingerprint else None, "is_wav": is_wav},
                    "timestamp": int(time.time() * 1000)
                }) + "\n")
        except:
            pass
        # #endregion
        
        # For WAV files, skip file metadata embedding but still sync to Eagle and Notion
        if is_wav:
            logger.info(f"  ⏭️  WAV file - skipping file metadata embedding (limited metadata support)")
            success = True  # Treat as success for WAV files
            skip_reason = None
        else:
            # Embed fingerprint in file metadata for supported formats
            # #region agent log
            try:
                with open('/Users/brianhellemn/Projects/github-production/.cursor/debug.log', 'a') as f:
                    f.write(json.dumps({
                        "sessionId": "debug-session",
                        "runId": "verify-updates",
                        "hypothesisId": "A",
                        "location": "batch_fingerprint_embedding.py:_process_single_item",
                        "message": "BEFORE local file metadata embed",
                        "data": {"item_id": item_id, "file_path": str(file_path)},
                        "timestamp": int(time.time() * 1000)
                    }) + "\n")
            except:
                pass
            # #endregion
            
            success, skip_reason = embed_fingerprint_in_metadata(str(file_path), fingerprint)
            
            # #region agent log
            try:
                with open('/Users/brianhellemn/Projects/github-production/.cursor/debug.log', 'a') as f:
                    f.write(json.dumps({
                        "sessionId": "debug-session",
                        "runId": "verify-updates",
                        "hypothesisId": "A",
                        "location": "batch_fingerprint_embedding.py:_process_single_item",
                        "message": "AFTER local file metadata embed",
                        "data": {"item_id": item_id, "file_path": str(file_path), "success": success, "skip_reason": skip_reason},
                        "timestamp": int(time.time() * 1000)
                    }) + "\n")
            except:
                pass
            # #endregion
        
        if success:
            with stats_lock:
                stats["succeeded"] = stats.get("succeeded", 0) + 1
            if not is_wav:
                logger.info(f"  ✅ Embedded fingerprint in metadata")
            else:
                logger.info(f"  ✅ Computed fingerprint (WAV - skipping file metadata)")
            
            # Sync to Eagle tags (pass item_id for better performance)
            if item_id:
                # #region agent log
                try:
                    with open('/Users/brianhellemn/Projects/github-production/.cursor/debug.log', 'a') as f:
                        f.write(json.dumps({
                            "sessionId": "debug-session",
                            "runId": "verify-updates",
                            "hypothesisId": "B",
                            "location": "batch_fingerprint_embedding.py:_process_single_item",
                            "message": "BEFORE Eagle tag sync",
                            "data": {"item_id": item_id, "file_path": str(file_path), "fingerprint": fingerprint[:16] + "..." if fingerprint else None},
                            "timestamp": int(time.time() * 1000)
                        }) + "\n")
                except:
                    pass
                # #endregion
                
                eagle_sync_result = sync_fingerprint_to_eagle(
                    str(file_path),
                    fingerprint,
                    eagle_base,
                    eagle_token,
                    {item_path: item} if item_path else None,
                    eagle_item_id=item_id
                )
                
                # #region agent log
                try:
                    with open('/Users/brianhellemn/Projects/github-production/.cursor/debug.log', 'a') as f:
                        f.write(json.dumps({
                            "sessionId": "debug-session",
                            "runId": "verify-updates",
                            "hypothesisId": "B",
                            "location": "batch_fingerprint_embedding.py:_process_single_item",
                            "message": "AFTER Eagle tag sync",
                            "data": {"item_id": item_id, "file_path": str(file_path), "eagle_sync_success": eagle_sync_result},
                            "timestamp": int(time.time() * 1000)
                        }) + "\n")
                except:
                    pass
                # #endregion
                
                if eagle_sync_result:
                    with stats_lock:
                        stats["eagle_synced"] = stats.get("eagle_synced", 0) + 1
                    logger.info(f"  ✅ Synced fingerprint to Eagle tags")
                else:
                    logger.warning(f"  ⚠️  Failed to sync fingerprint to Eagle tags")
            
            # Update Notion track if linked
            if notion and tracks_db_id:
                logger.debug(f"  🔄 Attempting Notion update for: {file_path.name}")
                notion_update_result = update_notion_track_fingerprint(notion, tracks_db_id, str(file_path), fingerprint)
                
                if notion_update_result:
                    with stats_lock:
                        stats["notion_updated"] = stats.get("notion_updated", 0) + 1
                    logger.info(f"  ✅ Updated Notion track")
                else:
                    logger.warning(f"  ⚠️  Failed to update Notion track (file may not be linked in Notion database)")
                    logger.debug(f"      File path: {file_path}")
                    logger.debug(f"      Tracks DB ID: {tracks_db_id[:8]}...")
            elif not notion:
                logger.debug(f"  ⏭️  Notion client not available - skipping Notion update")
            elif not tracks_db_id:
                logger.warning(f"  ⚠️  Notion tracks DB ID not configured - skipping Notion update")
                logger.debug(f"      Set TRACKS_DB_ID environment variable or configure in unified_config")
            
            result["status"] = "succeeded"
        
        elif skip_reason == "unsupported_format":
            with stats_lock:
                stats["skipped"] = stats.get("skipped", 0) + 1
            logger.debug(f"  ⏭️  Skipped unsupported format: {file_path.name} ({file_path.suffix})")
            result["status"] = "skipped"
            result["skipped_reason"] = "unsupported_format"
        
        else:
            with stats_lock:
                stats["failed"] = stats.get("failed", 0) + 1
                error_msg = f"Failed to embed fingerprint in {file_path.name}"
                stats["errors"] = stats.get("errors", [])
                stats["errors"].append({"file": str(file_path), "error": error_msg})
            logger.warning(f"  ⚠️  {error_msg}")
            result["status"] = "failed"
            result["error"] = error_msg
    
    except Exception as e:
        with stats_lock:
            stats["failed"] = stats.get("failed", 0) + 1
            error_msg = f"Error processing {file_path.name}: {e}"
            stats["errors"] = stats.get("errors", [])
            stats["errors"].append({"file": str(file_path), "error": str(e)})
        logger.error(f"  ❌ {error_msg}")
        result["status"] = "failed"
        result["error"] = str(e)
    
    return result


def process_eagle_items_fingerprint_embedding(
    execute: bool = False,
    limit: Optional[int] = None,
    eagle_base: Optional[str] = None,
    eagle_token: Optional[str] = None,
    notion: Optional[Any] = None,
    tracks_db_id: Optional[str] = None,
    max_workers: int = 4,
    checkpoint_file: Optional[Path] = None,
    resume: bool = False,
    fix_missing_tags_mode: bool = False
) -> Dict[str, Any]:
    """
    Process fingerprint embedding for all Eagle library items.
    
    Args:
        execute: If True, actually embed fingerprints; otherwise dry-run
        limit: Maximum number of items to process (None for all)
        eagle_base: Eagle API base URL
        eagle_token: Eagle API token
        notion: Notion client (optional)
        tracks_db_id: Notion tracks database ID (optional)
        max_workers: Number of parallel workers (default: 4)
        checkpoint_file: Path to checkpoint file for progress tracking
        resume: If True, resume from last checkpoint
    
    Returns:
        Dictionary with processing statistics
    """
    logger.info("=" * 80)
    logger.info("EAGLE ITEMS FINGERPRINT EMBEDDING")
    logger.info("=" * 80)
    logger.info(f"Mode: {'EXECUTE' if execute else 'DRY RUN'}")
    if fix_missing_tags_mode:
        logger.info(f"Target Mode: Fix Missing Tags (process items missing Eagle fingerprint tags)")
    else:
        logger.info(f"Target Mode: Standard (process items without metadata fingerprints)")
    logger.info(f"Limit: {limit if limit else 'None (all items)'} items")
    
    # #region agent log
    try:
        with open('/Users/brianhellemn/Projects/github-production/.cursor/debug.log', 'a') as f:
            import json
            f.write(json.dumps({
                "sessionId": "debug-session",
                "runId": "limit-debug",
                "hypothesisId": "ALL",
                "location": "batch_fingerprint_embedding.py:process_eagle_items_fingerprint_embedding",
                "message": "Function entry - limit parameter received",
                "data": {
                    "limit": limit,
                    "limit_type": type(limit).__name__,
                    "execute": execute
                },
                "timestamp": int(time.time() * 1000)
            }) + "\n")
    except:
        pass
    # #endregion
    
    # Initialize progress tracker
    from scripts.fingerprint_progress_tracker import FingerprintProgressTracker
    tracker = FingerprintProgressTracker(checkpoint_file)
    
    # Load checkpoint if resuming
    resume_info = None
    if resume:
        resume_info = tracker.get_resume_info()
        if resume_info:
            logger.info(f"Resuming from checkpoint:")
            logger.info(f"  Last processed: {resume_info.get('last_processed_item_id', 'N/A')}")
            logger.info(f"  Previously processed: {resume_info.get('processed_count', 0)} items")
            logger.info(f"  Previously succeeded: {resume_info.get('succeeded_count', 0)}")
        else:
            logger.info("No checkpoint found - starting fresh")
    
    logger.info("")
    
    configured_library_path = get_configured_eagle_library_path()
    if configured_library_path:
        maybe_switch_eagle_library(configured_library_path)

    library_path = configured_library_path or get_active_eagle_library_path()

    # Fetch all Eagle items
    logger.info("Fetching Eagle items...")
    
    # Try using Eagle client first (returns items with paths)
    eagle_items = []
    if EAGLE_CLIENT_AVAILABLE:
        try:
            eagle_client = get_eagle_client()
            if eagle_client.is_available():
                logger.info("Using Eagle client to fetch items...")
                # Search with high limit to get all items
                client_items = eagle_client.search(limit=50000)
                logger.info(f"Eagle client returned {len(client_items)} items")
                
                # Convert EagleItem objects to dicts
                # Note: Search doesn't return paths, and get_item() also doesn't return paths
                # We'll construct paths from library structure instead
                logger.info(f"Processing {len(client_items)} items, constructing file paths from library structure...")
                
                if not library_path:
                    logger.warning("Could not determine Eagle library path for item resolution")

                batch_size = 1000
                for i, item in enumerate(client_items):
                    if i % batch_size == 0 and i > 0:
                        logger.info(f"  Processed {i}/{len(client_items)} items, found {len(eagle_items)} with file paths...")
                    
                    # Construct file path from library structure
                    item_id = item.id
                    ext = item.ext if hasattr(item, 'ext') else ""
                    
                    if not ext:
                        continue
                    
                    file_path = get_eagle_item_file_path(item_id, ext, library_path)
                    if file_path and file_path.exists():
                        eagle_items.append({
                            "id": item_id,
                            "name": item.name if hasattr(item, 'name') else "",
                            "path": str(file_path),  # Use constructed path
                            "tags": item.tags if hasattr(item, 'tags') else [],
                            "ext": ext
                        })
                
                logger.info(f"Found {len(eagle_items)} Eagle items with file paths out of {len(client_items)} total items")
        except Exception as e:
            logger.warning(f"Eagle client failed, falling back to direct API: {e}")
            import traceback
            traceback.print_exc()
    
    # Fallback to direct API if client didn't work or not available
    if not eagle_items and eagle_base and eagle_token:
        try:
            logger.info("Using direct API to fetch items...")
            api_items = eagle_fetch_all_items(eagle_base, eagle_token, limit=50000)
            # Direct API doesn't return paths, so we need to fetch item details
            # This is slow, so we'll only do it if client isn't available
            if EAGLE_CLIENT_AVAILABLE:
                try:
                    eagle_client = get_eagle_client()
                    if eagle_client.is_available():
                        logger.info("Fetching item details for paths...")
                        for item in api_items[:1000]:  # Limit to first 1000 for performance
                            item_id = item.get("id")
                            if item_id:
                                full_item = eagle_client.get_item(item_id)
                                if full_item and full_item.path:
                                    eagle_items.append({
                                        "id": full_item.id,
                                        "name": full_item.name,
                                        "path": full_item.path,
                                        "tags": full_item.tags,
                                        "ext": full_item.ext
                                    })
                        logger.info(f"Fetched paths for {len(eagle_items)} items (limited to 1000)")
                except:
                    pass
            else:
                logger.warning("Cannot fetch item paths - Eagle client not available and direct API doesn't return paths")
                return {"error": "Cannot fetch item paths without Eagle client"}
        except Exception as e:
            logger.error(f"Failed to fetch Eagle items: {e}")
            return {"error": str(e)}
    
    if not eagle_items:
        logger.error("No Eagle items found or unable to get item paths")
        return {"error": "No Eagle items found or unable to get item paths"}
    
    logger.info(f"Found {len(eagle_items)} Eagle items with file paths")
    
    # Sort Eagle items to match Notion database sort order
    logger.info("Sorting Eagle items to match Notion database sort order...")
    try:
        order_mode = os.getenv("SC_ORDER_MODE", "priority_then_created").lower()
        eagle_items = sort_eagle_items_like_notion(eagle_items, order_mode)
        logger.info(f"✅ Eagle items sorted using order mode: {order_mode}")
    except Exception as e:
        logger.warning(f"⚠️  Failed to sort Eagle items: {e}, continuing with unsorted items")
    
    if not eagle_items:
        logger.warning("No Eagle items found")
        return {
            "total_scanned": 0,
            "already_has_fingerprint": 0,
            "planned": 0,
            "processed": 0,
            "succeeded": 0,
            "failed": 0,
            "eagle_synced": 0,
            "notion_updated": 0,
            "errors": []
        }
    
    # Debug: Log sample item structure
    if eagle_items:
        sample_item = eagle_items[0]
        logger.info(f"Sample item keys: {list(sample_item.keys()) if isinstance(sample_item, dict) else 'Not a dict'}")
        logger.info(f"Sample item path: {sample_item.get('path', 'NO PATH') if isinstance(sample_item, dict) else 'Not a dict'}")
        # Check for alternative path fields
        if isinstance(sample_item, dict):
            for key in ['filePath', 'file_path', 'ext', 'extension', 'url', 'ext', 'id', 'name']:
                if key in sample_item:
                    logger.info(f"Sample item {key}: {sample_item[key]}")
        
        # Count items with paths
        items_with_paths = sum(1 for item in eagle_items[:100] if isinstance(item, dict) and item.get("path"))
        logger.info(f"Items with paths (first 100): {items_with_paths}/100")
    
    # Process items
    stats = {
        "total_scanned": len(eagle_items),
        "already_has_fingerprint": 0,
        "already_complete": 0,  # Has both metadata fingerprint and Eagle tag
        "missing_eagle_tag": 0,  # Has metadata fingerprint but missing Eagle tag
        "planned": 0,
        "processed": 0,
        "succeeded": 0,
        "failed": 0,
        "skipped": 0,
        "eagle_synced": 0,
        "notion_updated": 0,
        "errors": []
    }
    
    logger.info("")
    logger.info("Processing Eagle items...")
    if execute:
        logger.info(f"Using {max_workers} parallel workers")
    
    skipped_no_path = 0
    skipped_not_exists = 0
    skipped_unsupported_format = 0
    
    # Supported formats for fingerprint embedding
    SUPPORTED_FORMATS = {'.m4a', '.mp4', '.aac', '.alac', '.mp3', '.flac', '.aiff', '.aif'}
    
    if not library_path:
        library_path = get_active_eagle_library_path()
    
    # Prepare items for processing (filter out items that should be skipped early)
    # Also filter out already-processed items if resuming
    items_to_process = []
    skipped_already_processed = 0
    
    # Early termination: stop scanning once we have enough items to process
    items_found = 0

    for item in eagle_items:
        # #region agent log
        try:
            with open('/Users/brianhellemn/Projects/github-production/.cursor/debug.log', 'a') as f:
                import json
                f.write(json.dumps({
                    "sessionId": "debug-session",
                    "runId": "limit-debug",
                    "hypothesisId": "H1",
                    "location": "batch_fingerprint_embedding.py:process_eagle_items_fingerprint_embedding",
                    "message": "Loop iteration start",
                    "data": {
                        "items_found": items_found,
                        "limit": limit,
                        "items_to_process_len": len(items_to_process),
                        "early_termination_check": limit is not None and items_found >= limit
                    },
                    "timestamp": int(time.time() * 1000)
                }) + "\n")
        except:
            pass
        # #endregion
        
        # Early termination if we've found enough items and limit is set
        if limit is not None and items_found >= limit:
            logger.info(f"Found {items_found} items matching criteria, stopping scan early (limit: {limit})")
            break
        item_id = item.get("id", "")
        if not item_id:
            skipped_no_path += 1
            continue
        
        # Try to get file path
        item_path = item.get("path", "")
        ext = item.get("ext", "")
        
        if item_path:
            file_path = Path(item_path)
            if not file_path.exists():
                file_path = get_eagle_item_file_path(item_id, ext, library_path)
        else:
            file_path = get_eagle_item_file_path(item_id, ext, library_path)
        
        if not file_path or not file_path.exists():
            skipped_not_exists += 1
            continue
        
        # Note: WAV files will be processed but fingerprint won't be embedded in file metadata
        # (WAV has limited metadata support, but we can still sync to Eagle tags and Notion)
        
        # Skip unsupported formats early (before expensive operations)
        ext_lower = file_path.suffix.lower()
        if ext_lower not in SUPPORTED_FORMATS:
            skipped_unsupported_format += 1
            continue
        
        # Check if fingerprint already exists in metadata
        existing_fp = extract_fingerprint_from_metadata(str(file_path))
        
        # Check if Eagle tag exists
        item_tags = item.get("tags", [])
        has_eagle_fp_tag = any(tag.lower().startswith("fingerprint:") for tag in item_tags)
        
        # In fix_missing_tags_mode, include items that have metadata fingerprint but missing Eagle tag
        if fix_missing_tags_mode:
            # #region agent log
            try:
                with open('/Users/brianhellemn/Projects/github-production/.cursor/debug.log', 'a') as f:
                    import json
                    f.write(json.dumps({
                        "sessionId": "debug-session",
                        "runId": "limit-debug",
                        "hypothesisId": "H2",
                        "location": "batch_fingerprint_embedding.py:process_eagle_items_fingerprint_embedding",
                        "message": "fix_missing_tags_mode branch",
                        "data": {
                            "has_existing_fp": bool(existing_fp),
                            "has_eagle_fp_tag": has_eagle_fp_tag,
                            "items_to_process_len_before": len(items_to_process),
                            "limit": limit
                        },
                        "timestamp": int(time.time() * 1000)
                    }) + "\n")
            except:
                pass
            # #endregion
            
            if existing_fp and not has_eagle_fp_tag:
                # Has metadata fingerprint but missing Eagle tag - include for processing
                items_to_process.append(item)
                # #region agent log
                try:
                    with open('/Users/brianhellemn/Projects/github-production/.cursor/debug.log', 'a') as f:
                        import json
                        f.write(json.dumps({
                            "sessionId": "debug-session",
                            "runId": "limit-debug",
                            "hypothesisId": "H2",
                            "location": "batch_fingerprint_embedding.py:process_eagle_items_fingerprint_embedding",
                            "message": "BUG: Adding item and continuing WITHOUT limit check",
                            "data": {
                                "items_to_process_len_after": len(items_to_process),
                                "limit": limit,
                                "limit_exceeded": limit is not None and len(items_to_process) > limit
                            },
                            "timestamp": int(time.time() * 1000)
                        }) + "\n")
                except:
                    pass
                # #endregion
                continue
            elif existing_fp and has_eagle_fp_tag:
                # Has both - skip (already complete)
                stats["already_complete"] = stats.get("already_complete", 0) + 1
                continue
            elif not existing_fp:
                # No metadata fingerprint - include for processing (will embed + sync)
                items_to_process.append(item)
                # #region agent log
                try:
                    with open('/Users/brianhellemn/Projects/github-production/.cursor/debug.log', 'a') as f:
                        import json
                        f.write(json.dumps({
                            "sessionId": "debug-session",
                            "runId": "limit-debug",
                            "hypothesisId": "H2",
                            "location": "batch_fingerprint_embedding.py:process_eagle_items_fingerprint_embedding",
                            "message": "BUG: Adding item and continuing WITHOUT limit check",
                            "data": {
                                "items_to_process_len_after": len(items_to_process),
                                "limit": limit,
                                "limit_exceeded": limit is not None and len(items_to_process) > limit
                            },
                            "timestamp": int(time.time() * 1000)
                        }) + "\n")
                except:
                    pass
                # #endregion
                continue
        
        # Standard mode: skip if fingerprint already exists in metadata
        if existing_fp:
            stats["already_has_fingerprint"] += 1
            continue
        
        # If resuming, skip items that were already processed
        if resume and resume_info:
            if tracker.is_item_processed(item_id):
                skipped_already_processed += 1
                continue
        
        items_to_process.append(item)
        
        # #region agent log
        try:
            with open('/Users/brianhellemn/Projects/github-production/.cursor/debug.log', 'a') as f:
                import json
                f.write(json.dumps({
                    "sessionId": "debug-session",
                    "runId": "limit-debug",
                    "hypothesisId": "H3",
                    "location": "batch_fingerprint_embedding.py:process_eagle_items_fingerprint_embedding",
                    "message": "After appending item, checking limit",
                    "data": {
                        "items_to_process_len": len(items_to_process),
                        "limit": limit,
                        "should_break": limit is not None and len(items_to_process) >= limit
                    },
                    "timestamp": int(time.time() * 1000)
                }) + "\n")
        except:
            pass
        # #endregion
        
        # Respect limit if set
        if limit is not None and len(items_to_process) >= limit:
            # #region agent log
            try:
                with open('/Users/brianhellemn/Projects/github-production/.cursor/debug.log', 'a') as f:
                    import json
                    f.write(json.dumps({
                        "sessionId": "debug-session",
                        "runId": "limit-debug",
                        "hypothesisId": "H3",
                        "location": "batch_fingerprint_embedding.py:process_eagle_items_fingerprint_embedding",
                        "message": "Limit reached, breaking loop",
                        "data": {
                            "items_to_process_len": len(items_to_process),
                            "limit": limit
                        },
                        "timestamp": int(time.time() * 1000)
                    }) + "\n")
            except:
                pass
            # #endregion
            break
    
    # #region agent log
    try:
        with open('/Users/brianhellemn/Projects/github-production/.cursor/debug.log', 'a') as f:
            import json
            f.write(json.dumps({
                "sessionId": "debug-session",
                "runId": "limit-debug",
                "hypothesisId": "H4",
                "location": "batch_fingerprint_embedding.py:process_eagle_items_fingerprint_embedding",
                "message": "Before parallel processing",
                "data": {
                    "items_to_process_len": len(items_to_process),
                    "limit": limit,
                    "limit_exceeded": limit is not None and len(items_to_process) > limit,
                    "execute": execute
                },
                "timestamp": int(time.time() * 1000)
            }) + "\n")
    except:
        pass
    # #endregion
    
    logger.info(f"Processing {len(items_to_process)} items (skipped {skipped_no_path + skipped_not_exists + skipped_unsupported_format} early)")
    if skipped_unsupported_format > 0:
        logger.info(f"  Skipped unsupported formats: {skipped_unsupported_format}")
    if skipped_already_processed > 0:
        logger.info(f"Skipped {skipped_already_processed} items already processed (resume mode)")
    
    # Process items in parallel if executing
    if execute and items_to_process:
        stats_lock = Lock()
        checkpoint_batch_size = 50  # Save checkpoint every 50 items
        processed_since_checkpoint = 0
        last_processed_item_id = None
        start_time = time.time()
        last_progress_log = time.time()
        progress_log_interval = 30  # Log progress every 30 seconds
        
        logger.info(f"Starting parallel processing with {max_workers} workers...")
        logger.info(f"Total items to process: {len(items_to_process)}")
        
        # #region agent log
        try:
            with open('/Users/brianhellemn/Projects/github-production/.cursor/debug.log', 'a') as f:
                import json
                f.write(json.dumps({
                    "sessionId": "debug-session",
                    "runId": "limit-debug",
                    "hypothesisId": "H4",
                    "location": "batch_fingerprint_embedding.py:process_eagle_items_fingerprint_embedding",
                    "message": "Submitting tasks to executor",
                    "data": {
                        "items_to_process_len": len(items_to_process),
                        "limit": limit,
                        "limit_exceeded": limit is not None and len(items_to_process) > limit,
                        "max_workers": max_workers
                    },
                    "timestamp": int(time.time() * 1000)
                }) + "\n")
        except:
            pass
        # #endregion
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all tasks
            futures = {
                executor.submit(
                    _process_single_item,
                    item,
                    execute,
                    library_path,
                    eagle_base,
                    eagle_token,
                    notion,
                    tracks_db_id,
                    stats_lock,
                    stats,
                    fix_missing_tags_mode
                ): item for item in items_to_process
            }
            
            # Process completed tasks
            for future in as_completed(futures):
                try:
                    result = future.result()
                    # Result is already handled in worker function via stats_lock
                    
                    # Track last processed item for checkpointing
                    if result.get("status") in ("succeeded", "failed", "skipped"):
                        item_id = result.get("item_id")
                        if item_id:
                            last_processed_item_id = item_id
                            tracker.add_processed_item(item_id)
                        processed_since_checkpoint += 1
                        
                        # Progress logging
                        current_time = time.time()
                        if current_time - last_progress_log >= progress_log_interval:
                            with stats_lock:
                                processed = stats.get("processed", 0)
                                succeeded = stats.get("succeeded", 0)
                                failed = stats.get("failed", 0)
                                elapsed = current_time - start_time
                                rate = processed / elapsed if elapsed > 0 else 0
                                remaining = len(items_to_process) - processed
                                eta = remaining / rate if rate > 0 else 0
                                
                                logger.info(
                                    f"Progress: {processed}/{len(items_to_process)} "
                                    f"({processed*100//len(items_to_process)}%) | "
                                    f"Succeeded: {succeeded} | Failed: {failed} | "
                                    f"Rate: {rate:.1f} items/s | ETA: {eta:.0f}s"
                                )
                            last_progress_log = current_time
                        
                        # Save checkpoint periodically
                        if processed_since_checkpoint >= checkpoint_batch_size:
                            with stats_lock:
                                tracker.update_from_stats(stats, last_processed_item_id)
                            processed_since_checkpoint = 0
                            logger.debug(f"Checkpoint saved (processed {stats.get('processed', 0)} items)")
                
                except Exception as e:
                    logger.error(f"Worker task failed: {e}")
                    with stats_lock:
                        stats["failed"] = stats.get("failed", 0) + 1
                        stats["errors"] = stats.get("errors", [])
                        stats["errors"].append({"error": f"Worker task exception: {str(e)}"})
        
        # Save final checkpoint
        if execute:
            tracker.update_from_stats(stats, last_processed_item_id)
            logger.info(f"Final checkpoint saved")
    elif items_to_process:
        # Dry run - count planned items
        for item in items_to_process:
            stats["planned"] += 1
            # In fix_missing_tags_mode, also check if item needs tag sync only
            if fix_missing_tags_mode:
                item_path = item.get("path", "")
                ext = item.get("ext", "")
                if item_path:
                    file_path = Path(item_path)
                    if not file_path.exists():
                        file_path = get_eagle_item_file_path(item.get("id", ""), ext, library_path)
                else:
                    file_path = get_eagle_item_file_path(item.get("id", ""), ext, library_path)
                
                if file_path and file_path.exists():
                    existing_fp = extract_fingerprint_from_metadata(str(file_path))
                    item_tags = item.get("tags", [])
                    has_eagle_fp_tag = any(tag.lower().startswith("fingerprint:") for tag in item_tags)
                    if existing_fp and not has_eagle_fp_tag:
                        stats["missing_eagle_tag"] = stats.get("missing_eagle_tag", 0) + 1
    
    
    # Summary
    logger.info("")
    logger.info("=" * 80)
    logger.info("EAGLE ITEMS FINGERPRINT EMBEDDING SUMMARY")
    logger.info("=" * 80)
    logger.info(f"Total items scanned: {stats['total_scanned']}")
    logger.info(f"Skipped (no path): {skipped_no_path}")
    logger.info(f"Skipped (file not found): {skipped_not_exists}")
    if fix_missing_tags_mode:
        logger.info(f"Already complete (has both metadata + Eagle tag): {stats.get('already_complete', 0)}")
        logger.info(f"Missing Eagle tag (has metadata fingerprint): {stats.get('missing_eagle_tag', 0)}")
        logger.info(f"Items planned: {stats['planned']} (includes items needing tag sync)")
    else:
        logger.info(f"Already have fingerprints: {stats['already_has_fingerprint']}")
        logger.info(f"Items planned: {stats['planned']}")
    if execute:
        logger.info(f"Items processed: {stats['processed']}")
        logger.info(f"Successfully processed: {stats['succeeded']}")
        logger.info(f"Skipped (unsupported formats): {stats.get('skipped', 0)}")
        logger.info(f"Failed: {stats['failed']}")
        logger.info(f"Eagle tags synced: {stats['eagle_synced']}")
        logger.info(f"Notion tracks updated: {stats['notion_updated']}")
    logger.info("")
    
    if stats["errors"]:
        logger.warning(f"Errors encountered: {len(stats['errors'])}")
        for error in stats["errors"][:10]:
            logger.warning(f"  - {error['file']}: {error['error']}")
        if len(stats["errors"]) > 10:
            logger.warning(f"  ... and {len(stats['errors']) - 10} more errors")
    
    return stats


def process_batch_fingerprint_embedding(
    scan_paths: List[str],
    execute: bool = False,
    limit: Optional[int] = None,
    eagle_base: Optional[str] = None,
    eagle_token: Optional[str] = None,
    notion: Optional[Any] = None,
    tracks_db_id: Optional[str] = None,
    include_eagle: bool = True
) -> Dict[str, Any]:
    """
    Process batch fingerprint embedding for files in specified directories.
    
    Args:
        scan_paths: List of directory paths to scan
        execute: If True, actually embed fingerprints; otherwise dry-run
        limit: Maximum number of files to process (None for all)
        eagle_base: Eagle API base URL
        eagle_token: Eagle API token
        notion: Notion client (optional)
        tracks_db_id: Notion tracks database ID (optional)
        include_eagle: Whether to sync fingerprints to Eagle
    
    Returns:
        Dictionary with processing statistics
    """
    logger.info("=" * 80)
    logger.info("BATCH FINGERPRINT EMBEDDING")
    logger.info("=" * 80)
    logger.info(f"Mode: {'EXECUTE' if execute else 'DRY RUN'}")
    logger.info(f"Limit: {limit if limit else 'None (all files)'} files")
    logger.info(f"Scan paths: {len(scan_paths)} directories")
    logger.info("")
    
    # Scan directories for audio files
    logger.info("Scanning directories for audio files...")
    records, missing_paths = scan_directories(
        scan_paths,
        with_hash=False,
        fast_hash=False,
        validate_integrity=False
    )
    logger.info(f"Found {len(records)} audio files")
    
    if missing_paths:
        logger.warning(f"Missing directories: {missing_paths}")
    
    # Fetch Eagle items if integration enabled
    # FIX: DEF-CRIT-001 - Use resolve_eagle_item_path() to construct paths from library structure
    # The Eagle API doesn't return paths directly, so we must resolve them
    eagle_items_by_path = {}
    if include_eagle and eagle_base and eagle_token:
        try:
            eagle_items = eagle_fetch_all_items(eagle_base, eagle_token)
            # Sort Eagle items to match Notion sort order
            eagle_items = sort_eagle_items_like_notion(eagle_items)
            # Build mapping using resolved paths (like music_library_remediation.py does)
            for item in eagle_items:
                resolved_path = resolve_eagle_item_path(item)
                if resolved_path:
                    eagle_items_by_path[str(resolved_path)] = item
            logger.info(f"Loaded {len(eagle_items_by_path)} Eagle items for fingerprint sync (from {len(eagle_items)} total)")
        except Exception as e:
            logger.warning(f"Failed to fetch Eagle items: {e}")
    
    # Process files
    stats = {
        "total_scanned": len(records),
        "already_has_fingerprint": 0,
        "planned": 0,
        "processed": 0,
        "succeeded": 0,
        "failed": 0,
        "skipped": 0,
        "eagle_synced": 0,
        "notion_updated": 0,
        "errors": []
    }
    
    logger.info("")
    logger.info("Processing files...")
    
    for record in records:
        file_path = Path(record.path)
        if not file_path.exists():
            continue
        
        # Skip WAV files (limited metadata support)
        if file_path.suffix.lower() == '.wav':
            logger.debug(f"Skipping {file_path.name} - WAV files have limited metadata support")
            continue
        
        # Check if fingerprint already exists
        existing_fp = extract_fingerprint_from_metadata(str(file_path))
        if existing_fp:
            stats["already_has_fingerprint"] += 1
            logger.debug(f"Skipping {file_path.name} - fingerprint already exists")
            continue
        
        # Plan fingerprint computation
        stats["planned"] += 1
        
        # Check if we should process this file (respect limit if set)
        if limit is not None and stats["processed"] >= limit:
            continue
        
        if execute:
            try:
                stats["processed"] += 1
                
                # Compute fingerprint
                limit_str = str(limit) if limit else "∞"
                logger.info(f"[{stats['processed']}/{limit_str}] Processing {file_path.name}...")
                fingerprint = compute_file_fingerprint(file_path)
                
                # Embed fingerprint in file metadata
                success, skip_reason = embed_fingerprint_in_metadata(str(file_path), fingerprint)
                
                if success:
                    stats["succeeded"] += 1
                    logger.info(f"  ✅ Embedded fingerprint in metadata")
                    
                    # Sync to Eagle tags
                    if include_eagle:
                        if sync_fingerprint_to_eagle(
                            str(file_path),
                            fingerprint,
                            eagle_base,
                            eagle_token,
                            eagle_items_by_path
                        ):
                            stats["eagle_synced"] += 1
                    
                    # Update Notion track if linked
                    if notion and tracks_db_id:
                        if update_notion_track_fingerprint(notion, tracks_db_id, str(file_path), fingerprint):
                            stats["notion_updated"] += 1
                            logger.debug(f"  ✅ Updated Notion track")
                
                elif skip_reason == "unsupported_format":
                    # Unsupported format (WAV, unknown extension) - count as skipped, not failed
                    stats["skipped"] = stats.get("skipped", 0) + 1
                    logger.debug(f"  ⏭️  Skipped unsupported format: {file_path.name} ({file_path.suffix})")
                
                else:
                    # Actual error occurred - count as failed
                    stats["failed"] += 1
                    error_msg = f"Failed to embed fingerprint in {file_path.name}"
                    stats["errors"].append({"file": str(file_path), "error": error_msg})
                    logger.warning(f"  ⚠️  {error_msg}")
            
            except Exception as e:
                stats["failed"] += 1
                error_msg = f"Error processing {file_path.name}: {e}"
                stats["errors"].append({"file": str(file_path), "error": str(e)})
                logger.error(f"  ❌ {error_msg}")
    
    # Summary
    logger.info("")
    logger.info("=" * 80)
    logger.info("BATCH FINGERPRINT EMBEDDING SUMMARY")
    logger.info("=" * 80)
    logger.info(f"Total files scanned: {stats['total_scanned']}")
    logger.info(f"Already have fingerprints: {stats['already_has_fingerprint']}")
    logger.info(f"Files planned: {stats['planned']}")
    if execute:
        logger.info(f"Files processed: {stats['processed']}")
        logger.info(f"Successfully embedded: {stats['succeeded']}")
        logger.info(f"Skipped (unsupported formats): {stats.get('skipped', 0)}")
        logger.info(f"Failed: {stats['failed']}")
        logger.info(f"Eagle tags synced: {stats['eagle_synced']}")
        logger.info(f"Notion tracks updated: {stats['notion_updated']}")
    logger.info("")
    
    if stats["errors"]:
        logger.warning(f"Errors encountered: {len(stats['errors'])}")
        for error in stats["errors"][:10]:
            logger.warning(f"  - {error['file']}: {error['error']}")
        if len(stats["errors"]) > 10:
            logger.warning(f"  ... and {len(stats['errors']) - 10} more errors")
    
    return stats


def get_fingerprint_operation_status(
    eagle_base: Optional[str] = None,
    eagle_token: Optional[str] = None
) -> Dict[str, Any]:
    """
    Get comprehensive status of fingerprint operations in Eagle library.
    
    Returns:
        Dictionary with status information including:
        - total_items: Total items in library
        - items_with_fingerprints: Items that have fingerprints
        - items_without_fingerprints: Items missing fingerprints
        - coverage_percentage: Fingerprint coverage percentage
        - items_by_format: Breakdown by file format
        - checkpoint_info: Checkpoint/resume information if available
    """
    logger.info("=" * 80)
    logger.info("FINGERPRINT OPERATION STATUS REPORT")
    logger.info("=" * 80)
    
    status = {
        "total_items": 0,
        "items_with_fingerprints": 0,
        "items_without_fingerprints": 0,
        "coverage_percentage": 0.0,
        "items_by_format": {},
        "checkpoint_info": None,
        "errors": []
    }
    
    try:
        # Fetch all Eagle items
        if eagle_base and eagle_token:
            all_items = eagle_fetch_all_items(eagle_base, eagle_token)
            # Sort Eagle items to match Notion sort order
            all_items = sort_eagle_items_like_notion(all_items)
        elif EAGLE_CLIENT_AVAILABLE:
            try:
                eagle_client = get_eagle_client()
                if eagle_client.is_available():
                    all_items_data = eagle_client.search(limit=50000)
                    all_items = []
                    for item in all_items_data:
                        if hasattr(item, 'id'):
                            all_items.append({
                                'id': item.id,
                                'name': item.name if hasattr(item, 'name') else '',
                                'tags': item.tags if hasattr(item, 'tags') else [],
                                'ext': item.ext if hasattr(item, 'ext') else ''
                            })
                        else:
                            all_items.append(item)
                    # Sort Eagle items to match Notion sort order
                    all_items = sort_eagle_items_like_notion(all_items)
                else:
                    logger.warning("Eagle client not available")
                    return status
            except Exception as e:
                logger.error(f"Failed to fetch items via client: {e}")
                status["errors"].append(str(e))
                return status
        else:
            logger.warning("No Eagle API configuration available")
            return status
        
        status["total_items"] = len(all_items)
        
        # Analyze items
        items_with_fp = 0
        items_without_fp = 0
        format_counts = {}
        
        for item in all_items:
            item_tags = item.get("tags", [])
            ext = item.get("ext", "").lower()
            
            # Count by format
            if ext:
                format_counts[ext] = format_counts.get(ext, 0) + 1
            
            # Check for fingerprint
            has_fp_tag = any(tag.lower().startswith("fingerprint:") for tag in item_tags)
            
            if has_fp_tag:
                items_with_fp += 1
            else:
                items_without_fp += 1
        
        status["items_with_fingerprints"] = items_with_fp
        status["items_without_fingerprints"] = items_without_fp
        status["coverage_percentage"] = (items_with_fp / len(all_items) * 100) if all_items else 0.0
        status["items_by_format"] = format_counts
        
        # Check checkpoint info
        from scripts.fingerprint_progress_tracker import FingerprintProgressTracker
        tracker = FingerprintProgressTracker()
        checkpoint_info = tracker.get_resume_info()
        if checkpoint_info:
            status["checkpoint_info"] = checkpoint_info
        
        # Log summary
        logger.info(f"Total items: {status['total_items']}")
        logger.info(f"Items with fingerprints: {status['items_with_fingerprints']} ({status['coverage_percentage']:.1f}%)")
        logger.info(f"Items without fingerprints: {status['items_without_fingerprints']}")
        logger.info("")
        logger.info("Breakdown by format:")
        for fmt, count in sorted(status["items_by_format"].items(), key=lambda x: x[1], reverse=True):
            logger.info(f"  {fmt}: {count}")
        
        if status["checkpoint_info"]:
            logger.info("")
            logger.info("Checkpoint information:")
            logger.info(f"  Last processed: {status['checkpoint_info'].get('last_processed_item_id', 'N/A')}")
            logger.info(f"  Processed count: {status['checkpoint_info'].get('processed_count', 0)}")
            logger.info(f"  Succeeded: {status['checkpoint_info'].get('succeeded_count', 0)}")
            logger.info(f"  Failed: {status['checkpoint_info'].get('failed_count', 0)}")
        
        logger.info("")
        logger.info("=" * 80)
        
    except Exception as e:
        logger.error(f"Failed to get fingerprint operation status: {e}")
        import traceback
        traceback.print_exc()
        status["errors"].append(str(e))
    
    return status


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Batch Fingerprint Embedding for Eagle Library",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Dry run - see what would be processed
  python batch_fingerprint_embedding.py

  # Process first 100 files
  python batch_fingerprint_embedding.py --execute --limit 100

  # Process Eagle library items (recommended)
  python batch_fingerprint_embedding.py --execute --source eagle --limit 1000

  # Fix missing Eagle tags (items with metadata fingerprints but missing tags)
  python batch_fingerprint_embedding.py --execute --fix-missing-tags --source eagle

  # Process with Eagle sync disabled
  python batch_fingerprint_embedding.py --execute --no-eagle --source directories
        """
    )
    parser.add_argument("--directories-db-id", default=os.getenv("MUSIC_DIRECTORIES_DB_ID", ""))
    parser.add_argument("--tracks-db-id", default=os.getenv("TRACKS_DB_ID", ""))
    parser.add_argument(
        "--source",
        choices=["eagle", "directories", "both"],
        default="eagle",
        help="Input source: Eagle library items, directories, or both (default: eagle)"
    )
    parser.add_argument("--limit", type=int, default=None, help="Maximum items to process (default: all)")
    parser.add_argument("--execute", action="store_true", help="Actually embed fingerprints (default: dry-run)")
    parser.add_argument("--no-eagle", action="store_true", help="Disable Eagle tag syncing")
    parser.add_argument("--no-notion", action="store_true", help="Disable Notion track updates (faster processing)")
    parser.add_argument("--max-workers", type=int, default=4, help="Number of parallel workers (default: 4)")
    parser.add_argument("--checkpoint-file", type=str, default="", help="Checkpoint file for Eagle item processing")
    parser.add_argument("--resume", action="store_true", help="Resume Eagle item processing from checkpoint")
    parser.add_argument("--status", action="store_true", help="Show fingerprint operation status and exit")
    parser.add_argument("--fix-missing-tags", action="store_true", help="Target items missing Eagle fingerprint tags (includes items with metadata fingerprints but missing tags)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose logging")
    args = parser.parse_args()
    
    # Handle status command
    if args.status:
        load_unified_env()
        unified_config = get_unified_config()
        eagle_base = unified_config.get("eagle_api_url") or os.getenv("EAGLE_API_BASE", "")
        eagle_token = unified_config.get("eagle_token") or os.getenv("EAGLE_TOKEN", "")
        status = get_fingerprint_operation_status(eagle_base, eagle_token)
        return 0 if not status.get("errors") else 1
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    load_unified_env()
    unified_config = get_unified_config()
    
    source = args.source

    # Initialize Notion client (optional, skip if --no-notion)
    notion = None
    if args.no_notion:
        logger.info("Notion updates disabled (--no-notion flag)")
    elif get_notion_client and (get_notion_token or os.getenv("NOTION_TOKEN")):
        try:
            notion = get_notion_client()
        except Exception as e:
            logger.warning(f"Failed to initialize Notion client: {e}")

    # Get configuration
    tracks_db_id = args.tracks_db_id or unified_config.get("tracks_db_id") or os.getenv("TRACKS_DB_ID", "")
    
    eagle_base = unified_config.get("eagle_api_url") or os.getenv("EAGLE_API_BASE", "")
    eagle_token = unified_config.get("eagle_token") or os.getenv("EAGLE_TOKEN", "")

    # Process Eagle library items (default)
    if source in ("eagle", "both"):
        checkpoint_path = Path(args.checkpoint_file) if args.checkpoint_file else None
        eagle_stats = process_eagle_items_fingerprint_embedding(
            execute=args.execute,
            limit=args.limit,
            eagle_base=eagle_base if not args.no_eagle else None,
            eagle_token=eagle_token if not args.no_eagle else None,
            notion=notion,
            tracks_db_id=tracks_db_id,
            max_workers=args.max_workers,
            checkpoint_file=checkpoint_path,
            resume=args.resume,
            fix_missing_tags_mode=args.fix_missing_tags
        )
        if eagle_stats.get("error"):
            return 1

    # Process directory-based scanning if requested
    if source in ("directories", "both"):
        directories_db_id = (
            args.directories_db_id
            or unified_config.get("music_directories_db_id")
            or os.getenv("MUSIC_DIRECTORIES_DB_ID", "")
        )

        try:
            from scripts.music_library_remediation import load_music_directories
            scan_paths = load_music_directories(notion, directories_db_id)
        except Exception as e:
            logger.error(f"Failed to load music directories: {e}")
            return 1

        if not scan_paths:
            logger.error("No music directories found to scan")
            return 1

        dir_stats = process_batch_fingerprint_embedding(
            scan_paths=scan_paths,
            execute=args.execute,
            limit=args.limit,
            eagle_base=eagle_base if not args.no_eagle else None,
            eagle_token=eagle_token if not args.no_eagle else None,
            notion=notion,
            tracks_db_id=tracks_db_id,
            include_eagle=not args.no_eagle
        )

        if dir_stats["errors"]:
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())

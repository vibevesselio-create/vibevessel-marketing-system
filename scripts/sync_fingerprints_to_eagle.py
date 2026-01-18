#!/usr/bin/env python3
"""
Sync Fingerprints to Eagle Tags
================================

Utility script to sync fingerprints from file metadata to Eagle tags.
This is useful for files that already have fingerprints embedded in their
metadata but don't have corresponding Eagle tags.

Process:
1. Scan Eagle library for all items
2. For each item, check if it has a fingerprint tag
3. If no fingerprint tag, extract fingerprint from file metadata
4. Add fingerprint tag to Eagle item

Version: 2026-01-12
"""

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import List, Optional, Dict, Any

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

# Import fingerprint functions
try:
    from scripts.music_library_remediation import (
        extract_fingerprint_from_metadata,
        eagle_fetch_all_items,
        eagle_update_tags
    )
except ImportError:
    logger.error("Failed to import fingerprint functions from music_library_remediation")
    sys.exit(1)

# Import Eagle client
try:
    from music_workflow.integrations.eagle.client import get_eagle_client
    EAGLE_CLIENT_AVAILABLE = True
except ImportError:
    EAGLE_CLIENT_AVAILABLE = False
    logger.warning("Eagle client module not available, using direct API only")


def sync_fingerprints_to_eagle_tags(
    execute: bool = False,
    limit: Optional[int] = None,
    eagle_base: Optional[str] = None,
    eagle_token: Optional[str] = None,
    use_client: bool = True
) -> Dict[str, Any]:
    """
    Sync fingerprints from file metadata to Eagle tags.
    
    Args:
        execute: If True, actually update Eagle tags; otherwise dry-run
        limit: Maximum number of items to process (None for all)
        eagle_base: Eagle API base URL
        eagle_token: Eagle API token
        use_client: Use Eagle client if available, otherwise use direct API
    
    Returns:
        Dictionary with sync statistics
    """
    logger.info("=" * 80)
    logger.info("SYNC FINGERPRINTS TO EAGLE TAGS")
    logger.info("=" * 80)
    logger.info(f"Mode: {'EXECUTE' if execute else 'DRY RUN'}")
    if limit:
        logger.info(f"Limit: {limit} items")
    logger.info("")
    
    # Fetch all Eagle items
    logger.info("Fetching Eagle items...")
    if eagle_base and eagle_token:
        all_items = eagle_fetch_all_items(eagle_base, eagle_token)
    elif use_client and EAGLE_CLIENT_AVAILABLE:
        try:
            eagle_client = get_eagle_client()
            if eagle_client.is_available():
                # Use direct API call to get all items (Eagle client search has limits)
                import requests
                import json
                url = f"{eagle_client.base_url}/api/item/list"
                resp = requests.get(url, timeout=30)
                if resp.status_code == 200:
                    data = resp.json()
                    all_items = data.get("data", [])
                else:
                    # Fallback to search with high limit
                    all_items_data = eagle_client.search(limit=10000)
                    # Convert EagleItem objects to dicts
                    all_items = []
                    for item in all_items_data:
                        if hasattr(item, 'id'):
                            # Get full item info to get path
                            full_item = eagle_client.get_item(item.id)
                            if full_item:
                                all_items.append({
                                    'id': full_item.id,
                                    'name': full_item.name,
                                    'path': '',  # Path not in EagleItem, need to fetch separately
                                    'tags': full_item.tags
                                })
                            else:
                                all_items.append({
                                    'id': item.id,
                                    'name': item.name,
                                    'path': '',
                                    'tags': item.tags if hasattr(item, 'tags') else []
                                })
                        else:
                            all_items.append(item)
            else:
                logger.error("Eagle client not available")
                return {"error": "Eagle client not available"}
        except Exception as e:
            logger.error(f"Failed to fetch items via client: {e}")
            # Fallback to direct API if available
            if eagle_base and eagle_token:
                logger.info("Falling back to direct API...")
                all_items = eagle_fetch_all_items(eagle_base, eagle_token)
            else:
                return {"error": str(e)}
    else:
        logger.error("No Eagle API configuration available")
        return {"error": "No Eagle API configuration"}
    
    logger.info(f"Found {len(all_items)} Eagle items")
    logger.info("")
    
    stats = {
        "total_items": len(all_items),
        "items_with_fp_tag": 0,
        "items_without_fp_tag": 0,
        "items_with_file_fp": 0,
        "items_synced": 0,
        "items_failed": 0,
        "items_skipped": 0,
        "errors": []
    }
    
    logger.info("Processing items...")
    
    processed = 0
    for item in all_items:
        if limit and processed >= limit:
            break
        
        item_id = item.get("id") if isinstance(item, dict) else getattr(item, 'id', None)
        item_name = item.get("name") if isinstance(item, dict) else getattr(item, 'name', 'Unknown')
        item_path = item.get("path") if isinstance(item, dict) else getattr(item, 'path', '')
        item_tags = item.get("tags", []) if isinstance(item, dict) else (getattr(item, 'tags', []) if hasattr(item, 'tags') else [])
        
        if not item_id:
            continue
        
        processed += 1
        
        # Check if item already has fingerprint tag
        has_fp_tag = any(tag.lower().startswith("fingerprint:") for tag in item_tags)
        
        if has_fp_tag:
            stats["items_with_fp_tag"] += 1
            logger.debug(f"Skipping {item_name} - already has fingerprint tag")
            continue
        
        stats["items_without_fp_tag"] += 1
        
        # Resolve file path - try item data first, then construct from library structure
        from scripts.eagle_path_resolution import resolve_eagle_item_path
        from scripts.eagle_path_resolution import get_eagle_library_path
        
        # Get library path for path resolution
        library_path = get_eagle_library_path()
        
        # Resolve path using workaround
        file_path = resolve_eagle_item_path(item, library_path)
        
        if not file_path or not file_path.exists():
            stats["items_skipped"] += 1
            if stats["items_skipped"] <= 5:  # Log first few
                logger.debug(f"Skipping {item_name} - file not found (ID: {item_id})")
            continue
        
        # Extract fingerprint from file metadata
        file_fp = extract_fingerprint_from_metadata(str(file_path))
        
        if not file_fp:
            stats["items_skipped"] += 1
            logger.debug(f"Skipping {item_name} - no fingerprint in file metadata")
            continue
        
        stats["items_with_file_fp"] += 1
        
        # Log progress
        if processed % 100 == 0:
            logger.info(f"  Processed {processed}/{len(all_items)} items...")
        
        # Sync fingerprint tag
        fp_tag = f"fingerprint:{file_fp.lower()}"
        
        if execute:
            try:
                if use_client and EAGLE_CLIENT_AVAILABLE:
                    eagle_client = get_eagle_client()
                    if eagle_client.is_available():
                        if eagle_client.sync_fingerprint_tag(item_id, file_fp, force=False):
                            stats["items_synced"] += 1
                            logger.info(f"  ✅ Synced fingerprint tag: {item_name}")
                        else:
                            stats["items_failed"] += 1
                            stats["errors"].append({
                                "item": item_name,
                                "error": "Failed to sync via client"
                            })
                            logger.warning(f"  ⚠️  Failed to sync: {item_name}")
                elif eagle_base and eagle_token:
                    # Use direct API
                    new_tags = list(item_tags) + [fp_tag]
                    if eagle_update_tags(eagle_base, eagle_token, item_id, new_tags):
                        stats["items_synced"] += 1
                        logger.info(f"  ✅ Synced fingerprint tag: {item_name}")
                    else:
                        stats["items_failed"] += 1
                        stats["errors"].append({
                            "item": item_name,
                            "error": "Failed to sync via API"
                        })
                        logger.warning(f"  ⚠️  Failed to sync: {item_name}")
            except Exception as e:
                stats["items_failed"] += 1
                stats["errors"].append({
                    "item": item_name,
                    "error": str(e)
                })
                logger.error(f"  ❌ Error syncing {item_name}: {e}")
        else:
            # Dry run - just log what would be synced
            logger.info(f"  Would sync fingerprint tag: {item_name} ({fp_tag[:32]}...)")
            stats["items_synced"] += 1  # Count as would-be synced in dry run
    
    # Summary
    logger.info("")
    logger.info("=" * 80)
    logger.info("SYNC SUMMARY")
    logger.info("=" * 80)
    logger.info(f"Total items scanned: {stats['total_items']}")
    logger.info(f"Items with fingerprint tag: {stats['items_with_fp_tag']}")
    logger.info(f"Items without fingerprint tag: {stats['items_without_fp_tag']}")
    logger.info(f"Items with fingerprint in file: {stats['items_with_file_fp']}")
    if execute:
        logger.info(f"Items synced: {stats['items_synced']}")
        logger.info(f"Items failed: {stats['items_failed']}")
    else:
        logger.info(f"Items that would be synced: {stats['items_synced']}")
    logger.info(f"Items skipped: {stats['items_skipped']}")
    logger.info("")
    
    if stats["errors"]:
        logger.warning(f"Errors encountered: {len(stats['errors'])}")
        for error in stats["errors"][:10]:
            logger.warning(f"  - {error['item']}: {error['error']}")
        if len(stats["errors"]) > 10:
            logger.warning(f"  ... and {len(stats['errors']) - 10} more errors")
    
    return stats


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sync Fingerprints from File Metadata to Eagle Tags",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Dry run - see what would be synced
  python sync_fingerprints_to_eagle.py

  # Execute sync for all items
  python sync_fingerprints_to_eagle.py --execute

  # Execute sync for first 100 items
  python sync_fingerprints_to_eagle.py --execute --limit 100

  # Use direct API instead of client
  python sync_fingerprints_to_eagle.py --execute --no-client
        """
    )
    parser.add_argument("--limit", type=int, default=None, help="Maximum items to process (default: all)")
    parser.add_argument("--execute", action="store_true", help="Actually sync tags (default: dry-run)")
    parser.add_argument("--no-client", action="store_true", help="Use direct API instead of Eagle client")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose logging")
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    load_unified_env()
    unified_config = get_unified_config()
    
    # Get Eagle configuration
    eagle_base = unified_config.get("eagle_api_url") or os.getenv("EAGLE_API_BASE", "")
    eagle_token = unified_config.get("eagle_token") or os.getenv("EAGLE_TOKEN", "")
    
    if not eagle_base and not eagle_token and not EAGLE_CLIENT_AVAILABLE:
        logger.error("No Eagle API configuration found. Set EAGLE_API_BASE and EAGLE_TOKEN or ensure Eagle client is available.")
        return 1
    
    # Sync fingerprints
    stats = sync_fingerprints_to_eagle_tags(
        execute=args.execute,
        limit=args.limit,
        eagle_base=eagle_base if not args.no_client else eagle_base,
        eagle_token=eagle_token if not args.no_client else eagle_token,
        use_client=not args.no_client
    )
    
    if "error" in stats:
        return 1
    
    if stats["errors"]:
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

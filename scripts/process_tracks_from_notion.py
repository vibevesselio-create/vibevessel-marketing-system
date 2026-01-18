#!/usr/bin/env python3
"""
Process Tracks from Notion
==========================

Batch process Notion tracks through the fingerprint workflow.
Fetches all Eagle items once, then processes each track individually.

DEDUPLICATION:
- Checks BOTH Eagle AND Notion for duplicates before processing
- Prevents duplicate Notion pages from being processed
- Logs all dedup matches for audit trail

Version: 2026-01-17 - Added Notion deduplication integration
"""

import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

try:
    from scripts.music_library_remediation import eagle_fetch_all_items
    from scripts.track_eagle_matcher import find_eagle_item_for_track
    from scripts.process_track_workflow import process_single_track_workflow, _get_track_file_path
except ImportError as e:
    logger.error(f"Failed to import required modules: {e}")
    raise

# Import Notion deduplication
try:
    from music_workflow.deduplication.notion_dedup import (
        NotionDeduplicator,
        check_notion_duplicate,
        log_notion_dedup_check,
    )
    NOTION_DEDUP_AVAILABLE = True
except ImportError:
    logger.warning("Notion deduplication module not available - dedup checks will be skipped")
    NOTION_DEDUP_AVAILABLE = False
    NotionDeduplicator = None
    check_notion_duplicate = None
    log_notion_dedup_check = None

# Import full production workflow from monolithic script
try:
    import importlib.util
    import sys
    from pathlib import Path
    PROJECT_ROOT = Path(__file__).resolve().parent.parent
    script_path = PROJECT_ROOT / "monolithic-scripts" / "soundcloud_download_prod_merge-2.py"
    if script_path.exists():
        spec = importlib.util.spec_from_file_location("soundcloud_download_prod_merge_2", script_path)
        monolithic_module = importlib.util.module_from_spec(spec)
        # Register module in sys.modules BEFORE exec_module to fix Python 3.13 @dataclass compatibility
        # Without this, dataclasses decorator fails with: 'NoneType' object has no attribute '__dict__'
        sys.modules[spec.name] = monolithic_module
        spec.loader.exec_module(monolithic_module)
        process_track_full_workflow = getattr(monolithic_module, "process_track", None)
        MONOLITHIC_AVAILABLE = process_track_full_workflow is not None
    else:
        MONOLITHIC_AVAILABLE = False
        process_track_full_workflow = None
except Exception as e:
    logger.warning(f"Could not load full production workflow: {e}")
    MONOLITHIC_AVAILABLE = False
    process_track_full_workflow = None


def process_tracks_from_notion(
    tracks: List[Dict[str, Any]],
    execute: bool = False,
    limit: Optional[int] = None,
    eagle_base: Optional[str] = None,
    eagle_token: Optional[str] = None,
    notion: Any = None,
    tracks_db_id: Optional[str] = None,
    stop_on_success: bool = True,
    eagle_items: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """
    Process tracks from Notion through the fingerprint workflow.

    Steps:
    1. Fetch all Eagle items (or use pre-fetched cache for streaming mode)
    2. For each track:
       a. Find matching Eagle item
       b. Execute workflow steps (embed, sync, update Notion)
       c. If successful and stop_on_success=True, stop. Otherwise, continue to next track.
    3. Return aggregate statistics
    
    Args:
        tracks: List of Notion track page dictionaries
        execute: If True, actually perform updates; otherwise dry-run
        limit: Maximum number of tracks to attempt (None for all)
        eagle_base: Eagle API base URL
        eagle_token: Eagle API token
        notion: Notion API client
        tracks_db_id: Notion tracks database ID
        stop_on_success: If True, stop processing after first successful track (default: True for single-item mode)
        eagle_items: Optional pre-fetched Eagle items (for streaming mode to avoid re-fetching per batch)

    Returns:
        Dictionary with processing statistics
    """
    stats = {
        "total_tracks": len(tracks),
        "processed": 0,
        "succeeded": 0,
        "failed": 0,
        "skipped": 0,
        "eagle_items_found": 0,
        "fingerprints_embedded": 0,
        "fingerprints_synced": 0,
        "notion_updated": 0,
        # Notion deduplication stats
        "notion_duplicates_found": 0,
        "notion_duplicates_skipped": 0,
        "notion_dedup_by_type": {},
        "errors": []
    }

    if not tracks:
        logger.warning("No tracks provided for processing")
        return stats

    logger.info(f"Processing tracks from Notion (will continue until success or limit reached)...")

    # Initialize Notion deduplicator if available
    notion_deduplicator = None
    if NOTION_DEDUP_AVAILABLE and notion and tracks_db_id:
        notion_deduplicator = NotionDeduplicator(
            notion_client=notion,
            tracks_db_id=tracks_db_id,
            similarity_threshold=0.85,
        )
        logger.info("🔍 NOTION DEDUP: Deduplicator initialized - will check for duplicates before processing")

    # Step 1: Fetch all Eagle items once (or use pre-fetched cache)
    if eagle_items is None:
        logger.info("Fetching all Eagle items for matching...")
        try:
            if eagle_base and eagle_token:
                eagle_items = eagle_fetch_all_items(eagle_base, eagle_token)
            else:
                logger.error("Eagle API configuration missing")
                stats["errors"].append("Eagle API configuration missing")
                return stats

            logger.info(f"Fetched {len(eagle_items)} Eagle items")
        except Exception as e:
            logger.error(f"Failed to fetch Eagle items: {e}")
            stats["errors"].append(f"Failed to fetch Eagle items: {e}")
            return stats
    else:
        logger.info(f"Using pre-fetched Eagle items cache ({len(eagle_items)} items)")
    
    # Step 2: Process tracks until one succeeds
    tracks_attempted = 0
    max_attempts = limit if limit else len(tracks)
    
    for i, track in enumerate(tracks, 1):
        if tracks_attempted >= max_attempts:
            logger.info(f"Reached limit of {max_attempts} tracks attempted")
            break
        
        track_id = track.get("id", "unknown")
        # Extract track title
        props = track.get("properties", {})
        title_prop = props.get("Title") or props.get("title")
        if title_prop:
            if title_prop.get("type") == "title" and title_prop.get("title"):
                track_title = title_prop["title"][0].get("plain_text", "Unknown")
            elif title_prop.get("type") == "rich_text" and title_prop.get("rich_text"):
                track_title = title_prop["rich_text"][0].get("plain_text", "Unknown")
            else:
                track_title = "Unknown"
        else:
            track_title = "Unknown"
        
        tracks_attempted += 1
        logger.info(f"[{tracks_attempted}/{max_attempts}] Processing track: {track_title}")

        try:
            # ========================================
            # NOTION DEDUPLICATION CHECK
            # ========================================
            # Check if this track has duplicates in Notion BEFORE processing
            if notion_deduplicator:
                logger.info(f"  🔍 NOTION DEDUP: Checking for duplicates...")
                dedup_result = notion_deduplicator.check_duplicate(track, exclude_page_id=track_id)

                if dedup_result.is_duplicate:
                    stats["notion_duplicates_found"] += 1

                    # Track by match type
                    if hasattr(dedup_result, 'all_matches') and dedup_result.all_matches:
                        match_type = dedup_result.all_matches[0].get("match_type", "unknown")
                        stats["notion_dedup_by_type"][match_type] = stats["notion_dedup_by_type"].get(match_type, 0) + 1

                    logger.warning(
                        f"  ⚠️  NOTION DUPLICATE FOUND: '{track_title}' "
                        f"matches existing page {dedup_result.matching_track_id[:8]}... "
                        f"(score: {dedup_result.similarity_score:.2f})"
                    )

                    # Skip processing - this is a duplicate
                    stats["notion_duplicates_skipped"] += 1
                    stats["skipped"] += 1
                    logger.info(f"  ⏭️  Skipping duplicate track - use canonical page: {dedup_result.matching_track_id}")
                    continue
                else:
                    logger.debug(f"  ✅ NOTION DEDUP: No duplicates found - proceeding with processing")

            # ========================================
            # FILE PATH CHECK
            # ========================================
            # FIXED: Check for missing file paths BEFORE finding Eagle match
            # If file path is missing or file doesn't exist, trigger download workflow
            file_path = _get_track_file_path(track)
            if not file_path:
                logger.warning(f"  ⚠️  File path missing or file does not exist for track: {track_title}")
                logger.info(f"  📥 Triggering full download workflow for track: {track_title}")
                
                # Trigger full production download workflow
                if MONOLITHIC_AVAILABLE and process_track_full_workflow:
                    try:
                        logger.info(f"  🔄 Running full production workflow (download → process → import → update)...")
                        success = process_track_full_workflow(track)
                        
                        if success:
                            logger.info(f"  ✅ Full workflow completed successfully for: {track_title}")
                            stats["succeeded"] += 1
                            stats["processed"] += 1
                            stats["fingerprints_embedded"] += 1  # Full workflow includes fingerprinting
                            stats["fingerprints_synced"] += 1  # Full workflow includes Eagle sync
                            stats["notion_updated"] += 1  # Full workflow updates Notion
                            
                            logger.info("")
                            logger.info("=" * 80)
                            logger.info(f"✅ SUCCESS: Track '{track_title}' fully processed via download workflow!")
                            logger.info(f"   - Downloaded and processed: ✅")
                            logger.info(f"   - Fingerprint embedded: ✅")
                            logger.info(f"   - Fingerprint synced to Eagle: ✅")
                            logger.info(f"   - Notion updated: ✅")
                            logger.info("=" * 80)
                            logger.info("")
                            if stop_on_success:
                                break  # Stop on first success (single-item mode)
                            # Batch mode: continue to next track (download workflow already handled everything)
                            continue
                        else:
                            logger.warning(f"  ⚠️  Full workflow failed for track: {track_title} - continuing to next track...")
                            stats["failed"] += 1
                            stats["errors"].append({"track": track_title, "error": "Full download workflow failed"})
                            continue
                    except Exception as e:
                        logger.error(f"  ❌ Error in full download workflow for {track_title}: {e}")
                        import traceback
                        traceback.print_exc()
                        stats["failed"] += 1
                        stats["errors"].append({"track": track_title, "error": f"Full workflow exception: {str(e)}"})
                        logger.info("  Continuing to next track...")
                        continue
                else:
                    logger.error(f"  ❌ Full production workflow not available - cannot download track: {track_title}")
                    stats["skipped"] += 1
                    stats["errors"].append({"track": track_title, "error": "Full workflow not available"})
                    logger.info("  Continuing to next track...")
                    continue

            # Find matching Eagle item
            match_result = find_eagle_item_for_track(track, eagle_items)
            
            if not match_result:
                logger.warning(f"  ⚠️  No matching Eagle item found for track: {track_title}")
                logger.info(f"  📥 Triggering full download workflow for track: {track_title}")

                # Trigger full production download workflow
                if MONOLITHIC_AVAILABLE and process_track_full_workflow:
                    try:
                        logger.info(f"  🔄 Running full production workflow (download → process → import → update)...")
                        success = process_track_full_workflow(track)

                        if success:
                            logger.info(f"  ✅ Full workflow completed successfully for: {track_title}")
                            stats["succeeded"] += 1
                            stats["processed"] += 1
                            stats["fingerprints_embedded"] += 1  # Full workflow includes fingerprinting
                            stats["fingerprints_synced"] += 1  # Full workflow includes Eagle sync
                            stats["notion_updated"] += 1  # Full workflow updates Notion

                            logger.info("")
                            logger.info("=" * 80)
                            logger.info(f"✅ SUCCESS: Track '{track_title}' fully processed via download workflow!")
                            logger.info(f"   - Downloaded and processed: ✅")
                            logger.info(f"   - Fingerprint embedded: ✅")
                            logger.info(f"   - Fingerprint synced to Eagle: ✅")
                            logger.info(f"   - Notion updated: ✅")
                            logger.info("=" * 80)
                            logger.info("")
                            if stop_on_success:
                                break  # Stop on first success (single-item mode)
                            # Batch mode: continue to next track (download workflow already handled everything)
                            continue
                        else:
                            logger.warning(f"  ⚠️  Full workflow failed for track: {track_title} - continuing to next track...")
                            stats["failed"] += 1
                            stats["errors"].append({"track": track_title, "error": "Full download workflow failed"})
                            continue
                    except Exception as e:
                        logger.error(f"  ❌ Error in full download workflow for {track_title}: {e}")
                        import traceback
                        traceback.print_exc()
                        stats["failed"] += 1
                        stats["errors"].append({"track": track_title, "error": f"Full workflow exception: {str(e)}"})
                        logger.info("  Continuing to next track...")
                        continue
                else:
                    logger.error(f"  ❌ Full production workflow not available - cannot download track: {track_title}")
                    stats["skipped"] += 1
                    stats["errors"].append({"track": track_title, "error": "Full workflow not available"})
                    logger.info("  Continuing to next track...")
                    continue

            eagle_item, match_type = match_result
            stats["eagle_items_found"] += 1
            logger.info(f"  ✓ Matched Eagle item via {match_type}: {eagle_item.get('name', 'Unknown')}")
            
            # Process track through workflow
            track_stats = process_single_track_workflow(
                track=track,
                eagle_item=eagle_item,
                execute=execute,
                notion_client=notion,  # FIXED: parameter name mismatch
                tracks_db_id=tracks_db_id,
                eagle_base=eagle_base,
                eagle_token=eagle_token
            )
            
            stats["processed"] += 1
            
            # FIXED: Success criteria is now handled consistently in process_single_track_workflow
            # It checks for notion_updated when notion_client is available, otherwise fingerprint_embedded + fingerprint_synced
            is_fully_successful = track_stats.get("success", False)
            
            if is_fully_successful:
                stats["succeeded"] += 1
                stats["fingerprints_embedded"] += 1
                stats["fingerprints_synced"] += 1
                stats["notion_updated"] += 1
                logger.info("")
                logger.info("=" * 80)
                logger.info(f"✅ SUCCESS: Track '{track_title}' fully processed!")
                logger.info(f"   - Fingerprint embedded: ✅")
                logger.info(f"   - Fingerprint synced to Eagle: ✅")
                logger.info(f"   - Notion updated: ✅")
                logger.info("=" * 80)
                logger.info("")
                if stop_on_success:
                    break  # Stop on first success (single-item mode)
                # Otherwise continue processing (batch mode)
            else:
                # Partial success or failure - continue to next track
                stats["failed"] += 1
                if track_stats.get("errors"):
                    error_msgs = [err for err in track_stats["errors"]]
                    logger.warning(f"  ⚠️  Track '{track_title}' not fully processed: {', '.join(error_msgs)}")
                    logger.info("  Continuing to next track...")
                    stats["errors"].extend([
                        {"track": track_title, "error": err}
                        for err in track_stats["errors"]
                    ])
        
        except Exception as e:
            logger.error(f"Error processing track {track_title}: {e}")
            import traceback
            traceback.print_exc()
            stats["failed"] += 1
            stats["errors"].append({"track": track_title, "error": str(e)})
            logger.info("  Continuing to next track...")
    
    # Update total tracks attempted
    stats["total_tracks"] = tracks_attempted
    
    # Summary
    logger.info("")
    logger.info("=" * 80)
    logger.info("TRACK PROCESSING SUMMARY")
    logger.info("=" * 80)
    logger.info(f"Tracks attempted: {tracks_attempted}")
    logger.info(f"Processed: {stats['processed']}")
    logger.info(f"Succeeded: {stats['succeeded']}")
    logger.info(f"Failed: {stats['failed']}")
    logger.info(f"Skipped: {stats['skipped']}")
    logger.info(f"Eagle items found: {stats['eagle_items_found']}")
    logger.info(f"Fingerprints embedded: {stats['fingerprints_embedded']}")
    logger.info(f"Fingerprints synced: {stats['fingerprints_synced']}")
    logger.info(f"Notion updated: {stats['notion_updated']}")

    # Notion deduplication summary
    logger.info("")
    logger.info("🔍 NOTION DEDUPLICATION:")
    logger.info(f"   Duplicates found: {stats['notion_duplicates_found']}")
    logger.info(f"   Duplicates skipped: {stats['notion_duplicates_skipped']}")
    if stats['notion_dedup_by_type']:
        logger.info(f"   By match type: {stats['notion_dedup_by_type']}")

    if stats["succeeded"] > 0:
        logger.info("")
        logger.info("✅ Workflow completed successfully!")
    else:
        logger.info("")
        logger.warning("⚠️  No tracks were fully processed successfully")

    logger.info("=" * 80)
    logger.info("")

    return stats

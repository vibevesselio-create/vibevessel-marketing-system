#!/usr/bin/env python3
"""
Production Run: Fingerprint Embedding + Sync + Deduplication + djay Pro Integration
====================================================================================

PRIMARY ENTRY POINT for Eagle library deduplication and djay Pro synchronization.

Runs fingerprint embedding, syncing, deduplication, and djay Pro library sync for production.

WORKFLOW ORDER:
1. EMBEDS fingerprints in file metadata FIRST (for files without fingerprints)
   - This should happen before deduplication for best results
   - Files without fingerprints will use fallback matching strategies
2. Syncs fingerprints from file metadata to Eagle tags
   - Ensures fingerprints are available in Eagle for matching
3. Reports fingerprint coverage (informational only)
4. Runs deduplication using multiple strategies:
   - Strategy 1: Fingerprint matching (PRIMARY - most accurate, when available)
   - Strategy 2: Fuzzy matching (FALLBACK - for items without fingerprints)
   - Strategy 3: N-gram matching (FALLBACK - for items without fingerprints)
5. DJAY PRO SYNC (runs by default, use --no-djay-sync to skip):
   - Step 5a: Export djay Pro library to CSV (living documents)
   - Step 5b: Sync djay Pro IDs to Notion tracks (+ BPM, Key, play counts)
   - Step 5c: Sync DJ sessions to Notion Calendar
   - Step 5d: Sync activity/play counts to Notion

IMPORTANT:
- Fingerprint-based matches are PRIMARY (Strategy 1), fuzzy matching is fallback (Strategy 2/3)
- Items without fingerprints will use fallback strategies
- DO NOT use run_dedup_bypass.py - it is deprecated and redirects here

Version: 2026-01-18 - djay Pro sync now runs by default; syncs BPM, Key, play counts
Version: 2026-01-18 - Added modular djay Pro library sync integration
Version: 2026-01-14 - Removed 80% coverage requirement - dedup proceeds with available fingerprints
Version: 2026-01-13 - Fixed deduplication to REQUIRE and PRIORITIZE fingerprints
Version: 2026-01-12 - Updated workflow order to fix fingerprint dependency issue
"""

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple

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
    def get_unified_config() -> dict:
        return {}

try:
    from shared_core.workflows.workflow_state_manager import WorkflowStateManager
    STATE_MANAGER_AVAILABLE = True
except ImportError:
    STATE_MANAGER_AVAILABLE = False
    logger.warning("WorkflowStateManager not available - state tracking disabled")


def check_fingerprint_coverage(min_coverage: float = 0.80, state_manager: Optional[WorkflowStateManager] = None) -> dict:
    """
    Check fingerprint coverage in Eagle library.
    
    Args:
        min_coverage: Minimum coverage threshold (0.0-1.0, default: 0.80)
    
    Returns:
        Dictionary with coverage statistics
    """
    logger.info("=" * 80)
    logger.info("CHECKING FINGERPRINT COVERAGE")
    logger.info("=" * 80)
    
    if state_manager:
        state_manager.start_step("fingerprint_coverage_check")
    
    try:
        import importlib.util
        import sys
        script_path = PROJECT_ROOT / "monolithic-scripts" / "soundcloud_download_prod_merge-2.py"

        if not script_path.exists():
            logger.error(f"Script not found: {script_path}")
            return {"error": "Script not found"}

        spec = importlib.util.spec_from_file_location("soundcloud_download_prod_merge_2", script_path)
        module = importlib.util.module_from_spec(spec)
        # Fix Python 3.13 @dataclass compatibility - register module before exec
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)

        # Fetch all Eagle items
        all_items = module.eagle_fetch_all_items()
        if not all_items:
            logger.warning("⚠️  No items found in Eagle library")
            return {
                "total_items": 0,
                "items_with_fingerprints": 0,
                "coverage": 0.0,
                "meets_threshold": False
            }
        
        # Count items with fingerprints
        items_with_fp = 0
        for item in all_items:
            item_tags = item.get("tags", [])
            has_fp_tag = any(tag.lower().startswith("fingerprint:") for tag in item_tags)
            
            if not has_fp_tag:
                # Check file metadata
                item_path = item.get("path", "")
                if item_path and hasattr(module, "extract_fingerprint_from_metadata"):
                    fp_in_file = module.extract_fingerprint_from_metadata(item_path)
                    if fp_in_file:
                        has_fp_tag = True
            
            if has_fp_tag:
                items_with_fp += 1
        
        total_items = len(all_items)
        coverage = items_with_fp / total_items if total_items > 0 else 0.0
        meets_threshold = coverage >= min_coverage
        
        logger.info(f"Total items: {total_items}")
        logger.info(f"Items with fingerprints: {items_with_fp}")
        logger.info(f"Coverage: {coverage:.1%}")
        logger.info(f"Threshold: {min_coverage:.1%}")
        
        if meets_threshold:
            logger.info("✅ Fingerprint coverage meets threshold - deduplication can proceed")
        else:
            logger.warning(f"⚠️  Fingerprint coverage ({coverage:.1%}) below threshold ({min_coverage:.1%})")
            logger.warning("   Consider running batch fingerprint embedding before deduplication")
        
        result = {
            "total_items": total_items,
            "items_with_fingerprints": items_with_fp,
            "coverage": coverage,
            "meets_threshold": meets_threshold
        }
        
        if state_manager:
            if "error" not in result:
                state_manager.complete_step("fingerprint_coverage_check", result)
            else:
                state_manager.fail_step("fingerprint_coverage_check", result.get("error", "Unknown error"))
        
        return result
    except Exception as e:
        logger.error(f"Fingerprint coverage check failed: {e}")
        import traceback
        traceback.print_exc()
        error_result = {"error": str(e)}
        if state_manager:
            state_manager.fail_step("fingerprint_coverage_check", str(e))
        return error_result


def run_fingerprint_embedding(execute: bool = False, limit: int = None, tracks: Optional[List[Dict]] = None, state_manager: Optional[WorkflowStateManager] = None, eagle_items_cache: Optional[List[Dict]] = None) -> dict:
    """
    Run batch fingerprint embedding for files without fingerprints.

    Args:
        execute: If True, actually embed fingerprints; otherwise dry-run
        limit: Maximum number of files to process (None for all)
        tracks: Optional list of Notion tracks to process (if None, processes Eagle items directly)
        state_manager: Optional workflow state manager
        eagle_items_cache: Optional pre-fetched Eagle items (for streaming mode to avoid re-fetching per batch)

    Returns:
        Dictionary with embedding statistics
    """
    logger.info("=" * 80)
    logger.info("STEP 1: EMBED FINGERPRINTS IN FILE METADATA")
    logger.info("=" * 80)
    logger.info(f"Mode: {'EXECUTE' if execute else 'DRY RUN'}")
    if limit:
        logger.info(f"Limit: {limit} files")
    if tracks:
        logger.info(f"Processing {len(tracks)} tracks from Notion")
    if eagle_items_cache:
        logger.info(f"Using pre-fetched Eagle items cache ({len(eagle_items_cache)} items)")
    logger.info("")

    if state_manager:
        state_manager.start_step("fingerprint_embedding")

    try:
        unified_config = get_unified_config()
        eagle_base = unified_config.get("eagle_api_url") or os.getenv("EAGLE_API_BASE", "")
        eagle_token = unified_config.get("eagle_token") or os.getenv("EAGLE_TOKEN", "")

        if not eagle_base or not eagle_token:
            logger.warning("⚠️  Eagle API configuration not available - skipping fingerprint embedding")
            return {
                "total_scanned": 0,
                "processed": 0,
                "succeeded": 0,
                "skipped": True
            }

        # Initialize Notion client (optional)
        notion = None
        try:
            from shared_core.notion.token_manager import get_notion_client
            notion = get_notion_client()
        except:
            notion = None

        tracks_db_id = unified_config.get("tracks_db_id") or os.getenv("TRACKS_DB_ID", "")

        # If tracks provided, process per-track workflow (MANDATORY - this is the new architecture)
        if tracks:
            logger.info("Processing tracks from Notion (Notion-first workflow)...")
            from scripts.process_tracks_from_notion import process_tracks_from_notion
            # FIXED: Batch mode (limit=None) should process all tracks, not stop on first success
            # Single-item mode (limit set) should stop on first success
            stop_on_success = limit is not None
            stats = process_tracks_from_notion(
                tracks=tracks,
                execute=execute,
                limit=limit,
                eagle_base=eagle_base,
                eagle_token=eagle_token,
                notion=notion,
                tracks_db_id=tracks_db_id,
                stop_on_success=stop_on_success,
                eagle_items=eagle_items_cache  # Pass cached Eagle items to avoid re-fetching per batch
            )
        else:
            # Fallback to batch Eagle processing (only if no tracks found)
            logger.info("No tracks from Notion - falling back to Eagle-only batch processing")
            from scripts.batch_fingerprint_embedding import process_eagle_items_fingerprint_embedding
            stats = process_eagle_items_fingerprint_embedding(
                execute=execute,
                limit=limit,
                eagle_base=eagle_base,
                eagle_token=eagle_token,
                notion=notion,
                tracks_db_id=tracks_db_id,
                resume=True  # ALWAYS resume to skip already-processed items
            )
        
        if state_manager:
            if "error" in stats:
                state_manager.fail_step("fingerprint_embedding", stats.get("error", "Unknown error"), stats)
            else:
                state_manager.complete_step("fingerprint_embedding", stats)
        
        return stats
    except Exception as e:
        logger.error(f"Fingerprint embedding failed: {e}")
        import traceback
        traceback.print_exc()
        error_result = {"error": str(e)}
        if state_manager:
            state_manager.fail_step("fingerprint_embedding", str(e))
        return error_result


def run_fingerprint_sync(execute: bool = False, limit: Optional[int] = None, tracks: Optional[List[Dict]] = None, state_manager: Optional[WorkflowStateManager] = None, sync_only: bool = False) -> dict:
    """
    Run fingerprint sync to Eagle tags.
    
    Args:
        execute: If True, actually sync fingerprints; otherwise dry-run
        limit: Maximum number of items to process (None for all)
        tracks: Optional list of Notion tracks (if None, syncs all Eagle items)
        state_manager: Optional workflow state manager
        sync_only: If True, force sync even when tracks are provided (for --sync-only mode)
    """
    logger.info("=" * 80)
    logger.info("STEP 2: SYNC FINGERPRINTS TO EAGLE TAGS")
    logger.info("=" * 80)
    
    if state_manager:
        state_manager.start_step("fingerprint_sync")
    
    try:
        unified_config = get_unified_config()
        eagle_base = unified_config.get("eagle_api_url") or os.getenv("EAGLE_API_BASE", "")
        eagle_token = unified_config.get("eagle_token") or os.getenv("EAGLE_TOKEN", "")
        
        # FIXED: --sync-only should still sync even when tracks are provided
        # Only skip sync if we're NOT in sync-only mode AND tracks were provided
        # In sync-only mode, we want to sync regardless of whether tracks exist
        # Debug instrumentation (guarded - enable via ENABLE_DEBUG_LOGGING env var)
        if os.getenv("ENABLE_DEBUG_LOGGING", "").lower() in ("1", "true", "yes"):
            import json
            debug_log_path = Path(__file__).parent.parent / ".cursor" / "debug.log"
            debug_log_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                with open(debug_log_path, 'a') as f:
                    f.write(json.dumps({
                        "id": f"log_{int(__import__('time').time())}_sync_only",
                        "timestamp": int(__import__('time').time() * 1000),
                        "location": "run_fingerprint_dedup_production.py:290",
                        "message": "Sync-only mode check",
                        "data": {
                            "has_tracks": tracks is not None,
                            "tracks_count": len(tracks) if tracks else 0,
                            "sync_only": sync_only,
                            "will_skip": tracks is not None and not sync_only
                        },
                        "sessionId": "debug-session",
                        "runId": "verify-fixes",
                        "hypothesisId": "sync-only-fix"
                    }) + "\n")
            except Exception:
                pass  # Silently fail if debug logging is unavailable
        if tracks and not sync_only:
            logger.info(f"Sync already handled in per-track workflow for {len(tracks)} tracks")
            # Return stats indicating sync was handled in embedding step
            return {
                "total_items": len(tracks),
                "items_synced": 0,  # Already synced in workflow
                "items_failed": 0,
                "skipped": True  # Indicates sync was handled elsewhere
            }
        
        # Fallback to batch sync
        from scripts.sync_fingerprints_to_eagle import sync_fingerprints_to_eagle_tags
        
        stats = sync_fingerprints_to_eagle_tags(
            execute=execute,
            limit=limit,
            eagle_base=eagle_base,
            eagle_token=eagle_token,
            use_client=True
        )
        
        if state_manager:
            if "error" in stats:
                state_manager.fail_step("fingerprint_sync", stats.get("error", "Unknown error"), stats)
            else:
                state_manager.complete_step("fingerprint_sync", stats)
        
        return stats
    except Exception as e:
        logger.error(f"Fingerprint sync failed: {e}")
        error_result = {"error": str(e)}
        if state_manager:
            state_manager.fail_step("fingerprint_sync", str(e))
        return error_result


def run_music_directories_scan(
    execute: bool = False,
    volumes: Optional[List[str]] = None,
    scan_all_volumes: bool = False,
    state_manager: Optional[WorkflowStateManager] = None
) -> dict:
    """
    Scan music directories for duplicates across volumes.

    This step scans configured music directories (from Notion or defaults)
    and identifies duplicate files based on fingerprint, hash, and metadata.

    Args:
        execute: If True, generate detailed report; otherwise summary only
        volumes: Specific volume paths to scan (None = all configured)
        scan_all_volumes: If True, scan all volumes one-by-one for detailed reporting
        state_manager: Optional workflow state manager

    Returns:
        Dictionary with scan results including duplicates found
    """
    logger.info("")
    logger.info("=" * 80)
    logger.info("STEP 5: MUSIC DIRECTORIES DUPLICATE SCAN")
    logger.info("=" * 80)
    logger.info(f"Mode: {'EXECUTE' if execute else 'DRY RUN'}")
    if volumes:
        logger.info(f"Scanning specific volumes: {len(volumes)}")
    elif scan_all_volumes:
        logger.info("Scanning all volumes one-by-one")
    else:
        logger.info("Scanning all configured directories")
    logger.info("")

    if state_manager:
        state_manager.start_step("music_directories_scan")

    try:
        from scripts.music_library_remediation import (
            load_music_directories,
            scan_directories,
            dedupe_inventory,
            FileRecord
        )

        # Get Notion client for loading directories
        notion = None
        try:
            if get_notion_client:
                notion = get_notion_client()
        except Exception as e:
            logger.warning(f"Could not initialize Notion client: {e}")

        # Load unified config for database IDs
        unified_config = get_unified_config()
        directories_db_id = (
            unified_config.get("music_directories_db_id")
            or os.getenv("MUSIC_DIRECTORIES_DB_ID", "")
        )

        # Load configured directories
        all_directories = load_music_directories(notion, directories_db_id)
        logger.info(f"Found {len(all_directories)} configured directories")

        # Filter to specific volumes if provided
        if volumes:
            scan_paths = [d for d in all_directories if any(d.startswith(v) or v in d for v in volumes)]
            if not scan_paths:
                scan_paths = volumes  # Use provided volumes directly
        else:
            scan_paths = all_directories

        # Group by volume for volume-by-volume scanning
        volume_groups: Dict[str, List[str]] = {}
        for path in scan_paths:
            # Extract volume from path
            path_obj = Path(path)
            if path.startswith("/Volumes/"):
                parts = path.split("/")
                volume_name = f"/Volumes/{parts[2]}" if len(parts) > 2 else "/Volumes"
            elif path.startswith("/Users/"):
                volume_name = "Local"
            else:
                volume_name = "Other"

            if volume_name not in volume_groups:
                volume_groups[volume_name] = []
            volume_groups[volume_name].append(path)

        logger.info(f"Directories grouped into {len(volume_groups)} volumes:")
        for vol_name, vol_paths in volume_groups.items():
            logger.info(f"  {vol_name}: {len(vol_paths)} directories")

        all_records: List[FileRecord] = []
        all_missing: List[str] = []
        volume_stats: Dict[str, Dict] = {}

        # Scan volume-by-volume for better reporting
        for volume_name, vol_paths in volume_groups.items():
            logger.info("")
            logger.info(f"📂 Scanning volume: {volume_name}")
            logger.info(f"   Directories: {len(vol_paths)}")

            # Scan this volume's directories
            records, missing = scan_directories(
                vol_paths,
                with_hash=True,  # Enable hashing for duplicate detection
                fast_hash=True,  # Use fast hash (first 64KB)
                validate_integrity=False
            )

            all_records.extend(records)
            all_missing.extend(missing)

            volume_stats[volume_name] = {
                "directories": len(vol_paths),
                "files_found": len(records),
                "missing_directories": len([m for m in missing if any(m.startswith(p) or p in m for p in vol_paths)]),
                "valid_files": sum(1 for r in records if r.is_valid),
                "invalid_files": sum(1 for r in records if not r.is_valid),
            }

            logger.info(f"   Files found: {len(records)}")
            logger.info(f"   Valid: {volume_stats[volume_name]['valid_files']}")
            logger.info(f"   Invalid: {volume_stats[volume_name]['invalid_files']}")

        # Run deduplication analysis across all scanned files
        logger.info("")
        logger.info("=" * 60)
        logger.info("Analyzing duplicates across all volumes...")
        logger.info("=" * 60)

        dedupe_groups, duplicates_list = dedupe_inventory(all_records)

        # Count duplicates by type
        hash_dupes = [g for g in dedupe_groups if g.get("match_type") == "hash"]
        fingerprint_dupes = [g for g in dedupe_groups if g.get("match_type") == "fingerprint"]
        metadata_dupes = [g for g in dedupe_groups if g.get("match_type") in ("metadata", "name")]

        # Calculate cross-volume duplicates
        cross_volume_groups = []
        for group in dedupe_groups:
            files = group.get("files", [])
            volumes_in_group = set()
            for f in files:
                fpath = f.get("path", "") if isinstance(f, dict) else str(f)
                if fpath.startswith("/Volumes/"):
                    parts = fpath.split("/")
                    volumes_in_group.add(f"/Volumes/{parts[2]}" if len(parts) > 2 else "/Volumes")
                elif fpath.startswith("/Users/"):
                    volumes_in_group.add("Local")
                else:
                    volumes_in_group.add("Other")
            if len(volumes_in_group) > 1:
                cross_volume_groups.append(group)

        results = {
            "total_directories": len(scan_paths),
            "total_files_scanned": len(all_records),
            "valid_files": sum(1 for r in all_records if r.is_valid),
            "invalid_files": sum(1 for r in all_records if not r.is_valid),
            "missing_directories": all_missing,
            "duplicate_groups": len(dedupe_groups),
            "total_duplicates": len(duplicates_list),
            "hash_duplicate_groups": len(hash_dupes),
            "fingerprint_duplicate_groups": len(fingerprint_dupes),
            "metadata_duplicate_groups": len(metadata_dupes),
            "cross_volume_duplicate_groups": len(cross_volume_groups),
            "volume_stats": volume_stats,
            "dedupe_groups_detail": dedupe_groups if execute else [],  # Only include details in execute mode
        }

        logger.info("")
        logger.info("=" * 60)
        logger.info("MUSIC DIRECTORIES SCAN SUMMARY")
        logger.info("=" * 60)
        logger.info(f"Total files scanned: {results['total_files_scanned']}")
        logger.info(f"Valid files: {results['valid_files']}")
        logger.info(f"Invalid files: {results['invalid_files']}")
        logger.info("")
        logger.info(f"Duplicate groups found: {results['duplicate_groups']}")
        logger.info(f"  - Hash matches: {results['hash_duplicate_groups']}")
        logger.info(f"  - Fingerprint matches: {results['fingerprint_duplicate_groups']}")
        logger.info(f"  - Metadata matches: {results['metadata_duplicate_groups']}")
        logger.info(f"  - Cross-volume duplicates: {results['cross_volume_duplicate_groups']}")
        logger.info("")

        if state_manager:
            state_manager.complete_step("music_directories_scan", results)

        return results

    except Exception as e:
        logger.error(f"Music directories scan failed: {e}")
        import traceback
        traceback.print_exc()
        error_result = {"error": str(e)}
        if state_manager:
            state_manager.fail_step("music_directories_scan", str(e))
        return error_result


def run_deduplication(dry_run: bool = True, cleanup: bool = False, min_similarity: float = 0.75, state_manager: Optional[WorkflowStateManager] = None) -> dict:
    """
    Run Eagle library deduplication.

    Workflow Order (RECOMMENDED):
    1. Embed fingerprints in file metadata (run_fingerprint_embedding)
    2. Sync fingerprints to Eagle tags (run_fingerprint_sync)
    3. THEN run deduplication (this function)

    Deduplication Behavior:
    - Fingerprint matching is PRIMARY strategy (Strategy 1) when available
    - Fuzzy/ngram matching is FALLBACK (Strategy 2/3) for items without fingerprints
    - No minimum coverage requirement - dedup proceeds with available fingerprints
    """
    logger.info("")
    logger.info("=" * 80)
    logger.info("STEP 4: EAGLE LIBRARY DEDUPLICATION")
    logger.info("=" * 80)
    logger.info(f"Mode: {'DRY RUN' if dry_run else 'LIVE'}")
    logger.info(f"Min Similarity: {min_similarity:.0%}")
    logger.info(f"Cleanup: {'Enabled' if cleanup else 'Disabled'}")
    logger.info("")

    if state_manager:
        state_manager.start_step("deduplication")

    try:
        # Import deduplication function from monolithic script
        import importlib.util
        import sys
        script_path = PROJECT_ROOT / "monolithic-scripts" / "soundcloud_download_prod_merge-2.py"

        if not script_path.exists():
            logger.error(f"Deduplication script not found: {script_path}")
            return {"error": "Deduplication script not found"}

        spec = importlib.util.spec_from_file_location("soundcloud_download_prod_merge_2", script_path)
        module = importlib.util.module_from_spec(spec)
        # Fix Python 3.13 @dataclass compatibility - register module before exec
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)

        result = module.eagle_library_deduplication(
            dry_run=dry_run,
            min_similarity=min_similarity,
            output_report=True,
            cleanup_duplicates=cleanup,
            require_fingerprints=False,
            min_fingerprint_coverage=0.0
        )
        
        if state_manager:
            if "error" in result:
                state_manager.fail_step("deduplication", result.get("error", "Unknown error"), result)
            else:
                state_manager.complete_step("deduplication", result)
        
        return result
    except Exception as e:
        logger.error(f"Deduplication failed: {e}")
        import traceback
        traceback.print_exc()
        error_result = {"error": str(e)}
        if state_manager:
            state_manager.fail_step("deduplication", str(e))
        return error_result


# =============================================================================
# DJAY PRO LIBRARY SYNC FUNCTIONS (Modular, System-Compliant)
# =============================================================================

def run_djay_pro_export(
    output_dir: Optional[Path] = None,
    db_path: Optional[Path] = None,
    state_manager: Optional["WorkflowStateManager"] = None
) -> Dict[str, Any]:
    """
    Step 5a: Export djay Pro library to CSV files (living documents).

    Uses the djay_pro_unified_export.py script to extract:
    - Library tracks (local + streaming)
    - Session history
    - Session tracks (with corrected session-track linking)
    - Playlists

    Args:
        output_dir: Output directory for CSV files (default: djay_pro_export/)
        db_path: Path to djay Pro database (default: ~/Music/djay/...)
        state_manager: Optional workflow state manager

    Returns:
        Dictionary with export statistics and file paths
    """
    logger.info("")
    logger.info("=" * 80)
    logger.info("STEP 5a: DJAY PRO LIBRARY EXPORT")
    logger.info("=" * 80)

    if state_manager:
        state_manager.start_step("djay_pro_export")

    try:
        # Import the unified exporter
        from scripts.djay_pro_unified_export import DjayProUnifiedExporter, DEFAULT_DB_PATH

        if output_dir is None:
            output_dir = PROJECT_ROOT / "djay_pro_export"

        if db_path is None:
            db_path = DEFAULT_DB_PATH

        exporter = DjayProUnifiedExporter(db_path=db_path, output_dir=output_dir)
        result = exporter.run(sync_sheets=False)

        if result.get("success"):
            logger.info(f"✅ djay Pro export complete")
            logger.info(f"   Total tracks: {result.get('stats', {}).get('total_tracks', 0)}")
            logger.info(f"   Sessions: {result.get('stats', {}).get('total_sessions', 0)}")
            logger.info(f"   Playlists: {result.get('stats', {}).get('total_playlists', 0)}")

            if state_manager:
                state_manager.complete_step("djay_pro_export", result)
        else:
            logger.error("❌ djay Pro export failed")
            if state_manager:
                state_manager.fail_step("djay_pro_export", "Export failed")

        return result

    except ImportError as e:
        logger.error(f"Could not import djay Pro exporter: {e}")
        error_result = {"error": f"Import error: {e}", "success": False}
        if state_manager:
            state_manager.fail_step("djay_pro_export", str(e))
        return error_result
    except Exception as e:
        logger.error(f"djay Pro export failed: {e}")
        import traceback
        traceback.print_exc()
        error_result = {"error": str(e), "success": False}
        if state_manager:
            state_manager.fail_step("djay_pro_export", str(e))
        return error_result


def run_djay_pro_id_sync(
    export_dir: Optional[Path] = None,
    dry_run: bool = True,
    similarity_threshold: float = 0.85,
    state_manager: Optional["WorkflowStateManager"] = None
) -> Dict[str, Any]:
    """
    Step 5b: Sync djay Pro IDs to Notion Music Tracks.

    Matches djay Pro tracks to Notion tracks using:
    1. Spotify ID (exact match)
    2. SoundCloud URL (exact match)
    3. Source ID (exact match)
    4. Fuzzy title/artist matching (fallback)

    Then updates the "djay Pro ID" field in Notion for matched tracks.

    Args:
        export_dir: Directory containing djay Pro CSV exports
        dry_run: If True, report what would be updated without making changes
        similarity_threshold: Minimum similarity for fuzzy matching (0.0-1.0)
        state_manager: Optional workflow state manager

    Returns:
        Dictionary with sync statistics
    """
    logger.info("")
    logger.info("=" * 80)
    logger.info("STEP 5b: DJAY PRO ID SYNC TO NOTION")
    logger.info("=" * 80)
    logger.info(f"Mode: {'DRY RUN' if dry_run else 'EXECUTE'}")
    logger.info(f"Similarity threshold: {similarity_threshold:.0%}")

    if state_manager:
        state_manager.start_step("djay_pro_id_sync")

    try:
        from music_workflow.integrations.djay_pro.id_sync import (
            DjayProIdSync,
            sync_djay_pro_ids,
        )
        from dotenv import load_dotenv

        # Ensure environment is loaded
        env_path = PROJECT_ROOT / ".env"
        if env_path.exists():
            load_dotenv(env_path)

        if export_dir is None:
            export_dir = PROJECT_ROOT / "djay_pro_export"

        stats = sync_djay_pro_ids(
            export_dir=export_dir,
            dry_run=dry_run,
            similarity_threshold=similarity_threshold
        )

        result = {
            "success": True,
            "total_tracks": stats.total_tracks,
            "already_synced": stats.already_synced,
            "newly_matched": stats.newly_matched,
            "updated": stats.updated,
            "unmatched": stats.unmatched,
            "errors": stats.errors,
            "dry_run": dry_run,
        }

        logger.info("")
        logger.info(f"✅ djay Pro ID sync complete")
        logger.info(f"   Total tracks: {stats.total_tracks}")
        logger.info(f"   Already synced: {stats.already_synced}")
        logger.info(f"   Newly matched: {stats.newly_matched}")
        logger.info(f"   Updated: {stats.updated}")
        logger.info(f"   Unmatched: {stats.unmatched}")
        logger.info(f"   Errors: {stats.errors}")

        if state_manager:
            state_manager.complete_step("djay_pro_id_sync", result)

        return result

    except ImportError as e:
        logger.error(f"Could not import djay Pro ID sync module: {e}")
        error_result = {"error": f"Import error: {e}", "success": False}
        if state_manager:
            state_manager.fail_step("djay_pro_id_sync", str(e))
        return error_result
    except Exception as e:
        logger.error(f"djay Pro ID sync failed: {e}")
        import traceback
        traceback.print_exc()
        error_result = {"error": str(e), "success": False}
        if state_manager:
            state_manager.fail_step("djay_pro_id_sync", str(e))
        return error_result


def run_djay_session_sync(
    export_dir: Optional[Path] = None,
    skip_existing: bool = True,
    state_manager: Optional["WorkflowStateManager"] = None
) -> Dict[str, Any]:
    """
    Step 5c: Sync DJ sessions to Notion Calendar.

    Creates Calendar entries for each DJ session with:
    - Session date/time
    - Device info
    - BPM statistics
    - Relations to Music Tracks played

    Args:
        export_dir: Directory containing djay Pro CSV exports
        skip_existing: Skip sessions already in Notion Calendar
        state_manager: Optional workflow state manager

    Returns:
        Dictionary with sync statistics
    """
    logger.info("")
    logger.info("=" * 80)
    logger.info("STEP 5c: DJAY SESSION SYNC TO NOTION CALENDAR")
    logger.info("=" * 80)
    logger.info(f"Skip existing: {skip_existing}")

    if state_manager:
        state_manager.start_step("djay_session_sync")

    try:
        from music_workflow.integrations.djay_pro import (
            sync_djay_sessions_to_notion,
            SessionSyncStats,
        )

        if export_dir is None:
            export_dir = PROJECT_ROOT / "djay_pro_export"

        stats = sync_djay_sessions_to_notion(
            export_dir=str(export_dir),
            skip_existing=skip_existing
        )

        result = {
            "success": True,
            "sessions_processed": stats.sessions_processed,
            "sessions_created": stats.sessions_created,
            "sessions_updated": stats.sessions_updated,
            "sessions_skipped": stats.sessions_skipped,
            "sessions_failed": stats.sessions_failed,
            "total_tracks_matched": stats.total_tracks_matched,
            "total_tracks_unmatched": stats.total_tracks_unmatched,
        }

        logger.info("")
        logger.info(f"✅ DJ session sync complete")
        logger.info(f"   Sessions processed: {stats.sessions_processed}")
        logger.info(f"   Sessions created: {stats.sessions_created}")
        logger.info(f"   Sessions updated: {stats.sessions_updated}")
        logger.info(f"   Sessions skipped: {stats.sessions_skipped}")
        logger.info(f"   Sessions failed: {stats.sessions_failed}")
        logger.info(f"   Tracks matched: {stats.total_tracks_matched}")
        logger.info(f"   Tracks unmatched: {stats.total_tracks_unmatched}")

        if state_manager:
            state_manager.complete_step("djay_session_sync", result)

        return result

    except ImportError as e:
        logger.error(f"Could not import djay session sync module: {e}")
        error_result = {"error": f"Import error: {e}", "success": False}
        if state_manager:
            state_manager.fail_step("djay_session_sync", str(e))
        return error_result
    except Exception as e:
        logger.error(f"DJ session sync failed: {e}")
        import traceback
        traceback.print_exc()
        error_result = {"error": str(e), "success": False}
        if state_manager:
            state_manager.fail_step("djay_session_sync", str(e))
        return error_result


def run_djay_activity_sync(
    export_dir: Optional[Path] = None,
    state_manager: Optional["WorkflowStateManager"] = None
) -> Dict[str, Any]:
    """
    Step 5d: Sync djay Pro activity (play counts) to Notion.

    Updates Music Tracks with:
    - Play count from djay Pro
    - Last played date
    - Session references

    Args:
        export_dir: Directory containing djay Pro CSV exports
        state_manager: Optional workflow state manager

    Returns:
        Dictionary with sync statistics
    """
    logger.info("")
    logger.info("=" * 80)
    logger.info("STEP 5d: DJAY ACTIVITY SYNC TO NOTION")
    logger.info("=" * 80)

    if state_manager:
        state_manager.start_step("djay_activity_sync")

    try:
        from music_workflow.integrations.djay_pro import (
            sync_djay_activity_to_notion,
            ActivitySyncStats,
        )

        if export_dir is None:
            export_dir = PROJECT_ROOT / "djay_pro_export"

        stats = sync_djay_activity_to_notion(export_dir=str(export_dir))

        result = {
            "success": True,
            "tracks_processed": stats.tracks_processed,
            "tracks_updated": stats.tracks_updated,
            "tracks_skipped": stats.tracks_skipped,
            "tracks_failed": stats.tracks_failed,
        }

        logger.info("")
        logger.info(f"✅ djay activity sync complete")
        logger.info(f"   Tracks processed: {stats.tracks_processed}")
        logger.info(f"   Tracks updated: {stats.tracks_updated}")
        logger.info(f"   Tracks skipped: {stats.tracks_skipped}")
        logger.info(f"   Tracks failed: {stats.tracks_failed}")

        if state_manager:
            state_manager.complete_step("djay_activity_sync", result)

        return result

    except ImportError as e:
        logger.error(f"Could not import djay activity sync module: {e}")
        error_result = {"error": f"Import error: {e}", "success": False}
        if state_manager:
            state_manager.fail_step("djay_activity_sync", str(e))
        return error_result
    except Exception as e:
        logger.error(f"djay activity sync failed: {e}")
        import traceback
        traceback.print_exc()
        error_result = {"error": str(e), "success": False}
        if state_manager:
            state_manager.fail_step("djay_activity_sync", str(e))
        return error_result


def run_djay_pro_full_sync(
    export_dir: Optional[Path] = None,
    dry_run: bool = True,
    skip_existing_sessions: bool = True,
    skip_export: bool = False,
    similarity_threshold: float = 0.85,
    state_manager: Optional["WorkflowStateManager"] = None
) -> Dict[str, Any]:
    """
    Run complete djay Pro library synchronization.

    Orchestrates all djay Pro sync steps in order:
    1. Export djay Pro library to CSV (unless skip_export=True)
    2. Sync djay Pro IDs to Notion tracks
    3. Sync DJ sessions to Notion Calendar
    4. Sync activity/play counts to Notion

    Args:
        export_dir: Directory for CSV exports
        dry_run: If True, don't make changes to Notion
        skip_existing_sessions: Skip sessions already in Notion
        skip_export: Skip the export step (use existing CSV files)
        similarity_threshold: Minimum similarity for fuzzy matching
        state_manager: Optional workflow state manager

    Returns:
        Dictionary with combined results from all steps
    """
    logger.info("")
    logger.info("=" * 80)
    logger.info("DJAY PRO FULL LIBRARY SYNC")
    logger.info("=" * 80)
    logger.info(f"Mode: {'DRY RUN' if dry_run else 'EXECUTE'}")
    logger.info(f"Skip export: {skip_export}")
    logger.info(f"Skip existing sessions: {skip_existing_sessions}")
    logger.info("")

    if export_dir is None:
        export_dir = PROJECT_ROOT / "djay_pro_export"

    results = {}

    # Step 5a: Export (unless skipped)
    if not skip_export:
        export_result = run_djay_pro_export(
            output_dir=export_dir,
            state_manager=state_manager
        )
        results["export"] = export_result
        if not export_result.get("success"):
            logger.error("Export failed - aborting djay sync")
            return {"success": False, "error": "Export failed", "results": results}

    # Step 5b: ID Sync
    id_sync_result = run_djay_pro_id_sync(
        export_dir=export_dir,
        dry_run=dry_run,
        similarity_threshold=similarity_threshold,
        state_manager=state_manager
    )
    results["id_sync"] = id_sync_result

    # Step 5c: Session Sync (only if not dry_run)
    if not dry_run:
        session_sync_result = run_djay_session_sync(
            export_dir=export_dir,
            skip_existing=skip_existing_sessions,
            state_manager=state_manager
        )
        results["session_sync"] = session_sync_result
    else:
        logger.info("⏭️  Skipping session sync in dry-run mode")
        results["session_sync"] = {"skipped": True, "reason": "dry_run"}

    # Step 5d: Activity Sync (only if not dry_run)
    if not dry_run:
        activity_sync_result = run_djay_activity_sync(
            export_dir=export_dir,
            state_manager=state_manager
        )
        results["activity_sync"] = activity_sync_result
    else:
        logger.info("⏭️  Skipping activity sync in dry-run mode")
        results["activity_sync"] = {"skipped": True, "reason": "dry_run"}

    # Summary
    logger.info("")
    logger.info("=" * 80)
    logger.info("DJAY PRO SYNC SUMMARY")
    logger.info("=" * 80)

    if "export" in results and results["export"].get("success"):
        stats = results["export"].get("stats", {})
        logger.info(f"Export: {stats.get('total_tracks', 0)} tracks, {stats.get('total_sessions', 0)} sessions")

    if results.get("id_sync", {}).get("success"):
        id_stats = results["id_sync"]
        logger.info(f"ID Sync: {id_stats.get('updated', 0)} updated, {id_stats.get('unmatched', 0)} unmatched")

    if results.get("session_sync", {}).get("success"):
        session_stats = results["session_sync"]
        logger.info(f"Sessions: {session_stats.get('sessions_created', 0)} created, {session_stats.get('sessions_skipped', 0)} skipped")

    if results.get("activity_sync", {}).get("success"):
        activity_stats = results["activity_sync"]
        logger.info(f"Activity: {activity_stats.get('tracks_updated', 0)} tracks updated")

    logger.info("=" * 80)

    return {"success": True, "results": results}


# =============================================================================
# END DJAY PRO LIBRARY SYNC FUNCTIONS
# =============================================================================


def _get_prop_value(prop: Dict[str, Any]) -> Optional[str]:
    """Extract text value from a Notion property."""
    if not prop:
        return None

    prop_type = prop.get("type")
    if prop_type == "title":
        title_array = prop.get("title", [])
        if title_array:
            return title_array[0].get("plain_text", "")
    elif prop_type == "rich_text":
        rich_text_array = prop.get("rich_text", [])
        if rich_text_array:
            return rich_text_array[0].get("plain_text", "")
    elif prop_type == "url":
        return prop.get("url")
    elif prop_type == "number":
        num = prop.get("number")
        return str(num) if num is not None else None

    return None


def _get_tracks_db_prop_types(notion: Any, tracks_db_id: str) -> Dict[str, str]:
    """Fetch Notion tracks DB property types for safe updates."""
    try:
        db_meta = notion.databases.retrieve(database_id=tracks_db_id)
        props = db_meta.get("properties", {})
        return {name: info.get("type") for name, info in props.items()}
    except Exception as e:
        logger.warning(f"Could not fetch Tracks DB property types: {e}")
        return {}


def _choose_prop_name(prop_types: Dict[str, str], candidates: List[str]) -> Optional[str]:
    """Pick the first existing property name from a candidate list."""
    for candidate in candidates:
        if candidate in prop_types:
            return candidate
    return None


def _extract_notion_file_paths(track: Dict[str, Any]) -> List[str]:
    """Return all file path values from a Notion track."""
    props = track.get("properties", {})
    paths = []
    for prop_name in ["M4A File Path", "WAV File Path", "AIFF File Path"]:
        path_prop = props.get(prop_name)
        path_value = _get_prop_value(path_prop)
        if path_value:
            paths.append(path_value)
    return paths


def _extract_notion_eagle_id(track: Dict[str, Any]) -> Optional[str]:
    """Extract Eagle ID from a Notion track if present."""
    props = track.get("properties", {})
    for prop_name in ["Eagle File ID", "Eagle ID", "eagle_id", "EagleID"]:
        prop_value = _get_prop_value(props.get(prop_name))
        if prop_value:
            return prop_value
    return None


def _eagle_item_timestamp(item: Dict[str, Any]) -> float:
    """Return a timestamp for sorting Eagle items (newest first)."""
    for key in ["modificationDate", "creationDate", "dateModified"]:
        value = item.get(key)
        if isinstance(value, (int, float)):
            return float(value)
    return 0.0


def _build_track_stub_from_eagle_item(
    eagle_item: Dict[str, Any],
    file_path: Path,
    prop_types: Dict[str, str]
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Build a Notion-like track payload from an Eagle item and file path."""
    try:
        from scripts.music_library_remediation import (
            parse_filename_for_artist_title,
            clean_title_advanced,
            clean_artist_name
        )
    except Exception:
        def parse_filename_for_artist_title(stem: str) -> Tuple[Optional[str], str]:
            return None, stem
        def clean_title_advanced(title: str) -> str:
            return title
        def clean_artist_name(artist: str) -> str:
            return artist

    try:
        from shared_core.fingerprint_schema import (
            get_format_from_extension,
            get_file_path_property_for_format
        )
    except Exception:
        def get_format_from_extension(path_str: str) -> Optional[str]:
            ext = Path(path_str).suffix.lower()
            return {".aiff": "aiff", ".aif": "aiff", ".wav": "wav", ".m4a": "m4a"}.get(ext)
        def get_file_path_property_for_format(fmt: str) -> Optional[str]:
            return {"aiff": "AIFF File Path", "wav": "WAV File Path", "m4a": "M4A File Path"}.get(fmt)

    eagle_name = eagle_item.get("name") or file_path.stem
    raw_artist, raw_title = parse_filename_for_artist_title(eagle_name)
    title = clean_title_advanced(raw_title) or eagle_name
    artist = clean_artist_name(raw_artist) if raw_artist else "Unknown Artist"

    fmt = get_format_from_extension(str(file_path))
    file_path_prop = get_file_path_property_for_format(fmt) if fmt else None

    props: Dict[str, Any] = {}

    title_prop = _choose_prop_name(prop_types, ["Title", "Name"])
    if title_prop:
        prop_type = prop_types.get(title_prop)
        if prop_type == "title":
            props[title_prop] = {"title": [{"text": {"content": title}}]}
        elif prop_type == "rich_text":
            props[title_prop] = {"rich_text": [{"text": {"content": title}}]}

    artist_prop = _choose_prop_name(prop_types, ["Artist Name", "Artist"])
    if artist_prop:
        prop_type = prop_types.get(artist_prop)
        if prop_type == "title":
            props[artist_prop] = {"title": [{"text": {"content": artist}}]}
        elif prop_type == "rich_text":
            props[artist_prop] = {"rich_text": [{"text": {"content": artist}}]}

    eagle_id_prop = _choose_prop_name(prop_types, ["Eagle File ID", "Eagle ID", "eagle_id", "EagleID"])
    if eagle_id_prop and eagle_item.get("id"):
        prop_type = prop_types.get(eagle_id_prop)
        if prop_type == "title":
            props[eagle_id_prop] = {"title": [{"text": {"content": eagle_item["id"]}}]}
        elif prop_type == "rich_text":
            props[eagle_id_prop] = {"rich_text": [{"text": {"content": eagle_item["id"]}}]}

    if file_path_prop and file_path_prop in prop_types:
        prop_type = prop_types.get(file_path_prop)
        if prop_type == "url":
            props[file_path_prop] = {"url": str(file_path)}
        elif prop_type == "rich_text":
            props[file_path_prop] = {"rich_text": [{"text": {"content": str(file_path)}}]}
        elif prop_type == "title":
            props[file_path_prop] = {"title": [{"text": {"content": str(file_path)}}]}

    track_stub = {
        "id": f"eagle-{eagle_item.get('id', 'unknown')}",
        "properties": {
            title_prop: props.get(title_prop) if title_prop else None,
            artist_prop: props.get(artist_prop) if artist_prop else None,
            file_path_prop: props.get(file_path_prop) if file_path_prop else None,
            eagle_id_prop: props.get(eagle_id_prop) if eagle_id_prop else None,
        }
    }

    # Drop empty properties in stub
    track_stub["properties"] = {k: v for k, v in track_stub["properties"].items() if k and v}

    return track_stub, props


def _create_notion_track_for_eagle_item(
    notion: Any,
    tracks_db_id: str,
    eagle_item: Dict[str, Any],
    file_path: Path,
    execute: bool,
    prop_types: Optional[Dict[str, str]] = None
) -> Optional[Dict[str, Any]]:
    """Create a Notion track page for an Eagle item if execute=True."""
    if not notion or not tracks_db_id:
        return None

    prop_types = prop_types or _get_tracks_db_prop_types(notion, tracks_db_id)
    track_stub, props = _build_track_stub_from_eagle_item(eagle_item, file_path, prop_types)

    if not props:
        logger.warning(f"⚠️  Cannot create Notion page - missing required properties for {file_path.name}")
        return None

    if not execute:
        logger.info(f"  [DRY-RUN] Would create Notion track for Eagle item: {eagle_item.get('name', file_path.name)}")
        return track_stub

    try:
        page = notion.pages.create(
            parent={"database_id": tracks_db_id},
            properties=props
        )
        logger.info(f"  ✅ Created Notion track for Eagle item: {eagle_item.get('name', file_path.name)}")
        return page
    except Exception as e:
        logger.error(f"  ❌ Failed to create Notion track for {file_path.name}: {e}")
        return None


def run_eagle_first_processing(
    execute: bool,
    limit: Optional[int],
    eagle_base: str,
    eagle_token: str,
    state_manager: Optional[WorkflowStateManager],
    strict_filename_threshold: float,
    strict_metadata_threshold: float
) -> Dict[str, Any]:
    """
    Eagle-first workflow:
    - Query full Eagle library and Notion tracks
    - Identify Eagle items not present in Notion (strict match thresholds)
    - Process newest unmatched items through embed/sync/Notion update
    """
    logger.info("=" * 80)
    logger.info("EAGLE-FIRST MODE: RECONCILE EAGLE LIBRARY TO NOTION")
    logger.info("=" * 80)

    if state_manager:
        state_manager.start_step("eagle_first_reconcile")

    try:
        from scripts.music_library_remediation import eagle_fetch_all_items, query_database_all
        from scripts.track_eagle_matcher import find_eagle_item_for_track
        from scripts.process_track_workflow import process_single_track_workflow
        from scripts.eagle_path_resolution import resolve_eagle_item_path, get_eagle_library_path
        from shared_core.notion.token_manager import get_notion_client
        from shared_core.fingerprint_schema import get_format_from_extension
    except Exception as e:
        logger.error(f"Failed to import Eagle-first dependencies: {e}")
        return {"error": str(e)}

    # Import Notion deduplication for Eagle-first mode
    notion_deduplicator = None
    DeduplicationResult = None
    try:
        from music_workflow.deduplication.notion_dedup import NotionDeduplicator, DeduplicationResult
        NOTION_DEDUP_AVAILABLE = True
    except ImportError:
        logger.warning("Notion deduplication module not available - dedup checks will be skipped")
        NOTION_DEDUP_AVAILABLE = False

    notion = None
    try:
        notion = get_notion_client()
    except Exception as e:
        logger.warning(f"Could not initialize Notion client: {e}")

    unified_config = get_unified_config()
    tracks_db_id = unified_config.get("tracks_db_id") or os.getenv("TRACKS_DB_ID", "")

    if not eagle_base or not eagle_token:
        logger.warning("⚠️  Eagle API configuration not available - cannot run eagle-first workflow")
        return {"error": "Eagle API configuration missing"}

    if not notion or not tracks_db_id:
        logger.warning("⚠️  Notion configuration not available - cannot run eagle-first workflow")
        return {"error": "Notion configuration missing"}

    # Initialize Notion deduplicator
    if NOTION_DEDUP_AVAILABLE and notion and tracks_db_id:
        notion_deduplicator = NotionDeduplicator(
            notion_client=notion,
            tracks_db_id=tracks_db_id,
            similarity_threshold=0.85,
        )
        logger.info("🔍 NOTION DEDUP: Deduplicator initialized for Eagle-first mode")

    eagle_items = eagle_fetch_all_items(eagle_base, eagle_token, limit=50000)
    notion_tracks = query_database_all(notion, tracks_db_id)
    prop_types = _get_tracks_db_prop_types(notion, tracks_db_id)

    notion_paths = set()
    notion_eagle_ids = set()
    for track in notion_tracks:
        notion_paths.update(_extract_notion_file_paths(track))
        eagle_id = _extract_notion_eagle_id(track)
        if eagle_id:
            notion_eagle_ids.add(eagle_id)

    matched_eagle_ids = set()
    match_type_counts = {"file_path": 0, "filename": 0, "metadata": 0}

    for track in notion_tracks:
        match = find_eagle_item_for_track(
            track,
            eagle_items,
            filename_threshold=strict_filename_threshold,
            metadata_threshold=strict_metadata_threshold
        )
        if match:
            eagle_item, match_type = match
            item_id = eagle_item.get("id")
            if item_id:
                matched_eagle_ids.add(item_id)
                match_type_counts[match_type] = match_type_counts.get(match_type, 0) + 1

    matched_eagle_ids.update(notion_eagle_ids)

    library_path = get_eagle_library_path()
    eagle_items_with_paths: List[Tuple[Dict[str, Any], Optional[Path]]] = []
    for item in eagle_items:
        resolved_path = resolve_eagle_item_path(item, library_path)
        eagle_items_with_paths.append((item, resolved_path))

    unmatched_items: List[Tuple[Dict[str, Any], Optional[Path]]] = []
    for item, resolved_path in eagle_items_with_paths:
        item_id = item.get("id")
        if item_id in matched_eagle_ids:
            continue
        if resolved_path and str(resolved_path) in notion_paths:
            continue
        unmatched_items.append((item, resolved_path))

    unmatched_items.sort(key=lambda pair: _eagle_item_timestamp(pair[0]), reverse=True)

    if limit:
        unmatched_items = unmatched_items[:limit]

    reconcile_stats = {
        "eagle_items_total": len(eagle_items),
        "notion_tracks_total": len(notion_tracks),
        "matched_eagle_items": len(matched_eagle_ids),
        "unmatched_eagle_items": len(unmatched_items),
        "matched_by_type": match_type_counts,
        "notion_paths_indexed": len(notion_paths),
        "notion_eagle_ids_indexed": len(notion_eagle_ids)
    }

    if state_manager:
        state_manager.complete_step("eagle_first_reconcile", reconcile_stats)

    if state_manager:
        state_manager.start_step("fingerprint_embedding")

    embed_stats = {
        "total_scanned": len(unmatched_items),
        "processed": 0,
        "succeeded": 0,
        "failed": 0,
        "skipped": 0,
        "eagle_synced": 0,
        "notion_updated": 0,
        # Notion deduplication stats
        "notion_duplicates_found": 0,
        "notion_duplicates_skipped": 0,
        "notion_dedup_by_type": {},
        "errors": []
    }

    if not unmatched_items:
        logger.info("No unmatched Eagle items found for processing")
        if state_manager:
            state_manager.complete_step("fingerprint_embedding", embed_stats)
        return {
            "reconciliation": reconcile_stats,
            "embedding": embed_stats
        }

    logger.info("")
    logger.info(f"Processing {len(unmatched_items)} Eagle items (newest first)...")

    for idx, (item, resolved_path) in enumerate(unmatched_items, 1):
        if not resolved_path or not resolved_path.exists():
            embed_stats["skipped"] += 1
            embed_stats["errors"].append({
                "item": item.get("id"),
                "error": "Missing or unresolved file path"
            })
            logger.warning(f"[{idx}/{len(unmatched_items)}] ⚠️  Skipping item {item.get('id')} - missing file path")
            continue

        fmt = get_format_from_extension(str(resolved_path))
        if not fmt:
            embed_stats["skipped"] += 1
            embed_stats["errors"].append({
                "item": item.get("id"),
                "error": f"Unsupported format: {resolved_path.suffix}"
            })
            logger.warning(
                f"[{idx}/{len(unmatched_items)}] ⚠️  Skipping item {item.get('id')} - unsupported format {resolved_path.suffix}"
            )
            continue

        logger.info(f"[{idx}/{len(unmatched_items)}] Processing Eagle item: {item.get('name', resolved_path.name)}")

        # ========================================
        # NOTION DEDUPLICATION CHECK (EAGLE-FIRST MODE)
        # ========================================
        # Before creating a new Notion page, check if a similar track already exists
        if notion_deduplicator:
            logger.info(f"  🔍 NOTION DEDUP: Checking for duplicates before creating page...")

            # Build a temporary track dict for dedup checking
            temp_track_for_dedup = {
                "id": None,  # No page ID yet
                "properties": {
                    "Title": {"type": "title", "title": [{"plain_text": item.get("name", resolved_path.stem)}]},
                    "Artist": {"type": "rich_text", "rich_text": []},  # Extract from tags if available
                    f"{fmt.upper()} File Path": {"type": "rich_text", "rich_text": [{"plain_text": str(resolved_path)}]},
                }
            }

            # Extract artist from Eagle tags
            eagle_tags = item.get("tags", [])
            for tag in eagle_tags:
                if tag.lower().startswith("artist:"):
                    artist_name = tag[7:].strip()
                    temp_track_for_dedup["properties"]["Artist"] = {
                        "type": "rich_text",
                        "rich_text": [{"plain_text": artist_name}]
                    }
                    break

            # Check for existing fingerprint tag
            for tag in eagle_tags:
                if tag.lower().startswith("fingerprint:"):
                    fp_value = tag[12:].strip()
                    temp_track_for_dedup["properties"][f"{fmt.upper()} Fingerprint"] = {
                        "type": "rich_text",
                        "rich_text": [{"plain_text": fp_value}]
                    }
                    break

            try:
                dedup_result = notion_deduplicator.check_duplicate(temp_track_for_dedup)
            except Exception as e:
                logger.warning(f"  ⚠️  NOTION DEDUP: Error during duplicate check: {e}")
                # Continue processing - treat as no duplicate found
                if DeduplicationResult:
                    dedup_result = DeduplicationResult(is_duplicate=False)
                else:
                    # Fallback if DeduplicationResult not available
                    dedup_result = type('obj', (object,), {'is_duplicate': False})()

            if dedup_result.is_duplicate:
                embed_stats["notion_duplicates_found"] += 1

                # Track by match type
                if hasattr(dedup_result, 'all_matches') and dedup_result.all_matches:
                    match_type = dedup_result.all_matches[0].get("match_type", "unknown")
                    embed_stats["notion_dedup_by_type"][match_type] = embed_stats["notion_dedup_by_type"].get(match_type, 0) + 1

                logger.warning(
                    f"  ⚠️  NOTION DUPLICATE FOUND: '{item.get('name')}' "
                    f"matches existing page {dedup_result.matching_track_id[:8]}... "
                    f"(score: {dedup_result.similarity_score:.2f})"
                )

                # Skip creating new page - use existing canonical page
                embed_stats["notion_duplicates_skipped"] += 1
                embed_stats["skipped"] += 1
                logger.info(f"  ⏭️  Skipping duplicate - use canonical page: {dedup_result.matching_track_id}")
                continue
            else:
                logger.debug(f"  ✅ NOTION DEDUP: No duplicates found - proceeding with page creation")

        track_page = _create_notion_track_for_eagle_item(
            notion,
            tracks_db_id,
            item,
            resolved_path,
            execute=execute,
            prop_types=prop_types
        )

        track_stub, _ = _build_track_stub_from_eagle_item(
            item,
            resolved_path,
            prop_types
        )

        track_payload = track_page if track_page else track_stub

        if not any(
            prop in track_payload.get("properties", {})
            for prop in ["M4A File Path", "WAV File Path", "AIFF File Path"]
        ):
            embed_stats["skipped"] += 1
            embed_stats["errors"].append({
                "item": item.get("id"),
                "error": "No usable file path property in Notion payload"
            })
            logger.warning(f"[{idx}/{len(unmatched_items)}] ⚠️  Skipping item {item.get('id')} - no file path property available")
            continue

        track_stats = process_single_track_workflow(
            track=track_payload,
            eagle_item=item,
            execute=execute,
            notion_client=notion,
            tracks_db_id=tracks_db_id,
            eagle_base=eagle_base,
            eagle_token=eagle_token
        )

        embed_stats["processed"] += 1

        if track_stats.get("success"):
            embed_stats["succeeded"] += 1
        else:
            embed_stats["failed"] += 1

        if track_stats.get("fingerprint_synced"):
            embed_stats["eagle_synced"] += 1
        if track_stats.get("notion_updated"):
            embed_stats["notion_updated"] += 1

        if track_stats.get("errors"):
            embed_stats["errors"].append({
                "item": item.get("id"),
                "error": "; ".join(track_stats["errors"])
            })

    if state_manager:
        state_manager.complete_step("fingerprint_embedding", embed_stats)

    return {
        "reconciliation": reconcile_stats,
        "embedding": embed_stats
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Production Run: Fingerprint Sync + Deduplication",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Dry run - see what would happen (embeds → syncs → dedup)
  python run_fingerprint_dedup_production.py

  # Execute fingerprint embedding only
  python run_fingerprint_dedup_production.py --embed-only --execute

  # Execute fingerprint sync only
  python run_fingerprint_dedup_production.py --sync-only --execute

  # Execute deduplication only (dry-run)
  python run_fingerprint_dedup_production.py --dedup-only

  # Full production run (execute embed + sync + deduplication dry-run)
  python run_fingerprint_dedup_production.py --execute --dedup-dry-run

  # Full production run with cleanup (USE WITH CAUTION)
  python run_fingerprint_dedup_production.py --execute --dedup-execute --cleanup

  # Eagle-first mode (dry run)
  python run_fingerprint_dedup_production.py --eagle-first

  # Eagle-first mode (execute)
  python run_fingerprint_dedup_production.py --eagle-first --execute

  # Music Directories Scan Examples:
  # Scan all music directories for duplicates (after processing)
  python run_fingerprint_dedup_production.py --execute --scan-directories

  # Scan directories ONLY (skip embedding/sync/dedup)
  python run_fingerprint_dedup_production.py --scan-only

  # Scan specific volumes only
  python run_fingerprint_dedup_production.py --scan-only --scan-volumes /Volumes/VIBES /Volumes/SYSTEM_SSD

  # Full run with volume-by-volume scan reporting
  python run_fingerprint_dedup_production.py --execute --scan-all-volumes

  # RECOMMENDED: Full production run (fingerprinting + dedup + djay sync)
  # This is the DEFAULT mode - all steps run automatically
  python run_fingerprint_dedup_production.py

  # Skip djay sync if you only want fingerprinting/dedup
  python run_fingerprint_dedup_production.py --no-djay-sync

  # djay Pro Library Sync Examples (standalone modes):
  # Run only djay sync (skip fingerprint/dedup steps)
  python run_fingerprint_dedup_production.py --djay-sync-only

  # Export djay Pro library only (to CSV files)
  python run_fingerprint_dedup_production.py --djay-export-only

  # Sync djay Pro IDs to Notion only
  python run_fingerprint_dedup_production.py --djay-id-sync-only

  # Sync DJ sessions to Notion Calendar only
  python run_fingerprint_dedup_production.py --djay-session-sync-only

  # djay sync using existing CSV exports (skip re-export)
  python run_fingerprint_dedup_production.py --djay-sync-only --djay-skip-export
        """
    )
    # Execution modes - all default to EXECUTE (use --dry-run flags to preview)
    parser.add_argument("--execute", action="store_true", default=True, help="[DEFAULT] Execute fingerprint embedding and sync")
    parser.add_argument("--dry-run", action="store_true", help="Run in dry-run mode (preview only, no changes)")
    parser.add_argument("--embed-only", action="store_true", help="Only run fingerprint embedding")
    parser.add_argument("--sync-only", action="store_true", help="Only run fingerprint sync")
    parser.add_argument("--dedup-only", action="store_true", help="Only run deduplication")
    parser.add_argument("--eagle-first", action="store_true", help="Process Eagle library items first (newest-first, Notion reconciliation)")
    parser.add_argument("--dedup-dry-run", action="store_true", help="Run deduplication in dry-run mode (preview only)")
    parser.add_argument("--dedup-execute", action="store_true", default=True, help="[DEFAULT] Execute deduplication")
    parser.add_argument("--cleanup", action="store_true", default=True, help="[DEFAULT] Enable cleanup of duplicates")
    parser.add_argument("--no-cleanup", action="store_true", help="Disable cleanup of duplicates (keep them)")
    parser.add_argument("--min-similarity", type=float, default=0.75, help="Minimum similarity threshold (0.0-1.0, default: 0.75)")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of items to process (for testing)")
    parser.add_argument("--batch-size", type=int, default=200, help="Batch size for processing (default: 200)")
    parser.add_argument("--offset", type=int, default=0, help="Skip first N items before processing (default: 0)")
    # Music directories scan options (2026-01-15)
    parser.add_argument("--scan-directories", action="store_true", help="Scan music directories for duplicates (runs after track processing)")
    parser.add_argument("--scan-only", action="store_true", help="Only run music directories scan (skip other steps)")
    parser.add_argument("--scan-volumes", type=str, nargs="*", help="Specific volumes to scan (e.g., /Volumes/VIBES /Volumes/SYSTEM_SSD)")
    parser.add_argument("--scan-all-volumes", action="store_true", help="Scan all configured volumes one-by-one with detailed reporting")
    # djay Pro sync options (2026-01-18) - djay sync runs by default
    parser.add_argument("--djay-sync", action="store_true", help="[DEPRECATED - now default] Run djay Pro library sync")
    parser.add_argument("--no-djay-sync", action="store_true", help="Skip djay Pro sync (it runs by default)")
    parser.add_argument("--djay-sync-only", action="store_true", help="Only run djay Pro sync (skip fingerprint/dedup steps)")
    parser.add_argument("--djay-export-only", action="store_true", help="Only export djay Pro library to CSV")
    parser.add_argument("--djay-id-sync-only", action="store_true", help="Only sync djay Pro IDs to Notion")
    parser.add_argument("--djay-session-sync-only", action="store_true", help="Only sync DJ sessions to Notion Calendar")
    parser.add_argument("--djay-skip-export", action="store_true", help="Skip djay Pro export (use existing CSV files)")
    parser.add_argument("--djay-similarity", type=float, default=0.85, help="Similarity threshold for djay track matching (0.0-1.0, default: 0.85)")
    # Workflow management
    parser.add_argument("--resume", action="store_true", help="Resume workflow from last completed step")
    parser.add_argument("--status", action="store_true", help="Show workflow status and exit")
    parser.add_argument("--clear-state", action="store_true", help="Clear workflow state and start fresh")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose logging")
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    load_unified_env()
    
    # Initialize state manager
    state_manager = None
    if STATE_MANAGER_AVAILABLE:
        state_manager = WorkflowStateManager()
        
        # Handle status query
        if args.status:
            status = state_manager.get_workflow_status()
            print("\n" + "=" * 80)
            print("WORKFLOW STATUS")
            print("=" * 80)
            print(f"Workflow ID: {status.get('workflow_id', 'N/A')}")
            print(f"Started: {status.get('started_at', 'N/A')}")
            print(f"Last Updated: {status.get('last_updated', 'N/A')}")
            print(f"Current Step: {status.get('current_step', 'N/A')}")
            print(f"Completed Steps: {', '.join(status.get('completed_steps', [])) or 'None'}")
            print(f"Can Resume: {status.get('can_resume', False)}")
            
            if status.get('errors'):
                print(f"\nErrors ({len(status['errors'])}):")
                for error in status['errors'][:5]:
                    print(f"  - [{error.get('step', 'unknown')}] {error.get('error', 'Unknown error')}")
            
            if status.get('steps'):
                print("\nStep Details:")
                for step_name, step_info in status['steps'].items():
                    print(f"  {step_name}:")
                    print(f"    Status: {step_info.get('status', 'unknown')}")
                    if step_info.get('stats'):
                        stats = step_info['stats']
                        print(f"    Stats: {stats}")
            
            resume_info = state_manager.get_resume_info()
            if resume_info:
                print(f"\nResume Information:")
                print(f"  Resume from: {resume_info.get('resume_from_step')}")
                print(f"  Completed: {', '.join(resume_info.get('completed_steps', []))}")
            
            print("=" * 80 + "\n")
            return 0
        
        # Handle clear state
        if args.clear_state:
            state_manager.clear_workflow_state()
            logger.info("✅ Workflow state cleared")
            return 0
        
        # Handle resume
        if args.resume:
            resume_info = state_manager.get_resume_info()
            if not resume_info:
                logger.error("❌ No workflow state found to resume from")
                logger.info("   Run workflow normally first, or use --clear-state to start fresh")
                return 1
            
            resume_step = resume_info.get("resume_from_step")
            completed_steps = resume_info.get("completed_steps", [])
            logger.info(f"📋 Resuming workflow from step: {resume_step}")
            logger.info(f"   Completed steps: {', '.join(completed_steps) or 'None'}")
        else:
            # Start new workflow
            state_manager.start_workflow()
    
    # Determine execution modes (--dry-run overrides all execute defaults)
    is_dry_run = args.dry_run
    execute_mode = not is_dry_run  # Default is execute unless --dry-run specified
    dedup_dry_run = args.dedup_dry_run or is_dry_run  # dedup dry run if either flag
    cleanup_enabled = cleanup_enabled and not args.no_cleanup and not is_dry_run

    # Handle scan-only mode
    if args.scan_only:
        logger.info("=" * 80)
        logger.info("MUSIC DIRECTORIES SCAN ONLY MODE")
        logger.info("=" * 80)
        scan_results = run_music_directories_scan(
            execute=execute_mode,
            volumes=args.scan_volumes,
            scan_all_volumes=args.scan_all_volumes,
            state_manager=state_manager
        )

        # Print summary
        if "error" not in scan_results:
            logger.info("")
            logger.info("=" * 80)
            logger.info("SCAN COMPLETE")
            logger.info("=" * 80)
            logger.info(f"Files scanned: {scan_results.get('total_files_scanned', 0)}")
            logger.info(f"Duplicate groups: {scan_results.get('duplicate_groups', 0)}")
            logger.info(f"Cross-volume duplicates: {scan_results.get('cross_volume_duplicate_groups', 0)}")
        return 0 if "error" not in scan_results else 1

    # Handle djay-sync-only mode
    if args.djay_sync_only:
        logger.info("=" * 80)
        logger.info("DJAY PRO SYNC ONLY MODE")
        logger.info("=" * 80)
        djay_results = run_djay_pro_full_sync(
            dry_run=not execute_mode,
            skip_export=args.djay_skip_export,
            similarity_threshold=args.djay_similarity,
            state_manager=state_manager
        )
        return 0 if djay_results.get("success") else 1

    # Handle djay-export-only mode
    if args.djay_export_only:
        logger.info("=" * 80)
        logger.info("DJAY PRO EXPORT ONLY MODE")
        logger.info("=" * 80)
        export_results = run_djay_pro_export(state_manager=state_manager)
        return 0 if export_results.get("success") else 1

    # Handle djay-id-sync-only mode
    if args.djay_id_sync_only:
        logger.info("=" * 80)
        logger.info("DJAY PRO ID SYNC ONLY MODE")
        logger.info("=" * 80)
        id_sync_results = run_djay_pro_id_sync(
            dry_run=not execute_mode,
            similarity_threshold=args.djay_similarity,
            state_manager=state_manager
        )
        return 0 if id_sync_results.get("success") else 1

    # Handle djay-session-sync-only mode
    if args.djay_session_sync_only:
        logger.info("=" * 80)
        logger.info("DJAY SESSION SYNC ONLY MODE")
        logger.info("=" * 80)
        session_results = run_djay_session_sync(state_manager=state_manager)
        return 0 if session_results.get("success") else 1

    logger.info("=" * 80)
    logger.info("PRODUCTION RUN: FINGERPRINT EMBEDDING + SYNC + DEDUPLICATION")
    logger.info("=" * 80)
    if args.eagle_first:
        logger.info("Mode: EAGLE-FIRST (newest Eagle items → Notion reconciliation)")
    if not args.dedup_only and not args.sync_only:
        logger.info(f"Fingerprint Embedding: {'EXECUTE' if execute_mode else 'DRY RUN'}")
    if not args.dedup_only:
        logger.info(f"Fingerprint Sync: {'EXECUTE' if execute_mode else 'DRY RUN'}")
    if not args.sync_only and not args.embed_only:
        logger.info(f"Deduplication: {'DRY RUN' if dedup_dry_run else 'EXECUTE'}")
        if cleanup_enabled:
            logger.warning("⚠️  CLEANUP ENABLED - Duplicates will be moved to trash!")
    if args.scan_directories or args.scan_all_volumes:
        logger.info(f"Music Directories Scan: ENABLED")
    logger.info("")

    results = {}

    # Determine which steps to run based on resume or normal execution
    should_run_embed = not args.dedup_only and not args.sync_only
    should_run_sync = not args.dedup_only
    should_run_coverage = not args.sync_only and not args.embed_only
    should_run_dedup = not args.sync_only
    should_run_scan = args.scan_directories or args.scan_all_volumes

    if args.resume and state_manager:
        resume_info = state_manager.get_resume_info()
        if resume_info:
            completed_steps = resume_info.get("completed_steps", [])
            resume_step = resume_info.get("resume_from_step")
            
            # Skip completed steps
            if "fingerprint_embedding" in completed_steps:
                should_run_embed = False
            if "fingerprint_sync" in completed_steps:
                should_run_sync = False
            if "fingerprint_coverage_check" in completed_steps:
                should_run_coverage = False
            if "deduplication" in completed_steps and resume_step != "deduplication":
                should_run_dedup = False
    
    # STREAMING MODE: Process tracks batch-by-batch as they're queried from Notion
    # This processes items as they're found instead of loading all into memory first
    if should_run_embed or should_run_sync:
        if args.eagle_first and should_run_embed:
            eagle_first_results = run_eagle_first_processing(
                execute=execute_mode,
                limit=args.limit,
                eagle_base=get_unified_config().get("eagle_api_url") or os.getenv("EAGLE_API_BASE", ""),
                eagle_token=get_unified_config().get("eagle_token") or os.getenv("EAGLE_TOKEN", ""),
                state_manager=state_manager,
                strict_filename_threshold=0.92,
                strict_metadata_threshold=0.75
            )
            if "error" in eagle_first_results:
                logger.error(f"Eagle-first processing failed: {eagle_first_results.get('error')}")
                return 1

            results["eagle_first_reconciliation"] = eagle_first_results.get("reconciliation", {})
            results["fingerprint_embedding"] = eagle_first_results.get("embedding", {})
        elif args.eagle_first and not should_run_embed:
            logger.info("Eagle-first mode requires embedding; running sync-only fallback")
            if should_run_sync:
                sync_results = run_fingerprint_sync(
                    execute=execute_mode,
                    limit=args.limit,
                    tracks=None,
                    state_manager=state_manager,
                    sync_only=args.sync_only
                )
                results["fingerprint_sync"] = sync_results

                if "error" in sync_results:
                    logger.error("Fingerprint sync failed, aborting")
                    return 1
        else:
            try:
                from scripts.notion_track_queries import stream_tracks_for_processing
                logger.info("")
                logger.info("=" * 80)
                logger.info("STREAMING MODE: Processing tracks batch-by-batch as queried from Notion")
                logger.info("=" * 80)
                logger.info("")

                # Pre-fetch Eagle items ONCE before streaming (critical for performance)
                eagle_items_cache = None
                if should_run_embed:
                    logger.info("Pre-fetching Eagle items for batch processing...")
                    try:
                        unified_config = get_unified_config()
                        eagle_base = unified_config.get("eagle_api_url") or os.getenv("EAGLE_API_BASE", "")
                        eagle_token = unified_config.get("eagle_token") or os.getenv("EAGLE_TOKEN", "")
                        if eagle_base and eagle_token:
                            from scripts.music_library_remediation import eagle_fetch_all_items
                            eagle_items_cache = eagle_fetch_all_items(eagle_base, eagle_token)
                            logger.info(f"✅ Pre-fetched {len(eagle_items_cache)} Eagle items (will be reused across all batches)")
                    except Exception as e:
                        logger.warning(f"⚠️  Could not pre-fetch Eagle items: {e}")
                        logger.info("Each batch will fetch Eagle items individually (slower)")

                # Aggregate stats across all batches
                # Keys match process_tracks_from_notion.py return values
                aggregate_embed_stats = {
                    "total_scanned": 0,  # Mapped from total_tracks
                    "processed": 0,
                    "succeeded": 0,
                    "failed": 0,
                    "skipped": 0,
                    "already_has_fingerprint": 0,  # Tracks that already had fingerprints
                    "eagle_synced": 0,  # Mapped from fingerprints_synced
                    "notion_updated": 0
                }
                batch_count = 0
                total_tracks_processed = 0

                # Track processed track IDs to prevent re-processing due to Notion API propagation delay
                # This is the PRIMARY mechanism to prevent infinite loops - tracks are only processed once
                processed_track_ids = set()

                # SINGLE PASS: Stream through all tracks once, tracking which have been processed
                # No continuous loop needed - we track processed IDs to avoid duplicates
                logger.info("")
                logger.info("=" * 80)
                logger.info("🔄 Querying Notion for tracks needing fingerprints...")
                logger.info(f"   Batch size: {args.batch_size}, Offset: {args.offset}")
                logger.info("=" * 80)

                # Track items seen for offset handling
                items_seen = 0
                items_skipped_for_offset = 0

                # Stream and process batches (fingerprint_only mode)
                for batch in stream_tracks_for_processing(batch_size=args.batch_size, limit=args.limit + args.offset if args.limit else None, filter_mode="fingerprint_only"):
                    # Filter out already-processed tracks (prevents re-processing due to API delay)
                    unprocessed_tracks = [
                        track for track in batch
                        if track.get("id") not in processed_track_ids
                    ]

                    if not unprocessed_tracks:
                        logger.debug(f"Batch contained only already-processed tracks, skipping")
                        continue

                    # Handle offset: skip items until we've passed the offset
                    if args.offset > 0 and items_seen < args.offset:
                        tracks_to_skip = min(len(unprocessed_tracks), args.offset - items_seen)
                        items_seen += len(unprocessed_tracks)
                        if tracks_to_skip >= len(unprocessed_tracks):
                            items_skipped_for_offset += len(unprocessed_tracks)
                            logger.debug(f"Skipping batch for offset ({items_seen}/{args.offset} items seen)")
                            continue
                        else:
                            # Partial skip - take only tracks after offset
                            unprocessed_tracks = unprocessed_tracks[tracks_to_skip:]
                            items_skipped_for_offset += tracks_to_skip
                            logger.info(f"⏭️  Skipped {items_skipped_for_offset} items for offset, starting processing...")

                    # Mark tracks as processed BEFORE processing (prevents race conditions)
                    for track in unprocessed_tracks:
                        processed_track_ids.add(track.get("id"))

                    batch_count += 1
                    batch_size = len(unprocessed_tracks)
                    logger.info("")
                    logger.info(f"🔄 BATCH {batch_count}: Processing {batch_size} tracks...")
                    logger.info("-" * 60)

                    # Step 1: Embed Fingerprints for this batch
                    if should_run_embed:
                        batch_embed_results = run_fingerprint_embedding(
                            execute=execute_mode,
                            limit=None,  # Process all tracks in the batch
                            tracks=unprocessed_tracks,
                            state_manager=None,  # Don't use state manager per-batch
                            eagle_items_cache=eagle_items_cache  # Pass cached Eagle items
                        )

                        # Aggregate batch results (map keys from process_tracks_from_notion.py)
                        aggregate_embed_stats["total_scanned"] += batch_embed_results.get("total_tracks", batch_embed_results.get("total_scanned", 0))
                        aggregate_embed_stats["processed"] += batch_embed_results.get("processed", 0)
                        aggregate_embed_stats["succeeded"] += batch_embed_results.get("succeeded", 0)
                        aggregate_embed_stats["failed"] += batch_embed_results.get("failed", 0)
                        aggregate_embed_stats["skipped"] += batch_embed_results.get("skipped", 0)
                        aggregate_embed_stats["eagle_synced"] += batch_embed_results.get("fingerprints_synced", batch_embed_results.get("eagle_synced", 0))
                        aggregate_embed_stats["notion_updated"] += batch_embed_results.get("notion_updated", 0)

                        total_tracks_processed += batch_size

                        if "error" in batch_embed_results:
                            logger.warning(f"⚠️  Batch {batch_count} had errors: {batch_embed_results.get('error')}")
                        else:
                            logger.info(f"✅ Batch {batch_count} complete: {batch_embed_results.get('succeeded', 0)} succeeded, {batch_embed_results.get('failed', 0)} failed")

                    # Step 2: Sync fingerprints for this batch (if not already done in embed step)
                    if should_run_sync and not should_run_embed:
                        batch_sync_results = run_fingerprint_sync(
                            execute=execute_mode,
                            limit=None,
                            tracks=unprocessed_tracks,
                            state_manager=None,
                            sync_only=args.sync_only
                        )
                        if "error" in batch_sync_results:
                            logger.warning(f"⚠️  Sync for batch {batch_count} had errors")

                    logger.info(f"📊 Running total: {total_tracks_processed} tracks processed across {batch_count} batches")

                logger.info("")
                logger.info(f"✅ Streaming complete - processed {len(processed_track_ids)} unique tracks")

                # Store aggregate results
                results["fingerprint_embedding"] = aggregate_embed_stats

                if state_manager and should_run_embed:
                    state_manager.complete_step("fingerprint_embedding", aggregate_embed_stats)

                logger.info("")
                logger.info("=" * 80)
                logger.info(f"STREAMING COMPLETE: {total_tracks_processed} tracks processed in {batch_count} batches")
                logger.info("=" * 80)
                logger.info("")

            except Exception as e:
                logger.warning(f"⚠️  Failed to stream tracks from Notion: {e}")
                logger.info("Falling back to Eagle-only processing")
                import traceback
                traceback.print_exc()

                # Fallback to Eagle-only processing
                if should_run_embed:
                    embed_results = run_fingerprint_embedding(execute=execute_mode, limit=args.limit, tracks=None, state_manager=state_manager)
                    results["fingerprint_embedding"] = embed_results

                if should_run_sync:
                    sync_results = run_fingerprint_sync(execute=execute_mode, limit=args.limit, tracks=None, state_manager=state_manager, sync_only=args.sync_only)
                    results["fingerprint_sync"] = sync_results

                    if "error" in sync_results:
                        logger.error("Fingerprint sync failed, aborting")
                        return 1

    # Step 3: Check Fingerprint Coverage (before deduplication)
    if should_run_coverage:
        coverage_results = check_fingerprint_coverage(min_coverage=0.0, state_manager=state_manager)
        results["fingerprint_coverage"] = coverage_results

        if "error" in coverage_results:
            logger.warning("⚠️  Could not check fingerprint coverage, but continuing...")
        else:
            coverage = coverage_results.get("coverage", 0.0)
            logger.info("")
            logger.info(f"📊 Fingerprint coverage: {coverage:.1%}")
            if coverage < 0.5:
                logger.info("   Note: Deduplication will use fuzzy/ngram matching for items without fingerprints")
            logger.info("")
    
    # Step 4: Deduplication
    if should_run_dedup:
        dedup_results = run_deduplication(
            dry_run=dedup_dry_run,
            cleanup=cleanup_enabled,
            min_similarity=args.min_similarity,
            state_manager=state_manager
        )
        results["deduplication"] = dedup_results

        if "error" in dedup_results:
            logger.error("Deduplication failed")
            return 1

        logger.info("")
        logger.info("✅ Deduplication completed")
        if dedup_results.get("report_path"):
            logger.info(f"📄 Deduplication report: {dedup_results['report_path']}")

    # Step 5: Music Directories Scan (optional, runs after track processing)
    if should_run_scan:
        scan_results = run_music_directories_scan(
            execute=execute_mode,
            volumes=args.scan_volumes,
            scan_all_volumes=args.scan_all_volumes,
            state_manager=state_manager
        )
        results["music_directories_scan"] = scan_results

        if "error" in scan_results:
            logger.warning("⚠️  Music directories scan failed, but continuing...")
        else:
            logger.info("")
            logger.info("✅ Music directories scan completed")
            logger.info(f"   Files scanned: {scan_results.get('total_files_scanned', 0)}")
            logger.info(f"   Duplicate groups: {scan_results.get('duplicate_groups', 0)}")
            logger.info(f"   Cross-volume duplicates: {scan_results.get('cross_volume_duplicate_groups', 0)}")

    # Step 6: djay Pro Library Sync (runs by default, use --no-djay-sync to skip)
    should_run_djay_sync = not getattr(args, 'no_djay_sync', False)
    if should_run_djay_sync:
        djay_sync_results = run_djay_pro_full_sync(
            dry_run=not execute_mode,
            skip_export=args.djay_skip_export,
            similarity_threshold=args.djay_similarity,
            state_manager=state_manager
        )
        results["djay_pro_sync"] = djay_sync_results

        if not djay_sync_results.get("success"):
            logger.warning("⚠️  djay Pro sync failed, but continuing...")
        else:
            logger.info("")
            logger.info("✅ djay Pro library sync completed")

    # Final Summary
    logger.info("")
    logger.info("=" * 80)
    logger.info("PRODUCTION RUN SUMMARY")
    logger.info("=" * 80)
    
    if "fingerprint_embedding" in results:
        embed_stats = results["fingerprint_embedding"]
        if not embed_stats.get("skipped"):
            logger.info("Fingerprint Embedding:")
            logger.info(f"  Total scanned: {embed_stats.get('total_scanned', 0)}")
            logger.info(f"  Already had fingerprints: {embed_stats.get('already_has_fingerprint', 0)}")
            logger.info(f"  Processed: {embed_stats.get('processed', 0)}")
            logger.info(f"  Successfully embedded: {embed_stats.get('succeeded', 0)}")
            logger.info(f"  Failed: {embed_stats.get('failed', 0)}")
            logger.info(f"  Eagle tags synced: {embed_stats.get('eagle_synced', 0)}")
            logger.info(f"  Notion updated: {embed_stats.get('notion_updated', 0)}")

    if "eagle_first_reconciliation" in results:
        recon_stats = results["eagle_first_reconciliation"]
        if recon_stats:
            logger.info("Eagle-First Reconciliation:")
            logger.info(f"  Eagle items total: {recon_stats.get('eagle_items_total', 0)}")
            logger.info(f"  Notion tracks total: {recon_stats.get('notion_tracks_total', 0)}")
            logger.info(f"  Matched Eagle items: {recon_stats.get('matched_eagle_items', 0)}")
            logger.info(f"  Unmatched Eagle items: {recon_stats.get('unmatched_eagle_items', 0)}")
    
    if "fingerprint_sync" in results:
        sync_stats = results["fingerprint_sync"]
        logger.info("Fingerprint Sync:")
        logger.info(f"  Total items: {sync_stats.get('total_items', 0)}")
        logger.info(f"  Items synced: {sync_stats.get('items_synced', 0)}")
        logger.info(f"  Items failed: {sync_stats.get('items_failed', 0)}")
    
    if "fingerprint_coverage" in results:
        coverage_stats = results["fingerprint_coverage"]
        if "error" not in coverage_stats:
            logger.info("Fingerprint Coverage:")
            logger.info(f"  Total items: {coverage_stats.get('total_items', 0)}")
            logger.info(f"  Items with fingerprints: {coverage_stats.get('items_with_fingerprints', 0)}")
            logger.info(f"  Coverage: {coverage_stats.get('coverage', 0.0):.1%}")
            logger.info(f"  Meets threshold: {'✅ Yes' if coverage_stats.get('meets_threshold') else '⚠️  No'}")
    
    if "deduplication" in results:
        dedup_stats = results["deduplication"]
        logger.info("Deduplication:")
        logger.info(f"  Total items: {dedup_stats.get('total_items', 0)}")
        logger.info(f"  Duplicate groups: {len(dedup_stats.get('duplicate_groups', []))}")
        logger.info(f"  Total duplicates: {sum(len(g.get('duplicates', [])) for g in dedup_stats.get('duplicate_groups', []))}")
        
        # Breakdown by match type
        groups = dedup_stats.get('duplicate_groups', [])
        fp_groups = [g for g in groups if g.get('match_type') == 'fingerprint']
        fuzzy_groups = [g for g in groups if g.get('match_type') == 'fuzzy']
        ngram_groups = [g for g in groups if g.get('match_type') == 'ngram']
        
        logger.info(f"  Fingerprint matches: {len(fp_groups)} groups")
        logger.info(f"  Fuzzy matches: {len(fuzzy_groups)} groups")
        logger.info(f"  N-gram matches: {len(ngram_groups)} groups")

    if "music_directories_scan" in results:
        scan_stats = results["music_directories_scan"]
        if "error" not in scan_stats:
            logger.info("Music Directories Scan:")
            logger.info(f"  Directories scanned: {scan_stats.get('total_directories', 0)}")
            logger.info(f"  Files scanned: {scan_stats.get('total_files_scanned', 0)}")
            logger.info(f"  Valid files: {scan_stats.get('valid_files', 0)}")
            logger.info(f"  Duplicate groups: {scan_stats.get('duplicate_groups', 0)}")
            logger.info(f"    - Hash matches: {scan_stats.get('hash_duplicate_groups', 0)}")
            logger.info(f"    - Fingerprint matches: {scan_stats.get('fingerprint_duplicate_groups', 0)}")
            logger.info(f"    - Metadata matches: {scan_stats.get('metadata_duplicate_groups', 0)}")
            logger.info(f"  Cross-volume duplicates: {scan_stats.get('cross_volume_duplicate_groups', 0)}")

            # Volume breakdown
            volume_stats = scan_stats.get('volume_stats', {})
            if volume_stats:
                logger.info("  Volume breakdown:")
                for vol_name, vol_stat in volume_stats.items():
                    logger.info(f"    {vol_name}: {vol_stat.get('files_found', 0)} files")

    if "djay_pro_sync" in results:
        djay_stats = results["djay_pro_sync"]
        if djay_stats.get("success"):
            logger.info("djay Pro Library Sync:")
            sub_results = djay_stats.get("results", {})

            if "export" in sub_results and sub_results["export"].get("success"):
                export_stats = sub_results["export"].get("stats", {})
                logger.info(f"  Export: {export_stats.get('total_tracks', 0)} tracks, {export_stats.get('total_sessions', 0)} sessions")

            if "id_sync" in sub_results and sub_results["id_sync"].get("success"):
                id_stats = sub_results["id_sync"]
                logger.info(f"  ID Sync: {id_stats.get('updated', 0)} updated, {id_stats.get('already_synced', 0)} already synced, {id_stats.get('unmatched', 0)} unmatched")

            if "session_sync" in sub_results and sub_results["session_sync"].get("success"):
                session_stats = sub_results["session_sync"]
                logger.info(f"  Sessions: {session_stats.get('sessions_created', 0)} created, {session_stats.get('sessions_skipped', 0)} skipped")

            if "activity_sync" in sub_results and sub_results["activity_sync"].get("success"):
                activity_stats = sub_results["activity_sync"]
                logger.info(f"  Activity: {activity_stats.get('tracks_updated', 0)} tracks updated")

    logger.info("")
    logger.info("=" * 80)

    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""
Direct Eagle Library Fingerprint Analysis and Embedding
========================================================

Processes all items in the active Eagle library to:
1. Compute and embed fingerprints in file metadata
2. Sync fingerprints to Eagle tags
3. Report coverage statistics

This script directly processes Eagle library items rather than scanning directories.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import logging
import os
from scripts.batch_fingerprint_embedding import (
    process_eagle_items_fingerprint_embedding,
    get_active_eagle_library_path
)
from unified_config import load_unified_env, get_unified_config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)

def main():
    """Run fingerprint analysis and embedding for active Eagle library."""
    logger.info("=" * 80)
    logger.info("EAGLE LIBRARY FINGERPRINT ANALYSIS AND EMBEDDING")
    logger.info("=" * 80)
    
    # Load configuration
    load_unified_env()
    unified_config = get_unified_config()
    
    # Get Eagle API configuration
    eagle_base = unified_config.get("eagle_api_url") or os.getenv("EAGLE_API_BASE", "http://localhost:41595")
    eagle_token = unified_config.get("eagle_token") or os.getenv("EAGLE_TOKEN", "")
    
    # Check active library
    library_path = get_active_eagle_library_path()
    if not library_path:
        logger.error("❌ Could not determine active Eagle library path")
        return 1
    
    logger.info(f"📚 Active Eagle library: {library_path}")
    logger.info("")
    
    # Process Eagle items - dry run first to see what needs processing
    logger.info("🔍 Step 1: Analyzing current fingerprint coverage (dry run)...")
    logger.info("")
    stats_dry = process_eagle_items_fingerprint_embedding(
        execute=False,
        limit=None,  # Process all items
        eagle_base=eagle_base,
        eagle_token=eagle_token,
        notion=None,
        tracks_db_id=None
    )
    
    logger.info("")
    logger.info("=" * 80)
    logger.info("DRY RUN SUMMARY")
    logger.info("=" * 80)
    logger.info(f"Total items scanned: {stats_dry.get('total_scanned', 0)}")
    logger.info(f"Items already with fingerprints: {stats_dry.get('already_has_fingerprint', 0)}")
    logger.info(f"Items needing fingerprints: {stats_dry.get('planned', 0)}")
    logger.info("")
    
    # Ask for confirmation or proceed
    if stats_dry.get('planned', 0) > 0:
        logger.info(f"📝 Ready to embed fingerprints in {stats_dry.get('planned', 0)} items")
        logger.info("🔄 Step 2: Embedding fingerprints in file metadata...")
        logger.info("")
        
        stats_execute = process_eagle_items_fingerprint_embedding(
            execute=True,
            limit=None,  # Process all items
            eagle_base=eagle_base,
            eagle_token=eagle_token,
            notion=None,
            tracks_db_id=None,
            max_workers=6,  # Use 6 workers for better throughput
            resume=True  # Enable resume from checkpoint
        )
        
        logger.info("")
        logger.info("=" * 80)
        logger.info("EXECUTION SUMMARY")
        logger.info("=" * 80)
        logger.info(f"Total items scanned: {stats_execute.get('total_scanned', 0)}")
        logger.info(f"Items processed: {stats_execute.get('processed', 0)}")
        logger.info(f"Fingerprints embedded: {stats_execute.get('succeeded', 0)}")
        logger.info(f"Eagle tags synced: {stats_execute.get('eagle_synced', 0)}")
        logger.info(f"Failed: {stats_execute.get('failed', 0)}")
        if stats_execute.get('errors'):
            logger.warning(f"Errors: {len(stats_execute['errors'])}")
            for error in stats_execute['errors'][:5]:
                logger.warning(f"  - {error.get('file', 'Unknown')}: {error.get('error', 'Unknown error')}")
    else:
        logger.info("✅ All items already have fingerprints embedded!")
    
    logger.info("")
    logger.info("=" * 80)
    logger.info("✅ Fingerprint analysis complete!")
    logger.info("=" * 80)
    
    return 0

if __name__ == "__main__":
    sys.exit(main())

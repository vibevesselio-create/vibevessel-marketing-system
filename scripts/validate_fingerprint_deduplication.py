#!/usr/bin/env python3
"""
Fingerprint Deduplication Validation Script
==========================================

Validates that fingerprints are actually being used in the deduplication workflow.
This addresses DEF-002 from the audit report.

Success Criteria:
- Fingerprint-based dedup groups > 50% of total duplicate groups
- Fingerprint coverage > 80% of supported formats
- All metrics accurately reported (no false failures)
"""

import sys
import logging
from pathlib import Path
from typing import Dict, Any, List

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from unified_config import load_unified_env, get_unified_config
import os

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)


def analyze_deduplication_results(dedup_results: Dict[str, Any]) -> Dict[str, Any]:
    """
    Analyze deduplication results to determine fingerprint usage.
    
    Args:
        dedup_results: Results dictionary from deduplication function
    
    Returns:
        Analysis dictionary with fingerprint usage statistics
    """
    duplicate_groups = dedup_results.get("duplicate_groups", [])
    total_groups = len(duplicate_groups)
    
    fingerprint_groups = 0
    non_fingerprint_groups = 0
    mixed_groups = 0
    
    for group in duplicate_groups:
        # Check if group was formed using fingerprints
        # Groups formed by fingerprint matching should have fingerprint_match=True
        # or all items should share the same fingerprint
        has_fingerprint_match = False
        fingerprints_in_group = set()
        
        for item in group.get("items", []):
            # Check for fingerprint in tags
            tags = item.get("tags", [])
            for tag in tags:
                if tag.lower().startswith("fingerprint:"):
                    fp = tag.lower().replace("fingerprint:", "").strip()
                    if fp:
                        fingerprints_in_group.add(fp)
                        has_fingerprint_match = True
        
        # If all items share the same fingerprint, it's a fingerprint-based group
        if len(fingerprints_in_group) == 1 and has_fingerprint_match:
            fingerprint_groups += 1
        elif has_fingerprint_match and len(fingerprints_in_group) > 1:
            mixed_groups += 1
        else:
            non_fingerprint_groups += 1
    
    fingerprint_percentage = (fingerprint_groups / total_groups * 100) if total_groups > 0 else 0
    
    return {
        "total_groups": total_groups,
        "fingerprint_groups": fingerprint_groups,
        "non_fingerprint_groups": non_fingerprint_groups,
        "mixed_groups": mixed_groups,
        "fingerprint_percentage": fingerprint_percentage,
        "meets_threshold": fingerprint_percentage >= 50.0
    }


def check_fingerprint_coverage() -> Dict[str, Any]:
    """
    Check fingerprint coverage in the Eagle library.
    
    Returns:
        Coverage statistics
    """
    from scripts.batch_fingerprint_embedding import process_eagle_items_fingerprint_embedding
    from scripts.music_library_remediation import extract_fingerprint_from_metadata
    
    logger.info("Checking fingerprint coverage...")
    
    # Run dry-run to get coverage stats
    stats = process_eagle_items_fingerprint_embedding(
        execute=False,
        limit=None,
        eagle_base=None,
        eagle_token=None,
        notion=None,
        tracks_db_id=None
    )
    
    total_scanned = stats.get("total_scanned", 0)
    already_has_fingerprint = stats.get("already_has_fingerprint", 0)
    
    coverage = (already_has_fingerprint / total_scanned * 100) if total_scanned > 0 else 0
    
    return {
        "total_items": total_scanned,
        "items_with_fingerprints": already_has_fingerprint,
        "coverage_percentage": coverage,
        "meets_threshold": coverage >= 80.0
    }


def run_validation() -> int:
    """
    Run full validation of fingerprint deduplication.
    
    Returns:
        Exit code (0 = success, 1 = failure)
    """
    logger.info("=" * 80)
    logger.info("FINGERPRINT DEDUPLICATION VALIDATION")
    logger.info("=" * 80)
    logger.info("")
    
    # Load configuration
    load_unified_env()
    unified_config = get_unified_config()
    
    # Check fingerprint coverage
    logger.info("Step 1: Checking fingerprint coverage...")
    coverage_stats = check_fingerprint_coverage()
    logger.info(f"  Total items: {coverage_stats['total_items']}")
    logger.info(f"  Items with fingerprints: {coverage_stats['items_with_fingerprints']}")
    logger.info(f"  Coverage: {coverage_stats['coverage_percentage']:.1f}%")
    logger.info(f"  Threshold: 80.0%")
    
    if not coverage_stats["meets_threshold"]:
        logger.warning(f"  ⚠️  Coverage below threshold ({coverage_stats['coverage_percentage']:.1f}% < 80.0%)")
        logger.warning("  Recommendation: Run fingerprint embedding before validation")
    else:
        logger.info(f"  ✅ Coverage meets threshold")
    
    logger.info("")
    
    # Run deduplication
    logger.info("Step 2: Running deduplication...")
    try:
        # Import deduplication function
        # Try to import from monolithic script first
        try:
            from monolithic_scripts.soundcloud_download_prod_merge_2 import eagle_library_deduplication
        except ImportError:
            try:
                from monolithic_scripts.soundcloud_download_prod_merge import eagle_library_deduplication
            except ImportError:
                logger.error("Could not import eagle_library_deduplication function")
                logger.error("Please ensure the deduplication function is available")
                return 1
        
        eagle_base = unified_config.get("eagle_api_url") or os.getenv("EAGLE_API_BASE", "http://localhost:41595")
        eagle_token = unified_config.get("eagle_token") or os.getenv("EAGLE_TOKEN", "")
        
        dedup_results = eagle_library_deduplication(
            eagle_base=eagle_base,
            eagle_token=eagle_token,
            dry_run=True,
            require_fingerprints=False,
            min_fingerprint_coverage=0.5
        )
        
        if dedup_results.get("blocked"):
            logger.error(f"  ❌ Deduplication blocked: {dedup_results.get('error', 'Unknown error')}")
            return 1
        
        logger.info(f"  ✅ Deduplication completed")
        logger.info(f"  Total duplicate groups: {len(dedup_results.get('duplicate_groups', []))}")
        
    except Exception as e:
        logger.error(f"  ❌ Failed to run deduplication: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    logger.info("")
    
    # Analyze results
    logger.info("Step 3: Analyzing fingerprint usage...")
    analysis = analyze_deduplication_results(dedup_results)
    
    logger.info(f"  Total duplicate groups: {analysis['total_groups']}")
    logger.info(f"  Fingerprint-based groups: {analysis['fingerprint_groups']}")
    logger.info(f"  Non-fingerprint groups: {analysis['non_fingerprint_groups']}")
    logger.info(f"  Mixed groups: {analysis['mixed_groups']}")
    logger.info(f"  Fingerprint percentage: {analysis['fingerprint_percentage']:.1f}%")
    logger.info(f"  Threshold: 50.0%")
    
    logger.info("")
    logger.info("=" * 80)
    logger.info("VALIDATION RESULTS")
    logger.info("=" * 80)
    
    all_passed = True
    
    # Check coverage
    if coverage_stats["meets_threshold"]:
        logger.info("✅ Coverage: PASS (>= 80%)")
    else:
        logger.warning(f"⚠️  Coverage: FAIL ({coverage_stats['coverage_percentage']:.1f}% < 80%)")
        all_passed = False
    
    # Check fingerprint usage
    if analysis["meets_threshold"]:
        logger.info("✅ Fingerprint Usage: PASS (>= 50% of groups)")
    else:
        logger.warning(f"⚠️  Fingerprint Usage: FAIL ({analysis['fingerprint_percentage']:.1f}% < 50%)")
        all_passed = False
    
    logger.info("")
    
    if all_passed:
        logger.info("✅ VALIDATION PASSED - Fingerprints are being used effectively in deduplication")
        return 0
    else:
        logger.warning("⚠️  VALIDATION PARTIAL - Some criteria not met")
        logger.warning("   Recommendations:")
        if not coverage_stats["meets_threshold"]:
            logger.warning("   - Run batch fingerprint embedding to increase coverage")
        if not analysis["meets_threshold"]:
            logger.warning("   - Verify fingerprint extraction and indexing in deduplication workflow")
        return 1


if __name__ == "__main__":
    sys.exit(run_validation())

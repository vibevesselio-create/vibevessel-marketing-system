#!/usr/bin/env python3
"""
Validate Per-Format Fingerprint Schema
=======================================

Validates the per-format fingerprint schema implementation:
1. Tests fingerprint property routing based on file format
2. Verifies backward compatibility with legacy fields
3. Tests fingerprint matching logic

Usage:
    python scripts/validate_per_format_fingerprints.py
    python scripts/validate_per_format_fingerprints.py --verbose

Version: 2026-01-14
"""

import argparse
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)


def test_format_detection():
    """Test file format detection from file paths."""
    logger.info("=" * 60)
    logger.info("TEST: Format Detection from File Paths")
    logger.info("=" * 60)

    from shared_core.fingerprint_schema import get_format_from_extension

    test_cases = [
        ("/path/to/track.m4a", "m4a"),
        ("/path/to/track.M4A", "m4a"),
        ("/path/to/track.mp4", "m4a"),
        ("/path/to/track.aac", "m4a"),
        ("/path/to/track.alac", "m4a"),
        ("/path/to/track.wav", "wav"),
        ("/path/to/track.WAV", "wav"),
        ("/path/to/track.aiff", "aiff"),
        ("/path/to/track.aif", "aiff"),
        ("/path/to/track.AIFF", "aiff"),
        ("/path/to/track.mp3", None),  # Not supported in per-format schema
        ("/path/to/track.flac", None),  # Not supported in per-format schema
        ("", None),
        (None, None),
    ]

    passed = 0
    failed = 0

    for file_path, expected in test_cases:
        result = get_format_from_extension(file_path or "")
        if result == expected:
            logger.info(f"  ✅ {file_path or '(empty)'} -> {result}")
            passed += 1
        else:
            logger.error(f"  ❌ {file_path or '(empty)'} -> {result} (expected {expected})")
            failed += 1

    logger.info(f"\nResults: {passed} passed, {failed} failed")
    return failed == 0


def test_fingerprint_property_mapping():
    """Test fingerprint property routing for each format."""
    logger.info("\n" + "=" * 60)
    logger.info("TEST: Fingerprint Property Mapping")
    logger.info("=" * 60)

    from shared_core.fingerprint_schema import (
        get_fingerprint_properties_for_format,
        get_file_path_property_for_format,
        FINGERPRINT_PROPERTIES,
        FILE_PATH_PROPERTIES,
    )

    test_cases = [
        ("m4a", "M4A File Path", ["M4A Fingerprint", "M4A Fingerprint Part 2", "M4A Fingerprint Part 3"]),
        ("wav", "WAV File Path", ["WAV Fingerprint", "WAV Fingerprint Part 2", "WAV Fingerprint Part 3"]),
        ("aiff", "AIFF File Path", ["AIFF Fingerprint", "AIFF Fingerprint Part 2", "AIFF Fingerprint Part 3"]),
    ]

    passed = 0
    failed = 0

    for fmt, expected_path_prop, expected_fp_props in test_cases:
        path_prop = get_file_path_property_for_format(fmt)
        fp_props = get_fingerprint_properties_for_format(fmt)

        if path_prop == expected_path_prop and fp_props == expected_fp_props:
            logger.info(f"  ✅ {fmt.upper()}: {path_prop} -> {fp_props}")
            passed += 1
        else:
            logger.error(f"  ❌ {fmt.upper()}: {path_prop} -> {fp_props}")
            logger.error(f"     Expected: {expected_path_prop} -> {expected_fp_props}")
            failed += 1

    logger.info(f"\nResults: {passed} passed, {failed} failed")
    return failed == 0


def test_fingerprint_splitting():
    """Test fingerprint splitting for storage."""
    logger.info("\n" + "=" * 60)
    logger.info("TEST: Fingerprint Splitting for Storage")
    logger.info("=" * 60)

    from shared_core.fingerprint_schema import split_fingerprint_for_storage, MAX_FINGERPRINT_CHUNK_LENGTH

    # Test cases: (input, expected_chunks)
    test_cases = [
        # Short fingerprint (fits in one chunk)
        ("abc123" * 10, ["abc123" * 10, "", ""]),
        # Empty fingerprint
        ("", ["", "", ""]),
        # Long fingerprint (needs splitting)
        ("x" * 3000, ["x" * 2000, "x" * 1000, ""]),
        # Very long fingerprint (needs 3 chunks)
        ("y" * 5000, ["y" * 2000, "y" * 2000, "y" * 1000]),
        # Max single chunk
        ("z" * 2000, ["z" * 2000, "", ""]),
    ]

    passed = 0
    failed = 0

    for fingerprint, expected in test_cases:
        result = split_fingerprint_for_storage(fingerprint)

        # Verify chunk count
        if len(result) != 3:
            logger.error(f"  ❌ Wrong chunk count: {len(result)} (expected 3)")
            failed += 1
            continue

        # Verify chunk lengths
        for i, chunk in enumerate(result):
            if len(chunk) > MAX_FINGERPRINT_CHUNK_LENGTH:
                logger.error(f"  ❌ Chunk {i} too long: {len(chunk)} > {MAX_FINGERPRINT_CHUNK_LENGTH}")
                failed += 1
                continue

        # Verify reconstruction
        reconstructed = "".join(result)
        if reconstructed == fingerprint:
            logger.info(f"  ✅ Fingerprint length {len(fingerprint)} -> chunks [{len(result[0])}, {len(result[1])}, {len(result[2])}]")
            passed += 1
        else:
            logger.error(f"  ❌ Reconstruction failed for length {len(fingerprint)}")
            failed += 1

    logger.info(f"\nResults: {passed} passed, {failed} failed")
    return failed == 0


def test_build_update_properties():
    """Test building Notion update properties for fingerprints."""
    logger.info("\n" + "=" * 60)
    logger.info("TEST: Build Update Properties")
    logger.info("=" * 60)

    from shared_core.fingerprint_schema import build_fingerprint_update_properties

    test_cases = [
        # M4A file
        {
            "fingerprint": "abc123",
            "file_path": "/path/to/track.m4a",
            "expected_props": ["M4A Fingerprint"],
        },
        # WAV file
        {
            "fingerprint": "def456",
            "file_path": "/path/to/track.wav",
            "expected_props": ["WAV Fingerprint"],
        },
        # AIFF file
        {
            "fingerprint": "ghi789",
            "file_path": "/path/to/track.aiff",
            "expected_props": ["AIFF Fingerprint"],
        },
        # Long fingerprint (needs Part 2)
        {
            "fingerprint": "x" * 3000,
            "file_path": "/path/to/track.m4a",
            "expected_props": ["M4A Fingerprint", "M4A Fingerprint Part 2"],
        },
    ]

    passed = 0
    failed = 0

    for tc in test_cases:
        result = build_fingerprint_update_properties(
            tc["fingerprint"],
            tc["file_path"],
            None  # No existing properties
        )

        if set(result.keys()) >= set(tc["expected_props"]):
            logger.info(f"  ✅ {Path(tc['file_path']).suffix} -> {list(result.keys())}")
            passed += 1
        else:
            logger.error(f"  ❌ {Path(tc['file_path']).suffix} -> {list(result.keys())}")
            logger.error(f"     Expected at least: {tc['expected_props']}")
            failed += 1

    logger.info(f"\nResults: {passed} passed, {failed} failed")
    return failed == 0


def test_extract_track_fingerprints():
    """Test extracting fingerprints from Notion properties."""
    logger.info("\n" + "=" * 60)
    logger.info("TEST: Extract Track Fingerprints")
    logger.info("=" * 60)

    from shared_core.fingerprint_schema import extract_track_fingerprints, TrackFingerprints

    # Mock Notion properties
    test_properties = {
        "M4A File Path": {"type": "url", "url": "/path/to/track.m4a"},
        "M4A Fingerprint": {"type": "rich_text", "rich_text": [{"plain_text": "m4a_fingerprint_123"}]},
        "WAV File Path": {"type": "url", "url": "/path/to/track.wav"},
        "WAV Fingerprint": {"type": "rich_text", "rich_text": [{"plain_text": "wav_fingerprint_456"}]},
        "AIFF File Path": {"type": "url", "url": ""},  # Empty
        "AIFF Fingerprint": {"type": "rich_text", "rich_text": []},  # Empty
    }

    result = extract_track_fingerprints(test_properties)

    passed = 0
    failed = 0

    # Test M4A fingerprint
    if result.m4a and result.m4a.full_fingerprint == "m4a_fingerprint_123":
        logger.info("  ✅ M4A fingerprint extracted correctly")
        passed += 1
    else:
        logger.error(f"  ❌ M4A fingerprint: {result.m4a.full_fingerprint if result.m4a else 'None'}")
        failed += 1

    # Test WAV fingerprint
    if result.wav and result.wav.full_fingerprint == "wav_fingerprint_456":
        logger.info("  ✅ WAV fingerprint extracted correctly")
        passed += 1
    else:
        logger.error(f"  ❌ WAV fingerprint: {result.wav.full_fingerprint if result.wav else 'None'}")
        failed += 1

    # Test AIFF fingerprint (should be empty)
    if result.aiff and not result.aiff.has_fingerprint:
        logger.info("  ✅ AIFF fingerprint correctly empty")
        passed += 1
    else:
        logger.error(f"  ❌ AIFF fingerprint should be empty: {result.aiff.full_fingerprint if result.aiff else 'None'}")
        failed += 1

    # Test best fingerprint (should be WAV due to priority)
    best_fp, best_fmt = result.get_best_fingerprint()
    if best_fmt == "wav" and best_fp == "wav_fingerprint_456":
        logger.info("  ✅ Best fingerprint is WAV (correct priority)")
        passed += 1
    else:
        logger.error(f"  ❌ Best fingerprint: {best_fmt} = {best_fp}")
        failed += 1

    logger.info(f"\nResults: {passed} passed, {failed} failed")
    return failed == 0


def test_legacy_fallback():
    """Test backward compatibility with legacy fingerprint fields."""
    logger.info("\n" + "=" * 60)
    logger.info("TEST: Legacy Fingerprint Fallback")
    logger.info("=" * 60)

    from shared_core.fingerprint_schema import (
        extract_track_fingerprints,
        has_legacy_fingerprint_only,
        has_per_format_fingerprint,
    )

    # Test 1: Only legacy fingerprint
    legacy_only_props = {
        "M4A File Path": {"type": "url", "url": "/path/to/track.m4a"},
        "M4A Fingerprint": {"type": "rich_text", "rich_text": []},  # Empty
        "Fingerprint": {"type": "rich_text", "rich_text": [{"plain_text": "legacy_fp_123"}]},
    }

    # Test 2: Per-format fingerprint (no legacy)
    per_format_props = {
        "M4A File Path": {"type": "url", "url": "/path/to/track.m4a"},
        "M4A Fingerprint": {"type": "rich_text", "rich_text": [{"plain_text": "m4a_fp_456"}]},
    }

    passed = 0
    failed = 0

    # Test legacy-only detection
    if has_legacy_fingerprint_only(legacy_only_props):
        logger.info("  ✅ Correctly identified legacy-only fingerprint")
        passed += 1
    else:
        logger.error("  ❌ Failed to identify legacy-only fingerprint")
        failed += 1

    # Test per-format detection
    if has_per_format_fingerprint(per_format_props):
        logger.info("  ✅ Correctly identified per-format fingerprint")
        passed += 1
    else:
        logger.error("  ❌ Failed to identify per-format fingerprint")
        failed += 1

    # Test legacy fallback in extraction
    result = extract_track_fingerprints(legacy_only_props)
    if result.legacy_fingerprint == "legacy_fp_123":
        logger.info("  ✅ Legacy fingerprint extracted correctly")
        passed += 1
    else:
        logger.error(f"  ❌ Legacy fingerprint: {result.legacy_fingerprint}")
        failed += 1

    # Test best fingerprint with legacy fallback
    best_fp, best_fmt = result.get_best_fingerprint()
    if best_fmt == "legacy" and best_fp == "legacy_fp_123":
        logger.info("  ✅ Legacy fallback works for get_best_fingerprint()")
        passed += 1
    else:
        logger.error(f"  ❌ Legacy fallback failed: {best_fmt} = {best_fp}")
        failed += 1

    logger.info(f"\nResults: {passed} passed, {failed} failed")
    return failed == 0


def test_fingerprint_matching():
    """Test fingerprint matching logic."""
    logger.info("\n" + "=" * 60)
    logger.info("TEST: Fingerprint Matching")
    logger.info("=" * 60)

    from shared_core.fingerprint_schema import (
        extract_track_fingerprints,
        fingerprints_match,
        get_fingerprint_for_file_path,
    )

    # Mock track with multiple format fingerprints
    test_props = {
        "M4A File Path": {"type": "url", "url": "/path/to/track.m4a"},
        "M4A Fingerprint": {"type": "rich_text", "rich_text": [{"plain_text": "m4a_fp_match"}]},
        "WAV File Path": {"type": "url", "url": "/path/to/track.wav"},
        "WAV Fingerprint": {"type": "rich_text", "rich_text": [{"plain_text": "wav_fp_match"}]},
    }

    track_fps = extract_track_fingerprints(test_props)

    passed = 0
    failed = 0

    # Test matching M4A fingerprint
    is_match, matched_fmt = fingerprints_match("m4a_fp_match", track_fps, "/path/to/track.m4a")
    if is_match and matched_fmt == "m4a":
        logger.info("  ✅ M4A fingerprint match works")
        passed += 1
    else:
        logger.error(f"  ❌ M4A match failed: {is_match}, {matched_fmt}")
        failed += 1

    # Test matching WAV fingerprint
    is_match, matched_fmt = fingerprints_match("wav_fp_match", track_fps, "/path/to/track.wav")
    if is_match and matched_fmt == "wav":
        logger.info("  ✅ WAV fingerprint match works")
        passed += 1
    else:
        logger.error(f"  ❌ WAV match failed: {is_match}, {matched_fmt}")
        failed += 1

    # Test non-matching fingerprint
    is_match, matched_fmt = fingerprints_match("no_match", track_fps)
    if not is_match:
        logger.info("  ✅ Non-matching fingerprint correctly rejected")
        passed += 1
    else:
        logger.error(f"  ❌ Non-match should return False")
        failed += 1

    # Test get_fingerprint_for_file_path
    fp = get_fingerprint_for_file_path("/path/to/track.wav", track_fps)
    if fp == "wav_fp_match":
        logger.info("  ✅ get_fingerprint_for_file_path works")
        passed += 1
    else:
        logger.error(f"  ❌ get_fingerprint_for_file_path: {fp}")
        failed += 1

    logger.info(f"\nResults: {passed} passed, {failed} failed")
    return failed == 0


def main():
    parser = argparse.ArgumentParser(description="Validate per-format fingerprint schema")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    logger.info("=" * 60)
    logger.info("PER-FORMAT FINGERPRINT SCHEMA VALIDATION")
    logger.info("=" * 60)
    logger.info("")

    all_tests = [
        ("Format Detection", test_format_detection),
        ("Property Mapping", test_fingerprint_property_mapping),
        ("Fingerprint Splitting", test_fingerprint_splitting),
        ("Build Update Properties", test_build_update_properties),
        ("Extract Track Fingerprints", test_extract_track_fingerprints),
        ("Legacy Fallback", test_legacy_fallback),
        ("Fingerprint Matching", test_fingerprint_matching),
    ]

    results = []
    for test_name, test_fn in all_tests:
        try:
            passed = test_fn()
            results.append((test_name, passed))
        except Exception as e:
            logger.error(f"  ❌ Test '{test_name}' failed with exception: {e}")
            import traceback
            traceback.print_exc()
            results.append((test_name, False))

    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("VALIDATION SUMMARY")
    logger.info("=" * 60)

    total_passed = sum(1 for _, passed in results if passed)
    total_failed = sum(1 for _, passed in results if not passed)

    for test_name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        logger.info(f"  {status}: {test_name}")

    logger.info("")
    logger.info(f"Total: {total_passed} passed, {total_failed} failed")
    logger.info("=" * 60)

    return 0 if total_failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

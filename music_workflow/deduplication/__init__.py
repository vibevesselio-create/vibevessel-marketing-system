"""Audio deduplication and fingerprinting modules.

This module provides audio fingerprinting and duplicate detection
capabilities for the music workflow system, including:
- Audio fingerprinting for content-based matching
- Notion database deduplication
- Eagle library deduplication
- Multi-source duplicate matching
"""

from music_workflow.deduplication.fingerprint import (
    AudioFingerprint,
    FingerprintGenerator,
    get_fingerprint,
    clear_fingerprint_cache,
)
from music_workflow.deduplication.matcher import (
    Match,
    DuplicateMatcher,
    check_for_duplicates,
)
from music_workflow.deduplication.notion_dedup import (
    NotionMatch,
    NotionDeduplicator,
    check_notion_duplicate,
    check_notion_duplicate_for_batch,
    log_notion_dedup_check,
)
from music_workflow.deduplication.eagle_dedup import (
    EagleMatch,
    EagleDeduplicator,
    check_eagle_duplicate,
)

__all__ = [
    # Fingerprinting
    "AudioFingerprint",
    "FingerprintGenerator",
    "get_fingerprint",
    "clear_fingerprint_cache",
    # Matching
    "Match",
    "DuplicateMatcher",
    "check_for_duplicates",
    # Notion deduplication
    "NotionMatch",
    "NotionDeduplicator",
    "check_notion_duplicate",
    "check_notion_duplicate_for_batch",
    "log_notion_dedup_check",
    # Eagle deduplication
    "EagleMatch",
    "EagleDeduplicator",
    "check_eagle_duplicate",
]

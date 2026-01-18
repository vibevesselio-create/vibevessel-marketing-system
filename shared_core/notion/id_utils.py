#!/usr/bin/env python3
"""
Notion ID Utilities
===================

This module provides utilities for handling Notion database and page IDs,
including format normalization between compact (32-char) and UUID (36-char) formats.

**CRITICAL ISSUE ADDRESSED:**
Database IDs stored in compact format cause Notion API failures because the API
requires standard UUID format (8-4-4-4-12 hyphen pattern).

**MANDATORY USAGE:**
All scripts that use Notion database/page IDs SHOULD normalize them first:

```python
from shared_core.notion.id_utils import normalize_notion_id

# Works with both formats:
db_id = normalize_notion_id("284e73616c278018872aeb14e82e0392")  # Compact
db_id = normalize_notion_id("284e7361-6c27-8018-872a-eb14e82e0392")  # UUID

# Use in API calls:
notion.databases.query(database_id=db_id, ...)
```

Issue: CRITICAL: Database ID Format Mismatch Causes Repeated Notion API Failures
Created: 2025-01-02
Author: Claude Code Agent
"""

import re
from typing import Optional


def normalize_notion_id(id_string: str) -> str:
    """
    Normalize a Notion database or page ID to standard UUID format.

    Notion accepts IDs in both formats, but some API endpoints are stricter.
    This function ensures consistent UUID format (8-4-4-4-12 pattern).

    Args:
        id_string: Notion ID in any format:
            - Compact: "284e73616c278018872aeb14e82e0392" (32 chars, no hyphens)
            - UUID: "284e7361-6c27-8018-872a-eb14e82e0392" (36 chars, with hyphens)

    Returns:
        ID in standard UUID format: "284e7361-6c27-8018-872a-eb14e82e0392"

    Examples:
        >>> normalize_notion_id("284e73616c278018872aeb14e82e0392")
        '284e7361-6c27-8018-872a-eb14e82e0392'

        >>> normalize_notion_id("284e7361-6c27-8018-872a-eb14e82e0392")
        '284e7361-6c27-8018-872a-eb14e82e0392'
    """
    if not id_string:
        return id_string

    # Strip whitespace
    id_string = id_string.strip()

    # Remove any existing hyphens to get clean 32-char string
    clean_id = id_string.replace("-", "")

    # Validate it looks like a hex string
    if not re.match(r"^[a-fA-F0-9]{32}$", clean_id):
        # Return as-is if not a valid Notion ID format
        # This handles edge cases like URLs, invalid input, etc.
        return id_string

    # Convert to standard UUID format (8-4-4-4-12)
    return f"{clean_id[:8]}-{clean_id[8:12]}-{clean_id[12:16]}-{clean_id[16:20]}-{clean_id[20:]}"


def compact_notion_id(id_string: str) -> str:
    """
    Convert a Notion ID to compact format (no hyphens).

    Useful for storage, file naming, or comparison operations.

    Args:
        id_string: Notion ID in any format

    Returns:
        ID in compact format (32 chars, no hyphens)

    Examples:
        >>> compact_notion_id("284e7361-6c27-8018-872a-eb14e82e0392")
        '284e73616c278018872aeb14e82e0392'
    """
    if not id_string:
        return id_string

    return id_string.strip().replace("-", "")


def validate_notion_id(id_string: str) -> bool:
    """
    Validate that a string is a valid Notion database or page ID.

    Accepts both compact (32-char) and UUID (36-char) formats.

    Args:
        id_string: String to validate

    Returns:
        True if valid Notion ID format, False otherwise

    Examples:
        >>> validate_notion_id("284e73616c278018872aeb14e82e0392")
        True
        >>> validate_notion_id("284e7361-6c27-8018-872a-eb14e82e0392")
        True
        >>> validate_notion_id("invalid-id")
        False
    """
    if not id_string or not isinstance(id_string, str):
        return False

    clean_id = id_string.strip().replace("-", "")
    return bool(re.match(r"^[a-fA-F0-9]{32}$", clean_id))


def extract_notion_id_from_url(url: str) -> Optional[str]:
    """
    Extract and normalize Notion ID from a Notion URL.

    Handles various Notion URL formats:
    - https://www.notion.so/workspace/Page-Title-284e73616c278018872aeb14e82e0392
    - https://notion.so/284e73616c278018872aeb14e82e0392
    - https://www.notion.so/284e7361-6c27-8018-872a-eb14e82e0392

    Args:
        url: Notion URL containing a page or database ID

    Returns:
        Normalized UUID format ID, or None if no valid ID found
    """
    if not url:
        return None

    # Pattern to find 32-char hex strings (with or without hyphens)
    # The ID is typically at the end of the URL path
    patterns = [
        r"([a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12})",  # UUID format
        r"([a-fA-F0-9]{32})(?:[?#]|$)",  # Compact format at end
        r"-([a-fA-F0-9]{32})(?:[?#]|$)",  # Compact after hyphen (common in URLs)
    ]

    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return normalize_notion_id(match.group(1))

    return None


# Export all functions
__all__ = [
    "normalize_notion_id",
    "compact_notion_id",
    "validate_notion_id",
    "extract_notion_id_from_url",
]


# Allow running as script for testing
if __name__ == "__main__":
    print("Notion ID Utils - Test Suite")
    print("=" * 60)

    # Test cases
    test_cases = [
        ("284e73616c278018872aeb14e82e0392", "Compact format"),
        ("284e7361-6c27-8018-872a-eb14e82e0392", "UUID format"),
        ("27be7361-6c27-8033-a323-dca0fafa80e6", "Execution logs DB"),
        ("229e73616c27808ebf06c202b10b5166", "Issues+Questions DB"),
    ]

    print("\nNormalize tests:")
    for id_str, desc in test_cases:
        normalized = normalize_notion_id(id_str)
        print(f"  {desc}:")
        print(f"    Input:  {id_str}")
        print(f"    Output: {normalized}")
        print(f"    Valid:  {validate_notion_id(normalized)}")

    print("\nURL extraction tests:")
    test_urls = [
        "https://www.notion.so/workspace/Page-284e73616c278018872aeb14e82e0392",
        "https://notion.so/284e7361-6c27-8018-872a-eb14e82e0392?v=123",
    ]
    for url in test_urls:
        extracted = extract_notion_id_from_url(url)
        print(f"  URL: {url[:50]}...")
        print(f"  Extracted: {extracted}")

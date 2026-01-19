#!/usr/bin/env python3
"""
File Verification Module
========================

Provides comprehensive file verification including:
- File existence checks
- File integrity/corruption detection
- File path resolution and validation
- Batch verification with detailed reporting

This module ensures all sync operations work with verified, non-corrupt files.

Version: 2026-01-18
"""

import hashlib
import logging
import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple, Set

__all__ = [
    "FileStatus",
    "FileVerificationResult",
    "BatchVerificationReport",
    "FileVerifier",
    "EagleFileVerifier",
    "get_eagle_file_verifier",
    "reset_eagle_file_verifier",
    "verify_eagle_library_integrity",
    "FILE_SIGNATURES",
    "MIN_FILE_SIZES",
    "COMPOUND_SIGNATURES",
]

logger = logging.getLogger(__name__)


class FileStatus(Enum):
    """Status of a file after verification."""
    VALID = "valid"
    MISSING = "missing"
    CORRUPT = "corrupt"
    EMPTY = "empty"
    INACCESSIBLE = "inaccessible"
    UNKNOWN = "unknown"


@dataclass
class FileVerificationResult:
    """Result of file verification."""
    path: Optional[Path]
    status: FileStatus
    size: int = 0
    error_message: Optional[str] = None
    content_hash: Optional[str] = None
    header_valid: bool = True

    @property
    def is_valid(self) -> bool:
        """Check if file is valid for processing."""
        return self.status == FileStatus.VALID

    @property
    def is_missing(self) -> bool:
        """Check if file is missing."""
        return self.status == FileStatus.MISSING


@dataclass
class BatchVerificationReport:
    """Report from batch file verification."""
    total_items: int = 0
    valid_count: int = 0
    missing_count: int = 0
    corrupt_count: int = 0
    empty_count: int = 0
    inaccessible_count: int = 0
    results: Dict[str, FileVerificationResult] = field(default_factory=dict)
    missing_items: List[Dict[str, Any]] = field(default_factory=list)
    corrupt_items: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def valid_percentage(self) -> float:
        """Percentage of valid files."""
        if self.total_items == 0:
            return 0.0
        return (self.valid_count / self.total_items) * 100

    @property
    def has_issues(self) -> bool:
        """Check if there are any file issues."""
        return self.missing_count > 0 or self.corrupt_count > 0

    def summary(self) -> str:
        """Generate human-readable summary."""
        lines = [
            f"File Verification Report",
            f"========================",
            f"Total items: {self.total_items}",
            f"Valid: {self.valid_count} ({self.valid_percentage:.1f}%)",
            f"Missing: {self.missing_count}",
            f"Corrupt: {self.corrupt_count}",
            f"Empty: {self.empty_count}",
            f"Inaccessible: {self.inaccessible_count}",
        ]
        return "\n".join(lines)


# File signatures (magic bytes) for common file types
# Format: {extension: [(signature, offset, is_required), ...]}
# For simple formats: [(signature, offset)] means any match is valid (OR logic)
# For compound formats (WAV, AIFF, M4A): use COMPOUND_SIGNATURES dict below
FILE_SIGNATURES = {
    # Audio formats
    ".mp3": [
        (b"\xff\xfb", 0),  # MP3 frame sync (MPEG-1 Layer 3)
        (b"\xff\xfa", 0),  # MP3 frame sync (MPEG-1 Layer 3)
        (b"\xff\xf3", 0),  # MP3 frame sync (MPEG-2 Layer 3)
        (b"\xff\xf2", 0),  # MP3 frame sync (MPEG-2 Layer 3)
        (b"ID3", 0),       # ID3v2 tag (most common)
    ],
    ".flac": [
        (b"fLaC", 0),
    ],
    # Image formats
    ".jpg": [
        (b"\xff\xd8\xff", 0),
    ],
    ".jpeg": [
        (b"\xff\xd8\xff", 0),
    ],
    ".png": [
        (b"\x89PNG\r\n\x1a\n", 0),
    ],
    ".gif": [
        (b"GIF87a", 0),
        (b"GIF89a", 0),
    ],
    # Document formats
    ".pdf": [
        (b"%PDF", 0),
    ],
}

# Compound signatures that require ALL parts to match (AND logic)
# Format: {extension: [(signature1, offset1), (signature2, offset2), ...]}
COMPOUND_SIGNATURES = {
    ".wav": [
        (b"RIFF", 0),
        (b"WAVE", 8),
    ],
    ".aiff": [
        (b"FORM", 0),
        (b"AIFF", 8),
    ],
    ".aif": [
        (b"FORM", 0),
        (b"AIFF", 8),
    ],
    ".webp": [
        (b"RIFF", 0),
        (b"WEBP", 8),
    ],
    # M4A/MP4/MOV all use ISO Base Media File Format with ftyp box
    ".m4a": [
        (b"ftyp", 4),  # ftyp identifier at offset 4 (after 4-byte size)
    ],
    ".mp4": [
        (b"ftyp", 4),
    ],
    ".mov": [
        (b"ftyp", 4),
    ],
}

# Minimum file sizes for different types (in bytes)
MIN_FILE_SIZES = {
    ".mp3": 1024,      # 1KB minimum for audio
    ".m4a": 1024,
    ".wav": 44,        # RIFF header minimum
    ".flac": 42,       # FLAC header minimum
    ".aiff": 12,
    ".aif": 12,
    ".jpg": 107,       # Minimum JPEG
    ".jpeg": 107,
    ".png": 67,        # Minimum PNG
    ".gif": 6,
    ".mp4": 8,
    ".mov": 8,
    ".pdf": 4,
}


class FileVerifier:
    """
    Comprehensive file verification system.

    Performs existence checks, corruption detection, and integrity validation.
    """

    def __init__(
        self,
        check_headers: bool = True,
        compute_hash: bool = False,
        min_size_check: bool = True
    ):
        """
        Initialize file verifier.

        Args:
            check_headers: Whether to verify file headers/magic bytes
            compute_hash: Whether to compute content hash (slower but more thorough)
            min_size_check: Whether to check minimum file sizes
        """
        self.check_headers = check_headers
        self.compute_hash = compute_hash
        self.min_size_check = min_size_check

    def verify_file(self, file_path: Optional[Path]) -> FileVerificationResult:
        """
        Verify a single file.

        Args:
            file_path: Path to the file

        Returns:
            FileVerificationResult with status and details
        """
        if file_path is None:
            return FileVerificationResult(
                path=None,
                status=FileStatus.MISSING,
                error_message="No file path provided"
            )

        path = Path(file_path) if not isinstance(file_path, Path) else file_path

        # Check existence (handles broken symlinks correctly)
        if not path.exists():
            # Check if it's a broken symlink
            if path.is_symlink():
                return FileVerificationResult(
                    path=path,
                    status=FileStatus.MISSING,
                    error_message=f"Broken symlink: {path}"
                )
            return FileVerificationResult(
                path=path,
                status=FileStatus.MISSING,
                error_message=f"File does not exist: {path}"
            )

        # Check if it's a regular file (not directory, etc.)
        if not path.is_file():
            return FileVerificationResult(
                path=path,
                status=FileStatus.CORRUPT,
                error_message=f"Not a regular file: {path}"
            )

        # Check if accessible
        if not os.access(path, os.R_OK):
            return FileVerificationResult(
                path=path,
                status=FileStatus.INACCESSIBLE,
                error_message=f"File is not readable: {path}"
            )

        # Get file size
        try:
            file_size = path.stat().st_size
        except OSError as e:
            return FileVerificationResult(
                path=path,
                status=FileStatus.INACCESSIBLE,
                error_message=f"Cannot stat file: {e}"
            )

        # Check for empty file
        if file_size == 0:
            return FileVerificationResult(
                path=path,
                status=FileStatus.EMPTY,
                size=0,
                error_message="File is empty"
            )

        # Check minimum size
        if self.min_size_check:
            ext = path.suffix.lower()
            min_size = MIN_FILE_SIZES.get(ext, 1)
            if file_size < min_size:
                return FileVerificationResult(
                    path=path,
                    status=FileStatus.CORRUPT,
                    size=file_size,
                    error_message=f"File too small ({file_size} bytes, minimum {min_size})"
                )

        # Check file headers
        header_valid = True
        if self.check_headers:
            header_valid = self._verify_header(path)
            if not header_valid:
                return FileVerificationResult(
                    path=path,
                    status=FileStatus.CORRUPT,
                    size=file_size,
                    header_valid=False,
                    error_message="Invalid file header/magic bytes"
                )

        # Compute hash if requested
        content_hash = None
        if self.compute_hash:
            try:
                content_hash = self._compute_hash(path)
            except Exception as e:
                return FileVerificationResult(
                    path=path,
                    status=FileStatus.CORRUPT,
                    size=file_size,
                    error_message=f"Failed to compute hash: {e}"
                )

        # File is valid
        return FileVerificationResult(
            path=path,
            status=FileStatus.VALID,
            size=file_size,
            content_hash=content_hash,
            header_valid=header_valid
        )

    def _verify_header(self, path: Path) -> bool:
        """
        Verify file header matches expected format.

        Handles both simple signatures (OR logic - any match is valid)
        and compound signatures (AND logic - all must match).

        Args:
            path: Path to file

        Returns:
            True if header is valid or unknown format
        """
        ext = path.suffix.lower()

        # Check for compound signatures first (require ALL to match)
        compound_sigs = COMPOUND_SIGNATURES.get(ext)
        if compound_sigs:
            return self._verify_compound_header(path, compound_sigs)

        # Check simple signatures (any match is valid)
        signatures = FILE_SIGNATURES.get(ext)
        if not signatures:
            # Unknown format, assume valid
            return True

        try:
            with open(path, "rb") as f:
                # Read enough bytes to check all signatures
                max_offset = max(offset + len(sig) for sig, offset in signatures)
                header = f.read(max_offset)

                if len(header) < max_offset:
                    # File too small for header check
                    return False

                # Check if any signature matches (OR logic)
                for signature, offset in signatures:
                    if header[offset:offset + len(signature)] == signature:
                        return True

                return False

        except Exception as e:
            logger.warning(f"Header verification failed for {path}: {e}")
            return False

    def _verify_compound_header(self, path: Path, signatures: List[Tuple[bytes, int]]) -> bool:
        """
        Verify compound file header where ALL signatures must match.

        Args:
            path: Path to file
            signatures: List of (signature, offset) tuples that must all match

        Returns:
            True if all signatures match
        """
        try:
            with open(path, "rb") as f:
                # Read enough bytes to check all signatures
                max_offset = max(offset + len(sig) for sig, offset in signatures)
                header = f.read(max_offset)

                if len(header) < max_offset:
                    return False

                # ALL signatures must match (AND logic)
                for signature, offset in signatures:
                    if header[offset:offset + len(signature)] != signature:
                        return False

                return True

        except Exception as e:
            logger.warning(f"Compound header verification failed for {path}: {e}")
            return False

    def _compute_hash(self, path: Path, algorithm: str = "md5") -> str:
        """
        Compute content hash of file.

        Args:
            path: Path to file
            algorithm: Hash algorithm to use

        Returns:
            Hex digest of hash
        """
        hasher = hashlib.new(algorithm)

        with open(path, "rb") as f:
            while chunk := f.read(8192):
                hasher.update(chunk)

        return hasher.hexdigest()

    def verify_batch(
        self,
        items: List[Dict[str, Any]],
        path_key: str = "file_path",
        id_key: str = "id"
    ) -> BatchVerificationReport:
        """
        Verify multiple items in batch.

        Args:
            items: List of item dictionaries
            path_key: Key for file path in item dict
            id_key: Key for item ID in item dict

        Returns:
            BatchVerificationReport with results
        """
        report = BatchVerificationReport(total_items=len(items))

        for item in items:
            item_id = item.get(id_key, "unknown")
            file_path = item.get(path_key) or item.get("path")

            if file_path:
                path = Path(file_path)
            else:
                path = None

            result = self.verify_file(path)
            report.results[item_id] = result

            if result.status == FileStatus.VALID:
                report.valid_count += 1
            elif result.status == FileStatus.MISSING:
                report.missing_count += 1
                report.missing_items.append(item)
            elif result.status == FileStatus.CORRUPT:
                report.corrupt_count += 1
                report.corrupt_items.append(item)
            elif result.status == FileStatus.EMPTY:
                report.empty_count += 1
                report.corrupt_items.append(item)  # Treat empty as corrupt
            elif result.status == FileStatus.INACCESSIBLE:
                report.inaccessible_count += 1
                report.missing_items.append(item)  # Treat inaccessible as missing

        return report


class EagleFileVerifier(FileVerifier):
    """
    Eagle-specific file verifier with path resolution.

    Handles Eagle's unique file storage structure and resolves
    paths that the API doesn't return.
    """

    def __init__(
        self,
        library_path: Optional[Path] = None,
        check_headers: bool = True,
        compute_hash: bool = False,
        min_size_check: bool = True
    ):
        """
        Initialize Eagle file verifier.

        Args:
            library_path: Path to Eagle library (auto-detected if not provided)
            check_headers: Whether to verify file headers
            compute_hash: Whether to compute content hash
            min_size_check: Whether to check minimum file sizes
        """
        super().__init__(check_headers, compute_hash, min_size_check)
        self._library_path = library_path
        self._path_cache: Dict[str, Optional[Path]] = {}

    @property
    def library_path(self) -> Optional[Path]:
        """Get Eagle library path (lazy loaded)."""
        if self._library_path is None:
            self._library_path = self._get_eagle_library_path()
        return self._library_path

    def _get_eagle_library_path(self) -> Optional[Path]:
        """Get Eagle library path from API or config."""
        # Try Eagle API first
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
                        return lib_path
        except Exception as e:
            logger.debug(f"Could not get library path from Eagle API: {e}")

        # Fallback to environment variable
        env_path = os.getenv("EAGLE_LIBRARY_PATH")
        if env_path:
            path = Path(env_path)
            if path.exists():
                return path

        # Fallback to config
        try:
            from unified_config import get_unified_config
            config = get_unified_config()
            config_path = config.get("eagle_library_path")
            if config_path:
                path = Path(config_path)
                if path.exists():
                    return path
        except Exception:
            pass

        return None

    def resolve_eagle_path(
        self,
        item_id: str,
        ext: str,
        name: Optional[str] = None
    ) -> Optional[Path]:
        """
        Resolve file path for an Eagle item.

        Eagle stores files at: {library_path}/images/{item_id}.info/{filename}.{ext}

        Args:
            item_id: Eagle item ID
            ext: File extension
            name: Optional filename (for better matching)

        Returns:
            Resolved file path or None
        """
        # Validate inputs
        if not item_id:
            return None

        # Handle empty or invalid extension
        if not ext or ext.strip() == "":
            # Try to find any non-metadata file in the info dir
            ext = ""
            cache_key = f"{item_id}:*"
        else:
            cache_key = f"{item_id}:{ext}"

        if cache_key in self._path_cache:
            return self._path_cache[cache_key]

        if not self.library_path:
            self._path_cache[cache_key] = None
            return None

        # Construct info directory path
        info_dir = self.library_path / "images" / f"{item_id}.info"

        if not info_dir.exists() or not info_dir.is_dir():
            self._path_cache[cache_key] = None
            return None

        # Normalize extension (handle empty, with dot, without dot)
        if ext:
            ext_lower = f".{ext.lower().lstrip('.')}"
        else:
            ext_lower = None  # Will match any extension

        # Search for matching file
        for file_path in info_dir.iterdir():
            if not file_path.is_file():
                continue

            # Skip metadata and thumbnail files
            if file_path.name == "metadata.json":
                continue
            if "thumbnail" in file_path.name.lower():
                continue
            if file_path.name.startswith("_"):
                continue

            # Check extension match (or accept any if ext not specified)
            if ext_lower is None or file_path.suffix.lower() == ext_lower:
                self._path_cache[cache_key] = file_path
                return file_path

        self._path_cache[cache_key] = None
        return None

    def verify_eagle_item(
        self,
        item: Dict[str, Any]
    ) -> Tuple[FileVerificationResult, Optional[Path]]:
        """
        Verify an Eagle item, resolving path if needed.

        Args:
            item: Eagle item dictionary

        Returns:
            Tuple of (verification result, resolved path)
        """
        item_id = item.get("id", "")
        ext = item.get("ext", "")
        name = item.get("name", "")

        # Try to use existing path first
        existing_path = item.get("path") or item.get("file_path")
        if existing_path:
            path = Path(existing_path)
            if path.exists():
                result = self.verify_file(path)
                return result, path

        # Resolve path from Eagle structure
        resolved_path = self.resolve_eagle_path(item_id, ext, name)
        if resolved_path:
            result = self.verify_file(resolved_path)
            return result, resolved_path

        # Could not resolve path
        return FileVerificationResult(
            path=None,
            status=FileStatus.MISSING,
            error_message=f"Cannot resolve path for item {item_id}"
        ), None

    def verify_eagle_items(
        self,
        items: List[Dict[str, Any]]
    ) -> BatchVerificationReport:
        """
        Verify multiple Eagle items with path resolution.

        Args:
            items: List of Eagle item dictionaries

        Returns:
            BatchVerificationReport with results and resolved paths
        """
        report = BatchVerificationReport(total_items=len(items))
        resolved_paths: Dict[str, Optional[Path]] = {}

        for item in items:
            item_id = item.get("id", "unknown")

            result, resolved_path = self.verify_eagle_item(item)
            report.results[item_id] = result
            resolved_paths[item_id] = resolved_path

            # Update item with resolved path for downstream use
            if resolved_path:
                item["_resolved_path"] = str(resolved_path)
                item["file_path"] = str(resolved_path)
                item["path"] = str(resolved_path)

            if result.status == FileStatus.VALID:
                report.valid_count += 1
            elif result.status == FileStatus.MISSING:
                report.missing_count += 1
                report.missing_items.append(item)
            elif result.status == FileStatus.CORRUPT:
                report.corrupt_count += 1
                report.corrupt_items.append(item)
            elif result.status == FileStatus.EMPTY:
                report.empty_count += 1
                report.corrupt_items.append(item)
            elif result.status == FileStatus.INACCESSIBLE:
                report.inaccessible_count += 1
                report.missing_items.append(item)

        logger.info(report.summary())

        return report

    def clear_cache(self) -> None:
        """Clear path resolution cache."""
        self._path_cache.clear()


# Singleton instance
_eagle_verifier: Optional[EagleFileVerifier] = None
_eagle_verifier_path: Optional[Path] = None


def get_eagle_file_verifier(
    library_path: Optional[Path] = None
) -> EagleFileVerifier:
    """
    Get the global Eagle file verifier instance.

    Args:
        library_path: Optional library path override (creates new instance if different)

    Returns:
        EagleFileVerifier instance
    """
    global _eagle_verifier, _eagle_verifier_path

    # Create new instance if:
    # 1. No instance exists
    # 2. A different library_path is requested
    needs_new_instance = (
        _eagle_verifier is None or
        (library_path is not None and library_path != _eagle_verifier_path)
    )

    if needs_new_instance:
        _eagle_verifier = EagleFileVerifier(library_path=library_path)
        _eagle_verifier_path = library_path

    return _eagle_verifier


def reset_eagle_file_verifier() -> None:
    """Reset the global Eagle file verifier instance (for testing)."""
    global _eagle_verifier, _eagle_verifier_path
    _eagle_verifier = None
    _eagle_verifier_path = None


def verify_eagle_library_integrity(
    filter_extension: Optional[str] = None,
    limit: Optional[int] = None
) -> BatchVerificationReport:
    """
    Verify integrity of entire Eagle library.

    Args:
        filter_extension: Optional extension to filter by
        limit: Optional limit on number of items to check

    Returns:
        BatchVerificationReport with full results
    """
    verifier = get_eagle_file_verifier()

    # Get all items from Eagle API
    try:
        import urllib.request
        import json

        params = {}
        if filter_extension:
            params["ext"] = filter_extension
        if limit:
            params["limit"] = limit

        url = 'http://localhost:41595/api/item/list'
        if params:
            from urllib.parse import urlencode
            url = f"{url}?{urlencode(params)}"

        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=30) as response:
            data = json.loads(response.read().decode('utf-8'))
            items = data.get('data', [])

    except Exception as e:
        logger.error(f"Failed to get Eagle items: {e}")
        return BatchVerificationReport()

    return verifier.verify_eagle_items(items)

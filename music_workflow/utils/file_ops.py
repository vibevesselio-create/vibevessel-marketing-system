"""
File operation utilities for music workflow.

This module provides safe file operations with proper error handling,
validation, and backup support.
"""

import hashlib
import os
import shutil
from pathlib import Path
from typing import List, Optional, Tuple

from music_workflow.utils.errors import FileOperationError


def ensure_directory(path: Path) -> Path:
    """Ensure a directory exists, creating it if necessary.

    Args:
        path: Directory path

    Returns:
        The directory path

    Raises:
        FileOperationError: If directory cannot be created
    """
    try:
        path.mkdir(parents=True, exist_ok=True)
        return path
    except OSError as e:
        raise FileOperationError(
            f"Failed to create directory: {path}",
            file_path=str(path),
            operation="mkdir",
            details={"error": str(e)},
        )


def safe_copy(
    source: Path, destination: Path, overwrite: bool = False
) -> Path:
    """Safely copy a file with verification.

    Args:
        source: Source file path
        destination: Destination file path
        overwrite: Whether to overwrite existing files

    Returns:
        Destination path

    Raises:
        FileOperationError: If copy fails
    """
    if not source.exists():
        raise FileOperationError(
            f"Source file does not exist: {source}",
            file_path=str(source),
            operation="copy",
        )

    if destination.exists() and not overwrite:
        raise FileOperationError(
            f"Destination already exists: {destination}",
            file_path=str(destination),
            operation="copy",
            details={"hint": "Use overwrite=True to replace"},
        )

    try:
        # Ensure destination directory exists
        ensure_directory(destination.parent)

        # Copy file
        shutil.copy2(source, destination)

        # Verify copy
        if not destination.exists():
            raise FileOperationError(
                f"Copy verification failed: {destination}",
                file_path=str(destination),
                operation="copy",
            )

        return destination
    except (OSError, shutil.Error) as e:
        raise FileOperationError(
            f"Failed to copy file: {source} -> {destination}",
            file_path=str(source),
            operation="copy",
            details={"error": str(e)},
        )


def safe_move(
    source: Path, destination: Path, overwrite: bool = False
) -> Path:
    """Safely move a file with verification.

    Args:
        source: Source file path
        destination: Destination file path
        overwrite: Whether to overwrite existing files

    Returns:
        Destination path

    Raises:
        FileOperationError: If move fails
    """
    if not source.exists():
        raise FileOperationError(
            f"Source file does not exist: {source}",
            file_path=str(source),
            operation="move",
        )

    if destination.exists() and not overwrite:
        raise FileOperationError(
            f"Destination already exists: {destination}",
            file_path=str(destination),
            operation="move",
            details={"hint": "Use overwrite=True to replace"},
        )

    try:
        # Ensure destination directory exists
        ensure_directory(destination.parent)

        # Move file
        shutil.move(str(source), str(destination))

        # Verify move
        if not destination.exists():
            raise FileOperationError(
                f"Move verification failed: {destination}",
                file_path=str(destination),
                operation="move",
            )

        return destination
    except (OSError, shutil.Error) as e:
        raise FileOperationError(
            f"Failed to move file: {source} -> {destination}",
            file_path=str(source),
            operation="move",
            details={"error": str(e)},
        )


def safe_delete(path: Path, verify: bool = True) -> bool:
    """Safely delete a file or directory.

    Args:
        path: Path to delete
        verify: Whether to verify deletion

    Returns:
        True if deleted successfully

    Raises:
        FileOperationError: If deletion fails
    """
    if not path.exists():
        return True  # Already doesn't exist

    try:
        if path.is_file():
            path.unlink()
        elif path.is_dir():
            shutil.rmtree(path)

        if verify and path.exists():
            raise FileOperationError(
                f"Delete verification failed: {path}",
                file_path=str(path),
                operation="delete",
            )

        return True
    except OSError as e:
        raise FileOperationError(
            f"Failed to delete: {path}",
            file_path=str(path),
            operation="delete",
            details={"error": str(e)},
        )


def calculate_file_hash(
    path: Path, algorithm: str = "sha256", chunk_size: int = 65536
) -> str:
    """Calculate hash of a file.

    Args:
        path: File path
        algorithm: Hash algorithm (md5, sha256, etc.)
        chunk_size: Read chunk size

    Returns:
        Hex digest of hash

    Raises:
        FileOperationError: If hash calculation fails
    """
    if not path.exists():
        raise FileOperationError(
            f"File does not exist: {path}",
            file_path=str(path),
            operation="hash",
        )

    try:
        hash_obj = hashlib.new(algorithm)
        with open(path, "rb") as f:
            while chunk := f.read(chunk_size):
                hash_obj.update(chunk)
        return hash_obj.hexdigest()
    except (OSError, ValueError) as e:
        raise FileOperationError(
            f"Failed to calculate hash: {path}",
            file_path=str(path),
            operation="hash",
            details={"error": str(e), "algorithm": algorithm},
        )


def get_file_size(path: Path) -> int:
    """Get file size in bytes.

    Args:
        path: File path

    Returns:
        File size in bytes

    Raises:
        FileOperationError: If size cannot be determined
    """
    if not path.exists():
        raise FileOperationError(
            f"File does not exist: {path}",
            file_path=str(path),
            operation="size",
        )

    try:
        return path.stat().st_size
    except OSError as e:
        raise FileOperationError(
            f"Failed to get file size: {path}",
            file_path=str(path),
            operation="size",
            details={"error": str(e)},
        )


def find_files(
    directory: Path,
    pattern: str = "*",
    recursive: bool = True,
    extensions: Optional[List[str]] = None,
) -> List[Path]:
    """Find files matching a pattern.

    Args:
        directory: Directory to search
        pattern: Glob pattern
        recursive: Whether to search recursively
        extensions: Optional list of allowed extensions

    Returns:
        List of matching file paths
    """
    if not directory.exists():
        return []

    if recursive:
        files = list(directory.rglob(pattern))
    else:
        files = list(directory.glob(pattern))

    # Filter by extension if specified
    if extensions:
        ext_set = {ext.lower().lstrip(".") for ext in extensions}
        files = [f for f in files if f.suffix.lower().lstrip(".") in ext_set]

    return sorted(files)


def create_backup(
    source: Path, backup_dir: Path, timestamp: bool = True
) -> Tuple[Path, str]:
    """Create a backup of a file.

    Args:
        source: Source file path
        backup_dir: Backup directory
        timestamp: Whether to add timestamp to filename

    Returns:
        Tuple of (backup path, original hash)

    Raises:
        FileOperationError: If backup fails
    """
    if not source.exists():
        raise FileOperationError(
            f"Source file does not exist: {source}",
            file_path=str(source),
            operation="backup",
        )

    # Calculate original hash
    original_hash = calculate_file_hash(source)

    # Generate backup filename
    if timestamp:
        from datetime import datetime
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"{source.stem}_{ts}{source.suffix}"
    else:
        backup_name = source.name

    backup_path = backup_dir / backup_name

    # Copy to backup location
    safe_copy(source, backup_path, overwrite=True)

    return backup_path, original_hash

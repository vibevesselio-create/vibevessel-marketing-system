"""Unit tests for file_ops module."""

import pytest
import tempfile
from pathlib import Path
from music_workflow.utils.file_ops import (
    ensure_directory,
    safe_copy,
    safe_move,
    safe_delete,
    calculate_file_hash,
    get_file_size,
    find_files,
    create_backup,
)
from music_workflow.utils.errors import FileOperationError


class TestEnsureDirectory:
    """Tests for ensure_directory function."""

    def test_create_new_directory(self, tmp_path):
        """Test creating a new directory."""
        new_dir = tmp_path / "new_directory"
        result = ensure_directory(new_dir)
        assert result.exists()
        assert result.is_dir()

    def test_existing_directory(self, tmp_path):
        """Test with existing directory."""
        result = ensure_directory(tmp_path)
        assert result.exists()
        assert result.is_dir()

    def test_nested_directory(self, tmp_path):
        """Test creating nested directories."""
        nested = tmp_path / "level1" / "level2" / "level3"
        result = ensure_directory(nested)
        assert result.exists()


class TestSafeCopy:
    """Tests for safe_copy function."""

    def test_copy_file(self, tmp_path):
        """Test copying a file."""
        source = tmp_path / "source.txt"
        source.write_text("test content")
        dest = tmp_path / "dest.txt"

        result = safe_copy(source, dest)
        assert result.exists()
        assert result.read_text() == "test content"
        assert source.exists()  # Source still exists

    def test_copy_with_overwrite(self, tmp_path):
        """Test copying with overwrite."""
        source = tmp_path / "source.txt"
        source.write_text("new content")
        dest = tmp_path / "dest.txt"
        dest.write_text("old content")

        result = safe_copy(source, dest, overwrite=True)
        assert result.read_text() == "new content"

    def test_copy_no_overwrite_fails(self, tmp_path):
        """Test copying without overwrite raises error."""
        source = tmp_path / "source.txt"
        source.write_text("new content")
        dest = tmp_path / "dest.txt"
        dest.write_text("old content")

        with pytest.raises(FileOperationError):
            safe_copy(source, dest, overwrite=False)

    def test_copy_nonexistent_source(self, tmp_path):
        """Test copying nonexistent source raises error."""
        source = tmp_path / "nonexistent.txt"
        dest = tmp_path / "dest.txt"

        with pytest.raises(FileOperationError):
            safe_copy(source, dest)


class TestSafeMove:
    """Tests for safe_move function."""

    def test_move_file(self, tmp_path):
        """Test moving a file."""
        source = tmp_path / "source.txt"
        source.write_text("test content")
        dest = tmp_path / "dest.txt"

        result = safe_move(source, dest)
        assert result.exists()
        assert result.read_text() == "test content"
        assert not source.exists()  # Source no longer exists


class TestSafeDelete:
    """Tests for safe_delete function."""

    def test_delete_file(self, tmp_path):
        """Test deleting a file."""
        file = tmp_path / "test.txt"
        file.write_text("test")

        result = safe_delete(file)
        assert result is True
        assert not file.exists()

    def test_delete_nonexistent(self, tmp_path):
        """Test deleting nonexistent file returns True (already doesn't exist)."""
        file = tmp_path / "nonexistent.txt"

        # Implementation returns True for nonexistent files (already doesn't exist)
        result = safe_delete(file)
        assert result is True


class TestCalculateFileHash:
    """Tests for calculate_file_hash function."""

    def test_hash_file(self, tmp_path):
        """Test calculating file hash."""
        file = tmp_path / "test.txt"
        file.write_text("test content")

        hash1 = calculate_file_hash(file)
        assert hash1 is not None
        assert len(hash1) == 64  # SHA256 hex length

    def test_same_content_same_hash(self, tmp_path):
        """Test same content produces same hash."""
        file1 = tmp_path / "file1.txt"
        file2 = tmp_path / "file2.txt"
        file1.write_text("same content")
        file2.write_text("same content")

        hash1 = calculate_file_hash(file1)
        hash2 = calculate_file_hash(file2)
        assert hash1 == hash2

    def test_different_content_different_hash(self, tmp_path):
        """Test different content produces different hash."""
        file1 = tmp_path / "file1.txt"
        file2 = tmp_path / "file2.txt"
        file1.write_text("content 1")
        file2.write_text("content 2")

        hash1 = calculate_file_hash(file1)
        hash2 = calculate_file_hash(file2)
        assert hash1 != hash2


class TestGetFileSize:
    """Tests for get_file_size function."""

    def test_get_size(self, tmp_path):
        """Test getting file size."""
        file = tmp_path / "test.txt"
        content = "test content"
        file.write_text(content)

        size = get_file_size(file)
        assert size == len(content)

    def test_nonexistent_file(self, tmp_path):
        """Test getting size of nonexistent file raises FileOperationError."""
        file = tmp_path / "nonexistent.txt"

        with pytest.raises(FileOperationError):
            get_file_size(file)


class TestFindFiles:
    """Tests for find_files function."""

    def test_find_by_pattern(self, tmp_path):
        """Test finding files by pattern."""
        (tmp_path / "test1.txt").write_text("1")
        (tmp_path / "test2.txt").write_text("2")
        (tmp_path / "other.md").write_text("3")

        files = find_files(tmp_path, "*.txt")
        assert len(files) == 2
        assert all(f.suffix == ".txt" for f in files)

    def test_find_no_matches(self, tmp_path):
        """Test finding with no matches."""
        (tmp_path / "test.txt").write_text("1")

        files = find_files(tmp_path, "*.py")
        assert len(files) == 0


class TestCreateBackup:
    """Tests for create_backup function."""

    def test_create_backup(self, tmp_path):
        """Test creating a backup."""
        source = tmp_path / "source.txt"
        source.write_text("test content")
        backup_dir = tmp_path / "backups"

        backup_path, file_hash = create_backup(source, backup_dir)

        assert backup_path.exists()
        assert backup_path.read_text() == "test content"
        assert "source" in backup_path.name
        assert file_hash is not None
        assert len(file_hash) == 64  # SHA256 hex length

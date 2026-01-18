"""Unit tests for validators module."""

import pytest
from pathlib import Path
from music_workflow.utils.validators import (
    validate_url,
    validate_bpm,
    validate_key,
    sanitize_filename,
    validate_notion_page_id,
    validate_spotify_id,
)
from music_workflow.utils.errors import ValidationError
from music_workflow.config.constants import Platform


class TestValidateUrl:
    """Tests for validate_url function."""

    def test_youtube_url(self):
        """Test YouTube URL validation."""
        is_valid, platform = validate_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        assert is_valid is True
        assert platform == Platform.YOUTUBE

    def test_youtube_short_url(self):
        """Test YouTube short URL validation."""
        is_valid, platform = validate_url("https://youtu.be/dQw4w9WgXcQ")
        assert is_valid is True
        assert platform == Platform.YOUTUBE

    def test_soundcloud_url(self):
        """Test SoundCloud URL validation."""
        is_valid, platform = validate_url("https://soundcloud.com/artist/track")
        assert is_valid is True
        assert platform == Platform.SOUNDCLOUD

    def test_spotify_url(self):
        """Test Spotify URL validation."""
        is_valid, platform = validate_url("https://open.spotify.com/track/abc123")
        assert is_valid is True
        assert platform == Platform.SPOTIFY

    def test_invalid_url(self):
        """Test invalid URL validation raises ValidationError."""
        with pytest.raises(ValidationError):
            validate_url("not-a-url")

    def test_empty_url(self):
        """Test empty URL validation raises ValidationError."""
        with pytest.raises(ValidationError):
            validate_url("")


class TestValidateBpm:
    """Tests for validate_bpm function."""

    def test_valid_bpm(self):
        """Test valid BPM values."""
        assert validate_bpm(120.0) == 120.0
        assert validate_bpm(60.0) == 60.0
        assert validate_bpm(200.0) == 200.0

    def test_invalid_bpm_too_low(self):
        """Test BPM below minimum raises ValidationError."""
        with pytest.raises(ValidationError):
            validate_bpm(10.0)

    def test_invalid_bpm_too_high(self):
        """Test BPM above maximum raises ValidationError."""
        with pytest.raises(ValidationError):
            validate_bpm(500.0)

    def test_invalid_bpm_none(self):
        """Test None BPM raises ValidationError."""
        with pytest.raises(ValidationError):
            validate_bpm(None)


class TestValidateKey:
    """Tests for validate_key function."""

    def test_valid_major_keys(self):
        """Test valid major keys."""
        assert validate_key("C") == "C"
        assert validate_key("D") == "D"
        assert validate_key("Eb") == "Eb"
        assert validate_key("F#") == "F#"

    def test_valid_minor_keys(self):
        """Test valid minor keys."""
        assert validate_key("Am") == "Am"
        assert validate_key("Bm") == "Bm"
        assert validate_key("Dbm") == "Dbm"

    def test_invalid_keys(self):
        """Test invalid keys raise ValidationError."""
        with pytest.raises(ValidationError):
            validate_key("X")
        with pytest.raises(ValidationError):
            validate_key("Cmaj7")
        with pytest.raises(ValidationError):
            validate_key("")
        with pytest.raises(ValidationError):
            validate_key(None)


class TestSanitizeFilename:
    """Tests for sanitize_filename function."""

    def test_clean_filename(self):
        """Test already clean filename."""
        result = sanitize_filename("track_name")
        assert result == "track name"  # underscores get replaced with spaces

    def test_filename_with_special_chars(self):
        """Test filename with special characters."""
        result = sanitize_filename("track/name:with*special?chars")
        assert "/" not in result
        assert ":" not in result
        assert "*" not in result
        assert "?" not in result

    def test_filename_with_spaces(self):
        """Test filename with spaces."""
        result = sanitize_filename("track name with spaces")
        assert result == "track name with spaces"

    def test_long_filename(self):
        """Test filename truncation."""
        long_name = "a" * 300
        result = sanitize_filename(long_name)
        assert len(result) <= 200  # default max_length


class TestValidateNotionPageId:
    """Tests for validate_notion_page_id function."""

    def test_valid_page_id(self):
        """Test valid Notion page ID."""
        result = validate_notion_page_id("12345678-1234-1234-1234-123456789abc")
        assert result == "12345678-1234-1234-1234-123456789abc"

    def test_valid_page_id_no_dashes(self):
        """Test valid Notion page ID without dashes."""
        result = validate_notion_page_id("123456781234123412341234567890ab")
        assert result == "123456781234123412341234567890ab"

    def test_invalid_page_id(self):
        """Test invalid Notion page ID raises ValidationError."""
        with pytest.raises(ValidationError):
            validate_notion_page_id("not-a-valid-id")
        with pytest.raises(ValidationError):
            validate_notion_page_id("")
        with pytest.raises(ValidationError):
            validate_notion_page_id(None)


class TestValidateSpotifyId:
    """Tests for validate_spotify_id function."""

    def test_valid_spotify_id(self):
        """Test valid Spotify ID."""
        result = validate_spotify_id("4cOdK2wGLETKBW3PvgPWqT")
        assert result == "4cOdK2wGLETKBW3PvgPWqT"

    def test_invalid_spotify_id(self):
        """Test invalid Spotify ID raises ValidationError."""
        with pytest.raises(ValidationError):
            validate_spotify_id("short")
        with pytest.raises(ValidationError):
            validate_spotify_id("")
        with pytest.raises(ValidationError):
            validate_spotify_id(None)

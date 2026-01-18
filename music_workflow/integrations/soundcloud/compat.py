"""
Compatibility adapter for SoundCloud integration migration.

This module provides adapter functions that maintain compatibility with
the monolithic script's SoundCloud usage patterns while using the new
integration module under the hood.

This is a transitional module to facilitate gradual migration.
"""

import os
import logging
from pathlib import Path
from typing import Dict, Optional, Any, List
from urllib.parse import urlparse, unquote

from music_workflow.integrations.soundcloud.client import (
    SoundCloudClient,
    SoundCloudTrack,
    SoundCloudIntegrationError,
    get_soundcloud_client,
)
from music_workflow.utils.errors import DownloadError

logger = logging.getLogger(__name__)


def parse_soundcloud_url(url: str) -> tuple[Optional[str], Optional[str]]:
    """
    Parse artist and track from SoundCloud URL.
    
    Compatible with the monolithic script's parse_soundcloud_url function.
    
    Args:
        url: SoundCloud track URL
        
    Returns:
        Tuple of (artist, track) or (None, None) if parsing fails
    """
    try:
        parts = urlparse(url).path.strip('/').split('/')
        if len(parts) >= 2:
            artist = unquote(parts[0])
            track = unquote(parts[1])
            return artist, track
        return None, None
    except Exception as e:
        logger.error(f"Failed to parse SoundCloud URL: {e}")
        return None, None


def extract_track_info_with_retry(
    url: str,
    max_retries: int = 3,
    retry_delay: int = 2,
    auth_header: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Extract track metadata with retry logic.
    
    Compatible with monolithic script's yt-dlp extraction pattern.
    Includes retry logic and error handling similar to the original.
    
    Args:
        url: SoundCloud track URL
        max_retries: Maximum number of retry attempts
        retry_delay: Initial delay between retries (exponential backoff)
        auth_header: Optional authorization header (for future use)
        
    Returns:
        Dictionary with track metadata or None if extraction fails
    """
    client = get_soundcloud_client()
    
    for attempt in range(max_retries + 1):
        try:
            info = client.extract_info(url)
            if info:
                # Convert to format expected by monolithic script
                track = client.get_track(url)
                if track:
                    return {
                        'id': track.id,
                        'title': track.title,
                        'uploader': track.artist,
                        'artist': track.artist,
                        'creator': track.artist,
                        'channel': track.artist,
                        'duration': track.duration_seconds,
                        'genre': track.genre,
                        'description': track.description,
                        'thumbnail': track.artwork_url,
                        'view_count': track.play_count,
                        'like_count': track.like_count,
                        'webpage_url': track.url,
                        'url': track.url,
                        'upload_date': track.upload_date,
                        'tags': track.tags,
                    }
            return None
            
        except SoundCloudIntegrationError as e:
            error_msg = str(e)
            
            # Check for 404 errors
            if "404" in error_msg or "Not Found" in error_msg:
                logger.info("Permanent 404. Aborting retries.")
                return None
            
            # Check for rate limiting
            if "429" in error_msg or attempt < max_retries:
                wait_time = min(60, retry_delay * (2 ** attempt))
                logger.info(f"Sleeping {wait_time}s before retry {attempt + 1}/{max_retries}")
                import time
                time.sleep(wait_time)
                continue
            
            logger.error(f"SoundCloud extraction error: {e}")
            return None
            
        except Exception as e:
            if attempt < max_retries:
                wait_time = min(60, retry_delay * (2 ** attempt))
                logger.info(f"Sleeping {wait_time}s before retry {attempt + 1}/{max_retries}")
                import time
                time.sleep(wait_time)
                continue
            logger.error(f"Unexpected error during extraction: {e}")
            return None
    
    return None


def download_track_to_wav(
    url: str,
    output_dir: Path,
    temp_dir: Optional[Path] = None,
    auth_header: Optional[str] = None,
) -> Optional[Path]:
    """
    Download SoundCloud track and convert to WAV format.
    
    Compatible with monolithic script's download pattern.
    Downloads track and converts to WAV using yt-dlp's postprocessing.
    
    Args:
        url: SoundCloud track URL
        output_dir: Directory to save the WAV file
        temp_dir: Optional temporary directory for intermediate files
        auth_header: Optional authorization header (for future use)
        
    Returns:
        Path to downloaded WAV file or None if download fails
    """
    client = get_soundcloud_client()
    
    # Use temp_dir if provided, otherwise use output_dir
    download_dir = temp_dir or output_dir
    download_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        # Download as WAV (best quality)
        downloaded_files = client.download(
            url=url,
            output_dir=download_dir,
            formats=["wav"],
            template="%(title)s.%(ext)s",
        )
        
        if "wav" in downloaded_files:
            wav_file = downloaded_files["wav"]
            
            # If downloaded to temp_dir, move to output_dir
            if temp_dir and wav_file.parent != output_dir:
                final_path = output_dir / wav_file.name
                import shutil
                shutil.move(str(wav_file), str(final_path))
                return final_path
            
            return wav_file
        
        return None
        
    except DownloadError as e:
        logger.error(f"Download failed: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected download error: {e}")
        return None


def is_preview_track(duration: Optional[float]) -> bool:
    """
    Check if track duration suggests it's a SoundCloud Go+ preview.
    
    Preview tracks are typically 25-35 seconds long.
    
    Args:
        duration: Track duration in seconds
        
    Returns:
        True if duration suggests preview track
    """
    if duration is None:
        return False
    return 25 <= duration <= 35


def is_geo_restricted(error: Exception) -> bool:
    """
    Check if error indicates geo-restriction.
    
    Args:
        error: Exception from download/extraction
        
    Returns:
        True if error suggests geo-restriction
    """
    error_msg = str(error).lower()
    geo_indicators = [
        "geo",
        "georestricted",
        "georestriction",
        "not available in your country",
        "blocked in your region",
        "region",
    ]
    return any(indicator in error_msg for indicator in geo_indicators)


__all__ = [
    "parse_soundcloud_url",
    "extract_track_info_with_retry",
    "download_track_to_wav",
    "is_preview_track",
    "is_geo_restricted",
]

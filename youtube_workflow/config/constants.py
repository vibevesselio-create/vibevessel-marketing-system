"""Constants for YouTube workflow."""

from enum import Enum


class Platform(Enum):
    """Supported platforms for media sources."""

    YOUTUBE = "youtube"
    SOUNDCLOUD = "soundcloud"
    SPOTIFY = "spotify"
    BANDCAMP = "bandcamp"
    UNKNOWN = "unknown"


class SearchStrategy(Enum):
    """Search strategies for finding YouTube videos."""

    EXACT = "exact"
    OFFICIAL_AUDIO = "official_audio"
    AUDIO_ONLY = "audio_only"
    TITLE_ONLY = "title_only"
    CLEANED = "cleaned"
    FIRST_ARTIST = "first_artist"


class VideoQuality(Enum):
    """Video quality presets."""

    BEST = "best"
    HIGH = "1080"
    MEDIUM = "720"
    LOW = "480"


class AudioFormat(Enum):
    """Supported audio output formats."""

    WAV = "wav"
    MP3 = "mp3"
    M4A = "m4a"
    FLAC = "flac"
    AIFF = "aiff"
    OGG = "ogg"


class VideoFormat(Enum):
    """Supported video output formats."""

    MP4 = "mp4"
    MKV = "mkv"
    WEBM = "webm"
    AVI = "avi"


# YouTube URL patterns
YOUTUBE_URL_PATTERNS = [
    r"(?:https?://)?(?:www\.)?youtube\.com/watch\?v=([a-zA-Z0-9_-]{11})",
    r"(?:https?://)?(?:www\.)?youtu\.be/([a-zA-Z0-9_-]{11})",
    r"(?:https?://)?(?:www\.)?youtube\.com/embed/([a-zA-Z0-9_-]{11})",
    r"(?:https?://)?(?:www\.)?youtube\.com/v/([a-zA-Z0-9_-]{11})",
]

# YouTube Data API v3 quotas (units per operation)
API_QUOTA_COSTS = {
    "search.list": 100,
    "videos.list": 1,
    "channels.list": 1,
    "playlists.list": 1,
    "playlistItems.list": 1,
}

# Default daily quota
DEFAULT_DAILY_QUOTA = 10000

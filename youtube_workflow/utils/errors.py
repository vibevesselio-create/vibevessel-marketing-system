"""Custom exceptions for YouTube workflow.

Hierarchy aligned with music_workflow and image_workflow error patterns.
"""


class YouTubeWorkflowError(Exception):
    """Base exception for YouTube workflow errors."""

    def __init__(self, message: str, details: dict = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class SearchError(YouTubeWorkflowError):
    """Error during YouTube search operations."""

    def __init__(self, message: str, query: str = None, strategy: str = None):
        super().__init__(message, {"query": query, "strategy": strategy})
        self.query = query
        self.strategy = strategy


class DownloadError(YouTubeWorkflowError):
    """Error during YouTube download operations."""

    def __init__(self, message: str, video_id: str = None, url: str = None):
        super().__init__(message, {"video_id": video_id, "url": url})
        self.video_id = video_id
        self.url = url


class APIError(YouTubeWorkflowError):
    """Error from YouTube Data API."""

    def __init__(self, message: str, status_code: int = None, reason: str = None):
        super().__init__(message, {"status_code": status_code, "reason": reason})
        self.status_code = status_code
        self.reason = reason


class QuotaExceededError(APIError):
    """YouTube API quota exceeded."""

    def __init__(self, message: str = "YouTube API quota exceeded"):
        super().__init__(message, status_code=403, reason="quotaExceeded")


class VideoUnavailableError(DownloadError):
    """Video is unavailable (private, deleted, geo-restricted)."""

    def __init__(self, message: str, video_id: str = None, reason: str = None):
        super().__init__(message, video_id=video_id)
        self.reason = reason


class AuthenticationError(YouTubeWorkflowError):
    """Error with Google/YouTube authentication."""

    def __init__(self, message: str, account: str = None):
        super().__init__(message, {"account": account})
        self.account = account


class AccountRoutingError(YouTubeWorkflowError):
    """Error routing to correct Google account."""

    def __init__(self, message: str, requested_account: str = None):
        super().__init__(message, {"requested_account": requested_account})
        self.requested_account = requested_account

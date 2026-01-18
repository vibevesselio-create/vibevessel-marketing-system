"""
Custom exception classes for image workflow.

Mirrors music_workflow/utils/errors.py pattern for consistency.
"""

from typing import Any, Dict, Optional


class ImageWorkflowError(Exception):
    """Base exception for all image workflow errors."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def __str__(self) -> str:
        if self.details:
            return f"{self.message} - Details: {self.details}"
        return self.message


class ProcessingError(ImageWorkflowError):
    """Error during image processing (fingerprinting, analysis, etc.)."""

    def __init__(
        self,
        message: str,
        file_path: Optional[str] = None,
        operation: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message, details)
        self.file_path = file_path
        self.operation = operation  # e.g., "fingerprint", "exif_extract", "perceptual_hash"

    def __str__(self) -> str:
        parts = [self.message]
        if self.operation:
            parts.append(f"Operation: {self.operation}")
        if self.file_path:
            parts.append(f"File: {self.file_path}")
        return " | ".join(parts)


class FingerprintError(ProcessingError):
    """Error computing image fingerprint or hash."""

    def __init__(
        self,
        message: str,
        file_path: Optional[str] = None,
        hash_type: Optional[str] = None,  # "sha256", "perceptual", "color"
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message, file_path, "fingerprint", details)
        self.hash_type = hash_type


class DuplicateFoundError(ImageWorkflowError):
    """Raised when a duplicate image is found."""

    def __init__(
        self,
        message: str,
        existing_uii: Optional[str] = None,
        existing_source: Optional[str] = None,
        similarity_score: float = 0.0,
        match_method: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message, details)
        self.existing_uii = existing_uii
        self.existing_source = existing_source
        self.similarity_score = similarity_score
        self.match_method = match_method  # "exact_hash", "perceptual", "metadata"

    def __str__(self) -> str:
        parts = [self.message]
        if self.existing_uii:
            parts.append(f"Existing UII: {self.existing_uii}")
        if self.existing_source:
            parts.append(f"Source: {self.existing_source}")
        if self.similarity_score > 0:
            parts.append(f"Similarity: {self.similarity_score:.2%}")
        return " | ".join(parts)


class IntegrationError(ImageWorkflowError):
    """Error communicating with external service (Notion, Eagle, Drive, etc.)."""

    def __init__(
        self,
        message: str,
        service: Optional[str] = None,  # "notion", "eagle", "lightroom", "google_drive"
        status_code: Optional[int] = None,
        operation: Optional[str] = None,  # "query", "create", "update", "delete"
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message, details)
        self.service = service
        self.status_code = status_code
        self.operation = operation

    def __str__(self) -> str:
        parts = [self.message]
        if self.service:
            parts.append(f"Service: {self.service}")
        if self.operation:
            parts.append(f"Operation: {self.operation}")
        if self.status_code:
            parts.append(f"Status: {self.status_code}")
        return " | ".join(parts)


class ConfigurationError(ImageWorkflowError):
    """Error in workflow configuration."""

    def __init__(
        self,
        message: str,
        config_key: Optional[str] = None,
        expected_type: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message, details)
        self.config_key = config_key
        self.expected_type = expected_type


class ValidationError(ImageWorkflowError):
    """Error validating input data."""

    def __init__(
        self,
        message: str,
        field: Optional[str] = None,
        value: Optional[Any] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message, details)
        self.field = field
        self.value = value

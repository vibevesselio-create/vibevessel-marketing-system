"""
Local LLM Request/Response Models
=================================

Data models for API requests and responses.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union


class Role(Enum):
    """Message roles for chat completion."""
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


@dataclass
class Message:
    """A single message in a conversation."""
    role: Role
    content: str
    name: Optional[str] = None
    images: Optional[List[str]] = None  # Base64 encoded images for vision

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for API calls."""
        d = {"role": self.role.value, "content": self.content}
        if self.name:
            d["name"] = self.name
        if self.images:
            d["images"] = self.images
        return d


@dataclass
class CompletionRequest:
    """Request for text completion."""
    prompt: Optional[str] = None
    messages: Optional[List[Message]] = None
    model: Optional[str] = None  # Model ID, uses default if not specified
    max_tokens: int = 1024
    temperature: float = 0.7
    top_p: float = 0.9
    stop: Optional[List[str]] = None
    stream: bool = False
    # Vision-specific
    images: Optional[List[str]] = None  # Base64 encoded images
    # Safety check
    check_safety: bool = True

    def __post_init__(self):
        if not self.prompt and not self.messages:
            raise ValueError("Either prompt or messages must be provided")


@dataclass
class CompletionResponse:
    """Response from text completion."""
    content: str
    model: str
    finish_reason: str = "stop"
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    latency_ms: float = 0.0
    safety_flagged: bool = False
    safety_categories: Optional[List[str]] = None
    timestamp: datetime = field(default_factory=datetime.now)

    @property
    def total_tokens_computed(self) -> int:
        """Compute total tokens if not set."""
        return self.total_tokens or (self.prompt_tokens + self.completion_tokens)


@dataclass
class EmbeddingRequest:
    """Request for text embeddings."""
    texts: List[str]
    model: Optional[str] = None  # Model ID, uses default if not specified
    normalize: bool = True


@dataclass
class EmbeddingResponse:
    """Response from embedding generation."""
    embeddings: List[List[float]]
    model: str
    dimensions: int = 0
    latency_ms: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class RerankRequest:
    """Request for document reranking."""
    query: str
    documents: List[str]
    model: Optional[str] = None
    top_k: int = 10


@dataclass
class RerankResult:
    """A single reranked document."""
    document: str
    score: float
    index: int


@dataclass
class RerankResponse:
    """Response from reranking."""
    results: List[RerankResult]
    model: str
    latency_ms: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class TranscriptionRequest:
    """Request for audio transcription."""
    audio_path: str
    model: Optional[str] = None  # Whisper model variant
    language: Optional[str] = None  # Auto-detect if not specified
    translate: bool = False  # Translate to English


@dataclass
class TranscriptionSegment:
    """A segment of transcribed audio."""
    text: str
    start: float  # Start time in seconds
    end: float    # End time in seconds
    confidence: float = 1.0


@dataclass
class TranscriptionResponse:
    """Response from audio transcription."""
    text: str
    segments: List[TranscriptionSegment]
    language: str
    model: str
    duration_seconds: float = 0.0
    latency_ms: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class OCRRequest:
    """Request for OCR/document analysis."""
    image_path: Optional[str] = None
    image_base64: Optional[str] = None
    model: Optional[str] = None
    task: str = "ocr"  # ocr, caption, region_caption, etc.

    def __post_init__(self):
        if not self.image_path and not self.image_base64:
            raise ValueError("Either image_path or image_base64 must be provided")


@dataclass
class OCRResponse:
    """Response from OCR/document analysis."""
    text: str
    model: str
    task: str
    bounding_boxes: Optional[List[Dict[str, Any]]] = None
    latency_ms: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class SafetyCheckRequest:
    """Request for content safety check."""
    content: str
    model: Optional[str] = None


@dataclass
class SafetyCheckResponse:
    """Response from content safety check."""
    is_safe: bool
    categories: List[str]  # Flagged categories if not safe
    confidence: float = 1.0
    model: str = ""
    latency_ms: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)


# Type aliases for convenience
CompletionInput = Union[str, List[Message], CompletionRequest]
EmbeddingInput = Union[str, List[str], EmbeddingRequest]

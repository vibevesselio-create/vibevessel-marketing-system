"""
Local LLM Configuration
=======================

Centralized configuration for the Local LLM Gateway.
Manages model specifications, paths, and 16GB memory guardrails.
"""

import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


class ModelType(Enum):
    """Types of models supported by the gateway."""
    TEXT = "text"           # llama.cpp text generation
    VISION = "vision"       # Vision-language models (Qwen-VL)
    OCR = "ocr"             # Document OCR (Florence-2)
    WHISPER = "whisper"     # Audio transcription
    EMBEDDING = "embedding" # Text embeddings (BGE-M3)
    RERANKER = "reranker"   # Reranking (bge-reranker)
    SAFETY = "safety"       # Content safety (Llama Guard)


class QuantLevel(Enum):
    """Quantization levels for GGUF models."""
    F16 = "f16"       # Full precision (not recommended for 16GB)
    Q8_0 = "q8_0"     # 8-bit
    Q6_K = "q6_k"     # 6-bit k-quant
    Q5_K_M = "q5_k_m" # 5-bit k-quant medium
    Q4_K_M = "q4_k_m" # 4-bit k-quant medium (recommended for 16GB)
    Q4_0 = "q4_0"     # 4-bit
    Q3_K_M = "q3_k_m" # 3-bit k-quant medium
    Q2_K = "q2_k"     # 2-bit k-quant (quality tradeoff)


@dataclass
class ModelSpec:
    """Specification for a local model."""
    model_id: str                           # Unique identifier
    model_type: ModelType                   # Type of model
    display_name: str                       # Human-readable name
    file_path: Optional[Path] = None        # Path to model file
    hf_repo: Optional[str] = None           # Hugging Face repo ID
    quant_level: Optional[QuantLevel] = None # Quantization (for GGUF)
    context_length: int = 4096              # Max context length
    memory_gb: float = 4.0                  # Estimated memory usage
    license: str = "unknown"                # License type
    sha256: Optional[str] = None            # File checksum
    is_default: bool = False                # Default for this type
    extra: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.file_path and isinstance(self.file_path, str):
            self.file_path = Path(self.file_path)


# Default model specifications for 16GB M2 Pro
DEFAULT_MODELS: Dict[str, ModelSpec] = {
    # Text generation (primary)
    "phi-4-mini-q4": ModelSpec(
        model_id="phi-4-mini-q4",
        model_type=ModelType.TEXT,
        display_name="Phi-4 Mini (Q4_K_M)",
        hf_repo="microsoft/Phi-4-mini-instruct-gguf",
        quant_level=QuantLevel.Q4_K_M,
        context_length=8192,
        memory_gb=4.5,
        license="MIT",
        is_default=True,
    ),
    "gemma-2-9b-q4": ModelSpec(
        model_id="gemma-2-9b-q4",
        model_type=ModelType.TEXT,
        display_name="Gemma 2 9B (Q4_K_M)",
        hf_repo="google/gemma-2-9b-it-GGUF",
        quant_level=QuantLevel.Q4_K_M,
        context_length=8192,
        memory_gb=6.0,
        license="Gemma",
    ),
    # Vision/OCR
    "florence-2-large": ModelSpec(
        model_id="florence-2-large",
        model_type=ModelType.OCR,
        display_name="Florence-2 Large",
        hf_repo="microsoft/Florence-2-large",
        context_length=2048,
        memory_gb=3.0,
        license="MIT",
        is_default=True,
    ),
    # Whisper
    "whisper-medium": ModelSpec(
        model_id="whisper-medium",
        model_type=ModelType.WHISPER,
        display_name="Whisper Medium",
        hf_repo="ggerganov/whisper.cpp",
        memory_gb=1.5,
        license="MIT",
        is_default=True,
    ),
    # Embeddings
    "bge-m3": ModelSpec(
        model_id="bge-m3",
        model_type=ModelType.EMBEDDING,
        display_name="BGE-M3 Embeddings",
        hf_repo="BAAI/bge-m3",
        context_length=8192,
        memory_gb=2.0,
        license="MIT",
        is_default=True,
    ),
    # Reranker
    "bge-reranker-v2-m3": ModelSpec(
        model_id="bge-reranker-v2-m3",
        model_type=ModelType.RERANKER,
        display_name="BGE Reranker v2 M3",
        hf_repo="BAAI/bge-reranker-v2-m3",
        memory_gb=1.5,
        license="MIT",
        is_default=True,
    ),
    # Safety
    "llama-guard-3-1b": ModelSpec(
        model_id="llama-guard-3-1b",
        model_type=ModelType.SAFETY,
        display_name="Llama Guard 3 1B",
        hf_repo="meta-llama/Llama-Guard-3-1B-GGUF",
        quant_level=QuantLevel.Q4_K_M,
        memory_gb=1.0,
        license="Llama 3.1",
        is_default=True,
    ),
}


@dataclass
class LLMConfig:
    """Configuration for the Local LLM Gateway."""

    # Storage paths
    model_root: Path = field(default_factory=lambda: Path(
        os.getenv("SEREN_LLM_ROOT",
                  str(Path.home() / "Library/Application Support/SerenLocalLLM/models"))
    ))
    archive_root: Path = field(default_factory=lambda: Path(
        os.getenv("SEREN_LLM_ARCHIVE_ROOT",
                  "/Volumes/SYSTEM_SSD/SerenLocalLLM/models-archive")
    ))

    # Memory constraints (16GB unified memory)
    max_memory_gb: float = 12.0  # Reserve 4GB for system
    max_concurrent_models: int = 1  # Single model at a time for safety

    # Server settings
    llama_server_port: int = 8080
    llama_server_host: str = "127.0.0.1"

    # Logging
    log_dir: Path = field(default_factory=lambda: Path(
        os.getenv("SEREN_LLM_ROOT",
                  str(Path.home() / "Library/Application Support/SerenLocalLLM/models"))
    ) / "logs")

    # Model registry
    models: Dict[str, ModelSpec] = field(default_factory=lambda: DEFAULT_MODELS.copy())

    def __post_init__(self):
        # Ensure paths are Path objects
        if isinstance(self.model_root, str):
            self.model_root = Path(self.model_root)
        if isinstance(self.archive_root, str):
            self.archive_root = Path(self.archive_root)
        if isinstance(self.log_dir, str):
            self.log_dir = Path(self.log_dir)

    @property
    def gguf_dir(self) -> Path:
        """Directory for GGUF model files."""
        return self.model_root / "gguf"

    @property
    def whisper_dir(self) -> Path:
        """Directory for Whisper model files."""
        return self.model_root / "whisper"

    @property
    def hf_dir(self) -> Path:
        """Directory for Hugging Face cache."""
        return self.model_root / "hf"

    @property
    def indexes_dir(self) -> Path:
        """Directory for vector indexes."""
        return self.model_root / "indexes"

    @property
    def registry_dir(self) -> Path:
        """Directory for model registry."""
        return self.model_root / "registry"

    def get_model(self, model_id: str) -> Optional[ModelSpec]:
        """Get a model specification by ID."""
        return self.models.get(model_id)

    def get_default_model(self, model_type: ModelType) -> Optional[ModelSpec]:
        """Get the default model for a given type."""
        for model in self.models.values():
            if model.model_type == model_type and model.is_default:
                return model
        return None

    def list_models(self, model_type: Optional[ModelType] = None) -> List[ModelSpec]:
        """List all models, optionally filtered by type."""
        models = list(self.models.values())
        if model_type:
            models = [m for m in models if m.model_type == model_type]
        return models

    def can_load_model(self, model: ModelSpec) -> bool:
        """Check if a model can be loaded given memory constraints."""
        return model.memory_gb <= self.max_memory_gb

    def ensure_directories(self) -> None:
        """Create all required directories if they don't exist."""
        for path in [
            self.model_root,
            self.gguf_dir,
            self.whisper_dir,
            self.hf_dir,
            self.indexes_dir,
            self.registry_dir,
            self.log_dir,
        ]:
            path.mkdir(parents=True, exist_ok=True)

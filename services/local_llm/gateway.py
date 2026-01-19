"""
Local LLM Gateway
=================

Main gateway class for routing requests to local LLM backends.
Enforces 16GB memory guardrails and provides consistent API.
"""

import asyncio
import logging
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from services.local_llm.config import LLMConfig, ModelSpec, ModelType
from services.local_llm.models import (
    CompletionRequest,
    CompletionResponse,
    EmbeddingRequest,
    EmbeddingResponse,
    Message,
    OCRRequest,
    OCRResponse,
    RerankRequest,
    RerankResponse,
    RerankResult,
    Role,
    SafetyCheckRequest,
    SafetyCheckResponse,
    TranscriptionRequest,
    TranscriptionResponse,
)

logger = logging.getLogger(__name__)


@dataclass
class LoadedModel:
    """Tracks a currently loaded model."""
    spec: ModelSpec
    process: Optional[subprocess.Popen] = None
    loaded_at: float = 0.0
    last_used: float = 0.0


class LocalLLMGateway:
    """
    Gateway for local LLM inference.

    Features:
    - Single-model-at-a-time enforcement (16GB guardrails)
    - Automatic model loading/unloading
    - Consistent API across model types
    - Safety checks before output

    Usage:
        gateway = LocalLLMGateway()

        # Text completion
        response = await gateway.complete("Summarize this text...")

        # Chat completion
        response = await gateway.chat([
            Message(Role.SYSTEM, "You are a helpful assistant."),
            Message(Role.USER, "Hello!"),
        ])

        # Embeddings
        embeddings = await gateway.embed(["text1", "text2"])

        # Transcription
        transcript = await gateway.transcribe("/path/to/audio.mp3")

        # OCR
        text = await gateway.ocr("/path/to/document.png")
    """

    def __init__(self, config: Optional[LLMConfig] = None):
        self.config = config or LLMConfig()
        self._loaded_model: Optional[LoadedModel] = None
        self._lock = asyncio.Lock()
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize the gateway and create required directories."""
        if self._initialized:
            return

        self.config.ensure_directories()
        logger.info(
            f"LocalLLMGateway initialized. Model root: {self.config.model_root}"
        )
        self._initialized = True

    async def shutdown(self) -> None:
        """Shutdown the gateway and unload any loaded models."""
        await self._unload_current_model()
        logger.info("LocalLLMGateway shutdown complete")

    # =========================================================================
    # Text Completion
    # =========================================================================

    async def complete(
        self,
        prompt: str,
        model: Optional[str] = None,
        max_tokens: int = 1024,
        temperature: float = 0.7,
        check_safety: bool = True,
        **kwargs,
    ) -> CompletionResponse:
        """
        Generate text completion from a prompt.

        Args:
            prompt: The input prompt
            model: Model ID (uses default text model if not specified)
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            check_safety: Run safety check on output
            **kwargs: Additional generation parameters

        Returns:
            CompletionResponse with generated text
        """
        request = CompletionRequest(
            prompt=prompt,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            check_safety=check_safety,
            **kwargs,
        )
        return await self._complete_internal(request)

    async def chat(
        self,
        messages: List[Message],
        model: Optional[str] = None,
        max_tokens: int = 1024,
        temperature: float = 0.7,
        check_safety: bool = True,
        **kwargs,
    ) -> CompletionResponse:
        """
        Generate chat completion from messages.

        Args:
            messages: List of conversation messages
            model: Model ID (uses default text model if not specified)
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            check_safety: Run safety check on output
            **kwargs: Additional generation parameters

        Returns:
            CompletionResponse with generated text
        """
        request = CompletionRequest(
            messages=messages,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            check_safety=check_safety,
            **kwargs,
        )
        return await self._complete_internal(request)

    async def _complete_internal(
        self, request: CompletionRequest
    ) -> CompletionResponse:
        """Internal completion implementation."""
        await self.initialize()
        start_time = time.time()

        # Resolve model
        model_id = request.model
        if not model_id:
            default_model = self.config.get_default_model(ModelType.TEXT)
            if not default_model:
                raise ValueError("No default text model configured")
            model_id = default_model.model_id

        model_spec = self.config.get_model(model_id)
        if not model_spec:
            raise ValueError(f"Unknown model: {model_id}")

        # Ensure model is loaded
        await self._ensure_model_loaded(model_spec)

        # TODO: Actually call llama-server API
        # For now, return a placeholder indicating the model would be called
        content = f"[PLACEHOLDER] Would call {model_spec.display_name} with prompt"

        latency_ms = (time.time() - start_time) * 1000

        response = CompletionResponse(
            content=content,
            model=model_id,
            finish_reason="stop",
            latency_ms=latency_ms,
        )

        # Safety check if enabled
        if request.check_safety:
            safety_result = await self.check_safety(content)
            response.safety_flagged = not safety_result.is_safe
            response.safety_categories = safety_result.categories

        return response

    # =========================================================================
    # Embeddings
    # =========================================================================

    async def embed(
        self,
        texts: Union[str, List[str]],
        model: Optional[str] = None,
        normalize: bool = True,
    ) -> EmbeddingResponse:
        """
        Generate embeddings for texts.

        Args:
            texts: Single text or list of texts
            model: Model ID (uses default embedding model if not specified)
            normalize: Whether to normalize embeddings

        Returns:
            EmbeddingResponse with embedding vectors
        """
        if isinstance(texts, str):
            texts = [texts]

        request = EmbeddingRequest(texts=texts, model=model, normalize=normalize)
        return await self._embed_internal(request)

    async def _embed_internal(self, request: EmbeddingRequest) -> EmbeddingResponse:
        """Internal embedding implementation."""
        await self.initialize()
        start_time = time.time()

        # Resolve model
        model_id = request.model
        if not model_id:
            default_model = self.config.get_default_model(ModelType.EMBEDDING)
            if not default_model:
                raise ValueError("No default embedding model configured")
            model_id = default_model.model_id

        model_spec = self.config.get_model(model_id)
        if not model_spec:
            raise ValueError(f"Unknown model: {model_id}")

        # TODO: Actually call embedding model
        # For now, return placeholder embeddings
        embeddings = [[0.0] * 1024 for _ in request.texts]

        latency_ms = (time.time() - start_time) * 1000

        return EmbeddingResponse(
            embeddings=embeddings,
            model=model_id,
            dimensions=1024,
            latency_ms=latency_ms,
        )

    # =========================================================================
    # Reranking
    # =========================================================================

    async def rerank(
        self,
        query: str,
        documents: List[str],
        model: Optional[str] = None,
        top_k: int = 10,
    ) -> RerankResponse:
        """
        Rerank documents by relevance to query.

        Args:
            query: The search query
            documents: List of documents to rerank
            model: Model ID (uses default reranker if not specified)
            top_k: Number of top results to return

        Returns:
            RerankResponse with ranked documents
        """
        request = RerankRequest(
            query=query, documents=documents, model=model, top_k=top_k
        )
        return await self._rerank_internal(request)

    async def _rerank_internal(self, request: RerankRequest) -> RerankResponse:
        """Internal reranking implementation."""
        await self.initialize()
        start_time = time.time()

        # Resolve model
        model_id = request.model
        if not model_id:
            default_model = self.config.get_default_model(ModelType.RERANKER)
            if not default_model:
                raise ValueError("No default reranker model configured")
            model_id = default_model.model_id

        # TODO: Actually call reranker
        # For now, return documents in original order with placeholder scores
        results = [
            RerankResult(document=doc, score=1.0 - (i * 0.1), index=i)
            for i, doc in enumerate(request.documents[: request.top_k])
        ]

        latency_ms = (time.time() - start_time) * 1000

        return RerankResponse(
            results=results,
            model=model_id,
            latency_ms=latency_ms,
        )

    # =========================================================================
    # Transcription
    # =========================================================================

    async def transcribe(
        self,
        audio_path: str,
        model: Optional[str] = None,
        language: Optional[str] = None,
        translate: bool = False,
    ) -> TranscriptionResponse:
        """
        Transcribe audio to text.

        Args:
            audio_path: Path to audio file
            model: Model ID (uses default whisper if not specified)
            language: Language code (auto-detect if not specified)
            translate: Whether to translate to English

        Returns:
            TranscriptionResponse with transcribed text
        """
        request = TranscriptionRequest(
            audio_path=audio_path,
            model=model,
            language=language,
            translate=translate,
        )
        return await self._transcribe_internal(request)

    async def _transcribe_internal(
        self, request: TranscriptionRequest
    ) -> TranscriptionResponse:
        """Internal transcription implementation."""
        await self.initialize()
        start_time = time.time()

        # Resolve model
        model_id = request.model
        if not model_id:
            default_model = self.config.get_default_model(ModelType.WHISPER)
            if not default_model:
                raise ValueError("No default whisper model configured")
            model_id = default_model.model_id

        # TODO: Actually call whisper.cpp
        # For now, return placeholder
        text = f"[PLACEHOLDER] Would transcribe {request.audio_path}"

        latency_ms = (time.time() - start_time) * 1000

        return TranscriptionResponse(
            text=text,
            segments=[],
            language=request.language or "en",
            model=model_id,
            latency_ms=latency_ms,
        )

    # =========================================================================
    # OCR
    # =========================================================================

    async def ocr(
        self,
        image_path: Optional[str] = None,
        image_base64: Optional[str] = None,
        model: Optional[str] = None,
        task: str = "ocr",
    ) -> OCRResponse:
        """
        Perform OCR on an image.

        Args:
            image_path: Path to image file
            image_base64: Base64-encoded image
            model: Model ID (uses default OCR model if not specified)
            task: Task type (ocr, caption, etc.)

        Returns:
            OCRResponse with extracted text
        """
        request = OCRRequest(
            image_path=image_path,
            image_base64=image_base64,
            model=model,
            task=task,
        )
        return await self._ocr_internal(request)

    async def _ocr_internal(self, request: OCRRequest) -> OCRResponse:
        """Internal OCR implementation."""
        await self.initialize()
        start_time = time.time()

        # Resolve model
        model_id = request.model
        if not model_id:
            default_model = self.config.get_default_model(ModelType.OCR)
            if not default_model:
                raise ValueError("No default OCR model configured")
            model_id = default_model.model_id

        # TODO: Actually call Florence-2
        # For now, return placeholder
        text = f"[PLACEHOLDER] Would OCR {request.image_path or 'base64 image'}"

        latency_ms = (time.time() - start_time) * 1000

        return OCRResponse(
            text=text,
            model=model_id,
            task=request.task,
            latency_ms=latency_ms,
        )

    # =========================================================================
    # Safety
    # =========================================================================

    async def check_safety(
        self,
        content: str,
        model: Optional[str] = None,
    ) -> SafetyCheckResponse:
        """
        Check content for safety issues.

        Args:
            content: Text content to check
            model: Model ID (uses default safety model if not specified)

        Returns:
            SafetyCheckResponse with safety status
        """
        request = SafetyCheckRequest(content=content, model=model)
        return await self._check_safety_internal(request)

    async def _check_safety_internal(
        self, request: SafetyCheckRequest
    ) -> SafetyCheckResponse:
        """Internal safety check implementation."""
        await self.initialize()
        start_time = time.time()

        # Resolve model
        model_id = request.model
        if not model_id:
            default_model = self.config.get_default_model(ModelType.SAFETY)
            if default_model:
                model_id = default_model.model_id
            else:
                # No safety model configured, assume safe
                return SafetyCheckResponse(
                    is_safe=True,
                    categories=[],
                    model="none",
                    latency_ms=0,
                )

        # TODO: Actually call Llama Guard
        # For now, assume safe
        latency_ms = (time.time() - start_time) * 1000

        return SafetyCheckResponse(
            is_safe=True,
            categories=[],
            model=model_id,
            latency_ms=latency_ms,
        )

    # =========================================================================
    # Model Management
    # =========================================================================

    async def _ensure_model_loaded(self, model_spec: ModelSpec) -> None:
        """Ensure a model is loaded, unloading current if necessary."""
        async with self._lock:
            # Check if already loaded
            if (
                self._loaded_model
                and self._loaded_model.spec.model_id == model_spec.model_id
            ):
                self._loaded_model.last_used = time.time()
                return

            # Check memory constraints
            if not self.config.can_load_model(model_spec):
                raise MemoryError(
                    f"Model {model_spec.model_id} requires {model_spec.memory_gb}GB, "
                    f"but max is {self.config.max_memory_gb}GB"
                )

            # Unload current model
            await self._unload_current_model()

            # Load new model
            await self._load_model(model_spec)

    async def _load_model(self, model_spec: ModelSpec) -> None:
        """Load a model into memory."""
        logger.info(f"Loading model: {model_spec.display_name}")

        # TODO: Implement actual model loading based on type
        # - TEXT: Start llama-server with the model
        # - WHISPER: No persistent process needed
        # - EMBEDDING/RERANKER: Load Transformers model
        # - OCR: Load Florence-2
        # - SAFETY: Load Llama Guard

        self._loaded_model = LoadedModel(
            spec=model_spec,
            loaded_at=time.time(),
            last_used=time.time(),
        )

        logger.info(f"Model loaded: {model_spec.display_name}")

    async def _unload_current_model(self) -> None:
        """Unload the currently loaded model."""
        if not self._loaded_model:
            return

        logger.info(f"Unloading model: {self._loaded_model.spec.display_name}")

        # Kill process if running
        if self._loaded_model.process:
            self._loaded_model.process.terminate()
            try:
                self._loaded_model.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._loaded_model.process.kill()

        self._loaded_model = None
        logger.info("Model unloaded")

    def get_loaded_model(self) -> Optional[ModelSpec]:
        """Get the currently loaded model spec."""
        if self._loaded_model:
            return self._loaded_model.spec
        return None

    def list_available_models(self) -> List[ModelSpec]:
        """List all configured models."""
        return list(self.config.models.values())

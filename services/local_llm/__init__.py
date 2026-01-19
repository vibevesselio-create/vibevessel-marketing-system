"""
Local LLM Gateway Service
=========================

A lightweight gateway service for routing requests to local LLM backends.
Designed for M2 Pro 16GB unified memory constraints.

Key Features:
- Single-model-at-a-time enforcement (16GB guardrails)
- Consistent API for text, vision, OCR, transcription, and RAG
- Centralized prompt templates and output schemas
- OpenAI-compatible-ish interface for internal use

Backends:
- llama.cpp (llama-server) for GGUF text models
- whisper.cpp for transcription
- Transformers for Florence-2, embeddings, reranker

Usage:
    from services.local_llm import LocalLLMGateway

    gateway = LocalLLMGateway()
    response = await gateway.complete("Summarize this text...")

Version: 2026-01-19
"""

from services.local_llm.gateway import LocalLLMGateway
from services.local_llm.config import LLMConfig, ModelSpec
from services.local_llm.models import (
    CompletionRequest,
    CompletionResponse,
    EmbeddingRequest,
    EmbeddingResponse,
)

__all__ = [
    "LocalLLMGateway",
    "LLMConfig",
    "ModelSpec",
    "CompletionRequest",
    "CompletionResponse",
    "EmbeddingRequest",
    "EmbeddingResponse",
]

__version__ = "0.1.0"

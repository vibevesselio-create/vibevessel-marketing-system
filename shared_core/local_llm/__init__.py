"""
Shared Core Local LLM Client
============================

Lightweight client for accessing the Local LLM Gateway from anywhere
in the codebase. Provides synchronous wrappers for common operations.

Usage:
    from shared_core.local_llm import complete, embed, transcribe

    # Simple text completion
    result = complete("Summarize this text...")

    # Embeddings
    vectors = embed(["text1", "text2"])

    # Transcription
    transcript = transcribe("/path/to/audio.mp3")

For async usage:
    from shared_core.local_llm import get_gateway

    gateway = get_gateway()
    response = await gateway.complete("...")
"""

import asyncio
from typing import List, Optional, Union

# Lazy import to avoid circular dependencies
_gateway_instance = None


def get_gateway():
    """Get or create the singleton gateway instance."""
    global _gateway_instance
    if _gateway_instance is None:
        from services.local_llm import LocalLLMGateway
        _gateway_instance = LocalLLMGateway()
    return _gateway_instance


def _run_async(coro):
    """Run an async coroutine synchronously."""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    if loop.is_running():
        # If we're already in an async context, can't use run_until_complete
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(asyncio.run, coro)
            return future.result()
    else:
        return loop.run_until_complete(coro)


def complete(
    prompt: str,
    model: Optional[str] = None,
    max_tokens: int = 1024,
    temperature: float = 0.7,
    check_safety: bool = True,
) -> str:
    """
    Generate text completion synchronously.

    Args:
        prompt: The input prompt
        model: Model ID (uses default if not specified)
        max_tokens: Maximum tokens to generate
        temperature: Sampling temperature
        check_safety: Run safety check on output

    Returns:
        Generated text string
    """
    gateway = get_gateway()
    response = _run_async(
        gateway.complete(
            prompt=prompt,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            check_safety=check_safety,
        )
    )
    return response.content


def embed(
    texts: Union[str, List[str]],
    model: Optional[str] = None,
    normalize: bool = True,
) -> List[List[float]]:
    """
    Generate embeddings synchronously.

    Args:
        texts: Single text or list of texts
        model: Model ID (uses default if not specified)
        normalize: Whether to normalize embeddings

    Returns:
        List of embedding vectors
    """
    gateway = get_gateway()
    response = _run_async(
        gateway.embed(texts=texts, model=model, normalize=normalize)
    )
    return response.embeddings


def rerank(
    query: str,
    documents: List[str],
    model: Optional[str] = None,
    top_k: int = 10,
) -> List[dict]:
    """
    Rerank documents by relevance synchronously.

    Args:
        query: The search query
        documents: List of documents to rerank
        model: Model ID (uses default if not specified)
        top_k: Number of top results to return

    Returns:
        List of dicts with 'document', 'score', and 'index' keys
    """
    gateway = get_gateway()
    response = _run_async(
        gateway.rerank(query=query, documents=documents, model=model, top_k=top_k)
    )
    return [
        {"document": r.document, "score": r.score, "index": r.index}
        for r in response.results
    ]


def transcribe(
    audio_path: str,
    model: Optional[str] = None,
    language: Optional[str] = None,
    translate: bool = False,
) -> str:
    """
    Transcribe audio to text synchronously.

    Args:
        audio_path: Path to audio file
        model: Model ID (uses default if not specified)
        language: Language code (auto-detect if not specified)
        translate: Whether to translate to English

    Returns:
        Transcribed text string
    """
    gateway = get_gateway()
    response = _run_async(
        gateway.transcribe(
            audio_path=audio_path,
            model=model,
            language=language,
            translate=translate,
        )
    )
    return response.text


def ocr(
    image_path: Optional[str] = None,
    image_base64: Optional[str] = None,
    model: Optional[str] = None,
    task: str = "ocr",
) -> str:
    """
    Perform OCR on an image synchronously.

    Args:
        image_path: Path to image file
        image_base64: Base64-encoded image
        model: Model ID (uses default if not specified)
        task: Task type (ocr, caption, etc.)

    Returns:
        Extracted text string
    """
    gateway = get_gateway()
    response = _run_async(
        gateway.ocr(
            image_path=image_path,
            image_base64=image_base64,
            model=model,
            task=task,
        )
    )
    return response.text


def check_safety(content: str, model: Optional[str] = None) -> bool:
    """
    Check content for safety issues synchronously.

    Args:
        content: Text content to check
        model: Model ID (uses default if not specified)

    Returns:
        True if content is safe, False otherwise
    """
    gateway = get_gateway()
    response = _run_async(
        gateway.check_safety(content=content, model=model)
    )
    return response.is_safe


__all__ = [
    "get_gateway",
    "complete",
    "embed",
    "rerank",
    "transcribe",
    "ocr",
    "check_safety",
]

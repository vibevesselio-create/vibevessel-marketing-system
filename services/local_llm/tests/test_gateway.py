"""Tests for Local LLM Gateway."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from services.local_llm.gateway import LocalLLMGateway, LoadedModel
from services.local_llm.config import LLMConfig, ModelSpec, ModelType
from services.local_llm.models import (
    CompletionRequest,
    CompletionResponse,
    EmbeddingResponse,
    Message,
    Role,
)


class TestLocalLLMGateway:
    """Tests for LocalLLMGateway class."""

    @pytest.fixture
    def gateway(self):
        """Create a gateway instance for testing."""
        return LocalLLMGateway()

    @pytest.fixture
    def config(self):
        """Create a test config."""
        return LLMConfig()

    @pytest.mark.asyncio
    async def test_initialization(self, gateway):
        """Test gateway initialization."""
        assert gateway._initialized is False
        await gateway.initialize()
        assert gateway._initialized is True

    @pytest.mark.asyncio
    async def test_double_initialization(self, gateway):
        """Test that double initialization is safe."""
        await gateway.initialize()
        await gateway.initialize()  # Should not raise

    @pytest.mark.asyncio
    async def test_shutdown(self, gateway):
        """Test gateway shutdown."""
        await gateway.initialize()
        await gateway.shutdown()
        assert gateway._loaded_model is None

    def test_list_available_models(self, gateway):
        """Test listing available models."""
        models = gateway.list_available_models()
        assert len(models) > 0
        assert all(isinstance(m, ModelSpec) for m in models)

    def test_get_loaded_model_none(self, gateway):
        """Test getting loaded model when none is loaded."""
        assert gateway.get_loaded_model() is None


class TestCompletionAPI:
    """Tests for completion API."""

    @pytest.fixture
    def gateway(self):
        """Create a gateway instance for testing."""
        return LocalLLMGateway()

    @pytest.mark.asyncio
    async def test_complete_basic(self, gateway):
        """Test basic text completion."""
        response = await gateway.complete("Hello, world!")
        assert isinstance(response, CompletionResponse)
        assert response.model is not None
        assert response.latency_ms >= 0

    @pytest.mark.asyncio
    async def test_complete_with_params(self, gateway):
        """Test completion with custom parameters."""
        response = await gateway.complete(
            prompt="Test prompt",
            max_tokens=512,
            temperature=0.5,
            check_safety=False,
        )
        assert isinstance(response, CompletionResponse)

    @pytest.mark.asyncio
    async def test_chat_completion(self, gateway):
        """Test chat completion with messages."""
        messages = [
            Message(Role.SYSTEM, "You are a helpful assistant."),
            Message(Role.USER, "Hello!"),
        ]
        response = await gateway.chat(messages)
        assert isinstance(response, CompletionResponse)


class TestEmbeddingAPI:
    """Tests for embedding API."""

    @pytest.fixture
    def gateway(self):
        """Create a gateway instance for testing."""
        return LocalLLMGateway()

    @pytest.mark.asyncio
    async def test_embed_single(self, gateway):
        """Test embedding a single text."""
        response = await gateway.embed("Hello, world!")
        assert isinstance(response, EmbeddingResponse)
        assert len(response.embeddings) == 1

    @pytest.mark.asyncio
    async def test_embed_multiple(self, gateway):
        """Test embedding multiple texts."""
        texts = ["Hello", "World", "Test"]
        response = await gateway.embed(texts)
        assert len(response.embeddings) == 3


class TestModelManagement:
    """Tests for model loading/unloading."""

    @pytest.fixture
    def gateway(self):
        """Create a gateway instance for testing."""
        return LocalLLMGateway()

    @pytest.mark.asyncio
    async def test_model_loading_sets_loaded_model(self, gateway):
        """Test that completing a request loads a model."""
        await gateway.complete("Test")
        # After completion, a model should be "loaded"
        # (In placeholder mode, this just sets _loaded_model)

    @pytest.mark.asyncio
    async def test_memory_check(self, gateway):
        """Test that memory constraints are checked."""
        # Add a model that exceeds memory
        huge_model = ModelSpec(
            model_id="huge-model",
            model_type=ModelType.TEXT,
            display_name="Huge Model",
            memory_gb=100.0,  # Way over 12GB limit
            is_default=False,
        )
        gateway.config.models["huge-model"] = huge_model

        with pytest.raises(MemoryError):
            await gateway._ensure_model_loaded(huge_model)


class TestSafetyChecks:
    """Tests for safety checking."""

    @pytest.fixture
    def gateway(self):
        """Create a gateway instance for testing."""
        return LocalLLMGateway()

    @pytest.mark.asyncio
    async def test_check_safety(self, gateway):
        """Test safety check API."""
        response = await gateway.check_safety("Hello, this is a test.")
        assert response.is_safe is True
        assert isinstance(response.categories, list)

    @pytest.mark.asyncio
    async def test_complete_with_safety(self, gateway):
        """Test that completion runs safety check when enabled."""
        response = await gateway.complete("Test", check_safety=True)
        # Safety check was run
        assert response.safety_flagged is not None


class TestTranscriptionAPI:
    """Tests for transcription API."""

    @pytest.fixture
    def gateway(self):
        """Create a gateway instance for testing."""
        return LocalLLMGateway()

    @pytest.mark.asyncio
    async def test_transcribe(self, gateway):
        """Test transcription API."""
        response = await gateway.transcribe("/path/to/audio.mp3")
        assert response.text is not None
        assert response.model is not None


class TestOCRAPI:
    """Tests for OCR API."""

    @pytest.fixture
    def gateway(self):
        """Create a gateway instance for testing."""
        return LocalLLMGateway()

    @pytest.mark.asyncio
    async def test_ocr_with_path(self, gateway):
        """Test OCR with image path."""
        response = await gateway.ocr(image_path="/path/to/image.png")
        assert response.text is not None
        assert response.task == "ocr"

    @pytest.mark.asyncio
    async def test_ocr_with_base64(self, gateway):
        """Test OCR with base64 image."""
        response = await gateway.ocr(image_base64="base64encodeddata")
        assert response.text is not None

    @pytest.mark.asyncio
    async def test_ocr_requires_image(self, gateway):
        """Test that OCR requires either path or base64."""
        with pytest.raises(ValueError):
            await gateway.ocr()  # No image provided


class TestRerankAPI:
    """Tests for reranking API."""

    @pytest.fixture
    def gateway(self):
        """Create a gateway instance for testing."""
        return LocalLLMGateway()

    @pytest.mark.asyncio
    async def test_rerank(self, gateway):
        """Test reranking API."""
        documents = ["Doc 1", "Doc 2", "Doc 3"]
        response = await gateway.rerank(query="test query", documents=documents)
        assert len(response.results) <= len(documents)
        assert all(r.score is not None for r in response.results)

    @pytest.mark.asyncio
    async def test_rerank_top_k(self, gateway):
        """Test reranking with top_k limit."""
        documents = ["Doc " + str(i) for i in range(10)]
        response = await gateway.rerank(
            query="test", documents=documents, top_k=3
        )
        assert len(response.results) == 3

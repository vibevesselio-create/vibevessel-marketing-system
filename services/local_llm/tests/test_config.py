"""Tests for Local LLM configuration."""

import pytest
from pathlib import Path

from services.local_llm.config import (
    LLMConfig,
    ModelSpec,
    ModelType,
    QuantLevel,
    DEFAULT_MODELS,
)


class TestModelSpec:
    """Tests for ModelSpec dataclass."""

    def test_basic_creation(self):
        """Test creating a basic model spec."""
        spec = ModelSpec(
            model_id="test-model",
            model_type=ModelType.TEXT,
            display_name="Test Model",
        )
        assert spec.model_id == "test-model"
        assert spec.model_type == ModelType.TEXT
        assert spec.display_name == "Test Model"
        assert spec.context_length == 4096  # default
        assert spec.memory_gb == 4.0  # default

    def test_with_file_path_string(self):
        """Test that string file paths are converted to Path."""
        spec = ModelSpec(
            model_id="test",
            model_type=ModelType.TEXT,
            display_name="Test",
            file_path="/path/to/model.gguf",
        )
        assert isinstance(spec.file_path, Path)
        assert str(spec.file_path) == "/path/to/model.gguf"

    def test_with_quantization(self):
        """Test model spec with quantization level."""
        spec = ModelSpec(
            model_id="phi-4-q4",
            model_type=ModelType.TEXT,
            display_name="Phi-4 Q4",
            quant_level=QuantLevel.Q4_K_M,
        )
        assert spec.quant_level == QuantLevel.Q4_K_M


class TestLLMConfig:
    """Tests for LLMConfig dataclass."""

    def test_default_config(self):
        """Test default configuration values."""
        config = LLMConfig()
        assert config.max_memory_gb == 12.0
        assert config.max_concurrent_models == 1
        assert config.llama_server_port == 8080
        assert len(config.models) > 0

    def test_directory_paths(self):
        """Test computed directory paths."""
        config = LLMConfig()
        assert config.gguf_dir == config.model_root / "gguf"
        assert config.whisper_dir == config.model_root / "whisper"
        assert config.hf_dir == config.model_root / "hf"
        assert config.indexes_dir == config.model_root / "indexes"
        assert config.registry_dir == config.model_root / "registry"

    def test_get_model(self):
        """Test getting a model by ID."""
        config = LLMConfig()
        model = config.get_model("phi-4-mini-q4")
        assert model is not None
        assert model.model_id == "phi-4-mini-q4"

    def test_get_model_not_found(self):
        """Test getting a nonexistent model."""
        config = LLMConfig()
        model = config.get_model("nonexistent")
        assert model is None

    def test_get_default_model(self):
        """Test getting default model for a type."""
        config = LLMConfig()
        model = config.get_default_model(ModelType.TEXT)
        assert model is not None
        assert model.is_default is True
        assert model.model_type == ModelType.TEXT

    def test_list_models(self):
        """Test listing all models."""
        config = LLMConfig()
        all_models = config.list_models()
        assert len(all_models) > 0

        # Filter by type
        text_models = config.list_models(ModelType.TEXT)
        assert all(m.model_type == ModelType.TEXT for m in text_models)

    def test_can_load_model(self):
        """Test memory constraint checking."""
        config = LLMConfig()
        config.max_memory_gb = 8.0

        small_model = ModelSpec(
            model_id="small",
            model_type=ModelType.TEXT,
            display_name="Small",
            memory_gb=4.0,
        )
        assert config.can_load_model(small_model) is True

        large_model = ModelSpec(
            model_id="large",
            model_type=ModelType.TEXT,
            display_name="Large",
            memory_gb=16.0,
        )
        assert config.can_load_model(large_model) is False


class TestDefaultModels:
    """Tests for default model configurations."""

    def test_default_models_exist(self):
        """Test that default models are configured."""
        assert "phi-4-mini-q4" in DEFAULT_MODELS
        assert "bge-m3" in DEFAULT_MODELS
        assert "whisper-medium" in DEFAULT_MODELS

    def test_default_models_have_required_fields(self):
        """Test that all default models have required fields."""
        for model_id, spec in DEFAULT_MODELS.items():
            assert spec.model_id == model_id
            assert spec.model_type is not None
            assert spec.display_name
            assert spec.memory_gb > 0
            assert spec.license

    def test_each_type_has_default(self):
        """Test that each model type has at least one default."""
        config = LLMConfig()
        for model_type in [
            ModelType.TEXT,
            ModelType.WHISPER,
            ModelType.EMBEDDING,
            ModelType.RERANKER,
            ModelType.OCR,
            ModelType.SAFETY,
        ]:
            default = config.get_default_model(model_type)
            assert default is not None, f"No default for {model_type}"

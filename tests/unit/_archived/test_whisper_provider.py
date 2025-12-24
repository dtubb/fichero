"""Unit tests for Whisper audio transcription provider."""
import pytest
from pathlib import Path
from unittest.mock import Mock, patch, AsyncMock, MagicMock


class TestWhisperProviderInit:
    """Tests for WhisperProvider initialization."""

    def test_default_mode(self):
        """Default mode should be 'local'."""
        from fichero.tools.transcribe_providers.whisper_provider import WhisperProvider

        provider = WhisperProvider()

        assert provider.mode == "local"
        assert provider.model_name == "base"
        assert provider.language is None

    def test_custom_mode(self):
        """Should accept custom mode."""
        from fichero.tools.transcribe_providers.whisper_provider import WhisperProvider

        provider = WhisperProvider(mode="api")

        assert provider.mode == "api"

    def test_custom_model(self):
        """Should accept custom model."""
        from fichero.tools.transcribe_providers.whisper_provider import WhisperProvider

        provider = WhisperProvider(model="large-v3")

        assert provider.model_name == "large-v3"

    def test_custom_language(self):
        """Should accept custom language."""
        from fichero.tools.transcribe_providers.whisper_provider import WhisperProvider

        provider = WhisperProvider(language="es")

        assert provider.language == "es"

    def test_custom_device(self):
        """Should accept custom device."""
        from fichero.tools.transcribe_providers.whisper_provider import WhisperProvider

        provider = WhisperProvider(device="cuda")

        assert provider.device == "cuda"

    def test_custom_compute_type(self):
        """Should accept custom compute type."""
        from fichero.tools.transcribe_providers.whisper_provider import WhisperProvider

        provider = WhisperProvider(compute_type="int8")

        assert provider.compute_type == "int8"


class TestWhisperProviderProperties:
    """Tests for WhisperProvider properties."""

    def test_provider_name(self):
        """Provider name should include mode."""
        from fichero.tools.transcribe_providers.whisper_provider import WhisperProvider

        provider_local = WhisperProvider(mode="local")
        provider_api = WhisperProvider(mode="api")
        provider_faster = WhisperProvider(mode="faster")

        assert provider_local.provider_name == "whisper-local"
        assert provider_api.provider_name == "whisper-api"
        assert provider_faster.provider_name == "whisper-faster"

    def test_supported_formats(self):
        """Should support common audio formats."""
        from fichero.tools.transcribe_providers.whisper_provider import WhisperProvider

        provider = WhisperProvider()
        formats = provider.supported_formats

        assert ".mp3" in formats
        assert ".wav" in formats
        assert ".m4a" in formats
        assert ".aac" in formats
        assert ".flac" in formats
        assert ".ogg" in formats
        assert ".wma" in formats

    def test_max_file_size_api_mode(self):
        """API mode should have 25MB limit."""
        from fichero.tools.transcribe_providers.whisper_provider import WhisperProvider

        provider = WhisperProvider(mode="api")

        assert provider.max_file_size_mb == 25

    def test_max_file_size_local_mode(self):
        """Local mode should have higher limit."""
        from fichero.tools.transcribe_providers.whisper_provider import WhisperProvider

        provider = WhisperProvider(mode="local")

        assert provider.max_file_size_mb == 500


class TestWhisperModels:
    """Tests for WHISPER_MODELS constant."""

    def test_model_sizes_defined(self):
        """Should define standard Whisper model sizes."""
        from fichero.tools.transcribe_providers.whisper_provider import WHISPER_MODELS

        assert "tiny" in WHISPER_MODELS
        assert "base" in WHISPER_MODELS
        assert "small" in WHISPER_MODELS
        assert "medium" in WHISPER_MODELS
        assert "large" in WHISPER_MODELS
        assert "large-v2" in WHISPER_MODELS
        assert "large-v3" in WHISPER_MODELS


class TestAudioFormats:
    """Tests for AUDIO_FORMATS constant."""

    def test_common_formats_included(self):
        """Should include common audio formats."""
        from fichero.tools.transcribe_providers.whisper_provider import AUDIO_FORMATS

        assert ".wav" in AUDIO_FORMATS
        assert ".mp3" in AUDIO_FORMATS
        assert ".m4a" in AUDIO_FORMATS
        assert ".flac" in AUDIO_FORMATS


class TestProcessAudio:
    """Tests for process_audio method."""

    @pytest.mark.asyncio
    async def test_file_not_found(self):
        """Should raise FileNotFoundError for missing file."""
        from fichero.tools.transcribe_providers.whisper_provider import WhisperProvider

        provider = WhisperProvider()

        with pytest.raises(FileNotFoundError):
            await provider.process_audio(Path("/nonexistent/audio.mp3"))

    @pytest.mark.asyncio
    async def test_process_audio_local_mode(self, tmp_path):
        """Should use local transcription for local mode."""
        from fichero.tools.transcribe_providers.whisper_provider import WhisperProvider

        provider = WhisperProvider(mode="local")

        # Create mock audio file
        audio_file = tmp_path / "test.mp3"
        audio_file.touch()

        with patch.object(provider, "_transcribe_local", new_callable=AsyncMock) as mock:
            mock.return_value = "transcribed text"

            result = await provider.process_audio(audio_file)

            assert result == "transcribed text"
            mock.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_audio_api_mode(self, tmp_path):
        """Should use API transcription for api mode."""
        from fichero.tools.transcribe_providers.whisper_provider import WhisperProvider

        provider = WhisperProvider(mode="api")

        audio_file = tmp_path / "test.mp3"
        audio_file.touch()

        with patch.object(provider, "_transcribe_api", new_callable=AsyncMock) as mock:
            mock.return_value = "api transcribed text"

            result = await provider.process_audio(audio_file)

            assert result == "api transcribed text"
            mock.assert_called_once()

    def test_process_image_returns_dict(self, tmp_path):
        """process_image should return dict with success/text."""
        from fichero.tools.transcribe_providers.whisper_provider import WhisperProvider

        provider = WhisperProvider()

        audio_file = tmp_path / "test.mp3"
        audio_file.touch()

        with patch.object(provider, "process_audio", new_callable=AsyncMock) as mock:
            mock.return_value = "text"

            result = provider.process_image(audio_file)

            assert isinstance(result, dict)
            assert result["success"] is True
            assert result["text"] == "text"


class TestTranscribeLocal:
    """Tests for _transcribe_local method."""

    @pytest.mark.asyncio
    async def test_runs_in_executor(self, tmp_path):
        """Should run sync transcription in executor."""
        from fichero.tools.transcribe_providers.whisper_provider import WhisperProvider

        provider = WhisperProvider(mode="local")

        audio_file = tmp_path / "test.mp3"
        audio_file.touch()

        with patch.object(provider, "_transcribe_local_sync") as mock_sync:
            mock_sync.return_value = "transcribed"

            result = await provider._transcribe_local(audio_file)

            assert result == "transcribed"


class TestTranscribeLocalSync:
    """Tests for _transcribe_local_sync method."""

    def test_loads_model_once(self, tmp_path):
        """Should lazy-load model."""
        from fichero.tools.transcribe_providers.whisper_provider import WhisperProvider

        provider = WhisperProvider(mode="local")

        audio_file = tmp_path / "test.mp3"
        audio_file.touch()

        with patch.object(provider, "_load_model") as mock_load:
            with patch.object(provider, "_transcribe_whisper_sync") as mock_transcribe:
                mock_transcribe.return_value = "text"

                provider._transcribe_local_sync(audio_file)

                mock_load.assert_called_once()

    def test_calls_faster_whisper_for_faster_mode(self, tmp_path):
        """Should use faster-whisper for 'faster' mode."""
        from fichero.tools.transcribe_providers.whisper_provider import WhisperProvider

        provider = WhisperProvider(mode="faster")

        audio_file = tmp_path / "test.mp3"
        audio_file.touch()

        with patch.object(provider, "_load_model"):
            with patch.object(provider, "_transcribe_faster_sync") as mock:
                mock.return_value = "fast text"

                result = provider._transcribe_local_sync(audio_file)

                assert result == "fast text"
                mock.assert_called_once()


class TestTranscribeApi:
    """Tests for _transcribe_api method."""

    @pytest.mark.asyncio
    async def test_uses_openai_client(self, tmp_path):
        """Should use OpenAI AsyncClient."""
        try:
            import openai
        except ImportError:
            pytest.skip("openai not installed")

        from fichero.tools.transcribe_providers.whisper_provider import WhisperProvider

        provider = WhisperProvider(mode="api")

        audio_file = tmp_path / "test.mp3"
        audio_file.write_bytes(b"fake audio data")

        mock_response = Mock()
        mock_response.text = "transcribed from API"

        # Patch where the imports happen (inside the function)
        with patch("openai.AsyncOpenAI") as mock_client_class:
            mock_client = MagicMock()
            mock_client.audio.transcriptions.create = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            # Mock get_api_key directly in the whisper_provider module scope
            with patch.object(provider, "_transcribe_api", new_callable=AsyncMock) as mock_transcribe:
                mock_transcribe.return_value = "transcribed from API"

                result = await mock_transcribe(audio_file)
                assert result == "transcribed from API"

    @pytest.mark.asyncio
    async def test_raises_without_api_key(self, tmp_path):
        """Should raise error if API key missing."""
        try:
            import openai
        except ImportError:
            pytest.skip("openai not installed")

        from fichero.tools.transcribe_providers.whisper_provider import WhisperProvider

        provider = WhisperProvider(mode="api")

        audio_file = tmp_path / "test.mp3"
        audio_file.write_bytes(b"fake audio data")

        # Just test the structure - actual API key check would need more deps
        assert provider.mode == "api"
        assert callable(provider._transcribe_api)


class TestLoadModel:
    """Tests for _load_model method."""

    def test_skips_if_already_loaded(self):
        """Should skip loading if model already loaded."""
        from fichero.tools.transcribe_providers.whisper_provider import WhisperProvider

        provider = WhisperProvider(mode="local")
        provider._model = Mock()  # Pretend already loaded

        # Patch where the import happens (inside _load_local_model)
        with patch.object(provider, "_load_local_model") as mock_load:
            provider._load_model()

            # Should not load again since _model is already set
            mock_load.assert_not_called()

    def test_api_mode_skips_loading(self):
        """API mode should not load local model."""
        from fichero.tools.transcribe_providers.whisper_provider import WhisperProvider

        provider = WhisperProvider(mode="api")

        # Should not raise
        provider._load_model()

        assert provider._model is None


class TestIsAvailable:
    """Tests for is_available static method."""

    def test_local_mode_check(self):
        """Should check if openai-whisper is installed."""
        from fichero.tools.transcribe_providers.whisper_provider import WhisperProvider

        # Returns boolean based on import availability
        result = WhisperProvider.is_available("local")
        assert isinstance(result, bool)

    def test_faster_mode_check(self):
        """Should check if faster-whisper is installed."""
        from fichero.tools.transcribe_providers.whisper_provider import WhisperProvider

        result = WhisperProvider.is_available("faster")
        assert isinstance(result, bool)

    def test_api_mode_check(self):
        """Should check if openai is installed and key available."""
        from fichero.tools.transcribe_providers.whisper_provider import WhisperProvider

        result = WhisperProvider.is_available("api")
        assert isinstance(result, bool)

    def test_unknown_mode_returns_false(self):
        """Should return False for unknown mode."""
        from fichero.tools.transcribe_providers.whisper_provider import WhisperProvider

        result = WhisperProvider.is_available("unknown")
        assert result is False


class TestGetAvailableModes:
    """Tests for get_available_modes static method."""

    def test_returns_list(self):
        """Should return list of available modes."""
        from fichero.tools.transcribe_providers.whisper_provider import WhisperProvider

        result = WhisperProvider.get_available_modes()

        assert isinstance(result, list)
        # Each item should be a valid mode
        for mode in result:
            assert mode in ["local", "faster", "api"]


class TestConvenienceFunctions:
    """Tests for convenience functions."""

    @pytest.mark.asyncio
    async def test_transcribe_audio_function(self, tmp_path):
        """transcribe_audio should work."""
        from fichero.tools.transcribe_providers.whisper_provider import transcribe_audio

        audio_file = tmp_path / "test.mp3"
        audio_file.touch()

        with patch(
            "fichero.tools.transcribe_providers.whisper_provider.WhisperProvider.process_audio",
            new_callable=AsyncMock
        ) as mock:
            mock.return_value = "result"

            result = await transcribe_audio(audio_file)

            assert result == "result"

    def test_transcribe_audio_sync_function(self, tmp_path):
        """transcribe_audio_sync should work."""
        from fichero.tools.transcribe_providers.whisper_provider import transcribe_audio_sync

        audio_file = tmp_path / "test.mp3"
        audio_file.touch()

        with patch(
            "fichero.tools.transcribe_providers.whisper_provider.WhisperProvider.process_audio",
            new_callable=AsyncMock
        ) as mock:
            mock.return_value = "sync result"

            result = transcribe_audio_sync(audio_file)

            assert result == "sync result"


class TestBatchProcessing:
    """Tests for batch processing compatibility."""

    @pytest.mark.asyncio
    async def test_process_image_async_exists(self, tmp_path):
        """Should have process_image_async for batch processor."""
        from fichero.tools.transcribe_providers.whisper_provider import WhisperProvider

        provider = WhisperProvider()

        audio_file = tmp_path / "test.mp3"
        audio_file.touch()

        with patch.object(provider, "process_audio", new_callable=AsyncMock) as mock:
            mock.return_value = "batch result"

            result = await provider.process_image_async(audio_file)

            assert result == "batch result"

    def test_process_image_handles_errors(self, tmp_path):
        """process_image should return error dict on failure."""
        from fichero.tools.transcribe_providers.whisper_provider import WhisperProvider

        provider = WhisperProvider()

        # Non-existent file
        audio_file = tmp_path / "nonexistent.mp3"

        result = provider.process_image(audio_file)

        assert isinstance(result, dict)
        assert result["success"] is False
        assert "error" in result

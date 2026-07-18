"""Coverage for shared audio/Whisper helpers."""

from __future__ import annotations

from fichero.workflows.tools import audio_base


class _Model:
    def __init__(self):
        self.calls = []

    def transcribe(self, path, *, language):
        self.calls.append((path, language))
        return {"text": "  hello world  "}


def test_whisper_model_cache_loads_once_and_sync_transcription_normalizes(monkeypatch, tmp_path):
    loaded = []
    model = _Model()

    class Whisper:
        @staticmethod
        def load_model(*args, **kwargs):
            loaded.append((args, kwargs))
            return model

    monkeypatch.setitem(__import__("sys").modules, "whisper", Whisper)
    monkeypatch.setattr(audio_base, "MODELS_BASE", tmp_path)
    audio_base._WHISPER_MODEL_CACHE.clear()

    assert audio_base.transcribe_with_whisper_sync("clip.wav", "tiny", "auto") == "hello world"
    assert audio_base.transcribe_with_whisper_sync("clip.wav", "tiny", "auto") == "hello world"
    assert len(loaded) == 1
    assert loaded[0][0] == ("tiny",)
    assert model.calls == [("clip.wav", None), ("clip.wav", None)]

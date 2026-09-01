"""Which models may be OFFERED, and which must be refused before a run.

Daniel's 2026-09-01 re-test produced two failures with one shape: the catalog
answered a question it could not actually answer, and the UI believed it.

  1. A batch-only model was offered as a regular default; the run died on the
     provider's own 404 ("only available through the Batch API").
  2. A model NEWER than the vendored registry arrived with no capability
     flags, so every vision picker filtered it out — "cannot select a model
     like Opus or Google".
"""

from fichero_server.llm.model_types import (
    infer_vision_support,
    is_batch_only_model,
)


class TestBatchOnlyModels:
    def test_an_id_that_names_itself_a_batch_sku_is_refused(self):
        assert is_batch_only_model("gpt-5-batch")
        assert is_batch_only_model("openai/batch-gpt-5")
        assert is_batch_only_model("some-model:batch")

    def test_ordinary_models_are_not_refused(self):
        # The registry rows that carry batch PRICING are still perfectly
        # callable interactively — pricing is not an endpoint.
        for model in (
            "claude-opus-4-7",
            "gpt-5.5",
            "gemini-3.1-flash-lite",
            "openai/gpt-4o",
        ):
            assert not is_batch_only_model(model), model

    def test_an_unknown_model_is_never_called_batch_only(self):
        # Absence of a registry row is not evidence. Guessing here would hide
        # working models — the exact failure the vision floor exists to undo.
        assert not is_batch_only_model("claude-opus-9-20991231")
        assert not is_batch_only_model("")

    def test_a_row_whose_only_endpoints_are_batch_is_refused(self, monkeypatch):
        import fichero_server.llm.model_types as model_types

        monkeypatch.setattr(
            model_types,
            "_resolve_entry",
            lambda model: {"supported_endpoints": ["/v1/batch"]},
        )
        assert model_types.is_batch_only_model("some/retired-model")

    def test_a_row_listing_an_interactive_endpoint_is_allowed(self, monkeypatch):
        import fichero_server.llm.model_types as model_types

        monkeypatch.setattr(
            model_types,
            "_resolve_entry",
            lambda model: {
                "supported_endpoints": ["/v1/chat/completions", "/v1/batch"]
            },
        )
        assert not model_types.is_batch_only_model("some/live-model")


class TestVisionFloor:
    def test_a_model_newer_than_the_snapshot_still_reads_as_vision_capable(self):
        # The whole point: these ids are NOT in the vendored registry.
        assert infer_vision_support("claude-opus-4-9-20260901")
        assert infer_vision_support("gemini-4.0-pro")
        assert infer_vision_support("gpt-6-turbo")

    def test_known_text_only_siblings_are_not_promoted(self):
        for model in (
            "text-embedding-3-large",
            "gemini-embedding-001",
            "whisper-1",
            "claude-instant-1.2",
            "claude-2.1",
            "gemma-3-27b",
            "text-moderation-latest",
        ):
            assert not infer_vision_support(model), model

    def test_local_vision_families_are_recognised(self):
        assert infer_vision_support("qwen3-vl-8b-instruct")
        assert infer_vision_support("llava:13b")
        assert infer_vision_support("pixtral-12b")

    def test_the_empty_model_is_not_a_vision_claim(self):
        assert not infer_vision_support("")

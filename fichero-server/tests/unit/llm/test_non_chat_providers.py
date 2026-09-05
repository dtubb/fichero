"""A provider that answers no prompts says so (#4671).

Daniel, on the AI-settings redesign: "mlx would be Fichero (MLX) or whatever,
and then choose models, ditto spacy, ditto kraken." spaCy is a real provider
with real models and it belongs in Settings — but it is a part-of-speech
tagger, not a language model, and a model picker for a chat or transcription
step that offers it is offering something there is nothing to pick from.

Every other capability on `ProviderInfo` refines what an LLM can do.
`supports_chat` is the one that says whether the row IS one. It defaults True
so the field adds a way to say no rather than asking twenty providers to
re-declare yes — which is also what makes it safe to add mid-release.
"""

from __future__ import annotations

import pytest

from fichero_server.llm.providers import (
    PROVIDERS,
    ProviderType,
    get_provider_info,
    list_providers,
)


class TestTheFieldIsAdditive:
    def test_every_language_model_provider_still_declares_chat(self):
        # The default is the whole point: adding this field must not have
        # silently demoted anything.
        for info in list_providers():
            if info.type is ProviderType.spacy:
                continue
            assert info.supports_chat, info.type.value

    def test_only_the_nlp_runtime_opts_out(self):
        assert [i.type.value for i in list_providers() if not i.supports_chat] == [
            "spacy"
        ]


class TestTheSpacyRow:
    @pytest.fixture
    def spacy(self):
        return PROVIDERS[ProviderType.spacy]

    def test_it_is_reachable_by_name_like_any_other_provider(self):
        assert get_provider_info("spacy") is PROVIDERS[ProviderType.spacy]

    def test_it_claims_no_capability_it_does_not_have(self, spacy):
        assert spacy.supports_chat is False
        assert spacy.supports_vision is False
        assert spacy.supports_embeddings is False
        assert spacy.supports_streaming is False

    def test_it_is_local_and_ships_with_the_app(self, spacy):
        # Daniel ruled the ~54 MB in (2026-09-04), so the gate works on first
        # launch, offline, with nothing to configure — which is what
        # `is_builtin` means to Settings.
        assert spacy.is_local is True
        assert spacy.is_builtin is True

    def test_the_model_rows_carry_what_the_provider_row_cannot(self):
        # A dev checkout without the `[kg]` extra has no runtime, and a static
        # provider row cannot know that. It does not have to: the MODEL rows
        # ask the runtime. Provider says "no configuration needed"; models say
        # "here is what is actually installed".
        from fichero_server.llm.local_models import LocalModelManager

        rows = LocalModelManager().list_spacy_models()
        assert rows
        assert all(hasattr(r, "available") and hasattr(r, "unavailable_reason") for r in rows)

    def test_it_needs_no_api_key(self, spacy):
        assert spacy.api_key_env is None
        assert spacy.api_key_url is None

    def test_its_default_model_is_the_one_the_gate_loads(self, spacy):
        from fichero_server.llm.local_models import SPACY_MODELS

        assert spacy.default_model in SPACY_MODELS

    def test_its_description_says_what_it_does_not_do(self, spacy):
        # A provider row whose description reads like an LLM's is the defect
        # `supports_chat` exists to prevent, one layer up in the UI.
        assert "no prompts" in spacy.description


class TestItIsNotChatRoutable:
    def test_asking_the_tagger_for_a_completion_fails_loudly(self):
        # Being in the provider catalog must not make it reachable as a chat
        # backend. Better a named failure than a picker that offers it.
        from fichero_server.llm import LLMConfig, get_langchain_model

        with pytest.raises(Exception) as excinfo:
            get_langchain_model(LLMConfig(provider="spacy", model="es_core_news_sm"))
        assert "spacy" in str(excinfo.value).lower()

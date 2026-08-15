"""Tests for the multi-provider NER abstraction."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from fichero_server.knowledge import spacy_ner
from fichero_server.knowledge.ner import ExtractedEntity
from fichero_server.workflows.ner.providers import (
    LLMNERProvider,
    SpacyNERProvider,
    TransformersNERProvider,
    get_ner_provider,
)
from fichero_server.workflows.tools.ner import ner


def test_get_ner_provider_resolves_known_backends():
    assert isinstance(get_ner_provider("spacy"), SpacyNERProvider)
    assert isinstance(get_ner_provider("transformers"), TransformersNERProvider)
    assert isinstance(get_ner_provider("llm"), LLMNERProvider)


def test_spacy_provider_clusters_aliases_and_sets_metadata(monkeypatch):
    provider = SpacyNERProvider(model_name="en_core_web_sm")
    spans = [
        spacy_ner.EntitySpan(
            text="Davidson [Deibinson]",
            fichero_type="person",
            start=0,
            end=20,
            label="PERSON",
        ),
        spacy_ner.EntitySpan(
            text="Davidson",
            fichero_type="person",
            start=30,
            end=38,
            label="PERSON",
        ),
    ]
    monkeypatch.setattr(spacy_ner, "extract_entities", lambda text, language=None: spans)

    records = asyncio.run(provider.extract("Davidson [Deibinson] signed the deed."))
    assert len(records) == 1
    assert records[0].name == "Davidson [Deibinson]"
    assert records[0].type == "person"
    assert records[0].provider_name == "spacy"
    assert records[0].model_name == "en_core_web_sm"
    assert "Davidson" in records[0].aliases


def test_llm_provider_flattens_entity_payload(monkeypatch):
    provider = LLMNERProvider(model_name="gpt-4o-mini")

    async def fake_extract_entities(inputs, state, llm_config):
        return {
            "entities": {
                "people": [
                    {
                        "name": "Leidy",
                        "confidence": 0.8,
                        "start": 3,
                        "end": 8,
                    }
                ],
                "organizations": [],
                "locations": [],
                "dates": [],
            }
        }

    monkeypatch.setattr(
        "fichero_server.workflows.tools.entities.extract_entities",
        fake_extract_entities,
    )

    records = asyncio.run(
        provider.extract(
            "Leidy is a miner.",
            state={},
            llm_config=SimpleNamespace(provider="openai", model="gpt-4o-mini"),
        )
    )
    assert len(records) == 1
    assert records[0].name == "Leidy"
    assert records[0].type == "person"
    assert records[0].provider_name == "openai"
    assert records[0].model_name == "gpt-4o-mini"
    assert records[0].source_offsets == (3, 8)


def test_ner_tool_serializes_selected_provider(monkeypatch):
    class FakeProvider:
        name = "spacy"
        model_name = "en_core_web_sm"

        async def extract(self, text, *, language=None, state=None, llm_config=None, inputs=None):
            return [
                ExtractedEntity(
                    name="Leidy",
                    type="person",
                    confidence=0.99,
                    source_offsets=(0, 5),
                    provider_name="spacy",
                    model_name="en_core_web_sm",
                )
            ]

    monkeypatch.setattr(
        "fichero_server.workflows.ner.providers.get_ner_provider",
        lambda provider, model=None: FakeProvider(),
    )

    result = asyncio.run(
        ner(
            {"text": "Leidy is a miner.", "provider": "spacy", "model": "en_core_web_sm"},
            state={},
            llm_config=SimpleNamespace(provider="openai", model="gpt-4o-mini"),
        )
    )
    assert result["entities"][0]["name"] == "Leidy"
    assert result["entities"][0]["provider_name"] == "spacy"
    assert result["value"] == result["entities"]

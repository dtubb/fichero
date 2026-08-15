"""Multi-provider NER adapters used by workflow nodes."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from fichero_server.knowledge import spacy_ner
from fichero_server.knowledge.ner import BaseNERProvider, ExtractedEntity

logger = logging.getLogger(__name__)


def _normalise_entity_type(entity_type: str) -> str:
    mapping = {
        "per": "person",
        "person": "person",
        "people": "person",
        "org": "organization",
        "organization": "organization",
        "organisation": "organization",
        "loc": "location",
        "gpe": "location",
        "location": "location",
        "place": "location",
        "date": "date",
        "money": "money",
        "event": "event",
        "misc": "concept",
    }
    return mapping.get(entity_type.lower(), entity_type.lower())


def _record(
    *,
    name: str,
    entity_type: str,
    provider_name: str,
    model_name: str | None,
    confidence: float = 1.0,
    source_offsets: tuple[int, int] | None = None,
    aliases: Iterable[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> ExtractedEntity:
    return ExtractedEntity(
        name=name,
        type=_normalise_entity_type(entity_type),
        confidence=confidence,
        source_offsets=source_offsets,
        provider_name=provider_name,
        model_name=model_name,
        aliases=list(aliases or []),
        metadata=dict(metadata or {}),
    )


def _flatten_llm_entities(
    entities: dict[str, Any],
    *,
    provider_name: str,
    model_name: str | None,
) -> list[ExtractedEntity]:
    records: list[ExtractedEntity] = []
    for entity_type, values in entities.items():
        if not isinstance(values, list):
            continue
        for value in values:
            if isinstance(value, str):
                name = value
                confidence = 1.0
                source_offsets = None
                aliases: list[str] = []
                metadata: dict[str, Any] = {}
            elif isinstance(value, dict):
                name = str(
                    value.get("name")
                    or value.get("entity")
                    or value.get("text")
                    or value.get("canonical_name")
                    or ""
                )
                confidence = float(value.get("confidence") or 1.0)
                start = value.get("start")
                end = value.get("end")
                source_offsets = (
                    (int(start), int(end))
                    if start is not None and end is not None
                    else None
                )
                aliases = [
                    str(alias)
                    for alias in (
                        value.get("aliases")
                        or value.get("alternative_spellings")
                        or []
                    )
                    if alias
                ]
                metadata = {
                    k: v
                    for k, v in value.items()
                    if k
                    not in {
                        "name",
                        "entity",
                        "text",
                        "canonical_name",
                        "confidence",
                        "start",
                        "end",
                        "aliases",
                        "alternative_spellings",
                    }
                }
            else:
                continue
            if not name:
                continue
            records.append(
                _record(
                    name=name,
                    entity_type=entity_type,
                    provider_name=provider_name,
                    model_name=model_name,
                    confidence=confidence,
                    source_offsets=source_offsets,
                    aliases=aliases,
                    metadata=metadata,
                )
            )
    return records


@dataclass
class LLMNERProvider(BaseNERProvider):
    name: str = "llm"
    model_name: str | None = None

    async def extract(
        self,
        text: str,
        *,
        language: str | None = None,
        state: Any | None = None,
        llm_config: Any | None = None,
        inputs: dict[str, Any] | None = None,
    ) -> list[ExtractedEntity]:
        from fichero_server.workflows.tools.entities import extract_entities as extract_entities_tool

        if not text:
            return []

        effective_inputs = dict(inputs or {})
        effective_inputs.setdefault("text", text)
        effective_inputs.setdefault(
            "entity_types",
            ["people", "organizations", "locations", "dates"],
        )
        effective_inputs.setdefault("include_context", False)
        effective_inputs.setdefault("deduplicate", True)
        effective_inputs["save_to_db"] = False
        effective_inputs["save_to_file"] = False
        if language:
            effective_inputs.setdefault("language", language)

        result = await extract_entities_tool(
            effective_inputs,
            state or {},
            llm_config,
        )
        entities = result.get("entities") or result.get("value") or {}
        provider_name = str(getattr(llm_config, "provider", None) or self.name)
        model_name = str(getattr(llm_config, "model", None) or self.model_name) or None
        return _flatten_llm_entities(
            entities if isinstance(entities, dict) else {},
            provider_name=provider_name,
            model_name=model_name,
        )


@dataclass
class SpacyNERProvider(BaseNERProvider):
    name: str = "spacy"
    model_name: str | None = None

    async def extract(
        self,
        text: str,
        *,
        language: str | None = None,
        state: Any | None = None,
        llm_config: Any | None = None,
        inputs: dict[str, Any] | None = None,
    ) -> list[ExtractedEntity]:
        if not text:
            return []

        effective_language = language if language in {"en", "es"} else None
        spans = spacy_ner.extract_entities(text, language=effective_language)
        clustered = spacy_ner.cluster_aliases(spans)
        records: list[ExtractedEntity] = []
        for canonical, aliases in clustered.items():
            records.append(
                _record(
                    name=canonical.text,
                    entity_type=canonical.fichero_type,
                    provider_name=self.name,
                    model_name=self.model_name,
                    confidence=0.99,
                    source_offsets=(canonical.start, canonical.end),
                    aliases=aliases,
                    metadata={"label": canonical.label},
                )
            )
        return records


@dataclass
class TransformersNERProvider(BaseNERProvider):
    name: str = "transformers"
    model_name: str | None = "dslim/bert-base-NER"

    def _load_pipeline(self):
        import transformers

        return transformers.pipeline(
            "token-classification",
            model=self.model_name,
            aggregation_strategy="simple",
        )

    async def extract(
        self,
        text: str,
        *,
        language: str | None = None,
        state: Any | None = None,
        llm_config: Any | None = None,
        inputs: dict[str, Any] | None = None,
    ) -> list[ExtractedEntity]:
        if not text:
            return []

        try:
            pipeline = self._load_pipeline()
        except Exception as exc:
            logger.warning(
                "transformers ner unavailable (%s) — falling back to no results",
                exc,
            )
            return []

        try:
            results = pipeline(text)
        except Exception as exc:
            logger.warning("transformers ner call failed: %s", exc)
            return []

        records: list[ExtractedEntity] = []
        for item in results or []:
            if not isinstance(item, dict):
                continue
            word = str(
                item.get("word") or item.get("entity_group") or item.get("entity") or ""
            )
            if not word:
                continue
            entity_type = str(item.get("entity_group") or item.get("entity") or "concept")
            records.append(
                _record(
                    name=word,
                    entity_type=entity_type,
                    provider_name=self.name,
                    model_name=self.model_name,
                    confidence=float(item.get("score") or 1.0),
                    source_offsets=(
                        (int(item["start"]), int(item["end"]))
                        if item.get("start") is not None and item.get("end") is not None
                        else None
                    ),
                    metadata={
                        k: v
                        for k, v in item.items()
                        if k not in {"word", "entity_group", "entity", "score", "start", "end"}
                    },
                )
            )
        return records


def get_ner_provider(provider: str | None, model: str | None = None) -> BaseNERProvider:
    """Return a provider instance for ``provider``."""

    key = (provider or "llm").strip().lower()
    if key in {"llm", "openai", "anthropic", "apple", "default", ""}:
        return LLMNERProvider(model_name=model)
    if key in {"spacy", "spacy_ner"}:
        return SpacyNERProvider(model_name=model or "en_core_web_sm")
    if key in {"transformers", "hf", "huggingface"}:
        return TransformersNERProvider(model_name=model or "dslim/bert-base-NER")
    logger.warning("Unknown NER provider %r; defaulting to llm", provider)
    return LLMNERProvider(model_name=model)

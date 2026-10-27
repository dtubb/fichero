"""Multi-provider NER adapters used by workflow nodes."""

from __future__ import annotations

import asyncio
import logging
import threading
import time
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
    # One choke point for every provider: a dotted paleographic surface form
    # ("Antonio.de.guzman") becomes a readable display name, and a PERSON whose
    # span ran on into a trailing descriptor ("… vecino de la ciudad de …") is
    # cut back to the name. Offsets are untouched, so the source anchor still
    # points at the original span.
    normalized_type = _normalise_entity_type(entity_type)
    display_name = spacy_ner.readable_surface_form(name)
    if normalized_type == "person":
        display_name = spacy_ner.trim_person_name(display_name)
    return ExtractedEntity(
        name=display_name,
        type=normalized_type,
        confidence=confidence,
        source_offsets=source_offsets,
        provider_name=provider_name,
        model_name=model_name,
        aliases=[spacy_ner.readable_surface_form(a) for a in (aliases or [])],
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

        # The caller may hand us a code ("en") or a resolved NAME ("English") —
        # the language-policy resolver emits names. Normalise both to the model
        # code so the DECLARED language routes to the matching model; None means
        # "unknown, detect from the text" rather than a wrong forced model.
        effective_language = spacy_ner.normalize_language(language)
        # The pinned pipeline and no other (`runtime.spacy.pin-is-honoured`).
        # On a worker thread: the call waits for the spaCy turn and then runs the pipeline, either of which held the
        # event loop (and every request on it) for as long as another page held the turn (`runtime.spacy.never-blocks`).
        def _work():
            found = spacy_ner.extract_entities(text, language=effective_language, model=self.model_name)
            return found, spacy_ner.cluster_aliases(found)

        spans, clustered = await asyncio.to_thread(_work)
        by_form = {(span.fichero_type, span.text): span for span in spans}
        records: list[ExtractedEntity] = []
        for canonical, aliases in clustered.items():
            # Every place the cluster's names are written, kept for the mentions (#5488).
            members = [canonical, *(by_form.get((canonical.fichero_type, a)) for a in aliases)]
            written = sorted({tuple(at) for m in members if m is not None
                              for at in (m.occurrences or ((m.start, m.end),))})
            records.append(
                _record(
                    name=canonical.text,
                    entity_type=canonical.fichero_type,
                    provider_name=self.name,
                    model_name=self.model_name,
                    confidence=0.99,
                    source_offsets=(canonical.start, canonical.end),
                    aliases=aliases,
                    metadata={"label": canonical.label, "spans": [list(at) for at in written]},
                )
            )
        return records


#: Loaded Transformers token-classification pipelines, one per model id (#5956 audit, ## 988): the provider is built per call, so the
#: pipeline lives here, as the spaCy pipelines do. It is ~1 GB with torch, so it is released like the embedders are (## 1003, #4999,
#: `activity.lane.idle-unload`): after `db.embeddings.EMBEDDER_IDLE_SECONDS` unused by a daemon thread, and at once when another model
#: needs the memory (`db.embeddings.release_idle_embedders(idle_seconds=0)` calls `release_idle_transformers`).
_TRANSFORMERS_PIPELINES: dict[str | None, Any] = {}
_TRANSFORMERS_LAST_USE: dict[str | None, float] = {}
_TRANSFORMERS_IN_USE: dict[str | None, int] = {}
_TRANSFORMERS_LOAD = threading.Lock()
_TRANSFORMERS_RELEASER: threading.Thread | None = None


def release_idle_transformers(idle_seconds: float | None = None, reason: str = "idle") -> list[str]:
    """Release every Transformers pipeline no extract holds and none has used for `idle_seconds`; the model ids released. Collected at
    once and the GPU's cached buffers given back (as Kraken's release does)."""
    if idle_seconds is None:
        from fichero_server.db import embeddings

        idle_seconds = embeddings.EMBEDDER_IDLE_SECONDS
    now = time.monotonic()
    with _TRANSFORMERS_LOAD:
        gone = [name for name in list(_TRANSFORMERS_PIPELINES)
                if not _TRANSFORMERS_IN_USE.get(name) and now - _TRANSFORMERS_LAST_USE.get(name, 0.0) >= idle_seconds]
        for name in gone:
            _TRANSFORMERS_PIPELINES.pop(name, None)
            _TRANSFORMERS_LAST_USE.pop(name, None)
    if gone:
        import gc
        import sys

        gc.collect()
        torch = sys.modules.get("torch")
        if torch is not None and torch.backends.mps.is_available():
            torch.mps.empty_cache()
        logger.info("model-lane: unload transformers ner %s (%s)", ", ".join(str(n) for n in gone), reason)
    return [str(n) for n in gone]


def clear_transformers_pipelines() -> None:
    """Forget the loaded pipelines now (a model replaced, or a test): the next extract loads again."""
    release_idle_transformers(idle_seconds=0, reason="cleared")
    with _TRANSFORMERS_LOAD:
        _TRANSFORMERS_PIPELINES.clear()
        _TRANSFORMERS_LAST_USE.clear()


def _release_transformers_when_idle() -> None:
    from fichero_server.db import embeddings

    while True:
        time.sleep(max(0.05, min(embeddings.EMBEDDER_IDLE_SECONDS / 4, 60.0)))
        release_idle_transformers()
        with _TRANSFORMERS_LOAD:
            if not _TRANSFORMERS_PIPELINES:
                return


def _start_transformers_releaser() -> None:
    """One daemon thread while a pipeline is loaded: checks for the idle spell, ends when none is."""
    global _TRANSFORMERS_RELEASER
    with _TRANSFORMERS_LOAD:
        if _TRANSFORMERS_RELEASER is not None and _TRANSFORMERS_RELEASER.is_alive():
            return
        _TRANSFORMERS_RELEASER = threading.Thread(target=_release_transformers_when_idle, name="transformers-ner-releaser", daemon=True)
        _TRANSFORMERS_RELEASER.start()


@dataclass
class TransformersNERProvider(BaseNERProvider):
    name: str = "transformers"
    model_name: str | None = "dslim/bert-base-NER"

    def _load_pipeline(self):
        """The pipeline for this model id: loaded once, under a lock (two pages asking at once load it once), then reused."""
        with _TRANSFORMERS_LOAD:
            if self.model_name not in _TRANSFORMERS_PIPELINES:
                _TRANSFORMERS_PIPELINES[self.model_name] = self._build_pipeline()
            _TRANSFORMERS_LAST_USE[self.model_name] = time.monotonic()
            _TRANSFORMERS_IN_USE[self.model_name] = _TRANSFORMERS_IN_USE.get(self.model_name, 0) + 1  # held until the extract ends
            pipeline = _TRANSFORMERS_PIPELINES[self.model_name]
        _start_transformers_releaser()
        return pipeline

    def _build_pipeline(self):
        # `transformers` is NOT in the embedded bundle. Say so by name rather
        # than let a bare ModuleNotFoundError reach the run log (2026-09-20).
        try:
            import transformers
        except ImportError as exc:
            raise RuntimeError(
                "The Transformers entity-recognition provider needs the "
                "'transformers' package, which this build of Fichero does not include. "
                "Choose the spaCy provider, or an LLM provider, instead."
            ) from exc

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
            pipeline = await asyncio.to_thread(self._load_pipeline)  # imports and loads weights: off the loop
        except Exception as exc:
            logger.warning(
                "transformers ner unavailable (%s) — falling back to no results",
                exc,
            )
            return []

        try:
            results = await asyncio.to_thread(pipeline, text)  # a model forward pass: off the loop (`runtime.spacy.never-blocks` family)
        except Exception as exc:
            logger.warning("transformers ner call failed: %s", exc)
            return []
        finally:  # the pipeline is no longer held: the idle spell counts from here (## 1003)
            with _TRANSFORMERS_LOAD:
                _TRANSFORMERS_IN_USE[self.model_name] = max(0, _TRANSFORMERS_IN_USE.get(self.model_name, 1) - 1)
                _TRANSFORMERS_LAST_USE[self.model_name] = time.monotonic()

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
        return SpacyNERProvider(model_name=model)  # unpinned: the language's preferred pipeline
    if key in {"transformers", "hf", "huggingface"}:
        return TransformersNERProvider(model_name=model or "dslim/bert-base-NER")
    logger.warning("Unknown NER provider %r; defaulting to llm", provider)
    return LLMNERProvider(model_name=model)

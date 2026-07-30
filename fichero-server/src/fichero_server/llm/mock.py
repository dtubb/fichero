"""Built-in deterministic mock LLM provider (#1566).

Backs ``LLMConfig(provider="mock")`` — a zero-cost, network-free responder
used to debug the catalogue / extraction pipeline (output, persistence,
per-page artifacts, UI) without spending a single paid LLM call.

The mock is *deterministic*: given the same prompt prefix it always returns
the same canned data, so a folder/PDF catalogue run is reproducible.

This module deliberately keeps ``extract_all`` imports LAZY (inside the
functions) to avoid a circular import — ``extract_all`` imports from
``fichero_server.llm``, which is where the ``provider == "mock"`` branch lives.
"""

from __future__ import annotations

from pydantic import BaseModel

# A short, fixed narrative used by the plain ``chat()`` mock branch so a
# catalogue's resumen / narrative node runs free end-to-end.
MOCK_NARRATIVE = (
    "Mock catalogue summary. This deterministic narrative is produced by the "
    "built-in debug provider so a full run can be exercised at zero cost."
)


def _prefix(prompt: str, n: int = 24) -> str:
    """Stable short token derived from the prompt prefix.

    Lets canned values vary a little per page (so distinct pages don't all
    collapse to byte-identical KG rows) while staying fully deterministic.
    """
    cleaned = " ".join((prompt or "").split())
    return cleaned[:n] or "mock"


def mock_chat_response(prompt: str) -> str:
    """Deterministic stand-in for the plain (non-structured) ``chat()`` call.

    The catalogue narrative node uses ``chat()`` directly, which the
    structured ``mock`` branch wouldn't intercept — so without this a full
    catalogue run with provider="mock" would hit LangChain with a
    nonexistent model and error. Returns a fixed canned narrative.
    """
    return MOCK_NARRATIVE


def mock_vision_response(prompt: str, image_count: int) -> str:
    """Deterministic stand-in for ``vision()`` under ``provider="mock"``.

    ``chat()`` and ``structured_output()`` both had a mock branch; ``vision()``
    did not, so any vision node in a mock run died with "Unknown LLM provider:
    'mock'" (#4345). Varies with the prompt prefix and image count the same way
    the other mock responders do, so distinct pages stay distinguishable while
    the run remains reproducible.
    """
    return (
        f"Mock vision response for {image_count} image(s). "
        f"Prompt: {_prefix(prompt)}"
    )


def mock_structured_response(schema: type[BaseModel], prompt: str) -> BaseModel:
    """Deterministic structured output for ``LLMConfig(provider="mock")``.

    For the extraction schemas (``_Extraction`` / ``_EntitiesOnly`` /
    ``_EntityClaims``) return small, grounded, canned instances. For any
    other Pydantic schema, construct it from its field defaults and fail
    loudly on a missing required field rather than silently dropping it.

    Args:
        schema: The Pydantic model class the caller expects back.
        prompt: The prompt text — used only to derive a stable per-call
            token so distinct pages produce distinct (but deterministic)
            source excerpts.

    Returns:
        An instance of ``schema``.
    """
    name = schema.__name__

    # Extraction schemas live in workflows/tools/extract_all.py — import
    # lazily to avoid a circular import (extract_all -> llm -> llm_mock).
    if name in {"_Extraction", "_EntitiesOnly", "_EntityClaims"}:
        from fichero_server.workflows.tools import extract_all as ea

        tag = _prefix(prompt)
        source = f"Mock source text for: {tag}"

        if name == "_Extraction":
            # Grounded SVO on every item so _extraction_is_thin() accepts
            # it (it rejects name-only lists where <50% are grounded).
            return ea._Extraction(
                people=[
                    ea._Person(
                        name="Ada Mock",
                        verb="signed",
                        object="the mock ledger",
                        source_text=source,
                    )
                ],
                places=[
                    ea._Place(
                        name="Mockton",
                        verb="hosted",
                        object="the mock meeting",
                        source_text=source,
                    )
                ],
                dates=[
                    ea._DateItem(
                        date="1 January 2000",
                        date_normalized="2000-01-01",
                        verb="marked",
                        object="the mock milestone",
                        source_text=source,
                    )
                ],
                keywords=["mock"],
            )

        if name == "_EntitiesOnly":
            return ea._EntitiesOnly(
                people=[ea._EntityOnly(name="Ada Mock", entity_type="person")],
                places=[ea._EntityOnly(name="Mockton", entity_type="place")],
                organizations=[],
                dates=[],
                events=[],
            )

        # _EntityClaims — one grounded claim for the requested subject.
        return ea._EntityClaims(
            subject="Ada Mock",
            claims=[
                ea._SVOClaim(
                    subject="Ada Mock",
                    verb="signed",
                    object="the mock ledger",
                    source_text=source,
                )
            ],
        )

    # Generic fallback: build from field defaults. Fail loudly (rather than
    # silently dropping) on any field that has neither a default nor a
    # default_factory — validation here surfaces the gap immediately.
    values: dict[str, object] = {}
    missing: list[str] = []
    for field_name, field in schema.model_fields.items():
        if field.is_required():
            missing.append(field_name)
    if missing:
        raise ValueError(
            f"mock_structured_response cannot construct {name}: required "
            f"field(s) {missing!r} have no default. Add a canned branch for "
            f"this schema in fichero_server.llm.mock."
        )
    return schema.model_construct(**values)

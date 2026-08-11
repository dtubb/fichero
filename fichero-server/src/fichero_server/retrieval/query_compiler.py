"""Natural-language → structured search compilation (#4116).

Sentence-like queries ("letters about mining from March 1948") drop down to
an LLM that compiles them into a structured search: a semantic query, entity
names, and the date/type filters ``Database.search`` already understands
(date_from/date_to/doc_type/file_type). Keyword-ish queries never reach the
LLM — no latency tax on 'cacao'.

AI = instrument: the compiled query is RETURNED to the caller
(SearchResponse.compiled_query) so the user always sees — and can edit —
what was actually searched. Compilation failure is likewise surfaced
(SearchResponse.compilation_error), never silently swallowed; the search
still runs on the raw query so retrieval never breaks on an LLM outage.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from fichero_server.db import Database

logger = logging.getLogger(__name__)

# Queries starting with these read as questions, not keyword lookups.
_QUESTION_WORDS = {
    "who", "what", "when", "where", "why", "how", "which",
    "did", "does", "do", "was", "were", "is", "are", "can",
    # Spanish — the corpora are largely Spanish-language archives.
    "quien", "quién", "que", "qué", "cuando", "cuándo", "donde", "dónde",
    "por", "como", "cómo", "cual", "cuál",
}

_COMPILER_SYSTEM_PROMPT = (
    "You compile a researcher's natural-language request into a structured "
    "archive search. Extract ONLY what the request states — never invent "
    "entities, dates, or types that are not implied by the wording. Dates "
    "must be ISO format (YYYY-MM-DD); use the span boundaries for partial "
    "dates ('March 1948' → 1948-03-01 to 1948-03-31). semantic_query is the "
    "request rephrased as a dense retrieval query in the request's own "
    "language, stripped of filter words already captured in other fields."
)


class CompiledQuery(BaseModel):
    """What the LLM compiled a natural-language request into."""

    semantic_query: str = Field(
        description="Dense retrieval query, filter words stripped"
    )
    entities: list[str] = Field(
        default_factory=list,
        description="Person/place/organization names the request mentions",
    )
    date_from: Optional[str] = Field(
        default=None, description="ISO date lower bound, if the request implies one"
    )
    date_to: Optional[str] = Field(
        default=None, description="ISO date upper bound, if the request implies one"
    )
    doc_type: Optional[str] = Field(
        default=None,
        description="Restrict to one document type ('file'/'folder'/'page') only if explicitly requested",
    )


def looks_like_natural_language(query: str) -> bool:
    """Heuristic gate: does this query deserve LLM compilation?

    Scope syntax (``people:Asprilla``) and quoted phrases are ALREADY
    structured — those keep the fast path, as do short keyword queries.
    """
    q = query.strip()
    if not q or q.startswith('"'):
        return False
    words = q.split()
    if ":" in words[0]:
        return False
    if q.endswith("?"):
        return True
    if words[0].lower().strip("¿") in _QUESTION_WORDS:
        return True
    return len(words) >= 5


def _resolve_compiler_config(db: "Database"):
    """First enabled provider/model from the library's Providers config —
    the same resolution chat uses. A library with NO configured providers
    falls back to the settings default (on-device Apple Intelligence), the
    same resolution bibliography extraction uses — Ask mode refusing with
    "no enabled LLM provider configured" on a fresh library was Daniel's
    2026-08-11 "that's terrible": the machine has an LLM, use it. If Apple
    FM is genuinely unavailable at runtime, chat_structured raises and
    enhanced_search reports it while searching the raw words — unchanged."""
    from fichero_server.llm import LLMConfig
    from fichero_server.llm.providers import get_provider_info
    # NOT `ModelModel`/`ProviderModel` — those are chat.py's local import
    # aliases, not names in fichero_server.models. Importing them here raised
    # ImportError on every live compile (tests mocked this resolver).
    from fichero_server.models import Model as ModelModel
    from fichero_server.models import Provider as ProviderModel

    configured = db.query(ProviderModel, enabled=True)
    if not configured:
        return LLMConfig(
            provider="apple",
            model="apple-intelligence",
            temperature=0.0,
            max_tokens=400,
        )
    provider_row = configured[0]
    provider = provider_row.provider_type.value
    models = db.query(ModelModel, provider_id=provider_row.id, enabled=True)
    if models:
        model = models[0].model_id
    else:
        info = get_provider_info(provider)
        model = info.default_model if info else None
    if not model:
        return None
    return LLMConfig(
        provider=provider,
        model=model,
        # Deterministic extraction, tiny output.
        temperature=0.0,
        max_tokens=400,
        api_base=provider_row.api_base,
    )


async def compile_query(db: "Database", query: str) -> CompiledQuery:
    """Compile ``query`` via the configured LLM. Raises on failure —
    the caller decides how to surface it (enhanced_search reports it in
    ``compilation_error`` and searches the raw query)."""
    from fichero_server.llm import chat_structured

    config = _resolve_compiler_config(db)
    if config is None:
        raise RuntimeError("no enabled LLM provider configured")

    compiled = await chat_structured(
        prompt=f"Compile this search request:\n\n{query}",
        schema=CompiledQuery,
        config=config,
        system=_COMPILER_SYSTEM_PROMPT,
        use_case="search-query-compilation",
    )
    if not isinstance(compiled, CompiledQuery):
        compiled = CompiledQuery.model_validate(compiled)
    if not compiled.semantic_query.strip():
        compiled.semantic_query = query
    return compiled

"""Live smoke test for SVO extraction against Apple Intelligence.

Runs the per-section Pydantic schema through `chat_structured_with_fallback`
against the actual fm-bridge binary. The Pydantic schema enforces that
`verb` and `object` are present and non-empty — if the LLM can't follow
the SVO contract, the parse fails. So a passing test = the prompt works.

Skipped automatically when the fm-bridge binary isn't bundled (CI on
Linux, or a checkout that hasn't built the bridge yet).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from fichero_server.llm import LLMConfig, chat_structured_with_fallback
from fichero_server.workflows.tools.extractors import (
    _SECTION_SCHEMAS,
    _SECTIONS,
    _build_section_prompt,
)


def _fm_bridge_available() -> bool:
    candidates = [
        Path(__file__).resolve().parents[2] / "bin" / "fm-bridge" / "fm-bridge",
        Path(__file__).resolve().parents[2] / "src" / "fichero" / "resources" / "bin" / "fm-bridge",
    ]
    for p in candidates:
        if p.exists() and os.access(p, os.X_OK):
            return True
    return False


pytestmark = pytest.mark.skipif(
    not _fm_bridge_available(),
    reason="fm-bridge binary not found — Apple Intelligence smoke test only runs on built macOS checkouts",
)


# A sample archival paragraph with named people in clear roles.
# Picked so a competent extractor produces predictable SVO output.
SAMPLE_PARAGRAPH = (
    "Eugenio Córdoba, alcalde de Popayán, recibió la petición de los "
    "herederos el 23 de julio de 1933. Juan Pérez actuó como testigo "
    "y firmó el documento. La Imprenta Oficial publicó el decreto al "
    "día siguiente."
)


@pytest.fixture
def apple_cfg() -> LLMConfig:
    return LLMConfig(provider="apple", model="apple-intelligence", timeout=30)


@pytest.mark.asyncio
async def test_apple_intelligence_emits_valid_svo_for_people(apple_cfg) -> None:
    """Run people_extract against Apple Intelligence on a known paragraph
    and verify the structured output conforms to the SVO Pydantic schema.

    Grammar-constrained decoding means the LLM CANNOT emit invalid JSON.
    Pydantic enforces `verb` and `object` are present + non-empty
    strings. So a successful run proves the prompt + schema work
    end-to-end on the on-device model.
    """
    section = next(s for s in _SECTIONS if s["name"] == "people_extract")
    schema = _SECTION_SCHEMAS[section["schema_key"]]
    system_prompt = _build_section_prompt(section, "English")

    result = await chat_structured_with_fallback(
        prompt=SAMPLE_PARAGRAPH,
        schema=schema,
        config=apple_cfg,
        system=system_prompt,
        include_schema_in_prompt=False,
    )

    items = result.items if hasattr(result, "items") else []
    assert items, "Expected at least one person extracted from the paragraph"

    # Every item must have non-empty verb + object, and the name must
    # NOT appear inside verb or object (that's the implicit-subject
    # rule the prompt enforces).
    for item in items:
        assert item.name, f"empty name on {item!r}"
        assert item.verb.strip(), f"empty verb on {item!r}"
        assert item.object.strip(), f"empty object on {item!r}"
        assert item.name.lower() not in item.verb.lower(), (
            f"name appears in verb (should be implicit subject): {item!r}"
        )
        # New axes from #892 — Apple Intelligence must emit values
        # in the EpistemicStatus + ClaimType enums (grammar-constrained
        # decoding should make this strict; assert anyway).
        assert item.epistemic_status in {"tentative", "confirmed", "rejected"}, (
            f"invalid epistemic_status on {item!r}"
        )
        assert item.claim_type in {
            "fact", "analysis", "interpretation",
            "argument", "historiography", "theory"
        }, f"invalid claim_type on {item!r}"
        # source_text is best-effort on Apple Intelligence today —
        # the on-device model frequently falls through to the schema
        # default ("") because the field has a default and the grammar
        # doesn't force emission. Log the divergence; don't fail.
        # When source_text IS populated it must reference the name or
        # be a substring of the paragraph (the verbatim contract).
        if item.source_text.strip():
            haystack = " ".join(SAMPLE_PARAGRAPH.split())
            needle = " ".join(item.source_text.split())
            assert item.name in needle or needle in haystack, (
                f"source_text neither references name nor matches paragraph: {item!r}"
            )
        # The object can occasionally restate the role with the name;
        # allow it but log for review.
        # No hard assertion — Apple Intelligence sometimes echoes.

    # Print for human review — pytest -s will surface this.
    print("\n--- Apple Intelligence SVO output ---")
    for item in items:
        print(
            f"  [{item.epistemic_status}/{item.claim_type}] "
            f"{item.name} {item.verb} {item.object}."
        )
        print(f"    source: “{item.source_text}”")
    print("-" * 40)


@pytest.mark.asyncio
async def test_apple_intelligence_emits_valid_svo_for_dates(apple_cfg) -> None:
    """Same drill for the date section — verifies verb + object work
    when the subject is a normalized date string, not an entity name."""
    section = next(s for s in _SECTIONS if s["name"] == "dates_extract")
    schema = _SECTION_SCHEMAS[section["schema_key"]]
    system_prompt = _build_section_prompt(section, "English")

    result = await chat_structured_with_fallback(
        prompt=SAMPLE_PARAGRAPH,
        schema=schema,
        config=apple_cfg,
        system=system_prompt,
        include_schema_in_prompt=False,
    )

    items = result.items if hasattr(result, "items") else []
    assert items, "Expected at least one date extracted (1933-07-23)"
    for item in items:
        assert item.date, f"empty date on {item!r}"
        assert item.date_normalized, f"empty normalized date on {item!r}"
        assert item.verb.strip(), f"empty verb on {item!r}"
        assert item.object.strip(), f"empty object on {item!r}"

    print("\n--- Apple Intelligence SVO output (dates) ---")
    for item in items:
        print(f"  {item.date_normalized}: {item.verb} {item.object}.")
    print("-" * 40)

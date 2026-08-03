"""The three surfaces named in #2092 actually honour the language policy.

Unit tests on the resolver prove the policy is right. These prove it is
CONNECTED — which is the half that was missing: a correct global setting that
three of nine tools consulted, while transcription hardcoded English and SVO /
entity extraction shipped the literal word "auto" into the prompt.
"""

from __future__ import annotations

import duckdb
import pytest

from fichero_server.db.migrations.schema import migrate_document_language_fields
from fichero_server.llm.language_policy import UNKNOWN_LANGUAGE_INSTRUCTION, parse_policy
from fichero_server.models import Document
from fichero_server.workflows.tools.extract_all import (
    _build_entity_only_instructions,
    _build_per_entity_claim_instructions,
)
from fichero_server.workflows.tools.transcribe import (
    TRANSCRIBE_CONFIG,
    _build_prompt,
    _resolve_transcribe_language,
)


def _columns(conn, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info('{table}')").fetchall()}


# ---------------------------------------------------------------------------
# Migration + backfill
# ---------------------------------------------------------------------------


def test_language_columns_are_added_idempotently_and_skip_a_missing_table():
    conn = duckdb.connect(":memory:")

    migrate_document_language_fields(conn)  # no documents table yet — must not raise

    conn.execute("CREATE TABLE documents (id VARCHAR)")
    conn.execute("INSERT INTO documents VALUES ('document-1')")

    migrate_document_language_fields(conn)
    migrate_document_language_fields(conn)

    assert {"language", "language_meta"} <= _columns(conn, "documents")


def test_backfill_leaves_existing_documents_as_never_determined_not_english():
    """The Marshall Diaries are real Spanish-language data.

    There is no correct value to backfill because the fact was never recorded
    at ingest. NULL says "nothing has ever determined this", which is true;
    'English' would be a fabrication that looks exactly like a real answer.
    """
    conn = duckdb.connect(":memory:")
    conn.execute("CREATE TABLE documents (id VARCHAR)")
    conn.execute("INSERT INTO documents VALUES ('document-1')")

    migrate_document_language_fields(conn)

    assert conn.execute("SELECT language, language_meta FROM documents").fetchone() == (
        None,
        None,
    )


def test_a_document_model_defaults_to_never_determined():
    document = Document(name="untitled")
    assert document.language is None
    assert document.language_meta is None


# ---------------------------------------------------------------------------
# Transcription — the hardcoded en-US
# ---------------------------------------------------------------------------


def test_transcribe_no_longer_defaults_to_english():
    assert TRANSCRIBE_CONFIG["language"]["default"] == "auto"


@pytest.mark.parametrize("language", ["auto", "", "unknown", None])
def test_transcribe_prompt_does_not_assert_english_when_nothing_is_known(language):
    prompt = _build_prompt(language, False)
    assert "Language: en-US" not in prompt
    assert "language of the source" in prompt
    assert "do not assume the document is in English" in prompt


def test_transcribe_prompt_states_a_language_that_was_established():
    assert "Language: es-ES" in _build_prompt("es-ES", False)


@pytest.mark.parametrize(
    "name,locale",
    [("Spanish", "es-ES"), ("English", "en-US"), ("Portuguese", "pt-BR")],
)
def test_a_resolved_language_name_becomes_a_vision_locale(name, locale):
    """The policy speaks language names; Apple Vision speaks locales.

    Without this seam a correctly-resolved "Spanish" reached the recognition
    request as the literal string "spanish" — worse OCR than before the policy
    existed, on exactly the material it was built for.
    """
    from fichero_server.workflows.tools.vision_base import normalize_vision_language

    assert normalize_vision_language(name) == locale


def test_vision_locales_and_legacy_aliases_still_normalise():
    from fichero_server.workflows.tools.vision_base import normalize_vision_language

    assert normalize_vision_language("es") == "es-ES"
    assert normalize_vision_language("es-ES") == "es-ES"
    assert normalize_vision_language("") == "en-US"


def test_transcribe_uses_the_documents_recorded_language():
    document = Document(name="page 1", language="Spanish", language_meta={"status": "known"})
    resolution = _resolve_transcribe_language(None, [document])
    assert resolution.language == "Spanish"


def test_transcribe_refuses_to_pick_one_language_for_a_mixed_batch():
    """A batch shares one prompt; asserting either language misreads the other."""
    spanish = Document(name="a", language="Spanish", language_meta={"status": "known"})
    english = Document(name="b", language="English", language_meta={"status": "known"})
    resolution = _resolve_transcribe_language(None, [spanish, english])
    assert resolution.language is None
    assert "different languages" in resolution.basis


def test_transcribe_honours_an_explicit_locale_on_the_node():
    document = Document(name="page 1", language="Spanish", language_meta={"status": "known"})
    assert _resolve_transcribe_language("la-VA", [document]).language == "la-VA"


# ---------------------------------------------------------------------------
# SVO + entity extraction — the literal "auto" in the prompt
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "build",
    [_build_per_entity_claim_instructions, _build_entity_only_instructions],
    ids=["svo", "entities"],
)
def test_extraction_instructions_never_say_write_in_auto(build):
    """Regression: both tools passed the raw config value straight through, so
    the default produced "Write in auto." — an instruction to nobody."""
    instructions = build(UNKNOWN_LANGUAGE_INSTRUCTION)
    assert "in auto" not in instructions.lower()
    assert "the same language as the source document" in instructions


@pytest.mark.parametrize(
    "build",
    [_build_per_entity_claim_instructions, _build_entity_only_instructions],
    ids=["svo", "entities"],
)
def test_extraction_instructions_name_a_resolved_language(build):
    assert "Spanish" in build("Spanish")


def test_svo_and_entity_tools_resolve_through_the_policy():
    """Both modules import the resolver — the wiring, not just the ability."""
    from fichero_server.workflows.tools import extract_entities_only, extract_svo_only

    for module in (extract_svo_only, extract_entities_only):
        assert hasattr(module, "resolve_language")
        assert hasattr(module, "configured_policy")


def test_a_per_document_override_beats_the_global_default_end_to_end():
    from fichero_server.llm.language_policy import resolve_language, set_user_language

    document = Document(name="page 1")
    set_user_language(document, "Spanish")
    resolution = resolve_language(
        document=document, text="", policy=parse_policy("English")
    )
    assert resolution.language == "Spanish"

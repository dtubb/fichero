"""Unit tests for the quotes_extract tool (#1099).

Covers:
- _SectionQuote schema accepts nullable speaker
- quotes_extract registered in EXTRACTORS with correct icon/color
- _write_kg_rows: attributed quote creates person entity + claim
- _write_kg_rows: unattributed quote creates claim with subject_canonical=None
"""

from __future__ import annotations

import pytest

from fichero_server.models.knowledge import EntityType, KnowledgeEntity, KnowledgeClaim
from fichero_server.models import Document, DocType
from fichero_server.llm import LLMConfig
from fichero_server.workflows.tools.extractors import EXTRACTORS, _SECTION_SCHEMAS


# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------


def test_section_quote_schema_nullable_speaker():
    """_SectionQuote must accept name=None (unattributed quote)."""
    schema = _SECTION_SCHEMAS["quotes"]
    result = schema(
        items=[
            {
                "name": None,
                "verb": "said",
                "object": "The land belongs to no one.",
                "source_text": "According to the document, 'The land belongs to no one.'",
            }
        ]
    )
    assert len(result.items) == 1
    assert result.items[0].name is None
    assert result.items[0].object == "The land belongs to no one."


def test_section_quote_schema_attributed():
    """_SectionQuote with a named speaker should parse correctly."""
    schema = _SECTION_SCHEMAS["quotes"]
    result = schema(
        items=[
            {
                "name": "Don Antonio",
                "verb": "argued",
                "object": "We have a right to this water.",
                "source_text": "Don Antonio argued: 'We have a right to this water.'",
            }
        ]
    )
    assert result.items[0].name == "Don Antonio"
    assert result.items[0].verb == "argued"


# ---------------------------------------------------------------------------
# Registration tests
# ---------------------------------------------------------------------------


def test_quotes_extract_registered():
    """quotes_extract must appear in the EXTRACTORS dict."""
    assert "quotes_extract" in EXTRACTORS


def test_quotes_extract_icon_and_color():
    """quotes_extract must use text.quote icon and purple color."""
    from fichero_server.workflows.registry import get_tool_def
    tool = get_tool_def("quotes_extract")
    assert tool is not None
    assert tool.icon == "text.quote"
    assert tool.color == "purple"


# ---------------------------------------------------------------------------
# KG-write tests
# ---------------------------------------------------------------------------


@pytest.fixture
def llm_config():
    return LLMConfig(provider="openai", model="gpt-4o-mini")


@pytest.fixture
def container_doc(db):
    doc = Document(name="Test Doc", path="/test.txt", doc_type=DocType.file)
    db.save(doc)
    return doc


def test_attributed_quote_creates_entity_and_claim(db, container_doc, llm_config):
    """An attributed quote writes a person entity + claim."""
    from fichero_server.workflows.tools.extractors import _write_kg_rows, _SECTIONS

    section = next(s for s in _SECTIONS if s["name"] == "quotes_extract")
    items = [
        {
            "name": "María López",
            "verb": "testified",
            "object": "I saw the men at the river.",
            "source_text": "María López testified: 'I saw the men at the river.'",
            "epistemic_status": "confirmed",
            "claim_type": "fact",
        }
    ]
    _write_kg_rows(
        db=db,
        section=section,
        items=items,
        container_id=container_doc.id,
        provider="openai",
        model="gpt-4o-mini",
    )

    entities = db.query(KnowledgeEntity, entity_type=EntityType.person)
    names = [e.canonical_name for e in entities]
    assert "María López" in names

    claims = db.query(KnowledgeClaim, source_document_id=container_doc.id)
    assert any("testified" in (c.predicate_verb or "") for c in claims)
    assert any("I saw the men at the river." in (c.object_phrase or "") for c in claims)


def test_unattributed_quote_writes_null_subject_claim(db, container_doc, llm_config):
    """An unattributed quote (name=None) must write a claim with subject_canonical=None."""
    from fichero_server.workflows.tools.extractors import _write_kg_rows, _SECTIONS

    section = next(s for s in _SECTIONS if s["name"] == "quotes_extract")
    items = [
        {
            "name": None,
            "verb": "said",
            "object": "No one remembers who was there.",
            "source_text": "It was said: 'No one remembers who was there.'",
            "epistemic_status": "tentative",
            "claim_type": "fact",
        }
    ]
    _write_kg_rows(
        db=db,
        section=section,
        items=items,
        container_id=container_doc.id,
        provider="openai",
        model="gpt-4o-mini",
    )

    claims = db.query(KnowledgeClaim, source_document_id=container_doc.id)
    null_subject_claims = [c for c in claims if c.subject_canonical is None]
    assert len(null_subject_claims) >= 1, "Expected a claim with null subject for unattributed quote"
    assert any(
        "No one remembers" in (c.object_phrase or "")
        for c in null_subject_claims
    )

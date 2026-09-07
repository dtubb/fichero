"""SVO claims carry an English DISPLAY rendering, without losing provenance (#4494).

Daniel wants the statements readable in English even on a Spanish corpus. The
verbatim source-language verb/object stay the ground truth every gate checks
against (grounding, the fuzzy anchor); these English fields are display only.

Population rule in _write_kg_rows:
  1. an extractor-supplied translation (verb_en/object_en) wins;
  2. else, when the source is English, the verbatim triple already reads as
     English, so mirror it;
  3. else leave the English fields null and let the surface fall back to the
     verbatim triple.
"""

from __future__ import annotations

from fichero_server.workflows.tools.extractors import _write_kg_rows

ENGLISH_PAGE = (
    "Hindenburg fled to the frontier and the party crossed the border in the night."
)
SPANISH_PAGE = (
    "El escribano Andrés Hernández huyó de la ciudad y sus hombres cruzaron la "
    "frontera por la noche, según el acta de la villa."
)


def _people_section():
    from fichero_server.models.knowledge import EntityType
    return {"name": "people", "key": "people", "entity_type": EntityType.person}


def _saved_claim(tmp_path, item, page_excerpt):
    from fichero_server.db import Database
    from fichero_server.models import Document, DocType
    from fichero_server.models.knowledge import KnowledgeClaim

    db = Database(tmp_path / "svo_en.fichero")
    db.save(Document(id="doc-1", name="page.pdf", doc_type=DocType.file))
    _write_kg_rows(
        db, _people_section(), [item], "doc-1",
        page_label="1", source_excerpt=page_excerpt,
        provider="fixture", model="fixture-v1",
    )
    claims = list(db.query(KnowledgeClaim))
    assert claims, "no claim saved"
    return claims[0]


def test_english_source_mirrors_the_verbatim_triple(tmp_path):
    item = {"name": "Hindenburg", "verb": "fled", "object": "the frontier", "source_text": ""}
    claim = _saved_claim(tmp_path, item, ENGLISH_PAGE)
    assert claim.predicate_verb_en == "fled"
    assert claim.object_phrase_en == "the frontier"
    assert claim.claim_text_en == "Hindenburg fled the frontier."
    # Verbatim ground truth is unchanged.
    assert claim.predicate_verb == "fled"


def test_extractor_translation_wins_on_a_spanish_source(tmp_path):
    item = {
        "name": "Andrés Hernández",
        "verb": "huyó",
        "object": "de la ciudad",
        "verb_en": "fled",
        "object_en": "from the city",
        "source_text": "",
    }
    claim = _saved_claim(tmp_path, item, SPANISH_PAGE)
    assert claim.predicate_verb_en == "fled"
    assert claim.object_phrase_en == "from the city"
    assert claim.claim_text_en == "Andrés Hernández fled from the city."
    # Verbatim stays source-language for grounding/provenance.
    assert claim.predicate_verb == "huyó"
    assert claim.object_phrase == "de la ciudad"


def test_spanish_source_without_a_translation_leaves_english_null(tmp_path):
    item = {"name": "Andrés Hernández", "verb": "huyó", "object": "de la ciudad", "source_text": ""}
    claim = _saved_claim(tmp_path, item, SPANISH_PAGE)
    # No English available → null, so the surface falls back to the verbatim
    # triple rather than showing an invented translation.
    assert claim.predicate_verb_en is None
    assert claim.object_phrase_en is None
    assert claim.claim_text_en is None
    assert claim.predicate_verb == "huyó"


class TestExtractorPlumbingCarriesTheTranslation:
    """The extractor schemas accept verb_en/object_en and the dict builders
    carry them to the item _write_kg_rows reads — the LLM half (prompt asks
    for the restatement) is verified live by the build lane."""

    def test_page_claim_schema_accepts_english_fields(self):
        from fichero_server.workflows.tools.extract_all import _PageClaimItem
        item = _PageClaimItem(
            subject="X", verb="huyó", object="de la ciudad",
            verb_en="fled", object_en="from the city",
        )
        dumped = item.model_dump()
        assert dumped["verb_en"] == "fled"
        assert dumped["object_en"] == "from the city"

    def test_svo_claim_schema_accepts_english_fields(self):
        from fichero_server.workflows.tools.extract_all import _SVOClaim
        claim = _SVOClaim(
            subject="X", verb="huyó", object="de la ciudad",
            verb_en="fled", object_en="from the city", source_text="huyó de la ciudad",
        )
        assert claim.verb_en == "fled" and claim.object_en == "from the city"

    def test_build_entity_items_carries_english_through_to_the_item(self):
        from types import SimpleNamespace
        from fichero_server.workflows.tools.extract_all import _build_entity_items_for_section
        entity = SimpleNamespace(name="Andrés Hernández", aliases=[])
        claims = [{
            "verb": "huyó", "object": "de la ciudad",
            "verb_en": "fled", "object_en": "from the city",
            "source_text": "", "date_normalized": "", "claim_location": "",
        }]
        items = _build_entity_items_for_section(entity, "people", claims)
        assert items[0]["verb_en"] == "fled"
        assert items[0]["object_en"] == "from the city"

"""A name, a mention and a statement in the record stream say who made them, how sure, and whether a person
reviewed them (#6805)."""

from fichero_server.export_service import iter_export_records
from fichero_server.models import DocType, Document, FileType, KnowledgeClaim, KnowledgeEntity
from fichero_server.models.knowledge import (
    AttributionRole,
    AttributionStep,
    ClaimCurationState,
    EntityCurationState,
    EntityType,
    SourceSupport,
)


def _seed(db):
    page = Document(id="p1", name="Folio 1", doc_type=DocType.file, file_type=FileType.text,
                    page_content="Pedro signed.")
    entity = KnowledgeEntity(
        id="e1", canonical_name="Pedro", entity_type=EntityType.person, source_document_ids=[page.id],
        curation_state=EntityCurationState.verified,
        attribution_chain=[AttributionStep(role=AttributionRole.extractor, name="ollama", label="llama3"),
                           AttributionStep(role=AttributionRole.editor, name="Ana")],
        source_supports=[SourceSupport(source_document_id=page.id, source_char_start=0, source_char_end=5,
                                       support_confidence=0.9)],
    )
    claim = KnowledgeClaim(
        id="c1", text="Pedro signed.", source_document_id=page.id, entity_ids=[entity.id],
        confidence=0.8, curation_state=ClaimCurationState.curated,
        attribution_chain=[AttributionStep(role=AttributionRole.editor, name="Ana")],
    )
    for row in (page, entity, claim):
        db.save(row)
    return page


def _by_type(db, record_type):
    return [r for r in iter_export_records(db, target_id=None, granularity="page") if r["record_type"] == record_type]


def test_a_claim_says_how_sure_whether_reviewed_and_who(db):
    _seed(db)
    (claim,) = _by_type(db, "claim")
    assert claim["confidence"] == 0.8
    assert claim["curation_state"] == "curated"
    assert claim["made_by"] == {"by": "person", "name": "Ana"}


def test_an_entity_says_who_made_it_and_whether_reviewed(db):
    _seed(db)
    (entity,) = _by_type(db, "entity")
    assert entity["curation_state"] == "verified"
    assert entity["made_by"] == {"by": "person", "name": "Ana"}


def test_a_mention_says_how_sure_and_whether_reviewed(db):
    _seed(db)
    (mention,) = _by_type(db, "mention")
    assert mention["confidence"] == 0.9
    assert mention["curation_state"] == "verified"

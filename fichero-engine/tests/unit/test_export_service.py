import pytest

from fichero.export_service import export_eleventy_site, iter_export_records
from fichero.knowledge_models import ClaimType, EntityType
from fichero.models import DocType, Document, FileType, KnowledgeClaim, KnowledgeEntity


def _seed_export_library(db):
    root = Document(id="root", name="Archivo", doc_type=DocType.folder)
    box = Document(id="box", name="Caja 7", parent_id=root.id, doc_type=DocType.folder)
    expediente = Document(
        id="expediente",
        name="Expediente 12",
        parent_id=box.id,
        doc_type=DocType.folder,
    )
    page = Document(
        id="page-1",
        name="Folio 1",
        parent_id=expediente.id,
        doc_type=DocType.file,
        file_type=FileType.text,
        sequence=1,
        page_label="1r",
        page_content="Pedro signed the petition.",
    )
    page_two = Document(
        id="page-2",
        name="Folio 2",
        parent_id=expediente.id,
        doc_type=DocType.file,
        file_type=FileType.text,
        sequence=2,
        page_content="Maria witnessed the signature.",
    )
    entity = KnowledgeEntity(
        id="entity-pedro",
        canonical_name="Pedro",
        entity_type=EntityType.person,
        source_document_ids=[page.id, page_two.id],
    )
    claim = KnowledgeClaim(
        id="claim-pedro",
        text="Pedro signed the petition.",
        source_document_id=page.id,
        source_page_label="1r",
        source_excerpt="Pedro signed",
        entity_ids=[entity.id],
        claim_type=ClaimType.fact,
    )
    for row in (root, box, expediente, page, page_two, entity, claim):
        db.save(row)
    return root, box, expediente, page, page_two, entity, claim


def test_iter_export_records_page_granularity_carries_document_provenance(db):
    root, box, expediente, page, page_two, entity, claim = _seed_export_library(db)

    records = list(iter_export_records(db, target_id=root.id, granularity="page"))
    entity_records = [r for r in records if r["record_type"] == "entity"]
    claim_records = [r for r in records if r["record_type"] == "claim"]
    document_records = [r for r in records if r["record_type"] == "document"]

    assert {r["document_id"] for r in document_records} == {page.id, page_two.id}
    assert {r["scope_id"] for r in entity_records} == {page.id, page_two.id}
    assert claim_records == [
        {
            "record_type": "claim",
            "granularity": "page",
            "scope_id": page.id,
            "scope_name": page.name,
            "scope_kind": "page",
            "found_in_document_id": page.id,
            "found_in_document_name": page.name,
            "found_in_page_id": page.id,
            "found_in_page_label": "1r",
            "found_in_expediente_id": expediente.id,
            "found_in_expediente_name": expediente.name,
            "found_in_box_collection_id": box.id,
            "found_in_box_collection_name": box.name,
            "found_in_excerpt": "Pedro signed",
            "id": claim.id,
            "claim_id": claim.id,
            "text": claim.text,
            "claim_type": "fact",
            "epistemic_status": None,
            "entity_ids": [entity.id],
            "metadata": {},
            "source_document_id": page.id,
            "source_page_label": "1r",
            "source_excerpt": "Pedro signed",
        }
    ]


def test_iter_export_records_expediente_granularity_dedupes_entity_scopes(db):
    root, _, expediente, _, _, entity, _ = _seed_export_library(db)

    records = list(
        iter_export_records(db, target_id=root.id, granularity="expediente-folder")
    )
    entity_records = [r for r in records if r["record_type"] == "entity"]

    assert len(entity_records) == 1
    assert entity_records[0]["entity_id"] == entity.id
    assert entity_records[0]["scope_id"] == expediente.id
    assert entity_records[0]["scope_name"] == expediente.name
    assert entity_records[0]["scope_kind"] == "expediente-folder"
    assert entity_records[0]["found_in_expediente_id"] == expediente.id


def test_iter_export_records_box_granularity_uses_top_collection_scope(db):
    root, box, _, page, _, _, _ = _seed_export_library(db)

    records = list(iter_export_records(db, target_id=root.id, granularity="box-collection"))
    document_records = [r for r in records if r["record_type"] == "document"]

    assert {r["scope_id"] for r in document_records} == {box.id}
    assert {r["scope_name"] for r in document_records} == {box.name}
    assert {r["found_in_page_id"] for r in document_records} == {page.id, "page-2"}


def test_export_eleventy_site_output_stays_document_only(db, tmp_path):
    root, _, _, _, _, _, _ = _seed_export_library(db)

    result = export_eleventy_site(db, tmp_path / "site", target_id=root.id)
    page = tmp_path / "site" / "src" / "Caja-7" / "Expediente-12" / "Folio-1.md"

    assert result.document_count == 2
    assert page.exists()
    body = page.read_text(encoding="utf-8")
    assert "# Folio 1" in body
    assert "Pedro signed the petition." in body
    assert "Knowledge Graph Appendix" not in body


def test_iter_export_records_empty_corpus_returns_no_records(db):
    assert list(iter_export_records(db)) == []


def test_iter_export_records_document_without_knowledge_rows_exports_document_only(db):
    root = Document(id="plain-root", name="Archivo", doc_type=DocType.folder)
    page = Document(
        id="plain-page",
        name="Folio solo",
        parent_id=root.id,
        doc_type=DocType.file,
        file_type=FileType.text,
        page_content="Solo texto.",
    )
    db.save(root)
    db.save(page)

    assert list(iter_export_records(db, target_id=root.id, granularity="page")) == [
        {
            "record_type": "document",
            "granularity": "page",
            "scope_id": page.id,
            "scope_name": page.name,
            "scope_kind": "page",
            "found_in_document_id": page.id,
            "found_in_document_name": page.name,
            "found_in_page_id": page.id,
            "found_in_page_label": None,
            "found_in_expediente_id": None,
            "found_in_expediente_name": None,
            "found_in_box_collection_id": None,
            "found_in_box_collection_name": None,
            "id": page.id,
            "document_id": page.id,
            "name": page.name,
            "doc_type": "file",
            "file_type": "text",
            "path": None,
            "parent_id": root.id,
            "sequence": None,
            "page_content": "Solo texto.",
            "metadata": {},
            "provenance_chain": [],
            "workflow_runs": [],
        }
    ]


def test_iter_export_records_preserves_unicode_and_mojibakeish_names(db):
    root = Document(id="unicode-root", name="Archivo", doc_type=DocType.folder)
    doc_nfc = Document(
        id="doc-nfc",
        name="Chocó",
        parent_id=root.id,
        doc_type=DocType.file,
        file_type=FileType.text,
        page_content='Carta "Niño".',
    )
    doc_nfd = Document(
        id="doc-nfd",
        name="Choco\u0301",
        parent_id=root.id,
        doc_type=DocType.file,
        file_type=FileType.text,
        page_content="BogotÃ¡ en el margen.",
    )
    entity = KnowledgeEntity(
        id="entity-unicode",
        canonical_name="Señora Bogotá",
        entity_type=EntityType.person,
        source_document_ids=[doc_nfc.id, doc_nfd.id],
    )
    db.save(root)
    db.save(doc_nfc)
    db.save(doc_nfd)
    db.save(entity)

    records = list(iter_export_records(db, target_id=root.id, granularity="page"))

    document_names = [record["name"] for record in records if record["record_type"] == "document"]
    entity_names = [
        record["canonical_name"] for record in records if record["record_type"] == "entity"
    ]
    assert "Chocó" in document_names
    assert "Choco\u0301" in document_names
    assert document_names.count("Chocó") == 1
    assert document_names.count("Choco\u0301") == 1
    assert entity_names == ["Señora Bogotá", "Señora Bogotá"]


def test_iter_export_records_raises_for_missing_claim_provenance_source(db):
    root = Document(id="missing-root", name="Archivo", doc_type=DocType.folder)
    page = Document(
        id="missing-page",
        name="Folio 1",
        parent_id=root.id,
        doc_type=DocType.file,
        file_type=FileType.text,
        page_content="Texto.",
    )
    claim = KnowledgeClaim(
        id="claim-missing-source",
        text="Cita con fuente borrada.",
        source_document_id="deleted-source",
        source_ids=[page.id],
        claim_type=ClaimType.fact,
    )
    db.save(root)
    db.save(page)
    db.save(claim)

    with pytest.raises(ValueError, match="deleted-source"):
        list(iter_export_records(db, target_id=root.id, granularity="page"))

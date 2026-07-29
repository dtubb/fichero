from pathlib import Path

import pytest

from fichero_server.export_service import (
    export_eleventy_site,
    export_jsonl,
    export_parquet,
    export_markdown_folder,
    export_word_docx,
    iter_export_records,
)
from fichero_server.models.knowledge import ClaimType, EntityType
from fichero_server.models import DocType, Document, FileType, KnowledgeClaim, KnowledgeEntity


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


def test_export_jsonl_writes_canonical_unicode_records(db, tmp_path):
    import json

    root, _, _, _, _, _, _ = _seed_export_library(db)
    result = export_jsonl(db, tmp_path / "records", target_id=root.id)

    records = [json.loads(line) for line in (tmp_path / "records.jsonl").read_text(encoding="utf-8").splitlines()]

    assert result.output_path == str(tmp_path / "records.jsonl")
    assert result.document_count == 2
    assert result.entity_count == 2
    assert result.claim_count == 1
    assert result.bytes_written > 0
    assert [record["record_type"] for record in records] == [
        "document",
        "document",
        "entity",
        "entity",
        "claim",
    ]
    assert records[-1]["found_in_page_label"] == "1r"


def test_export_jsonl_honors_recursive_and_overwrite(db, tmp_path):
    root, _, _, _, _, _, _ = _seed_export_library(db)
    output_path = tmp_path / "records.jsonl"
    output_path.write_text("keep\n", encoding="utf-8")

    with pytest.raises(FileExistsError):
        export_jsonl(db, output_path, target_id=root.id)

    result = export_jsonl(
        db,
        output_path,
        target_id=root.id,
        recursive=False,
        overwrite=True,
    )

    assert result.document_count == 0
    assert output_path.read_text(encoding="utf-8") == ""


def test_export_parquet_writes_typed_files_and_manifest(db, tmp_path):
    import duckdb
    import json

    root, _, _, page, _, _, _ = _seed_export_library(db)
    result = export_parquet(db, tmp_path / "records", target_id=root.id)
    output_dir = tmp_path / "records"

    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    with duckdb.connect() as connection:
        documents = connection.execute(
            "SELECT document_id, page_content FROM read_parquet(?)",
            [str(output_dir / "documents.parquet")],
        ).fetchall()
        claims = connection.execute(
            "SELECT claim_id, found_in_page_label FROM read_parquet(?)",
            [str(output_dir / "claims.parquet")],
        ).fetchall()

    assert result.document_count == 2
    assert result.entity_count == 2
    assert result.claim_count == 1
    assert result.bytes_written > 0
    assert documents[0] == (page.id, page.page_content)
    assert claims == [("claim-pedro", "1r")]
    assert manifest["schema_version"] == 1
    assert manifest["files"]["documents"]["record_count"] == 2
    assert manifest["files"]["claims"]["path"] == "claims.parquet"


def test_export_parquet_uses_database_parquet_writer(db, tmp_path, monkeypatch):
    root, _, _, _, _, _, _ = _seed_export_library(db)
    calls = []
    real_export_jsonl_as_parquet = db.export_jsonl_as_parquet

    def recording_export_jsonl_as_parquet(jsonl_path, output_path, *, empty=False):
        calls.append((jsonl_path, output_path, empty))
        return real_export_jsonl_as_parquet(jsonl_path, output_path, empty=empty)

    monkeypatch.setattr(db, "export_jsonl_as_parquet", recording_export_jsonl_as_parquet)

    export_parquet(db, tmp_path / "records", target_id=root.id)

    assert len(calls) == 3
    assert {Path(output_path).name for _, output_path, _ in calls} == {
        "documents.parquet",
        "entities.parquet",
        "claims.parquet",
    }


def test_export_parquet_empty_partitions_keep_canonical_columns(db, tmp_path):
    import duckdb

    root = Document(id="empty-root", name="Empty", doc_type=DocType.folder)
    db.save(root)
    export_parquet(db, tmp_path / "empty", target_id=root.id)

    page = Document(
        id="claim-page",
        name="Folio 1",
        doc_type=DocType.file,
        file_type=FileType.text,
    )
    claim = KnowledgeClaim(
        id="claim-without-excerpt",
        text="Claim without an excerpt.",
        source_document_id=page.id,
        claim_type=ClaimType.fact,
    )
    db.save(page)
    db.save(claim)
    export_parquet(db, tmp_path / "populated", target_id=page.id)

    with duckdb.connect() as connection:
        def columns(output_dir):
            return {
                path.stem: {
                    row[0]
                    for row in connection.execute(
                        "DESCRIBE SELECT * FROM read_parquet(?)", [str(path)]
                    ).fetchall()
                }
                for path in output_dir.glob("*.parquet")
            }

        empty_columns = columns(tmp_path / "empty")
        populated_columns = columns(tmp_path / "populated")

    assert {"document_id", "page_content", "metadata"} <= empty_columns["documents"]
    assert {"entity_id", "canonical_name", "source_document_ids"} <= empty_columns["entities"]
    assert {"claim_id", "source_document_id", "source_excerpt"} <= empty_columns["claims"]
    assert empty_columns["claims"] == populated_columns["claims"]
    assert "found_in_excerpt" in populated_columns["claims"]


def test_export_parquet_honors_non_recursive_and_overwrite(db, tmp_path):
    root, _, _, _, _, _, _ = _seed_export_library(db)
    output_dir = tmp_path / "records"
    output_dir.mkdir()
    (output_dir / "keep.txt").write_text("keep", encoding="utf-8")

    with pytest.raises(FileExistsError):
        export_parquet(db, output_dir, target_id=root.id)

    result = export_parquet(
        db,
        output_dir,
        target_id=root.id,
        recursive=False,
        overwrite=True,
    )

    assert result.document_count == 0
    assert (output_dir / "keep.txt").read_text(encoding="utf-8") == "keep"


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


def test_markdown_export_aggregates_ordered_page_child_text_for_parent_document(db, tmp_path):
    parent = Document(
        id="paged-parent",
        name="Scanned book",
        doc_type=DocType.file,
        file_type=FileType.pdf,
    )
    pages = [
        Document(
            id=f"paged-{sequence}",
            name=f"Page {sequence}",
            parent_id=parent.id,
            doc_type=DocType.page,
            sequence=sequence,
            page_content=text,
        )
        for sequence, text in enumerate(("First page.", "Second page.", "Third page."), 1)
    ]
    for document in (parent, *pages):
        db.save(document)

    result = export_markdown_folder(db, tmp_path / "export", target_id=parent.id)
    markdown = next(file for file in result.files if file.document_id == parent.id)

    body = open(markdown.path, encoding="utf-8").read()
    assert body.index("First page.") < body.index("Second page.") < body.index("Third page.")
    assert "_No text content available._" not in body


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


def test_export_eleventy_site_raises_for_missing_claim_page_path(db, tmp_path):
    _, _, _, page, _, _, claim = _seed_export_library(db)

    with pytest.raises(ValueError, match=page.id):
        from fichero_server.export_service import _render_eleventy_claim_index

        _render_eleventy_claim_index(
            [
                {
                    "record_type": "claim",
                    "found_in_page_id": page.id,
                    "found_in_document_name": page.name,
                    "text": claim.text,
                }
            ],
            page_path=tmp_path / "site" / "src" / "claims" / "index.md",
            page_paths_by_id={},
            src_dir=tmp_path / "site" / "src",
        )


def test_export_eleventy_site_raises_for_missing_search_page_path(db, tmp_path):
    root = Document(id="search-root", name="Archivo", doc_type=DocType.folder)
    page = Document(
        id="search-page",
        name="Folio 1",
        parent_id=root.id,
        doc_type=DocType.file,
        file_type=FileType.text,
        page_content="Texto.",
    )
    db.save(root)
    db.save(page)

    with pytest.raises(ValueError, match=page.id):
        from fichero_server.export_service import _eleventy_search_entries

        _eleventy_search_entries(
            db=db,
            documents=[page],
            page_records=[],
            page_paths_by_id={},
            search_page=tmp_path / "site" / "src" / "search.md",
            src_dir=tmp_path / "site" / "src",
        )


def test_export_markdown_folder_raises_for_missing_declared_image_source(db, tmp_path, caplog):
    root = Document(id="image-root", name="Archivo", doc_type=DocType.folder)
    image = Document(
        id="image-doc",
        name="Photo One",
        parent_id=root.id,
        doc_type=DocType.file,
        file_type=FileType.image,
        path="files/missing.jpg",
    )
    db.save(root)
    db.save(image)

    with pytest.raises(ValueError, match=image.id):
        export_markdown_folder(db, tmp_path / "export", target_id=root.id)
    assert image.id in caplog.text


def test_export_word_docx_raises_for_missing_declared_image_source(db, tmp_path, caplog):
    root = Document(id="word-root", name="Archivo", doc_type=DocType.folder)
    image = Document(
        id="word-image-doc",
        name="Photo One",
        parent_id=root.id,
        doc_type=DocType.file,
        file_type=FileType.image,
        path="files/missing.jpg",
    )
    db.save(root)
    db.save(image)

    with pytest.raises(ValueError, match=image.id):
        export_word_docx(db, tmp_path / "export.docx", target_id=root.id)
    assert image.id in caplog.text

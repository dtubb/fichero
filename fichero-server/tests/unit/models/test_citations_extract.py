from __future__ import annotations

import asyncio

import httpx
from typer.testing import CliRunner

from fichero_cli import __main__ as cli
from fichero_cli import FicheroClient
from fichero_server.db import db_manager
from fichero_server.models.knowledge import (
    EntityResolutionRule,
    EntityResolutionRuleType,
    EntityType,
    KnowledgeClaim,
    KnowledgeEntity,
)
from fichero_server.llm import LLMConfig
from fichero_server.models import DocType, Document, FileType
from fichero_server.workflows.tools import citations_extract as cite_tool
from fichero_server.workflows.tools.citations_extract import (
    detect_inline_citations,
    extract_citations_for_document,
    find_bibliography_section,
    parse_bibliography_entry_regex,
    resolve_inline_citation,
    split_bibliography_entries,
)


def test_bibliography_section_and_entry_split():
    body, bibliography = find_bibliography_section(
        "A claim cites (Smith 1999).\n\nReferences\nSmith, John. 1999. A Book. Press.\n\nDoe, Jane. 2001. Article."
    )

    assert "Smith 1999" in body
    entries = split_bibliography_entries(bibliography)
    assert entries == [
        "Smith, John. 1999. A Book. Press.",
        "Doe, Jane. 2001. Article.",
    ]


def test_inline_citations_resolve_to_author_year_entry():
    entry = parse_bibliography_entry_regex(
        "Smith, John. 1999. A Book. Press.",
        1,
    )
    citations = detect_inline_citations([
        cite_tool.PageRecord("page-1", "This follows Smith (1999) and (Smith 1999).", "1")
    ])

    resolved = [resolve_inline_citation(citation, [entry]) for citation in citations]

    assert len(citations) == 2
    assert all(item == entry for item in resolved)


def test_extract_citations_writes_page_scoped_kg_rows(tmp_path, monkeypatch):
    package_path = tmp_path / "Lib.fichero"
    (package_path / "lance").mkdir(parents=True)
    (package_path / "storage").mkdir()
    db = db_manager.get_database(package_path)

    parent = Document(
        id="doc-book",
        name="Book.pdf",
        path="/tmp/Book.pdf",
        doc_type=DocType.file,
        file_type=FileType.pdf,
    )
    page1 = Document(
        id="page-1",
        parent_id=parent.id,
        name="Book.pdf - Page 1",
        doc_type=DocType.page,
        sequence=1,
        page_content="The argument follows Smith (1999).",
    )
    page2 = Document(
        id="page-2",
        parent_id=parent.id,
        name="Book.pdf - Page 2",
        doc_type=DocType.page,
        sequence=2,
        page_content="References\nSmith, John. 1999. A Book. Press.",
    )
    for doc in (parent, page1, page2):
        db.save(doc)

    async def fake_parse(raw_text, index, llm_config):
        return parse_bibliography_entry_regex(raw_text, index)

    monkeypatch.setattr(cite_tool, "parse_bibliography_entry", fake_parse)

    result = asyncio.run(
        extract_citations_for_document(
            db,
            parent,
            LLMConfig(provider="openrouter", model="openai/gpt-4o-mini"),
        )
    )

    assert result["entries"][0]["canonical_name"] == "Smith-1999"
    entities = db.query(KnowledgeEntity, entity_type=EntityType.citation)
    assert len(entities) == 1
    assert entities[0].canonical_name == "Smith-1999"
    assert entities[0].metadata["citation_entry"]["title"] == "A Book"

    claims = db.query(KnowledgeClaim, source_document_id=page1.id)
    assert len(claims) == 1
    assert claims[0].entity_ids == [entities[0].id]
    assert claims[0].metadata["citation_entry"]["canonical_name"] == "Smith-1999"


def test_citations_extract_preserves_selected_page_document(tmp_path, monkeypatch):
    package_path = tmp_path / "Lib.fichero"
    (package_path / "lance").mkdir(parents=True)
    (package_path / "storage").mkdir()
    db = db_manager.get_database(package_path)

    parent = Document(
        id="doc-book-page-select",
        name="Book.pdf",
        path="/tmp/Book.pdf",
        doc_type=DocType.file,
        file_type=FileType.pdf,
    )
    page1 = Document(
        id="page-selected",
        parent_id=parent.id,
        name="Book.pdf - Page 1",
        doc_type=DocType.page,
        sequence=1,
        page_content="No bibliography on this page.",
    )
    page2 = Document(
        id="page-other",
        parent_id=parent.id,
        name="Book.pdf - Page 2",
        doc_type=DocType.page,
        sequence=2,
        page_content="References\nSmith, John. 1999. A Book. Press.",
    )
    for doc in (parent, page1, page2):
        db.save(doc)

    async def fake_parse(raw_text, index, llm_config):
        return parse_bibliography_entry_regex(raw_text, index)

    monkeypatch.setattr(cite_tool, "parse_bibliography_entry", fake_parse)

    result = asyncio.run(
        cite_tool.citations_extract(
            inputs={},
            state={
                "library_path": str(package_path),
                "selected_doc_ids": [page1.id],
            },
            llm_config=LLMConfig(provider="openrouter", model="openai/gpt-4o-mini"),
        )
    )

    assert result["citations"]["entries"] == []
    assert db.query(KnowledgeClaim, source_document_id=page1.id) == []
    assert db.query(KnowledgeClaim, source_document_id=page2.id) == []


def test_extract_citations_detects_footnote_citation_lines(tmp_path, monkeypatch):
    package_path = tmp_path / "Lib.fichero"
    (package_path / "lance").mkdir(parents=True)
    (package_path / "storage").mkdir()
    db = db_manager.get_database(package_path)

    parent = Document(
        id="doc-book-footnote",
        name="Book.pdf",
        path="/tmp/Book.pdf",
        doc_type=DocType.file,
        file_type=FileType.pdf,
    )
    page1 = Document(
        id="page-foot-1",
        parent_id=parent.id,
        name="Book.pdf - Page 1",
        doc_type=DocType.page,
        sequence=1,
        page_content="Claim in body.\n\n1 Smith, John. 1999. A Book. Press.",
    )
    page2 = Document(
        id="page-foot-2",
        parent_id=parent.id,
        name="Book.pdf - Page 2",
        doc_type=DocType.page,
        sequence=2,
        page_content="References\n1. Smith, John. 1999. A Book. Press.",
    )
    for doc in (parent, page1, page2):
        db.save(doc)

    async def fake_parse(raw_text, index, llm_config):
        return parse_bibliography_entry_regex(raw_text, index)

    monkeypatch.setattr(cite_tool, "parse_bibliography_entry", fake_parse)

    asyncio.run(
        extract_citations_for_document(
            db,
            parent,
            LLMConfig(provider="openrouter", model="openai/gpt-4o-mini"),
        )
    )

    claims = db.query(KnowledgeClaim, source_document_id=page1.id)
    assert len(claims) == 1
    assert claims[0].source_excerpt.startswith("1 Smith")


def test_extract_citations_skips_suppressed_citation_entity(tmp_path, monkeypatch):
    package_path = tmp_path / "Lib.fichero"
    (package_path / "lance").mkdir(parents=True)
    (package_path / "storage").mkdir()
    db = db_manager.get_database(package_path)

    parent = Document(
        id="doc-book-suppress",
        name="Book.pdf",
        path="/tmp/Book.pdf",
        doc_type=DocType.file,
        file_type=FileType.pdf,
    )
    page1 = Document(
        id="page-suppress-1",
        parent_id=parent.id,
        name="Book.pdf - Page 1",
        doc_type=DocType.page,
        sequence=1,
        page_content="The argument follows Smith (1999).",
    )
    page2 = Document(
        id="page-suppress-2",
        parent_id=parent.id,
        name="Book.pdf - Page 2",
        doc_type=DocType.page,
        sequence=2,
        page_content="References\nSmith, John. 1999. A Book. Press.",
    )
    for doc in (parent, page1, page2):
        db.save(doc)
    db.save(
        EntityResolutionRule(
            rule_type=EntityResolutionRuleType.suppress,
            match_canonical_name="Smith-1999",
            match_entity_type=EntityType.citation,
            reason="known bad citation entity",
        )
    )

    async def fake_parse(raw_text, index, llm_config):
        return parse_bibliography_entry_regex(raw_text, index)

    monkeypatch.setattr(cite_tool, "parse_bibliography_entry", fake_parse)

    result = asyncio.run(
        extract_citations_for_document(
            db,
            parent,
            LLMConfig(provider="openrouter", model="openai/gpt-4o-mini"),
        )
    )

    assert result["claims"] == []
    assert db.query(KnowledgeEntity, entity_type=EntityType.citation) == []
    assert db.query(KnowledgeClaim, source_document_id=page1.id) == []


def test_citations_extract_workflow_uses_selected_document(tmp_path, monkeypatch):
    package_path = tmp_path / "Lib.fichero"
    (package_path / "lance").mkdir(parents=True)
    (package_path / "storage").mkdir()
    db = db_manager.get_database(package_path)
    doc = Document(
        id="doc-1",
        name="Article.txt",
        doc_type=DocType.file,
        page_content=(
            "As shown by (Doe 2001).\n\n"
            "Bibliography\nDoe, Jane. 2001. An Article. Journal."
        ),
    )
    db.save(doc)

    async def fake_parse(raw_text, index, llm_config):
        return parse_bibliography_entry_regex(raw_text, index)

    monkeypatch.setattr(cite_tool, "parse_bibliography_entry", fake_parse)

    result = asyncio.run(
        cite_tool.citations_extract(
            inputs={},
            state={"library_path": str(package_path), "selected_doc_ids": [doc.id]},
            llm_config=LLMConfig(provider="openrouter", model="openai/gpt-4o-mini"),
        )
    )

    assert result["citations"]["entries"][0]["canonical_name"] == "Doe-2001"
    assert "1 resolved inline citations" in result["text"]


def test_client_citations_at_doc_filters_citation_entities():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/claims":
            return httpx.Response(
                200,
                json=[
                    {
                        "id": "claim-1",
                        "text": "Doc cites Smith-1999",
                        "source_document_id": "doc-1",
                        "entity_ids": ["entity-citation"],
                    }
                ],
            )
        if request.url.path == "/api/documents":
            return httpx.Response(200, json={"items": []})
        if request.url.path == "/api/entities/entity-citation":
            return httpx.Response(
                200,
                json={
                    "id": "entity-citation",
                    "canonical_name": "Smith-1999",
                    "entity_type": "citation",
                },
            )
        return httpx.Response(404, text="missing")

    client = FicheroClient(
        base_url="http://test",
        token="token",
        library_path="/tmp/Lib.fichero",
        transport=httpx.MockTransport(handler),
    )

    citations = client.citations_at_doc("doc-1")

    assert [entity.canonical_name for entity in citations] == ["Smith-1999"]


def test_kg_citations_command_uses_client(monkeypatch):
    class FakeClient:
        calls: list[tuple[str, str]] = []

        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

        def citations_at_doc(self, doc_id: str):
            self.calls.append(("citations_at_doc", doc_id))
            return [{"canonical_name": "Smith-1999", "entity_type": "citation"}]

    monkeypatch.setattr(cli, "FicheroClient", FakeClient)

    result = CliRunner().invoke(cli.app, ["kg", "citations", "doc-1"])

    assert result.exit_code == 0
    assert FakeClient.calls == [("citations_at_doc", "doc-1")]

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import fitz
import httpx
from typer.testing import CliRunner

from fichero_server import __main__ as cli
from fichero_server.cli import FicheroClient
from fichero_server.db import db_manager
from fichero_server.llm import LLMConfig
from fichero_server.models import DocType, Document, FileType
from fichero_server.workflows.tools.split_chapters import (
    ChapterRange,
    PdfPageText,
    _heading_starts_from_pages,
    detect_chapter_ranges,
    split_chapters,
    split_pdf_into_chapter_documents,
)


def test_detect_chapter_ranges_uses_pdf_outline(tmp_path: Path):
    pdf_path = tmp_path / "book.pdf"
    _write_pdf(
        pdf_path,
        pages=[
            ("Chapter 1", "Opening text"),
            ("Body", "More text"),
            ("Chapter 2", "Second text"),
            ("Body", "The end"),
        ],
        toc=[[1, "Chapter 1", 1], [1, "Chapter 2", 3]],
    )

    ranges = detect_chapter_ranges(pdf_path)

    assert ranges == [
        ChapterRange("Chapter 1", 1, 2, "outline"),
        ChapterRange("Chapter 2", 3, 4, "outline"),
    ]


def test_heading_heuristic_detects_chapter_and_roman_starts():
    pages = [
        PdfPageText(1, "preface", ("Preface",)),
        PdfPageText(2, "one", ("CHAPTER I", "The Beginning")),
        PdfPageText(3, "body", ("Body text",)),
        PdfPageText(4, "two", ("II", "The Next Part")),
    ]

    starts = _heading_starts_from_pages(pages)

    assert starts == [("CHAPTER I", 2, "heading"), ("II", 4, "heading")]


def test_split_pdf_into_chapter_documents_persists_and_replaces(tmp_path: Path):
    package_path = tmp_path / "book.fichero"
    (package_path / "lance").mkdir(parents=True)
    (package_path / "storage").mkdir()
    db = db_manager.get_database(package_path)

    pdf_path = tmp_path / "source.pdf"
    _write_pdf(
        pdf_path,
        pages=[
            ("Chapter 1", "Opening text"),
            ("Body", "More text"),
            ("Chapter 2", "Second text"),
        ],
        toc=[[1, "Chapter 1", 1], [1, "Chapter 2", 3]],
    )
    source_doc = Document(
        id="book-doc",
        name="source.pdf",
        path=str(pdf_path),
        doc_type=DocType.file,
        file_type=FileType.pdf,
    )
    db.save(source_doc)

    chapters = split_pdf_into_chapter_documents(db, source_doc)

    assert [doc.name for doc in chapters] == [
        "source.pdf - Chapter 1",
        "source.pdf - Chapter 2",
    ]
    assert chapters[0].doc_type == DocType.group
    assert chapters[0].parent_id == source_doc.id
    assert chapters[0].metadata["page_range"] == {"start": 1, "end": 2}
    assert chapters[0].metadata["basis"] == "outline"
    assert "Opening text" in (chapters[0].page_content or "")

    repeat = split_pdf_into_chapter_documents(db, source_doc)
    children = [
        doc
        for doc in db.query(Document, parent_id=source_doc.id)
        if doc.metadata.get("split_chapters_tool")
    ]
    assert len(repeat) == 2
    assert len(children) == 2


def test_split_chapters_workflow_tool_persists_from_selected_doc(tmp_path: Path):
    package_path = tmp_path / "book.fichero"
    (package_path / "lance").mkdir(parents=True)
    (package_path / "storage").mkdir()
    db = db_manager.get_database(package_path)

    pdf_path = tmp_path / "source.pdf"
    _write_pdf(
        pdf_path,
        pages=[("Chapter 1", "A"), ("Chapter 2", "B")],
        toc=[[1, "Chapter 1", 1], [1, "Chapter 2", 2]],
    )
    source_doc = Document(
        id="book-doc",
        name="source.pdf",
        path=str(pdf_path),
        doc_type=DocType.file,
        file_type=FileType.pdf,
    )
    db.save(source_doc)

    result = asyncio.run(
        split_chapters(
            inputs={},
            state={"library_path": str(package_path), "selected_doc_ids": ["book-doc"]},
            llm_config=LLMConfig(provider="openai", model="gpt-4o"),
        )
    )

    assert result["count"] == 2
    assert "source.pdf - Chapter 1" in result["text"]
    assert len(db.query(Document, parent_id=source_doc.id)) == 2


def test_client_split_chapters_runs_default_workflow():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path == "/api/workflows":
            return httpx.Response(
                200,
                json={"items": [{"id": "wf-split", "name": "Split Chapters"}]},
            )
        payload = json.loads(request.content)
        assert payload["workflow_id"] == "wf-split"
        assert payload["inputs"] == {"selected_doc_ids": ["doc-1"]}
        return httpx.Response(
            202,
            json={
                "thread_id": "thread-1",
                "workflow_id": "wf-split",
                "workflow_name": "Split Chapters",
                "status": "accepted",
                "stream_url": "/stream/thread-1",
            },
        )

    client = FicheroClient(
        base_url="http://test",
        token="token",
        library_path="/tmp/Lib.fichero",
        transport=httpx.MockTransport(handler),
    )
    result = client.split_chapters("doc-1")

    assert result.thread_id == "thread-1"
    assert [request.url.path for request in seen] == [
        "/api/workflows",
        "/api/workflow-execution/execute",
    ]


def test_docs_split_chapters_command_uses_client(monkeypatch):
    class FakeClient:
        calls: list[tuple[str, str]] = []

        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

        def split_chapters(self, doc_id: str) -> dict[str, str]:
            self.calls.append(("split_chapters", doc_id))
            return {"thread_id": "thread-1", "status": "accepted"}

    monkeypatch.setattr(cli, "FicheroClient", FakeClient)
    result = CliRunner().invoke(cli.app, ["docs", "split-chapters", "doc-1"])

    assert result.exit_code == 0
    assert FakeClient.calls == [("split_chapters", "doc-1")]


def _write_pdf(
    path: Path,
    *,
    pages: list[tuple[str, str]],
    toc: list[list[object]] | None = None,
) -> None:
    doc = fitz.open()
    for heading, body in pages:
        page = doc.new_page()
        page.insert_text((72, 72), heading, fontsize=20)
        page.insert_text((72, 110), body, fontsize=11)
    if toc:
        doc.set_toc(toc)
    doc.save(path)
    doc.close()

from __future__ import annotations

import asyncio
from pathlib import Path

import fitz

from fichero.db import db_manager
from fichero.knowledge_models import BookStructureNode
from fichero.llm import LLMConfig
from fichero.models import DocType, Document
from fichero.workflows.tools.book_structure import (
    book_structure,
    extract_book_structure_from_pdf,
    render_book_structure_markdown,
)


def test_extract_book_structure_from_pdf_builds_hierarchy(tmp_path: Path):
    pdf_path = tmp_path / "book.pdf"
    _write_pdf_with_toc(
        pdf_path,
        toc=[
            [1, "Chapter 1", 1],
            [2, "Section 1.1", 2],
            [3, "Subsection 1.1.1", 3],
            [2, "Section 1.2", 4],
            [1, "Chapter 2", 5],
        ],
        page_count=6,
        page_label_prefix="Front ",
    )

    nodes = extract_book_structure_from_pdf(pdf_path, source_document_id="book-doc")
    assert [node.title for node in nodes] == [
        "Chapter 1",
        "Section 1.1",
        "Subsection 1.1.1",
        "Section 1.2",
        "Chapter 2",
    ]

    chapter_1, section_1_1, subsection_1_1_1, section_1_2, chapter_2 = nodes
    assert chapter_1.level == 1
    assert chapter_1.kind == "chapter"
    assert chapter_1.start_sequence == 1
    assert chapter_1.end_sequence == 4
    assert chapter_1.parent_structure_id is None
    assert chapter_1.source_page_label == "Front 1"
    assert section_1_1.level == 2
    assert section_1_1.parent_structure_id == chapter_1.id
    assert section_1_1.start_sequence == 2
    assert section_1_1.end_sequence == 3
    assert subsection_1_1_1.level == 3
    assert subsection_1_1_1.parent_structure_id == section_1_1.id
    assert subsection_1_1_1.start_sequence == 3
    assert subsection_1_1_1.end_sequence == 3
    assert section_1_2.parent_structure_id == chapter_1.id
    assert section_1_2.start_sequence == 4
    assert section_1_2.end_sequence == 4
    assert chapter_2.level == 1
    assert chapter_2.start_sequence == 5
    assert chapter_2.end_sequence == 6

    markdown = render_book_structure_markdown(nodes)
    assert "Chapter: Chapter 1 (1-4)" in markdown
    assert "  - Section: Section 1.1 (2-3)" in markdown


def test_book_structure_tool_persists_nodes(tmp_path: Path):
    package_path = tmp_path / "book.fichero"
    (package_path / "lance").mkdir(parents=True)
    (package_path / "storage").mkdir()
    db = db_manager.get_database(package_path)

    pdf_path = tmp_path / "source.pdf"
    _write_pdf_with_toc(
        pdf_path,
        toc=[
            [1, "Chapter 1", 1],
            [2, "Section 1.1", 2],
            [1, "Chapter 2", 5],
        ],
        page_count=6,
    )

    source_doc = Document(
        id="book-doc",
        name="source.pdf",
        path=str(pdf_path),
        doc_type=DocType.file,
    )
    db.save(source_doc)

    result = asyncio.run(
        book_structure(
            inputs={},
            state={
                "library_path": str(package_path),
                "selected_doc_ids": [source_doc.id],
            },
            llm_config=LLMConfig(provider="openai", model="gpt-4o"),
        )
    )

    assert "Chapter 1" in result["text"]
    assert len(result["value"]) == 3

    rows = sorted(
        db.query(BookStructureNode, source_document_id=source_doc.id),
        key=lambda node: (node.start_sequence, node.level),
    )
    assert [row.title for row in rows] == ["Chapter 1", "Section 1.1", "Chapter 2"]
    assert rows[0].end_sequence == 4
    assert rows[1].parent_structure_id == rows[0].id
    assert rows[2].start_sequence == 5

    repeat = asyncio.run(
        book_structure(
            inputs={},
            state={
                "library_path": str(package_path),
                "selected_doc_ids": [source_doc.id],
            },
            llm_config=LLMConfig(provider="openai", model="gpt-4o"),
        )
    )
    assert "Chapter 1" in repeat["text"]
    assert len(db.query(BookStructureNode, source_document_id=source_doc.id)) == 3


def _write_pdf_with_toc(
    path: Path,
    *,
    toc: list[list[object]],
    page_count: int,
    page_label_prefix: str | None = None,
) -> None:
    doc = fitz.open()
    for _ in range(page_count):
        doc.new_page()
    if page_label_prefix is not None:
        doc.set_page_labels(
            [
                {
                    "startpage": 0,
                    "prefix": page_label_prefix,
                    "style": "D",
                    "firstpagenum": 1,
                }
            ]
        )
    doc.set_toc(toc)
    doc.save(path)
    doc.close()

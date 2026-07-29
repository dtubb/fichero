from __future__ import annotations

import pytest

from fichero_server.models.knowledge import KnowledgeClaim
from fichero_server.llm import LLMConfig
from fichero_server.models import DocType, Document
from fichero_server.workflows.tools import citations_extract as citations_module


@pytest.mark.asyncio
async def test_citations_extract_dedupes_numeric_and_footnote_hits(db, monkeypatch):
    source = Document(name="Essay", doc_type=DocType.file)
    page = Document(
        name="Essay p1",
        doc_type=DocType.page,
        parent_id=source.id,
        sequence=1,
        page_content=(
            "This argument is discussed [1].\n"
            "1 Doe, Jane. 1999. The Cited Work.\n\n"
            "References\n"
            "[1] Doe, Jane. 1999. The Cited Work."
        ),
    )
    db.save(source)
    db.save(page)

    class _Parsed:
        def __init__(self):
            self.authors = ["Doe, Jane"]
            self.year = "1999"
            self.title = "The Cited Work"
            self.journal_or_publisher = ""
            self.doi = ""
            self.url = ""

    async def _fake_parse(*args, **kwargs):
        return _Parsed()

    monkeypatch.setattr(
        citations_module,
        "chat_structured_with_fallback",
        _fake_parse,
    )

    result = await citations_module.extract_citations_for_document(
        db,
        source,
        LLMConfig(provider="openai", model="gpt-4o-mini"),
    )

    assert len(result["claims"]) == 1
    claims = db.query(KnowledgeClaim, source_document_id=page.id)
    assert len(claims) == 1

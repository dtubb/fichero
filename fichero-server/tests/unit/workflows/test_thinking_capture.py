"""Per-node thinking capture (Daniel, 2026-08-11).

A thinking model's reasoning used to be parsed, logged truncated, and
discarded — a run could not be investigated afterwards. Now each page's
thinking rides that page's artifact data under "thinking".
"""

import pytest

from fichero_server.llm import LLMConfig
from fichero_server.models import Artifact, Document, DocType
from fichero_server.workflows.tools.vision_base import _propagate_to_page_children


@pytest.fixture
def pdf_with_pages(db):
    parent = Document(name="book.pdf", doc_type=DocType.file)
    db.save(parent)
    for i in (1, 2):
        db.save(
            Document(
                parent_id=parent.id,
                doc_type=DocType.page,
                name=f"book.pdf - Page {i}",
                sequence=i,
            )
        )
    return parent


class TestThinkingRidesThePageArtifact:
    @pytest.mark.asyncio
    async def test_per_page_thinking_lands_on_each_artifact(
        self, db, pdf_with_pages, test_package
    ):
        ids = await _propagate_to_page_children(
            pdf_with_pages.id,
            ["page one text", "page two text"],
            str(test_package),
            artifact_type="transcription",
            llm_config=LLMConfig(provider="hf", model="think-1"),
            page_thinking=["reasoning for page 1", None],
        )
        assert ids, "propagation produced no artifacts"

        pages = sorted(
            db.query(Document, parent_id=pdf_with_pages.id),
            key=lambda d: d.sequence or 0,
        )
        arts_p1 = db.query(Artifact, document_id=pages[0].id)
        arts_p2 = db.query(Artifact, document_id=pages[1].id)
        assert arts_p1 and arts_p2

        assert (arts_p1[0].data or {}).get("thinking") == "reasoning for page 1"
        # A page with no thinking must not inherit its sibling's.
        assert (arts_p2[0].data or {}).get("thinking") is None

    @pytest.mark.asyncio
    async def test_no_thinking_leaves_data_untouched(
        self, db, pdf_with_pages, test_package
    ):
        await _propagate_to_page_children(
            pdf_with_pages.id,
            ["text a", "text b"],
            str(test_package),
            artifact_type="transcription",
            llm_config=LLMConfig(provider="hf", model="plain-1"),
            artifact_data={"target_format": "text"},
        )
        pages = db.query(Document, parent_id=pdf_with_pages.id)
        for page in pages:
            for art in db.query(Artifact, document_id=page.id):
                assert "thinking" not in (art.data or {})
                assert (art.data or {}).get("target_format") == "text"

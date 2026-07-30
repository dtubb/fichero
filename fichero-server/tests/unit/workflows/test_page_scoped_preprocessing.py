"""Page-scoped preprocessing regression tests (#4298, reopened).

A page-scoped run pairs each file path with the page document whose
``sequence`` confines the work to that ONE page. The preprocessing tools that
sit UPSTREAM of the vision tools (``zoom``, ``prepare_images``) must honor
that pairing — and recover it from the upstream node's recorded outputs when
a stored graph wires only the ``files`` port (older stored preset copies, the
#2523 backstop class). Before this fix, a single-page selection through the
stale stored paleography-ensemble graph tiled and transcribed EVERY page of
the parent PDF.
"""

from __future__ import annotations

import pytest
from fichero_server.llm import LLMConfig
from fichero_server.workflows.tools.prepare_images import prepare_images
from fichero_server.workflows.tools.zoom import zoom

LLM = LLMConfig(provider="test", model="test")


@pytest.fixture()
def three_page_pdf(tmp_path):
    """A tiny 3-page PDF written on the spot."""
    import fitz

    path = tmp_path / "three_pages.pdf"
    doc = fitz.open()
    for index in range(3):
        page = doc.new_page(width=120, height=160)
        page.insert_text((20, 40), f"page {index + 1}")
    doc.save(path)
    doc.close()
    return path


def _page_doc(sequence: int) -> dict:
    return {"id": f"page-{sequence}", "doc_type": "page", "sequence": sequence, "parent_id": "pdf-1"}


class TestZoomPageScoping:
    @pytest.mark.asyncio
    async def test_wired_documents_confine_to_one_page(self, three_page_pdf, tmp_path):
        result = await zoom(
            {
                "files": [str(three_page_pdf)],
                "documents": [_page_doc(2)],
                "rows": 2,
                "output_dir": str(tmp_path / "out"),
            },
            {},
            LLM,
        )
        assert result["error"] is None
        assert len(result["files"]) == 2  # 2 tiles of ONE page, not 6 of three
        assert all(".page-002." in path for path in result["files"])

    @pytest.mark.asyncio
    async def test_unwired_documents_recovered_from_state_outputs(self, three_page_pdf, tmp_path):
        """Stale stored graph: only the files port is wired — the pairing is
        recovered from the source node's recorded outputs, so the run stays
        page-scoped instead of widening to the whole PDF (#4298)."""
        state = {
            "outputs": {
                "files-source": {
                    "files": [str(three_page_pdf)],
                    "documents": [_page_doc(3)],
                }
            }
        }
        result = await zoom(
            {"files": [str(three_page_pdf)], "rows": 2, "output_dir": str(tmp_path / "out")},
            state,
            LLM,
        )
        assert result["error"] is None
        assert len(result["files"]) == 2
        assert all(".page-003." in path for path in result["files"])
        # The recovered pairing is re-emitted so downstream vision tools stay
        # page-scoped too.
        assert result["documents"] == [_page_doc(3), _page_doc(3)]

    @pytest.mark.asyncio
    async def test_whole_pdf_selection_still_processes_every_page(self, three_page_pdf, tmp_path):
        """No pairing anywhere = the user genuinely targeted the whole file."""
        result = await zoom(
            {"files": [str(three_page_pdf)], "rows": 2, "output_dir": str(tmp_path / "out")},
            {"outputs": {}},
            LLM,
        )
        assert result["error"] is None
        assert len(result["files"]) == 6  # 3 pages x 2 tiles


class TestPrepareImagesPageScoping:
    @pytest.mark.asyncio
    async def test_wired_documents_confine_to_one_page(self, three_page_pdf, tmp_path):
        result = await prepare_images(
            {
                "files": [str(three_page_pdf)],
                "documents": [_page_doc(2)],
                "output_dir": str(tmp_path / "out"),
            },
            {},
            LLM,
        )
        assert result["error"] is None
        assert len(result["output_files"]) == 1
        assert "_page_002" in result["output_files"][0]
        # Pairing survives downstream, index-aligned with the outputs.
        assert result["documents"] == [_page_doc(2)]

    @pytest.mark.asyncio
    async def test_unwired_documents_recovered_from_state_outputs(self, three_page_pdf, tmp_path):
        state = {
            "outputs": {
                "files-source": {
                    "files": [str(three_page_pdf)],
                    "documents": [_page_doc(1)],
                }
            }
        }
        result = await prepare_images(
            {"files": [str(three_page_pdf)], "output_dir": str(tmp_path / "out")},
            state,
            LLM,
        )
        assert result["error"] is None
        assert len(result["output_files"]) == 1
        assert "_page_001" in result["output_files"][0]

    @pytest.mark.asyncio
    async def test_whole_pdf_selection_still_processes_every_page(self, three_page_pdf, tmp_path):
        result = await prepare_images(
            {"files": [str(three_page_pdf)], "output_dir": str(tmp_path / "out")},
            {"outputs": {}},
            LLM,
        )
        assert result["error"] is None
        assert len(result["output_files"]) == 3

    @pytest.mark.asyncio
    async def test_out_of_range_page_is_an_error_not_a_widen(self, three_page_pdf, tmp_path):
        """A stale sequence must fail loudly, never silently process every
        page (prefer-raise-over-silent-fallback)."""
        result = await prepare_images(
            {
                "files": [str(three_page_pdf)],
                "documents": [_page_doc(99)],
                "output_dir": str(tmp_path / "out"),
            },
            {},
            LLM,
        )
        assert result["output_files"] == []
        assert "not found" in (result["error"] or "")

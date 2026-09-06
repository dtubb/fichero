"""Fresh SVO extraction anchors claims to their PAGE, not the whole document.

Legacy catalogue-imported claims were doc-level (source_page_label=[]) — that is
data, not fixable retroactively. But going forward, click-a-claim → jump-to-page
needs a real target: a multi-page document's page-1 claims must carry page 1 and
page-2 claims page 2. The capability is real (files_tool expands a parent PDF to
one work unit per page child; extract_svo_only stamps page_label per page). This
guards that it stays that way and does not collapse to doc-level.
"""

from __future__ import annotations

import pytest

from tests.integration._seedlib import seed

from fichero_server.db import db_manager
from fichero_server.llm import LLMConfig
from fichero_server.models import DocType, Document, FileType
from fichero_server.models.knowledge import EntityType, KnowledgeEntity
from fichero_server.workflows.runtime import build_initial_state
import fichero_server.workflows.tools  # noqa: F401  (registers tools)
import fichero_server.workflows.tools.extract_svo_only as svo


def _seed_two_pages(tmp_path):
    library_path = tmp_path / "page-anchor.fichero"
    seed(library_path)
    db = db_manager.get_database(library_path)

    source = tmp_path / "src.pdf"
    source.write_bytes(b"%PDF-1.4\n")
    parent = Document(
        id="pa-root",
        name="root",
        path=str(source),
        doc_type=DocType.file,
        file_type=FileType.pdf,
        metadata={"canonical_external_id": "pa-root"},
    )
    db.save(parent)
    pages = []
    for n in (1, 2):
        page = Document(
            id=f"pa-page-{n}",
            parent_id=parent.id,
            name=f"page {n}",
            doc_type=DocType.page,
            sequence=n,
            page_content=f"Juan{n} firmó la escritura en la página {n}.",
            metadata={
                "page_number": n,
                "transcription": f"Juan{n} firmó la escritura en la página {n}.",
            },
        )
        db.save(page)
        pages.append(page)
        # One person entity per page, anchored to that page.
        db.save(
            KnowledgeEntity(
                id=f"pa-ent-{n}",
                canonical_name=f"Juan{n}",
                entity_type=EntityType.person,
                source_document_ids=[f"pa-page-{n}"],
            )
        )
    return library_path, pages


@pytest.mark.asyncio
async def test_multipage_claims_carry_their_own_page_label(tmp_path, monkeypatch):
    library_path, pages = _seed_two_pages(tmp_path)

    async def fake_claims(*args, **kwargs):
        return [{"verb": "firmó"}]

    # Keep the write path reachable without depending on claim/item internals —
    # what matters here is WHICH page_label reaches _write_kg_rows per document.
    monkeypatch.setattr(svo, "_extract_claims_for_entity", fake_claims)
    monkeypatch.setattr(
        svo, "_build_entity_items_for_section", lambda entity, section_key, claims: [{"i": 1}]
    )
    captured: list[tuple[str, str | None]] = []

    def fake_write(db, section, items, doc_id, *, page_label=None, **kwargs):
        captured.append((doc_id, page_label))

    monkeypatch.setattr(svo, "_write_kg_rows", fake_write)

    state = build_initial_state(
        {"selected_doc_ids": ["pa-page-1", "pa-page-2"]}, library_path=str(library_path)
    )
    await svo.extract_svo_only(
        {
            "documents": [{"id": "pa-page-1"}, {"id": "pa-page-2"}],
            "entity_types": "people",
        },
        state,
        LLMConfig(provider="mock", model="mock"),
    )

    labels = dict(captured)
    # Each page's claims are stamped with THAT page's label — not doc-level.
    assert labels["pa-page-1"] == "1"
    assert labels["pa-page-2"] == "2"
    assert labels["pa-page-1"] != labels["pa-page-2"]


def test_files_tool_expands_a_parent_pdf_to_one_unit_per_page(tmp_path):
    # The gate for page-anchoring: the source node must hand extraction the PAGE
    # children (each its own doc_id), not the parent as one blob.
    from fichero_server.workflows.tools.sources import _resolve_selection_pairs

    library_path, pages = _seed_two_pages(tmp_path)
    db = db_manager.get_database(library_path)

    pairs = _resolve_selection_pairs(db, ["pa-root"], str(library_path))
    resolved_ids = [doc.id for _path, doc in pairs]
    assert resolved_ids == ["pa-page-1", "pa-page-2"]

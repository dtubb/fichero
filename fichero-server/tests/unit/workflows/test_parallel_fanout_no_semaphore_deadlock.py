"""The parallel fan-out must not deadlock on its own concurrency semaphore.

#4553 — running Transcribe on ONE 10-page PDF started ten `[PARALLEL] [n/10]`
branches and then emitted nothing at all: no node output, no error, no terminal
event. The cause was two layers acquiring the SAME non-reentrant module-global
semaphore:

    builder._make_parallel_node_function:  async with _get_vision_semaphore()
    vision_base.process_vision._run_one:   async with _get_vision_semaphore()

With ``VISION_FAN_OUT_CONCURRENCY == 4``, the first four branches took the last
four permits and then blocked forever on their own inner acquire, while the
remaining branches blocked on the outer one. Nothing was ever released. A
fan-out of 1-3 files never reached the cap, which is why the defect survived —
a 3-page PDF worked, a 10-page PDF hung.

These tests go RED against the pre-#4553 code: the first hangs (guarded by
``asyncio.wait_for``, so it fails as a TimeoutError rather than wedging the
suite), the second proves each branch still renders ITS OWN page.
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from fichero_server.models import DocType, Document, FileType, Status
from fichero_server.workflows.builder import VISION_FAN_OUT_CONCURRENCY, build_graph
from fichero_server.workflows.types import WorkflowDef


# One more page than the cap is the minimum that deadlocks; use a comfortable
# margin so the test still means something if the cap is raised.
PAGE_COUNT = VISION_FAN_OUT_CONCURRENCY * 2 + 2


@pytest.fixture(autouse=True)
def _fresh_vision_semaphore():
    """Rebind the lazily-created module-global semaphore per test loop."""
    import fichero_server.workflows.builder as _b

    _b._vision_fan_out_sem = None
    yield
    _b._vision_fan_out_sem = None


def _fan_out_workflow() -> WorkflowDef:
    """A minimal files-source -> transcribe graph (the shape every transcribe
    preset has: a SOURCE_TOOL wired into a PARALLEL_TOOL, which is what makes
    the builder create per-file Send branches)."""
    return WorkflowDef(
        id="wf-4553",
        name="fanout",
        provider="openai",
        model="gpt-4o",
        nodes=[
            {"id": "files-source", "tool": "files", "label": "Files", "config": {}},
            {
                "id": "transcribe",
                "tool": "transcribe",
                "label": "Transcribe",
                "config": {"vision_mode": "llm", "save_to_db": False},
            },
        ],
        edges=[
            {
                "id": "e-files",
                "source": "files-source",
                "target": "transcribe",
                "source_port": "files",
                "target_port": "files",
            },
            {
                "id": "e-docs",
                "source": "files-source",
                "target": "transcribe",
                "source_port": "documents",
                "target_port": "documents",
            },
        ],
    )


def _library(tmp_path: Path) -> tuple[str, str, MagicMock]:
    """A fake library holding one parent PDF with PAGE_COUNT page children."""
    library_path = str(tmp_path)
    pdf_path = tmp_path / "files" / "fi" / "scan.pdf"
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    pdf_path.write_bytes(b"%PDF-1.4 stub")

    parent = Document(
        id="pdf-1",
        name="scan.pdf",
        doc_type=DocType.file,
        file_type=FileType.pdf,
        path=str(pdf_path),
        status=Status.completed,
        metadata={},
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )
    pages = [
        Document(
            id=f"page-{i}",
            name=f"scan.pdf - Page {i}",
            doc_type=DocType.page,
            parent_id="pdf-1",
            sequence=i,
            page_content=None,
            status=Status.completed,
            metadata={
                "pdf_parent_id": "pdf-1",
                "pdf_path": str(pdf_path),
                "page_number": i,
                "text_extracted": False,
                "text_length": 0,
            },
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        for i in range(1, PAGE_COUNT + 1)
    ]

    by_id = {d.id: d for d in [parent, *pages]}
    db = MagicMock()
    db.get.side_effect = lambda model, doc_id: by_id.get(str(doc_id))
    db.query.side_effect = lambda model, **kw: (
        pages if kw.get("parent_id") == "pdf-1" else []
    )
    db.query_in.side_effect = lambda *a, **k: []
    return library_path, str(pdf_path), db


async def _drive_graph(tmp_path: Path, vision) -> None:
    """Run the real files-source -> transcribe graph with ``vision`` stubbed."""
    library_path, _pdf, db = _library(tmp_path)

    graph = build_graph(_fan_out_workflow(), skip_cache=True)
    state = {
        "selected_doc_ids": ["pdf-1"],
        "library_path": library_path,
        "task_id": "run-4553",
        "workflow_id": "wf-4553",
        "input_files": [],
        "outputs": {},
        "completed_nodes": [],
    }

    with (
        patch(
            "fichero_server.workflows.tools.sources.db_manager.get_database",
            return_value=db,
        ),
        patch("fichero_server.db.db_manager.get_database", return_value=db),
        patch(
            "fichero_server.workflows.tools.vision_base._try_pdf_text_layer",
            return_value=None,
        ),
        patch(
            "fichero_server.workflows.tools.vision_base._pdf_page_to_data_uri",
            side_effect=lambda path, page_index=0, **kw: f"PAGE{page_index}",
        ),
        patch("fichero_server.llm.vision", new=vision),
    ):
        await asyncio.wait_for(graph.ainvoke(state), timeout=60)


async def _run_fan_out(tmp_path: Path) -> list[str]:
    """Run the graph to completion; return the rendered page URIs, in call order.

    Raises ``asyncio.TimeoutError`` if the run deadlocks (the #4553 symptom).
    """
    rendered: list[str] = []

    async def _vision(images, prompt, config, *, language=None, **kwargs):
        rendered.append(images[0])
        return f"text for {images[0]}"

    await _drive_graph(tmp_path, _vision)
    return rendered


@pytest.mark.asyncio
async def test_fan_out_wider_than_the_cap_reaches_a_terminal_event(tmp_path):
    """#4553: a fan-out wider than VISION_FAN_OUT_CONCURRENCY must finish.

    RED before the fix: every branch blocks on the semaphore it already holds,
    no vision call is ever made and ``ainvoke`` never returns — this fails as a
    TimeoutError with zero recorded calls.
    """
    rendered = await _run_fan_out(tmp_path)

    assert len(rendered) == PAGE_COUNT, (
        f"expected one vision call per page ({PAGE_COUNT}), got {len(rendered)}"
    )


@pytest.mark.asyncio
async def test_each_fan_out_branch_renders_its_own_page(tmp_path):
    """Per-page identity survives the fan-out: N branches, N DISTINCT pages.

    All N branches carry the SAME parent-PDF path by design
    (``_resolve_selection_pairs``); the page identity travels in the paired
    document's ``sequence``. This asserts the rendered page indices are
    0..N-1 exactly once each — no page processed twice, none skipped, and no
    branch falling back to the whole-PDF path.
    """
    rendered = await _run_fan_out(tmp_path)

    assert sorted(rendered) == sorted(f"PAGE{i}" for i in range(PAGE_COUNT))


@pytest.mark.asyncio
async def test_fan_out_still_caps_in_flight_vision_calls(tmp_path):
    """Making the slot re-entrant must not make it UNLIMITED.

    The semaphore exists to stop a wide fan-out holding every page's image
    bytes and LLM buffers at once. A re-entrancy fix that accidentally let
    every branch through would trade a deadlock for an OOM on a large batch —
    and would pass every other test in this file, because they only assert
    that work completes.

    Measures the real graph: peak simultaneously in-flight vision calls must
    stay <= the cap, and must exceed 1 (or the "fix" was to serialise, which
    would make a 5,000-page batch unusably slow rather than merely wrong).
    """
    inflight = 0
    peak = 0

    async def _vision(images, prompt, config, *, language=None, **kwargs):
        nonlocal inflight, peak
        inflight += 1
        peak = max(peak, inflight)
        try:
            await asyncio.sleep(0.02)
        finally:
            inflight -= 1
        return "text"

    await _drive_graph(tmp_path, _vision)

    assert peak <= VISION_FAN_OUT_CONCURRENCY, (
        f"peak in-flight {peak} exceeded the cap {VISION_FAN_OUT_CONCURRENCY} "
        f"across {PAGE_COUNT} pages — the re-entrant slot stopped capping"
    )
    assert peak >= 2, (
        f"peak in-flight was {peak}: the fan-out serialised instead of "
        "running concurrently"
    )


@pytest.mark.asyncio
async def test_vision_slot_is_reentrant_but_still_caps_new_holders():
    """The re-entrant slot must not become an unlimited slot.

    Re-entering inside a task that already holds the slot is free; a task that
    does NOT hold it still has to wait when all permits are taken.
    """
    from fichero_server.workflows.builder import vision_slot

    async with vision_slot():
        # Re-entry in the same task is a no-op — this must not block.
        async with asyncio.timeout(1):
            async with vision_slot():
                pass

        # Drain the remaining permits from independent tasks, then prove a
        # further independent acquirer blocks.
        released = asyncio.Event()
        holders = [
            asyncio.create_task(_hold_slot(released))
            for _ in range(VISION_FAN_OUT_CONCURRENCY - 1)
        ]
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        blocked = asyncio.create_task(_hold_slot(released))
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(asyncio.shield(blocked), timeout=0.2)

        released.set()
        await asyncio.gather(*holders, blocked)


async def _hold_slot(released: asyncio.Event) -> None:
    from fichero_server.workflows.builder import vision_slot

    async with vision_slot():
        await released.wait()

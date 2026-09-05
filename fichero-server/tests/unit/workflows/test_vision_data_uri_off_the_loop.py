"""Rendering a page for a vision call must not stop the event loop.

`process_vision` fans its files out with `asyncio.gather`, capped at
`VISION_FAN_OUT_CONCURRENCY`. Inside each task it built the image to send by
calling `_pdf_page_to_data_uri` / `file_to_data_uri` INLINE — both CPU-bound,
and the PDF one doubly so: on a cache miss it rasterizes EVERY page of the
document at 300 dpi through Quartz before PNG-encoding the one page it wants.

Run on the event loop, that means the first page of a PDF to arrive halts every
other task in the process until the whole document has been rasterized — the
other fan-out slots, the run's own progress reporting, every unrelated request
the engine is serving. And nothing reports it, so it reads as "slow", which is
how a stall like this survives.

The fix does not make the render cheaper — the `lru_cache` still means one
rasterization per document. It stops that work happening on the thread whose
job is to hand out work.

Both tests below use a fake that blocks a real thread, so they measure the
property rather than the implementation: with a correct wrapper the loop keeps
ticking, and with an inline call it cannot.

No engine, no PDF, no model.
"""

from __future__ import annotations

import asyncio
import threading
from functools import lru_cache

import pytest

from fichero_server.workflows.tools import vision_base


@pytest.mark.asyncio
async def test_pdf_render_runs_off_the_event_loop_thread(monkeypatch) -> None:
    """The blocking render happens on a worker thread, not the loop's."""
    loop_thread = threading.get_ident()
    ran_on: dict[str, int] = {}

    def fake_render(file_path, page_index=0, max_dimension=2048):
        ran_on["thread"] = threading.get_ident()
        return "data:image/png;base64,AAAA"

    monkeypatch.setattr(vision_base, "_pdf_page_to_data_uri", fake_render)

    uri = await vision_base._pdf_page_to_data_uri_async("/x.pdf", 0, 2048)

    assert uri == "data:image/png;base64,AAAA"
    assert ran_on["thread"] != loop_thread, (
        "the PDF render ran on the event loop thread — every other task in the "
        "process is stopped for the duration of the rasterization"
    )


@pytest.mark.asyncio
async def test_image_encode_runs_off_the_event_loop_thread(monkeypatch) -> None:
    """Same rule for the plain-image seam; PIL decode/resize is CPU-bound too."""
    loop_thread = threading.get_ident()
    ran_on: dict[str, int] = {}

    def fake_encode(file_path, max_dimension=2048):
        ran_on["thread"] = threading.get_ident()
        return "data:image/jpeg;base64,BBBB"

    monkeypatch.setattr(vision_base, "file_to_data_uri", fake_encode)

    await vision_base.file_to_data_uri_async("/x.jpg", 2048)

    assert ran_on["thread"] != loop_thread


@pytest.mark.asyncio
async def test_the_loop_keeps_running_during_a_slow_render(monkeypatch) -> None:
    """The property that actually matters, stated as behaviour.

    A neighbour task must make progress while a page is being rendered. This is
    what the fan-out needs and what an inline call cannot provide: a sibling
    counter that never advances is the stall the beta tester experienced as
    minutes of nothing.
    """
    render_started = threading.Event()
    release_render = threading.Event()

    def slow_render(file_path, page_index=0, max_dimension=2048):
        render_started.set()
        # Blocks a REAL thread, exactly as a Quartz rasterization does.
        release_render.wait(timeout=5)
        return "data:image/png;base64,CCCC"

    monkeypatch.setattr(vision_base, "_pdf_page_to_data_uri", slow_render)

    ticks = 0

    async def neighbour() -> None:
        nonlocal ticks
        while not release_render.is_set():
            ticks += 1
            await asyncio.sleep(0.005)

    async def render() -> str:
        uri = await vision_base._pdf_page_to_data_uri_async("/big.pdf", 0, 2048)
        return uri

    neighbour_task = asyncio.create_task(neighbour())
    render_task = asyncio.create_task(render())

    # Let the render actually start and the neighbour get some turns.
    await asyncio.sleep(0.1)
    started = render_started.is_set()
    ticks_during_render = ticks

    release_render.set()
    uri = await render_task
    await neighbour_task

    assert started, "the render never started"
    assert uri == "data:image/png;base64,CCCC"
    assert ticks_during_render > 0, (
        "no other task advanced while a page was rendering — the render is "
        "blocking the event loop, which is the whole defect"
    )


@pytest.mark.asyncio
async def test_a_render_failure_still_propagates(monkeypatch) -> None:
    """Moving work to a thread must not swallow the reason it failed."""

    def boom(file_path, page_index=0, max_dimension=2048):
        raise ValueError("Could not open PDF: /nope.pdf")

    monkeypatch.setattr(vision_base, "_pdf_page_to_data_uri", boom)

    with pytest.raises(ValueError, match="Could not open PDF"):
        await vision_base._pdf_page_to_data_uri_async("/nope.pdf", 0, 2048)


@pytest.mark.asyncio
async def test_concurrent_pages_rasterize_the_document_only_once(
    monkeypatch, tmp_path
) -> None:
    """N pages of one PDF must not each rasterize the whole document.

    `lru_cache` deduplicates RESULTS; it does not serialize COMPUTATION. Once
    the render moved onto worker threads, every page task that missed the cache
    together would rasterize all N pages — a 7-page PDF rendered 7 times over.

    While the render ran inline on the event loop this could not happen: the
    blocking call was an accidental mutex. That accident is exactly what moving
    the work off the loop removes, which is why the lock is explicit now — and
    why this test exists rather than being assumed from the cache.
    """
    pdf = tmp_path / "same.pdf"
    pdf.write_bytes(b"%PDF-1.4 stub")  # the readability guard runs for real here

    renders = 0
    renders_lock = threading.Lock()

    # The fake carries lru_cache because the REAL function does. Cache and lock
    # are a pair: the cache stops repeat work, the lock stops SIMULTANEOUS work
    # that the cache has not recorded yet. A fake without the cache would be
    # testing a different function than the one that ships.
    @lru_cache(maxsize=4)
    def counting_render(pdf_path, dpi=300):
        nonlocal renders
        with renders_lock:
            renders += 1
        # Wide enough that every sibling task is inside the window.
        threading.Event().wait(0.05)
        return ([object()] * 7, 7)

    monkeypatch.setattr(
        vision_base, "_batch_render_pdf_pages_to_cgimages", counting_render
    )
    monkeypatch.setattr(
        vision_base, "_cgimage_to_data_uri", lambda img, max_dimension=2048: "data:,x"
    )

    results = await asyncio.gather(
        *(
            vision_base._pdf_page_to_data_uri_async(str(pdf), page, 2048)
            for page in range(7)
        )
    )

    assert results == ["data:,x"] * 7
    assert renders == 1, (
        f"the document was rasterized {renders} times for 7 pages — concurrent "
        "cache misses are each rendering the whole PDF"
    )


@pytest.mark.asyncio
async def test_without_the_lock_the_stampede_really_happens(
    monkeypatch, tmp_path
) -> None:
    """Proof that the LOCK is what prevents it, not the cache alone.

    Same setup as the test above with the lock replaced by a no-op. If this
    does not stampede, the test above is passing for some other reason and is
    not guarding what it claims to guard.
    """
    import contextlib

    pdf = tmp_path / "same.pdf"
    pdf.write_bytes(b"%PDF-1.4 stub")

    renders = 0
    renders_lock = threading.Lock()

    @lru_cache(maxsize=4)
    def counting_render(pdf_path, dpi=300):
        nonlocal renders
        with renders_lock:
            renders += 1
        threading.Event().wait(0.05)
        return ([object()] * 7, 7)

    monkeypatch.setattr(
        vision_base, "_batch_render_pdf_pages_to_cgimages", counting_render
    )
    monkeypatch.setattr(
        vision_base, "_cgimage_to_data_uri", lambda img, max_dimension=2048: "data:,x"
    )
    monkeypatch.setattr(vision_base, "_PDF_RENDER_LOCK", contextlib.nullcontext())

    await asyncio.gather(
        *(
            vision_base._pdf_page_to_data_uri_async(str(pdf), page, 2048)
            for page in range(7)
        )
    )

    assert renders > 1, (
        "expected concurrent cache misses to each rasterize the document; if "
        "they do not, the lock test above proves nothing"
    )

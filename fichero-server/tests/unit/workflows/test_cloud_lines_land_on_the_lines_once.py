"""A cloud model reading Kraken's lines one call a page lands its readings on the page's own lines, once (#5487):
no second line pass, no second set of segments, and each reading on the line it was cut from."""
from __future__ import annotations

import pytest

from tests.unit.workflows.test_one_line_pass_read_many import (  # noqa: F401  (`page` is the shared fixture)
    _counting, _lines, _passes, _transcribe, page,
)


@pytest.mark.asyncio
async def test_a_page_a_call_read_adds_readings_to_the_one_pass(page, monkeypatch):  # noqa: F811
    import fichero_server.llm as llm
    from fichero_server.models import Segment

    await _transcribe(page)
    (lines_pass,) = _passes(page)
    before = len([s for s in page["db"].query(Segment, document_id=page["doc"].id) if s.deleted_at is None])

    async def teacher(images, prompt, config, **_):
        return '["primera", "segunda", "tercera"]'

    monkeypatch.setattr(llm, "vision", teacher)
    await _transcribe(page, lines_read_by="model", read_granularity="page")
    assert [p.id for p in _passes(page)] == [lines_pass.id]
    after = len([s for s in page["db"].query(Segment, document_id=page["doc"].id) if s.deleted_at is None])
    assert after == before, "reading made new segments"
    assert _counting(page, _lines(page, lines_pass.id)) == ["primera", "segunda", "tercera"]


@pytest.mark.asyncio
async def test_a_fresh_page_found_and_read_in_one_run_has_one_reading_a_line(page, monkeypatch):  # noqa: F811
    """Find Lines + Read as one run (`start.plan_start` merges them): the lines are found, read, and each line holds ONE reading."""
    import fichero_server.llm as llm
    from fichero_server.api.routes.document.segment_readings import readings_of_segment

    async def teacher(images, prompt, config, **_):
        return '["primera", "segunda", "tercera"]'

    monkeypatch.setattr(llm, "vision", teacher)
    await _transcribe(page, lines_read_by="model", read_granularity="page")
    (made,) = _passes(page)
    for row in _lines(page, made.id):
        assert [r.content for r in readings_of_segment(page["db"], row.id)] in (["primera"], ["segunda"], ["tercera"])

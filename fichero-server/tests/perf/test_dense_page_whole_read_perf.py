"""source.store.dense-page-reads-whole-in-bound (#4956): the whole dense page, one read, no filter, cold.

500 ms at 20,000 segments is a TARGET (ruled 2026-10-17), not a measured fact. This is the named perf test the spec
points at: it always asserts the read returns every segment; it asserts the target only when the person running it says
the M4 is idle (PERF_IDLE=1) and the machine is not thermally limited. Anywhere else it prints the number and passes.
"""
from __future__ import annotations

import os
import time

import pytest

from fichero_server.actions.registry import ActionContext, registry
from fichero_server.models import DocType, Document, FileType, Status
from tests.perf.test_segment_edit_undo_perf import _load, _thermal_state

pytestmark = [pytest.mark.timing, pytest.mark.slow, pytest.mark.source_model]

TARGET_MS = 500


def test_the_whole_dense_page_reads_in_one_cold_call(db, client, tmp_path):
    from fichero_server.formats import write_page

    data, _ = write_page("pagexml", _load("perf_fixture").generate(20000))
    page_file = tmp_path / "dense.page.xml"
    page_file.write_bytes(data)
    doc = Document(name="dense.jpg", doc_type=DocType.file, file_type=FileType.image,
                   path="/path/dense.jpg", status=Status.completed)
    db.save(doc)
    registry.invoke(db, "format.import", {"document_id": doc.id, "path": str(page_file)},
                    ActionContext(actor="historian", library_path=None, is_bootstrap=True))

    started = time.perf_counter()  # first read after the import: nothing asked for yet
    r = client.get(f"/api/segments/document/{doc.id}")
    elapsed_ms = (time.perf_counter() - started) * 1000

    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["segments"] if isinstance(body, dict) else body) >= 20000, "every segment of the page comes back"
    print(f"\ndense page whole read: {elapsed_ms:.0f} ms (target {TARGET_MS} ms, thermal {_thermal_state()})")
    if os.environ.get("PERF_IDLE") == "1" and _thermal_state() == "nominal":
        assert elapsed_ms <= TARGET_MS, f"{elapsed_ms:.0f} ms is over the {TARGET_MS} ms target"

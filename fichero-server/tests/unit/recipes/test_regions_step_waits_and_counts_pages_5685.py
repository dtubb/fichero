"""`activity.throttle.power-heat-memory` (#5685): Find Regions inside a recipe run waits while the throttle says so,
saying why, and counts pages.

Spec: docs/contributor_manual/specs/ui/activity-and-automatic-work.md. WHY (2026-10-11, the MCP onboarding walk):
while Find Regions ran, the run's row said "running", "Running step find-regions: 0 of 1 folder done", while
machine.why_wait said "Waiting: you're using the Mac". The regions model is stubbed; the throttle is the real one
with its probe answered.
"""
from __future__ import annotations

from fichero_server.recipes import regions


def test_it_waits_saying_why_then_counts_pages(db, tmp_path, monkeypatch):
    from PIL import Image

    from fichero_server.execution import throttle
    from fichero_server.models import DocType, Document, FileType

    docs = []
    for i in range(3):
        path = tmp_path / f"p{i}.png"
        Image.new("RGB", (40, 60), (250, 250, 250)).save(path)
        doc = Document(name=path.name, doc_type=DocType.file, file_type=FileType.image, path=str(path))
        db.save(doc)
        docs.append(doc.id)
    in_use = iter([True, True, False, False, False, False])
    monkeypatch.setattr(throttle, "why_wait",
                        lambda **_: "Waiting: you're using the Mac" if next(in_use, False) else None)
    from fichero_server.llm import kraken_runtime

    monkeypatch.setattr(kraken_runtime, "segment_lines", lambda path, **k: {"width": 40, "height": 60, "regions": [], "lines": []})
    from fichero_server.execution import jobs

    # The model lane is not under test (a unit test has no scheduler running it): the segmenter's call runs inline.
    monkeypatch.setattr(jobs, "run_on_lane_blocking", lambda library, kind, subject, *, fn, **kw: fn())
    monkeypatch.setattr(regions, "WAIT_POLL_SECONDS", 0)
    said: list[str] = []

    account = regions.find_regions(db, docs, "run-1", "blla", provider="kraken", say=said.append)

    assert account["pages"] == 3
    assert said[0] == "Waiting: you're using the Mac", said
    assert said[-1] == "Finding regions: 3 of 3 pages", said
    assert not any("folder" in s for s in said)

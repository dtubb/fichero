"""Pages in iCloud: warn, copy them into the project, and fetch boundedly as the last line of defence (#5669).

WHY: on EAP 1740, 88 of 92 pages failed a review step with "File is stored in iCloud and not downloaded locally".
The reader refused them by name, on purpose: opening a dataless file blocks silently while macOS downloads it (it
once hung a transcription for 45 minutes). Ruled 2026-10-11: before Start (and after an import) say how many pages
are in iCloud and offer to copy them into the project, so it never depends on iCloud again; no silent download in
place by default; and before a step reads its pages, bring the evicted ones down, bounded and off the event loop,
said in Activity, a page still not here failing in words.

A dataless file cannot be made in a test: `dataless_reason` is stood in for over a set of "evicted" paths, and the
fetcher is a fake that materializes a file after a delay (or never).
"""

from __future__ import annotations

import asyncio
import threading
from pathlib import Path

import pytest
from _scan_files import scan_rglob

from fichero_server.importers import dataless
from fichero_server.models import DocType, Document, FileType


@pytest.fixture
def evicted(monkeypatch):
    """Paths whose bytes are "in iCloud": dataless until a fetch takes them off this set."""
    gone: set[str] = set()
    real = dataless.dataless_reason
    monkeypatch.setattr(dataless, "dataless_reason",
                        lambda path: "a cloud placeholder (test)" if str(path) in gone else real(path))
    dataless.NOT_FETCHED.clear()
    yield gone
    dataless.NOT_FETCHED.clear()


def _later(gone: set[str], delay: float):
    """A fetcher that brings a file down after `delay` seconds, as macOS would, without the caller waiting on it."""
    asked = []

    def fetch(path: Path) -> None:
        asked.append(str(path))
        threading.Timer(delay, gone.discard, [str(path)]).start()

    fetch.asked = asked
    return fetch


def _pages(tmp_path, n=2) -> list[str]:
    folder = tmp_path / "Mobile Documents" / "EAP 1740"
    folder.mkdir(parents=True)
    out = []
    for i in range(n):
        p = folder / f"page_{i}.jpg"
        p.write_bytes(b"\xff\xd8" + b"x" * 1000)
        out.append(str(p))
    return out


def test_evicted_pages_are_fetched_first_and_the_count_is_said(tmp_path, evicted):
    pages = _pages(tmp_path)
    evicted.update(pages)
    said = []
    fetch = _later(evicted, 0.2)

    failed = dataless.fetch_first(pages, say=said.append, fetch=fetch, min_timeout=5)

    assert failed == {} and sorted(fetch.asked) == sorted(pages)
    assert said[0] == "Downloading 2 pages from iCloud: 0 of 2" and said[-1] == "Downloading 2 pages from iCloud: 2 of 2"


def test_a_page_that_never_comes_down_fails_in_words_after_its_bound(tmp_path, evicted):
    from fichero_server.workflows.tools import vision_base

    pages = _pages(tmp_path, 1)
    evicted.update(pages)

    failed = dataless.fetch_first(pages, fetch=lambda path: None, min_timeout=1, sleep=lambda s: None)

    assert failed == {pages[0]: "page_0.jpg is in iCloud and did not download in 1 s (no network?)"}
    # The reader, the last line of defence, says that rather than its own refusal.
    stat = type("Stat", (), {"st_flags": vision_base._SF_DATALESS, "st_blocks": 0, "st_size": 1002})()
    import os

    real_stat = os.stat
    try:
        os.stat = lambda p, *a, **k: stat if str(p) == pages[0] else real_stat(p, *a, **k)
        with pytest.raises(ValueError, match="did not download in 1 s"):
            vision_base.assert_source_readable(pages[0])
    finally:
        os.stat = real_stat


def test_nothing_is_fetched_when_the_disk_would_fill(tmp_path, evicted, monkeypatch):
    import shutil

    pages = _pages(tmp_path)
    evicted.update(pages)
    monkeypatch.setattr(shutil, "disk_usage", lambda path: type("U", (), {"free": dataless.FETCH_FREE_FLOOR_BYTES})())
    asked = []

    failed = dataless.fetch_first(pages, fetch=asked.append, min_timeout=1)

    assert asked == [] and set(failed) == set(pages)
    assert all("Free some space" in why and "free" in why for why in failed.values())


def test_a_run_source_fetches_its_pages_before_any_step_reads_them(tmp_path, evicted):
    """The per-step guard: every source tool's pages are brought down before the steps after it read them."""
    from fichero_server.workflows.tools import sources

    pages = _pages(tmp_path)
    evicted.update(pages)
    fetch = _later(evicted, 0.1)
    real = dataless.request_download
    dataless.request_download = fetch
    try:
        async def source(inputs, state, llm_config):
            return {"files": pages, "documents": [], "count": 2}

        result = asyncio.run(sources._fetches_first(source)({}, {}, None))
    finally:
        dataless.request_download = real
    assert result["files"] == pages and sorted(fetch.asked) == sorted(pages)
    assert not evicted  # here before any step reads them


# --- the warning and the copy into the project, through the routes -------------------------------------------


def _linked(db, path: str) -> Document:
    doc = Document(name=Path(path).name, doc_type=DocType.file, file_type=FileType.image, path=path)
    db.save(doc)
    return doc


def test_ready_warns_and_copying_them_in_makes_the_project_keep_its_own(client, db, tmp_path, evicted, monkeypatch):
    pages = _pages(tmp_path)
    here = _pages(tmp_path / "local", 1)
    linked = [_linked(db, p) for p in pages]
    _linked(db, here[0])  # on this Mac: never in the warning
    evicted.update(pages)

    warned = client.get("/api/documents/in-icloud").json()
    assert warned["pages"] == 2 and warned["sentence"] == "2 pages are in iCloud and not on this Mac."
    assert warned["offer"].startswith("Copy them into the project (") and warned["room"] is True
    assert warned["action"] == "document.copy_into_project"
    assert sorted(warned["params"]["ids"]) == sorted(d.id for d in linked)
    plan = client.get("/api/recipes/project/start").json()
    assert plan["in_icloud"]["pages"] == 2 and plan["in_icloud"]["offer"] == warned["offer"]

    monkeypatch.setattr(dataless, "request_download", _later(evicted, 0.1))
    copied = client.post("/api/documents/copy-into-project", json=warned["params"])

    assert copied.status_code == 200, copied.text
    assert copied.json()["not_copied"] == {}
    package = Path(db.path).parent
    for doc in linked:
        now = db.get(Document, doc.id)
        assert not Path(now.path).is_absolute() and now.path.startswith("files/")
        assert (package / now.path).read_bytes() == Path(doc.path).read_bytes()
        assert now.metadata["copied_from"] == doc.path
    assert client.get("/api/documents/in-icloud").json() is None  # the project keeps its own now

    # Undo puts the pages back on their originals and removes only the copies it made.
    from fichero_server.models import ActionAudit

    audit = next(a for a in db.query(ActionAudit) if a.action_name == "document.copy_into_project")
    undone = client.post(f"/api/actions/audit/{audit.id}/undo")
    assert undone.status_code == 200, undone.text
    for doc in linked:
        assert db.get(Document, doc.id).path == doc.path
    assert not [p for p in scan_rglob(package / "files", "*") if p.is_file() and "page_" in p.name]


def test_no_room_refuses_start_with_the_numbers(client, db, tmp_path, evicted, monkeypatch):
    import shutil

    pages = _pages(tmp_path)
    for p in pages:
        _linked(db, p)
    evicted.update(pages)
    monkeypatch.setattr(shutil, "disk_usage", lambda path: type("U", (), {"free": 1_000})())

    plan = client.get("/api/recipes/project/start").json()

    assert plan["in_icloud"]["room"] is False
    assert any("in iCloud need" in r and "Free some space first" in r for r in plan["refusals"]), plan["refusals"]

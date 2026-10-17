"""`source.recipe.pinned-model-gone` (#5364): the failed-fetch record survives concurrent writers and a crash mid-write.

Spec: docs/contributor_manual/specs/source/models-chains-and-projects.md. WHY: two downloads that fail at once both read the record,
add their repository and write it back, so one entry was lost (and a write cut short left a file nothing could read). The write is
a temporary file replaced into place under a lock.
"""
from __future__ import annotations

import threading

from fichero_server.llm import failed_fetches


def test_concurrent_failures_all_land(tmp_path):
    """source.recipe.pinned-model-gone: every failed fetch is recorded, however many fail at once."""
    repos = [f"org/model-{i}" for i in range(40)]
    gate = threading.Barrier(len(repos))

    def fail(repo):
        gate.wait()
        failed_fetches.record(tmp_path, repo, "404")

    threads = [threading.Thread(target=fail, args=(r,)) for r in repos]
    [t.start() for t in threads]
    [t.join() for t in threads]

    assert all(failed_fetches.last(r, tmp_path) == "404" for r in repos)


def test_a_write_never_leaves_a_half_file(tmp_path, monkeypatch):
    """source.recipe.pinned-model-gone: a write that dies part-way leaves the old record whole, no stray temporary file."""
    failed_fetches.record(tmp_path, "org/kept", "gone")

    def dies(src, dst):
        raise OSError("disk full")

    monkeypatch.setattr(failed_fetches.os, "replace", dies)
    try:
        failed_fetches.record(tmp_path, "org/new", "gone")
    except OSError:
        pass
    monkeypatch.undo()

    assert failed_fetches.last("org/kept", tmp_path) == "gone"
    assert [p.name for p in tmp_path.iterdir()] == [failed_fetches.FILE]

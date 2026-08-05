"""One thumbnail generation at a time PER DOCUMENT (2026-08-05).

Two concurrent requests for the same document both saw a cache miss and both
generated, writing the same output path underneath each other. uvicorn then
raised ``RuntimeError: Response content shorter than Content-Length`` — one
response had measured the file, the other rewrote it mid-send, so the byte
count it had promised no longer existed.

Two properties, and the second matters as much as the first: the lock must be
per document, or a grid of thumbnails serialises behind one slow image.
"""

from __future__ import annotations

import threading

from fichero_server.db.storage import _thumbnail_lock


def test_same_document_shares_one_lock():
    assert _thumbnail_lock("doc-a") is _thumbnail_lock("doc-a")


def test_different_documents_do_not_block_each_other():
    """A global lock would pass the test above and fail this one."""
    assert _thumbnail_lock("doc-a") is not _thumbnail_lock("doc-b")

    held = _thumbnail_lock("doc-a")
    held.acquire()
    try:
        other = _thumbnail_lock("doc-b")
        assert other.acquire(blocking=False), (
            "doc-b blocked while doc-a was generating — the lock is global, "
            "not per document"
        )
        other.release()
    finally:
        held.release()


def test_second_caller_for_one_document_waits():
    lock = _thumbnail_lock("doc-serialised")
    lock.acquire()
    try:
        assert not lock.acquire(blocking=False), (
            "a second generation for the SAME document was allowed to start — "
            "this is the race that truncated an in-flight response"
        )
    finally:
        lock.release()


def test_registry_is_safe_under_concurrent_first_use():
    """The keys are created lazily, so creation itself must not race."""
    seen: list[threading.Lock] = []
    barrier = threading.Barrier(8)

    def grab() -> None:
        barrier.wait()
        seen.append(_thumbnail_lock("doc-contended"))

    threads = [threading.Thread(target=grab) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(seen) == 8
    assert len({id(lock) for lock in seen}) == 1, (
        "concurrent first use produced more than one lock for one document — "
        "the registry itself is unguarded"
    )

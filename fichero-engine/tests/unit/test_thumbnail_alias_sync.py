"""The thumbnail alias sync is idempotent and never fails a good request (#4231).

`_sync_alias_to_cache` unlinked then hard-linked, which threw three different
ways once the alias and the cache entry were the same inode — the steady state
after the very first call:

* `FileExistsError` when the unlink lost a race
* `SameFileError` from the `copy2` fallback that existed to handle this case
* `FileNotFoundError` when the destination vanished between the two steps

It surfaced as intermittent 500s on thumbnails that had generated perfectly,
because the exception escaped after the response headers were already sent —
so the failure was both spurious and unattributable.

Calling it twice is the whole test. Everything else here is the boundary.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from fichero.db.storage import _sync_alias_to_cache


def _cache_entry(tmp_path: Path, data: bytes = b"jpegbytes") -> Path:
    cache = tmp_path / "cache" / "ab" / "doc__200x200.jpg"
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_bytes(data)
    return cache


class TestIdempotence:
    def test_calling_it_twice_does_not_raise(self, tmp_path):
        """The bug, in one line. The second call used to throw."""
        cache = _cache_entry(tmp_path)
        alias = tmp_path / "thumbs" / "doc.jpg"

        _sync_alias_to_cache(cache, alias)
        _sync_alias_to_cache(cache, alias)

        assert alias.exists()
        assert alias.read_bytes() == b"jpegbytes"

    def test_calling_it_many_times_is_stable(self, tmp_path):
        cache = _cache_entry(tmp_path)
        alias = tmp_path / "thumbs" / "doc.jpg"

        for _ in range(5):
            _sync_alias_to_cache(cache, alias)

        assert alias.exists()

    def test_the_same_inode_case_short_circuits(self, tmp_path):
        """After one sync the two paths ARE the same file; that must be a no-op."""
        cache = _cache_entry(tmp_path)
        alias = tmp_path / "thumbs" / "doc.jpg"
        _sync_alias_to_cache(cache, alias)

        assert os.path.samefile(cache, alias)

        _sync_alias_to_cache(cache, alias)  # must not raise

        assert os.path.samefile(cache, alias)


class TestItActuallyUpdates:
    def test_a_new_cache_entry_replaces_the_alias(self, tmp_path):
        """Idempotence must not become 'never updates'."""
        first = _cache_entry(tmp_path, b"old")
        alias = tmp_path / "thumbs" / "doc.jpg"
        _sync_alias_to_cache(first, alias)

        second = tmp_path / "cache" / "ab" / "doc__400x400.jpg"
        second.write_bytes(b"new")
        _sync_alias_to_cache(second, alias)

        assert alias.read_bytes() == b"new"

    def test_the_alias_is_never_missing_midway(self, tmp_path):
        """os.replace is atomic, so there is no window with no alias.

        The old code unlinked first, leaving a gap in which a concurrent
        request saw no alias at all.
        """
        cache = _cache_entry(tmp_path)
        alias = tmp_path / "thumbs" / "doc.jpg"
        _sync_alias_to_cache(cache, alias)
        assert alias.exists()

        newer = tmp_path / "cache" / "ab" / "doc__800x800.jpg"
        newer.write_bytes(b"newer")
        _sync_alias_to_cache(newer, alias)

        assert alias.exists()


class TestConcurrentCallsDoNotRace:
    """The actual reported symptom: INTERMITTENT 500s, not deterministic ones.

    Sequential calls do not reproduce it — mutation proved that, because the
    old unlink-then-link passed the idempotence tests above. The failure needs
    two requests interleaving: one unlinks the alias while the other is between
    its own unlink and link, so one of them hits FileExistsError or
    FileNotFoundError on a thumbnail that generated perfectly.

    `os.replace` removes the window entirely — there is no unlink to lose.
    """

    def test_many_threads_syncing_the_same_alias(self, tmp_path):
        import threading

        # TWO distinct cache entries, alternated per iteration: with a single
        # entry the samefile short-circuit makes every call after the first a
        # no-op, so the link/replace path — the one that raced — never runs
        # and the test is vacuous.
        cache_a = _cache_entry(tmp_path, b"variant-a")
        cache_b = tmp_path / "cache" / "ab" / "doc__400x400.jpg"
        cache_b.write_bytes(b"variant-b")
        alias = tmp_path / "thumbs" / "doc.jpg"
        alias.parent.mkdir(parents=True, exist_ok=True)
        errors: list[BaseException] = []

        def worker(seed: int) -> None:
            for i in range(40):
                try:
                    _sync_alias_to_cache(cache_a if (i + seed) % 2 else cache_b, alias)
                except BaseException as exc:  # noqa: BLE001 - recording, not handling
                    errors.append(exc)

        threads = [threading.Thread(target=worker, args=(n,)) for n in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"concurrent alias sync raised: {errors[:3]}"
        assert alias.exists(), "the alias vanished under concurrent syncs"
        assert alias.read_bytes() in (b"variant-a", b"variant-b"), (
            "alias holds neither variant - a torn or skipped update"
        )
        leftovers = list(alias.parent.glob("*.sync-*"))
        assert not leftovers, f"staging files leaked under concurrency: {leftovers}"

    def test_the_alias_is_readable_throughout_concurrent_syncs(self, tmp_path):
        """A reader must never observe a missing alias mid-update."""
        import threading

        # Alternate two cache entries so every writer iteration exercises the
        # real link/replace path (a single entry short-circuits on samefile
        # and the reader would be watching a no-op loop).
        cache_a = _cache_entry(tmp_path, b"stable-a")
        cache_b = tmp_path / "cache" / "ab" / "doc__400x400.jpg"
        cache_b.write_bytes(b"stable-b")
        alias = tmp_path / "thumbs" / "doc.jpg"
        _sync_alias_to_cache(cache_a, alias)
        missing: list[str] = []
        stop = threading.Event()

        def writer() -> None:
            for i in range(60):
                _sync_alias_to_cache(cache_a if i % 2 else cache_b, alias)
            stop.set()

        def reader() -> None:
            while not stop.is_set():
                if not alias.exists():
                    missing.append("gone")

        threads = [threading.Thread(target=writer), threading.Thread(target=reader)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not missing, "a reader saw the alias missing during an update"


class TestFailureIsNonFatal:
    """A bookkeeping copy must not fail a request whose image is fine."""

    def test_a_missing_cache_entry_does_not_raise(self, tmp_path, caplog):
        caplog.set_level(logging.WARNING, logger="fichero.db.storage")
        alias = tmp_path / "thumbs" / "doc.jpg"

        _sync_alias_to_cache(tmp_path / "nope.jpg", alias)  # must not raise

        assert not alias.exists(), "no alias should appear for a missing cache entry"
        assert any("alias sync failed" in r.getMessage() for r in caplog.records), (
            "the swallowed failure must still be logged"
        )

    def test_an_unwritable_destination_does_not_raise(self, tmp_path, caplog):
        caplog.set_level(logging.WARNING, logger="fichero.db.storage")
        cache = _cache_entry(tmp_path)
        locked = tmp_path / "locked"
        locked.mkdir()
        locked.chmod(0o500)
        try:
            _sync_alias_to_cache(cache, locked / "doc.jpg")  # must not raise
        finally:
            locked.chmod(0o700)

        assert not (locked / "doc.jpg").exists()
        assert any("alias sync failed" in r.getMessage() for r in caplog.records), (
            "the swallowed failure must still be logged"
        )

    def test_no_staging_file_is_left_behind(self, tmp_path):
        """The temp name must never survive a success or a failure."""
        cache = _cache_entry(tmp_path)
        alias = tmp_path / "thumbs" / "doc.jpg"

        _sync_alias_to_cache(cache, alias)
        _sync_alias_to_cache(tmp_path / "nope.jpg", alias)

        leftovers = list(alias.parent.glob("*.sync-*"))
        assert not leftovers, f"staging files left behind: {leftovers}"

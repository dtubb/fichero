"""Regression guard for #2246.

Non-parallel (sequential) LLM nodes in Catalogue-style workflows
(extract_all, catalogue, *_folder_cleanup, citations_extract) now use a
content-addressed batch cache keyed on the full input-files list rather than
a single file path.

These tests verify:
- compute_batch_cache_key produces stable, distinct keys
- is_sequentially_cacheable covers the expected tool set (explicit + suffix)
- Key changes when any file in the batch changes identity
- Key is stable when file list order is shuffled
"""

import os
import tempfile

import pytest

from fichero.workflows.cache import (
    compute_batch_cache_key,
    is_sequentially_cacheable,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_tmp_file(content: bytes, suffix: str = ".txt") -> str:
    """Write a temp file and return its path (caller is responsible for cleanup)."""
    fd, path = tempfile.mkstemp(suffix=suffix)
    with os.fdopen(fd, "wb") as fh:
        fh.write(content)
    return path


# ---------------------------------------------------------------------------
# is_sequentially_cacheable
# ---------------------------------------------------------------------------


class TestIsSequentiallyCacheable:
    def test_explicit_tools(self):
        for tool in ("extract_all", "catalogue", "citations_extract"):
            assert is_sequentially_cacheable(tool), f"{tool!r} should be cacheable"

    def test_folder_cleanup_suffix(self):
        for key in ("people", "places", "organizations", "dates", "events", "keywords"):
            assert is_sequentially_cacheable(f"{key}_folder_cleanup")

    def test_page_cleanup_suffix(self):
        for key in ("people", "places"):
            assert is_sequentially_cacheable(f"{key}_page_cleanup")

    def test_non_cacheable_tools(self):
        for tool in ("files", "aggregate", "route", "condition", "sub_workflow"):
            assert not is_sequentially_cacheable(tool), f"{tool!r} should NOT be cacheable"

    def test_parallel_cacheable_tools_are_also_sequential(self):
        # CACHEABLE_TOOLS is a subset of sequentially cacheable — extract_all,
        # describe, transcribe etc. can all be cached in both paths.
        for tool in ("describe", "transcribe", "summarize", "extract_all"):
            assert is_sequentially_cacheable(tool)


# ---------------------------------------------------------------------------
# compute_batch_cache_key
# ---------------------------------------------------------------------------


class TestComputeBatchCacheKey:
    @pytest.fixture(autouse=True)
    def tmp_files(self):
        paths = [
            _write_tmp_file(b"file-a content", ".txt"),
            _write_tmp_file(b"file-b content", ".pdf"),
        ]
        yield paths
        for p in paths:
            try:
                os.unlink(p)
            except OSError:
                pass

    def _key(self, file_paths, *, node_id="n1", tool="extract_all", config=None):
        return compute_batch_cache_key(
            workflow_id="wf-test",
            node_id=node_id,
            tool=tool,
            config=config or {},
            provider="openai",
            model="gpt-4o",
            file_paths=file_paths,
        )

    def test_returns_32_char_hex(self, tmp_files):
        key = self._key(tmp_files)
        assert len(key) == 32
        assert all(c in "0123456789abcdef" for c in key)

    def test_stable_across_calls(self, tmp_files):
        assert self._key(tmp_files) == self._key(tmp_files)

    def test_order_independent(self, tmp_files):
        """Shuffled file list produces the same key (sorted internally)."""
        key_asc = self._key(tmp_files)
        key_desc = self._key(list(reversed(tmp_files)))
        assert key_asc == key_desc

    def test_different_tools_give_different_keys(self, tmp_files):
        key1 = self._key(tmp_files, tool="extract_all")
        key2 = self._key(tmp_files, tool="catalogue")
        assert key1 != key2

    def test_different_configs_give_different_keys(self, tmp_files):
        key1 = self._key(tmp_files, config={"output_language": "en"})
        key2 = self._key(tmp_files, config={"output_language": "es"})
        assert key1 != key2

    def test_file_content_change_invalidates_key(self, tmp_files):
        key_before = self._key(tmp_files)
        # Overwrite first file to change mtime + size
        with open(tmp_files[0], "wb") as fh:
            fh.write(b"completely different content CHANGED")
        key_after = self._key(tmp_files)
        assert key_before != key_after

    def test_empty_file_list(self):
        key = self._key([])
        assert len(key) == 32

    def test_nonexistent_file_does_not_raise(self):
        key = self._key(["/tmp/does-not-exist-xyz.pdf"])
        assert len(key) == 32

    def test_single_file_vs_batch(self, tmp_files):
        key_one = self._key([tmp_files[0]])
        key_two = self._key(tmp_files)
        assert key_one != key_two

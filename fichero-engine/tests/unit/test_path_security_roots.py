"""Coverage for the root-enumeration / confinement logic in ``path_security``.

The existing ``test_path_security_xml_security_adversarial.py`` covers the
escape/traversal *rejections*. This disjoint file pins the parts it doesn't:
the allowed-root enumeration + dedup, the engine temp roots, and the
early-return / accept branches of the validators (all pure, filesystem-light).
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from fichero.security.path_security import (
    ENGINE_TEMP_DERIVED_DIRS,
    allowed_source_roots,
    engine_temp_derived_roots,
    path_within_any_root,
    resolve_snapshot_record_path,
    resolve_under_allowed_roots,
    validate_stored_document_path,
)


@pytest.fixture
def lib(tmp_path):
    return tmp_path / "library"


# ===========================================================================
# engine_temp_derived_roots
# ===========================================================================


def test_engine_temp_roots_cover_all_declared_dirs():
    roots = engine_temp_derived_roots()
    assert len(roots) == len(ENGINE_TEMP_DERIVED_DIRS)
    temp_root = Path(tempfile.gettempdir())
    assert {r.name for r in roots} == set(ENGINE_TEMP_DERIVED_DIRS)
    assert all(r.parent == temp_root for r in roots)


# ===========================================================================
# allowed_source_roots — enumeration + dedup
# ===========================================================================


def test_allowed_roots_library_subdirs(lib):
    roots = allowed_source_roots(lib, include_engine_temp=False)
    resolved = {r for r in roots}
    for sub in ("", "files", "storage", "artifacts", "cache"):
        expected = (lib / sub if sub else lib).expanduser().resolve()
        assert expected in resolved
    assert len(roots) == 5


def test_allowed_roots_includes_temp_by_default(lib):
    roots = allowed_source_roots(lib)
    assert len(roots) == 5 + len(ENGINE_TEMP_DERIVED_DIRS)


def test_allowed_roots_storage_base_adds_four_subdirs(lib, tmp_path):
    storage = tmp_path / "storage_base"
    roots = allowed_source_roots(lib, storage_base=storage, include_engine_temp=False)
    # 5 library roots + 4 storage roots (files/thumbnails/artifacts/cache).
    assert len(roots) == 9
    assert (storage / "thumbnails").resolve() in set(roots)


def test_allowed_roots_dedupes_overlap(lib):
    # storage_base == library: files/artifacts/cache overlap and collapse;
    # only thumbnails is new -> 5 + 1.
    roots = allowed_source_roots(lib, storage_base=lib, include_engine_temp=False)
    assert len(roots) == 6
    # No duplicates in the returned list.
    assert len(roots) == len(set(roots))


def test_allowed_roots_none_library_is_only_temp():
    roots = allowed_source_roots(None)
    # allowed_source_roots resolves each root; compare against resolved temp roots
    # (on macOS /tmp is a symlink to /private/tmp).
    assert set(roots) == {r.resolve() for r in engine_temp_derived_roots()}


# ===========================================================================
# path_within_any_root
# ===========================================================================


def test_path_within_any_root_multi_root(tmp_path):
    root_a = tmp_path / "a"
    root_b = tmp_path / "b"
    candidate = root_b / "sub" / "file.txt"
    assert path_within_any_root(candidate, [root_a, root_b]) is True


def test_path_within_any_root_none_match(tmp_path):
    assert path_within_any_root(tmp_path / "outside" / "x", [tmp_path / "a"]) is False


def test_resolve_under_allowed_roots_returns_resolved_when_inside(lib):
    candidate = lib / "files" / "doc.pdf"
    assert resolve_under_allowed_roots(candidate, [lib]) == candidate.resolve()


# ===========================================================================
# validate_stored_document_path — early-return / accept branches
# ===========================================================================


def test_validate_none_and_empty_are_noops(lib):
    validate_stored_document_path(None, lib)  # no raise
    validate_stored_document_path("", lib)  # no raise


def test_validate_clean_relative_path_is_trusted(lib):
    # No absolute, no '..' -> fast path, no filesystem confinement check.
    validate_stored_document_path("files/report.pdf", lib)  # no raise


def test_validate_relative_with_parent_ref_that_stays_inside(lib):
    # Contains '..' so the confinement check engages, but resolves back inside.
    validate_stored_document_path("files/../storage/doc.pdf", lib)  # no raise


def test_validate_relative_traversal_escape_rejected(lib):
    with pytest.raises(ValueError, match="inside the library"):
        validate_stored_document_path("files/../../outside/secret.pdf", lib)


# ===========================================================================
# resolve_snapshot_record_path — accept + absolute reject
# ===========================================================================


def test_snapshot_clean_relative_resolves_inside(tmp_path):
    snapshots = tmp_path / "snapshots"
    result = resolve_snapshot_record_path(snapshots, "sub/record.json")
    assert result == (snapshots / "sub" / "record.json").resolve()


def test_snapshot_absolute_rejected(tmp_path):
    with pytest.raises(ValueError, match="relative"):
        resolve_snapshot_record_path(tmp_path / "snapshots", "/etc/passwd")

"""Tests for fichero.library_discovery — the depth-2 ``*.fichero`` walk.

This module was extracted from ``__main__`` in #3163 so the API server could
import it without pulling in ``typer``; it had no direct coverage. These lock
in the depth cap, dedup, and error-skipping behaviour (all of which the engine
startup-recovery path relies on).
"""
from __future__ import annotations

from pathlib import Path

from fichero.library_discovery import _discover_libraries


def _mk(root: Path, rel: str) -> Path:
    p = root / rel
    p.mkdir(parents=True, exist_ok=True)
    return p


def test_empty_roots_return_nothing(tmp_path: Path) -> None:
    assert _discover_libraries(roots=(tmp_path,)) == []


def test_nonexistent_root_is_skipped(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist"
    assert _discover_libraries(roots=(missing,)) == []


def test_depth_1_library_is_found(tmp_path: Path) -> None:
    lib = _mk(tmp_path, "Foo.fichero")
    assert _discover_libraries(roots=(tmp_path,)) == [str(lib.resolve())]


def test_depth_2_library_is_found(tmp_path: Path) -> None:
    lib = _mk(tmp_path, "SomeFolder/Bar.fichero")
    assert _discover_libraries(roots=(tmp_path,)) == [str(lib.resolve())]


def test_depth_3_library_is_NOT_found(tmp_path: Path) -> None:
    # Depth cap is 2 on purpose (unbounded walk is slow + noisy).
    _mk(tmp_path, "A/B/TooDeep.fichero")
    assert _discover_libraries(roots=(tmp_path,)) == []


def test_root_itself_never_matches(tmp_path: Path) -> None:
    # Even if the root dir is named *.fichero, depth-0 is not collected.
    root = _mk(tmp_path, "Root.fichero")
    assert _discover_libraries(roots=(root,)) == []


def test_non_fichero_dirs_are_ignored(tmp_path: Path) -> None:
    _mk(tmp_path, "NotALibrary")
    _mk(tmp_path, "Nested/AlsoNot")
    assert _discover_libraries(roots=(tmp_path,)) == []


def test_results_are_sorted_and_deduped(tmp_path: Path) -> None:
    b = _mk(tmp_path, "B.fichero")
    a = _mk(tmp_path, "A.fichero")
    # A symlinked root that resolves to the same place must not double-count.
    link_root = tmp_path / "link"
    try:
        link_root.symlink_to(tmp_path, target_is_directory=True)
        roots: tuple[Path, ...] = (tmp_path, link_root)
    except OSError:
        roots = (tmp_path,)
    result = _discover_libraries(roots=roots)
    assert result == sorted({str(a.resolve()), str(b.resolve())})


def test_multiple_roots_are_merged(tmp_path: Path) -> None:
    r1 = _mk(tmp_path, "r1")
    r2 = _mk(tmp_path, "r2")
    a = _mk(r1, "One.fichero")
    b = _mk(r2, "Two.fichero")
    result = _discover_libraries(roots=(r1, r2))
    assert result == sorted([str(a.resolve()), str(b.resolve())])


def test_unreadable_subdir_is_skipped_not_fatal(tmp_path: Path, monkeypatch) -> None:
    # An OSError while walking one entry must not abort discovery of siblings.
    good = _mk(tmp_path, "Good.fichero")
    bad = _mk(tmp_path, "BadDir")
    real_iterdir = Path.iterdir

    def flaky_iterdir(self: Path):
        if self == bad:
            raise PermissionError("denied")
        return real_iterdir(self)

    monkeypatch.setattr(Path, "iterdir", flaky_iterdir)
    # The bad depth-1 dir raises inside the inner loop; discovery keeps going
    # and still returns the good library.
    assert _discover_libraries(roots=(tmp_path,)) == [str(good.resolve())]

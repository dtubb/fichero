"""Kraken build-time bundling script (#4959) — pure tests, no real pip/network.

Three failure modes the manager's trial against a REAL bundle copy exposed
(2026-09-20), each pinned here:

1. A scratch-venv `pip --dry-run` cannot see torchvision missing (kraken's
   OWN --no-deps install hides its transitive pin from pip) — the pinned
   list must come from `pyproject.toml`, not a rebuilt-by-hand list here.
2. Running with the WRONG Python (the shebang's `env python3` on this
   machine is 3.14; the bundle is 3.12) would fill a cp312 bundle with
   cp314 wheels — the script must refuse.
3. `pip install --target`'s "leave it alone" safety only covers a name
   already on disk; a dependency resolving at a DIFFERENT version drops a
   SECOND dist-info for one project, which the OLD safety check (mtime of
   pre-existing names only) did not see.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_SCRIPT = (
    Path(__file__).resolve().parents[4] / "scripts" / "install_kraken_into_engine_bundle.py"
)
_SPEC = importlib.util.spec_from_file_location("install_kraken_into_engine_bundle", _SCRIPT)
assert _SPEC and _SPEC.loader
ikieb = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = ikieb
_SPEC.loader.exec_module(ikieb)  # type: ignore[attr-defined]


# --- name normalization ------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("NumPy", "numpy"),
        ("scikit-image", "scikit-image"),
        ("scikit_image", "scikit-image"),
        ("scikit.image", "scikit-image"),
        ("Torch-Vision", "torch-vision"),
        ("A---B__C.D", "a-b-c-d"),
    ],
)
def test_normalize_matches_pep_503(raw: str, expected: str) -> None:
    assert ikieb._normalize(raw) == expected


# --- reading dist-info + duplicate detection ---------------------------------


def _write_dist_info(app_packages: Path, dirname: str, name: str, version: str) -> None:
    d = app_packages / dirname
    d.mkdir(parents=True)
    (d / "METADATA").write_text(f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n", encoding="utf-8")


def test_dist_info_name_versions_reads_name_and_version(tmp_path: Path) -> None:
    app_packages = tmp_path / "app_packages"
    _write_dist_info(app_packages, "numpy-2.5.2.dist-info", "numpy", "2.5.2")

    result = ikieb._dist_info_name_versions(app_packages)

    assert result == {"numpy": [("numpy", "2.5.2")]}


def test_two_dist_info_for_one_project_is_a_reportable_duplicate(tmp_path: Path) -> None:
    """The exact shape from the manager's trial: pip resolves a dependency at
    a DIFFERENT version than the one already in the bundle and drops a
    SECOND dist-info folder for the same (normalized) project name."""
    app_packages = tmp_path / "app_packages"
    _write_dist_info(app_packages, "numpy-2.5.2.dist-info", "numpy", "2.5.2")
    _write_dist_info(app_packages, "numpy-2.5.4.dist-info", "numpy", "2.5.4")

    result = ikieb._dist_info_name_versions(app_packages)

    assert result["numpy"] == [("numpy", "2.5.2"), ("numpy", "2.5.4")]
    assert len(result["numpy"]) > 1  # this is what `install()` treats as a failure


def test_dist_info_without_a_metadata_file_is_skipped(tmp_path: Path) -> None:
    app_packages = tmp_path / "app_packages"
    (app_packages / "broken.dist-info").mkdir(parents=True)

    assert ikieb._dist_info_name_versions(app_packages) == {}


def test_constraints_file_pins_every_existing_distribution(tmp_path: Path) -> None:
    app_packages = tmp_path / "app_packages"
    _write_dist_info(app_packages, "numpy-2.5.2.dist-info", "numpy", "2.5.2")
    _write_dist_info(app_packages, "Torch-2.14.0.dist-info", "Torch", "2.14.0")
    dest = tmp_path / "constraints.txt"

    ikieb._write_constraints_file(app_packages, dest)

    lines = set(dest.read_text(encoding="utf-8").splitlines())
    assert lines == {"numpy==2.5.2", "Torch==2.14.0"}


# --- the python-version guard (item 2) ---------------------------------------


def _make_bundle(tmp_path: Path, *, cpython_tag: str | None) -> Path:
    app_packages = tmp_path / "app_packages"
    app_packages.mkdir()
    _write_dist_info(app_packages, "kraken-7.1.1.dist-info", "kraken", "7.1.1")
    if cpython_tag is not None:
        (app_packages / f"_fake.{cpython_tag}-darwin.so").write_bytes(b"\x00")
    return app_packages


def test_bundle_python_version_reads_from_an_existing_extension(tmp_path: Path) -> None:
    app_packages = _make_bundle(tmp_path, cpython_tag="cpython-312")
    assert ikieb._bundle_python_version(app_packages) == (3, 12)


def test_bundle_python_version_is_none_without_any_compiled_extension(tmp_path: Path) -> None:
    app_packages = _make_bundle(tmp_path, cpython_tag=None)
    assert ikieb._bundle_python_version(app_packages) is None


def test_install_refuses_on_a_python_version_mismatch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    app_packages = _make_bundle(tmp_path, cpython_tag="cpython-312")
    monkeypatch.setattr(ikieb.sys, "version_info", (3, 14, 5, "final", 0))

    def _boom(*args, **kwargs):
        raise AssertionError("pip must never run when the interpreter is wrong")

    monkeypatch.setattr(ikieb, "_run_pip", _boom)

    assert ikieb.install(app_packages) == 6


def test_install_refuses_when_the_bundle_python_cannot_be_determined(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fail SAFE, not just on a confirmed mismatch: an app_packages with no
    compiled extension at all (e.g. a not-yet-populated bundle) must not be
    read as "anything goes"."""
    app_packages = _make_bundle(tmp_path, cpython_tag=None)

    def _boom(*args, **kwargs):
        raise AssertionError("pip must never run when the bundle python is unknown")

    monkeypatch.setattr(ikieb, "_run_pip", _boom)

    assert ikieb.install(app_packages) == 6


# --- the post-install safety net (item 3) ------------------------------------


def test_install_fails_when_a_dependency_lands_at_a_new_duplicate_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Simulates exactly what a REAL pip run can do even with `-c` absent or
    ignored by a future pip: land a second dist-info for an existing
    project at a different version. `install()` must catch this AFTER the
    (mocked) pip calls, not just trust the constraints file to have worked."""
    major, minor = sys.version_info[:2]
    app_packages = _make_bundle(tmp_path, cpython_tag=f"cpython-{major}{minor}")
    _write_dist_info(app_packages, "numpy-2.5.2.dist-info", "numpy", "2.5.2")

    monkeypatch.setattr(
        ikieb,
        "_kraken_bundle_table",
        lambda: {"version": "7.1.1", "missing_packages": ["scikit-image~=0.25.2"], "no_deps_packages": []},
    )

    written = {"done": False}

    def _fake_run_pip(app_packages, args, *, constraints):
        # Simulate pip resolving a NEW numpy version alongside the existing
        # one — but only once: `install()` calls `_run_pip` for kraken
        # itself AND for missing_packages, and this must land the extra
        # dist-info exactly once, like a real off-pin resolve would.
        if not written["done"]:
            _write_dist_info(app_packages, "numpy-2.5.4.dist-info", "numpy", "2.5.4")
            written["done"] = True

    monkeypatch.setattr(ikieb, "_run_pip", _fake_run_pip)

    assert ikieb.install(app_packages) == 3


def test_install_succeeds_when_nothing_pre_existing_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    major, minor = sys.version_info[:2]
    app_packages = _make_bundle(tmp_path, cpython_tag=f"cpython-{major}{minor}")

    monkeypatch.setattr(
        ikieb,
        "_kraken_bundle_table",
        lambda: {"version": "7.1.1", "missing_packages": [], "no_deps_packages": []},
    )
    monkeypatch.setattr(ikieb, "_run_pip", lambda *a, **k: None)

    assert ikieb.install(app_packages) == 0

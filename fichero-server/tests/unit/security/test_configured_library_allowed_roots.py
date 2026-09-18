"""Pins `harness.library-allowed` (spec: ui-test-harness): the UI-test harness sets
FICHERO_LIBRARY_ALLOWED_ROOTS to its per-run temp dir, and the engine's
`configured_library_allowed_roots()` must both parse that env var and actually
permit opening a library under it — the two halves of the claim.
"""

from __future__ import annotations

import re
from pathlib import Path

import fichero_server.security.path_security as path_security

REPO_ROOT = Path(__file__).resolve().parents[4]
HARNESS = REPO_ROOT / "fichero-server" / "scripts" / "test_engine_harness.py"


def test_harness_script_sets_library_allowed_roots_to_the_per_run_temp_dir():
    text = HARNESS.read_text(encoding="utf-8")
    assert re.search(
        r'env\["FICHERO_LIBRARY_ALLOWED_ROOTS"\]\s*=\s*str\(self\.temp_dir\)', text
    ), "test_engine_harness.py no longer whitelists its own per-run temp dir"


def test_configured_library_allowed_roots_parses_env_var(monkeypatch):
    monkeypatch.setenv("FICHERO_LIBRARY_ALLOWED_ROOTS", "")
    assert path_security.configured_library_allowed_roots() == []


def test_configured_library_allowed_roots_permits_a_library_under_it(tmp_path, monkeypatch):
    """The exact end-to-end shape the harness relies on: HOME is a disposable
    app-home (outside `tmp_path`), but a library under the allowlisted temp dir
    is still permitted."""
    allowed_dir = tmp_path / "PerRunTemp"
    allowed_dir.mkdir()
    fake_home = tmp_path / "AppHome"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("FICHERO_LIBRARY_ALLOWED_ROOTS", str(allowed_dir))

    library = allowed_dir / "Seed.fichero"
    library.mkdir()

    roots = path_security.configured_library_allowed_roots()
    assert path_security.path_within_any_root(library, roots)
    # Outside the allowlisted temp dir (e.g. the disposable app-home) stays rejected.
    assert not path_security.path_within_any_root(fake_home / "Elsewhere.fichero", roots)

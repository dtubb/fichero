"""New Library staging in the app container is creatable — and NOTHING ELSE.

The New Library flow writes `Untitled-….fichero` into the app container's
`Data/tmp` before moving it into place, and that directory was not in the
allowed roots — so a sandboxed app could not create a library inside its OWN
sandbox (engine sandbox P0 plan, option (a), approved 2026-08-08; log
evidence 08:40:09).

Like its drop-staging sibling this is a SECURITY BOUNDARY: the widening that
fixes New Library is one relaxation away from exposing every sandboxed app's
tmp (Mail's, Messages'). The denial cases are written so a wider rule fails
them — a guard never observed to fire is not protection.
"""

from __future__ import annotations

from pathlib import Path

from fichero_server.security.path_security import (
    is_sandbox_container_library_staging as _is_library_staging,
)

HOME = Path("/Users/tester")
CONTAINER = HOME / "Library" / "Containers" / "app.fichero.fichero"
MAIL = HOME / "Library" / "Containers" / "com.apple.mail"
SANDBOX_HOME = CONTAINER / "Data"


def _allowed(path: Path, home: Path = HOME) -> bool:
    return _is_library_staging(path, home)


# ---- what the fix must allow -------------------------------------------------


def test_staged_fichero_package_in_container_tmp_is_allowed():
    """Unsandboxed engine's view: the full Containers path."""
    staged = CONTAINER / "Data" / "tmp" / "Untitled-3F2A.fichero"
    assert _allowed(staged)
    # ...and files INSIDE the package while it is being assembled.
    assert _allowed(staged / "fichero.duckdb")


def test_staged_fichero_package_under_sandboxed_home_is_allowed():
    """Sandboxed engine's view: HOME is the container's Data dir, so the same
    directory is $HOME/tmp/<name>.fichero."""
    assert _allowed(SANDBOX_HOME / "tmp" / "Untitled-3F2A.fichero", home=SANDBOX_HOME)


# ---- what must stay denied ---------------------------------------------------


def test_non_fichero_files_in_container_tmp_stay_denied():
    """The suffix is the scope: tmp itself did NOT become an allowed root."""
    assert not _allowed(CONTAINER / "Data" / "tmp" / "scratch.txt")
    assert not _allowed(CONTAINER / "Data" / "tmp")
    assert not _allowed(SANDBOX_HOME / "tmp" / "scratch.txt", home=SANDBOX_HOME)


def test_other_apps_container_data_stays_denied():
    """The whole Containers tree is not a root — Mail's data stays private."""
    assert not _allowed(MAIL / "Data" / "Documents" / "Evil.fichero")
    assert not _allowed(HOME / "Library" / "Containers" / "Evil.fichero")


def test_two_components_between_containers_and_data_stay_denied():
    """Single-component container scoping, same as the two siblings."""
    nested = HOME / "Library" / "Containers" / "a" / "b" / "Data" / "tmp" / "X.fichero"
    assert not _allowed(nested)


def test_fichero_must_be_directly_under_tmp():
    """A .fichero buried deeper is not the New Library staging shape."""
    assert not _allowed(CONTAINER / "Data" / "tmp" / "nested" / "X.fichero")
    assert not _allowed(SANDBOX_HOME / "tmp" / "nested" / "X.fichero", home=SANDBOX_HOME)

"""Unit tests for the library-path allowlist (_is_allowed_library_path).

Regression coverage for the iCloud-synced ~/Documents 403 bug: when macOS
"Desktop & Documents in iCloud" is ON, ~/Documents is a symlink into
~/Library/Mobile Documents/com~apple~CloudDocs/Documents. Path.resolve()
follows that symlink, so a library at ~/Documents/Fichero/X.fichero resolved
to a path outside every allowed root and got a 403. The allowlist must now:

- accept the iCloud physical container path,
- accept ~/Documents/... whether or not Documents is symlinked into iCloud
  (dual-check of resolved + un-resolved path),
- still require a .fichero suffix,
- still reject un-allowed roots.
"""

import os
from pathlib import Path

from fichero.api.main import _is_allowed_library_path


def test_icloud_physical_documents_path_allowed():
    """A .fichero under the iCloud physical container is allowed."""
    home = Path.home()
    p = (
        home
        / "Library"
        / "Mobile Documents"
        / "com~apple~CloudDocs"
        / "Documents"
        / "Fichero"
        / "Marshall.fichero"
    )
    assert _is_allowed_library_path(str(p)) is True


def test_icloud_drive_root_path_allowed():
    """A .fichero directly under iCloud Drive is allowed."""
    home = Path.home()
    p = (
        home
        / "Library"
        / "Mobile Documents"
        / "com~apple~CloudDocs"
        / "X.fichero"
    )
    assert _is_allowed_library_path(str(p)) is True


def test_documents_symlinked_into_icloud_allowed(tmp_path, monkeypatch):
    """~/Documents/X.fichero is allowed even when Documents is a symlink
    into the iCloud container (resolve() leaves the literal Documents root)."""
    fake_home = tmp_path / "home"
    fake_home.mkdir()

    # Real iCloud-style container that Documents will point into.
    icloud_documents = (
        fake_home
        / "Library"
        / "Mobile Documents"
        / "com~apple~CloudDocs"
        / "Documents"
    )
    icloud_documents.mkdir(parents=True)

    # ~/Documents -> the iCloud container (the macOS sync behaviour).
    documents = fake_home / "Documents"
    documents.symlink_to(icloud_documents, target_is_directory=True)

    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))

    # Path expressed via the symlinked Documents folder.
    p = fake_home / "Documents" / "Fichero" / "Marshall.fichero"
    assert _is_allowed_library_path(str(p)) is True


def test_documents_plain_path_allowed():
    """A plain ~/Documents/X.fichero is allowed (non-iCloud Macs)."""
    p = Path.home() / "Documents" / "Fichero" / "X.fichero"
    assert _is_allowed_library_path(str(p)) is True


def test_desktop_path_allowed():
    """~/Desktop/X.fichero is allowed (Desktop is iCloud-syncable)."""
    p = Path.home() / "Desktop" / "X.fichero"
    assert _is_allowed_library_path(str(p)) is True


def test_home_fichero_path_allowed():
    """~/Fichero/X.fichero is allowed for Daniel's local libraries."""
    p = Path.home() / "Fichero" / "Jesuit Mapping.fichero"
    assert _is_allowed_library_path(str(p)) is True


def test_cloudstorage_box_path_allowed():
    """~/Library/CloudStorage provider roots are allowed for library packages."""
    p = (
        Path.home()
        / "Library"
        / "CloudStorage"
        / "Box-Box"
        / "Libraries"
        / "Jesuit Mapping.fichero"
    )
    assert _is_allowed_library_path(str(p)) is True


def test_home_code_path_allowed():
    """Corpus/dev libraries under ~/code are allowed."""
    p = Path.home() / "code" / "marshall_diaries" / "Marshall.fichero"
    assert _is_allowed_library_path(str(p)) is True


def test_env_configured_remote_roots_allowed(tmp_path, monkeypatch):
    """Remote/Linux engines can add server-side package roots."""
    remote_root = tmp_path / "srv" / "fichero-libraries"
    other_root = tmp_path / "mnt" / "fichero"
    monkeypatch.setenv(
        "FICHERO_LIBRARY_ALLOWED_ROOTS",
        f"  {tmp_path / 'unused'}  {os.pathsep}{remote_root},\n{other_root}",
    )

    assert _is_allowed_library_path(str(remote_root / "Remote.fichero")) is True
    assert _is_allowed_library_path(str(other_root / "Nested" / "Remote.fichero")) is True


def test_env_configured_root_directory_is_ignored(monkeypatch):
    """A broad '/' allowlist entry must not make arbitrary packages valid."""
    monkeypatch.setenv("FICHERO_LIBRARY_ALLOWED_ROOTS", "/")

    assert _is_allowed_library_path("/usr/local/Unsafe.fichero") is False


def test_non_fichero_suffix_rejected():
    """A path without a .fichero suffix is rejected."""
    p = Path.home() / "Documents" / "notes.txt"
    assert _is_allowed_library_path(str(p)) is False


def test_unallowed_root_rejected():
    """A .fichero under an un-allowed root (e.g. ~/Downloads) is rejected."""
    p = Path.home() / "Downloads" / "Y.fichero"
    assert _is_allowed_library_path(str(p)) is False


# ---------------------------------------------------------------------------
# Sandbox-container Application Support (external Debug engine + sandboxed app)
#
# Regression for the empty-sidebar / all-403 bug: the sandboxed Mac app sends
# its container library path
#   ~/Library/Containers/<id>/Data/Library/Application Support/Fichero/global.fichero
# but the UNSANDBOXED external Debug engine's Path.home() is the real home, so
# the container path was under no allowed root -> 403 on every library route.
# The Release build embeds the engine INSIDE the sandbox (home == container),
# which is why Release smoke tests never saw it.
#
# The widening is deliberately scoped: only <one container>/Data/Library/
# Application Support/... is allowed — never the whole ~/Library/Containers
# tree (that would expose every sandboxed app's private data).
# ---------------------------------------------------------------------------


def _container_app_support(container: str) -> Path:
    return (
        Path.home()
        / "Library"
        / "Containers"
        / container
        / "Data"
        / "Library"
        / "Application Support"
    )


def test_sandbox_container_app_support_uuid_allowed():
    """The sandboxed app's container Application Support library is allowed
    (UUID-named container dir, the on-disk form on newer macOS)."""
    p = (
        _container_app_support("3472B4E7-339E-41D9-B4B6-86B4BC578547")
        / "Fichero"
        / "global.fichero"
    )
    assert _is_allowed_library_path(str(p)) is True


def test_sandbox_container_app_support_bundle_id_allowed():
    """Same, via the bundle-id-named container path."""
    p = _container_app_support("app.fichero.fichero") / "Fichero" / "global.fichero"
    assert _is_allowed_library_path(str(p)) is True


def test_sandbox_container_app_support_direct_child_allowed():
    """A .fichero directly under the container's Application Support is allowed."""
    p = _container_app_support("app.fichero.fichero") / "global.fichero"
    assert _is_allowed_library_path(str(p)) is True


def test_plain_app_support_still_allowed():
    """The unsandboxed ~/Library/Application Support root still works."""
    p = Path.home() / "Library" / "Application Support" / "Fichero" / "global.fichero"
    assert _is_allowed_library_path(str(p)) is True


def test_container_root_not_blanket_allowed():
    """A .fichero directly under a container (NOT under its Data/Library/
    Application Support) is rejected — the Containers tree is not a root."""
    home = Path.home()
    assert (
        _is_allowed_library_path(
            str(home / "Library" / "Containers" / "com.apple.mail" / "Evil.fichero")
        )
        is False
    )
    assert (
        _is_allowed_library_path(
            str(
                home
                / "Library"
                / "Containers"
                / "com.apple.mail"
                / "Data"
                / "Evil.fichero"
            )
        )
        is False
    )
    assert (
        _is_allowed_library_path(
            str(
                home
                / "Library"
                / "Containers"
                / "com.apple.mail"
                / "Data"
                / "Library"
                / "Evil.fichero"
            )
        )
        is False
    )


def test_container_nested_extra_component_rejected():
    """Two components between Containers and Data must not match the scope."""
    p = (
        Path.home()
        / "Library"
        / "Containers"
        / "a"
        / "b"
        / "Data"
        / "Library"
        / "Application Support"
        / "X.fichero"
    )
    assert _is_allowed_library_path(str(p)) is False


def test_container_non_fichero_suffix_rejected():
    """The .fichero suffix requirement holds inside the container scope."""
    p = _container_app_support("app.fichero.fichero") / "Fichero" / "notes.txt"
    assert _is_allowed_library_path(str(p)) is False


def test_container_traversal_escape_rejected():
    """A ..-traversal that lexically starts inside a container but resolves
    outside every allowed root is rejected."""
    home = Path.home()
    p = f"{home}/Library/Containers/x/Data/Library/Application Support/../../../../../../../../etc/foo.fichero"
    assert _is_allowed_library_path(p) is False


def test_documents_traversal_escape_rejected():
    """A ..-traversal that lexically starts under ~/Documents but resolves to
    /etc must be rejected (is_relative_to alone is lexical and spoofable)."""
    p = f"{Path.home()}/Documents/../../../../../../etc/passwd.fichero"
    assert _is_allowed_library_path(p) is False


def test_absolute_outside_path_rejected():
    """An absolute path outside every root is rejected even with .fichero."""
    assert _is_allowed_library_path("/etc/passwd.fichero") is False


def test_benign_dotdot_within_allowed_root_still_allowed():
    """A ..-containing path that RESOLVES inside an allowed root stays allowed
    (the resolved candidate handles it; only the lexical spoof is closed)."""
    p = f"{Path.home()}/Documents/sub/../X.fichero"
    assert _is_allowed_library_path(p) is True

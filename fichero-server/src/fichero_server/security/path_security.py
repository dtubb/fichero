"""Shared filesystem confinement helpers.

Three grants, deliberately different widths (#4230):

* ``is_allowed_ingest_path`` — may this path ENTER a library? The widest list
  (``~/Desktop``, ``~/Documents``, …) and the ONE authority for ingest.
* ``resolve_document_source_path`` — may we SERVE a path this engine RECORDED
  on a document row? The library/storage roots plus the ingest roots, because
  ``IngestMode.LINK`` (the default) records the original path. Authorisation
  here is "this document was imported", not "this directory is blessed" — the
  HTTP surface reaches it only with a document id, never a client path.
* ``validate_stored_document_path`` — may a CLIENT point a document row at this
  path? The narrowest list: the library package only. Writing a path is a
  bigger grant than reading one the engine wrote itself, so this one is NOT
  widened along with the other two.

Before #4230 the first two disagreed with nothing enforcing agreement, so the
engine imported files from ``~/Desktop`` it could never serve (404 on every
thumbnail, "No source found"). ``test_ingest_serving_allowlist_agreement.py``
now fails if they diverge again.
"""

from __future__ import annotations

import logging
import os
import tempfile
import threading
from pathlib import Path
from typing import Callable, Iterable

logger = logging.getLogger(__name__)


ENGINE_TEMP_DERIVED_DIRS = (
    "fichero-image-edits",
    "fichero-rotated-images",
    "fichero-segmented-images",
    "fichero-split-images",
    "fichero-fuzzy-cleaned-images",
    "fichero-recombined-segments",
    "fichero-enhanced-images",
    "fichero-prepared-images",
    "fichero-background-removed-images",
)


def _resolved(path: Path | str) -> Path:
    return Path(path).expanduser().resolve()


def _path_within(root: Path | str, candidate: Path | str) -> bool:
    """Return True when candidate's real path is inside root's real path."""
    try:
        _resolved(candidate).relative_to(_resolved(root))
    except (OSError, RuntimeError, ValueError):
        return False
    return True


def _candidate_has_parent_ref(candidate: Path | str) -> bool:
    return ".." in Path(candidate).parts


def engine_temp_derived_roots() -> list[Path]:
    temp_root = Path(tempfile.gettempdir())
    return [temp_root / dirname for dirname in ENGINE_TEMP_DERIVED_DIRS]


def allowed_source_roots(
    library_root: Path | str | None = None,
    *,
    storage_base: Path | str | None = None,
    include_engine_temp: bool = True,
) -> list[Path]:
    """Roots the backend may serve as document source/derived files."""
    roots: list[Path] = []
    if library_root is not None:
        root = Path(library_root).expanduser()
        roots.extend(
            [
                root,
                root / "files",
                root / "storage",
                root / "artifacts",
                root / "cache",
            ]
        )
    if storage_base is not None:
        base = Path(storage_base).expanduser()
        roots.extend(
            [
                base / "files",
                base / "thumbnails",
                base / "artifacts",
                base / "cache",
            ]
        )
    if include_engine_temp:
        roots.extend(engine_temp_derived_roots())

    unique: list[Path] = []
    seen: set[Path] = set()
    for root in roots:
        try:
            resolved = _resolved(root)
        except (OSError, RuntimeError):
            continue
        if resolved in seen:
            continue
        seen.add(resolved)
        unique.append(resolved)
    return unique


def path_within_any_root(
    candidate: Path | str,
    roots: Iterable[Path | str],
) -> bool:
    return any(_path_within(root, candidate) for root in roots)


def resolve_under_allowed_roots(
    candidate: Path | str,
    roots: Iterable[Path | str],
) -> Path | None:
    try:
        resolved = _resolved(candidate)
    except (OSError, RuntimeError):
        return None
    return resolved if path_within_any_root(resolved, roots) else None


# =============================================================================
# Ingest authority — what may ENTER a library (moved here from api/main.py so
# the serving side can consult the SAME list, #4230)
# =============================================================================


def configured_library_allowed_roots() -> list[Path]:
    """Extra server-side library roots for remote/Linux engines.

    FICHERO_LIBRARY_ALLOWED_ROOTS accepts an os.pathsep-separated list and also
    tolerates commas/newlines for deployment systems that make pathsep awkward.
    The filesystem root is ignored: library access must always be scoped.
    """
    raw = os.environ.get("FICHERO_LIBRARY_ALLOWED_ROOTS", "")
    if not raw.strip():
        return []

    parts = raw.replace("\n", os.pathsep).replace(",", os.pathsep).split(os.pathsep)
    roots: list[Path] = []
    for part in parts:
        value = part.strip()
        if not value:
            continue
        root = Path(value).expanduser()
        try:
            resolved = root.resolve()
        except Exception:
            continue
        if resolved == Path(resolved.anchor):
            logger.warning("Ignoring unsafe FICHERO_LIBRARY_ALLOWED_ROOTS entry: %s", value)
            continue
        roots.append(resolved)
    return roots


def is_sandbox_container_app_support(path: Path, home: Path) -> bool:
    """True iff path is under ONE sandbox container's Application Support.

    Matches ~/Library/Containers/<container>/Data/Library/Application Support/...
    where <container> is exactly one path component (bundle id or the UUID
    form newer macOS uses on disk). This is where a sandboxed host app's own
    Application Support lives, so an UNSANDBOXED external Debug engine can
    open the sandboxed app's default library.

    ponytail: the ceiling is a single container's Data/Library/Application
    Support subtree — NEVER widen to all of ~/Library/Containers, which would
    expose every sandboxed app's private data (Mail, Messages, ...) to
    library-path reads.
    """
    try:
        parts = path.relative_to(home / "Library" / "Containers").parts
    except ValueError:
        return False
    # parts = (<container>, "Data", "Library", "Application Support", <...>+)
    # len >= 5 forces the .fichero to live BELOW Application Support.
    return len(parts) >= 5 and parts[1:4] == ("Data", "Library", "Application Support")


def is_sandbox_container_drop_staging(path: Path, home: Path) -> bool:
    """True iff path is a Finder-drop staging dir inside ONE sandbox container.

    Matches ~/Library/Containers/<container>/Data/tmp/fichero-drop-<uuid>/...
    where <container> is exactly one path component. The app stages every
    Finder drop there (`SidebarItemRow+DropHandlers.swift`), and an externally
    started engine — the default Dev Local scheme — could not read it, so every
    drop returned 403 (#4223).

    The bookmark fallback cannot rescue this: the app mints a TRANSIENT,
    unpersisted grant, and grants live in the engine process's own `_GRANTED`.
    A separately started engine has no channel to receive one.

    ponytail: this is DELIBERATELY narrower than its Application Support
    sibling. That helper accepts any single container's Application Support;
    this one additionally requires the `fichero-drop-` prefix, so it grants
    Fichero's own staging directories and nothing else. Without the prefix
    check this would open every sandboxed app's Data/tmp — Mail's, Messages' —
    which is the same exposure the sibling's comment warns against, one
    directory over. NEVER relax either the single-component container or the
    prefix.

    TWO SHAPES, because the engine sees this directory under different names
    depending on how it was started, and BOTH were denied:

    * UNSANDBOXED engine (Dev Local, DMG) — real HOME, so the drop dir is
      ~/Library/Containers/<container>/Data/tmp/fichero-drop-<uuid>/
    * SANDBOXED engine (App Store, embedded) — the sandbox redirects HOME
      INTO the container, so the SAME directory is $HOME/tmp/fichero-drop-
      <uuid>/ and the `Library/Containers` prefix never matches.

    The second shape was established by simulating the redirected HOME rather
    than assumed: without it the App Store build would ship with drag-and-drop
    still returning 403.
    """
    # Sandboxed view: HOME is already the container's Data dir.
    try:
        parts = path.relative_to(home / "tmp").parts
    except ValueError:
        pass
    else:
        return bool(parts) and parts[0].startswith("fichero-drop-")

    try:
        parts = path.relative_to(home / "Library" / "Containers").parts
    except ValueError:
        return False
    # parts = (<container>, "Data", "tmp", "fichero-drop-<uuid>", <...>*)
    # len >= 4 admits the staging directory itself (a folder drop) as well as
    # the files staged inside it.
    return (
        len(parts) >= 4
        and parts[1:3] == ("Data", "tmp")
        and parts[3].startswith("fichero-drop-")
    )


def is_sandbox_container_library_staging(path: Path, home: Path) -> bool:
    """True iff path is a .fichero package staged in ONE sandbox container's tmp.

    The New Library flow creates `Untitled-….fichero` under the app
    container's `Data/tmp` before moving it into place — and that directory
    was not in the allowed roots, so a sandboxed app could not create a
    library inside its OWN sandbox (engine sandbox P0 plan, option (a),
    approved by Daniel 2026-08-08; log evidence 08:40:09).

    Same TWO SHAPES as `is_sandbox_container_drop_staging` (see its docstring
    for why): the sandboxed engine sees the container tmp as `$HOME/tmp`, the
    unsandboxed one as `~/Library/Containers/<container>/Data/tmp`.

    ponytail: like its drop-staging sibling this is DELIBERATELY narrower
    than the tmp directory — the first component under tmp must itself be a
    `.fichero` package, so it admits Fichero's own library staging and
    nothing else in any container's tmp. NEVER relax the single-component
    container or the suffix.
    """
    try:
        parts = path.relative_to(home / "tmp").parts
    except ValueError:
        pass
    else:
        return bool(parts) and parts[0].endswith(".fichero")

    try:
        parts = path.relative_to(home / "Library" / "Containers").parts
    except ValueError:
        return False
    # parts = (<container>, "Data", "tmp", "<name>.fichero", <...>*)
    return (
        len(parts) >= 4
        and parts[1:3] == ("Data", "tmp")
        and parts[3].endswith(".fichero")
    )


def ingest_allowed_roots() -> list[Path]:
    """Directory roots a file may be imported FROM.

    Enumerated (rather than only answered as a yes/no predicate) so the
    agreement guardrail can walk the list and assert every entry is servable
    once a document records it — see the module docstring and #4230.

    The two sandbox-container shapes are NOT roots: they are pattern rules on
    a single container and stay in their helpers.
    """
    home = Path.home().resolve()
    icloud = home / "Library" / "Mobile Documents" / "com~apple~CloudDocs"
    return [
        home / "Documents",
        home / "Desktop",
        home / "Fichero",
        home / "Dropbox",
        home / "code",
        home / "Library" / "Application Support",
        home / "Library" / "CloudStorage",
        icloud,
        Path("/var/folders"),
        Path("/private/var/folders"),
        Path("/tmp"),
        Path("/private/tmp"),
        *configured_library_allowed_roots(),
        *_granted_roots(),
    ]


def _granted_roots() -> list[Path]:
    """Security-scoped bookmark grants held by THIS engine process."""
    from fichero_server.security.security_scoped_access import granted_paths

    roots: list[Path] = []
    for grant in granted_paths():
        try:
            roots.append(Path(grant).expanduser().resolve())
        except (OSError, RuntimeError):
            continue
    return roots


# Library packages the engine's OWNER opened through ``POST /api/registry/add`` this
# process (#5464). An unsandboxed engine (Dev Local external, a server) cannot read the
# app's bookmarks, so a project the app opened in a folder outside the fixed roots (say
# ~/Fichero Test Library) was refused on every request by its own engine. Exact packages
# only — never their folder — and only from the owner (loopback + bootstrap token), so a
# remote caller still cannot widen what this engine opens (audit A1's concern).
_OPENED_PACKAGES: set[str] = set()


def _package_key(path: str | Path) -> str | None:
    import unicodedata

    try:
        resolved = Path(path).expanduser().resolve()
    except (OSError, RuntimeError, ValueError):
        return None
    return unicodedata.normalize("NFC", str(resolved))


def note_owner_opened_package(path: str | Path) -> bool:
    """Allow one existing ``.fichero`` package the owner opened. Returns whether it was noted."""
    key = _package_key(path)
    if key is None or not key.endswith(".fichero") or not Path(key).is_dir():
        return False
    _OPENED_PACKAGES.add(key)
    return True


def forget_owner_opened_package(path: str | Path) -> None:
    key = _package_key(path)
    if key is not None:
        _OPENED_PACKAGES.discard(key)


def is_owner_opened_package(path: str | Path) -> bool:
    """Is ``path`` exactly a package the owner opened (after resolving symlinks and ``..``)?"""
    key = _package_key(path)
    return key is not None and key in _OPENED_PACKAGES


# Folders the engine's OWNER picked in the app's own panel (setup › Add a Folder…, File ›
# Import…) and handed over through ``POST /api/sandbox/security-scoped-access`` (#5484). An
# unsandboxed engine cannot use the app's bookmark (audit A1), so the owner's pick itself is the
# grant: that exact folder (resolved) and everything under it. Owner only (loopback + bootstrap
# token); a paired device or remote session never adds one. Persisted by the route in the global
# DB's ``owner_granted_folders`` and loaded back once per process through the loader the registry
# routes register below, like the owner-opened packages (#5464).
_OWNER_GRANTED_FOLDERS: set[str] = set()
_OWNER_GRANT_LOADER: Callable[[], None] | None = None
_OWNER_GRANT_LOADING = threading.local()

# Never grantable, whoever asks: the system's own folders. Their contents are not an archive.
_SYSTEM_FOLDERS = (
    "/System", "/Library", "/usr", "/bin", "/sbin", "/etc", "/private/etc", "/var", "/private/var",
    "/dev", "/cores", "/opt", "/Applications",
)
# Refused only as themselves: a drive or share under them is where archives often live.
_MOUNT_FOLDERS = ("/Volumes", "/Network")
# …except the per-user temp folders under /var, which are already ingest roots (CI, test runs).
_SYSTEM_FOLDER_EXCEPTIONS = ("/var/folders", "/private/var/folders")
# ~/Library is refused except where synced drives keep people's files (iCloud Drive, Dropbox,
# Google Drive, OneDrive): a folder under these is material; the two parents themselves are not.
_HOME_LIBRARY_EXCEPTIONS = ("Library/Mobile Documents", "Library/CloudStorage")


class OwnerFolderGrantRefused(ValueError):
    """The owner's pick cannot be allowed. The message says why, in one sentence."""


def set_owner_grant_loader(loader: Callable[[], None] | None) -> None:
    """Register the once-per-process loader of persisted owner grants (set by the registry routes)."""
    global _OWNER_GRANT_LOADER
    _OWNER_GRANT_LOADER = loader


def _load_owner_grants() -> None:
    loader = _OWNER_GRANT_LOADER
    if loader is None or getattr(_OWNER_GRANT_LOADING, "active", False):
        return  # not wired (a bare unit test), or already loading on this thread (no recursion)
    _OWNER_GRANT_LOADING.active = True
    try:
        loader()
    except Exception as exc:  # fail closed: nothing loaded
        logger.warning("Could not load the owner's granted folders: %s", exc)
    finally:
        _OWNER_GRANT_LOADING.active = False


def owner_folder_grant_key(path: str | Path) -> str:
    """The resolved key the owner's pick is allowed under, or raise ``OwnerFolderGrantRefused``.

    Fail closed: a path with ``..`` (the panel never sends one), one that does not exist, and a
    system folder (``/``, ``/System``, …, HOME itself or an ancestor of it, ``~/Library``, a hidden
    folder of HOME) are refused. Symlinks are resolved first, so a link to a system folder is that
    system folder.
    """
    import unicodedata

    raw = Path(path).expanduser()
    if not raw.is_absolute() or ".." in raw.parts:
        raise OwnerFolderGrantRefused(f"Fichero allows only a folder picked by its full path, not {path}.")
    try:
        resolved = raw.resolve(strict=True)
    except (OSError, RuntimeError, ValueError):
        raise OwnerFolderGrantRefused(f"{path} does not exist.") from None
    home = Path.home().resolve()
    system = [Path(p) for p in _SYSTEM_FOLDERS]
    if (
        resolved == Path(resolved.anchor)
        or resolved == home
        or home.is_relative_to(resolved)
        or (
            any(resolved.is_relative_to(root) for root in system)
            and not any(resolved.is_relative_to(Path(p)) for p in _SYSTEM_FOLDER_EXCEPTIONS)
        )
        or resolved in [Path(p) for p in _MOUNT_FOLDERS]
        or (
            resolved.is_relative_to(home / "Library")
            and not any(
                resolved.is_relative_to(home / e) and resolved != home / e for e in _HOME_LIBRARY_EXCEPTIONS
            )
        )
        or (resolved.is_relative_to(home) and resolved.relative_to(home).parts[0].startswith("."))
    ):
        raise OwnerFolderGrantRefused(
            f"{resolved} is a system folder; choose the folder that holds your material instead."
        )
    return unicodedata.normalize("NFC", str(resolved))


def note_owner_granted_folder(path: str | Path) -> str:
    """Allow one folder the owner picked (and everything under it). Returns its resolved key."""
    key = owner_folder_grant_key(path)
    _OWNER_GRANTED_FOLDERS.add(key)
    return key


def is_owner_granted_folder(path: str | Path) -> bool:
    """Is ``path`` exactly a folder the owner picked (already noted), after resolving?"""
    try:
        return owner_folder_grant_key(path) in _OWNER_GRANTED_FOLDERS
    except OwnerFolderGrantRefused:
        return False


def _within_owner_granted_folder(candidate: Path) -> bool:
    _load_owner_grants()  # once per process; the loader returns at once after its first success
    return any(candidate.is_relative_to(Path(folder)) for folder in tuple(_OWNER_GRANTED_FOLDERS))


def is_allowed_ingest_path(path: str | Path) -> bool:
    """Return whether a local file path is below an engine-approved root.

    Symlink tolerance: when "Desktop & Documents in iCloud" is ON, ~/Documents
    is a symlink into ~/Library/Mobile Documents/com~apple~CloudDocs/Documents,
    so BOTH the resolved and the un-resolved form are tested.
    """
    try:
        expanded = Path(path).expanduser()
        resolved = expanded.resolve()
    except Exception:
        return False

    home = Path.home().resolve()
    allowed_roots = ingest_allowed_roots()
    candidates = [resolved]
    if ".." not in expanded.parts:
        candidates.append(expanded)
    return any(
        candidate.is_relative_to(root)
        for candidate in candidates
        for root in allowed_roots
    ) or any(
        is_sandbox_container_app_support(candidate, home) for candidate in candidates
    ) or any(
        is_sandbox_container_drop_staging(candidate, home) for candidate in candidates
    ) or any(
        is_sandbox_container_library_staging(candidate, home) for candidate in candidates
    ) or _within_owner_granted_folder(resolved)  # #5484: the RESOLVED path only, so `..` and links can't escape


def resolve_document_source_path(
    candidate: Path | str,
    library_root: Path | str | None = None,
    *,
    storage_base: Path | str | None = None,
) -> Path | None:
    """Resolve a path RECORDED ON A DOCUMENT and confine it.

    Accepts the library/storage/derived roots *or* anywhere a file could
    legitimately have been imported from, because ``IngestMode.LINK`` — the
    default — records the original path (#4230). Never call this with a
    client-supplied path: the grant is "this document was imported", and the
    only callers are the source/derivative resolvers, reached by document id.

    The wider half applies ONLY to an absolute, ``..``-free path — i.e. the
    shape ingest records for a LINK import. A package-relative path that
    escapes via ``..`` gets the narrow roots and nothing more, so
    ``path="../outside.txt"`` stays a 404 (test_routes_storage's confinement
    case caught exactly this while the widening was being written).
    """
    resolved = resolve_under_allowed_roots(
        candidate,
        allowed_source_roots(library_root, storage_base=storage_base),
    )
    if resolved is not None:
        return resolved
    raw = Path(candidate).expanduser()
    if not raw.is_absolute() or _candidate_has_parent_ref(raw):
        return None
    if not is_allowed_ingest_path(candidate):
        return None
    try:
        return _resolved(candidate)
    except (OSError, RuntimeError):
        return None


def validate_stored_document_path(
    path: str | None,
    library_root: Path | str,
    *,
    storage_base: Path | str | None = None,
) -> None:
    """Reject stored document paths that can resolve outside trusted roots."""
    if not path:
        return

    candidate = Path(path).expanduser()
    if not candidate.is_absolute() and not _candidate_has_parent_ref(candidate):
        return

    if not candidate.is_absolute():
        candidate = Path(library_root).expanduser() / candidate

    roots = allowed_source_roots(
        library_root,
        storage_base=storage_base,
        include_engine_temp=True,
    )
    if not path_within_any_root(candidate, roots):
        raise ValueError("Document path must stay inside the library package")


def resolve_snapshot_record_path(snapshots_dir: Path | str, record_path: str) -> Path:
    """Resolve a snapshot record path and require it to stay in snapshots_dir."""
    candidate = Path(record_path)
    if candidate.is_absolute() or _candidate_has_parent_ref(candidate):
        raise ValueError("Snapshot record path must be relative to snapshots dir")
    resolved = _resolved(Path(snapshots_dir) / candidate)
    if not _path_within(snapshots_dir, resolved):
        raise ValueError("Snapshot record path escapes snapshots dir")
    return resolved

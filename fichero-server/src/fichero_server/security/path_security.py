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
from pathlib import Path
from typing import Iterable

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
    )


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

"""Library-path discovery, split out from the CLI entrypoint.

This lived in ``fichero.__main__`` next to the Typer CLI, but the API server
imports ``_discover_libraries`` for startup recovery — and importing
``__main__`` drags in ``import typer`` at module load. ``typer`` is a CLI-only
dependency that the Briefcase-bundled engine does NOT ship, so the import blew
up with ``ModuleNotFoundError: No module named 'typer'`` and silently broke
startup library-discovery recovery in the packaged app (#3163 follow-up).

Keeping this pure (only ``pathlib``) lets both the CLI and the embedded engine
import it without pulling in ``typer``.
"""

from __future__ import annotations

from pathlib import Path

# Allowlist roots walked (up to depth 2) for ``*.fichero`` libraries. Small,
# curated set — an unbounded walk of ``~/Library/Application Support`` is slow
# and noisy. Read at call time (not captured at definition) so tests can
# ``monkeypatch.setattr(library_discovery, "_LIBRARY_LIST_ROOTS", ...)``.
_LIBRARY_LIST_ROOTS = (
    Path.home() / "Documents",
    Path.home() / "Dropbox",
    Path.home() / "code",
    Path.home() / "Library" / "Application Support",
)


def _discover_libraries(roots: tuple[Path, ...] | None = None) -> list[str]:
    """Walk the allowlist roots up to depth 2 and collect ``*.fichero`` paths.

    Depth cap is small on purpose — Daniel's libraries live one or two levels
    below ``~/Documents`` (or ``~/Dropbox``), and an unbounded walk over
    ``~/Library/Application Support`` is slow and pulls in noise we don't
    care about.

    ``roots`` defaults to ``_LIBRARY_LIST_ROOTS`` resolved at call time (not
    at function definition) so tests can ``monkeypatch.setattr`` it.
    """
    if roots is None:
        roots = _LIBRARY_LIST_ROOTS
    found: list[str] = []
    for root in roots:
        if not root.exists():
            continue
        # Depth 0: the root itself never matches (no .fichero suffix).
        # Depth 1: ~/Documents/Foo.fichero
        # Depth 2: ~/Documents/SomeFolder/Foo.fichero
        for entry in root.iterdir():
            try:
                if entry.is_dir() and entry.suffix == ".fichero":
                    found.append(str(entry.resolve()))
                elif entry.is_dir():
                    for sub in entry.iterdir():
                        if sub.is_dir() and sub.suffix == ".fichero":
                            found.append(str(sub.resolve()))
            except OSError:
                # Permission denied / broken symlink — skip and keep going.
                continue
    # De-dup (resolved paths can collide across roots via symlinks) and sort
    # for deterministic output.
    return sorted(set(found))

"""Single Python resolver for the shared, cross-layer fixture library.

The canonical specimen files live at the REPO root in ``test-fixtures/files``
(shared with the Swift test targets, which resolve the same tree through
``TestFixtures.swift``). Engine-only fixtures (contract JSON, paleography)
stay under ``fichero-engine/tests/fixtures``.

Usage::

    from tests.fixture_paths import sample_file, SAMPLE_FILES_DIR

    pdf = sample_file("multipage.pdf")
"""

from __future__ import annotations

from pathlib import Path

# tests/fixture_paths.py -> tests -> fichero-engine -> <repo root>
REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLE_FILES_DIR = REPO_ROOT / "test-fixtures" / "files"


def sample_file(name: str) -> Path:
    """Return the path of one shared specimen; raise if it is missing.

    Raising (never returning a dangling path) keeps a typo or an unsynced
    checkout from surfacing later as a confusing downstream failure.
    """
    path = SAMPLE_FILES_DIR / name
    if not path.is_file():
        raise FileNotFoundError(
            f"shared fixture missing: {path} — expected in test-fixtures/files/"
        )
    return path

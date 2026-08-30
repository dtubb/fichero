"""The two LICENSE files are one license (2026-08-27 relicense).

fichero-server ships standalone via Briefcase, so pyproject's
``license.file = "LICENSE"`` must name a REAL file inside fichero-server/ —
a symlink to the repo root would break the sdist. The price of the copy is
drift, and this test is the price's receipt: byte-identical, always.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_server_license_is_byte_identical_to_root():
    root_license = (ROOT / "LICENSE").read_bytes()
    server_license = (ROOT / "fichero-server" / "LICENSE").read_bytes()
    assert root_license == server_license, (
        "fichero-server/LICENSE drifted from the root LICENSE — copy the root "
        "file over it (Briefcase packaging needs the real copy; see docstring)"
    )


def test_the_license_is_the_agpl():
    text = (ROOT / "LICENSE").read_text(encoding="utf-8")
    assert "GNU AFFERO GENERAL PUBLIC LICENSE" in text.splitlines()[0].strip().upper() or \
        "GNU AFFERO" in text[:200].upper(), (
        "the root LICENSE is no longer the AGPL — LICENSING.md, NOTICE, CLA.md "
        "and the site all state AGPL-3.0; change them together or not at all"
    )

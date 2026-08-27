"""The engine's mimetypes seeding must never read the filesystem.

The sandbox denies /etc/apache2/mime.types. The first fix used
``mimetypes.init(files=[])`` — which APPENDS to knownfiles and still read
/etc, crashing the engine at boot (live, 2026-08-27, twice)."""

from __future__ import annotations

import mimetypes


def test_seed_skips_unreadable_known_files(tmp_path, monkeypatch):
    denied = tmp_path / "mime.types"
    denied.write_text("application/x-nope nope\n")
    denied.chmod(0o000)

    from fichero_server.__main__ import _seed_mimetypes_from_builtins

    # Simulate the sandbox: the only known file raises PermissionError on
    # open. The seed must neither raise nor read it.
    monkeypatch.setattr(mimetypes, "knownfiles", [str(denied)])
    _seed_mimetypes_from_builtins()

    kind, _ = mimetypes.guess_type("page.png")
    assert kind == "image/png", "built-in table must be live after seeding"
    assert mimetypes.guess_type("x.nope")[0] is None, (
        "the denied file must not have been read"
    )

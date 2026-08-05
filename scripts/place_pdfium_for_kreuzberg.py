#!/usr/bin/env python3
"""Put libpdfium.dylib where kreuzberg's Rust binding will actually look for it.

## Why this exists

kreuzberg ships no ``libpdfium.dylib``. Its Rust binding
(``kreuzberg/_internal_bindings.abi3.so``) resolves the library by
``@loader_path/libpdfium.dylib`` — i.e. *beside the binding itself* — and when
that file is absent it extracts a copy into a temp directory at first use.

On macOS that fallback cannot work in a shipped app. A file the app writes gets
``com.apple.quarantine`` stamped on it, the copy is only ad-hoc/linker-signed,
and Gatekeeper refuses to ``dlopen`` it:

    "libpdfium.dylib" Not Opened — Apple could not verify "libpdfium.dylib" is
    free of malware that may harm your Mac or compromise your privacy.

The engine then logs ``Kreuzberg extraction failed (ParsingError: ... Pdfium
initialization failed ...)`` and falls back to fitz for page splitting (#2430),
so a PDF imports as page images with **no searchable text**. Observed on
2026-08-04; it would happen on every machine, because a dylib fetched at runtime
can never inherit the app's notarization.

Adding ``pypdfium2`` to the briefcase requires puts a real ``libpdfium.dylib``
in the bundle, where the app's codesign pass covers it — but it lands in
``pypdfium2_raw/``, which is not ``@loader_path``. This script closes that gap
by placing it beside the binding. Run it AFTER ``briefcase build`` (so
app_packages exists) and BEFORE the codesign pass, so the placed file is signed
with everything else.

Idempotent: an existing, identical file is left alone.

## Usage

    python3 scripts/place_pdfium_for_kreuzberg.py <path-to-app_packages>

Exits non-zero with a specific reason if it cannot do its job — never silently,
because a silent skip here reappears as "PDFs have no text" weeks later, far
from its cause.
"""

from __future__ import annotations

import filecmp
import shutil
import sys
from pathlib import Path

DYLIB = "libpdfium.dylib"


def find_source(app_packages: Path) -> Path | None:
    """The dylib pypdfium2 shipped, wherever in its package it landed."""
    for candidate in app_packages.glob(f"pypdfium2*/**/{DYLIB}"):
        return candidate
    return None


def place(app_packages: Path) -> int:
    binding_dir = app_packages / "kreuzberg"
    if not binding_dir.is_dir():
        print(f"error: no kreuzberg package under {app_packages}", file=sys.stderr)
        return 2

    source = find_source(app_packages)
    if source is None:
        print(
            f"error: no {DYLIB} under {app_packages}/pypdfium2*/ — is pypdfium2 in\n"
            "       the briefcase `requires`? Without it the binding extracts a\n"
            "       quarantined copy at runtime and PDF text extraction fails.",
            file=sys.stderr,
        )
        return 3

    destination = binding_dir / DYLIB
    if destination.exists() and filecmp.cmp(source, destination, shallow=False):
        print(f"ok: {destination} already matches {source}")
        return 0

    # A real copy, not a symlink: codesign signs the file it finds, and a
    # symlink out of the signed directory is not what gets sealed.
    shutil.copy2(source, destination)
    print(f"placed: {source} -> {destination}")
    return 0


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 1
    app_packages = Path(argv[1])
    if not app_packages.is_dir():
        print(f"error: not a directory: {app_packages}", file=sys.stderr)
        return 1
    return place(app_packages)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

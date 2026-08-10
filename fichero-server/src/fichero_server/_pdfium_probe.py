"""Kreuzberg PDF worker + probe, run OUT-OF-PROCESS (#4555).

Run VIA THE BRIEFCASE STUB with ``BRIEFCASE_MAIN_MODULE=fichero_server._pdfium_probe``
— the shipped engine bundles no standalone python binary, and the stub with
its default module boots a whole second engine. Dev/venv layouts run this
with ``python -m``.

WHY OUT-OF-PROCESS (measured live, 2026-08-09/10, faulthandler dumps):
kreuzberg's sync Rust FFI holds the GIL while its worker threads call back
into Python; any LAZY import in that callback (charset_normalizer one dump,
uuid_utils the next) deadlocks against the import lock and freezes EVERY
thread in the engine — health goes dark, the watchdog SIGKILLs. Pre-import
lists don't converge; isolation does. A hang or crash lands here, in a
throwaway child the parent kills on timeout, never in the engine.

Modes (env-driven):
- FICHERO_KREUZBERG_EXTRACT_INPUT/_OUTPUT set: extract per-page records
  from the input PDF and write {"pages": [...]} JSON to the output path.
- FICHERO_PDFIUM_PROBE_PDF set: bind pdfium by extracting the probe PDF,
  exit 0 on success (the availability gate).
"""

import json
import os
import sys


def main() -> None:
    extract_in = os.environ.get("FICHERO_KREUZBERG_EXTRACT_INPUT")
    extract_out = os.environ.get("FICHERO_KREUZBERG_EXTRACT_OUTPUT")
    probe = os.environ.get("FICHERO_PDFIUM_PROBE_PDF")

    import kreuzberg

    if extract_in and extract_out:
        cfg = kreuzberg.ExtractionConfig(
            pages=kreuzberg.PageConfig(extract_pages=True)
        )
        result = kreuzberg.extract_file_sync(extract_in, None, cfg)
        with open(extract_out, "w", encoding="utf-8") as f:
            json.dump({"pages": result.pages or []}, f, default=str)
        sys.exit(0)

    if probe:
        kreuzberg.extract_file_sync(probe, None, kreuzberg.ExtractionConfig())
        sys.exit(0)

    print("no mode env set", file=sys.stderr)
    sys.exit(64)


main()

"""Subprocess probe target for kreuzberg_pdf_usable() (#4555).

Run VIA THE BRIEFCASE STUB with ``BRIEFCASE_MAIN_MODULE=fichero_server._pdfium_probe``
— the shipped engine bundles no standalone python binary, and the stub with
its default module boots a whole second engine (which died on the DuckDB
lock, measured live). This module does exactly one thing: bind pdfium by
extracting a one-page PDF, then exit 0. Any hang or crash lands here, in a
throwaway child, never in the engine.
"""

import os
import sys


def main() -> None:
    path = os.environ.get("FICHERO_PDFIUM_PROBE_PDF")
    if not path:
        print("FICHERO_PDFIUM_PROBE_PDF not set", file=sys.stderr)
        sys.exit(64)
    import kreuzberg

    kreuzberg.extract_file_sync(path, None, kreuzberg.ExtractionConfig())
    sys.exit(0)


main()

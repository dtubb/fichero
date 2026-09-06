"""Kreuzberg PDF worker + probe entry point for the DEV/VENV `python -m` child.

This module is the dev/venv out-of-process shape only — `python -m
fichero_server._pdfium_probe`, a real child interpreter. The shipped BUNDLE
does NOT run this module via its Briefcase stub: re-execing the stub as a
grandchild wedges in `_libsecinit_appsandbox` (the stub carries
`{app-sandbox, inherit}`, and `inherit` is single-level, so the engine — itself
an inherit child — cannot be the sandbox-parent of another inherit child). The
bundle instead fork()s the worker in-process; see
`kreuzberg_cache._fork_worker`. Both shapes run the same body,
`kreuzberg_cache.run_worker_from_env()`.

WHY OUT-OF-PROCESS (measured live, 2026-08-09/10, faulthandler dumps):
kreuzberg's sync Rust FFI holds the GIL while its worker threads call back
into Python; any LAZY import in that callback (charset_normalizer one dump,
uuid_utils the next) deadlocks against the import lock and freezes EVERY
thread in the engine — health goes dark, the watchdog SIGKILLs. Pre-import
lists don't converge; isolation does. A hang or crash lands in a throwaway
child the parent kills on timeout, never in the engine.

Modes (env-driven), handled by run_worker_from_env():
- FICHERO_KREUZBERG_EXTRACT_INPUT/_OUTPUT set: extract per-page records
  from the input PDF and write {"pages": [...]} JSON to the output path.
- FICHERO_PDFIUM_PROBE_PDF set: bind pdfium by extracting the probe PDF,
  exit 0 on success (the availability gate).
"""

import sys


def main() -> None:
    # The worker body lives in kreuzberg_cache so the dev `python -m` child
    # (here) and the shipped-bundle fork() child (kreuzberg_cache._fork_worker)
    # run EXACTLY the same code — see run_worker_from_env's docstring.
    from fichero_server.loaders import kreuzberg_cache

    sys.exit(kreuzberg_cache.run_worker_from_env())


main()

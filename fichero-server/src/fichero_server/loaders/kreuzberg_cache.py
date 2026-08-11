"""
Route the kreuzberg extraction cache to ~/Library/Caches/com.fichero.fichero/kreuzberg/
so it stays out of the working directory of whichever process invokes it.

Without this shim, kreuzberg writes its msgpack/meta cache to `.kreuzberg/`
relative to cwd — which means running the backend or tests from the repo
root leaves `.kreuzberg/` polluting `git status` (#589).

Import this module for its side effect **before** importing or calling
kreuzberg. `document_loader` and `pdf_loader` both import it at the top
so any callsite that triggers an extraction has the env var set.
"""

import os
import shutil
from pathlib import Path

# ~/Library/Caches per Apple HIG: this is regenerable derived data, not user
# content. OS may prune it under disk pressure; Time Machine skips it.
_KREUZBERG_CACHE = (
    Path.home() / "Library" / "Caches" / "com.fichero.fichero" / "kreuzberg"
)

# One-time migration from the previous Application Support location.
# Safe to remove this block after 0.0.3 ships.
_LEGACY_CACHE = (
    Path.home()
    / "Library"
    / "Application Support"
    / "com.fichero.fichero"
    / "kreuzberg"
)
if _LEGACY_CACHE.exists() and not _KREUZBERG_CACHE.exists():
    _KREUZBERG_CACHE.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(_LEGACY_CACHE), str(_KREUZBERG_CACHE))

# Only set if the operator hasn't already overridden via env — respects
# explicit user config (e.g. tests pointing to a tmpdir).
if not os.environ.get("KREUZBERG_CACHE_DIR"):
    _KREUZBERG_CACHE.mkdir(parents=True, exist_ok=True)
    os.environ["KREUZBERG_CACHE_DIR"] = str(_KREUZBERG_CACHE)


# ---------------------------------------------------------------------------
# pdfium quarantine strip (#4555, live-diagnosed 2026-08-09 on the sandboxed
# Dev Embedded engine).
#
# kreuzberg's Rust core binds libpdfium.dylib from a per-user extraction dir
# ($TMPDIR/kreuzberg-pdfium/). In a SANDBOXED engine that extraction is
# written with com.apple.quarantine — and Gatekeeper refuses dlopen of
# quarantined, non-notarized code with "library load disallowed by system
# policy" NO MATTER what entitlements the process holds (live-proven: the
# rung-2 {app-sandbox, inherit, disable-library-validation} signature still
# failed; stripping the xattr + a fresh process loaded pdfium and the same
# scanned PDF extracted cleanly). Every PDF then imported with page images
# but no extracted text.
#
# Two levers, both idempotent, both best-effort:
#  1. If the extraction is already there (persists across spawns), strip the
#     quarantine BEFORE kreuzberg's first bind in this process — a failed
#     bind is cached per-process, so post-failure stripping only helps the
#     NEXT spawn.
#  2. If it is not there yet, pre-place the wheel's own bundled
#     libpdfium.dylib and strip the copy — the extractor accepts an existing
#     file, so the quarantined first-extraction never happens.
# ---------------------------------------------------------------------------


def _strip_quarantine(path: Path) -> None:
    # ctypes, not os.removexattr: the os-module xattr API is LINUX-ONLY —
    # on macOS Python it does not exist, so the first draft of this fix was
    # a silent no-op (caught by the unit test). libc's removexattr is the
    # real call; in-process, so no subprocess for the sandbox to police.
    import ctypes
    import ctypes.util

    try:
        libc = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)
        libc.removexattr(str(path).encode(), b"com.apple.quarantine", 0)
    except Exception:
        pass  # not quarantined / no libc — both fine


def prepare_pdfium(logger=None) -> None:
    """Point kreuzberg's pdfium bind path at the SIGNED bundled dylib.

    A HARDLINK, not a copy and not a symlink (live-iterated 2026-08-09,
    three failure modes measured on the sandboxed Dev Embedded engine):
    - a COPY written by the sandboxed engine is quarantined by its own
      write, and the sandbox refuses to REMOVE com.apple.quarantine, so a
      copy can never be made loadable from inside;
    - a SYMLINK got the engine KILLED OUTRIGHT at dlopen — no Python
      traceback, no faulthandler output, the AMFI hard-kill signature;
    - the entitlement alone (disable-library-validation) did not unblock
      the quarantined copy.
    A hardlink shares the INODE of the wheel's own dylib inside the signed
    app bundle: no quarantine xattr can exist on it separately, dlopen sees
    a regular file at the path kreuzberg binds, and the extractor skips its
    doomed quarantined write because the path exists.
    """
    try:
        import kreuzberg  # noqa: PLC0415 — resolve the wheel's location

        bundled = Path(kreuzberg.__file__).parent / "libpdfium.dylib"
        if not bundled.exists():
            if logger:
                logger.warning("pdfium: wheel has no bundled libpdfium.dylib")
            return
        tmpdir = Path(os.environ.get("TMPDIR", "/tmp"))
        target_dir = tmpdir / "kreuzberg-pdfium"
        target = target_dir / "libpdfium.dylib"
        target_dir.mkdir(parents=True, exist_ok=True)
        try:
            if target.stat().st_ino == bundled.stat().st_ino:
                return  # already hardlinked to the bundle
        except OSError:
            pass
        if target.exists() or target.is_symlink():
            # A previous run's quarantined extraction, or the symlink shape
            # that got the process AMFI-killed.
            target.unlink()
        try:
            os.link(bundled, target)
        except OSError:
            # Cross-volume (hardlink impossible): last resort is the copy;
            # it may be quarantined, in which case only entitled builds load.
            shutil.copy2(bundled, target)
            _strip_quarantine(target)
        if logger:
            logger.info("pdfium bind path hardlinked to bundled dylib: %s", target)
    except Exception as exc:  # pragma: no cover - defensive
        if logger:
            logger.warning("pdfium preparation failed (PDF text extraction may degrade): %s", exc)


import sys

if sys.platform == "darwin":
    prepare_pdfium()


# ---------------------------------------------------------------------------
# kreuzberg PDF usability gate (2026-08-09, the freeze root).
#
# kreuzberg's PDF path is a SYNC Rust-FFI call that does not release the GIL.
# When its pdfium bind hangs (the quarantined-extraction dance above), every
# Python thread stops — event loop included — so the WHOLE ENGINE freezes,
# /api/health goes dark, and the app watchdog SIGKILLs it: the silent engine
# deaths and multi-minute UI stalls Daniel hit all evening.
#
# The gate probes kreuzberg's PDF extraction ONCE, in a SUBPROCESS with a
# hard timeout — a hang or a kill in the probe can never touch the engine.
# When the probe fails, callers skip kreuzberg for PDFs (fitz still extracts
# text layers; scans import as page images pending OCR) instead of gambling
# the process on it.
# ---------------------------------------------------------------------------

_KREUZBERG_PDF_USABLE: bool | None = None

# A minimal one-page PDF, enough to force the pdfium bind.
_PROBE_PDF = (
    b"%PDF-1.1\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 100 100]>>endobj\n"
    b"trailer<</Root 1 0 R>>\n%%EOF"
)


def kreuzberg_pdf_usable(logger=None) -> bool:
    """True when kreuzberg can bind pdfium in this installation."""
    global _KREUZBERG_PDF_USABLE
    if _KREUZBERG_PDF_USABLE is not None:
        return _KREUZBERG_PDF_USABLE
    import subprocess
    import sys
    import tempfile

    try:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(_PROBE_PDF)
            probe_path = f.name
        proc = subprocess.run(
            _worker_command(), capture_output=True, timeout=60,
            env=_worker_env({**os.environ, "FICHERO_PDFIUM_PROBE_PDF": probe_path}),
        )
        _KREUZBERG_PDF_USABLE = proc.returncode == 0
        if not _KREUZBERG_PDF_USABLE and logger:
            logger.warning(
                "kreuzberg PDF probe failed (rc=%s) — scanned-PDF text "
                "extraction disabled for this run; text-layer PDFs still "
                "extract via fitz. stderr tail: %s",
                proc.returncode,
                (proc.stderr or b"")[-300:].decode(errors="replace"),
            )
    except subprocess.TimeoutExpired:
        _KREUZBERG_PDF_USABLE = False
        if logger:
            logger.warning(
                "kreuzberg PDF probe HUNG (>60s) — pdfium bind wedge; "
                "kreuzberg disabled for PDFs this run (the engine stays alive)"
            )
    except Exception as exc:  # pragma: no cover - defensive
        _KREUZBERG_PDF_USABLE = False
        if logger:
            logger.warning("kreuzberg PDF probe errored: %s — disabled", exc)
    return _KREUZBERG_PDF_USABLE


# ---------------------------------------------------------------------------
# Pre-import kreuzberg's lazy Python dependencies (2026-08-09, the SECOND
# wedge layer, faulthandler-dumped live once pdfium finally loaded).
#
# kreuzberg's Rust pipeline calls back into Python from FFI threads, and
# those callbacks LAZILY import modules (charset_normalizer.api was caught
# mid-import at the freeze). A lazy import from an FFI callback deadlocks:
# the sync FFI entry holds the GIL while its worker needs the import lock —
# every thread in the engine stops, health goes dark, the watchdog SIGKILLs.
# Importing them here, single-threaded at startup, means the callback only
# ever finds cached modules. Best-effort: a missing module just falls out.
# ---------------------------------------------------------------------------
for _lazy in ("charset_normalizer", "charset_normalizer.api"):
    try:
        __import__(_lazy)
    except Exception:  # noqa: S112 — absence is kreuzberg's problem, not fatal
        pass


def _worker_command() -> list[str]:
    """The out-of-process kreuzberg worker invocation for THIS layout."""
    import sys

    exe = Path(sys.executable)
    if exe.name.lower().startswith("python"):
        # Dev/venv: sys.executable IS a python (sys.base_prefix would escape
        # the venv to a bare interpreter with no kreuzberg).
        return [str(exe), "-m", "fichero_server._pdfium_probe"]
    # Shipped Briefcase: sys.executable is the app stub; BRIEFCASE_MAIN_MODULE
    # (set in _worker_env) points it at the worker module instead of the app.
    return [str(exe)]


def _worker_env(env: dict) -> dict:
    env = dict(env)
    env["BRIEFCASE_MAIN_MODULE"] = "fichero_server._pdfium_probe"
    return env


class KreuzbergSubprocessError(RuntimeError):
    """The out-of-process kreuzberg extraction failed (rc, timeout, bad JSON)."""


def extract_pdf_pages_subprocess(path, timeout: int = 300) -> list:
    """Per-page kreuzberg extraction, OUT OF PROCESS (#4555).

    The in-process call deadlocked the whole engine (sync FFI holds the GIL
    while callbacks lazily import C extensions — charset_normalizer one
    faulthandler dump, uuid_utils the next; the list does not converge).
    A child does the extraction and hands back JSON; a hang costs the child
    its life at `timeout`, never the engine's.
    """
    import json
    import subprocess
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as out:
        out_path = out.name
    env = {
        **os.environ,
        "FICHERO_KREUZBERG_EXTRACT_INPUT": str(path),
        "FICHERO_KREUZBERG_EXTRACT_OUTPUT": out_path,
    }
    try:
        proc = subprocess.run(
            _worker_command(), capture_output=True, timeout=timeout,
            env=_worker_env(env),
        )
    except subprocess.TimeoutExpired as exc:
        raise KreuzbergSubprocessError(
            f"kreuzberg worker timed out after {timeout}s (killed; engine unharmed)"
        ) from exc
    if proc.returncode != 0:
        tail = (proc.stderr or b"")[-400:].decode(errors="replace")
        raise KreuzbergSubprocessError(
            f"kreuzberg worker rc={proc.returncode}: {tail}"
        )
    try:
        with open(out_path, encoding="utf-8") as f:
            return json.load(f).get("pages") or []
    except (OSError, ValueError) as exc:
        raise KreuzbergSubprocessError(f"worker output unreadable: {exc}") from exc
    finally:
        try:
            os.unlink(out_path)
        except OSError:
            pass

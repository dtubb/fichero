"""Coverage for kreuzberg cache environment routing."""

import os
import subprocess
import sys


def test_explicit_kreuzberg_cache_dir_is_preserved():
    env = os.environ.copy()
    env["KREUZBERG_CACHE_DIR"] = "/tmp/fichero-test-kreuzberg"
    result = subprocess.run(
        [sys.executable, "-c", "import os; import fichero_server.loaders.kreuzberg_cache; print(os.environ['KREUZBERG_CACHE_DIR'])"],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.stdout.strip() == "/tmp/fichero-test-kreuzberg"


def _import_probe(script: str) -> str:
    """Run `script` in a clean interpreter and return its stdout."""
    return subprocess.run(
        [sys.executable, "-c", script],
        check=True,
        capture_output=True,
        text=True,
        env=os.environ.copy(),
    ).stdout.strip()


def test_engine_startup_does_not_import_kreuzberg():
    """Engine startup must not pay for the extraction stack (2026-09-01).

    Importing the FastAPI app used to pull kreuzberg's 66 MB Rust binding and
    charset_normalizer — 114 modules, ~69 MB of reads — because
    `kreuzberg_cache` did that work at MODULE scope and `api.main` imports it
    for its cheap env-var side effect. That is pure launch latency: nothing in
    the extraction stack is needed until a document is actually extracted.

    This pins the fast path. If it fails, someone put the prewarm (or another
    `import kreuzberg`) back on the import path of `api.main`.
    """
    out = _import_probe(
        "import sys; import fichero_server.api.uds_transport;"
        " print('kreuzberg' in sys.modules, 'charset_normalizer' in sys.modules)"
    )
    assert out == "False False", f"extraction stack imported at engine startup: {out}"


def test_startup_still_routes_the_kreuzberg_cache_dir():
    """The CHEAP side effect stays at startup — only the costly half moved."""
    out = _import_probe(
        "import os; import fichero_server.api.uds_transport;"
        " print(bool(os.environ.get('KREUZBERG_CACHE_DIR')))"
    )
    assert out == "True"


def test_loaders_prewarm_before_any_kreuzberg_ffi():
    """The deadlock guard still fires — just later, and off the launch path.

    The 2026-08-09 freeze root: kreuzberg's sync Rust FFI holds the GIL while
    its worker threads lazily import Python modules, which deadlocks the whole
    engine. The fix requires pdfium bound and those modules cached BEFORE the
    first FFI call — an ordering guarantee, not a startup one. Every
    `import kreuzberg` in the engine sits inside a function in `pdf_loader` /
    `document_loader`, and both call `prewarm_for_extraction()` at their own
    module scope, which is strictly earlier.
    """
    for module in ("document_loader", "pdf_loader"):
        out = _import_probe(
            f"import sys; import fichero_server.loaders.{module};"
            " from fichero_server.loaders import kreuzberg_cache;"
            " print(kreuzberg_cache._PREWARMED, 'charset_normalizer' in sys.modules)"
        )
        assert out == "True True", f"{module} did not prewarm before FFI: {out}"

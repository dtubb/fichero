"""The side effects that must happen before `api.main`'s imports (#5051).

These three ran inline between `api/main.py`'s imports, which made every later
import an E402. Moving them into `api/_startup.py` removed the cause instead of
silencing the rule — but it also moved a load-bearing ORDERING guarantee into a
module whose whole purpose is invisible at the call site. A reader who does not
know why it exists could delete the import, or move it below the FastAPI ones,
and nothing would fail loudly: tokenizers would simply deadlock across a fork,
sometimes, on someone else's machine.

So these pin the behaviour rather than the arrangement. Each runs in a FRESH
interpreter, because the thing under test is what happens AT IMPORT and an
already-imported module cannot be re-imported to observe it.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[3] / "src"


def _in_fresh_interpreter(body: str) -> str:
    """Run `body` in a new interpreter with the engine importable, return stdout.

    Rule 0: a non-zero exit FAILS the test with the child's stderr, rather than
    returning empty stdout that an `assert "x" in out` would quietly read as a
    missing feature.
    """
    result = subprocess.run(
        [sys.executable, "-c", body],
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(SRC), "HOME": str(Path.home())},
    )
    assert result.returncode == 0, (
        f"child interpreter failed ({result.returncode}), so this test saw nothing:\n"
        f"{result.stderr[-2000:]}"
    )
    return result.stdout


def test_importing_the_engine_disables_tokenizer_parallelism() -> None:
    """The Rust tokenizer's thread pool deadlocks across a fork unless this is
    set. The engine spawns subprocesses, so it must be set by the time anything
    can fork — and the only way to guarantee that is at import."""
    out = _in_fresh_interpreter(
        "import os\n"
        "assert 'TOKENIZERS_PARALLELISM' not in os.environ, 'precondition: must start unset'\n"
        "import fichero_server.api.main\n"
        "print(os.environ.get('TOKENIZERS_PARALLELISM'))\n"
    )
    assert out.strip() == "false"


def test_the_setting_lands_before_transformers_could_read_it() -> None:
    """The ordering, not just the value. `transformers` reads the variable when
    IT is imported, so setting it afterwards is the same as not setting it. This
    asserts the engine's own import leaves the variable set while `transformers`
    has not yet been pulled in at all — the state any later fork depends on."""
    out = _in_fresh_interpreter(
        "import os, sys\n"
        "import fichero_server.api.main\n"
        "print(os.environ.get('TOKENIZERS_PARALLELISM'), 'transformers' in sys.modules)\n"
    )
    value, transformers_loaded = out.split()
    assert value == "false"
    # If transformers ever IS imported at engine-import time, this test stops
    # proving the ordering and must be replaced by one that can — it does not
    # get to pass quietly on a weaker claim.
    assert transformers_loaded == "False", (
        "transformers is now imported at engine start, so this test no longer proves "
        "the env var was set first. Rewrite it to observe the ordering directly."
    )


def test_the_extraction_cache_is_primed_at_import_not_on_first_use() -> None:
    """`kreuzberg_cache` reroutes the extraction cache and runs a one-time
    migration of the legacy location. Imported eagerly so that happens at engine
    startup, whether or not the user extracts anything this session — a lazy
    import would leave the old location in place for anyone who never does."""
    out = _in_fresh_interpreter(
        "import sys\n"
        "import fichero_server.api.main\n"
        "print('fichero_server.loaders.kreuzberg_cache' in sys.modules)\n"
    )
    assert out.strip() == "True"


def test_the_import_timing_stamp_still_works() -> None:
    """`api_stamp` measures from `_startup`'s import, which is the first thing
    `api.main` imports — so the epoch starts before the imports it measures. A
    module cannot time its own import from inside itself, which is why the epoch
    lives here and not there."""
    out = _in_fresh_interpreter(
        "import logging, io\n"
        "buf = io.StringIO()\n"
        "logging.basicConfig(stream=buf, level=logging.INFO)\n"
        "from fichero_server.api._startup import api_stamp\n"
        "api_stamp('probe')\n"
        "print('engine-launch: probe' in buf.getvalue())\n"
    )
    assert out.strip() == "True"

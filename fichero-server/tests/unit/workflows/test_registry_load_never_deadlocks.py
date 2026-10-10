"""The tool registry's first load can't deadlock with a request importing `tools` (2026-10-10).

The engine hung at start: a request thread imported `workflows.tools` (holding
that module's import lock) and read TOOLS, while a recipe job thread held the
registry's lock and waited on the same import. This replays that interleaving
in a fresh interpreter, with an import hook that pauses the request thread
inside `tools` until the job thread is waiting.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap

_SCRIPT = textwrap.dedent(
    """
    import sys, threading, time
    from fichero_server.workflows import registry

    class PauseInsideTools:
        def find_spec(self, name, path=None, target=None):
            if name == "fichero_server.workflows.tools.mcp" and threading.current_thread() is threading.main_thread():
                time.sleep(1.0)  # the job thread reads the registry meanwhile
            return None

    sys.meta_path.insert(0, PauseInsideTools())

    def job():
        time.sleep(0.3)
        registry._ensure_tools_loaded()

    worker = threading.Thread(target=job, daemon=True)
    worker.start()
    from fichero_server.workflows import tools  # the request thread's direct import
    worker.join(20)
    assert not worker.is_alive(), "job thread still waiting"
    assert registry._TOOLS_LOADED
    print("loaded", len(registry.TOOL_DEFS))
    """
)


def test_a_request_importing_tools_and_a_job_reading_the_registry_both_finish() -> None:
    done = subprocess.run(
        [sys.executable, "-c", _SCRIPT], capture_output=True, text=True, timeout=120
    )
    assert done.returncode == 0, done.stderr[-2000:]
    assert done.stdout.startswith("loaded ")

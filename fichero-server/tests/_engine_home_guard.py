"""No test spawns the engine with the maintainer's real HOME (#5187).

WHY: an engine started with the real HOME runs its startup library discovery over the maintainer's
own libraries, and `migrate_legacy_server_state` moves files inside his real Application Support.
Two spawners did exactly that -- test_cli_engine_contract and test_transport_round_trips never set
HOME -- and the second had already clobbered his real `.api-key` once (2026-09-19). Tests never
touch the real libraries; this makes the rule a check instead of a habit.

It is a RUNTIME check on `subprocess.Popen`, installed by the root conftest, not a source scan: a
spawn's env is often built in another function (`_child_env`), which a scan cannot follow, while
every spawn -- however its env was built -- passes through Popen.
"""

from __future__ import annotations

import os
import re
import subprocess
import tempfile

#: Captured at import, before any test could change it.
REAL_HOME = os.path.realpath(os.path.expanduser("~"))
TEMP_ROOTS = tuple({os.path.realpath(tempfile.gettempdir()), "/private/tmp"})


#: An engine START names its ASGI app (`uvicorn fichero_server.api.tcp_transport:app`, the UDS target):
#: an import probe (`python -c "import fichero_server.api..."`) or `uvicorn --help` starts nothing.
_ENGINE_APP = re.compile(r"fichero_server\.api\.[\w.]+:app\b")


def _is_engine(args) -> bool:
    text = args if isinstance(args, str) else " ".join(str(a) for a in args)
    return bool(_ENGINE_APP.search(text))


def engine_spawn_problem(args, env) -> str | None:
    """Why this spawn must not happen, or None. Only spawns of the engine are judged."""
    if not _is_engine(args):
        return None
    home = (os.environ if env is None else env).get("HOME")
    if not home:
        return "spawns the engine with no HOME"
    real = os.path.realpath(home)
    inside_temp = any(real == root or real.startswith(root + os.sep) for root in TEMP_ROOTS)
    if real == REAL_HOME or not inside_temp:
        return (f"spawns the engine with HOME={home}, not inside a temp dir: it would read the "
                "maintainer's real libraries (#5187). Give it HOME under its temp base "
                "(`_engine_wait._share_real_model_cache` shares only the model cache).")
    return None


class GuardedPopen(subprocess.Popen):
    def __init__(self, args, *rest, **kwargs):
        problem = engine_spawn_problem(args, kwargs.get("env"))
        if problem:
            raise AssertionError(problem)
        super().__init__(args, *rest, **kwargs)


def install() -> None:
    subprocess.Popen = GuardedPopen

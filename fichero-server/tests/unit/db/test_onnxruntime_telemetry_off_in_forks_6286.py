"""A forked child that imports onnxruntime must not start ORT's telemetry (Network.framework is not fork-safe, #6286)."""
import os
import subprocess
import sys
import textwrap

import pytest

pytest.importorskip("onnxruntime")

_CHILD = textwrap.dedent("""
    import os
    from fichero_server.db import embed_process  # noqa: F401  (sets the env before onnxruntime is imported)
    pid = os.fork()
    if pid == 0:
        import onnxruntime  # noqa: F401
        os._exit(0)
    _, status = os.waitpid(pid, 0)
    raise SystemExit(os.waitstatus_to_exitcode(status))
""")


def test_embed_process_turns_ort_telemetry_off_even_if_inherited_on():
    from fichero_server.db import embed_process  # noqa: F401

    assert os.environ["ORT_DISABLE_TELEMETRY"] == "1"


def test_forked_child_imports_onnxruntime_and_exits_zero():
    env = {**os.environ, "ORT_DISABLE_TELEMETRY": "0"}
    done = subprocess.run([sys.executable, "-c", _CHILD], env=env, capture_output=True, timeout=120)
    assert done.returncode == 0, done.stderr.decode()

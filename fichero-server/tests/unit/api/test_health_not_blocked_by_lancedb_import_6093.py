"""#6093: the engine must answer /api/health before the embed stage's `lancedb` import finishes.

That means importing the engine's app module (everything the FastAPI app and the
health route pull in at start) must NOT itself import `lancedb`. `lancedb` is only
needed by the embed/search code, so it is imported lazily inside the functions that
actually open a LanceDB table — never at module top level on the health/startup path.

We prove it in a fresh interpreter (a subprocess) by importing the app module and then
checking that no `lancedb` module landed in `sys.modules`.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

SERVER_ROOT = Path(__file__).resolve().parents[3]

PROBE = """
import sys
import fichero_server.api.main  # the engine's FastAPI app: everything it imports at start
import fichero_server.api.tcp_transport
import fichero_server.api.uds_transport
hit = sorted(m for m in sys.modules if "lancedb" in m.lower())
print("LANCEDB IMPORTED:", hit)
"""


def test_importing_the_engine_app_module_does_not_import_lancedb():
    result = subprocess.run(
        [sys.executable, "-c", PROBE],
        capture_output=True,
        text=True,
        cwd=str(SERVER_ROOT),
        env={**os.environ, "PYTHONPATH": str(SERVER_ROOT / "src")},
        timeout=300,
    )
    assert result.returncode == 0, (
        "the engine app module failed to import:\n" + result.stderr[-2500:]
    )
    assert "LANCEDB IMPORTED: []" in result.stdout, (
        "importing the engine app module pulled in lancedb at start "
        "(it must stay lazy, imported only where a LanceDB table is opened): "
        + result.stdout[-500:]
    )
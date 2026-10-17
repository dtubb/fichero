"""#5745: PyObjC resolves Quartz names lazily and not thread-safely, so the first page read on
parallel threads died with a bare KeyError('CGImageGetWidth'). Importing the engine's Quartz
users resolves every name they use up front, on the importing thread."""
import subprocess
import sys

import pytest

pytest.importorskip("Quartz")

CODE = """
import sys; sys.path[:0] = {paths!r}
import Quartz
import fichero_server.media.quartz_warm as w
missing = [n for n in w.NAMES if n not in vars(Quartz)]
print("MISSING", missing)
"""


def test_every_quartz_name_is_resolved_on_import():
    out = subprocess.run([sys.executable, "-I", "-c", CODE.format(paths=sys.path)], capture_output=True, text=True,
                         check=True).stdout
    assert "MISSING []" in out, out

"""#5745: PyObjC resolves Quartz names lazily and not thread-safely, so the first page read on
parallel threads died with a bare KeyError('CGImageGetWidth'). Importing the engine's Quartz
users resolves every name they use under a lock on first use (`warm()`), not at import (#3950)."""
import subprocess
import sys

import pytest

pytest.importorskip("Quartz")

CODE = """
import sys; sys.path[:0] = {paths!r}
import Quartz
import fichero_server.media.quartz_warm as w
w.warm()
missing = [n for n in w.NAMES if n not in vars(Quartz) and hasattr(Quartz, n)]  # a name this macOS lacks is not ours to resolve
print("MISSING", missing)
"""


def test_every_quartz_name_is_resolved_by_warm():
    out = subprocess.run([sys.executable, "-I", "-c", CODE.format(paths=sys.path)], capture_output=True, text=True,
                         check=True).stdout
    assert "MISSING []" in out, out


def test_names_cover_every_quartz_name_the_code_uses():
    import ast
    import pathlib

    import fichero_server
    from fichero_server.media import quartz_warm

    used = set()
    for path in pathlib.Path(fichero_server.__file__).parent.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.ImportFrom) and node.module == "Quartz":
                used |= {a.name for a in node.names}
            elif isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "Quartz":
                used.add(node.attr)
    assert used - set(quartz_warm.NAMES) == set()


def test_every_module_that_uses_quartz_calls_warm():
    """#5745 after #3950: quartz_warm no longer imports Quartz at import, so a module that uses Quartz must
    call `quartz_warm.warm()` itself, or its first threaded use races on PyObjC's lazy names again."""
    import ast
    import pathlib

    import fichero_server

    missing = []
    for path in pathlib.Path(fichero_server.__file__).parent.rglob("*.py"):
        if path.name == "quartz_warm.py":
            continue
        text = path.read_text()
        uses = any(
            (isinstance(n, ast.ImportFrom) and n.module == "Quartz")
            or (isinstance(n, ast.Import) and any(a.name == "Quartz" for a in n.names))
            for n in ast.walk(ast.parse(text))
        )
        if uses and "quartz_warm.warm()" not in text:
            missing.append(str(path.relative_to(pathlib.Path(fichero_server.__file__).parent)))
    assert missing == []

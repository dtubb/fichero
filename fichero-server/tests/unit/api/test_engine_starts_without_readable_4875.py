"""`engine.readable-py-import-is-a-startup-single-point-of-failure` (#4875): a broken knowledge/readable.py must cost
only the route that renders it, not the whole engine's start.
"""
from __future__ import annotations

import asyncio
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

MODULE = "fichero_server.knowledge.readable"


def test_the_engine_starts_when_readable_cannot_be_imported():
    import fichero_server

    src = str(Path(fichero_server.__file__).resolve().parents[1])  # THIS tree's source, not an installed copy
    code = (
        f"import sys; sys.path.insert(0, {src!r}); sys.modules[{MODULE!r}] = None\n"  # a None entry makes `import` raise ImportError
        "import fichero_server.api.main as m\n"
        "print('started', any(getattr(r, 'path', '') == '/api/health' for r in m.app.routes))\n"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=300)
    assert out.returncode == 0, out.stderr[-600:]
    assert "started True" in out.stdout


def test_the_route_answers_503_naming_the_module(monkeypatch):
    from fichero_server.api.routes.kg import render

    monkeypatch.setitem(sys.modules, MODULE, None)

    class _Db:
        def get(self, *_a, **_k):
            return object()  # the entity exists

    with pytest.raises(HTTPException) as caught:
        asyncio.run(render.get_entity_readable("e1", db=_Db()))
    assert caught.value.status_code == 503
    assert MODULE in caught.value.detail

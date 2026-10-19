"""HTR-United's catalogue is fetched with the bundled CA list (#5809).

Live 2026-10-19 on the embedded app: "HTR-United's catalogue could not be read: <urlopen error [SSL:
CERTIFICATE_VERIFY_FAILED] ...>", so Transkribus-style sources read 'not searched' for good. The embedded Python has
no system certificate store; `core.tls.https_context()` is the context every urllib fetch passes.
"""

from __future__ import annotations

import ast
import urllib.request
from pathlib import Path

import fichero_server
from fichero_server.core.tls import https_context
from fichero_server.recipes import htr_united
from _scan_files import scan_rglob


def test_the_catalogue_fetch_passes_the_verifying_context(monkeypatch):
    seen = {}

    def fake_urlopen(url, timeout=None, context=None):
        seen["context"] = context
        raise OSError("stop after the request is made")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    try:
        htr_united._fetch_catalogue()  # not _harvest: the suite's conftest replaces that with a refusal
    except OSError:
        pass
    assert seen["context"] is https_context()


def test_no_urlopen_in_the_engine_goes_without_a_context():
    """The sweep: the same omission anywhere else in the engine fails here, not in the owner's app."""
    root = Path(fichero_server.__file__).parent
    bare = []
    for path in scan_rglob(root, "*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call) and getattr(node.func, "attr", getattr(node.func, "id", "")) == "urlopen":
                given = [k.value for k in node.keywords if k.arg == "context"]
                # No context=, or the literal None (which is the default: no CA list), is the same omission.
                if not given or (isinstance(given[0], ast.Constant) and given[0].value is None):
                    bare.append(f"{path.relative_to(root)}:{node.lineno}")
    assert bare == []

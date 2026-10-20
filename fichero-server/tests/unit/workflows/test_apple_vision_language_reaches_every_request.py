"""The language Apple Vision is told reaches EVERY recognition request (#5894; the owner's rule: es-ES, never auto).

Found by reading, 2026-10-20: `es-ES` goes from `line_reader.read_lines` through `llm.vision` and `_apple_vision_dispatch` to
`set_vision_languages` on all five `VNRecognizeTextRequest`s the OCR makes (Accurate, the Fast retry, the gap band, the ink
residue, the revision-1 second detector). Vision treats it as a hint, not a limit on characters (Cyrillic and Vietnamese marks
still appear in handwriting it cannot read), so there is no bug to fix; this is the guard that keeps it so. No macOS needed.
"""
from __future__ import annotations

import ast
import asyncio
from pathlib import Path

import pytest

from fichero_server.workflows.tools import vision_base

SOURCE = Path(vision_base.__file__)
#: The one request that asks Vision what it supports; it reads nothing, so it has no language.
NOT_A_READ = {"_ask_vision_locales"}


def _own(func):
    """The nodes of a function without those of the functions nested in it (each is judged on its own)."""
    stack = list(ast.iter_child_nodes(func))
    while stack:
        node = stack.pop()
        yield node
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            stack.extend(ast.iter_child_nodes(node))


def _requests():
    """(function, variable, line, lines of `set_vision_languages(variable, ...)` after it in the same function) of each
    `x = Vision.VNRecognizeTextRequest.alloc().init()`."""
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    found = []
    for func in (n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))):
        nodes = list(_own(func))
        for node in nodes:
            if (isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)
                    and "VNRecognizeTextRequest" in ast.unparse(node.value) and ".alloc()" in ast.unparse(node.value)):
                var = node.targets[0].id
                sets = [c.lineno for c in nodes if isinstance(c, ast.Call) and ast.unparse(c.func) == "set_vision_languages"
                        and c.args and ast.unparse(c.args[0]) == var and c.lineno > node.lineno]
                found.append((func.name, var, node.lineno, sets))
    return found


def test_every_recognition_request_gets_its_language_set_before_it_is_performed():
    reads = [r for r in _requests() if r[0] not in NOT_A_READ]
    assert len(reads) >= 5, f"the five request sites were expected, found {reads}: renamed? update this guard, do not drop it"
    missing = [(name, line) for name, _var, line, sets in reads if not sets]
    assert not missing, f"a Vision request that never gets set_vision_languages: {missing}"


@pytest.mark.parametrize("given", ["es-ES", "es", "es_ES", "Spanish", "spanish", "español"])
def test_spanish_in_any_spelling_is_es_ES_and_never_auto(given):
    assert vision_base.normalize_vision_language(given) == "es-ES"


def test_an_empty_language_is_not_auto_either():
    assert vision_base.normalize_vision_language("") == "en-US"
    assert vision_base.normalize_vision_language(None) == "en-US"


def test_the_language_the_line_reader_is_given_reaches_the_apple_dispatch(monkeypatch, tmp_path):
    from PIL import Image

    from fichero_server import llm
    from fichero_server.llm import line_reader
    from fichero_server.media.ocr_geometry import OCRGeometryBox, OCRGeometryLevel, OCRGeometryResult

    seen = []

    async def dispatch(images, prompt, config, *, language=None):
        seen.append((config.provider, config.model, language))
        return "hola"

    monkeypatch.setattr(llm, "_apple_vision_dispatch", dispatch)
    page = tmp_path / "p.png"
    Image.new("RGB", (400, 100), "white").save(page)
    poly = [[10, 10], [390, 10], [390, 40], [10, 40]]
    box = OCRGeometryBox(text="", bbox=[0, 0.1, 1, 0.3], level=OCRGeometryLevel.LINE, provider="kraken", model="m",
                         source="kraken-htr", confidence=0.9, metadata={"polygon_px": poly})
    geometry = OCRGeometryResult(text="", provider="kraken", model="m", boxes=[box], source="kraken-blla", metadata={})
    asyncio.run(line_reader.read_lines(str(page), geometry, None, language="es-ES", apple=True))
    assert seen == [("apple", "apple-vision", "es-ES")]

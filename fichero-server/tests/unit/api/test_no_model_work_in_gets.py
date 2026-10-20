"""`activity.read.get-runs-no-model`: no GET handler runs a model. The scan reads every `@router.get` body in the API."""
from __future__ import annotations

import ast
import re
from pathlib import Path
import importlib.util

# scripts/ is not a package: load the repo's scan helper by path (see test_scan_files_skips_nested_worktrees).
_spec = importlib.util.spec_from_file_location(
    "_scan_files", Path(__file__).resolve().parents[4] / "scripts" / "_scan_files.py")
assert _spec and _spec.loader
scan_files = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(scan_files)

API = Path(__file__).resolve().parents[3] / "src" / "fichero_server" / "api"
# A model entry point called by name: a read, an OCR, an embedding, a lane job.
MODEL_CALL = re.compile(
    r"(recognize_to_geometry|recognize_lines|segment_to_geometry|read_given_lines|apple_vision_ocr\w*|_embed_text\w*|"
    r"embed_texts|get_embedder|run_on_lane|\b(?:model|embedder|encoder|tokenizer|st_model)\.encode\()"
)


def _get_handlers():
    for path in sorted(scan_files.scan_rglob(API, "*.py")):
        source = path.read_text()
        lines = source.splitlines()
        for node in ast.walk(ast.parse(source)):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if any(isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) and d.func.attr == "get"
                   for d in node.decorator_list):
                yield path.relative_to(API), node.name, "\n".join(lines[node.lineno - 1:node.end_lineno])


def test_no_get_handler_calls_a_model_entry_point():
    offenders = [f"{path}::{name}: {sorted(set(MODEL_CALL.findall(body)))}"
                 for path, name, body in _get_handlers() if MODEL_CALL.search(body)]
    assert not offenders, "a GET runs a model (it returns what is stored, or says it isn't ready):\n" + "\n".join(offenders)


def test_the_scan_sees_the_get_handlers():
    names = {name for _path, name, _body in _get_handlers()}
    assert {"get_document_text", "find_similar_claims"} <= names and len(names) > 100

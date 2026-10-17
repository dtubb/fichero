"""`engine.llm-no-local-inference-mlx-cycle` (#4080): llm/local_inference.py and llm/mlx_model_store.py
are not mutually dependent (the store never imports local_inference), and the hardware gate is owned by the local-models leaf they both ask.

Static (AST, every scope incl. lazy in-function imports) so a function-local import cannot hide a cycle.
"""
from __future__ import annotations

import ast
from pathlib import Path

LLM = Path(__file__).resolve().parents[3] / "src" / "fichero_server" / "llm"
FACTS = "fichero_server.llm.local_model_facts"


def _imports(name: str) -> set[str]:
    out: set[str] = set()
    for node in ast.walk(ast.parse((LLM / f"{name}.py").read_text())):
        if isinstance(node, ast.ImportFrom) and node.module:
            out.add(node.module)
            out.update(f"{node.module}.{a.name}" for a in node.names)
        elif isinstance(node, ast.Import):
            out.update(a.name for a in node.names)
    return out


def test_the_store_does_not_import_local_inference():
    """local_inference uses the store as a service (one way); the store asks the facts leaf, never back."""
    assert "fichero_server.llm.local_inference" not in _imports("mlx_model_store")


def test_the_leaf_imports_neither():
    leaf = _imports("local_model_facts")
    assert not {"fichero_server.llm.local_inference", "fichero_server.llm.mlx_model_store"} & leaf


def test_one_gate_seen_through_every_door():
    from fichero_server.llm import local_inference, local_model_facts, local_models

    for name in ("check_local_model_hardware", "get_local_inference_capabilities", "LocalModelHardwareError"):
        owner = getattr(local_model_facts, name)
        assert getattr(local_inference, name) is owner
        assert getattr(local_models, name) is owner

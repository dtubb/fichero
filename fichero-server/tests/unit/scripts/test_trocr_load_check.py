"""`scripts/trocr_load_check.py` (#5981): one repository's failure is its row, never the end of the check; a crash after the row still
returns the row with the exit status. No network, no torch: the engine's loaders are replaced."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "trocr_load_check.py"


def _script():
    spec = importlib.util.spec_from_file_location("trocr_load_check", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_a_repository_that_fails_to_load_is_a_row_with_the_error_in_words(monkeypatch):
    check = _script()
    import types

    fake = types.ModuleType("fichero_server.workflows.tools.economy_htr")
    fake._load_trocr = lambda repo: (_ for _ in ()).throw(ValueError("no .safetensors file in acme/old"))
    monkeypatch.setitem(sys.modules, "fichero_server.workflows.tools.economy_htr", fake)
    monkeypatch.setitem(sys.modules, "torch", types.SimpleNamespace(__version__="2.14"))
    monkeypatch.setitem(sys.modules, "transformers", types.SimpleNamespace(__version__="5.19.0"))
    row = check.check_one("acme/old", ["a.png"])
    assert row["loaded"] is False and "no .safetensors" in row["error"] and row["transformers"] == "5.19.0"


def test_a_loaded_repository_reads_its_crops(monkeypatch):
    check = _script()
    import types

    fake = types.ModuleType("fichero_server.workflows.tools.economy_htr")
    fake._load_trocr = lambda repo: None
    fake.trocr_transcribe_lines = lambda crops, repo: ["texto"] * len(crops)
    monkeypatch.setitem(sys.modules, "fichero_server.workflows.tools.economy_htr", fake)
    monkeypatch.setitem(sys.modules, "torch", types.SimpleNamespace(__version__="2.14"))
    monkeypatch.setitem(sys.modules, "transformers", types.SimpleNamespace(__version__="5.19.0"))
    row = check.check_one("acme/new", ["a.png", "b.png"])
    assert row["loaded"] is True and row["texts"] == ["texto", "texto"] and row["error"] is None


def test_crops_are_the_images_of_a_folder_in_order_up_to_the_limit(tmp_path):
    check = _script()
    for name in ("b.png", "a.png", "c.jpg", "notes.txt"):
        (tmp_path / name).write_bytes(b"x")
    assert [Path(p).name for p in check.crops_in(tmp_path, 2)] == ["a.png", "b.png"]
    assert [Path(p).name for p in check.crops_in(tmp_path / "a.png", 5)] == ["a.png"]

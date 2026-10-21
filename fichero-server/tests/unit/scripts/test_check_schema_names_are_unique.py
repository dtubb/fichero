"""Two route models with one class name become one qualified schema name and break the clients that used the short one
(the cand 14 regen's `InviteResponse`). The guard names a NEW clash and a stale known entry."""
from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "check_schema_names_are_unique.py"
spec = importlib.util.spec_from_file_location("check_schema_names_are_unique", SCRIPT)
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


def _tree(tmp_path: Path, files: dict[str, str]) -> Path:
    routes = tmp_path / guard.ROUTES
    for rel, body in files.items():
        (routes / rel).parent.mkdir(parents=True, exist_ok=True)
        (routes / rel).write_text(body)
    return tmp_path


MODEL = "from pydantic import BaseModel\n\n\nclass {name}(BaseModel):\n    x: int = 0\n"


def test_a_name_defined_in_two_route_modules_fails_and_is_named(tmp_path, capsys):
    root = _tree(tmp_path, {"auth/a.py": MODEL.format(name="InviteResponse"), "auth/b.py": MODEL.format(name="InviteResponse")})
    assert guard.main(root, frozenset()) == 1
    out = capsys.readouterr().out
    assert "InviteResponse" in out and "a.py" in out and "b.py" in out


def test_distinct_names_and_a_subclass_of_a_model_pass(tmp_path):
    root = _tree(tmp_path, {"a.py": MODEL.format(name="A") + "\n\nclass Child(A):\n    y: int = 1\n", "b.py": MODEL.format(name="B")})
    assert guard.main(root, frozenset()) == 0


def test_a_clash_between_a_model_and_a_plain_class_is_not_a_schema_clash(tmp_path):
    root = _tree(tmp_path, {"a.py": MODEL.format(name="Same"), "b.py": "class Same:\n    pass\n"})
    assert guard.main(root, frozenset()) == 0


def test_a_known_clash_passes_and_a_known_name_that_no_longer_clashes_fails(tmp_path, capsys):
    clash = _tree(tmp_path / "x", {"a.py": MODEL.format(name="Old"), "b.py": MODEL.format(name="Old")})
    assert guard.main(clash, frozenset({"Old"})) == 0
    single = _tree(tmp_path / "y", {"a.py": MODEL.format(name="Old")})
    assert guard.main(single, frozenset({"Old"})) == 1
    assert "remove from KNOWN" in capsys.readouterr().out


def test_an_empty_tree_fails_rather_than_passes(tmp_path):
    (tmp_path / guard.ROUTES).mkdir(parents=True)
    assert guard.main(tmp_path, frozenset()) == 1

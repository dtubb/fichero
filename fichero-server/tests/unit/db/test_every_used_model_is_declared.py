"""Every model the engine stores in a library is a DECLARED table (#5178).

WHY: a model passed to `db.save` / `get` / `query` but missing from `Database._all_schema_models`
gets its table on FIRST SAVE. That table bypasses the schema, the migration path, the snapshot and
the export walkers, and an existing library does not have it until something happens to write one
(the Reader's line map had exactly this; archive's sweep then found nine more). This guard derives
the set of models the engine's code actually uses -- by reading the code, not a hand list -- and
fails on one that is not declared, so the class cannot come back with the next model.

Library calls only: the app database (`app_db`, accounts and devices) has its own schema.
"""

from __future__ import annotations

import ast
from pathlib import Path

from fichero_server.db import Database

SRC = Path(__file__).resolve().parents[3] / "src" / "fichero_server"
DB_METHODS = {"save", "save_many", "get", "query", "query_in", "all", "delete", "count", "get_many", "delete_many", "exists"}

#: Models the scan sees used and that are deliberately NOT tables, with why.
NOT_A_TABLE: dict[str, str] = {
    "SourceSupport": "embedded in an entity's `source_supports`; `db.query(SourceSupport)` fails outright (segment_conversion.py)",
}


def model_class_names(src: Path = SRC) -> set[str]:
    """Every class in the engine that is a pydantic model (directly, or through another one)."""
    bases: dict[str, set[str]] = {}
    for path in src.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.ClassDef):
                names = {b.id if isinstance(b, ast.Name) else b.attr if isinstance(b, ast.Attribute) else "" for b in node.bases}
                bases.setdefault(node.name, set()).update(names)
    models, changed = {"BaseModel"}, True
    while changed:
        changed = False
        for name, parents in bases.items():
            if name not in models and parents & models:
                models.add(name)
                changed = True
    return models - {"BaseModel"}


def models_used(src: Path = SRC) -> dict[str, set[str]]:
    """Model class name -> where it is passed to a LIBRARY database call (as the class, or a new row)."""
    classes = model_class_names(src)
    used: dict[str, set[str]] = {}
    for path in src.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr in DB_METHODS and node.args):
                continue
            receiver = ast.unparse(node.func.value)
            if "app_db" in receiver or "app_database" in receiver or "get_app_db" in receiver:
                continue
            if "db" not in receiver.lower() and not (receiver == "self" and "/db/" in str(path)):
                continue
            arg = node.args[0]
            name = arg.func.id if isinstance(arg, ast.Call) and isinstance(arg.func, ast.Name) else (
                arg.id if isinstance(arg, ast.Name) else None)
            if name in classes:
                used.setdefault(name, set()).add(f"{path.relative_to(src)}:{node.lineno}")
    return used


def problems(used: dict[str, set[str]], declared: set[str], not_a_table: dict[str, str]) -> list[str]:
    return [
        f"{name} is stored by the engine ({', '.join(sorted(where)[:2])}) but not declared in "
        "Database._all_schema_models: its table would appear on first save"
        for name, where in sorted(used.items()) if name not in declared and name not in not_a_table
    ]


def test_every_model_the_engine_stores_is_declared():
    declared = {model.__name__ for model in Database._all_schema_models(None)}
    found = problems(models_used(), declared, NOT_A_TABLE)
    assert found == [], "\n".join(found)


def test_the_scan_sees_what_it_must():
    """Not vacuous: the scan finds models the engine plainly stores, and #5178's."""
    used = models_used()
    assert {"Segment", "Document", "ContentRepresentation", "Rendition", "NoteLink", "MigrationRunRecord"} <= set(used)


class TestTheGuardFires:
    def test_an_undeclared_model_is_reported(self):
        found = problems({"Widget": {"api/widgets.py:12"}}, {"Segment"}, {})
        assert found == ["Widget is stored by the engine (api/widgets.py:12) but not declared in "
                         "Database._all_schema_models: its table would appear on first save"]

    def test_declared_or_explained_is_clean(self):
        assert problems({"Segment": {"a"}, "Embedded": {"b"}}, {"Segment"}, {"Embedded": "a reason"}) == []

    def test_a_model_through_another_model_is_still_a_model(self, tmp_path):
        (tmp_path / "m.py").write_text(
            "from pydantic import BaseModel\nclass Base(BaseModel): pass\nclass Row(Base): pass\n"
            "def f(db):\n    db.save(Row())\n    app_db.save(Row())\n")
        assert set(models_used(tmp_path)) == {"Row"} and len(models_used(tmp_path)["Row"]) == 1

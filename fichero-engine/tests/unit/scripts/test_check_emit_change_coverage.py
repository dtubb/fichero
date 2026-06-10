from __future__ import annotations

import importlib.util
from pathlib import Path


_SCRIPT = (
    Path(__file__).resolve().parents[3] / "scripts" / "check_emit_change_coverage.py"
)
_SPEC = importlib.util.spec_from_file_location("check_emit_change_coverage", _SCRIPT)
assert _SPEC and _SPEC.loader
check_emit_change_coverage = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(check_emit_change_coverage)  # type: ignore[attr-defined]


def _write_route(path: Path, method: str, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"""
from fastapi import APIRouter

router = APIRouter()


@router.{method}(\"/notes\")
def post_note():
    {body}
""",
        encoding="utf-8",
    )


def test_observed_domains_from_store_file(tmp_path, monkeypatch):
    models_dir = tmp_path / "fichero" / "fichero" / "Models"
    models_dir.mkdir(parents=True)
    (models_dir / "NoteStore.swift").write_text(
        """
class NoteStore {
    let changeDomains: Set<String> = [
        "note",
        "annotation"
    ]
}
""",
        encoding="utf-8",
    )

    routes_dir = tmp_path / "fichero-engine" / "src" / "fichero" / "api" / "routes"
    monkeypatch.setattr(check_emit_change_coverage, "ROOT", tmp_path)
    monkeypatch.setattr(check_emit_change_coverage, "MODELS_DIR", models_dir)
    monkeypatch.setattr(check_emit_change_coverage, "ROUTES_DIR", routes_dir)

    assert check_emit_change_coverage._observed_domains() == {"note", "annotation"}


def test_mutating_route_with_emit_change_is_not_a_gap(tmp_path, monkeypatch):
    routes_dir = tmp_path / "fichero-engine" / "src" / "fichero" / "api" / "routes"
    route_file = routes_dir / "notes.py"
    _write_route(route_file, "post", "emit_change()\n    return {'ok': True}")

    models_dir = tmp_path / "fichero" / "fichero" / "Models"
    models_dir.mkdir(parents=True)
    (models_dir / "NoteStore.swift").write_text(
        """
class NoteStore {
    let changeDomains: Set<String> = [
        "note"
    ]
}
""",
        encoding="utf-8",
    )

    monkeypatch.setattr(check_emit_change_coverage, "ROOT", tmp_path)
    monkeypatch.setattr(check_emit_change_coverage, "ROUTES_DIR", routes_dir)
    monkeypatch.setattr(check_emit_change_coverage, "MODELS_DIR", models_dir)
    monkeypatch.setattr(check_emit_change_coverage, "EXEMPT", set())

    rows = check_emit_change_coverage.scan()
    assert len(rows) == 1
    assert rows[0].emit_change
    assert rows[0].gap is False


def test_mutating_route_without_emit_change_is_gap(tmp_path, monkeypatch):
    routes_dir = tmp_path / "fichero-engine" / "src" / "fichero" / "api" / "routes"
    route_file = routes_dir / "notes.py"
    _write_route(route_file, "post", "return {'ok': True}")

    models_dir = tmp_path / "fichero" / "fichero" / "Models"
    models_dir.mkdir(parents=True)
    (models_dir / "NoteStore.swift").write_text(
        """
class NoteStore {
    let changeDomains: Set<String> = [
        "note"
    ]
}
""",
        encoding="utf-8",
    )

    monkeypatch.setattr(check_emit_change_coverage, "ROOT", tmp_path)
    monkeypatch.setattr(check_emit_change_coverage, "ROUTES_DIR", routes_dir)
    monkeypatch.setattr(check_emit_change_coverage, "MODELS_DIR", models_dir)
    monkeypatch.setattr(check_emit_change_coverage, "EXEMPT", set())

    rows = check_emit_change_coverage.scan()
    assert len(rows) == 1
    assert rows[0].emit_change is False
    assert rows[0].gap is True


def test_exempt_route_is_not_reported_as_gap(tmp_path, monkeypatch):
    routes_dir = tmp_path / "fichero-engine" / "src" / "fichero" / "api" / "routes"
    route_file = routes_dir / "notes.py"
    _write_route(route_file, "post", "return {'ok': True}")

    models_dir = tmp_path / "fichero" / "fichero" / "Models"
    models_dir.mkdir(parents=True)
    (models_dir / "NoteStore.swift").write_text(
        """
class NoteStore {
    let changeDomains: Set<String> = [
        "note"
    ]
}
""",
        encoding="utf-8",
    )

    monkeypatch.setattr(check_emit_change_coverage, "ROOT", tmp_path)
    monkeypatch.setattr(check_emit_change_coverage, "ROUTES_DIR", routes_dir)
    monkeypatch.setattr(check_emit_change_coverage, "MODELS_DIR", models_dir)
    monkeypatch.setattr(
        check_emit_change_coverage,
        "EXEMPT",
        {"fichero-engine/src/fichero/api/routes/notes.py::post_note"},
    )

    rows = check_emit_change_coverage.scan()
    assert len(rows) == 1
    assert rows[0].gap is True
    gaps = {
        row.key: row
        for row in rows
        if row.gap and row.key not in check_emit_change_coverage.EXEMPT
    }
    assert gaps == {}

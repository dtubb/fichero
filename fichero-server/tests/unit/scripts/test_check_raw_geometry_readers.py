"""The raw-geometry guardrail must be able to FAIL (#4924).

"Guardrails must match granularity": a rule with no fixture proving it can
fail is a rule nobody has tested. Every case below builds a small source
tree on disk and runs the real script's `main()` against it.

Why this guardrail exists, in one line: from a person's first edit the
stored `Artifact.ocr_geometry` block is frozen at the state BEFORE that
edit, so a reader that takes it serves a page as it looked before its owner
curated it -- correct-looking, silently wrong, nothing raised.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

SCRIPT = (
    Path(__file__).resolve().parents[4] / "scripts" / "check_raw_geometry_readers.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("check_raw_geometry_readers", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _tree(tmp_path: Path, files: dict[str, str]) -> Path:
    for rel, body in files.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    return tmp_path


def _run(monkeypatch, root: Path, scanned=("src",)):
    module = _load()
    monkeypatch.setattr(module, "REPO", root)
    monkeypatch.setattr(module, "SCANNED_ROOTS", scanned)
    monkeypatch.setattr(module, "PERMITTED", {"src/permitted.py"})
    return module.main()


def test_the_script_is_where_the_test_thinks_it_is():
    """A moved script would make every case below pass vacuously."""
    assert SCRIPT.exists(), SCRIPT


class TestItFails:
    def test_a_plain_read_outside_the_permitted_files_fails(self, tmp_path, monkeypatch, capsys):
        root = _tree(tmp_path, {"src/reader.py": "def f(a):\n    return a.ocr_geometry\n"})
        assert _run(monkeypatch, root) == 1
        assert "src/reader.py:2" in capsys.readouterr().out

    def test_a_read_buried_in_an_expression_fails(self, tmp_path, monkeypatch):
        root = _tree(tmp_path, {
            "src/reader.py": "def f(a):\n    return len(a.ocr_geometry.boxes) if a.ocr_geometry else 0\n"
        })
        assert _run(monkeypatch, root) == 1

    def test_a_read_in_a_comprehension_fails(self, tmp_path, monkeypatch):
        """The shape four of the six real offenders had."""
        root = _tree(tmp_path, {
            "src/reader.py": "def f(rows):\n    return [r for r in rows if r.ocr_geometry]\n"
        })
        assert _run(monkeypatch, root) == 1

    def test_a_pragma_with_no_reason_fails(self, tmp_path, monkeypatch, capsys):
        """The reason IS the allowance; an empty one is worse than none,
        because it looks considered."""
        root = _tree(tmp_path, {
            "src/reader.py": "def f(a):\n    return a.ocr_geometry  # raw-geometry-ok:\n"
        })
        assert _run(monkeypatch, root) == 1
        assert "no reason" in capsys.readouterr().out

    def test_a_missing_scanned_root_fails_rather_than_passing_vacuously(
        self, tmp_path, monkeypatch, capsys
    ):
        """The failure mode that matters most: a moved directory must not
        turn the check into a green no-op."""
        root = _tree(tmp_path, {"src/reader.py": "x = 1\n"})
        assert _run(monkeypatch, root, scanned=("src", "gone")) == 1
        assert "vacuously" in capsys.readouterr().out


class TestItPasses:
    def test_a_clean_tree_passes(self, tmp_path, monkeypatch):
        root = _tree(tmp_path, {"src/reader.py": "def f(db, a):\n    return live_geometry(db, a)\n"})
        assert _run(monkeypatch, root) == 0

    def test_a_permitted_file_may_read_it(self, tmp_path, monkeypatch):
        root = _tree(tmp_path, {"src/permitted.py": "def f(a):\n    return a.ocr_geometry\n"})
        assert _run(monkeypatch, root) == 0

    def test_a_line_with_a_reason_is_allowed_and_reported(self, tmp_path, monkeypatch, capsys):
        root = _tree(tmp_path, {
            "src/reader.py": "def f(a):\n    return a.ocr_geometry  # raw-geometry-ok: wants the original\n"
        })
        assert _run(monkeypatch, root) == 0
        out = capsys.readouterr().out
        assert "wants the original" in out, "an allowance must be visible, not silent"

    def test_writing_the_field_is_not_a_read(self, tmp_path, monkeypatch):
        """Building an artifact is how a block gets there in the first
        place; this guardrail is about READS."""
        root = _tree(tmp_path, {
            "src/writer.py": (
                "def f(a, g):\n"
                "    a.ocr_geometry = g\n"
                "    return Artifact(ocr_geometry=g)\n"
            )
        })
        assert _run(monkeypatch, root) == 0

    def test_a_similarly_named_attribute_is_not_matched(self, tmp_path, monkeypatch):
        root = _tree(tmp_path, {
            "src/reader.py": "def f(a):\n    return a.ocr_geometry_status, a.geometry\n"
        })
        assert _run(monkeypatch, root) == 0


class TestItAdmitsWhatItCannotSee:
    def test_a_dynamic_read_is_reported_not_silently_dropped(self, tmp_path, monkeypatch, capsys):
        """A green run means "no direct attribute read", NOT "everything
        reads live". Saying so is the difference between a guardrail and a
        false sense of one."""
        root = _tree(tmp_path, {
            "src/reader.py": "def f(a, field):\n    return getattr(a, field)\n"
        })
        assert _run(monkeypatch, root) == 0
        out = capsys.readouterr().out
        assert "dynamic" in out and "does not cover" in out


class TestTheRealTreeIsClean:
    def test_the_repository_passes_its_own_guardrail(self, capsys):
        """The check running against the real source, not a fixture."""
        module = _load()
        assert module.main() == 0, capsys.readouterr().out

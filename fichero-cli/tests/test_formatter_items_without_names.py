"""An item with no id or name says what it holds (#5659 hands-on pass).

WHY: `fichero docs transfer --dry-run` printed `counts: - (item)`: the plan's counts by kind are rows with no
id or name, so the human renderer dropped everything a person ran the dry run to read.
"""

from fichero_cli.formatters import _human


def test_a_row_without_id_or_name_prints_its_fields():
    text = _human({"counts": [{"kind": "Document", "planned": 2, "written": None}]})
    assert "(item)" not in text
    assert "kind: Document, planned: 2" in text and "written" not in text


def test_a_trash_row_says_why_it_is_there():
    text = _human({"items": [{"id": "e3", "name": "p2.png", "doc_type": "file", "why": "Moved to Destino on 11 Oct 2026"}]})
    assert "p2.png  [file]  — Moved to Destino on 11 Oct 2026" in text

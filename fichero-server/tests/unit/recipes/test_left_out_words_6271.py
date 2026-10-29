"""The left-out reason is worded by its real cause (#6271), to the spec `source.recipe.left-out-is-not-done`.

WHY: "all N left out as blank" counted every left_out entry, but for find-names those are pages too uncertain for names."""

from __future__ import annotations

from fichero_server.models import DocType, Document
from fichero_server.recipes import runner
from tests.unit.recipes.test_names_on_unreadable_text_5694 import NAMES, _read
from tests.unit.training.test_kraken_training_set import BOOT, PAGE, _page


def test_names_left_out_for_uncertainty_is_not_called_blank(db, tmp_path, monkeypatch):
    from fichero_server.actions.registry import registry

    folder = Document(name="CACIQUES", doc_type=DocType.folder)
    db.save(folder)
    poor = _page(db, tmp_path, "1_Hoja", folder, read_by=None)
    registry.invoke(db, "format.import", {"document_id": poor.id, "path": str(PAGE)}, BOOT)
    _read(db, poor, 0.42)
    monkeypatch.setattr(runner, "_run_workflow", lambda *a, **k: ("thread", "done", None))
    job_id = runner.enqueue(db, {"runs": [NAMES], "skipped": []}, documents=[poor.id], started_by="owner")
    _kind, subject = db.execute_fetchone("SELECT kind, subject FROM jobs WHERE id = ?", [job_id])

    (step,) = runner.run(db, subject)["steps"]

    assert "blank" not in step["why"] and "too uncertain for names" in step["why"] and "1 page" in step["why"]

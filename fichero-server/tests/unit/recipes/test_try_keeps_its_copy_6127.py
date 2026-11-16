"""`wide.try.start-reuses-a-matching-try`, slice A (#6127): a done try keeps its copy and a record per page; the copy expires after the
project's days or at the next try of the same stage; the days and the overlap are the project's settings."""
from __future__ import annotations

import json
import time

from fichero_server.recipes import adopt


def _kept(samples, name, stage, age_days):
    path = samples / f"{name}.fichero"
    path.mkdir(parents=True)
    adopt.keep(path, {"stage": stage, "pages": []})
    record = json.loads((path / adopt.RECORD).read_text())
    record["kept_at"] = time.time() - age_days * 86400
    (path / adopt.RECORD).write_text(json.dumps(record))
    return path


def test_settings_default_to_the_approved_figures_and_a_project_can_say_otherwise(tmp_path):
    assert adopt.settings(tmp_path) == {"keep_days": 7.0, "match_iou": 0.9}
    (tmp_path / "recipe").mkdir()
    (tmp_path / "recipe" / "try-settings.yaml").write_text("keep_days: 2\nmatch_iou: 0.8\n")
    assert adopt.settings(tmp_path) == {"keep_days": 2.0, "match_iou": 0.8}
    (tmp_path / "recipe" / "try-settings.yaml").write_text("keep_days: -1\nmatch_iou: 5\n")
    assert adopt.settings(tmp_path) == {"keep_days": 7.0, "match_iou": 0.9}  # nonsense falls back, never fails


def test_a_copy_older_than_the_days_goes_and_a_newer_one_stays(tmp_path):
    old, new = _kept(tmp_path, "read", "read", 8), _kept(tmp_path, "read-1", "read", 1)
    assert adopt.sweep(tmp_path, keep_days=7) == ["read.fichero"] and not old.exists() and new.exists()


def test_the_next_try_of_a_stage_replaces_that_stages_copies_only(tmp_path):
    mine, other = _kept(tmp_path, "read", "read", 0), _kept(tmp_path, "lines", "find-lines", 0)
    assert adopt.sweep(tmp_path, keep_days=7, stage="read") == ["read.fichero"] and not mine.exists() and other.exists()


def test_the_settings_hash_follows_the_cards_not_their_key_order():
    a = [{"card": "x", "model": {"hf": "m"}, "answers": {"b": 1, "a": 2}}]
    b = [{"answers": {"a": 2, "b": 1}, "model": {"hf": "m"}, "card": "x"}]
    assert adopt.settings_hash(a) == adopt.settings_hash(b) != adopt.settings_hash([{"card": "y"}])


def test_a_page_record_names_card_hash_signature_and_the_copy_page(db, tmp_path):
    from PIL import Image

    from fichero_server.models import DocType, Document, FileType

    path = tmp_path / "p.png"
    Image.new("RGB", (20, 20), (200, 200, 200)).save(path)
    doc = Document(name="p.png", doc_type=DocType.page, file_type=FileType.image, path=str(path), metadata={})
    db.save(doc)
    row = adopt.page_record(db, tmp_path, doc.id, "copy-1", card_ids=["workflow"], hash_="h")
    assert row["page"] == doc.id and row["copy_page"] == "copy-1" and row["cards"] == ["workflow"] and row["settings"] == "h"
    assert row["signature"]  # the photograph's own signature, the one a later read compares

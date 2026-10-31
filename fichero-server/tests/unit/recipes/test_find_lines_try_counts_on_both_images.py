"""`wide.faded.line-counts-before-and-after` engine half (#6271): the Find Lines try segments a page with a clarified copy on
the photograph and on the copy, and answers both counts, so Set Up can show them side by side."""
from __future__ import annotations

from types import SimpleNamespace

from fichero_server.recipes import samples
from tests.unit.recipes.test_stage_try_words_5687 import _pages, _run, _set_up


def _image(path, why, kind="rendition"):
    return SimpleNamespace(path=path, kind=kind, photograph="/lib/photo.jpg", why=why)


def test_wide_a_page_with_a_clarified_copy_is_counted_on_both_and_the_others_are_named(db, tmp_path, monkeypatch):
    from fichero_server.media import current_image

    faded, clear = _pages(db, tmp_path, 2)
    images = {faded.id: _image("/lib/prepared.png", "the newest rendition (prepared)"),
              clear.id: _image("/lib/photo.jpg", "the photograph", kind="original")}
    monkeypatch.setattr(current_image, "current_page_image", lambda db_, doc, **k: images[doc.id])
    counted = []
    monkeypatch.setattr(samples, "_count_lines", lambda db_, doc, path, run: counted.append(path) or (12 if path.endswith("prepared.png") else 5))

    got = samples.line_counts_on_both(db, [faded.id, clear.id], "job-1")

    assert got["pages"] == {faded.id: {"photograph": 5, "clarified": 12}}
    assert got["not_clarified"] == [clear.id], "a page with no clarified copy is named, not counted twice"
    assert sorted(counted) == ["/lib/photo.jpg", "/lib/prepared.png"], "the segmenter ran once on each image"


def test_wide_the_find_lines_try_result_carries_the_two_counts(client, db, tmp_path, monkeypatch, jobs_run_by_the_test):
    from fichero_server.media import current_image
    from fichero_server.recipes import runner

    page, = _pages(db, tmp_path, 1)
    _set_up(client, ["find-lines"])
    monkeypatch.setattr(runner, "_run_workflow", lambda *a, **k: (None, "done", None))
    monkeypatch.setattr(current_image, "current_page_image",
                        lambda db_, doc, **k: _image("/lib/prepared.png", "the newest rendition (prepared)"))
    monkeypatch.setattr(samples, "_count_lines", lambda db_, doc, path, run: 12 if path.endswith("prepared.png") else 5)
    started = client.post("/api/recipes/stages/find-lines/try", json={"candidates": ["kraken:builtin/blla@bundled"]})
    assert started.status_code == 200, started.text
    _run(db, started.json())

    result = client.get("/api/recipes/stages/find-lines/try").json()
    assert result["line_counts"]["pages"] == {page.id: {"photograph": 5, "clarified": 12}}, result

"""Prepare Images answers per folder, the paper answer's gates, the split gate and the two new suggestions
(`prep.setup.three-questions-suggested-from-a-sample`, `prep.setup.what-runs-by-itself`, #5580)."""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from PIL import Image, ImageDraw

from fichero_server.recipes import prepare_suggest
from fichero_server.recipes.answers import normalise
from fichero_server.recipes.start import plan_start
from tests.unit.recipes.test_start_plan import LINES, _recipe

PREP = {"id": "prep", "job": "prepare-the-image", "model": {"builtin": "image-preparer"}}
SPLIT = {"id": "split", "job": "split-pages", "model": {"builtin": "page-splitter"}}
PAPER = (238, 236, 224)


def _runs(plan, job):
    return [r for r in plan["runs"] if r["job"] == job]


def test_a_folders_own_paper_answer_gets_its_own_prepare_run_and_the_project_run_leaves_it_out():
    plan = plan_start(_recipe(PREP, LINES), stays_local=True, job_answers={"the_paper": ["faded"]},
                      job_answers_by_folder={"f1": {"the_paper": ["ruled"]}})
    base, own = _runs(plan, "prepare-the-image")
    assert base["paper"] == ["faded"] and base["exclude_folders"] == ["f1"] and "folder_id" not in base
    assert own["folder_id"] == "f1" and own["paper"] == ["ruled"] and own["exclude_folders"] == []


def test_no_folder_answers_plans_exactly_as_before():
    plan = plan_start(_recipe(PREP, SPLIT, LINES), stays_local=True, job_answers={"the_paper": ["faded"]})
    assert all("folder_id" not in r and "exclude_folders" not in r for r in plan["runs"])
    assert len(_runs(plan, "split-pages")) == 1  # an unanswered split question keeps today's behaviour


def test_each_paper_option_is_its_own_gate_and_the_plan_says_what_is_not_built():
    plan = plan_start(_recipe(PREP, LINES), stays_local=True, job_answers={"the_paper": ["ruled", "show-through"]})
    (run,) = _runs(plan, "prepare-the-image")
    assert run["paper"] == ["ruled", "show-through"]
    assert "Ruling is not taken out yet" in run["how"] and "Show-through is not taken out yet" in run["how"]
    faded = plan_start(_recipe(PREP, LINES), stays_local=True, job_answers={"the_paper": ["faded"]})
    assert "not taken out" not in _runs(faded, "prepare-the-image")[0]["how"]


def test_the_contrast_step_runs_only_for_faded_or_no_answer():
    from fichero_server.recipes.prepare import runs_contrast

    assert runs_contrast([]) and runs_contrast(None) and runs_contrast(["faded", "ruled"])
    assert not runs_contrast(["ruled"]) and not runs_contrast(["show-through"])


def test_two_pages_answered_no_skips_the_split_with_its_why_and_yes_or_unanswered_runs_it():
    no = plan_start(_recipe(SPLIT, LINES), stays_local=True, job_answers={"two_pages_per_image": False})
    assert not _runs(no, "split-pages")
    assert any(s["step"] == "split" and "Two pages in one picture?" in s["why"] for s in no["skipped"])
    yes = plan_start(_recipe(SPLIT, LINES), stays_local=True, job_answers={"two_pages_per_image": True})
    assert len(_runs(yes, "split-pages")) == 1
    assert not any(s["step"] == "split" for s in yes["skipped"])


def test_a_folder_can_say_yes_where_the_project_says_no_and_no_where_it_says_yes():
    yes_in_folder = plan_start(_recipe(SPLIT, LINES), stays_local=True, job_answers={"two_pages_per_image": False},
                               job_answers_by_folder={"f1": {"two_pages_per_image": True}})
    (only,) = _runs(yes_in_folder, "split-pages")
    assert only["folder_id"] == "f1"
    no_in_folder = plan_start(_recipe(SPLIT, LINES), stays_local=True, job_answers={"two_pages_per_image": True},
                              job_answers_by_folder={"f2": {"two_pages_per_image": False}})
    (base,) = _runs(no_in_folder, "split-pages")
    assert base["exclude_folders"] == ["f2"] and "folder_id" not in base


def test_a_folder_answer_beside_a_folder_reader_keeps_both_exclusions():
    recipe = _recipe(PREP, LINES)
    recipe["overrides"] = []
    plan = plan_start(recipe, stays_local=True, job_answers_by_folder={"f1": {"the_paper": ["faded"]}})
    assert _runs(plan, "prepare-the-image")[0]["exclude_folders"] == ["f1"]


def test_a_folders_answers_are_kept_by_folder_and_a_bad_shape_is_refused():
    kept = normalise({"purposes": ["transcribe"], "job_answers_by_folder": {"f1": {"the_paper": ["faded"]}}}, strict=True)
    assert kept["job_answers_by_folder"] == {"f1": {"the_paper": ["faded"]}}
    with pytest.raises(ValueError, match="folder"):
        normalise({"purposes": ["transcribe"], "job_answers_by_folder": {"f1": ["faded"]}}, strict=True)


def _words(draw, boxes, fill):
    for x, y in boxes:
        for i in range(5):
            draw.rectangle([x + i * 70, y, x + i * 70 + 50, y + 8], fill=fill)


ROWS = [(60, 100 + 90 * i) for i in range(10)]
LINE_BOXES = [[[0.04, (y - 20) / 1200], [0.6, (y - 20) / 1200], [0.6, (y + 30) / 1200], [0.04, (y + 30) / 1200]]
              for _, y in ROWS]


def test_ink_outside_the_line_boxes_is_the_missed_lines_figure():
    inside = Image.new("RGB", (900, 1200), PAPER)
    _words(ImageDraw.Draw(inside), ROWS, (25, 25, 40))
    assert prepare_suggest.outside_share(inside, LINE_BOXES) < 0.01
    missed = inside.copy()
    _words(ImageDraw.Draw(missed), [(60, 1020), (60, 1080), (60, 1130)], (25, 25, 40))  # lines the segmenter did not find
    assert prepare_suggest.outside_share(missed, LINE_BOXES) > prepare_suggest.MISSED_SHARE
    assert prepare_suggest.outside_share(Image.new("RGB", (900, 1200), PAPER), LINE_BOXES) is None


def _page(strong=(), faint=(), ruling=False):
    image = Image.new("RGB", (900, 1200), PAPER)
    draw = ImageDraw.Draw(image)
    if ruling:
        for y in range(80, 1200, 40):
            draw.line([(0, y), (900, y)], fill=(210, 208, 196), width=2)
    _words(draw, strong, (25, 25, 40))
    _words(draw, faint, (218, 216, 204))
    return image


def _mirror(boxes):
    return [(900 - x - 5 * 70 + 20, y) for x, y in boxes]  # the flip of a row of five words, 50 wide at 70 steps


def test_a_faint_mirrored_copy_of_the_previous_page_is_show_through_and_a_ruling_alone_is_not():
    previous = _page(strong=ROWS)
    other_rows = [(60, 100 + 90 * i + 45) for i in range(10)]
    through = _page(strong=other_rows, faint=_mirror(ROWS))
    assert prepare_suggest.shows_through(previous, through) is True
    unrelated = _page(strong=other_rows, faint=[(300, 100 + 90 * i) for i in range(10)])
    assert prepare_suggest.shows_through(previous, unrelated) is False
    ruled_only = _page(strong=other_rows, ruling=True)
    assert not prepare_suggest.shows_through(previous, ruled_only)  # no faint marks beyond the ruling: it cannot say


def _fake_db(monkeypatch, tmp_path, pages):
    from fichero_server.media import find_page as module
    from fichero_server.recipes import prepare

    ids = [f"p{i}" for i in range(len(pages))]
    by_id = dict(zip(ids, pages))
    db = SimpleNamespace(unit_of_work_ids=lambda: ids)
    monkeypatch.setattr(prepare_suggest, "_page_image", lambda _db, i, frame_upright=True: by_id[i].copy())
    monkeypatch.setattr(prepare_suggest, "_page_path", lambda _db, i: None)
    monkeypatch.setattr(prepare, "is_faded", lambda path: False)
    monkeypatch.setattr(module, "find_page", lambda image: None)
    monkeypatch.setattr(prepare_suggest, "is_ruled", lambda image: False)
    return db


def test_the_sample_suggests_check_missed_lines_when_three_of_five_leave_ink_outside_the_boxes(monkeypatch, tmp_path):
    from fichero_server.llm import working_lines as module

    leaky = _page(strong=[*ROWS, (60, 1020), (60, 1080), (60, 1130)])
    clean = _page(strong=ROWS)
    db = _fake_db(monkeypatch, tmp_path, [leaky, leaky, leaky, clean, clean])
    monkeypatch.setattr(module, "working_lines", lambda _db, doc_id: SimpleNamespace(lines=[], frame=None))
    monkeypatch.setattr(prepare_suggest, "_fraction_polygons", lambda lines: LINE_BOXES)
    got = prepare_suggest.suggest(db)
    assert got["check_missed_lines"]["value"] is True and got["check_missed_lines"]["agree"] == "3 of 5"
    assert "not built" in got["check_missed_lines"]["why"]
    db = _fake_db(monkeypatch, tmp_path, [leaky, leaky, clean, clean, clean])
    assert "check_missed_lines" not in prepare_suggest.suggest(db)


def test_the_sample_suggests_show_through_from_the_previous_page_and_not_from_a_ruling(monkeypatch, tmp_path):
    from fichero_server.llm import working_lines as module

    monkeypatch.setattr(module, "working_lines", lambda _db, doc_id: None)
    front = _page(strong=ROWS)
    other_rows = [(60, 100 + 90 * i + 45) for i in range(10)]
    back = _page(strong=other_rows, faint=_mirror(ROWS))
    db = _fake_db(monkeypatch, tmp_path, [front, back, front, back, front])
    got = prepare_suggest.suggest(db)
    assert got["the_paper"]["value"] == ["show-through"]
    ruled = _page(strong=other_rows, ruling=True)
    db = _fake_db(monkeypatch, tmp_path, [front, ruled, front, ruled, front])
    assert "the_paper" not in prepare_suggest.suggest(db)


def test_the_card_says_which_prepare_questions_no_step_reads():
    """Review LOW: `beside_the_page` and `check_missed_lines` are asked but no step reads them; the card says so
    (`read_by_a_step` false). `two_pages_per_image` and `the_paper` are read: the plan gates the split and the contrast."""
    from fichero_server.recipes.stages import STAGES

    (stage,) = [s for s in STAGES if s.id == "prepare-images"]
    read = {q.key: q.read_by_a_step for q in stage.questions}
    assert read == {"two_pages_per_image": True, "beside_the_page": False, "the_paper": True, "check_missed_lines": False}

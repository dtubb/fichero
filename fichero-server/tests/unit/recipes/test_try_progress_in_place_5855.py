"""#5855, #5856: a Set Up try shows its progress in place, and Compare carries each model's lines per page
(`source.onboard.stages.try-progress-in-place`, `source.onboard.stages.compare-results-per-model`).

The pieces are pure so they are tested without a library: the progress sentence data, the shape of a segment as the
compare window draws it, and the writer that updates one candidate's column in the kept result as pages finish."""
from __future__ import annotations

import json
from types import SimpleNamespace

from fichero_server.recipes import samples


def _page(pid, **segments):
    return {"id": pid, "name": pid, "readings": [], "segments": segments, "statements": []}


def test_progress_counts_the_pages_a_model_has_made_something_on_and_names_the_step_in_words():
    made = [_page("p1", line=27), _page("p2", line=3)]
    p = samples.progress_of(made, total=5, stage_id="find-lines", state="running", page="IMG_2.jpg")
    assert p == {"state": "running", "done": 2, "total": 5, "page": "IMG_2.jpg", "step": "finding lines",
                 "waiting_for": None}


def test_a_stage_whose_kind_is_reading_says_reading_and_an_unknown_stage_its_title_in_lower_case():
    assert samples.progress_of([], total=3, stage_id="read", state="waiting")["step"] == "reading"
    assert samples.progress_of([], total=3, stage_id="find-regions", state="waiting")["step"] == "finding regions"
    assert samples.progress_of([], total=3, stage_id="no-such-stage", state="waiting")["step"] == "working"


def test_a_page_with_no_result_yet_does_not_count_as_done():
    assert samples.progress_of([_page("p1")], total=2, stage_id="find-lines", state="running")["done"] == 0


def test_a_segment_is_drawn_from_its_kind_box_and_baseline():
    seg = SimpleNamespace(kind="line", bbox_x=0.1, bbox_y=0.2, bbox_w=0.5, bbox_h=0.05, baseline=[[0.1, 0.24], [0.6, 0.24]])
    assert samples.shape_of(seg) == {"kind": "line", "bbox": [0.1, 0.2, 0.5, 0.05], "baseline": [[0.1, 0.24], [0.6, 0.24]]}
    seg.baseline = None
    assert samples.shape_of(seg)["baseline"] is None


def test_shapes_are_capped_a_page():
    many = [SimpleNamespace(kind="line", bbox_x=0, bbox_y=0, bbox_w=1, bbox_h=1, baseline=None)] * (samples.MAX_SHAPES + 50)
    assert len(samples.shapes_of(many)) == samples.MAX_SHAPES


def test_publishing_a_candidates_progress_updates_only_its_column_and_keeps_the_rest(tmp_path):
    library = tmp_path
    samples._write(library, "find-lines", {"stage": "find-lines", "state": "waiting",
                                           "candidates": [{"card": "a", "state": "waiting"}, {"card": "b", "state": "waiting"}]})
    made = [_page("p1", line=27)]
    samples.publish_progress(library, "find-lines", "b", samples.progress_of(made, 5, "find-lines", "running"), made)
    result = json.loads(samples._result_path(library, "find-lines").read_text())
    a, b = result["candidates"]
    assert "progress" not in a and "per_page" not in a
    assert b["progress"]["done"] == 1 and b["progress"]["total"] == 5 and b["per_page"] == made and b["state"] == "running"


def test_publishing_into_a_try_with_no_record_is_quietly_nothing(tmp_path):
    samples.publish_progress(tmp_path, "find-lines", "b", {"state": "running"}, [])  # no error: the try may be gone


# --- review 323 and the M4 TRYPROGRESS run -------------------------------------------------------------------------

def test_concurrent_writes_to_one_result_never_raise_and_leave_a_whole_file(tmp_path):
    """The watcher and the try thread both wrote the same `.tmp` name: a replace could find it gone."""
    import threading

    samples._write(tmp_path, "find-lines", {"state": "waiting", "candidates": [{"card": "a"}]})
    errors: list[BaseException] = []

    def hammer(kind):
        try:
            for n in range(150):
                if kind == "publish":
                    samples.publish_progress(tmp_path, "find-lines", "a", {"state": "running", "done": n}, [])
                else:
                    samples._write(tmp_path, "find-lines", {"state": "done", "candidates": [{"card": "a"}]})
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=hammer, args=(k,)) for k in ("publish", "publish", "write", "write")]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert not errors
    assert json.loads(samples._result_path(tmp_path, "find-lines").read_text())["candidates"][0]["card"] == "a"
    assert not list(samples._folder(tmp_path).glob("*.tmp")), "no temp file is left behind"


def test_a_stage_try_with_no_candidates_publishes_its_progress_on_the_result(tmp_path):
    samples._write(tmp_path, "names", {"stage": "names", "state": "waiting"})
    made = [_page("p1", line=2)]
    samples.publish_progress(tmp_path, "names", None, samples.progress_of(made, 3, "names", "running"), made)
    result = json.loads(samples._result_path(tmp_path, "names").read_text())
    assert result["progress"]["done"] == 1 and result["progress"]["total"] == 3 and result["per_page"] == made


def test_a_run_that_ended_paused_says_so_in_words_and_no_failure_is_blank():
    from fichero_server.recipes.runner import outcome_why

    assert outcome_why("paused", None) == "the engine stopped while this was running; try it again"
    assert outcome_why("failed", "the model is missing") == "the model is missing"
    assert outcome_why("cancelled", None) and outcome_why("something-odd", "")


def test_the_final_progress_counts_the_pages_with_a_result_and_names_how_it_ended():
    made = [_page("p1", line=2), _page("p2", line=1)]
    assert samples.finished_progress("failed", made, 5, "find-lines")["state"] == "failed"
    assert samples.finished_progress("failed", made, 5, "find-lines")["done"] == 2
    assert samples.finished_progress("done", made, 2, "find-lines")["state"] == "done"

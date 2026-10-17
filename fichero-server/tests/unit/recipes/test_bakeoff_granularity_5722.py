"""A/B measures how a model is asked: a line, a region or the page (#5722, `source.try.asking-granularity-is-measured`).

WHY: how many lines a model is asked at once changes how well it reads them, and a small model may read a paragraph
right and a page wrong. Nothing measured it, so the recipe could only guess. The bake-off asks its two best vision
candidates (and any the person named) at every granularity, the table names the granularity beside each row, and Use
This records it with the model. A card's `lines_per_request` caps every request.

Vision is faked at its seam (`evaluation.ask_vision`) and the line pictures are not cut: no model, no network.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fichero_server.recipes import bakeoff
from fichero_server.training import evaluation
from fichero_server.workflows.transcription_accuracy import DEFAULT_POLICY_NAME
from tests.unit.training.test_evaluation_job import (  # noqa: F401  (fixtures)
    CHECKED,
    _run,
    homes,
    project,
)

MODEL = "mlx-community/some-vl"
CARD = "mlx:hf/mlx-community/some-vl@unpinned"


def _lines(regions: list[int]) -> list[dict]:
    """Lines numbered across regions of the given sizes, in reading order."""
    out = []
    for r, size in enumerate(regions):
        for _ in range(size):
            i = len(out)
            out.append({"id": f"l{i}", "text": f"text {i}", "polygon": [[i, 0], [i + 1, 0], [i + 1, 1]],
                        "region": f"r{r}"})
    return out


def _sizes(groups: list[list[dict]]) -> list[int]:
    return [len(g) for g in groups]


def test_a_request_is_a_line_a_region_or_the_page_and_never_over_the_cap():
    lines = _lines([3, 5, 2])
    assert _sizes(evaluation.requests_for(lines, "lines")) == [1] * 10
    assert _sizes(evaluation.requests_for(lines, "region")) == [3, 5, 2]
    assert _sizes(evaluation.requests_for(lines, "page")) == [10]
    # A region longer than the card's limit is split on line boundaries, in order, never over it.
    split = evaluation.requests_for(lines, "region", 2)
    assert _sizes(split) == [2, 1, 2, 2, 1, 2] and [ln["id"] for g in split for ln in g] == [ln["id"] for ln in lines]
    assert max(_sizes(evaluation.requests_for(lines, "page", 4))) == 4
    # A page with no regions is one region.
    bare = [{**ln, "region": ""} for ln in lines]
    assert _sizes(evaluation.requests_for(bare, "region")) == [10]


def test_a_vision_model_is_asked_at_the_granularity_and_every_answer_lands_on_its_line(monkeypatch, tmp_path):
    from PIL import Image

    photo = tmp_path / "page.png"
    Image.new("RGB", (20, 20), "white").save(photo)
    lines = _lines([3, 2])
    by_uri = {f"uri:{ln['polygon'][0][0]}": ln for ln in lines}
    monkeypatch.setattr("fichero_server.llm.line_reader._crop_data_uri", lambda page, polygon: f"uri:{polygon[0][0]}")
    asked = []

    async def answer(candidate, images, prompt):
        asked.append(len(images))
        return json.dumps([by_uri[u]["text"] for u in images])

    monkeypatch.setattr(evaluation, "ask_vision", answer)
    for granularity, expected in (("lines", [1] * 5), ("region", [3, 2]), ("page", [5])):
        asked.clear()
        candidate = evaluation.EvaluationCandidate(model=MODEL, reader="vision", provider="omlx",
                                                   granularity=granularity)
        reads, why = evaluation.read_with_vision(str(photo), candidate, lines, None)
        assert asked == expected and why is None
        assert reads == [ln["text"] for ln in lines]


def test_an_answer_that_does_not_match_its_request_is_not_guessed_into_place(monkeypatch, tmp_path):
    """The measure is how well the model answers asked THIS way: a request answered with the wrong number of
    lines reads as nothing for its lines (the other requests still read), never re-asked another way."""
    from PIL import Image

    photo = tmp_path / "page.png"
    Image.new("RGB", (20, 20), "white").save(photo)
    lines = _lines([2, 2])
    monkeypatch.setattr("fichero_server.llm.line_reader._crop_data_uri", lambda page, polygon: f"uri:{polygon[0][0]}")
    calls = []

    async def answer(candidate, images, prompt):
        calls.append(len(images))
        return json.dumps(["only one"]) if images[0] == "uri:0" else json.dumps(["a", "b"])

    monkeypatch.setattr(evaluation, "ask_vision", answer)
    candidate = evaluation.EvaluationCandidate(model=MODEL, reader="vision", provider="omlx", granularity="region")
    reads, why = evaluation.read_with_vision(str(photo), candidate, lines, None)
    assert calls == [2, 2] and reads == ["", "", "a", "b"] and why is None


@pytest.fixture
def right_only_per_paragraph(db, project, monkeypatch):  # noqa: F811
    """A model whose answers are right only when it is asked exactly one region's lines."""
    monkeypatch.setattr(evaluation, "on_this_mac", lambda *a, **k: True)
    monkeypatch.setattr("fichero_server.llm.line_reader._crop_data_uri",
                        lambda page, polygon: "uri:" + json.dumps(polygon))
    pages = [evaluation.reference_page(db, d.id, CHECKED)[0] for d in project["held"]]
    lines = {"uri:" + json.dumps(ln["polygon"]): ln for p in pages for ln in p["lines"]}
    region_of = {u: ln["region"] for u, ln in lines.items()}
    members = {}
    for u, r in region_of.items():
        members.setdefault(r, set()).add(u)
    asked = []

    async def answer(candidate, images, prompt):
        asked.append(len(images))
        whole_region = set(images) == members[region_of[images[0]]]
        return json.dumps([lines[u]["text"] if whole_region else lines[u]["text"][::-1] for u in images])

    monkeypatch.setattr(evaluation, "ask_vision", answer)
    return asked


def _cer(result):
    return {m["granularity"]: m["scores"][DEFAULT_POLICY_NAME]["cer"] for m in result["models"]}


def test_a_model_right_only_per_paragraph_wins_at_paragraph_and_loses_at_page(client, db, project,  # noqa: F811
                                                                              right_only_per_paragraph):
    held = [d.id for d in project["held"]]
    _, status = _run(client, db, candidates=[{"model": MODEL, "reader": "vision"}], add_out_of_the_box=False,
                     held_out_ids=held, granularities_for_best=2)
    result = status["result"]
    assert {m["granularity"] for m in result["models"]} == {"lines", "region", "page"}
    cer = _cer(result)
    assert cer["region"] == 0.0 and cer["page"] > 0.0 and cer["lines"] > 0.0
    # One model asked three ways is still one candidate: the table ranks the rows, a winner needs two models.
    assert result["no_best_why"]


def test_the_full_set_goes_to_the_two_best_and_the_named_the_rest_run_once(client, db, project,  # noqa: F811
                                                                           right_only_per_paragraph):
    held = [d.id for d in project["held"]]
    others = ["mlx-community/b-vl", "mlx-community/c-vl", "mlx-community/d-vl"]
    cands = [{"model": m, "reader": "vision"} for m in (MODEL, *others)]
    _, status = _run(client, db, candidates=cands, add_out_of_the_box=False, held_out_ids=held,
                     granularities_for_best=2, named=[others[2]])
    seen = {}
    for m in status["result"]["models"]:
        seen.setdefault(m["model"], set()).add(m["granularity"])
    full = {"lines", "region", "page"}
    with_full = {m for m, g in seen.items() if g == full}
    assert others[2] in with_full and len(with_full) == 3  # the two best, and the one the person named
    assert [m for m, g in seen.items() if m not in with_full and g == {"lines"}]  # the other ran once


def test_a_cards_lines_per_request_caps_every_request_and_means_no_page(client, db, project,  # noqa: F811
                                                                        right_only_per_paragraph):
    held = [d.id for d in project["held"]]
    _, status = _run(client, db, candidates=[{"model": MODEL, "reader": "vision", "lines_per_request": 3}],
                     add_out_of_the_box=False, held_out_ids=held, granularities_for_best=2)
    assert {m["granularity"] for m in status["result"]["models"]} == {"lines", "region"}  # no page: it states a cap
    assert max(right_only_per_paragraph) <= 3


def test_without_a_trial_a_model_runs_once_at_its_default(client, db, project, right_only_per_paragraph):  # noqa: F811
    held = [d.id for d in project["held"]]
    _, status = _run(client, db, candidates=[{"model": MODEL, "reader": "vision"}], add_out_of_the_box=False,
                     held_out_ids=held)
    assert [m["granularity"] for m in status["result"]["models"]] == ["lines"]


def test_the_table_names_the_granularity_beside_each_row_and_use_this_records_it(client, db, project,  # noqa: F811
                                                                                   right_only_per_paragraph):
    held = [d.id for d in project["held"]]
    job_id, _ = _run(client, db, candidates=[{"model": MODEL, "reader": "vision"}], add_out_of_the_box=False,
                     held_out_ids=held, granularities_for_best=2)
    library = Path(db.path).parent
    candidate = {"card": CARD, "name": "Some VL", "pin": {"hf": MODEL}, "role": "contender", "rule_rank": None,
                 "reader": "vision", "model": MODEL, "provider": "omlx", "runs_on": "this-mac", "local": True,
                 "not_scored": None, "cost_usd": {"value": 0.0, "basis": "measured", "source": "runs here"},
                 "carbon_g_per_page": None, "trainable": False, "size_gb": 1.0, "material": ["handwriting"]}
    bakeoff.write_record(library, {"id": "bk1", "job_id": job_id, "step": "read-a-line", "started_at": "2026-10-16",
                                   "material": "handwriting", "volume": 10, "pages": [], "left_out": [], "lines": 88,
                                   "candidates": [candidate]})
    table = bakeoff.result(db, library, "bk1")
    by = {r["granularity"]: r for r in table["rows"]}
    assert set(by) == {"lines", "region", "page"} and by["region"]["rank"] == 1
    assert table["rows"][0]["granularity"] == "region"

    from fichero_server.recipes.assemble import Card

    card = Card(id=CARD, pin={"hf": MODEL}, jobs=frozenset({"read-a-line"}), scripts=None, languages=None,
                material=frozenset({"handwriting"}), runs_on="this-mac", note="Some VL")
    recipe = {"steps": [{"id": "read", "job": "read-a-line"}]}
    used = bakeoff.use_this(recipe, table, card, scope="project", folder_id=None, now="2026-10-16")
    (override,) = used["overrides"]
    assert override["card"] == CARD and override["granularity"] == "region"
    assert used["steps"][0]["granularity"] == "region"
    page = bakeoff.use_this(recipe, table, card, scope="project", folder_id=None, now="2026-10-16",
                            granularity="page")
    assert page["overrides"][0]["granularity"] == "page"


def test_the_cost_of_the_extra_runs_is_shown_before_anything_runs(db, monkeypatch):
    def cand(card, cost, granularities):
        return {"card": card, "name": card, "role": "contender", "runs_on": "cloud", "local": False,
                "not_scored": None, "run_cost_usd": {"value": cost}, "granularities": granularities}

    chosen = [cand("a", 1.0, ["lines", "region", "page"]), cand("b", 0.5, ["lines", "region", "page"]),
              cand("c", 0.25, ["lines", "region", "page"]), cand("kraken", 0.0, [])]
    chosen[3].update(local=True, runs_on="this-mac")
    monkeypatch.setattr(bakeoff, "candidates", lambda *a, **k: chosen)
    monkeypatch.setattr(bakeoff, "ground_truth", lambda *a, **k: ([{"document_id": "p"}] * 2, []))
    out = bakeoff.next_run(db, None, [], volume=10)
    # The two dearest, each asked at its two other granularities: 2 x 1.00 + 2 x 0.50.
    assert out["granularity_run_cost_usd"] == pytest.approx(3.0)
    assert "$3.00" in out["sentence"] and "two best" in out["sentence"]

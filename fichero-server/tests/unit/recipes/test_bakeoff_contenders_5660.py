"""The bake-off tries every kind of reader, scores words too, and compares the line finders (#5660 item 7).

WHY: "Are these the best models for this script?" The maintainer's Set Up offered the rules' top three Kraken
readers and nothing else, so the table could not say whether Apple Vision, an MLX vision model or Claude would read
these pages better, and nothing compared the line finders at all. The bake-off now tries one of each kind beside the
rules' three (Kraken, Apple Vision, an MLX vision model, a cloud reader where a provider is set up and the project lets
pages leave), scores each by CER and WER against the person's checked lines, with cost and time; a kind that cannot
read here is listed with why, never faked. The same comparison for the step that finds lines scores each line finder
by how many checked lines it finds.

Through the routes Set Up calls; Kraken, Apple Vision and the line finders are faked at their seams.
"""

from __future__ import annotations

import pytest

from fichero_server.recipes import bakeoff
from fichero_server.recipes.assemble import Answers
from fichero_server.recipes.cards import all_seed_cards
from fichero_server.training import evaluation
from tests.unit.recipes.test_bakeoff_readers import (  # noqa: F401  (fixtures)
    MCCATMUS,
    MEDIEVAL,
    PPOCR,
    _corrected,
    _run,
    _set_up,
    folder,
    homes,
    readers,
)

APPLE = "apple:vision/recognize-text@os"
SEVEN = "mlx:hf/mlx-community/Qwen2.5-VL-7B-Instruct-4bit@unpinned"
CLAUDE_HERE = "anthropic:claude-sonnet-4-5@"


def _named(cloud_allowed=False):
    a = Answers(purposes=("transcribe",), languages=frozenset({"es"}), scripts=frozenset({"Latn"}),
                materials=("handwriting",), mac_memory_gb=16, cloud_allowed=cloud_allowed)
    return {c["card"]: c for c in bakeoff.candidates(a, list(all_seed_cards()), volume=100)}


@pytest.fixture
def apple_here(monkeypatch):
    monkeypatch.setattr(evaluation, "apple_vision_here", lambda: True)


@pytest.fixture
def claude_row(app_db):
    from fichero_server.models import Model, Provider, ProviderType

    row = app_db.save_provider(Provider(name="Anthropic", provider_type=ProviderType("anthropic")))
    app_db.save_model(Model(provider_id=row.id, name="Claude Sonnet", model_id="claude-sonnet-4-5"))
    return row


def test_each_kind_takes_part_two_at_most_and_no_fixed_ranking(app_db, apple_here):
    """Ruled 2026-10-11: the bake-off decides, not the rules' top three; at most two of each kind take part."""
    named = _named()
    assert all(c["role"] == "contender" and c["rule_rank"] is None for c in named.values())
    assert [c for c in named if c.startswith("kraken:")] == [PPOCR, MEDIEVAL]  # not McCATMuS: two of a kind
    contenders = named
    assert {APPLE, SEVEN, "anthropic:claude@settings"} <= set(contenders)
    assert len([c for c in named if c.startswith("mlx:")]) <= 2
    assert contenders[APPLE]["not_scored"] is None  # Apple Vision reads here
    assert contenders[APPLE]["provider"] == "apple" and contenders[APPLE]["model"] == "apple-vision"
    assert contenders[SEVEN]["not_scored"] == "not on this Mac: download it to score it"
    assert contenders["anthropic:claude@settings"]["not_scored"] == (
        "not available yet: add Claude (Anthropic) in Settings › AI")


def test_without_apple_vision_it_is_listed_with_why(app_db, monkeypatch):
    monkeypatch.setattr(evaluation, "apple_vision_here", lambda: False)
    assert _named()[APPLE]["not_scored"] == "Apple Vision's text recognition is not available on this Mac"


def test_claude_reads_only_where_pages_may_leave(app_db, apple_here, claude_row):
    kept_here = next(c for card, c in _named().items() if card.startswith(CLAUDE_HERE))
    assert kept_here["not_scored"] == "this project keeps its pages on this Mac: priced, not scored"
    allowed = next(c for card, c in _named(cloud_allowed=True).items() if card.startswith(CLAUDE_HERE))
    assert allowed["not_scored"] is None and allowed["provider"] == "anthropic" and not allowed["local"]
    # The evaluation reads with it only when the request lets the lines leave this Mac.
    from fichero_server.models.compute_requests import EvaluationCandidate, EvaluationRunRequest

    cand = EvaluationCandidate(model="claude-sonnet-4-5", reader="vision", provider="anthropic")
    with pytest.raises(evaluation.EvaluationRefused, match="off this Mac"):
        evaluation.plan(None, EvaluationRunRequest(candidates=[cand], add_out_of_the_box=False))


def test_apple_vision_reads_the_same_pages_scored_by_cer_and_wer(client, db, tmp_path, folder, readers, apple_here,
                                                                  monkeypatch, with_material):
    """Apple Vision's recognised text is the reading (not a JSON array); every reader gets a WER beside its CER."""
    _set_up(client)
    pages = [_corrected(db, tmp_path, f"SM_NPQ_C01_00{i}", folder) for i in (1, 2, 3)]
    lines = [ln["text"] for p in pages for ln in evaluation.reference_page(db, p.id, None)[0]["lines"]]
    asked = []

    async def recognise(candidate, image, prompt):
        asked.append(candidate.provider)
        text = lines[len(asked) - 1]
        return text.rsplit(" ", 1)[0] if " " in text else text  # its last word missed

    monkeypatch.setattr(evaluation, "ask_vision", recognise)
    # The fixture's photographs are small stand-ins for the PAGE file's pixels: each line's picture is not cut.
    monkeypatch.setattr("fichero_server.llm.line_reader._crop_data_uri", lambda page, polygon: "data:image/jpeg;base64,")
    started, done = _run(client, db)
    rows = {r["card"]: r for r in done["rows"]}
    assert set(asked) == {"apple"} and len(asked) == len(lines)
    apple = rows[APPLE]
    assert apple["measured"] and apple["cer"] > 0 and apple["wer"] > 0 and apple["role"] == "contender"
    assert rows[PPOCR]["wer"] == 0.0 and rows[MEDIEVAL]["wer"] > 0  # a dropped character is a wrong word
    assert rows[SEVEN]["why"] == "not on this Mac: download it to score it" and rows[SEVEN]["cer"] is None
    assert all(r["seconds"] is not None for r in rows.values() if r["measured"])
    # The winner can be used for the step, as any bake-off choice.
    used = client.post(f"/api/recipes/project/bakeoffs/{started['id']}/use", json={"card": APPLE})
    assert used.status_code == 200, used.text


# --- the line finders --------------------------------------------------------------------------------------------


def test_the_line_finders_are_scored_by_the_checked_lines_they_find(client, db, tmp_path, folder, apple_here,
                                                                     monkeypatch, with_material):
    from fichero_server.execution import jobs

    monkeypatch.setattr("fichero_server.llm.kraken_runtime.is_installed", lambda: True)
    _set_up(client)
    for i in (1, 2, 3):
        _corrected(db, tmp_path, f"SM_NPQ_C01_00{i}", folder)

    def find(finder, photo):
        page = next(p for p in (evaluation.reference_page(db, d.id, None)[0]
                                for d in bakeoff_pages) if p["photo"] == photo)
        boxes = bakeoff._checked_boxes(page)
        return boxes if finder == "kraken-blla" else boxes[::2] + [[0.0, 0.0, 1.0, 0.01]]

    from fichero_server.models import Document

    bakeoff_pages = [d for d in db.query(Document, parent_id=folder.id)]
    monkeypatch.setattr(bakeoff, "find_lines_with", find)
    r = client.post("/api/recipes/project/bakeoffs", json={"step": "find-lines"})
    assert r.status_code == 200, r.text
    started = r.json()
    assert started["step"] == "find-lines"
    kind, subject = db.execute_fetchone("SELECT kind, subject FROM jobs WHERE id = ?", [started["job_id"]])
    assert kind == bakeoff.LINE_KIND
    jobs._current.job_id = started["job_id"]
    try:
        jobs.KINDS[kind].run(db, subject)
    finally:
        jobs._current.job_id = None
    done = client.get(f"/api/recipes/project/bakeoffs/{started['id']}").json()
    rows = {r["model"]: r for r in done["rows"]}
    checked = rows["kraken-blla"]["lines_checked"]
    assert checked and rows["kraken-blla"]["lines_found"] == checked and rows["kraken-blla"]["extra_lines"] == 0
    assert rows["apple-vision"]["lines_found"] < checked and rows["apple-vision"]["extra_lines"] == 3
    assert rows["yolo"]["why"] == "not available yet: it finds regions, not lines" and not rows["yolo"]["measured"]
    assert done["winner"] == "kraken:builtin/blla@bundled" and done["rows"][0]["model"] == "kraken-blla"
    use = f"/api/recipes/project/bakeoffs/{started['id']}/use"
    # Apple Vision's lines are a finder the planner can run (#5451); a YOLO layout model is not a line finder.
    assert client.post(use, json={"card": "apple:vision/find-lines@os"}).status_code == 200
    refused = client.post(use, json={"card": "yolo:hf/hantian/yolo-doclaynet@main"})
    assert refused.status_code == 422, refused.text
    assert client.post(use, json={"card": "kraken:builtin/blla@bundled"}).status_code == 200


def test_score_lines_counts_found_checked_and_extra():
    checked = [[0.1, 0.10, 0.8, 0.03], [0.1, 0.20, 0.8, 0.03]]
    found = [[0.09, 0.095, 0.82, 0.04], [0.0, 0.5, 1.0, 0.4]]  # the first line, and a box round a whole block
    assert bakeoff.score_lines(found, checked) == {"found": 1, "checked": 2, "extra": 1}

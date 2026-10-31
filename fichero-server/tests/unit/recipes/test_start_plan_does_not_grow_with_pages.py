"""Start's plan looked at each page with several queries, twice (the estimate, then the notes), so it took seconds on a
real project and Start waited for it (owner, 2026-10-25). It reads once for all the pages, and once a plan."""
from __future__ import annotations

import pytest

from fichero_server.db import Database
from fichero_server.recipes import done
from tests.unit.recipes.test_bakeoff_readers import _set_up, folder  # noqa: F401
from tests.unit.recipes.test_unread_lines_not_read_5758 import _page

CARDS = [{"job": "find-lines"}, {"job": "read-a-line", "model_override": None}, {"job": "leave-out"}]
#: Every other step `done.KNOWS_DONE` knows: the ones a plan reaches only when the recipe has them (review H3).
OPTION_CARDS = [{"job": "find-regions", "model": "m"}, {"job": "find-regions", "model": "m", "provider": "kraken"},
                {"job": "read-a-page", "model_override": "m"}, {"job": "correct", "model_override": "m", "steps": ["correct"]},
                {"job": "correct", "steps": ["correct-2"]}, {"job": "prepare-the-image"}, {"job": "split-pages"},
                {"job": "split-into-entries"}, {"job": "find-names-tag-words", "model_override": "m"},
                {"job": "translate-transliterate-normalise", "model_override": "m",
                 "tool_config": {"analyze": {"reading_kind": "translation"}}}]


def _shapes(db, n):
    """Pages with the shapes each step's "done" looks at: done and not done of everything."""
    from fichero_server.models import Artifact, DocType, Document

    pages = [_page(db, *shape) for shape in ([(3, 3), (10, 3), (4, 0), (0, 0)] * n)[:n]]
    for i, page in enumerate(pages):
        if i % 2:
            for kind in ("regions", "transcription", done.REVIEWED, "translation"):
                db.save(Artifact(document_id=page, artifact_type=kind, model="m" if i % 4 == 1 else "other"))
            db.save(Document(name="c", doc_type=DocType.chunk, parent_id=page, node_kind="entry" if i % 4 == 1 else None))
    return pages


@pytest.mark.parametrize("card", OPTION_CARDS, ids=lambda c: f"{c['job']}-{c.get('provider') or (c.get('steps') or [''])[0]}")
def test_a_step_a_plan_reaches_only_by_option_reads_once_and_agrees_with_asking_each_page(db, monkeypatch, card):
    pages = _shapes(db, 40)
    expected = [p for p in pages if not done.is_done(db, card, p)]
    seen = _statements(monkeypatch)
    done._split_done(db, card, pages[:4])
    few = len(seen)
    seen.clear()
    todo, finished = done._split_done(db, card, pages)
    assert len(seen) == few, f"{len(seen)} statements for 40 pages, {few} for 4"
    assert todo == expected and finished == len(pages) - len(expected)


def test_a_page_judged_on_its_only_pass_needs_no_ranking(db, monkeypatch):
    from fichero_server.models.segments import SegmentPass

    pages = _shapes(db, 8)
    with_lines = pages[:3]
    keys = {done.judged_key(db, p) for p in with_lines}
    monkeypatch.setattr(done, "pages_a_run_did", lambda *a, **k: keys)
    expected = [p for p in pages if not done.is_done(db, {"job": "leave-out"}, p)]
    monkeypatch.setattr(done, "judged_key", lambda *a: pytest.fail("a page's lines read for one key"))
    todo, _ = done._split_done(db, {"job": "leave-out"}, pages)
    assert todo == expected and SegmentPass


def test_a_certainty_bar_prices_from_named_columns_and_agrees_with_the_rule(db, monkeypatch):
    """Review H3: every line read whole, one reading rule at a time: over a million lines, unfinished at 32 minutes."""
    from fichero_server.api.routes.document.segment_readings import counting_readings
    from fichero_server.models import ContentRepresentation, Segment
    from fichero_server.models.anchors import SourceAnchor

    pages = _shapes(db, 8)
    lines = [s for s in db.query(Segment) if s.kind == "line"]
    for i, r in enumerate(db.query(ContentRepresentation)):
        r.machine_confidence = i / 100
        db.save(r)
    anchor = SourceAnchor(document_id=pages[1], rect=[0.1, 0.1, 0.2, 0.2])
    read = [s for s in lines if counting_readings(db, [s])]
    db.save(ContentRepresentation(document_id=read[0].document_id, segment_id=read[0].id, kind="transcription", content="b",
                                  source_anchor=anchor, machine_confidence=0.5))  # two readings: the rule decides
    counted = counting_readings(db, lines)
    known = done.kraken_lines_known(db, pages)
    assert (known["lines"], known["segmented"]) == (len(lines), len({s.document_id for s in lines}))
    expected = [counted[s.id].machine_confidence if s.id in counted else None for s in lines]
    assert sorted(known["sures"], key=str) == sorted(expected, key=str)
    calls = []
    real = db.query
    monkeypatch.setattr(db, "query", lambda m, **k: calls.append(m.__name__) or real(m, **k))
    done.kraken_lines_known(db, pages[2:3])
    assert "Segment" not in calls


def _statements(monkeypatch) -> list[str]:
    seen: list[str] = []
    real = Database._execute_fetch_with_columns

    def spy(self, sql, *a, **k):
        seen.append(sql)
        return real(self, sql, *a, **k)

    monkeypatch.setattr(Database, "_execute_fetch_with_columns", spy)
    return seen


@pytest.mark.parametrize("card", CARDS, ids=lambda c: c["job"])
def test_a_step_asks_the_database_the_same_number_of_times_for_ten_pages_or_forty(db, monkeypatch, card):
    # mixed pages: lines all read, some read, none read, no lines at all
    pages = [_page(db, *shape) for shape in [(3, 3), (10, 3), (4, 0), (0, 0)] * 10]
    seen = _statements(monkeypatch)
    done.split_done(db, card, pages[:4])
    few = len(seen)
    seen.clear()
    done.split_done(db, card, pages)
    assert len(seen) == few, f"{len(seen)} statements for 40 pages, {few} for 4"


@pytest.mark.parametrize("card", CARDS[:2], ids=lambda c: c["job"])
def test_the_one_read_agrees_with_asking_each_page(db, card):
    pages = [_page(db, *shape) for shape in [(3, 3), (10, 3), (4, 0), (0, 0)] * 2]
    todo, finished = done.split_done(db, card, pages)
    assert todo == [p for p in pages if not done.is_done(db, card, p)]
    assert finished == len(pages) - len(todo) == {"find-lines": 6, "read-a-line": 2}[card["job"]]


def test_the_plan_works_out_what_each_step_has_done_once(client, db, folder, with_material, monkeypatch):  # noqa: F811
    from fichero_server.api.routes.system import recipes as routes

    _set_up(client)
    asked: list[str] = []
    real = done._split_done
    monkeypatch.setattr(done, "_split_done", lambda db_, card, pages, own=None: asked.append(card["job"]) or real(db_, card, pages, own))
    routes._start_plan(db, None, clusters=[])
    assert asked and len(asked) == len(set(asked)), f"asked twice: {asked}"


def test_the_cards_a_translate_step_makes_for_two_levels_are_counted_apart(monkeypatch):
    """Cards as the plan builds them (they carry no id): one step asked for two levels is two cards that differ only in
    their tool_config."""
    from fichero_server.recipes.start import plan_start
    from tests.unit.recipes.test_find_where_readers_disagree_step_5665 import _recipe
    from tests.unit.recipes.test_installed_model_first_to_spec import SEVEN

    step = {"id": "norm", "job": "translate-transliterate-normalise", "model": SEVEN, "runs_on": "this-mac"}
    plan = plan_start(_recipe(step), stays_local=True, job_answers={"normalise_how_far": ["as_written", "expanded"]})
    cards = [r for r in plan["runs"] if r["job"] == "translate-transliterate-normalise"]
    assert len(cards) == 2 and "id" not in cards[0], plan["skipped"]
    calls: list[dict] = []
    monkeypatch.setattr(done, "_split_done", lambda db_, card, pages, own=None: calls.append(card) or ([], len(calls)))
    memo: dict = {}
    first, second = (done.split_done(None, c, ["p"], memo=memo) for c in cards)
    assert first != second and len(calls) == 2
    assert done.split_done(None, cards[0], ["p"], memo=memo) == first and len(calls) == 2


def test_who_called_pages_blank_is_one_read_and_agrees_with_asking_each_page(db, monkeypatch):
    """The plan asked page by page, a whole row each: minutes on 70k pages (review sweep 2026-10-31)."""
    from fichero_server.models import Document
    from fichero_server.recipes import sorting

    pages = [_page(db, 0, 0) for _ in range(3)]
    for page, by in zip(pages[:2], (sorting.BY_PERSON, "a-run")):
        doc = db.get(Document, page)
        doc.attributes = {sorting.KIND: sorting.BLANK, sorting.SET_BY: by}
        db.save(doc)
    expected = {p: who for p in pages if (who := done._blank_by(db, p))}
    assert set(expected) == set(pages[:2])
    seen = _statements(monkeypatch)
    assert done.blank_by(db, pages) == expected and len(seen) == 1


def test_a_plan_s_notes_do_not_ask_page_by_page_who_called_it_blank(db, monkeypatch):
    pages = [_page(db, 0, 0) for _ in range(2)]
    monkeypatch.setattr(done, "_blank_by", lambda *a: pytest.fail("a read a page"))
    plan = {"runs": [{"job": "find-lines", "card": "workflow", "steps": ["find-lines"]}]}
    assert done.annotate(db, plan)["runs"][0]["of"] == len(pages)


def _cut_page(db, parent, **extra):
    from fichero_server.models import DocType, Document

    doc = Document(name="c", doc_type=DocType.chunk, parent_id=parent, metadata={"split_source_id": parent, "lines": [1], **extra})
    db.save(doc)
    return doc


def test_a_folder_s_cut_pages_are_read_from_the_folder_not_the_library(db, monkeypatch):
    """Review H1: rows read, not time."""
    mine, others = [_cut_page(db, "here") for _ in range(2)], [_cut_page(db, "there") for _ in range(30)]
    rows: list[int] = []
    real = Database._execute_fetch_with_columns
    monkeypatch.setattr(Database, "_execute_fetch_with_columns",
                        lambda self, sql, *a, **k: (out := real(self, sql, *a, **k), rows.append(len(out[0] or [])))[0])
    assert {d.id for d in done.split_pages(db, {d.id for d in mine})} == {d.id for d in mine}
    assert sum(rows) == len(mine), others[0].id


def test_the_library_s_cut_pages_agree_with_asking_each_page(db):
    from fichero_server.models import DocType, Document

    kept = _cut_page(db, "a")
    hidden = _cut_page(db, "a", blank={"blank": True})
    hidden.exclude_from_processing = True
    db.save(hidden)
    excluded_only = _cut_page(db, "a")
    excluded_only.exclude_from_processing = True
    db.save(excluded_only)
    gone = _cut_page(db, "a")
    gone.deleted_at = gone.created_at
    db.save(gone)
    db.save(Document(name="no-source", doc_type=DocType.chunk, metadata={}))
    expected = {kept.id, excluded_only.id}
    assert {d.id for d in done.split_pages(db, None)} == expected
    assert {d.id for d in done.split_pages(db, None)} == {d.id for d in db.query(Document, doc_type=DocType.chunk) if not d.deleted_at and done._is_split_page(d)}


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
    monkeypatch.setattr(done, "_split_done", lambda db_, card, pages, own=None: calls.append(card) or ((["p"], 0) if len(calls) == 1 else ([], 1)))
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


def test_one_press_of_start_reads_the_library_once_and_outside_the_transaction(client, db, folder, with_material, monkeypatch):  # noqa: F811
    """Review H2: POST built the plan three times, the middle one under the writer gate: writers waited for the whole plan."""
    _set_up(client)
    asked: list[bool] = []
    real_ids = Database.unit_of_work_ids
    monkeypatch.setattr(Database, "unit_of_work_ids", lambda self: asked.append(self.in_transaction) or real_ids(self))
    done_in: list[tuple[str, bool]] = []
    real = done._split_done
    monkeypatch.setattr(done, "_split_done", lambda db_, card, pages, own=None: done_in.append((card["job"], db_.in_transaction)) or real(db_, card, pages, own))
    answer = client.post("/api/recipes/project/start", json={})
    assert answer.status_code == 200, answer.text
    assert asked[0] is False and True not in asked, "the order of the pages is worked out before the transaction, not in it"
    assert done_in and not any(held for _, held in done_in), done_in


def test_the_spending_check_is_asked_again_inside_the_transaction(client, db, folder, with_material, monkeypatch):  # noqa: F811
    """The plan's reads are kept; the cap is not. Money booked while the plan was read refuses the Start, as it did when the
    whole plan ran under the gate."""
    from fichero_server.api.routes.system import recipes as routes
    from fichero_server.llm import spend as cloud_spend

    _set_up(client)
    held: list[bool] = []
    real = cloud_spend.plan_line

    def line(library, **kw):
        held.append(db.in_transaction)
        out = real(library, **kw)
        return {**out, "over": True, "over_month": True, "estimate_usd": 9.0, "remaining_usd": 1.0, "cap_usd": 1.0, "needed_cap_usd": 9.0,
                "over_project": False} if db.in_transaction else out

    monkeypatch.setattr(cloud_spend, "plan_line", line)
    monkeypatch.setattr(routes, "first_pages_that_fit", lambda *a, **k: None)
    answer = client.post("/api/recipes/project/start", json={})
    assert answer.status_code == 422 and "monthly cap" in answer.text, answer.text
    assert True in held and False in held


def test_two_callers_of_the_plan_share_one_plan(db, monkeypatch):
    import asyncio

    from fichero_server.api.routes.system import recipes as routes

    built = []

    def plan(*a, **k):
        built.append(1)
        import time

        time.sleep(0.2)
        return {"refusals": []}

    monkeypatch.setattr(routes, "_start_plan", plan)

    async def both():
        return await asyncio.gather(*[routes._plan_once(db=db, folder_id=None, clusters=(), first_pages=None) for _ in range(2)])

    asyncio.run(both())
    assert len(built) == 1


def test_a_second_plan_on_the_same_reads_asks_nothing_of_the_pages(client, db, folder, with_material, monkeypatch):  # noqa: F811
    from fichero_server.api.routes.system import recipes as routes

    _set_up(client)
    memo: dict = {}
    first = routes._start_plan(db, None, clusters=[], memo=memo)
    seen = _statements(monkeypatch)
    again = routes._start_plan(db, None, clusters=[], memo=memo)
    assert again["estimate"] == first["estimate"] and again["runs"] == first["runs"]
    heavy = [s for s in seen if any(t in s for t in ('"segments"', '"contentrepresentations"', "page_content", "ocr_geometry"))]
    assert not heavy, heavy



def test_a_certainty_bar_is_read_once_per_press_and_outside_the_transaction(client, db, folder, with_material, monkeypatch):  # noqa: F811
    """Review M1: with a bar each plan read every line again, under the writer gate too: about 27 s of writers waiting on 1M lines."""
    from fichero_server.recipes import start

    _set_up(client)
    real_plan = start.plan_start
    bar = {"workflow": "w", "workflow_id": "w", "job": "correct", "steps": ["correct"], "runs_on": "this-mac", "tool_config": {"transcribe_review": {"only_below_confidence": 0.6}}}

    def with_a_bar(*args, **kwargs):
        plan = real_plan(*args, **kwargs)
        return {**plan, "workflows": [*plan["workflows"], bar]}

    monkeypatch.setattr(start, "plan_start", with_a_bar)
    held: list[bool] = []
    real = done._stated_certainties
    monkeypatch.setattr(done, "_stated_certainties", lambda db_, rows: held.append(db_.in_transaction) or real(db_, rows))
    answer = client.post("/api/recipes/project/start", json={})
    assert answer.status_code == 200, answer.text
    assert held and True not in held, held


def test_lines_known_on_the_same_reads_answers_any_pages_without_asking_again(db, monkeypatch):
    """"Run fewer pages" prices many first-page counts: the lines are read once, and each answer matches a fresh read."""
    pages = [_page(db, *shape) for shape in ((3, 3), (0, 0), (4, 2))]
    expected = {tuple(ids): done.kraken_lines_known(db, list(ids)) for ids in (pages, pages[:1])}
    memo: dict = {}
    first = done.kraken_lines_known(db, pages, memo)
    monkeypatch.setattr(done, "_stated_certainties", lambda *a: pytest.fail("read the lines again"))
    for ids, want in expected.items():
        got = done.kraken_lines_known(db, list(ids), memo)
        assert {**got, "sures": sorted(got["sures"], key=str)} == {**want, "sures": sorted(want["sures"], key=str)}
    assert first["lines"] == expected[tuple(pages)]["lines"]


def test_a_reload_after_a_save_does_not_join_the_plan_from_before_it(db, tmp_path, monkeypatch):
    """Review M2: the Start sheet could show the old cap until the next load."""
    import asyncio
    import time
    from types import SimpleNamespace

    from fichero_server.api.routes.system import recipes as routes
    from fichero_server.recipes import project

    project.write_project_setup(tmp_path, {"cloud_spend_cap_usd": 1}, None)

    def plan(*a, **k):
        cap = project.read_saved_answers(tmp_path)["cloud_spend_cap_usd"]
        time.sleep(0.3)
        return {"cap_seen": cap}

    monkeypatch.setattr(routes, "_library", lambda db_: tmp_path)
    monkeypatch.setattr(routes, "_cluster_names", lambda http: [])
    monkeypatch.setattr(routes, "_start_plan", plan)
    monkeypatch.setattr(routes, "StartPlan", lambda **kw: kw)

    def reload():
        return routes.get_start_plan(http=SimpleNamespace(), folder_id=None, summary=False, first_pages=None, steps=None, db=db)

    async def in_flight_then_saved():
        first = asyncio.ensure_future(reload())
        await asyncio.sleep(0.1)
        project.write_project_setup(tmp_path, {"cloud_spend_cap_usd": 99}, None)
        return await asyncio.gather(first, reload())

    before, after = asyncio.run(in_flight_then_saved())
    assert (before["cap_seen"], after["cap_seen"]) == (1, 99)


def test_a_partial_attribution_step_answers_as_the_model_did(db, monkeypatch):
    """A stored step missing `label` or `document_id` took the model's defaults; it must not stop the plan."""
    from types import SimpleNamespace

    entities = [SimpleNamespace(source_document_ids=["named"], attribution_chain=[{"role": "extractor"}]),
                SimpleNamespace(source_document_ids=["by-a-person"], attribution_chain=[{"role": "editor"}])]
    monkeypatch.setattr(db, "query_fields", lambda *a, **k: entities)
    assert done.pages_with_names(db, "some-model") == {"by-a-person"}


def test_only_a_true_blank_mark_hides_a_cut_page(db):
    """As the rule per page has it (`done.split_pages`): a mark of the word "true" isn't a mark."""
    marked = _cut_page(db, "here", blank={"blank": True})
    word = _cut_page(db, "here", blank={"blank": "true"})
    for page in (marked, word):
        page.exclude_from_processing = True
        db.save(page)
    assert [row[0] for row in db.cut_pages_of([marked.id, word.id])] == [word.id]


def test_a_page_arriving_while_the_first_plan_runs_is_left_out_of_that_press_s_count_only(client, db, folder, with_material, monkeypatch):  # noqa: F811
    """The window: from the first plan's read of the pages until the run is queued, which is that plan plus any wait for the
    writer gate. The run's count may be that old; a fresh read of the pages is not."""
    from fichero_server.api.routes.system import recipes as routes
    from fichero_server.execution import jobs
    from fichero_server.recipes import runner

    _set_up(client)
    pages_before = len(done.pages_for(db, {}, None))
    real = routes._accept_asked

    def a_page_arrives_after(*args, **kwargs):
        out = real(*args, **kwargs)
        db.save(with_material.model_copy(update={"id": "arrived-in-the-window", "name": "arrived.png"}))
        return out

    monkeypatch.setattr(routes, "_accept_asked", a_page_arrives_after)
    answer = client.post("/api/recipes/project/start", json={})
    assert answer.status_code == 200, answer.text
    [run] = jobs.find_jobs(db, kinds=[runner.KIND])
    assert runner.name_and_pages(db, run["id"])[1] == pages_before
    assert "arrived-in-the-window" in done.pages_for(db, {}, None)

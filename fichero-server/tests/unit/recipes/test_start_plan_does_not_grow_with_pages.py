"""Start's plan looked at each page with several queries, twice (the estimate, then the notes), so it took seconds on a
real project and Start waited for it (owner, 2026-10-25). It reads once for all the pages, and once a plan."""
from __future__ import annotations

import pytest

from fichero_server.db import Database
from fichero_server.recipes import done
from tests.unit.recipes.test_bakeoff_readers import _set_up, folder  # noqa: F401
from tests.unit.recipes.test_unread_lines_not_read_5758 import _page

CARDS = [{"job": "find-lines"}, {"job": "read-a-line", "model_override": None}, {"job": "leave-out"}]


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

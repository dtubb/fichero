"""A local reader (Kraken) and a hosted one use different resources, so Read runs them side by side instead of one after the
other (owner, 2026-10-25, #6127: Kraken took 16 minutes for 20 pages, then the cloud reader started)."""
from __future__ import annotations

import threading

import pytest

from fichero_server.execution import jobs
from fichero_server.recipes import runner

KRAKEN = {"card": "workflow", "job": "read-a-line", "steps": ["a"], "runs_on": "this-mac", "takes": ["lines"],
          "gives": ["line_readings"]}
CLOUD = {"card": "workflow", "job": "read-a-page", "steps": ["b"], "runs_on": "cloud:openrouter", "takes": ["page_image"],
         "gives": ["page_reading"]}


def _run(monkeypatch, cards, work, pages=None, redo=(), detail=None, stopped=lambda: False, keep=(), db=None):
    """`_run_batch` over `cards`, each step's work being `work(card)`; the states it ends with. `pages(card)` is the pages a
    step finds to do each time it asks (a step's pages are worked out again as it is about to run)."""
    asked: dict[str, int] = {}

    def pages_now(db, card, *a, **k):
        asked[card["job"]] = asked.get(card["job"], 0) + 1
        return ((pages or (lambda c, n: ["p1"]))(card, asked[card["job"]]), {}, {})

    for name, value in {"_step_pages": pages_now, "_blocked": lambda *a: None,
                        "_await_downloads": lambda *a: None, "_stop_asked": lambda *a: stopped(),
                        "_wait_out_a_pause": lambda *a: None, "_after_the_step": lambda *a, **k: None, "_recount_on_the_folder": lambda *a: None,
                        "_let_go_after_the_last_served_step": lambda *a: None,
                        "_run_card": lambda db, card, *a, **k: (card["steps"][0], *work(card))}.items():
        if name not in keep:
            monkeypatch.setattr(runner, name, value)
    monkeypatch.setattr(jobs, "save_detail", lambda *a, **k: None)
    detail = detail if detail is not None else {"runs": cards, "steps": [{"state": "waiting"} for _ in cards], "batch_states": [None] * len(cards),
              "redo": list(redo)}
    runner._run_batch(db, "job", detail, {"units": ["p1"], "folder": "f"}, {}, "test", final=True)
    return [step["state"] for step in detail["steps"]]


def _fresh(cards):
    return {"runs": cards, "steps": [{"state": "waiting"} for _ in cards], "batch_states": [None] * len(cards), "redo": []}


def test_a_local_reader_and_a_hosted_one_run_at_the_same_time(monkeypatch):
    meet = threading.Barrier(2, timeout=10)  # each waits for the other: broken (so failed) if they run one after the other

    def work(card):
        meet.wait()
        return "done", None

    assert _run(monkeypatch, [KRAKEN, CLOUD], work) == ["done", "done"]


@pytest.mark.parametrize("other", [{**CLOUD, "runs_on": "this-mac"}, {**CLOUD, "job": "read-a-line"},
                                   {**CLOUD, "takes": ["line_readings"]}], ids=["both local", "same job", "takes the other's"])
def test_two_steps_that_share_a_resource_or_an_input_run_one_after_the_other(monkeypatch, other):
    now, most = [0], [0]
    lock = threading.Lock()

    def work(card):
        with lock:
            now[0] += 1
            most[0] = max(most[0], now[0])
        threading.Event().wait(0.2)
        with lock:
            now[0] -= 1
        return "done", None

    assert _run(monkeypatch, [KRAKEN, other], work) == ["done", "done"]
    assert most[0] == 1


def test_a_step_that_ran_beside_the_one_before_keeps_its_own_end_and_is_not_run_again(monkeypatch):
    """review 1185 items 2: the pages of the step beside were worked out again as its turn came, so a step that had read
    them all was recorded done whatever it ended with, and one that had not was run a second time."""
    ran: list[str] = []

    def work(card):
        ran.append(card["job"])
        return ("failed", "the cloud said no") if card["job"] == "read-a-page" else ("done", None)

    # Asked again, the cloud step finds nothing left to do (it read them all, and failed on one).
    assert _run(monkeypatch, [KRAKEN, CLOUD], work, pages=lambda c, n: ["p1"] if n == 1 else []) == ["done", "failed"]
    assert sorted(ran) == ["read-a-line", "read-a-page"]


def test_a_read_again_reaches_the_step_that_runs_beside(monkeypatch):
    """review 1185 item 3: Redo's read-all-lines was put on the step's card only when its turn came."""
    seen: dict[str, dict] = {}

    def work(card):
        seen[card["job"]] = card
        return "done", None

    assert _run(monkeypatch, [CLOUD, KRAKEN], work, redo=["a"]) == ["done", "done"]
    assert seen["read-a-line"]["tool_config"]["transcribe"]["read_all_lines"] is True


@pytest.mark.parametrize("order", [(KRAKEN, CLOUD), (CLOUD, KRAKEN)], ids=["local first", "hosted first"])
def test_the_page_text_is_the_hosted_readers_whichever_finishes_first(monkeypatch, order):
    """review 1185/1186: `source.recipe.kraken-lines-cloud-reads`: the page text is the model's, never Kraken's. Run beside a
    hosted reader the local one writes its lines' readings and leaves the page text alone."""
    seen: dict[str, dict] = {}
    meet = threading.Barrier(2, timeout=10)

    def work(card):
        seen[card["job"]] = card
        meet.wait()
        return "done", None

    assert _run(monkeypatch, list(order), work) == ["done", "done"]
    assert seen["read-a-line"]["tool_config"]["transcribe"] == {"update_page_content": False, "force_ocr": False}
    assert "tool_config" not in seen["read-a-page"]


def test_a_local_reader_that_runs_alone_still_writes_the_page_text(monkeypatch):
    seen: dict[str, dict] = {}

    def work(card):
        seen[card["job"]] = card
        return "done", None

    assert _run(monkeypatch, [KRAKEN], work) == ["done"]
    assert "tool_config" not in seen["read-a-line"]


def test_stop_reaches_a_local_and_a_hosted_read_running_together(monkeypatch):
    """Stop while both run: each ends stopped (the workflow's own stop check sees the recipe's Stop), neither is run again."""
    stop, both_running = threading.Event(), threading.Barrier(3, timeout=10)
    ran: list[str] = []

    def work(card):
        ran.append(card["job"])
        both_running.wait()  # the test and the two reads
        assert stop.wait(10)
        return "cancelled", "Stopped by you"

    box = {}
    thread = threading.Thread(target=lambda: box.update(states=_run(monkeypatch, [KRAKEN, CLOUD], work,
                                                                     stopped=stop.is_set)))
    thread.start()
    both_running.wait()
    stop.set()
    thread.join(20)
    assert box["states"] == ["cancelled", "cancelled"] and sorted(ran) == ["read-a-line", "read-a-page"]


def test_an_engine_lost_with_one_read_done_runs_only_the_other_on_resume(monkeypatch):
    """Engine death between the two ends: the step that ended is a checkpoint and is not read again on resume; the one that
    did not end runs once."""
    detail, ran = _fresh([KRAKEN, CLOUD]), []

    def dies(card):
        ran.append(card["job"])
        if card["job"] == "read-a-page":
            raise jobs.JobDeferred("engine lost")
        return "done", None

    with pytest.raises(jobs.JobDeferred):
        _run(monkeypatch, [KRAKEN, CLOUD], dies, detail=detail)
    assert detail["batch_states"] == ["done", None]
    ran.clear()
    assert _run(monkeypatch, [KRAKEN, CLOUD], lambda card: (ran.append(card["job"]), ("done", None))[1], detail=detail) == \
        ["done", "done"]
    assert ran == ["read-a-page"], "the read that had ended was read again"


def test_a_pause_during_the_pair_takes_both_ends_and_holds_the_step_after(db, monkeypatch):
    """review 1207: the pause wait ran before the beside step's end was taken, so JobDeferred dropped the running thread and
    Resume read its pages again. Both ends are taken; the Pause holds the step after the pair."""
    paused, ran = threading.Event(), []
    both_started = threading.Barrier(2, timeout=10)
    monkeypatch.setattr("fichero_server.execution.cancellation.pause_requested", lambda _id: paused.is_set())
    after = {"card": "embed", "job": "make-a-vector", "steps": ["c"], "runs_on": "this-mac", "takes": [], "gives": []}

    def work(card):
        ran.append(card["job"])
        if card["job"] != "make-a-vector":
            both_started.wait()
            paused.set()  # Pause is pressed with both running
        return "done", None

    detail = _fresh([KRAKEN, CLOUD, after])
    with pytest.raises(jobs.JobDeferred):
        _run(monkeypatch, [KRAKEN, CLOUD, after], work, detail=detail, keep=("_wait_out_a_pause",), db=db)
    assert detail["batch_states"] == ["done", "done", None] and sorted(ran) == ["read-a-line", "read-a-page"]


def test_a_page_the_hosted_reader_lost_is_listed_as_failed_beside_the_local_one(db, monkeypatch):
    """review 1207: the end of the step that ran beside goes through the same account as any step's: its lost page is named."""
    from fichero_server.workflows.run_account import PageFailure

    monkeypatch.setattr("fichero_server.kept_export.queue_rewrites", lambda *a, **k: None)
    monkeypatch.setattr("fichero_server.recipes.train_offers.start_when_ready", lambda *a, **k: None)
    monkeypatch.setattr(runner, "_did_no_page", lambda *a, **k: (False, 1, [PageFailure(page="IMG_002", reason="the cloud refused it")])
                        if a[1]["job"] == "read-a-page" else (False, 0, []))
    detail = _fresh([KRAKEN, CLOUD])
    assert _run(monkeypatch, [KRAKEN, CLOUD], lambda card: ("done", None), detail=detail, keep=("_after_the_step",),
                db=db) == ["done", "partial"]
    assert detail["steps"][1]["failed_pages"] == [{"page": "IMG_002", "reason": "the cloud refused it"}]


@pytest.mark.parametrize("order", [(KRAKEN, CLOUD), (CLOUD, KRAKEN)], ids=["local first", "hosted first"])
def test_a_hosted_read_that_fails_is_not_covered_by_krakens_text(monkeypatch, order):
    """Owner ruling 2026-10-25 (#6127): when the hosted reader fails on a page (after the one retry layer's backoff,
    `ai.where.one-retry-policy`), the page is failed, never given Kraken's text instead. Kraken's card is the same with the
    hosted step failed, and it is not run again to write the page."""
    ran: list[dict] = []

    def work(card):
        ran.append(card)
        return ("failed", "the cloud refused it") if card["job"] == "read-a-page" else ("done", None)

    assert sorted(_run(monkeypatch, list(order), work)) == ["done", "failed"]
    (kraken,) = [c for c in ran if c["job"] == "read-a-line"]
    assert kraken["tool_config"]["transcribe"] == {"update_page_content": False, "force_ocr": False}

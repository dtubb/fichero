"""#6295: a Start refused for a cloud spend cap names which cap and the amount it needs; both caps (the monthly one and the
project's total one) are changed in the app by one audited, undoable action; "run fewer pages" is the first N pages in
Finder order (`ai.where.cloud-spend-cap`, maintainer's ruling 2026-10-30: no margin, the best estimate)."""

from __future__ import annotations

import asyncio

import pytest

from fichero_server.llm import LLMConfig, spend, usage
from fichero_server.models import DocType, Document, FileType


def _library(db) -> str:
    from fichero_server.api.routes.system import recipes as routes

    return str(routes._library(db))


def _answers(client) -> dict:
    return client.get("/api/recipes/project").json().get("answers") or {}


def _project(tmp_path, **answers) -> str:
    folder = tmp_path / "P.fichero" / "recipe"
    folder.mkdir(parents=True)
    (folder / "setup.yaml").write_text(
        "".join(f"{k}: {v}\n" for k, v in answers.items()) or "cloud_allowed: true\n"
    )
    return str(tmp_path / "P.fichero")


# --- the plan line: which cap, how much -----------------------------------------------------------------------------


def test_the_plan_line_says_the_monthly_cap_the_estimate_needs(tmp_path):
    library = _project(tmp_path)
    over = spend.plan_line(library, estimate_usd=12.341, pages=100)
    assert over["over"] and over["over_month"] and not over["over_project"]
    assert (
        over["needed_cap_usd"] == 12.35
    )  # to the cent, rounded up so the estimate fits, no margin
    assert over["needed_project_cap_usd"] is None
    fits = spend.plan_line(library, estimate_usd=9.99, pages=100)
    assert (
        not fits["over"]
        and fits["needed_cap_usd"] is None
        and fits["fewer_pages"] is None
    )
    unknown = spend.plan_line(library, estimate_usd=None)
    assert (
        not unknown["over"] and unknown["needed_cap_usd"] is None
    )  # unknown is never a number


def test_the_needed_cap_counts_what_is_already_booked(tmp_path):
    library = _project(tmp_path)
    spend._book(library, 4.0)
    line = spend.plan_line(
        library, estimate_usd=7.0
    )  # cap 10, 4 spent: 6 left, 7 wanted
    assert line["over_month"] and line["needed_cap_usd"] == 11.0
    assert (
        spend.needed_cap_usd(0.1, 0.2) == 0.3
    )  # no float dust: 0.30000000000000004 stays 0.3


def test_the_project_cap_is_its_own_limit_and_names_its_own_amount(tmp_path):
    library = _project(tmp_path, cloud_spend_cap_usd=100, cloud_project_cap_usd=5)
    spend._book(library, 2.0)
    line = spend.plan_line(
        library, estimate_usd=4.0, pages=40
    )  # month has 98 left; the project's total has 3
    assert line["over"] and line["over_project"] and not line["over_month"]
    assert line["needed_cap_usd"] is None and line["needed_project_cap_usd"] == 6.0
    assert line["project_cap_usd"] == 5.0 and line["project_spent_usd"] == 2.0
    assert line["fewer_pages"] is None  # the caller finds it: it needs the plan's own pricing
    both = spend.plan_line(
        _project(tmp_path / "b", cloud_spend_cap_usd=1, cloud_project_cap_usd=2),
        estimate_usd=9.0,
    )
    assert both["over_month"] and both["over_project"]
    assert both["needed_cap_usd"] == 9.0 and both["needed_project_cap_usd"] == 9.0


def test_no_project_cap_is_no_limit_and_a_bad_one_is_none(tmp_path):
    assert spend.project_cap_usd(_project(tmp_path / "a")) is None
    for bad in ("-1", "'ten'", "true"):
        assert (
            spend.project_cap_usd(
                _project(tmp_path / bad.strip("'-"), cloud_project_cap_usd=bad)
            )
            is None
        )


def test_the_total_is_kept_across_months_and_an_old_ledger_counts_its_month(tmp_path):
    from datetime import datetime, timezone

    library = _project(tmp_path)
    spend._book(library, 1.5, datetime(2026, 9, 3, tzinfo=timezone.utc))
    spend._book(
        library, 2.0, datetime(2026, 10, 3, tzinfo=timezone.utc)
    )  # a new month: the month starts again, the total does not
    assert spend.total_booked_usd(library) == pytest.approx(3.5)
    assert spend.booked_usd(
        library, datetime(2026, 10, 4, tzinfo=timezone.utc)
    ) == pytest.approx(2.0)
    (tmp_path / "P.fichero" / "recipe" / spend.LEDGER).write_text(
        '{"month": "2026-09", "usd": 7.0}'
    )  # from before the total
    assert spend.total_booked_usd(library) == 7.0


# --- the send-time hold enforces the project cap too ----------------------------------------------------------------


def test_a_call_past_the_project_cap_is_refused_naming_that_cap(tmp_path, monkeypatch):
    monkeypatch.setattr(
        usage,
        "_registry_entry",
        lambda model, provider="": {
            "input_cost_per_token": 1e-6,
            "output_cost_per_token": 1e-5,
        },
    )
    spend._RESERVED.clear()
    library = _project(tmp_path, cloud_spend_cap_usd=100, cloud_project_cap_usd=1.0)
    spend._book(library, 0.99)
    config = LLMConfig(
        provider="openai", model="gpt-test", api_key="k", max_tokens=1000
    )  # worst case $0.04

    async def call():
        async with spend.holding(config, library):
            raise AssertionError("sent")

    with pytest.raises(spend.CloudSpendRefusedError) as refused:
        asyncio.run(call())
    words = str(refused.value)
    assert "$1.00 in all" in words and "not sent" in words and "Raise the cap" in words


# --- the refusal's words --------------------------------------------------------------------------------------------


def _line(**kw) -> dict:
    base = {
        "over": True,
        "over_month": False,
        "over_project": False,
        "estimate_usd": 14.0,
        "remaining_usd": 6.0,
        "cap_usd": 10.0,
        "needed_cap_usd": None,
        "project_cap_usd": None,
        "project_spent_usd": 0.0,
        "project_remaining_usd": None,
        "needed_project_cap_usd": None,
        "fewer_pages": None,
        "refusal": None,
    }
    return {**base, **kw}


def test_the_refusal_names_the_monthly_cap_and_the_amount():
    from fichero_server.recipes.cloud_cap import cap_refusals as _cap_refusals

    plan = {
        "refusals": [],
        "cloud_cap": _line(over_month=True, needed_cap_usd=18.0, fewer_pages=42),
    }
    _cap_refusals(plan)
    (said,) = plan["refusals"]
    assert (
        "US$14.00" in said
        and "US$6.00" in said
        and "Raise the monthly cap to US$18.00" in said
    )
    assert "first 42 pages" in said


def test_the_refusal_names_the_project_cap_and_both_when_both_are_over():
    from fichero_server.recipes.cloud_cap import cap_refusals as _cap_refusals

    plan = {
        "refusals": [],
        "cloud_cap": _line(
            over_project=True,
            project_cap_usd=5.0,
            project_spent_usd=2.0,
            project_remaining_usd=3.0,
            needed_project_cap_usd=16.0,
        ),
    }
    _cap_refusals(plan)
    assert (
        "Raise the project cap to US$16.00" in plan["refusals"][0]
        and "total cap leaves" in plan["refusals"][0]
    )
    both = {
        "refusals": [],
        "cloud_cap": _line(
            over_month=True,
            over_project=True,
            needed_cap_usd=18.0,
            project_cap_usd=5.0,
            project_spent_usd=2.0,
            project_remaining_usd=3.0,
            needed_project_cap_usd=16.0,
        ),
    }
    _cap_refusals(both)
    assert (
        "monthly cap to US$18.00" in both["refusals"][0]
        and "project cap to US$16.00" in both["refusals"][0]
    )
    quiet = {"refusals": [], "cloud_cap": _line(over=False)}
    _cap_refusals(quiet)
    assert quiet["refusals"] == []


def test_the_plan_line_carries_the_caps_own_refusal_so_a_client_never_reads_prose():
    """The app hid the cap's refusal from the list by matching the engine's sentence, and missed it when another refusal came
    first (the 422 then began with that one). The line carries the sentence it added, whatever else is in `refusals`."""
    from fichero_server.recipes.cloud_cap import cap_refusals as _cap_refusals

    plan = {
        "refusals": ["step 1 (find-lines): its model is not pinned in a known form"],
        "cloud_cap": _line(over_month=True, needed_cap_usd=18.0),
    }
    _cap_refusals(plan)
    assert plan["refusals"][0].startswith("step 1")
    assert plan["cloud_cap"]["refusal"] == plan["refusals"][1]
    assert "Raise the monthly cap to US$18.00" in plan["cloud_cap"]["refusal"]
    quiet = {"refusals": [], "cloud_cap": _line(over=False)}
    _cap_refusals(quiet)
    assert quiet["cloud_cap"]["refusal"] is None


def test_the_plan_line_says_what_the_project_cap_leaves(tmp_path):
    """The app worked `max(0, cap - spent)` out itself; the engine says it."""
    library = _project(tmp_path, cloud_spend_cap_usd=100, cloud_project_cap_usd=5)
    spend._book(library, 7.0)
    assert spend.plan_line(library, estimate_usd=1.0)["project_remaining_usd"] == 0.0
    assert spend.plan_line(_project(tmp_path / "n"), estimate_usd=1.0)["project_remaining_usd"] is None


# --- the one audited, undoable action -------------------------------------------------------------------------------


def test_changing_the_caps_is_audited_keeps_the_rest_and_one_undo_puts_both_back(
    client, db
):
    from fichero_server.models import ActionAudit

    assert (
        client.put(
            "/api/recipes/project",
            json={
                "answers": {"purposes": ["transcribe"], "cloud_spend_cap_usd": 10},
                "recipe": None,
            },
        ).status_code
        == 200
    )
    r = client.put(
        "/api/recipes/project/cloud-cap", json={"cap_usd": 25.5, "project_cap_usd": 60}
    )
    assert (
        r.status_code == 200
        and r.json()["cap_usd"] == 25.5
        and r.json()["project_cap_usd"] == 60
    )
    answers = _answers(client)
    assert (
        answers["cloud_spend_cap_usd"] == 25.5
        and answers["cloud_project_cap_usd"] == 60
        and answers["purposes"] == ["transcribe"]
    )
    assert (
        spend.cap_usd(_library(db)) == 25.5
        and spend.project_cap_usd(_library(db)) == 60
    )  # the ones the engine enforces
    audit = client.get("/api/actions/audit").json()["items"][0]
    assert (
        audit["id"] == r.json()["audit_id"]
        and audit["action_name"] == "project.save_setup"
    )
    assert any(a.id == audit["id"] for a in db.all(ActionAudit))
    assert client.post(f"/api/actions/audit/{audit['id']}/undo").status_code == 200
    answers = _answers(client)
    assert (
        answers["cloud_spend_cap_usd"] == 10 and "cloud_project_cap_usd" not in answers
    )


def test_one_cap_alone_leaves_the_other_and_the_project_cap_can_be_cleared(client, db):
    client.put("/api/recipes/project/cloud-cap", json={"project_cap_usd": 8})
    assert (
        client.put("/api/recipes/project/cloud-cap", json={"cap_usd": 20}).json()[
            "project_cap_usd"
        ]
        == 8
    )
    r = client.put("/api/recipes/project/cloud-cap", json={"clear_project_cap": True})
    assert r.json()["project_cap_usd"] is None and r.json()["cap_usd"] == 20
    assert spend.project_cap_usd(_library(db)) is None


@pytest.mark.parametrize(
    "bad",
    [
        {"cap_usd": -1},
        {"cap_usd": "ten"},
        {"project_cap_usd": -5},
        {},
        {"project_cap_usd": 3, "clear_project_cap": True},
    ],
)
def test_a_cap_below_zero_not_a_number_or_nothing_said_is_refused(client, bad):
    assert client.put("/api/recipes/project/cloud-cap", json=bad).status_code == 422


def test_a_zero_cap_is_a_cap(client, db):
    assert (
        client.put("/api/recipes/project/cloud-cap", json={"cap_usd": 0}).status_code
        == 200
    )
    assert spend.cap_usd(_library(db)) == 0.0


def test_setup_refuses_a_project_cap_below_zero_too(client):
    r = client.put(
        "/api/recipes/project",
        json={"answers": {"cloud_project_cap_usd": -1}, "recipe": None},
    )
    assert r.status_code == 422 and "total cloud spending cap" in r.text


# --- run fewer pages: the first N in Finder order -------------------------------------------------------------------


def test_the_first_pages_that_fit_are_priced_on_what_each_has_still_to_do(db):
    """100 pages, the last 80 done: only the first 20 cost anything. Pro-rating the estimate over all 100 pages offered a
    run on the first 62 (still all 20 to do, still over); walking the pages in Finder order finds the 12 that fit."""
    from fichero_server.recipes.cloud_cap import estimate_on, first_pages_that_fit
    from fichero_server.models import Artifact
    from fichero_server.recipes.done import material

    model = "claude-haiku-4-5"
    card = {
        "card": "workflow",
        "runs_on": "cloud:anthropic",
        "model_override": model,
        "provider_override": "anthropic",
        "workflow_id": None,
        "job": "read-a-page",
        "steps": ["read-a-page"],
        "workflow": "Read",
    }
    plan = {"runs": [card], "workflows": [card]}
    for i in range(100):
        doc = Document(name=f"p{i:03}", doc_type=DocType.page, page_content="")
        db.save(doc)
        if i >= 20:  # the last 80 are read already
            db.save(
                Artifact(
                    document_id=doc.id,
                    artifact_type="transcription",
                    content="x",
                    model=model,
                )
            )
    whole = estimate_on(db, plan, material(db, None), None, {})
    per_page = whole["total_cost_usd"] / 20
    assert whole["runs"][0]["pages"] == 20 and per_page > 0
    def price(within):
        return estimate_on(db, plan, material(db, within), within, {})

    line = {
        "remaining_usd": 12.5 * per_page,
        "project_remaining_usd": None,
    }
    assert first_pages_that_fit(db, plan, line, whole["pages"], price) == 12
    assert int(line["remaining_usd"] * 100 / whole["total_cost_usd"]) == 62  # the old answer
    line["remaining_usd"] = per_page / 2
    assert first_pages_that_fit(db, plan, line, whole["pages"], price) is None  # not even one page
    line["remaining_usd"] = 0.0
    assert first_pages_that_fit(db, plan, line, whole["pages"], price) is None


def test_the_first_pages_are_the_first_in_finder_order(db):
    from fichero_server.recipes.cloud_cap import first_pages_of as _first_pages

    names = {}
    for name in [
        "IMG_10.png",
        "IMG_2.png",
        "IMG_1.png",
        "IMG_9.png",
    ]:  # saved shuffled: creation order is not the answer
        doc = Document(
            name=name,
            doc_type=DocType.file,
            file_type=FileType.image,
            path=f"/x/{name}",
        )
        db.save(doc)
        names[doc.id] = name
    assert [names[i] for i in _first_pages(db, 3)] == [
        "IMG_1.png",
        "IMG_2.png",
        "IMG_9.png",
    ]
    assert len(_first_pages(db, 99)) == 4


def test_a_plan_on_the_first_pages_counts_only_them_and_refuses_a_folder_beside_it(
    client, db
):
    for n in (1, 2, 3):
        db.save(
            Document(
                name=f"IMG_{n}.png",
                doc_type=DocType.file,
                file_type=FileType.image,
                path=f"/x/{n}.png",
            )
        )
    assert (
        client.put(
            "/api/recipes/project",
            json={"answers": {"purposes": ["transcribe"]}, "recipe": None},
        ).status_code
        == 200
    )
    whole = client.get("/api/recipes/project/start").json()["estimate"]["pages"]
    two = client.get("/api/recipes/project/start", params={"first_pages": 2}).json()[
        "estimate"
    ]["pages"]
    assert (whole, two) == (3, 2)
    assert (
        client.get("/api/recipes/project/start", params={"first_pages": 0}).status_code
        == 422
    )
    assert (
        client.get(
            "/api/recipes/project/start", params={"first_pages": 2, "folder_id": "x"}
        ).status_code
        == 422
    )


# --- a run paused at a cap says so, in a field ----------------------------------------------------------------------


def test_a_step_run_paused_at_a_cap_is_marked_on_its_recipe_run_until_it_goes_on(
    tmp_path, db, monkeypatch
):
    """The run strip offered "Change the Cap" by matching words the paused run's reason did not carry. The engine marks
    the run (`stopped_at_cap`, and its words in `reason`) from the call it refused; Resume, or a call sent, clears it."""
    import json

    from fichero_server.execution import jobs
    from fichero_server.recipes import runner
    from fichero_server.workflows import node_context

    monkeypatch.setattr(
        usage,
        "_registry_entry",
        lambda model, provider="": {
            "input_cost_per_token": 1e-6,
            "output_cost_per_token": 1e-5,
        },
    )
    runner.register_job_kinds()
    library = _project(tmp_path, cloud_spend_cap_usd=1)
    spend._book(library, 1.0)
    recipe = jobs.enqueue(db, runner.KIND, "capped")
    jobs.enqueue(db, "workflow", "thread-cap-1")
    db.execute(
        "UPDATE jobs SET state = 'paused', detail = ? WHERE id = ?",
        [json.dumps({"awaiting": {"card": "read", "child": "thread-cap-1"}}), recipe],
    )
    assert runner.status(db, recipe)["stopped_at_cap"] is False

    async def refused():
        node_context.set_current_node("n1", run_id="thread-cap-1")
        config = LLMConfig(provider="openai", model="gpt-test", api_key="k", max_tokens=1000)  # worst case $0.04
        async with spend.holding(config, library):
            raise AssertionError("sent")

    try:
        with pytest.raises(spend.CloudSpendRefusedError):
            asyncio.run(refused())
        said = runner.status(db, recipe)
        assert said["stopped_at_cap"] is True
        assert "capped at $1.00 a month" in said["reason"]
        # the plan's estimate may fit while one call's worst case does not: the stop names the cap that lets that call through
        assert said["stopped_needs_cap_usd"] == 1.04
        assert said["stopped_needs_project_cap_usd"] is None
        spend.forget_cap_stop("thread-cap-1")  # Resume
        assert runner.status(db, recipe)["stopped_at_cap"] is False
    finally:
        spend.forget_cap_stop("thread-cap-1")
        from fichero_server.execution.cancellation import clear_pause

        clear_pause("thread-cap-1")

"""The three ruled money-and-place settings (#5769, ruled 2026-10-17): `source.onboard.spend-cap`,
`source.onboard.cluster-offer`, `source.onboard.copies-may-stay-on-cluster`.

WHY: setup had none of them, so Hugging Face training said it ran by itself with no cap, a person with ACENet access
was never offered it, and nothing said whether working copies may stay on the cluster.
"""
from __future__ import annotations

import pytest

from fichero_server.recipes.answers import copies_may_stay, normalise, spend_cap
from fichero_server.recipes.train_offers import TRAIN_HERE_MIN_RAM_GB, train_offers, training_setting

SMALL = TRAIN_HERE_MIN_RAM_GB - 8
RECIPE = {"steps": [{"id": "read", "job": "read-a-line", "settings": {}}]}
COUNTS = {"pages": [], "unmarked": 0, "region_pages": 0, "scope_ids": ["root"], "teacher": "gemini-2.5-pro"}


def test_spend_cap_holds_paid_offers():
    """Default $0: every paid offer stays an offer. Hugging Face never runs by itself under a $0 cap, and its places say
    why they are held; a cap above $0 lets the setting stand."""
    assert spend_cap({}) == 0.0
    held = training_setting("huggingface", mac_memory_gb=SMALL, hf_configured=True, spend_cap=0.0)
    assert held["mode"] == "offered" and "$0" in held["why"]
    assert training_setting(None, mac_memory_gb=SMALL, hf_configured=True, spend_cap=0.0)["mode"] == "offered"
    assert training_setting("huggingface", mac_memory_gb=SMALL, hf_configured=True, spend_cap=20.0)["mode"] == "huggingface"
    (offer,) = train_offers(RECIPE, COUNTS, stays_local=False, setting=held, spend_cap=0.0)
    hf = [t for w in offer["ways"] for t in w["targets"] if t["place"] == "huggingface-jobs"]
    assert hf and all("$0" in t["held"] for t in hf)
    assert all(t.get("held") is None for w in offer["ways"] for t in w["targets"] if t["place"] == "this-mac")
    with pytest.raises(ValueError, match="spend cap"):
        normalise({"purposes": ["transcribe"], "hf_spend_cap_usd": -5}, strict=True)


def test_cluster_offered_beside_hf():
    """Where a cluster is set up, every way offered on Hugging Face also offers the cluster, free, with the attended first
    run's steps named; no cluster set up, none is offered."""
    (offer,) = train_offers(RECIPE, COUNTS, stays_local=False, setting={"mode": "offered", "why": ""},
                            clusters=["ACENET Siku"])
    for way in offer["ways"]:
        if any(t["place"] == "huggingface-jobs" for t in way["targets"]):
            (cluster,) = [t for t in way["targets"] if t["place"] == "cluster"]
            assert cluster["name"] == "ACENET Siku" and cluster["first_run"] and cluster["starts"] is None
    (none,) = train_offers(RECIPE, COUNTS, stays_local=False, setting={"mode": "offered", "why": ""})
    assert not [t for w in none["ways"] for t in w["targets"] if t["place"] == "cluster"]
    (kept,) = train_offers(RECIPE, COUNTS, stays_local=True, setting={"mode": "offered", "why": ""},
                           clusters=["ACENET Siku"])
    assert not [t for w in kept["ways"] for t in w["targets"] if t["place"] == "cluster"]  # pages stay on this Mac


def test_copies_stay_default_follows_pages_may_leave():
    assert copies_may_stay({"cloud_allowed": True}) is True
    assert copies_may_stay({}) is False
    assert copies_may_stay({"cloud_allowed": True, "copies_may_stay_on_cluster": False}) is False
    with pytest.raises(ValueError, match="copies"):
        normalise({"purposes": ["transcribe"], "copies_may_stay_on_cluster": "maybe"}, strict=True)


def test_spend_this_month_is_shown_against_the_cap(db):
    """`source.onboard.spend-cap`: the Start plan shows this month's Hugging Face spend against the cap, each Job at its
    most (its hardware's price an hour times its time limit, where it ends); a Job of last month, or one never sent,
    does not count, and a Job with no listed price is counted as unknown, never as $0."""
    import json
    from datetime import datetime, timezone

    from fichero_server.execution import jobs
    from fichero_server.recipes.train_offers import spend_this_month

    now = datetime(2026, 10, 18, tzinfo=timezone.utc)
    jobs._ensure(db)

    def sent(kind, price, timeout, *, at=None, far_id="far-1"):  # a finished row: the scheduler never runs it
        db.execute("INSERT INTO jobs (id, kind, subject, state, attempts, started_by, created_at, target, detail) "
                   "VALUES (?, ?, ?, 'done', 0, 't', ?, 'huggingface-jobs', ?)",
                   [f"{kind}-{price}-{timeout}-{at}-{far_id}", kind, "s", at or now,
                    json.dumps({"price_per_hour_usd": price, "far_id": far_id, "request": {"timeout": timeout}})])

    sent("train-a-model", 0.4, "4h")  # at most $1.60
    sent("read-at-scale", 1.0, "1h30m")  # at most $1.50
    sent("train-a-model", None, "2h")  # price unknown
    sent("train-a-model", 9.0, "4h", at=datetime(2026, 9, 30, tzinfo=timezone.utc))  # last month
    sent("train-a-model", 9.0, "4h", far_id=None)  # still waiting to be sent: nothing spent yet
    spend = spend_this_month(db, cap=5.0, now=now)
    assert spend["cap_usd"] == 5.0 and spend["spent_at_most_usd"] == 3.1 and spend["jobs"] == 3
    assert spend["unpriced"] == 1 and spend["month"] == "2026-10"
    assert "$3.10 of $5.00" in spend["sentence"] and "1 with no listed price" in spend["sentence"]


def test_a_reading_run_counts_each_shard_it_sent_and_a_cluster_read_costs_nothing_here(db):
    """A reading run is one row of many Jobs: each shard sent (each try) is a Job at its most. A read on a cluster is
    the same kind of row and is not bought by the hour, so it is outside the Hugging Face spend."""
    import json
    from datetime import datetime, timezone

    from fichero_server.execution import jobs
    from fichero_server.recipes.train_offers import spend_this_month

    now = datetime(2026, 10, 18, tzinfo=timezone.utc)
    jobs._ensure(db)

    def read(row_id, target, shards):
        db.execute("INSERT INTO jobs (id, kind, subject, state, attempts, started_by, created_at, target, detail) "
                   "VALUES (?, 'read-at-scale', 's', 'done', 0, 't', ?, 'huggingface-jobs', ?)",
                   [row_id, now, json.dumps({"price_per_hour_usd": 1.0, "request": {"timeout": "1h", "target": target},
                                             "shards": shards})])

    read("hf", "huggingface-jobs", {"0": {"state": "landed", "tries": 2, "far_id": "a"},
                                    "1": {"state": "landed", "tries": 1, "far_id": "b"},
                                    "2": {"state": "pending", "tries": 0}})
    read("cluster", "rorqual", {"0": {"state": "landed", "tries": 1, "far_id": "101_0"}})
    spend = spend_this_month(db, cap=5.0, now=now)
    assert spend["jobs"] == 3 and spend["spent_at_most_usd"] == 3.0, spend


def test_the_month_turns_at_midnight_utc(db):
    """Review 104: the month's boundary is UTC, whatever zone a row's time was written in."""
    import json
    from datetime import datetime, timedelta, timezone

    from fichero_server.execution import jobs
    from fichero_server.recipes.train_offers import spend_this_month

    jobs._ensure(db)
    eastern = timezone(timedelta(hours=-4))
    for row_id, at in (("late-sept-eastern", datetime(2026, 9, 30, 21, 30, tzinfo=eastern)),  # 01:30 UTC on 1 Oct
                       ("sept-utc", datetime(2026, 9, 30, 23, 59, tzinfo=timezone.utc))):
        db.execute("INSERT INTO jobs (id, kind, subject, state, attempts, started_by, created_at, target, detail) "
                   "VALUES (?, 'train-a-model', 's', 'done', 0, 't', ?, 'huggingface-jobs', ?)",
                   [row_id, at, json.dumps({"price_per_hour_usd": 1.0, "far_id": row_id, "request": {"timeout": "1h"}})])
    now = datetime(2026, 10, 1, 1, 0, tzinfo=eastern)  # 05:00 UTC on 1 Oct
    assert spend_this_month(db, cap=5.0, now=now)["jobs"] == 1


def test_a_reading_runs_inspector_shows_the_spend_against_the_cap(db):
    """The remote-run Inspector shows Hugging Face cost against the spend cap (rulings 2026-10-17 11:50)."""
    import json

    from fichero_server.execution import jobs
    from fichero_server.remote_read import job as read_job

    jobs._ensure(db)

    def row(row_id, request):  # a finished row: the scheduler never runs it
        db.execute("INSERT INTO jobs (id, kind, subject, state, attempts, started_by, created_at, target, detail) "
                   "VALUES (?, ?, ?, 'done', 0, 't', now(), ?, ?)",
                   [row_id, read_job.KIND, f"read:{row_id}", read_job.TARGET, json.dumps({"request": request})])
        return row_id

    request = {"scope_ids": ["f"], "reader": "vlm", "card": "c", "pages_may_leave": True}
    assert "of $0.00" in read_job.status(db, row("hf", request))["hf_spend"]["sentence"]
    cluster = row("cluster", {**request, "target": "rorqual"})
    assert read_job.status(db, cluster)["hf_spend"] is None


def test_the_start_plan_carries_the_spend(client):
    from tests.unit.recipes.test_recipe_execution_to_spec import _recipe, _save

    _save(client, _recipe(None, {"id": "lines", "job": "find-lines",
                                 "model": {"kraken": "blla", "kraken_version": "bundled"}}))
    spend = client.get("/api/recipes/project/start").json()["hf_spend"]
    assert spend["cap_usd"] == 0.0 and spend["spent_at_most_usd"] == 0.0 and "$0.00 of $0.00" in spend["sentence"]


def test_setup_reads_the_money_and_place_settings_from_the_engine(client, monkeypatch):
    """The setup screen shows the three settings as the engine holds them (on the stages it reads), and works none
    out: the copies question's value follows pages-may-leave until the person answers it, and is asked only where a
    cluster is set up."""
    from fichero_server.api.routes.system import recipes as routes

    monkeypatch.setattr(routes, "_cluster_names", lambda request: ["Rorqual"])

    def put(answers):
        body = {"answers": {"purposes": ["transcribe"], **answers}, "recipe": None}
        r = client.put("/api/recipes/project", json=body)
        assert r.status_code == 200, r.text
        r = client.get("/api/recipes/stages")
        assert r.status_code == 200, r.text
        return r.json()["money_and_place"]

    shown = put({"cloud_allowed": True})
    assert shown["hf_spend_cap_usd"] == 0.0 and shown["clusters"] == ["Rorqual"]
    assert shown["copies_may_stay_on_cluster"] is True and shown["copies_follow_pages_may_leave"] is True
    shown = put({"cloud_allowed": True, "copies_may_stay_on_cluster": False, "hf_spend_cap_usd": 20})
    assert shown["copies_may_stay_on_cluster"] is False and shown["copies_follow_pages_may_leave"] is False
    assert shown["hf_spend_cap_usd"] == 20.0


@pytest.mark.parametrize("owner", [True, False])
def test_cluster_names_reach_only_the_owner(client, monkeypatch, owner):
    """Review 124: every /api/hpc route is owner-only (review 85), so the stages' money_and_place and the Start plan's
    cluster offer name no cluster to anyone else."""
    from fastapi import HTTPException

    from fichero_server.api.routes.ai import hpc
    from fichero_server.api.routes.auth import accounts
    from fichero_server.db import app as app_db

    def check(request):
        if not owner:
            raise HTTPException(status_code=403, detail="owner access required")

    monkeypatch.setattr(accounts, "_require_owner_or_bootstrap", check)
    monkeypatch.setattr(app_db, "get_app_db", lambda: None)
    monkeypatch.setattr(hpc, "_load_clusters", lambda db: {"r": {"name": "Rorqual", "cluster_id": "r"}})
    r = client.put("/api/recipes/project", json={"answers": {"purposes": ["transcribe"]}, "recipe": None})
    assert r.status_code == 200, r.text
    shown = client.get("/api/recipes/stages").json()["money_and_place"]
    assert shown["clusters"] == (["Rorqual"] if owner else [])
    from fichero_server.api.routes.system import recipes as routes

    seen, real = [], routes._start_plan

    def plan(db, folder_id=None, *, clusters=()):
        seen.append(list(clusters))
        return real(db, folder_id, clusters=clusters)

    monkeypatch.setattr(routes, "_start_plan", plan)
    client.get("/api/recipes/project/start")
    assert seen == [["Rorqual"] if owner else []]

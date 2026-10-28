"""`source.recipe.step-runs-on-huggingface` (#6173): a step the person puts on Hugging Face Jobs is placed there by the plan
and sent there by Start as a read-at-scale run under its step; pages leave only with the project's yes, the app's place and
a monthly cap above $0, checked at plan time and again when the step runs.

WHY: the engine could read with Kraken on Hugging Face Jobs, but the recipe runner only ever sent a read to a cluster, so no
step could choose Hugging Face."""
from __future__ import annotations

import pytest

from fichero_server.recipes import places, runner
from fichero_server.recipes.start import place_runs

HF_RUN = {"steps": ["read"], "job": "read-a-line", "card": "workflow", "provider_override": "kraken",
          "model_override": "catmus-medieval", "runs_on": "this-mac", "chosen_place": "huggingface-jobs"}
HERE_RUN = {**HF_RUN, "chosen_place": None}
VISION_RUN = {**HF_RUN, "provider_override": "omlx", "model_override": "mlx-community/Qwen2.5-VL-7B-Instruct-4bit"}


def _place(run, pages=100, **kw):
    kw.setdefault("cloud_allowed", True)
    kw.setdefault("hf_allowed", True)
    kw.setdefault("hf_cap_usd", 10.0)
    [out] = place_runs([dict(run)], pages, **kw)
    return out


def test_a_kraken_step_the_person_put_on_huggingface_is_placed_there_at_any_size():
    run = _place(HF_RUN, pages=100)
    assert run["place"] == "huggingface" and run["target"] == "huggingface-jobs"
    assert "Hugging Face" in run["why"]


def test_a_person_who_allows_huggingface_but_not_acenet_still_gets_the_step_placed_there():
    """`cloud_allowed` is the ACENet check the cluster path uses; the chosen-Hugging Face branch reads `hf_allowed` alone."""
    run = _place(HF_RUN, cloud_allowed=False)
    assert run["place"] == "huggingface"


def test_a_step_not_put_there_stays_here():
    assert _place(HERE_RUN)["place"] == "this-mac"


@pytest.mark.parametrize("kw, said", [({"hf_allowed": False}, "pages may not leave"),
                                      ({"hf_cap_usd": 0.0}, "cap"),
                                      ({"hf_spent_usd": 10.0}, "reached")])
def test_pages_stay_here_and_it_says_why_when_they_may_not_leave_or_there_is_no_cap(kw, said):
    run = _place(HF_RUN, **kw)
    assert run["place"] == "this-mac" and run["target"] is None and said in run["why"]


def test_a_vision_reader_stays_here_and_says_so():
    run = _place(VISION_RUN)
    assert run["place"] == "this-mac" and "Kraken" in run["why"]


def _card():
    return {"place": "huggingface", "target": "huggingface-jobs", "model_override": "catmus-medieval", "job": "read-a-line"}


def _setup(monkeypatch, answers):
    from fichero_server.recipes import project

    monkeypatch.setattr(project, "read_project_setup", lambda _lib: {"answers": answers})
    monkeypatch.setattr(runner, "_library", lambda _db: "lib")


def test_start_sends_the_read_to_huggingface_as_one_run_under_its_step(monkeypatch):
    from fichero_server.remote_read import job as read_job

    _setup(monkeypatch, {"cloud_allowed": True, "hf_spend_cap_usd": 10})
    monkeypatch.setattr(places, "allows", lambda place, _p=None: True)
    from fichero_server.recipes import train_offers

    monkeypatch.setattr(train_offers, "spend_this_month", lambda _db, *, cap: {"spent_at_most_usd": 1.5})
    sent = {}

    def start(db, request, *, started_by):
        sent.update(request=request, by=started_by)
        return {"job_id": "read-1"}

    monkeypatch.setattr(read_job, "start", start)
    monkeypatch.setattr(runner, "_wait", lambda _db, child, parent: (child, "done", None))
    child, state, why = runner._run_at_scale(None, _card(), ["p1", "p2"], "run-1", "owner")
    request = sent["request"]
    assert (child, state, why) == ("read-1", "done", None)
    assert (request.target, request.reader, request.card, request.scope_ids, request.parent_job_id) == (
        "huggingface-jobs", "kraken", "catmus-medieval", ["p1", "p2"], "run-1")
    assert request.pages_may_leave is True


@pytest.mark.parametrize("answers, app_allows, spent, said", [
    ({"cloud_allowed": False, "hf_spend_cap_usd": 10}, True, 0.0, "may not leave"),
    ({"cloud_allowed": True, "hf_spend_cap_usd": 10}, False, 0.0, "may not leave"),
    ({"cloud_allowed": True}, True, 0.0, "cap"),
    ({"cloud_allowed": True, "hf_spend_cap_usd": 10}, True, 10.0, "reached")])
def test_the_step_is_refused_when_it_runs_if_the_yes_the_place_or_the_cap_is_gone(monkeypatch, answers, app_allows, spent,
                                                                                said):
    from fichero_server.recipes import train_offers
    from fichero_server.remote_read import job as read_job

    _setup(monkeypatch, answers)
    monkeypatch.setattr(train_offers, "spend_this_month", lambda _db, *, cap: {"spent_at_most_usd": spent})
    monkeypatch.setattr(places, "allows", lambda place, _p=None: app_allows)
    monkeypatch.setattr(read_job, "start", lambda *a, **k: pytest.fail("pages left this Mac"))
    child, state, why = runner._run_at_scale(None, _card(), ["p1"], "run-1", "owner")
    assert (child, state) == (None, "failed") and said in why


def test_a_reading_step_is_put_on_huggingface_and_back_and_nothing_else_is():
    from fichero_server.recipes.start import set_step_place

    recipe = {"steps": [{"id": "read", "job": "read-a-line"}, {"id": "names", "job": "find-names-tag-words"}]}
    there = set_step_place(recipe, "read", "huggingface-jobs")
    assert there["steps"][0]["place"] == "huggingface-jobs" and "place" not in recipe["steps"][0]
    assert "place" not in set_step_place(there, "read", "this-mac")["steps"][0]
    for step, place in (("names", "huggingface-jobs"), ("nope", "huggingface-jobs"), ("read", "the-moon")):
        with pytest.raises(ValueError):
            set_step_place(recipe, step, place)


def test_a_chosen_reader_keeps_the_place_the_person_put_its_step_on():
    """Choosing a reader (Use This) sets the step's runs_on from the card; the place is its own key and stays."""
    from fichero_server.recipes.assemble import Card
    from fichero_server.recipes.bakeoff import apply_project_overrides

    card = Card(id="kraken-x", pin={"zenodo": "10.5281/zenodo.1"}, jobs=frozenset({"read-a-line"}), scripts=None,
                languages=None, material=frozenset())
    recipe = {"steps": [{"id": "read", "job": "read-a-line", "place": "huggingface-jobs"}],
              "overrides": [{"step": "read", "scope": "project", "card": "kraken-x", "model": dict(card.pin)}]}
    assert apply_project_overrides(recipe, [card])["steps"][0]["place"] == "huggingface-jobs"


def test_a_recipe_step_on_huggingface_reads_every_page_and_the_readings_land_under_the_step(db, tmp_path, monkeypatch):
    """The whole chain with Hugging Face replaced by the fake hub that runs Fichero's own shard runner: the recipe's step ->
    one read-at-scale run under it -> shards -> each page's reading landed as a pass. The job and the pages are real."""
    from fichero_server.execution import jobs
    from fichero_server.models import DocType, Document, FileType, SegmentPass
    from fichero_server.remote_read import job as read_job
    from fichero_server.training import hf_jobs
    from tests.unit.remote_read.test_read_at_scale_job import FakeHub

    monkeypatch.setattr(read_job, "_work_dir", lambda job_id: tmp_path / "work" / job_id)
    monkeypatch.setattr(jobs._scheduler, "wake", lambda key: None)
    monkeypatch.setattr(read_job, "resolve_step", lambda request, bucket: {
        "reader": "vlm", "card": request.card, "model": "/work/models/student", "prompt": "Read the line.",
        "lines_per_call": 1, "language": "es"})
    monkeypatch.setattr(places, "get_places", lambda: list(places.PLACES))
    _setup(monkeypatch, {"cloud_allowed": True, "hf_spend_cap_usd": 10})
    hub = FakeHub()
    monkeypatch.setattr(hf_jobs, "HfJobsTarget", lambda: hub)
    folder = Document(name="Folder", doc_type=DocType.folder)
    db.save(folder)
    (tmp_path / "photos").mkdir()
    ids = []
    from PIL import Image

    for i in range(5):
        path = tmp_path / "photos" / f"p{i}.jpg"
        Image.new("RGB", (300, 400), (200 + i, 200, 190)).save(path)
        doc = Document(name=path.name, doc_type=DocType.file, file_type=FileType.image, path=str(path),
                       parent_id=folder.id, sequence=i)
        db.save(doc)
        ids.append(doc.id)
    cards = [{"steps": ["read"], "card": "workflow", "job": "read-a-line"}]
    parent = runner.enqueue(db, {"runs": cards, "skipped": []}, documents=None, started_by="owner")

    def wait_and_run(_db, child, _parent):  # the lane would run it; here it runs at once, against the fake hub
        jobs.set_parent(db, child, _parent)
        subject = db.execute_fetchone("SELECT subject FROM jobs WHERE id = ?", [child])[0]
        read_job.run(db, subject, target=hub, sleep=lambda s: None)
        return child, "done", None

    monkeypatch.setattr(runner, "_wait", wait_and_run)
    card = {**_card(), "model_override": "fichero-trained/sergio"}
    child, state, why = runner._run_at_scale(db, card, ids, parent, "owner")
    assert (state, why) == ("done", None)
    assert db.execute_fetchone("SELECT parent_id FROM jobs WHERE id = ?", [child])[0] == parent
    assert all(len(list(db.query(SegmentPass, document_id=doc_id))) == 1 for doc_id in ids)

"""The model chooser is per step (#5668, the maintainer's walkthrough, section 4), tested to the spec:
`source.find.candidates-fit-the-step`, `source.find.online-search-per-step`
(docs/contributor_manual/specs/source/models-chains-and-projects.md) and `prep.regions.open-default`
(docs/contributor_manual/specs/source/image-preparation.md).

WHY: Find statements listed OCR vision models (Qwen-VL OCR) and said "Searched for readers only"; Find Regions'
only model was AGPL-3.0, so a licence sheet stood between a new project and its first run. Hugging Face is a fake
(`_fetch_hf_models`), counting what it was asked; the model store is the stubbed `mac`.
"""

from __future__ import annotations


import pytest

from fichero_server.recipes import discovery
from tests.unit.recipes.test_installed_model_first_to_spec import mac  # noqa: F401  (fixture)


@pytest.fixture(autouse=True)
def _store(monkeypatch, tmp_path):
    monkeypatch.setattr(discovery, "_store_root", lambda: tmp_path / "store")


def _candidates(client, job, **params):
    r = client.get("/api/recipes/candidates", params={"job": job, "scripts": "Latn", "languages": "es", **params})
    assert r.status_code == 200, r.text
    return r.json()


# --- source.find.candidates-fit-the-step -------------------------------------------------------------------------


def test_find_statements_never_lists_a_reader_and_find_regions_lists_layout_models(client, mac):
    """"A vision model made to read pages … is never a card for a text job, so Find statements never lists
    Qwen-VL OCR": the catalogue's text model is offered, none with a vision path, installed or not."""
    from fichero_server.llm.mlx_model_store import MANAGED_MLX_MODELS

    mac.installed.add("Qwen2.5-VL-3B")
    readers = {s.repo_id for s in MANAGED_MLX_MODELS.values() if "vision" in s.capabilities}
    texts = {s.repo_id for s in MANAGED_MLX_MODELS.values() if tuple(s.capabilities) == ("text",)}
    for job in ("find-statements", "find-names-tag-words", "split-into-entries"):
        offered = {i["pin"].get("hf") for i in _candidates(client, job)["items"]}
        assert not offered & readers, (job, offered & readers)
        assert texts <= offered, (job, texts - offered)

    regions = _candidates(client, "find-regions")["items"]
    assert {i["id"] for i in regions} == {"kraken:builtin/blla@bundled",
                                         "yolo:hf/hantian/yolo-doclaynet/yolov11n@unpinned"}


# --- prep.regions.open-default ------------------------------------------------------------------------------------


def test_find_regions_defaults_to_krakens_open_segmenter_and_yolo_stays_a_choice(client, with_material):
    """"Find Regions' default is Kraken's built-in segmenter (Apache-2.0 …). The YOLO DocLayNet model (AGPL-3.0)
    stays a candidate to choose, with its licence sheet.\""""
    r = client.post("/api/recipes/assemble", json={"languages": ["es"], "scripts": ["Latn"], "mac_memory_gb": 16,
                                                    "jobs": ["find-regions"]})
    assert r.status_code == 200, r.text
    step = next(s for s in r.json()["steps"] if s["job"] == "find-regions")
    assert step["model"] == {"kraken": "blla", "kraken_version": "bundled"}, step
    assert step["card"]["licence"] == "Apache-2.0" and step.get("problem") is None

    items = {i["id"]: i for i in _candidates(client, "find-regions")["items"]}
    assert items["kraken:builtin/blla@bundled"]["rule_rank"] == 1
    yolo = items["yolo:hf/hantian/yolo-doclaynet/yolov11n@unpinned"]
    assert yolo["licence"] == "AGPL-3.0" and yolo["open_licence"] is False


def test_krakens_regions_land_as_a_machines_regions(client, db, tmp_path, monkeypatch):
    """"each text block it finds becomes a region with its outline, made by Kraken": the segmenter's region
    outlines, as page fractions, on a pass made by Kraken, never a person."""
    from PIL import Image

    from fichero_server.llm import kraken_runtime
    from fichero_server.models import Artifact, DocType, Document, FileType, Status
    from fichero_server.recipes.regions import find_regions

    photo = tmp_path / "page.jpg"
    Image.new("RGB", (1000, 2000), (230, 225, 210)).save(photo)
    page = Document(name="page.jpg", doc_type=DocType.file, file_type=FileType.image, path=str(photo),
                    status=Status.completed)
    db.save(page)
    monkeypatch.setattr(kraken_runtime, "segment_lines", lambda path, **k: {
        "width": 1000, "height": 2000, "lines": [{"id": "l1"}],
        "regions": [{"id": "r1", "type": "text", "polygon": [[100, 200], [900, 200], [900, 1000], [100, 1000]]}]})

    account = find_regions(db, [page.id], "run-1", "blla", provider="kraken")

    assert account == {"pages": 1, "regions": 1, "no_image": 0}
    (art,) = db.query(Artifact, document_id=page.id)
    assert (art.provider, art.model, art.artifact_type) == ("kraken", "blla", "regions")
    body = client.get(f"/api/segments/document/{page.id}").json()
    (layer,) = [p for p in body["passes"] if p.get("model") == "blla"]
    assert layer["provenance_kind"] != "human"
    (region,) = [s for s in body["segments"] if s["pass_id"] == layer["id"]]
    assert region["kind"] == "region" and region["kind_raw"] == "text"


# --- source.find.online-search-per-step ---------------------------------------------------------------------------


class FakeHub:
    """Hugging Face's listing, by (task, tags) asked: what each step's search asks is recorded."""

    def __init__(self, listings):
        self.listings, self.asked = listings, []

    async def __call__(self, task=None, tags=None, limit=20, **kw):
        self.asked.append((task, tuple(tags or ())))
        return [m for (t, needs), ms in self.listings.items() if t == task and set(needs) <= set(tags or ())
                for m in ms]


def _model(repo, task, *tags):
    return {"modelId": repo, "pipeline_tag": task, "tags": list(tags), "downloads": 10}


def test_each_steps_search_asks_by_its_own_pipeline_and_tags_and_keeps_its_finds_for_that_step(monkeypatch):
    """"Search Online searches Hugging Face for THAT step's job, by the step's own pipeline tags and Hub tags …
    An MLX text build found for a text job downloads into the model store and runs …; anything else found is
    listed as one Fichero cannot run yet, saying why.\""""
    from fichero_server.api.routes.ai import models

    hub = FakeHub({
        ("text-generation", ("mlx",)): [_model("mlx-community/Qwen3-8B-4bit", "text-generation", "mlx",
                                               "license:apache-2.0")],
        ("token-classification", ("ner",)): [_model("someone/bert-ner-es", "token-classification", "ner", "es")],
        ("object-detection", ("doclaynet",)): [_model("someone/detr-doclaynet", "object-detection", "doclaynet")],
    })
    monkeypatch.setattr(models, "_fetch_hf_models", hub)
    monkeypatch.setattr(discovery, "egress_allowed", lambda: True)

    result = discovery.search_online_for_step("find-names-tag-words", frozenset({"es"}))

    assert result["sources"]["hugging-face"]["state"] == "searched"
    assert {task for task, _ in hub.asked} == {"token-classification", "text-generation"}
    assert ("token-classification", ("ner", "es")) in hub.asked  # each ask with the project's language too
    cards = {c.pin["hf"]: c for c in discovery.step_hub_cards("find-names-tag-words", frozenset({"es"}))}
    assert cards["mlx-community/Qwen3-8B-4bit"].runs_here and cards["mlx-community/Qwen3-8B-4bit"].open_licence
    tagger = cards["someone/bert-ner-es"]
    assert not tagger.runs_here and "spaCy" in tagger.cannot_run_because
    assert all(c.jobs == frozenset({"find-names-tag-words"}) for c in cards.values())
    assert discovery.step_hub_cards("find-statements", frozenset({"es"})) is None  # kept for its step only
    spec = discovery.hub_spec("mlx-community/Qwen3-8B-4bit")
    assert spec is not None and tuple(spec.capabilities) == ("text",)  # downloads as a text model, not a reader

    hub.asked.clear()
    discovery.search_online_for_step("find-regions", frozenset({"es"}))
    assert {task for task, _ in hub.asked} == {"object-detection"}
    (layout,) = discovery.step_hub_cards("find-regions", frozenset({"es"}))
    assert not layout.runs_here and "layout model" in layout.cannot_run_because


def test_a_steps_search_is_its_own_job_and_a_step_without_one_says_so(jobs_run_by_the_test, client, db, monkeypatch):
    """The step's search is queued as its own `find-models` job, by job and languages, beside the reader search;
    a job with no search of its own says so in place of "Searched for readers only".

    `jobs_run_by_the_test` first (#5701): queuing the search wakes the lanes, and a lane thread then ran the same
    job beside the test's own run, so the search ran twice on a loaded machine. The test runs it, once."""
    subject = discovery._subject(frozenset({"es"}), "find-statements")
    assert (discovery._job_of(subject), discovery._languages_of(subject)) == ("find-statements", frozenset({"es"}))
    reader = discovery._subject(frozenset({"es"}))
    assert (discovery._job_of(reader), discovery._languages_of(reader)) == (None, frozenset({"es"}))

    ran = []
    monkeypatch.setattr(discovery, "search_online_for_step", lambda job, languages, progress=None: ran.append(
        (job, languages)) or {"sources": {"hugging-face": {"state": "searched", "detail": "0 found"}}})
    from fichero_server.execution import jobs

    row = discovery.search(db, frozenset({"es"}), "find-statements")
    assert jobs.job_id_for(db, discovery.SEARCH_KIND, subject) == row["id"]  # queued by this step's subject
    assert jobs.read_job(db, row["id"])["state"] == "waiting", "no lane took it: this test runs it, once"
    discovery._run_search(db, subject)
    assert ran == [("find-statements", frozenset({"es"}))]

    body = _candidates(client, "put-in-order", online="true")
    hub = next(s for s in body["sources"] if s["source"] == "hugging-face")
    assert hub["detail"] == discovery.NO_STEP_SEARCH
    assert not any("readers only" in s["detail"] for s in body["sources"])

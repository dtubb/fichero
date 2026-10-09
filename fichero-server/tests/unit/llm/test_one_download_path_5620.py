"""Downloading a model has one path, and it shows (#5620), tested to the spec
(docs/contributor_manual/specs/source/models-chains-and-projects.md: `source.find.one-download-path`).

WHY: the maintainer pressed Download in Set Up › Ready and nothing happened: the route read the project's header raw,
so a project whose path had a space ("Marshall Diary 1940.fichero") was refused with a bare 404; and an MLX download
ran outside Activity, so its progress and its failure were seen nowhere. Through the public route the app calls
(`POST /api/local-models/download/{runtime}/{model}`) and the job's own run; this Mac's model store is stubbed
(`mac`): nothing is fetched.
"""
from __future__ import annotations

import asyncio
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from fichero_server.execution import jobs
from fichero_server.llm import local_models
from tests.unit.recipes.test_installed_model_first_to_spec import mac  # noqa: F401  (fixture)


@pytest.fixture
def held(monkeypatch):
    """The scheduler holds what is queued, so a test reads the row before it runs."""
    monkeypatch.setattr(jobs._scheduler, "wake", lambda key: None)


def test_a_project_whose_path_has_a_space_queues_the_download(tmp_path, held, app_db):
    """"The route reads the project from the library header as every other route does (#5620: a project whose path
    had a space was refused with a bare 404, so Download did nothing)." The app sends the header percent-encoded; the
    download is queued in that project and Activity lists it."""
    from fichero_server.api.auth import initialize_token
    from fichero_server.api.main import app
    from fichero_server.db import db_manager

    app.dependency_overrides.clear()
    client = TestClient(app)
    client.headers["Authorization"] = f"Bearer {initialize_token()}"
    package = tmp_path / "Projects" / "Marshall Diary 1940.fichero"
    try:
        assert client.post("/api/library", json={"path": str(package)}).status_code == 200
        headers = {"X-Fichero-Library-Path": quote(str(package), safe="/")}
        r = client.post("/api/local-models/download/spacy/es_core_news_md", headers=headers)
        assert r.status_code == 200, r.text
        job_id = r.json()["job_id"]
        listed = client.get("/api/activity/jobs", headers=headers).json()["jobs"]
        row = next(j for j in listed if j["id"] == job_id)
        assert row["task_type"] == local_models.DOWNLOAD_KIND and row["name"] == "Download a model"
    finally:
        db_manager.close_all()


def test_an_mlx_download_is_an_activity_job_too(client, db, held, mac):
    """"… which queues a `download-model` job on the network lane for every runtime, MLX included, so Activity lists
    it." Asking twice queues it once."""
    r = client.post("/api/local-models/download/mlx/Qwen2.5-VL-3B")
    assert r.status_code == 200, r.text
    job_id = r.json()["job_id"]
    row = jobs.read_job(db, job_id)
    assert row["kind"] == local_models.DOWNLOAD_KIND and row["subject"] == "mlx:Qwen2.5-VL-3B"
    again = client.post("/api/local-models/download/mlx/mlx-community/Qwen2.5-VL-3B-Instruct-4bit")
    assert again.status_code == 200 and again.json()["job_id"] == job_id, "its repository names the same model"
    assert any(j["id"] == job_id for j in client.get("/api/activity/jobs").json()["jobs"])


def test_a_model_this_mac_cannot_run_or_does_not_know_is_refused_at_once(client, held, mac, monkeypatch):
    """"… a refusal before queueing, such as a model this Mac cannot run, is said at once": in words, never queued."""
    monkeypatch.setattr("fichero_server.llm.local_inference.check_local_model_hardware",
                        lambda **kw: (False, "Qwen2.5-VL 3B needs 8 GB of memory; this Mac has 4 GB"))
    r = client.post("/api/local-models/download/mlx/Qwen2.5-VL-3B")
    assert r.status_code == 400 and "this Mac has 4 GB" in r.json()["detail"]
    unknown = client.post("/api/local-models/download/mlx/no-such-model")
    assert unknown.status_code == 400 and "no download for mlx:no-such-model" in unknown.json()["detail"]
    assert not [j for j in client.get("/api/activity/jobs").json()["jobs"]
                if j["task_type"] == local_models.DOWNLOAD_KIND]


def _fetching(mac, *, fail: str | None = None):
    """The store's fetch, stubbed: it says how far it has got twice, then finishes (or fails with `fail`)."""
    async def fetch(job, spec):
        job.state = "running"
        for done in (1, 2):
            job.message = f"Downloading {spec.display_name}: {done}.0 GB of 2.3 GB"
            await asyncio.sleep(0.05)
        if fail:
            raise RuntimeError(fail)
        job.state, job.message = "completed", "Download complete"
        mac.installed.add(spec.model_id)

    mac._run_download = fetch


def test_the_job_says_how_far_it_has_got_and_the_model_is_then_installed(client, db, held, mac, monkeypatch):
    """"While it runs the job's reason says how far it has got … when it finishes the engine says
    `model.installed`, the Start plan is read again and the step it waited for can run.\""""
    monkeypatch.setattr(local_models, "PROGRESS_EVERY_SECONDS", 0.0)
    monkeypatch.setattr("fichero_server.llm.mlx_model_store.DOWNLOAD_PROGRESS_POLL_SECONDS", 0.01)
    said = []
    monkeypatch.setattr(local_models, "say_installed", lambda runtime, model: said.append((runtime, model)))
    monkeypatch.setattr("fichero_server.api.change_stream.emit_change_all_libraries",
                        lambda **kw: said.append((kw["metadata"]["runtime"], kw["metadata"]["model"])))
    _fetching(mac)
    job_id = client.post("/api/local-models/download/mlx/Qwen2.5-VL-3B").json()["job_id"]
    reasons = []
    real = jobs.save_detail
    monkeypatch.setattr(jobs, "save_detail", lambda db_, jid, detail, reason=None: (reasons.append(reason),
                                                                                     real(db_, jid, detail, reason=reason)))
    jobs._current.job_id = job_id
    try:
        local_models._run_download("mlx:Qwen2.5-VL-3B", db)
    finally:
        jobs._current.job_id = None
    assert any(r and r.startswith("Downloading Qwen2.5-VL 3B") and "of 2.3 GB" in r for r in reasons), reasons
    assert "Qwen2.5-VL-3B" in mac.installed
    assert ("mlx", "Qwen2.5-VL-3B") in said


def test_a_failed_download_says_why(client, db, held, mac, monkeypatch):
    """"… a failure says why on the row, in the job's words": the job raises with the store's reason, which the
    scheduler keeps as the failed row's reason."""
    monkeypatch.setattr("fichero_server.llm.mlx_model_store.DOWNLOAD_PROGRESS_POLL_SECONDS", 0.01)
    _fetching(mac, fail="the MLX runtime is not set up on this Mac: set it up in Settings › AI")
    with pytest.raises(RuntimeError, match="the MLX runtime is not set up"):
        local_models._run_download("mlx:Qwen2.5-VL-3B", db)
    assert "Qwen2.5-VL-3B" not in mac.installed


def test_a_kraken_reader_downloads_by_the_same_path(client, db, held, monkeypatch):
    """"… for every runtime": Settings' Kraken reader rows use the one route too, so a Kraken reader is a
    `download-model` job, fetched by the job and then said installed; one that is not a reader is refused at once."""
    fetched, said = [], []
    monkeypatch.setattr("fichero_server.llm.kraken_runtime.download_recognition_model", fetched.append)
    monkeypatch.setattr(local_models, "say_installed", lambda runtime, model: said.append((runtime, model)))
    r = client.post("/api/local-models/download/kraken/kraken-mccatmus")
    assert r.status_code == 200, r.text
    assert jobs.read_job(db, r.json()["job_id"])["subject"] == "kraken:kraken-mccatmus"
    local_models._run_download("kraken:kraken-mccatmus", db)
    assert fetched == ["kraken-mccatmus"] and said == [("kraken", "kraken-mccatmus")]
    refused = client.post("/api/local-models/download/kraken/kraken-blla")
    assert refused.status_code == 400 and "not a Kraken reader" in refused.json()["detail"]

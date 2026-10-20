"""The egress gate fails closed (`ai.where.one-egress-gate`, #5368, review 672): a stored job's model calls belong to the
job's project, a call under no project is refused, an existing project is never migrated silently (one audited click
allows it, and Set Up takes it back), and a package sent to Hugging Face needs the project's yes AND the request's."""

from __future__ import annotations

import dataclasses
import time

import pytest

from fichero_server import llm
from fichero_server.execution import jobs
from fichero_server.llm import EgressRefusedError, LLMConfig, egress
from fichero_server.models import ActionAudit

CLOUD = LLMConfig(provider="openai", model="gpt-test", api_key="sk-test")


@pytest.fixture(autouse=True)
def _gate_on(monkeypatch):
    monkeypatch.setenv("FICHERO_LOCAL_ONLY", "0")
    egress._CACHE.clear()


@pytest.fixture
def built(monkeypatch):
    models: list[LLMConfig] = []
    monkeypatch.setattr(llm, "_build_langchain_model", lambda config: models.append(config) or object())
    return models


def _seen_by_a_metrics_job(client, monkeypatch) -> dict:
    """Run the metrics job with a body that makes a cloud call, as a stored job's worker thread would."""
    seen: dict = {}

    def body(db, subject):
        from fichero_server.observability.episodes import _episode_library_path

        seen["library"] = _episode_library_path.get()
        try:
            llm.get_langchain_model(CLOUD)
            seen["sent"] = True
        except EgressRefusedError as exc:
            seen["sent"], seen["words"] = False, str(exc)

    monkeypatch.setitem(jobs.KINDS, "metrics", dataclasses.replace(jobs.KINDS["metrics"], run=body))
    task_id = client.post("/api/tasks/metrics", json={"name": "Figures"}).json()["task_id"]
    deadline = time.time() + 60
    while "sent" not in seen and time.time() < deadline:
        time.sleep(0.05)
    assert "sent" in seen, "the job never ran"
    return seen


def test_a_stored_job_runs_under_its_project_and_a_project_that_has_not_said_yes_sends_nothing(
        client, test_package, built, monkeypatch):
    seen = _seen_by_a_metrics_job(client, monkeypatch)
    assert seen["library"] and seen["library"].rstrip("/").endswith(test_package.name)
    assert seen["sent"] is False and built == []
    assert test_package.stem in seen["words"] and "nothing left this Mac" in seen["words"]


def test_a_call_under_no_project_is_refused_in_words(built):
    with pytest.raises(EgressRefusedError) as refused:
        llm.get_langchain_model(CLOUD)
    assert built == [] and "No project is open" in str(refused.value)


def test_a_refusal_is_allowed_by_one_audited_click_and_taken_back_in_set_up(client, test_package, db, built):
    from fichero_server.observability import episodes

    token = episodes.set_library(str(test_package))
    try:
        with pytest.raises(EgressRefusedError) as refused:
            llm.get_langchain_model(CLOUD)
        assert refused.value.allow_action == "project.allow_cloud" and refused.value.project == str(test_package)

        answer = client.post("/api/recipes/project/allow-cloud")
        assert answer.status_code == 200 and answer.json() == {"project": test_package.stem, "cloud_allowed": True}
        llm.get_langchain_model(CLOUD)  # the next call goes
        assert len(built) == 1
        audits = [a for a in db.query(ActionAudit) if a.action_name == "project.allow_cloud"]
        assert len(audits) == 1 and audits[0].actor and audits[0].created_at  # who and when; the project is the db's

        saved = client.put("/api/recipes/project", json={"answers": {"cloud_allowed": False}})  # Set Up takes it back
        assert saved.status_code == 200, saved.text
        with pytest.raises(EgressRefusedError):
            llm.get_langchain_model(CLOUD)
    finally:
        episodes._episode_library_path.reset(token)


def test_allowing_keeps_the_rest_of_the_setup(client, test_package):
    client.put("/api/recipes/project", json={"answers": {"cloud_allowed": False, "pages": 40}})
    client.post("/api/recipes/project/allow-cloud")
    answers = client.get("/api/recipes/project").json()["answers"]
    assert answers["cloud_allowed"] is True and answers.get("pages") == 40


def test_a_package_sent_to_hugging_face_needs_the_projects_yes_as_well_as_the_requests(client, db, test_package):
    from fichero_server.models.compute_requests import ReadAtScaleRequest
    from fichero_server.remote_read import job as read_job

    request = ReadAtScaleRequest(scope_ids=["d1"], reader="kraken", card="x", target="huggingface-jobs",
                                 pages_may_leave=True)
    with pytest.raises(read_job.PagesMayNotLeave, match="keeps its pages on this Mac"):  # the request says yes, the project not
        read_job.start(db, request, started_by="t")
    request = request.model_copy(update={"pages_may_leave": False})
    client.post("/api/recipes/project/allow-cloud")
    with pytest.raises(read_job.PagesMayNotLeave, match="Say yes for this project"):  # the project says yes, the request not
        read_job.start(db, request, started_by="t")


def test_the_runs_failure_for_a_refusal_names_the_way_to_allow_it():
    from fichero_server.execution.runner import _typed_failure

    failure = _typed_failure(EgressRefusedError("openai", model="m", kind="chat"))
    assert failure["category"] == "egress_refused" and "Allow cloud" in failure["action"]


def test_the_key_test_and_the_model_list_never_meet_the_gate_because_they_send_no_content():
    """Named exemptions (spec): the provider key test and the model lists reach a provider with a key, never a page. They
    must stay that way: neither module may call a model."""
    import ast
    from pathlib import Path

    root = Path(llm.__file__).parent.parent / "api" / "routes" / "ai"
    forbidden = {"get_langchain_model", "chat", "chat_structured", "vision", "structured_output", "chat_with_tools",
                 "audio_transcription", "model_call_slot"}
    for name in ("provider_keys.py", "provider_models.py"):
        tree = ast.parse((root / name).read_text(encoding="utf-8"))
        called = {n.func.attr if isinstance(n.func, ast.Attribute) else getattr(n.func, "id", "")
                  for n in ast.walk(tree) if isinstance(n, ast.Call)}
        assert not (called & forbidden), f"{name} calls a model: {called & forbidden}"

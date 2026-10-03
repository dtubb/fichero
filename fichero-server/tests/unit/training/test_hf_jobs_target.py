"""Hugging Face Jobs as a place to train (#5398), with `HfApi` replaced at the boundary.

The real run needs a token with Jobs permission; these pin what Fichero SENDS and how it reads the
answers, which is all Fichero owns.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from fichero_server.training import hf_jobs
from fichero_server.training.hf_jobs import HfJobsTarget, NoHuggingFaceToken


class FakeApi:
    """Records every call; answers like the service."""

    def __init__(self, stage: str = "RUNNING") -> None:
        self.calls: list[tuple[str, tuple, dict]] = []
        self.stage = stage

    def _record(self, name, *args, **kwargs):
        self.calls.append((name, args, kwargs))

    def whoami(self, **kw):
        self._record("whoami", **kw)
        return {"name": "historian"}

    def list_jobs_hardware(self, **kw):
        self._record("list_jobs_hardware", **kw)
        return [SimpleNamespace(name="t4-small", unit_cost_usd=0.000667, unit_label="minute"),
                SimpleNamespace(name="a100-large", unit_cost_usd=0.0415, unit_label="minute")]

    def create_bucket(self, *a, **kw):
        self._record("create_bucket", *a, **kw)

    def sync_bucket(self, *a, **kw):
        self._record("sync_bucket", *a, **kw)

    def run_uv_job(self, *a, **kw):
        self._record("run_uv_job", *a, **kw)
        return SimpleNamespace(id="job-123")

    def inspect_job(self, **kw):
        self._record("inspect_job", **kw)
        return SimpleNamespace(status=SimpleNamespace(stage=SimpleNamespace(value=self.stage), message="out of memory"))

    def fetch_job_logs(self, **kw):
        self._record("fetch_job_logs", **kw)
        return iter(["epoch 3 val_accuracy 0.91\n", "stage: done\n"])

    def cancel_job(self, **kw):
        self._record("cancel_job", **kw)


def _called(api, name):
    return [c for c in api.calls if c[0] == name]


def test_the_token_comes_from_fichero_and_a_missing_one_says_where_to_add_it(monkeypatch):
    """WHY (`compute.secret.never-in-a-recipe`): the only token is the one the person gave Fichero for
    Hugging Face. With none, the refusal must say where to add it, not fail inside the client."""
    monkeypatch.setattr("fichero_server.llm.get_api_key", lambda provider: None)
    with pytest.raises(NoHuggingFaceToken, match="Settings"):
        HfJobsTarget(api=FakeApi())
    monkeypatch.setattr("fichero_server.llm.get_api_key", lambda provider: "hf_x" if provider == "huggingface" else None)
    assert HfJobsTarget(api=FakeApi()).token == "hf_x"


def test_data_goes_to_a_private_bucket_of_the_persons_own_account():
    """WHY: page images of an archive leave this Mac only into the person's own private storage, one
    folder per job, so two jobs never mix their sets."""
    api = FakeApi()
    target = HfJobsTarget(token="hf_x", api=api)
    target.send("/tmp/set", "job-a")

    (_, args, kwargs), = _called(api, "create_bucket")
    assert args == ("historian/fichero-training",) and kwargs["private"] is True
    (_, args, _), = _called(api, "sync_bucket")
    assert args == ("/tmp/set", "hf://buckets/historian/fichero-training/job-a/data")


def test_the_job_runs_fichero_s_trainer_with_an_explicit_time_limit_and_the_bucket_mounted():
    """WHY: the service ends a Job at 30 minutes unless told; a Kraken run takes longer, so a limit is
    always sent. The trainer is Fichero's own script, reading and writing the job's folders."""
    api = FakeApi()
    far_id = HfJobsTarget(token="hf_x", api=api).submit("job-a", base_file="medium.safetensors", model_name="sergio")

    assert far_id == "job-123"
    (_, args, kwargs), = _called(api, "run_uv_job")
    assert args == (str(hf_jobs.TRAINER),) and kwargs["timeout"] == hf_jobs.DEFAULT_TIMEOUT
    assert kwargs["flavor"] == "t4-small" and kwargs["labels"] == {"fichero-job": "job-a"}
    assert kwargs["script_args"][:4] == ["--data", "/work/job-a/data", "--out", "/work/job-a/out"]
    (volume,) = kwargs["volumes"]
    assert (volume.type, volume.source, volume.mount_path) == ("bucket", "historian/fichero-training", "/work")
    with pytest.raises(ValueError, match="time limit"):
        HfJobsTarget(token="hf_x", api=api).submit("job-b", base_file=None, model_name="x", timeout="")


def test_the_price_is_read_from_the_service_per_hour():
    """WHY (`compute.job.costs-shown-where-known`): the person sees what an hour costs before sending;
    the service lists it per minute, and an unlisted flavour has no price rather than a guessed one."""
    target = HfJobsTarget(token="hf_x", api=FakeApi())
    assert target.price_per_hour("t4-small") == pytest.approx(0.04)
    assert target.price_per_hour("h100-x8") is None


@pytest.mark.parametrize("stage, state", [("SCHEDULING", "waiting"), ("RUNNING", "running"),
                                          ("COMPLETED", "done"), ("ERROR", "failed"), ("CANCELED", "cancelled")])
def test_the_services_stages_read_as_job_states(stage, state):
    """WHY: a job row has one vocabulary; the service's stages map onto it, and its message (the
    reason a Job failed) is kept."""
    status = HfJobsTarget(token="hf_x", api=FakeApi(stage)).status("job-123")
    assert (status.state, status.stage, status.message) == (state, stage, "out of memory")


def test_the_output_comes_home_from_the_jobs_own_folder(tmp_path):
    api = FakeApi()
    HfJobsTarget(token="hf_x", api=api).fetch("job-a", tmp_path / "out")
    (_, args, _), = _called(api, "sync_bucket")
    assert args == ("hf://buckets/historian/fichero-training/job-a/out", str(tmp_path / "out"))


def test_every_call_carries_the_token_and_nothing_else_does():
    """WHY (`compute.package.no-secrets`): the token goes to the API client only; it is never an
    argument of the script, a label or a path, where it would be stored on the Job."""
    api = FakeApi()
    target = HfJobsTarget(token="hf_secret", api=api)
    target.send("/tmp/set", "job-a")
    target.submit("job-a", base_file=None, model_name="m")
    for name, args, kwargs in api.calls:
        assert kwargs.get("token") == "hf_secret", name
        visible = repr(args) + repr({k: v for k, v in kwargs.items() if k != "token"})
        assert "hf_secret" not in visible, name

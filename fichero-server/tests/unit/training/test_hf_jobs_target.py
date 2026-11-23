"""Hugging Face Jobs as a place to train (#5398), with `HfApi` replaced at the boundary.

The real run needs a token with Jobs permission; these pin what Fichero SENDS and how it reads the
answers, which is all Fichero owns.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from fichero_server.training import hf_jobs
from fichero_server.training import job as training_job
from fichero_server.training.hf_jobs import HfJobsTarget, NoHuggingFaceToken
from tests.unit.training.test_training_job import (  # noqa: F401,F811  (fixtures)
    FakeHub, _subject, full_size_notebook, isolated,
)
from tests.unit.training.test_kraken_training_set import TEACHER as TEACHERS


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

    def list_jobs(self, **kw):
        self._record("list_jobs", **kw)
        job = lambda i, key, stage: SimpleNamespace(  # noqa: E731
            id=i, labels={"fichero-job": key}, status=SimpleNamespace(stage=SimpleNamespace(value=stage), message=None))
        return [job("a", "read-1", "COMPLETED"), job("b", "read-1", "ERROR"), job("c", "other", "RUNNING"),
                SimpleNamespace(id="d", labels=None, status=SimpleNamespace(stage="RUNNING", message=None))]


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
    far_id = HfJobsTarget(token="hf_x", api=api).submit(
        "job-a", script_args=hf_jobs.kraken_args("job-a", base_file="medium.safetensors", model_name="sergio"))

    assert far_id == "job-123"
    (_, args, kwargs), = _called(api, "run_uv_job")
    assert args == (str(hf_jobs.TRAINER),) and kwargs["timeout"] == hf_jobs.DEFAULT_TIMEOUT
    assert kwargs["flavor"] == "t4-small" and kwargs["labels"] == {"fichero-job": "job-a"}
    assert kwargs["script_args"][:4] == ["--data", "/work/job-a/data", "--out", "/work/job-a/out"]
    (volume,) = kwargs["volumes"]
    assert (volume.type, volume.source, volume.mount_path) == ("bucket", "historian/fichero-training", "/work")
    with pytest.raises(ValueError, match="time limit"):
        HfJobsTarget(token="hf_x", api=api).submit("job-b", script_args=[], timeout="")


def test_the_vision_lora_runs_on_the_cheapest_gpu_that_fits():
    """WHY: an A10G and an L4 both fit a 7B LoRA in bf16; the person pays for the cheaper, read from
    the service's own list, not a name fixed in code that may cost more next month."""
    api = FakeApi()
    api.list_jobs_hardware = lambda **kw: [SimpleNamespace(name="a10g-large", unit_cost_usd=0.025, unit_label="minute"),
                                           SimpleNamespace(name="l4x1", unit_cost_usd=0.0133, unit_label="minute"),
                                           SimpleNamespace(name="a10g-small", unit_cost_usd=0.0167, unit_label="minute")]
    target = HfJobsTarget(token="hf_x", api=api)
    assert target.cheapest(hf_jobs.LORA_FLAVORS) == "l4x1"
    with pytest.raises(ValueError, match="listed"):
        target.cheapest(("h100-x8",))


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
    target.submit("job-a", script_args=hf_jobs.kraken_args("job-a", base_file=None, model_name="m"))
    for name, args, kwargs in api.calls:
        assert kwargs.get("token") == "hf_secret", name
        visible = repr(args) + repr({k: v for k, v in kwargs.items() if k != "token"})
        assert "hf_secret" not in visible, name


def test_every_shard_of_one_job_is_seen_in_one_call_and_carries_its_label():
    """WHY (`compute.job.poll-is-gentle`, `.array-by-shard`): a reading run of a hundred shards asks
    Hugging Face once a round, and finds its own Jobs by the `fichero-job` label, never another job's."""
    api = FakeApi()
    target = HfJobsTarget(token="hf_x", api=api)
    target.submit("read-1", script_args=["--shard", "3"], labels={"fichero-shard": "3"}, dependencies=["torch"])
    sent = _called(api, "run_uv_job")[0][2]
    assert sent["labels"] == {"fichero-shard": "3", "fichero-job": "read-1"} and sent["dependencies"] == ["torch"]
    seen = target.statuses("read-1")
    assert {k: v.state for k, v in seen.items()} == {"a": hf_jobs.DONE, "b": hf_jobs.FAILED}
    assert len(_called(api, "list_jobs")) == 1


# --- a LoRA recipe file drives the Job; the adapter always returns, the merged model only when asked
# (`compute.tune.lora`, `compute.tune.adapter-always-returns`; no Job is submitted, the Hub is replaced) ---

def test_a_lora_recipe_file_drives_the_jobs_arguments(tmp_path):
    from fichero_server.training import lora_recipe

    path = tmp_path / "student.lora.json"
    path.write_text('{"rank": 8, "learning_rate": 3e-05, "epochs": 3, "prompt_form": "why"}', encoding="utf-8")
    recipe = lora_recipe.load(path)
    args = hf_jobs.lora_args("job-9", base_repo="Qwen/Qwen3-VL-8B-Instruct", **recipe.job_options())
    assert args[args.index("--rank") + 1] == "8" and args[args.index("--lr") + 1] == "3e-05"
    assert args[args.index("--epochs") + 1] == "3" and args[args.index("--arm") + 1] == "why"
    assert "--merged" not in args  # the adapter alone, unless the merged model is asked for
    assert "--merged" in hf_jobs.lora_args("job-9", base_repo="x", epochs=1, rank=2, merged=True)
    for bad, words in (('{"rank": 8}', "learning_rate"), ('{"rank": 8, "learning_rate": 0, "epochs": 1, "prompt_form": "answer"}', "learning_rate"),
                       ('{"rank": 8, "learning_rate": 1e-4, "epochs": 1, "prompt_form": "poem"}', "prompt_form")):
        path.write_text(bad, encoding="utf-8")
        with pytest.raises(ValueError, match=words):
            lora_recipe.load(path)


@pytest.mark.usefixtures("project_says_yes")
def test_the_recipe_file_reaches_the_submitted_job(db, full_size_notebook, tmp_path, monkeypatch):
    from fichero_server.training import mlx_landing
    from fichero_server.training.job import TrainVisionLoraRequest

    recipe = tmp_path / "r.lora.json"
    recipe.write_text('{"rank": 8, "learning_rate": 3e-05, "epochs": 3, "prompt_form": "answer"}', encoding="utf-8")
    monkeypatch.setattr(mlx_landing, "land_vision_student", lambda *a, **k: "fichero-trained/x")
    monkeypatch.setattr(training_job.jobs, "run_on_lane_blocking", lambda lib, kind, subject, *, model, fn: fn())
    hub = FakeHub()
    request = TrainVisionLoraRequest(scope_ids=[full_size_notebook.folder.id], teacher=TEACHERS, name="x", pages_may_leave=True,
                                     held_out_ids=[full_size_notebook.test_page.id], recipe_file=str(recipe))
    started = training_job.start(db, request, started_by="historian", target_factory=lambda: hub)
    training_job.run(db, _subject(db, started["job_id"]), target=hub, sleep=lambda s: None)
    args = hub.submitted[0]["script_args"]
    assert args[args.index("--rank") + 1] == "8" and args[args.index("--lr") + 1] == "3e-05"
    assert args[args.index("--epochs") + 1] == "3"
    assert "--merged" in args  # the MLX conversion asks for the merged model


def test_the_result_package_holds_the_adapter_and_the_merged_model_only_when_asked(tmp_path):
    from fichero_server.training import lora_recipe

    out = tmp_path / "out"
    for part in ("adapter", "merged"):
        (out / part).mkdir(parents=True)
        (out / part / "w.safetensors").write_bytes(b"x")
    (out / "train.log").write_text("log", encoding="utf-8")
    assert lora_recipe.result_package(out, merged=False) == ["adapter/w.safetensors", "train.log"]
    assert lora_recipe.result_package(out, merged=True) == ["adapter/w.safetensors", "merged/w.safetensors", "train.log"]
    for gone in ("adapter",):
        import shutil

        shutil.rmtree(out / gone)
    with pytest.raises(FileNotFoundError, match="adapter"):
        lora_recipe.result_package(out, merged=False)

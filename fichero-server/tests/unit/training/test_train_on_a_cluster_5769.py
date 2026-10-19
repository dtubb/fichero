"""Training a Kraken reader on a cluster, as one job row (#5769, `source.onboard.cluster-offer`).

WHY: the cluster was offered beside Hugging Face as the free alternative, with nothing that could train there. The
same training loop now drives a Slurm cluster: the set goes to the run's folder, one GPU job runs Fichero's own trainer
in the server image, and the reader comes home. The login node is a fake; the row, the set and the landing are real.
"""
from __future__ import annotations

import shutil
import tarfile

import pytest

from fichero_server.execution import jobs
from fichero_server.llm import kraken_runtime as kr
from fichero_server.training import job as training_job
from tests.unit.training.test_training_job import _request, _subject, isolated, notebook  # noqa: F401

RUNS = "project/def-lab/u/fichero/runs"


class FakeLogin:
    """A login node: `sbatch` "trains" (writes a model into the run's out/ and tars it, as the script's last line
    does), `sacct` says it finished, `tail` gives the log's last lines."""

    def __init__(self, root, state="COMPLETED"):
        self.root, self.state, self.scripts = root, state, []

    def _at(self, remote):
        return self.root / remote.lstrip("/")

    def run(self, argv):
        if argv[0] == "mkdir":
            for d in argv[2:]:
                self._at(d).mkdir(parents=True, exist_ok=True)
        elif argv[0] == "sbatch":
            script = self._at(argv[-1])
            self.scripts.append(script.read_text())
            run_dir = script.parent.parent
            if self.state == "COMPLETED":
                (run_dir / "out").mkdir(exist_ok=True)
                (run_dir / "out" / "sergio_best.safetensors").write_bytes(b"trained on the cluster")
                with tarfile.open(run_dir / "out.tar", "w") as tar:
                    tar.add(run_dir / "out", arcname=".")
            return 0, "201;rorqual\n", ""
        elif argv[0] == "sacct":
            return 0, f"201|{self.state}\n", ""
        elif argv[0] == "tail":
            return 0, "epoch 3 val_accuracy 0.91\nCUDA error: out of memory\n", ""
        elif argv[0] == "rm":
            shutil.rmtree(self._at(argv[-1]), ignore_errors=True)
        return 0, "", ""

    def put(self, local, remote):
        self._at(remote).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(local, self._at(remote))

    def put_text(self, text, remote):
        self._at(remote).parent.mkdir(parents=True, exist_ok=True)
        self._at(remote).write_text(text)

    def get(self, remote, local):
        shutil.copy2(self._at(remote), local)


def _target(tmp_path, state="COMPLETED"):
    from fichero_server.remote_read.slurm_target import SlurmTrainTarget
    from fichero_server.workflows.remote_jobs import HpcClusterConfig

    cluster = HpcClusterConfig(cluster_id="r", name="Rorqual", host_alias="rorqual", username="u",
                               remote_base_dir="/project/def-lab/u", account="def-lab")
    shell = FakeLogin(tmp_path / "login", state)
    return SlurmTrainTarget(cluster, shell), shell


def test_a_kraken_reader_trains_on_a_cluster_and_comes_home(db, notebook, tmp_path):  # noqa: F811
    target, shell = _target(tmp_path)
    started = training_job.start(db, _request(notebook, target="r"), started_by="historian",
                                 target_factory=lambda: target)
    assert started["price_per_hour_usd"] is None  # an allocation is not bought by the hour
    assert jobs.read_job(db, started["job_id"])["reason"] == "Waiting to send to Rorqual"
    reader = training_job.run(db, _subject(db, started["job_id"]), target=target, sleep=lambda s: None)

    job_id = started["job_id"]
    (script,) = shell.scripts
    assert "#SBATCH --gres=gpu:1" in script and "#SBATCH --account=def-lab" in script
    assert "--bind /project/def-lab/u/fichero/runs:/work" in script
    assert f"/work/{job_id}/_fichero/hf_kraken_train.py" in script and f"--data /work/{job_id}/data" in script
    status = training_job.status(db, job_id)
    assert status["yes"]["to"] == "r" and status["reader_id"] == reader
    card = kr.trained_reader_card(reader)
    assert card["target"] == "r" and card["far_id"] == "201"
    # the project never said the copies may stay: the run's folder leaves the cluster with the reader home
    assert not (tmp_path / "login" / RUNS / job_id).exists()


def test_a_failed_cluster_job_says_why_with_the_logs_last_lines(db, notebook, tmp_path):  # noqa: F811
    target, _shell = _target(tmp_path, state="FAILED")
    started = training_job.start(db, _request(notebook, target="r"), started_by="historian",
                                 target_factory=lambda: target)
    with pytest.raises(RuntimeError, match="Rorqual.*out of memory"):
        training_job.run(db, _subject(db, started["job_id"]), target=target, sleep=lambda s: None)


def test_a_cluster_with_no_key_is_refused_by_name_before_anything_is_queued(db, notebook):  # noqa: F811
    from fichero_server.remote_read.slurm_target import NoKey

    with pytest.raises(NoKey, match="r"):
        training_job.start(db, _request(notebook, target="r"), started_by="historian")
    assert db.execute_fetchone("SELECT count(*) FROM jobs WHERE kind = ?", [training_job.KIND])[0] == 0


def test_a_cluster_training_row_says_where_it_runs_and_is_never_set_aside(db, notebook, tmp_path):  # noqa: F811
    """Review 111: the row's target is the cluster, not Hugging Face, so Activity names where it runs; and like a Job
    on Hugging Face it is never set aside for the engine's restarts, since the job runs there whatever happens here."""
    target, _shell = _target(tmp_path)
    job_id = training_job.start(db, _request(notebook, target="r"), started_by="historian",
                                target_factory=lambda: target)["job_id"]
    assert db.execute_fetchone("SELECT target FROM jobs WHERE id = ?", [job_id])[0] == "r"
    db.execute("UPDATE jobs SET state = 'running', attempts = ? WHERE id = ?", [jobs.MAX_ATTEMPTS + 2, job_id])
    jobs.resume(db)
    assert db.execute_fetchone("SELECT state FROM jobs WHERE id = ?", [job_id])[0] != "failed"


def test_nothing_leaves_for_a_cluster_without_a_yes_and_the_refusal_names_it(db, notebook):  # noqa: F811
    from fichero_server.training.job import PagesMayNotLeave

    with pytest.raises(PagesMayNotLeave, match="the cluster r") as refused:
        training_job.start(db, _request(notebook, target="r", pages_may_leave=False), started_by="historian")
    assert "Hugging Face" not in str(refused.value)

"""SlurmTarget against a fake login shell (`compute.hpc.slurm-target`, `compute.hpc.status-from-sacct`)."""
from __future__ import annotations

import pytest

from fichero_server.remote_read.slurm_target import SlurmError, SlurmTarget, parse_sacct
from fichero_server.workflows.remote_jobs import HpcClusterConfig

RORQUAL = HpcClusterConfig(cluster_id="r", name="Rorqual", host_alias="rorqual", username="u",
                           remote_base_dir="/project/def-lab/u", account="def-lab")


class FakeShell:
    def __init__(self, answers=None):
        self.ran, self.files, self.answers = [], {}, answers or {}

    def run(self, argv):
        self.ran.append(argv)
        return self.answers.get(argv[0], (0, "", ""))

    def put(self, local, remote):
        self.files[remote] = local.read_bytes()

    def put_text(self, text, remote):
        self.files[remote] = text.encode()

    def get(self, remote, local):
        local.write_bytes(self.files[remote])


def test_sacct_rows_become_one_status_per_task_in_words():
    """WHY (`compute.hpc.status-from-sacct`, `compute.hpc.failure-states-in-words`): a pending array is ONE
    row for all its tasks; a finished one has a row each; TIMEOUT and OOM say what happened."""
    found = parse_sacct("77_[3-4%2]|PENDING\n77_0|COMPLETED\n77_1|TIMEOUT\n77_2|CANCELLED by 1000\n77_5|OUT_OF_MEMORY\nnoise\n")
    assert [found[f"77_{i}"].state for i in range(6)] == ["done", "failed", "cancelled", "waiting", "waiting", "failed"]
    assert "out of time" in found["77_1"].message and "memory" in found["77_5"].message


def test_a_package_is_sent_submitted_polled_once_and_fetched(tmp_path):
    """WHY (the loop `read-at-scale` runs): send puts the tars, submit returns the array id from `--parsable`,
    one sacct call covers every task, and a shard's results come home by name."""
    (tmp_path / "shards").mkdir()
    (tmp_path / "shards" / "shard-00000.tar").write_bytes(b"tar")
    (tmp_path / "job.json").write_text("{}")
    shell = FakeShell({"sbatch": (0, "4242;rorqual\n", ""), "sacct": (0, "4242_0|RUNNING\n4242_1|PENDING\n", "")})
    target = SlurmTarget(RORQUAL, shell)
    remote = target.send(tmp_path, "job-1")
    assert shell.files[f"{remote}/shards/shard-00000.tar"] == b"tar" and f"{remote}/job.json" in shell.files
    array = target.submit("job-1", script="#!/bin/bash\n")
    assert array == "4242" and shell.files[f"{remote}/_fichero/read.sbatch"] == b"#!/bin/bash\n"
    seen = target.statuses(array)
    assert seen["4242_0"].state == "running" and seen["4242_1"].state == "waiting"
    assert [a for a in shell.ran if a[0] == "sacct"] == [["sacct", "-j", "4242", "-X", "-P", "-n", "-o", "JobID,State"]]
    shell.files[f"{remote}/out/shard-00000.tar"] = b"results"
    assert (target.fetch_part("job-1", "shard-00000", tmp_path / "home") / "shard-00000.tar").read_bytes() == b"results"
    assert target.price_per_hour("any") is None


def test_a_refused_command_is_named_not_swallowed():
    """WHY (rule 0, raise not fall back): a failed sbatch says what the cluster said."""
    target = SlurmTarget(RORQUAL, FakeShell({"sbatch": (1, "", "Invalid account")}))
    with pytest.raises(SlurmError, match="Invalid account"):
        target.submit("job-1", script="x")

"""A training job longer than its time limit (`compute.tune.survives-the-time-limit`, `compute.hpc.resume-long-training`):
the warning signal makes the trainer checkpoint, the job re-queues itself, and the next part resumes with no repeated step."""
from __future__ import annotations

import os
import signal
import stat
import subprocess
import time

from fichero_server.training.resumable import part_words, training_sbatch, wrapper_script
from fichero_server.workflows.remote_jobs import HpcClusterConfig, SlurmJobConfig

# A stub trainer: steps 1..12 at 0.1 s; on USR1 it saves the step it reached and exits; `--resume F` continues.
TRAINER = """#!/bin/bash
step=0; log="$1"; shift
if [ "$1" = "--resume" ]; then step=$(cat "$2"); fi
trap 'echo $step > "$CKPT"; exit 0' USR1
while [ $step -lt 12 ]; do step=$((step+1)); echo "step $step" >> "$log"; sleep 0.1; done
echo $step > "$CKPT"; echo done >> "$log"
"""
SCONTROL = """#!/bin/sh
echo "$@" >> "$FAKE_BIN/requeued"
"""


def _setup(tmp_path):
    (tmp_path / "bin").mkdir()
    for name, text in (("trainer", TRAINER), ("scontrol", SCONTROL)):
        f = tmp_path / "bin" / name
        f.write_text(text)
        f.chmod(f.stat().st_mode | stat.S_IEXEC)
    wrapper = tmp_path / "resumable.sh"
    wrapper.write_text(wrapper_script())
    return wrapper


def _run(tmp_path, wrapper, restart, kill_after=None):
    env = {**os.environ, "PATH": f"{tmp_path}/bin:{os.environ['PATH']}", "FAKE_BIN": f"{tmp_path}/bin",
           "CKPT": str(tmp_path / "last.ckpt"), "FICHERO_CKPT": str(tmp_path / "last.ckpt"),
           "SLURM_RESTART_COUNT": str(restart), "SLURM_JOB_ID": "77"}
    proc = subprocess.Popen(["bash", str(wrapper), "--", "trainer", str(tmp_path / "steps.log")], env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if kill_after:
        time.sleep(kill_after)
        proc.send_signal(signal.SIGUSR1)  # Slurm's --signal=B:USR1@N
    out, _ = proc.communicate(timeout=30)
    return proc.returncode, out


def test_the_run_completes_across_two_parts_with_no_repeated_step(tmp_path):
    wrapper = _setup(tmp_path)
    code, out = _run(tmp_path, wrapper, restart=0, kill_after=0.5)
    assert code == 0 and "part 1" in out
    assert (tmp_path / "bin" / "requeued").read_text().strip() == "requeue 77"
    code, out = _run(tmp_path, wrapper, restart=1)
    assert code == 0 and "part 2" in out
    steps = [line for line in (tmp_path / "steps.log").read_text().splitlines() if line.startswith("step")]
    assert steps == [f"step {i}" for i in range(1, 13)]  # 1..12, once each
    assert (tmp_path / "steps.log").read_text().rstrip().endswith("done")
    assert not (tmp_path / "bin" / "requeued").read_text().count("requeue") > 1  # the finished part did not requeue


def test_the_sbatch_asks_for_the_warning_signal_and_requeue_and_the_row_reads_the_part():
    cluster = HpcClusterConfig(cluster_id="r", name="Rorqual", host_alias="rorqual", username="u",
                               remote_base_dir="/project/def-lab/u", account="def-lab")
    script = training_sbatch(cluster, SlurmJobConfig(job_name="ketos", gpus=1, account="def-lab"),
                             ["ketos", "train", "-f", "page"], run_id="run-1")
    assert "#SBATCH --requeue" in script and "--signal=B:USR1@" in script
    assert "resumable.sh" in script and "ketos train -f page" in script.replace("'", "")
    assert part_words(0) == "running (part 1)" and part_words(1) == "running (part 2)"

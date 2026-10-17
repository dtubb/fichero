"""A training job that outlives its time limit (`compute.tune.survives-the-time-limit`, `compute.hpc.resume-long-training`).

Slurm sends SIGUSR1 a few minutes before the limit (`--signal=B:USR1@N`). The wrapper forwards it to the trainer, which
checkpoints and exits; the wrapper then re-queues the SAME job id (`scontrol requeue`), and the next part starts the
trainer again with `--resume <checkpoint>`: no step repeated. `SLURM_RESTART_COUNT` says which part this is.
"""
from __future__ import annotations

from fichero_server.workflows.remote_jobs import HpcClusterConfig, SlurmJobConfig, build_slurm_script

#: Shipped beside the package as `_fichero/resumable.sh`. The trainer must checkpoint on SIGUSR1 and take `--resume`.
_WRAPPER = r"""#!/usr/bin/env bash
# usage: resumable.sh -- <trainer command...>
ckpt="${FICHERO_CKPT:-out/last.ckpt}"
shift
restarts="${SLURM_RESTART_COUNT:-0}"
max="${FICHERO_MAX_RESTARTS:-5}"
# `--requeue` also re-queues after a crash; a count stops a broken trainer looping, and says so
if [ "$restarts" -gt "$max" ]; then echo "gave up after $restarts restarts (more than $max)"; exit 1; fi
echo "part $(( restarts + 1 ))"
args=("$@")
if [ -f "$ckpt" ]; then args+=(--resume "$ckpt"); fi
before=$(cksum < "$ckpt" 2>/dev/null)
warned=0
on_warning() { warned=1; kill -USR1 "$child" 2>/dev/null; }
trap on_warning USR1
"${args[@]}" &
child=$!
wait "$child"; status=$?
while kill -0 "$child" 2>/dev/null; do wait "$child"; status=$?; done
if [ "$warned" = 1 ]; then
  if [ "$restarts" -ge "$max" ]; then echo "gave up: the part limit ($max restarts) is reached, not re-queuing"; exit 1; fi
  # re-queue only if the trainer stopped cleanly AND left a new checkpoint; else fail where it can be seen
  after=$(cksum < "$ckpt" 2>/dev/null)
  if [ "$status" -ne 0 ] || [ -z "$after" ] || [ "$after" = "$before" ]; then
    echo "not re-queuing: the trainer stopped with status $status and no new checkpoint"; exit 1
  fi
  scontrol requeue "$SLURM_JOB_ID"; exit 0
fi
exit "$status"
"""


def wrapper_script() -> str:
    return _WRAPPER


def part_words(restart_count: int) -> str:
    """The job row's words: `running (part 2)` after one re-queue."""
    return f"running (part {restart_count + 1})"


def training_sbatch(cluster: HpcClusterConfig, config: SlurmJobConfig, trainer_argv: list[str], *, run_id: str) -> str:
    """The sbatch script of a resumable training job: `--requeue`, the warning signal, the wrapper around the trainer."""
    return build_slurm_script(config=config, remote_workdir=cluster.remote_workdir(run_id),
                              runner_command=["bash", "_fichero/resumable.sh", "--", *trainer_argv])

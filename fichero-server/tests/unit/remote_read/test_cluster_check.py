"""The live cluster check (`compute.connect.check-really-checks`): each step passed, failed with its reason, or
not tried; `ok` only when every step passed just now."""
from __future__ import annotations

from fichero_server.remote_read.cluster_check import check_cluster


class Shell:
    def __init__(self, answers):
        self.answers, self.ran = answers, []

    def run(self, argv):
        self.ran.append(argv[0])
        return self.answers.get(argv[0], (0, f"{argv[0]} answered\n", ""))


def test_every_step_passes_and_ok_is_true():
    result = check_cluster(Shell({"sinfo": (0, "gpu|up|h100:4\n", "")}))
    assert result["ok"] is True
    assert [s["name"] for s in result["steps"]] == ["hostname", "storage", "apptainer", "gpus", "fair share"]
    assert all(s["state"] == "passed" for s in result["steps"]) and result["steps"][3]["answer"] == "gpu|up|h100:4"


def test_a_stopped_scheduler_fails_that_step_with_its_reason_and_ok_is_false():
    result = check_cluster(Shell({"sinfo": (1, "", "slurm_load_partitions: Unable to contact slurm controller")}))
    by = {s["name"]: s for s in result["steps"]}
    assert by["hostname"]["state"] == "passed" and result["ok"] is False
    assert by["gpus"]["state"] == "failed" and "Unable to contact" in by["gpus"]["answer"]


def test_nothing_is_tried_when_the_login_itself_fails():
    result = check_cluster(Shell({"hostname": (255, "", "Permission denied (publickey)")}))
    assert result["ok"] is False and result["steps"][0]["state"] == "failed"
    assert all(s["state"] == "not tried" for s in result["steps"][1:])


def test_apptainer_is_asked_through_a_login_shell_where_module_exists():
    """WHY (review 41): `module` is a shell function of a login shell, and it answers on stderr."""
    shell = Shell({})
    check_cluster(shell)
    assert "bash" in shell.ran

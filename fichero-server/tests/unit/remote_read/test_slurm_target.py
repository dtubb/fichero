"""SlurmTarget against a fake login shell (`compute.hpc.slurm-target`, `compute.hpc.status-from-sacct`)."""
from __future__ import annotations

import pytest

from fichero_server.remote_read.slurm_target import SlurmError, SlurmReadTarget, SlurmTarget, parse_sacct
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


def test_ssh_shell_runs_through_the_system_ssh_with_one_reused_connection_and_refuses_without_a_key(tmp_path):
    """WHY (`compute.connect.one-connection-reused`, no new dependency): the system ssh gets the key, a
    ControlPath and the quoted command; a missing key is refused by name."""
    import stat

    from fichero_server.remote_read.slurm_target import NoKey, SshShell

    with pytest.raises(NoKey, match="no key"):
        SshShell(RORQUAL, tmp_path / "none", tmp_path)
    key = tmp_path / "id"
    key.write_text("k")
    fake = tmp_path / "fakessh"
    fake.write_text('#!/bin/sh\nprintf "%s\\n" "$@" > "$0.args"\ncat > "$0.stdin"\necho out\n')
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    shell = SshShell(RORQUAL, key, tmp_path, ssh=str(fake))
    assert shell.run(["tail", "-n", "5", "a b"]) == (0, "out\n", "")
    args = (tmp_path / "fakessh.args").read_text().splitlines()
    assert "ControlMaster=auto" in args and "IdentitiesOnly=yes" in args and args[-2] == "u@rorqual"
    assert args[-1] == "tail -n 5 'a b'"
    shell.put_text("hello", "/r/x")
    assert (tmp_path / "fakessh.stdin").read_text() == "hello"


def test_ssh_shell_puts_double_dash_before_the_destination_and_streams_files(tmp_path):
    """WHY (security): a host starting with "-" must never be read by ssh as an option; first contact
    accepts a new host key without a prompt; files stream through stdin/stdout, not memory."""
    import stat

    from fichero_server.remote_read.slurm_target import SshShell

    key = tmp_path / "id"
    key.write_text("k")
    fake = tmp_path / "fakessh"
    fake.write_text('#!/bin/sh\nprintf "%s\\n" "$@" > "$0.args"\ncat > "$0.stdin"\necho out\n')
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    shell = SshShell(RORQUAL, key, tmp_path, ssh=str(fake))
    shell.run(["true"])
    args = (tmp_path / "fakessh.args").read_text().splitlines()
    assert args[-3:] == ["--", "u@rorqual", "true"]
    assert "BatchMode=yes" in args and "StrictHostKeyChecking=accept-new" in args
    src = tmp_path / "src.bin"
    src.write_bytes(b"payload")
    shell.put(src, "/r/x")
    assert (tmp_path / "fakessh.stdin").read_bytes() == b"payload"
    dst = tmp_path / "dst.bin"
    shell.get("/r/x", dst)
    assert dst.read_bytes() == b"out\n"


@pytest.mark.parametrize("field,bad", [("host_alias", "-oProxyCommand=touch x"), ("host_alias", "a b"),
                                       ("username", "-oProxyCommand=x"), ("username", "u@h"), ("username", "")])
def test_cluster_create_refuses_option_shaped_host_or_username(field, bad):
    """WHY (security): a value reaching ssh as an argument must not be an option; FastAPI turns this into a 422."""
    from pydantic import ValidationError

    from fichero_server.api.routes.ai.hpc import HpcClusterCreate

    ok = dict(name="n", host_alias="rorqual.alliancecan.ca", username="u-1.x_y", remote_base_dir="/r")
    HpcClusterCreate(**ok)
    with pytest.raises(ValidationError):
        HpcClusterCreate(**{**ok, field: bad})


def _sent_package(tmp_path, shell):
    import json

    pkg = tmp_path / "pkg"
    (pkg / "shards").mkdir(parents=True)
    (pkg / "shards" / "shard-00001.tar").write_bytes(b"t")
    (pkg / "job.json").write_text(json.dumps({"shards": [[0], [1]], "sources": [{"id": "a"}, {"id": "b"}]}))
    target = SlurmReadTarget(RORQUAL, shell)
    target.send(pkg, "job-1")
    return target


def test_the_read_loop_runs_one_single_task_sbatch_per_shard_and_reads_them_in_one_sacct(tmp_path):
    """WHY (`read-at-scale` target=cluster): job.py submits a shard at a time (max_in_flight throttles), a shard's
    id is Slurm's `<job>_<task>`, one sacct covers every shard sent, and the shard's tar of results lands as the
    folder `land()` expects."""
    shell = FakeShell({"sbatch": (0, "77;rorqual\n", ""), "sacct": (0, "77_1|COMPLETED\n", "")})
    target = _sent_package(tmp_path, shell)
    far = target.submit("job-1", script="ignored", flavor="t4-small", timeout="2h", script_args=[],
                        labels={"fichero-shard": "1"})
    assert far == "77_1"
    script = shell.files[f"{target._dir('job-1')}/_fichero/read-1.sbatch"].decode()
    assert "#SBATCH --array=1" in script and "--time=02:00:00" in script and "tar -C out/shard-00001" in script
    assert target.statuses("job-1")["77_1"].state == "done"
    assert [a for a in shell.ran if a[0] == "sacct"] == [["sacct", "-j", "77", "-X", "-P", "-n", "-o", "JobID,State"]]
    import io
    import tarfile

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        info = tarfile.TarInfo("_outcome.json")
        info.size = 2
        tar.addfile(info, io.BytesIO(b"{}"))
    shell.files[f"{target._dir('job-1')}/out/shard-00001.tar"] = buf.getvalue()
    folder = target.fetch_part("job-1", "shard-00001", tmp_path / "home")
    assert (folder / "_outcome.json").read_text() == "{}"


def test_iiif_pages_are_fetched_on_this_mac_into_the_package_before_it_is_sent_never_on_a_login_node(tmp_path,
                                                                                                    monkeypatch):
    """WHY (`compute.hpc.nothing-heavy-on-a-login-node`; compute nodes have no internet): a package of IIIF pages is
    filled on this Mac, politely, before it leaves, so the pages travel in it; the cluster fetches nothing."""
    import json

    from fichero_server.remote_read import runner

    pkg = tmp_path / "pkg"
    (pkg / "shards").mkdir(parents=True)
    (pkg / "job.json").write_text(json.dumps({"shards": [[0]], "sources": [{"id": "a", "iiif_service": "https://x/a"}]}))
    fetched = []

    def prefetch(package, *, get=None):
        fetched.append(package)
        (package / "images").mkdir(exist_ok=True)
        (package / runner.prefetched({"id": "a"})).write_bytes(b"jpeg")
        return {"failed": {}}

    monkeypatch.setattr(runner, "prefetch", prefetch)
    shell = FakeShell()
    SlurmReadTarget(RORQUAL, shell).send(pkg, "job-1")
    assert fetched == [pkg]
    assert any(remote.endswith("images/iiif-a.jpg") for remote in shell.files), "the page travels in the package"
    assert not [a for a in shell.ran if "--prefetch" in " ".join(a)], "nothing fetched on the login node"


def test_a_package_with_no_iiif_pages_is_sent_as_it_is(tmp_path, monkeypatch):
    from fichero_server.remote_read import runner

    monkeypatch.setattr(runner, "prefetch", lambda *a, **k: pytest.fail("nothing to fetch"))
    _sent_package(tmp_path, FakeShell())

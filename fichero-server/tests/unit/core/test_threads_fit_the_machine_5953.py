"""`source.read.threads-fit-the-machine` (#5953, #5931): one rule gives the cores a run may use, from the machine it runs on:
Slurm's cpus per task, the container's cgroup quota, a Mac's performance cores, else the process's allowed CPUs; torch threads
per pipeline are the cores divided by the pipelines; the numbers chosen are written in the run's Activity details; the
host's `os.cpu_count` is never a thread count."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from fichero_server.core import cores


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.delenv("SLURM_CPUS_PER_TASK", raising=False)
    # cgroup_cores binds its paths as default arguments when it is defined, so patching the module's path constants changes
    # nothing: fake the source itself, never read this machine's cgroup (a Mac has none, a container host has one).
    monkeypatch.setattr(cores, "cgroup_cores", lambda: None)
    monkeypatch.setattr(cores, "sysctl_int", lambda name: None)


def _sysctl(monkeypatch, **values):
    monkeypatch.setattr(cores, "sysctl_int", lambda name: values.get(name))


@pytest.mark.parametrize("sysctl, expected", [
    ({"hw.perflevel0.physicalcpu": 4, "hw.physicalcpu": 8}, 4),
    ({"hw.perflevel0.physicalcpu": 10, "hw.physicalcpu": 14}, 10),
    ({"hw.physicalcpu": 8}, 4),                                    # Intel: no performance levels, half the physical cores
    ({"hw.physicalcpu": 2}, 1),
    ({"hw.perflevel0.physicalcpu": 0, "hw.physicalcpu": 6}, 3),    # a level that reads zero is no level
    ({"hw.perflevel0.physicalcpu": -1, "hw.physicalcpu": 8}, 4),
    ({"hw.perflevel0.physicalcpu": None, "hw.physicalcpu": 8}, 4),
    ({"hw.physicalcpu": -4}, None),                                # no usable count: not a Mac reading
    ({"hw.physicalcpu": 0}, None),
    ({}, None),
])
def test_a_macs_cores_are_its_performance_cores_else_half_the_physical_ones(monkeypatch, sysctl, expected):
    _sysctl(monkeypatch, **sysctl)
    assert cores.mac_performance_cores() == expected


def test_the_source_order_is_slurm_then_the_container_then_the_mac_then_the_allowed_cpus(monkeypatch):
    _sysctl(monkeypatch, **{"hw.perflevel0.physicalcpu": 4, "hw.physicalcpu": 8})
    assert cores.cores_available() == (4, "mac-performance-cores")
    monkeypatch.setattr(cores, "cgroup_cores", lambda: 2)
    assert cores.cores_available() == (2, "cgroup")
    monkeypatch.setenv("SLURM_CPUS_PER_TASK", "6")
    assert cores.cores_available() == (6, "slurm")


@pytest.mark.parametrize("text, expected", [
    ("200000 100000\n", 2), ("150000 100000\n", 2),   # rounded up
    ("50000 100000\n", 1),                            # a fraction of a core is one
    ("max 100000\n", None),                           # no quota
    ("garbage", None), ("", None)])
def test_the_container_quota_is_quota_over_period_rounded_up_and_max_is_none(tmp_path, text, expected):
    path = tmp_path / "cpu.max"
    path.write_text(text)
    assert cores.cgroup_cores(v2=path, v1_quota=tmp_path / "no", v1_period=tmp_path / "no") == expected


def test_a_version_one_cgroup_is_read_too_and_minus_one_is_no_quota(tmp_path):
    quota, period = tmp_path / "q", tmp_path / "p"
    period.write_text("100000\n")
    quota.write_text("300000\n")
    assert cores.cgroup_cores(v2=tmp_path / "none", v1_quota=quota, v1_period=period) == 3
    quota.write_text("-1\n")
    assert cores.cgroup_cores(v2=tmp_path / "none", v1_quota=quota, v1_period=period) is None


@pytest.mark.parametrize("value", ["0", "-2", "many", ""])
def test_a_slurm_value_that_is_not_a_positive_number_is_ignored(monkeypatch, value):
    monkeypatch.setenv("SLURM_CPUS_PER_TASK", value)
    assert cores.cores_available()[1] != "slurm"


def test_with_nothing_to_go_by_it_is_the_allowed_cpus_never_the_hosts(monkeypatch):
    monkeypatch.setattr(cores.os, "sched_getaffinity", lambda pid: {0, 1, 2}, raising=False)
    assert cores.cores_available() == (3, "affinity")
    monkeypatch.delattr(cores.os, "sched_getaffinity", raising=False)
    assert cores.cores_available() == (1, "none")


def test_every_thread_count_is_built_from_the_cores_available(monkeypatch):
    from fichero_server.core import background_compute as bc
    from fichero_server.core import compute_preferences

    monkeypatch.setattr(cores, "cores_available", lambda: (8, "slurm"))
    monkeypatch.setattr(bc, "set_fast_qos", lambda: None)
    monkeypatch.delenv("FICHERO_EMBED_THREADS", raising=False)
    assert bc.cpu_count() == 8 and bc.embed_threads() == 4
    assert compute_preferences.apply_to_this_thread("fast") == 8


def test_torch_threads_per_pipeline_are_the_cores_over_the_pipelines_never_below_one():
    for available, pipelines, threads in ((8, 1, 8), (8, 2, 4), (8, 4, 2), (8, 8, 1), (8, 16, 1), (1, 3, 1)):
        assert max(1, available // max(1, pipelines)) == threads


def test_the_numbers_chosen_are_written_in_the_activity_details(monkeypatch):
    from fichero_server.execution import jobs
    from fichero_server.llm import kraken_runtime as kr

    notes = []
    monkeypatch.setattr(cores, "cores_available", lambda: (4, "mac-performance-cores"))
    monkeypatch.setattr(jobs, "note_call_log", lambda message, **kw: notes.append(message))
    kr._note_threads_chosen(2, 2)
    assert notes == ["Threads: 2 torch threads a page; 4 cores available (mac-performance-cores), 2 pages at once"]


def test_no_thread_number_is_taken_from_the_hosts_cpu_count():
    """Guard: `os.cpu_count` appears only in `background_compute.host_cpu_count` (Activity's machine figure, display), never in
    a number that sizes threads or pipelines."""
    src = Path(cores.__file__).parent.parent
    offenders = []
    for path in src.rglob("*.py"):
        rel = str(path.relative_to(src))
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Attribute) and node.attr == "cpu_count" and getattr(node.value, "id", "") == "os":
                offenders.append(rel)
    assert offenders == ["core/background_compute.py"], offenders


def test_the_real_sysctl_answers_an_integer_or_nothing_and_never_starts_a_process(monkeypatch):
    """sysctlbyname through ctypes: a sandboxed app cannot exec `sysctl` (#4555)."""
    import subprocess

    monkeypatch.undo()
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: pytest.fail("started a child process"))
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: pytest.fail("started a child process"))
    assert cores.sysctl_int("hw.no.such.name") is None
    count, source = cores.cores_available()
    assert isinstance(count, int) and count >= 1 and source

"""How many cores a run may use, from the machine it runs on (`source.read.threads-fit-the-machine`, #5953, #5931).

One rule, never `os.cpu_count` (that is the HOST's cores: 128 inside a container limited to 4, every core of a Slurm node
a job was given two of):

* under Slurm (ACENet), the cores the job was given: `SLURM_CPUS_PER_TASK`;
* in a container (Hugging Face Jobs), the cgroup quota: `cpu.max` (v2) or `cpu.cfs_quota_us` / `cpu.cfs_period_us` (v1)
  as quota / period, rounded up; `max` or -1 is no quota;
* on a Mac, the performance cores (`hw.perflevel0.physicalcpu`), else half of `hw.physicalcpu` (an Intel Mac has no
  performance levels); the efficiency cores stay for the app and the person;
* otherwise the CPUs this process is allowed (`sched_getaffinity`), else one.
"""

from __future__ import annotations

import ctypes
import math
import os
import sys
from pathlib import Path

CGROUP_V2 = Path("/sys/fs/cgroup/cpu.max")
CGROUP_V1_QUOTA = Path("/sys/fs/cgroup/cpu/cpu.cfs_quota_us")
CGROUP_V1_PERIOD = Path("/sys/fs/cgroup/cpu/cpu.cfs_period_us")


def sysctl_int(name: str) -> int | None:
    """An integer `hw.*` value through sysctlbyname (ctypes, no child process: a sandboxed app cannot start one, #4555);
    None where the name does not exist (Intel Macs have no performance levels) or off macOS."""
    if sys.platform != "darwin":
        return None
    try:
        libc = ctypes.CDLL("libc.dylib", use_errno=True)
        value, size = ctypes.c_int32(0), ctypes.c_size_t(ctypes.sizeof(ctypes.c_int32))  # the hw.*cpu values are ints
        if libc.sysctlbyname(name.encode(), ctypes.byref(value), ctypes.byref(size), None, 0) != 0:
            return None
        return int(value.value)
    except (OSError, AttributeError):
        return None


def mac_performance_cores() -> int | None:
    """The Mac's performance cores, else half its physical cores; None off a Mac. Never below one."""
    cores = sysctl_int("hw.perflevel0.physicalcpu")
    if cores is None or cores < 1:
        physical = sysctl_int("hw.physicalcpu")
        if physical is None or physical < 1:
            return None
        cores = physical // 2
    return max(1, cores)


def _positive_int(text: str | None) -> int | None:
    try:
        value = int(str(text).strip())
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def cgroup_cores(v2: Path = CGROUP_V2, v1_quota: Path = CGROUP_V1_QUOTA, v1_period: Path = CGROUP_V1_PERIOD) -> int | None:
    """The container's CPU quota in cores (quota / period, rounded up), None when there is none."""
    try:
        quota, period = v2.read_text(encoding="utf-8").split()[:2]
    except (OSError, ValueError):
        try:
            quota, period = v1_quota.read_text(encoding="utf-8").strip(), v1_period.read_text(encoding="utf-8").strip()
        except OSError:
            return None
    q, p = _positive_int(quota), _positive_int(period)  # "max" and -1 are no quota
    return max(1, math.ceil(q / p)) if q and p else None


def cores_available() -> tuple[int, str]:
    """(the cores a run may use, where that number came from)."""
    slurm = _positive_int(os.environ.get("SLURM_CPUS_PER_TASK"))
    if slurm:
        return slurm, "slurm"
    cgroup = cgroup_cores()
    if cgroup:
        return cgroup, "cgroup"
    mac = mac_performance_cores()
    if mac:
        return mac, "mac-performance-cores"
    try:
        return max(1, len(os.sched_getaffinity(0))), "affinity"
    except (AttributeError, OSError):
        return 1, "none"


def is_a_mac_pipeline_host(source: str) -> bool:
    """Whether the cores are a Mac's: pages are read side by side only there; a cluster task reads one page pipeline and
    gets its parallelism from array tasks (`source.read.pages-at-once-scales`)."""
    return source == "mac-performance-cores"

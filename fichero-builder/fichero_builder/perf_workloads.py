"""The performance sweep's workload table and machine tags (#6600 Step 3: `perf-sweep.workload.set`, `perf-sweep.source.machines`).

`harness.toml [perf.workloads]` declares ten fixed workloads (w1..w5 engine, w6..w10 app); `[perf.machines.<name>]` declares where
profiling may run (`tags`) and which tools may use sudo there. Both are read, never probed: a table with a missing field is refused
naming the workload, and a profile is placed only on a machine whose tags say it may be."""
from __future__ import annotations

from fichero_builder import perf_corpus

NAMES = tuple(f"w{i}" for i in range(1, 11))
SIDE_OF = {n: "engine" if i < 5 else "app" for i, n in enumerate(NAMES)}
FIELDS = ("side", "driver", "corpus", "outputs", "budget_s")


def load(rules: dict, manifest: dict) -> list[dict]:
    """The ten workloads in order, each with `drivers` (a list). ValueError names the workload and the field that is missing
    or points at a corpus the manifest does not declare."""
    table = rules.get("perf", {}).get("workloads", {})
    corpora = {e["name"] for e in perf_corpus.load(manifest)}
    out = []
    for n in NAMES:
        w = table.get(n)
        if w is None:
            raise ValueError(f"[perf.workloads]: {n} is not declared")
        for f in FIELDS:
            if w.get(f) in (None, "", [], 0):
                raise ValueError(f"[perf.workloads].{n}: {f} is required")
        if w["side"] != SIDE_OF[n]:
            raise ValueError(f"[perf.workloads].{n}: side is {SIDE_OF[n]}")
        if w["corpus"] not in corpora:
            raise ValueError(f"[perf.workloads].{n}: corpus {w['corpus']} is not in the manifest")
        out.append({"name": n, **w, "drivers": [w["driver"]] if isinstance(w["driver"], str) else list(w["driver"])})
    if extra := sorted(set(table) - set(NAMES)):
        raise ValueError(f"[perf.workloads]: {extra} are not workloads")
    return out


def machine_tags(rules: dict) -> dict[str, dict]:
    return {n: {"tags": list(m.get("tags", [])), "sudo": list(m.get("sudo", []))} for n, m in rules.get("perf", {}).get("machines", {}).items()}


def place(rules: dict, side: str) -> tuple[str | None, str | None]:
    """(machine, None) for the first declared machine that may run this side, or (None, reason). No `profile` machine at all is a
    refusal naming the tag; an app profile needs `gui` as well, and without one it is `not-run`, never a silent skip."""
    machines = machine_tags(rules)
    prof = [n for n, m in machines.items() if "profile" in m["tags"]]
    if not prof:
        raise ValueError("no [perf.machines] entry has the `profile` tag: the sweep refuses to profile")
    if side == "app":
        gui = [n for n in prof if "gui" in machines[n]["tags"]]
        return (gui[0], None) if gui else (None, "not-run: no GUI machine")
    return prof[0], None


def py_spy_allowed(rules: dict, machine: str) -> bool:
    return "py-spy" in machine_tags(rules).get(machine, {}).get("sudo", [])

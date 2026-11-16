"""The one-run overrides of a cloud refusal (`ai.cloud.one-run-overrides`, #6349, #6350): "allow cloud once" and "run past the cap
once" apply to the calls of ONE run, are written to no project or app setting, and end with the run. Keyed by the run's id, which
every node of the run carries (`node_context`), so the gate and the spend hold find them from inside the run."""

from __future__ import annotations

import threading

_LOCK = threading.Lock()
_RUNS: dict[str, dict[str, bool]] = {}


def set_for_run(run_id: str, *, allow_cloud: bool = False, over_cap: bool = False) -> None:
    """Record the run's overrides; nothing is kept for a run that asked for none."""
    with _LOCK:
        if allow_cloud or over_cap:
            _RUNS[run_id] = {"allow_cloud": allow_cloud, "over_cap": over_cap}
        else:
            _RUNS.pop(run_id, None)


def clear(run_id: str) -> None:
    with _LOCK:
        _RUNS.pop(run_id, None)


def for_run(run_id: str | None) -> dict[str, bool]:
    with _LOCK:
        return dict(_RUNS.get(run_id or "", {}))


def _current_run() -> str | None:
    from fichero_server.workflows.node_context import get_current_node

    node = get_current_node()
    return (node.run_id or None) if node else None


def allows_cloud() -> bool:
    """The call under way belongs to a run that was told "allow cloud once"."""
    return bool(for_run(_current_run()).get("allow_cloud"))


def over_cap() -> bool:
    """The call under way belongs to a run that was told "run past the cap once"."""
    return bool(for_run(_current_run()).get("over_cap"))

"""A failed run said in words, with the fix and the command that does each action (`run.fail.cli-says-the-fix`, #6354): the engine
serves `failure` (`llm/failure.py`: kind, words, fix, actions); the CLI prints the words, `Fix: <fix>`, then each action as the
command or flag that does it. Never a traceback. A cloud refusal keeps its own words and exit code 3 (`cloud_refusal`)."""

from __future__ import annotations

from typing import Any

EXIT_CODE = 1


def of(payload: Any) -> dict[str, Any] | None:
    """The `failure` of a run's status or job (a model or a dict) when the run failed, else None."""
    if hasattr(payload, "model_dump"):
        payload = payload.model_dump(mode="json")
    if not isinstance(payload, dict) or payload.get("status") not in ("failed", None, "paused"):
        return None
    failure = payload.get("failure")
    return failure if isinstance(failure, dict) and failure.get("kind") else None


def _line(action: dict[str, Any], failure: dict[str, Any], run_id: str) -> str | None:
    kind, control = action.get("kind"), action.get("control")
    if kind in ("retry", "resume"):
        wait = action.get("retry_after_seconds")
        after = f" (the provider asked for {wait:.0f} seconds first)" if wait else ""
        return f"run it again{after}: fichero activity-api retry-job {run_id}"
    if kind == "open-settings":
        if control == "settings.ai.providers":
            return "check the key: fichero providers set-api-key <provider> --api-key <key>, or change it in the app (Settings > AI > Providers)"
        return f"or change it in the app: Settings > AI ({control})"
    if kind == "choose-model":
        return "run it with another model: fichero workflow run <workflow> <documents> --model <provider>/<model>"
    if kind == "report-bug":
        return f"send a bug report: fichero activity-api post-job-bug-report {run_id}"
    if kind == "reconnect":
        return "reconnect the folder in the app, then run it again"
    return None


def words(failure: dict[str, Any], run_id: str) -> str:
    """The failure as text: what happened, `Fix: <fix>`, then each way on, the bug report first for a bug in Fichero."""
    lines = [str(failure.get("words") or "The run stopped."), f"Fix: {failure.get('fix')}"]
    actions = list(failure.get("actions") or [])
    if failure.get("kind") == "unexpected":
        actions.sort(key=lambda a: a.get("kind") != "report-bug")  # a stable sort: the bug report first, the rest as served
    ways = [line for action in actions if (line := _line(action, failure, run_id))]
    if ways:
        lines.append("Ways on:")
        lines += [f"  - {line}" for line in ways]
    return "\n".join(lines)

"""Thin AppleScript wrapper for programmatic Fichero UI navigation (#1133)."""

from __future__ import annotations

import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

Runner = Callable[..., subprocess.CompletedProcess[str]]

VALID_PANELS = {"library", "inspector", "kg", "activity"}


@dataclass(slots=True)
class AppleScriptError(RuntimeError):
    """Raised when `osascript` rejects a Fichero UI command."""

    command: str
    returncode: int
    stderr: str

    def __str__(self) -> str:
        return f"osascript failed ({self.returncode}) for {self.command}: {self.stderr}"


def open_library(path: str | Path, *, app: str = "Fichero", runner: Runner | None = None) -> str:
    """Open or focus a `.fichero` library."""

    return _run(_tell(app, f"open library {_quote(str(path))}"), runner=runner)


def select_document(
    document_id: str,
    *,
    app: str = "Fichero",
    runner: Runner | None = None,
) -> str:
    """Select a document by backend document id in the active library window."""

    if not document_id:
        raise ValueError("document_id is required")
    return _run(_tell(app, f"select document id {_quote(document_id)}"), runner=runner)


def show_panel(panel: str, *, app: str = "Fichero", runner: Runner | None = None) -> str:
    """Show one of: library, inspector, kg, activity."""

    normalized = panel.strip().lower()
    if normalized not in VALID_PANELS:
        raise ValueError(f"panel must be one of {sorted(VALID_PANELS)}")
    return _run(_tell(app, f"show panel {_quote(normalized)}"), runner=runner)


def navigate(
    *,
    panel: str | None = None,
    document_id: str | None = None,
    library_path: str | Path | None = None,
    app: str = "Fichero",
    runner: Runner | None = None,
) -> list[str]:
    """Convenience wrapper for agents: open library, select doc, show panel."""

    outputs: list[str] = []
    if library_path is not None:
        outputs.append(open_library(library_path, app=app, runner=runner))
    if document_id is not None:
        outputs.append(select_document(document_id, app=app, runner=runner))
    if panel is not None:
        outputs.append(show_panel(panel, app=app, runner=runner))
    return outputs


def _run(script: str, *, runner: Runner | None = None) -> str:
    run = runner or subprocess.run
    result = run(
        ["osascript", "-e", script],
        capture_output=True,
        check=False,
        text=True,
    )
    if result.returncode != 0:
        raise AppleScriptError(script, result.returncode, result.stderr.strip())
    return result.stdout.strip()


def _tell(app: str, command: str) -> str:
    return f"tell application {_quote(app)} to {command}"


def _quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


__all__: Sequence[str] = (
    "AppleScriptError",
    "navigate",
    "open_library",
    "select_document",
    "show_panel",
)

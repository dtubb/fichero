"""The app's UI verbs as MCP tools, over AppleScript (#5453, `openapi.ui.mcp-reaches-the-verbs`).

Each function runs one command of the app's AppleScript dictionary (`fichero/fichero/Fichero.sdef`)
through ``osascript``; the command calls the same method the click calls. So an agent that changed
something through the engine tools can open it, show it and take a picture of it, the way a person
would see it. Mac only: osascript drives the running app on this machine.

The ``ui`` toolset (``--toolsets ui``) lists ``UI_TOOLS``. The app is ``Fichero`` unless
``FICHERO_UI_APP`` names another (a name, or a path to a built ``.app``).
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

Runner = Callable[..., subprocess.CompletedProcess[str]]

#: The panes `show pane` and `screenshot ... of pane` accept (`UIPane` in the app).
PANES = ("library", "preview", "reader", "inspector", "activity", "chat", "segments")

#: The toolset name the MCP server lists these under.
TOOLSET = "ui"


@dataclass(slots=True)
class AppleScriptError(RuntimeError):
    """Raised when `osascript` rejects a Fichero UI command."""

    command: str
    returncode: int
    stderr: str

    def __str__(self) -> str:
        return f"osascript failed ({self.returncode}) for {self.command}: {self.stderr}"


def open_project(path: str | Path, *, app: str | None = None, runner: Runner | None = None) -> str:
    """Open a .fichero project in the front window, as File > Open does. Returns the project's id."""

    return _run(_tell(app, f"open project {_quote(str(path))}"), runner=runner)


def open_node(node_id: str, *, app: str | None = None, runner: Runner | None = None) -> bool:
    """Open a node (a page, document or folder) by id, as clicking it does."""

    return _bool(_run(_tell(app, f"open node {_quote(_required(node_id, 'node_id'))}"), runner=runner))


def select_nodes(node_ids: Sequence[str], *, app: str | None = None, runner: Runner | None = None) -> bool:
    """Select nodes in the Library by id, as clicking (and command-clicking) them does."""

    return _bool(_run(_tell(app, f"select nodes {_list(node_ids, 'node_ids')}"), runner=runner))


def reveal_segments(
    segment_ids: Sequence[str],
    page_id: str,
    *,
    app: str | None = None,
    runner: Runner | None = None,
) -> list[str]:
    """Select segments in the Preview showing their page and zoom to them, as clicking a line in the Reader does.

    Returns the segment ids revealed: none when no Preview shows the page (open the page first).
    """

    script = f"reveal segments {_list(segment_ids, 'segment_ids')} in page {_quote(_required(page_id, 'page_id'))}"
    out = _run(_tell(app, script), runner=runner)
    return [part.strip() for part in out.split(",") if part.strip()]


def show_pane(pane: str, *, app: str | None = None, runner: Runner | None = None) -> bool:
    """Show a pane in the front window: library, preview, reader, inspector, activity, chat or segments."""

    return _bool(_run(_tell(app, f"show pane {_quote(_pane(pane))}"), runner=runner))


def show_inspector_tab(tab: str, *, app: str | None = None, runner: Runner | None = None) -> bool:
    """Show the Inspector at a tab (Content, Artifacts, Entities, Knowledge Graph, Info, ...), as clicking it does."""

    return _bool(_run(_tell(app, f"show inspector tab {_quote(_required(tab, 'tab'))}"), runner=runner))


def screenshot(
    path: str | Path,
    pane: str | None = None,
    *,
    app: str | None = None,
    runner: Runner | None = None,
) -> str:
    """Save a picture of the front window, or of one pane, as a PNG at ``path``. Returns the path written.

    The app draws its own window, so no screen-recording permission is involved. Use it to check what
    a change looks like, and for documentation screenshots (``docs/assets/<milestone>/``).
    """

    command = f"screenshot {_quote(str(path))}"
    if pane is not None:
        command += f" of pane {_quote(_pane(pane))}"
    return _run(_tell(app, command), runner=runner)


def fichero_ui_open_project(path: str) -> str:
    """Open a .fichero project in the app's front window, as File > Open does. Returns the project's id."""
    return open_project(path)


def fichero_ui_open_node(node_id: str) -> bool:
    """Open a node (a page, document or folder) in the app by its id, as clicking it does."""
    return open_node(node_id)


def fichero_ui_select_nodes(node_ids: list[str]) -> bool:
    """Select nodes in the app's Library by id, as clicking them does."""
    return select_nodes(node_ids)


def fichero_ui_reveal_segments(segment_ids: list[str], page_id: str) -> list[str]:
    """Reveal segments (lines) in the app's Preview of their page: selected and zoomed to.

    Returns the ids revealed; none when no Preview shows the page, so open the page first
    (`fichero_ui_open_node`).
    """
    return reveal_segments(segment_ids, page_id)


def fichero_ui_show_pane(pane: str) -> bool:
    """Show a pane in the app's front window: library, preview, reader, inspector, activity, chat or segments."""
    return show_pane(pane)


def fichero_ui_show_inspector_tab(tab: str) -> bool:
    """Show the app's Inspector at a tab: Content, Artifacts, Annotations, Notes, Interpretation, Entities,
    Knowledge Graph, Citations, Related, Edits or Info."""
    return show_inspector_tab(tab)


def fichero_ui_screenshot(path: str, pane: str | None = None) -> str:
    """Save a PNG of the app's front window, or of one pane (library, preview, reader, inspector, activity,
    chat, segments), at an absolute path. Returns the path written. Use it to check on screen what a
    change did, and for documentation screenshots."""
    return screenshot(path, pane)


#: The ``ui`` toolset: (tool name, function).
UI_TOOLS: tuple[tuple[str, Callable[..., Any]], ...] = tuple(
    (fn.__name__, fn)
    for fn in (
        fichero_ui_open_project,
        fichero_ui_open_node,
        fichero_ui_select_nodes,
        fichero_ui_reveal_segments,
        fichero_ui_show_pane,
        fichero_ui_show_inspector_tab,
        fichero_ui_screenshot,
    )
)


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


def _tell(app: str | None, command: str) -> str:
    return f"tell application {_quote(app or os.environ.get('FICHERO_UI_APP') or 'Fichero')} to {command}"


def _quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _list(values: Sequence[str], name: str) -> str:
    if isinstance(values, str) or not values or not all(values):
        raise ValueError(f"{name} must be a non-empty list of ids")
    return "{" + ", ".join(_quote(v) for v in values) + "}"


def _required(value: str, name: str) -> str:
    if not value:
        raise ValueError(f"{name} is required")
    return value


def _pane(pane: str) -> str:
    normalized = pane.strip().lower()
    if normalized == "reading":
        normalized = "reader"
    if normalized not in PANES:
        raise ValueError(f"pane must be one of {list(PANES)}")
    return normalized


def _bool(out: str) -> bool:
    return out.strip().lower() == "true"


__all__: Sequence[str] = (
    "AppleScriptError",
    "PANES",
    "TOOLSET",
    "UI_TOOLS",
    "open_node",
    "open_project",
    "reveal_segments",
    "screenshot",
    "select_nodes",
    "show_inspector_tab",
    "show_pane",
)

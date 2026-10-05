"""The app's UI verbs as MCP tools (#5453, `openapi.ui.mcp-reaches-the-verbs`).

Each tool must build the AppleScript command `fichero/fichero/Fichero.sdef` declares, quoted so an
id or path can never break out of its string, and the `ui` toolset must list every tool. osascript is
replaced by a recording runner; the app side is pinned by the Swift `UIVerbsTests`.
"""

from __future__ import annotations

import asyncio
import re
import subprocess
from pathlib import Path

import pytest
from mcp.server.fastmcp import FastMCP

from fichero_mcp import server as mcp_server
from fichero_mcp import ui_control

SDEF = Path(__file__).resolve().parents[2] / "fichero" / "fichero" / "Fichero.sdef"


class RecordingRunner:
    def __init__(self, *, returncode: int = 0, stdout: str = "true\n", stderr: str = ""):
        self.calls: list[list[str]] = []
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr

    def __call__(self, args, **_kwargs):
        self.calls.append(list(args))
        return subprocess.CompletedProcess(args=args, returncode=self.returncode, stdout=self.stdout, stderr=self.stderr)

    @property
    def scripts(self) -> list[str]:
        return [call[2] for call in self.calls]


@pytest.fixture(autouse=True)
def _default_app(monkeypatch):
    monkeypatch.delenv("FICHERO_UI_APP", raising=False)


def test_each_verb_builds_the_applescript_command_the_dictionary_declares() -> None:
    """WHY: a tool whose script names a command the dictionary does not declare fails only at run
    time, on the maintainer's machine; every verb here must be one the sdef declares, with its
    arguments in the shape the command reads."""
    runner = RecordingRunner()
    ui_control.open_project("/tmp/Test Project.fichero", runner=runner)
    ui_control.open_node("doc-1", runner=runner)
    ui_control.select_nodes(["doc-1", "doc-2"], runner=runner)
    ui_control.reveal_segments(["seg-1"], "doc-1", runner=runner)
    ui_control.show_pane("Reading", runner=runner)
    ui_control.show_inspector_tab("Knowledge Graph", runner=runner)
    ui_control.screenshot("/tmp/shot.png", runner=runner)
    ui_control.screenshot("/tmp/preview.png", "preview", runner=runner)

    assert runner.scripts == [
        'tell application "Fichero" to open project "/tmp/Test Project.fichero"',
        'tell application "Fichero" to open node "doc-1"',
        'tell application "Fichero" to select nodes {"doc-1", "doc-2"}',
        'tell application "Fichero" to reveal segments {"seg-1"} in page "doc-1"',
        'tell application "Fichero" to show pane "reader"',
        'tell application "Fichero" to show inspector tab "Knowledge Graph"',
        'tell application "Fichero" to screenshot "/tmp/shot.png"',
        'tell application "Fichero" to screenshot "/tmp/preview.png" of pane "preview"',
    ]
    declared = set(re.findall(r'<command name="([^"]+)"', SDEF.read_text(encoding="utf-8")))
    assert len(declared) > 10, "the sdef scan found implausibly few commands"
    used = {"open project", "open node", "select nodes", "reveal segments", "show pane", "show inspector tab", "screenshot"}
    assert used <= declared, used - declared
    assert 'name="in page"' in SDEF.read_text(encoding="utf-8") and 'name="of pane"' in SDEF.read_text(encoding="utf-8")


def test_ids_and_paths_are_quoted_so_they_cannot_break_out() -> None:
    """WHY: an id or path with a quote or backslash must stay one AppleScript string, never become script."""
    runner = RecordingRunner()
    ui_control.select_nodes(['doc-"quoted"', "a\\b"], runner=runner)
    assert runner.scripts == ['tell application "Fichero" to select nodes {"doc-\\"quoted\\"", "a\\\\b"}']


def test_a_bad_pane_or_empty_ids_are_refused_without_running_osascript() -> None:
    """WHY: a typo must say what would have worked, not reach the app as a silent no-op."""
    runner = RecordingRunner()
    with pytest.raises(ValueError, match="pane must be one of"):
        ui_control.show_pane("settings", runner=runner)
    with pytest.raises(ValueError, match="pane must be one of"):
        ui_control.screenshot("/tmp/x.png", "kg", runner=runner)
    with pytest.raises(ValueError, match="non-empty list"):
        ui_control.select_nodes([], runner=runner)
    with pytest.raises(ValueError, match="non-empty list"):
        ui_control.reveal_segments("seg-1", "doc-1", runner=runner)  # a bare string is not a list of ids
    assert runner.calls == []


def test_results_are_read_back_typed() -> None:
    """WHY: the agent checks what happened from the answer -- the ids revealed (none when no Preview
    shows the page), whether a request was accepted, the path written."""
    assert ui_control.reveal_segments(["s1", "s2"], "d", runner=RecordingRunner(stdout="s1, s2\n")) == ["s1", "s2"]
    assert ui_control.reveal_segments(["s1"], "d", runner=RecordingRunner(stdout="\n")) == []
    assert ui_control.show_pane("library", runner=RecordingRunner(stdout="true\n")) is True
    assert ui_control.screenshot("/tmp/a.png", runner=RecordingRunner(stdout="/tmp/a.png\n")) == "/tmp/a.png"


def test_the_app_can_be_a_built_bundle(monkeypatch) -> None:
    """WHY: a Debug build is driven by its path, so the dev app and an installed one are never confused."""
    monkeypatch.setenv("FICHERO_UI_APP", "/build/Debug/Fichero.app")
    runner = RecordingRunner()
    ui_control.open_node("doc-1", runner=runner)
    assert runner.scripts == ['tell application "/build/Debug/Fichero.app" to open node "doc-1"']


def test_osascript_failure_raises_contextual_error() -> None:
    """WHY: the app's refusal (no window, unknown tab) must reach the agent as an error naming it."""
    runner = RecordingRunner(returncode=1, stderr="Not an Inspector tab: Foo.")
    with pytest.raises(ui_control.AppleScriptError) as exc:
        ui_control.show_inspector_tab("Foo", runner=runner)
    assert exc.value.returncode == 1
    assert "Not an Inspector tab" in str(exc.value)


def test_the_ui_toolset_lists_every_verb_and_only_when_chosen() -> None:
    """WHY (openapi.ui.mcp-reaches-the-verbs): `--toolsets ui` must give an agent every UI verb, with a
    usable schema, and an agent that did not ask for them must not see them."""
    server = FastMCP("ui")
    names = mcp_server.select_toolsets(mcp_server.parse_toolsets("ui"), server)
    expected = {
        "fichero_ui_open_project", "fichero_ui_open_node", "fichero_ui_select_nodes", "fichero_ui_reveal_segments",
        "fichero_ui_show_pane", "fichero_ui_show_inspector_tab", "fichero_ui_screenshot",
    }
    assert expected <= set(names)
    tools = {tool.name: tool for tool in asyncio.run(server.list_tools())}
    assert tools["fichero_ui_reveal_segments"].inputSchema["required"] == ["segment_ids", "page_id"]
    assert tools["fichero_ui_screenshot"].inputSchema["required"] == ["path"]
    assert "ui" in mcp_server.parse_toolsets("all")

    other = FastMCP("hpc")
    assert not expected & set(mcp_server.select_toolsets(["hpc"], other))


def test_a_tool_runs_its_verb(monkeypatch) -> None:
    """WHY: the registered tool must be the verb, not a lookalike: calling it through the MCP server runs
    the osascript the verb builds."""
    runner = RecordingRunner(stdout="/tmp/inspector.png\n")
    monkeypatch.setattr(ui_control.subprocess, "run", runner)
    server = FastMCP("ui")
    mcp_server.select_toolsets(["ui"], server)
    asyncio.run(server.call_tool("fichero_ui_screenshot", {"path": "/tmp/inspector.png", "pane": "inspector"}))
    assert runner.scripts == ['tell application "Fichero" to screenshot "/tmp/inspector.png" of pane "inspector"']

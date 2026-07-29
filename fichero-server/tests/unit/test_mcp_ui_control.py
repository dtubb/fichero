"""Tests for the Fichero AppleScript UI control wrapper (#1133)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from fichero_mcp import ui_control


class RecordingRunner:
    def __init__(self, *, returncode: int = 0, stdout: str = "true\n", stderr: str = ""):
        self.calls: list[list[str]] = []
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr

    def __call__(self, args, **_kwargs):
        self.calls.append(list(args))
        return subprocess.CompletedProcess(
            args=args,
            returncode=self.returncode,
            stdout=self.stdout,
            stderr=self.stderr,
        )


def test_select_document_builds_structured_applescript_command() -> None:
    runner = RecordingRunner()

    ui_control.select_document('doc-"quoted"', runner=runner)

    assert runner.calls == [
        [
            "osascript",
            "-e",
            'tell application "Fichero" to select document id "doc-\\"quoted\\""',
        ]
    ]


def test_navigate_orders_library_document_then_panel() -> None:
    runner = RecordingRunner()

    ui_control.navigate(
        library_path=Path("/tmp/Test Library.fichero"),
        document_id="doc-123",
        panel="inspector",
        runner=runner,
    )

    scripts = [call[2] for call in runner.calls]
    assert scripts == [
        'tell application "Fichero" to open library "/tmp/Test Library.fichero"',
        'tell application "Fichero" to select document id "doc-123"',
        'tell application "Fichero" to show panel "inspector"',
    ]


def test_show_panel_rejects_unknown_panel_without_running_osascript() -> None:
    runner = RecordingRunner()

    with pytest.raises(ValueError, match="panel must be one of"):
        ui_control.show_panel("settings", runner=runner)

    assert runner.calls == []


def test_osascript_failure_raises_contextual_error() -> None:
    runner = RecordingRunner(returncode=1, stderr="Application isn't running")

    with pytest.raises(ui_control.AppleScriptError) as exc:
        ui_control.show_panel("kg", runner=runner)

    assert exc.value.returncode == 1
    assert "Application isn't running" in str(exc.value)

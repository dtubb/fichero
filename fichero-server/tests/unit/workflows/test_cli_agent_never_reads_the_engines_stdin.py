"""A `cli_agent` node never reads the engine's own stdin, and its timeout is a real bound (#5186).

WHY: `claude -p` (like `cat`, like most CLIs) reads a stdin that is not a terminal to EOF before it
answers. The tool gave its child the ENGINE's fd 0; under the app, a launcher or a test runner that
is often a pipe nobody ever closes -- so the child waited for input that could never come and the
node hung for its whole timeout (120 s in the #5186 audit). The task goes on the command line; a
child has nothing to read. If this regresses, a workflow's CLI step hangs whenever the engine was
started with a pipe on stdin.

And the timeout killed only the CLI: anything the CLI had started kept the output pipe open, so
the drain after the kill waited for it -- the node hung past its own timeout (the audit's "hung past
120 s"). If that regresses, a timed-out node never returns at all.

Real subprocesses: a stand-in `claude` on PATH. Each call is bounded from outside, so the old code
fails here instead of hanging the run.
"""

from __future__ import annotations

import asyncio
import os
import stat
import time

import pytest

from fichero_server.llm import LLMConfig
from fichero_server.workflows.tools.cli_agent import cli_agent


def _fake_cli(tmp_path, monkeypatch, script: str) -> None:
    fake = tmp_path / "claude"
    fake.write_text("#!/bin/sh\n" + script)
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ['PATH']}")


async def _ask(timeout_seconds: int) -> dict:
    return await cli_agent({"task": "say hello", "_config": {"cli": "claude", "timeout_seconds": timeout_seconds}},
                           {}, LLMConfig(provider="openai", model="gpt-4o-mini"))


@pytest.mark.asyncio
async def test_the_child_gets_no_stdin_and_answers_at_once(tmp_path, monkeypatch):
    _fake_cli(tmp_path, monkeypatch, "cat > /dev/null\necho answered\n")
    read_end, write_end = os.pipe()              # write_end held open: EOF never comes on it
    saved = os.dup(0)
    os.dup2(read_end, 0)
    try:
        result = await asyncio.wait_for(_ask(5), timeout=15)
    finally:
        os.dup2(saved, 0)
        for fd in (saved, read_end, write_end):
            os.close(fd)
    assert result.get("error") is None, result          # old code: "CLI timed out after 5s"
    assert (result["exit_code"], result["text"]) == (0, "answered")


@pytest.mark.asyncio
async def test_a_timeout_returns_even_when_the_cli_started_something_that_lingers(tmp_path, monkeypatch):
    _fake_cli(tmp_path, monkeypatch, "sleep 60 &\nsleep 60\n")     # a grandchild holding stdout
    started = time.monotonic()
    result = await asyncio.wait_for(_ask(1), timeout=15)
    assert (result["exit_code"], result["error"]) == (124, "CLI timed out after 1s")
    assert time.monotonic() - started < 10                           # bounded by its timeout, not by the grandchild

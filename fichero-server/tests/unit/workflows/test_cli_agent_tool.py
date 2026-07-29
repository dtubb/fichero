import asyncio
from unittest.mock import AsyncMock, Mock, patch

import pytest

from fichero_server.llm import LLMConfig
from fichero_server.workflows.tools.cli_agent import cli_agent
from fichero_server.workflows.types import State


@pytest.mark.asyncio
async def test_cli_agent_runs_claude_and_captures_stdout():
    inputs = {
        "task": "Summarize this text",
        "_config": {"cli": "claude", "timeout_seconds": 30},
    }
    state: State = {}
    llm_config = LLMConfig(provider="openai", model="gpt-4o-mini")

    proc = Mock()
    proc.returncode = 0
    proc.communicate = AsyncMock(return_value=(b"hello from claude\n", b""))

    with patch("fichero_server.workflows.tools.cli_agent.asyncio.create_subprocess_exec", new=AsyncMock(return_value=proc)) as sp:
        result = await cli_agent(inputs, state, llm_config)

    sp.assert_awaited_once()
    args = sp.await_args.args
    assert args[:2] == ("claude", "-p")
    assert "Summarize this text" in args[2]
    assert result["stdout"] == "hello from claude"
    assert result["exit_code"] == 0
    assert "error" not in result


@pytest.mark.asyncio
async def test_cli_agent_runs_codex_with_template():
    inputs = {
        "task": "Refactor this function",
        "context": {"language": "python"},
        "_config": {
            "cli": "codex",
            "prompt_template": "[{cli}] {task}\\nCTX={context}",
        },
    }
    state: State = {}
    llm_config = LLMConfig(provider="openai", model="gpt-4o-mini")

    proc = Mock()
    proc.returncode = 0
    proc.communicate = AsyncMock(return_value=(b"codex output", b""))

    with patch("fichero_server.workflows.tools.cli_agent.asyncio.create_subprocess_exec", new=AsyncMock(return_value=proc)) as sp:
        result = await cli_agent(inputs, state, llm_config)

    args = sp.await_args.args
    assert args[0:2] == ("codex", "exec")
    assert "[codex] Refactor this function" in args[2]
    assert "language" in args[2]
    assert result["text"] == "codex output"


@pytest.mark.asyncio
async def test_cli_agent_timeout_kills_process():
    inputs = {"task": "Long task", "_config": {"cli": "claude", "timeout_seconds": 1}}
    state: State = {}
    llm_config = LLMConfig(provider="openai", model="gpt-4o-mini")

    proc = Mock()
    proc.kill = Mock()
    proc.communicate = AsyncMock(return_value=(b"", b""))

    async def _fake_wait_for(coro, timeout):
        del timeout
        coro.close()
        raise asyncio.TimeoutError

    with patch("fichero_server.workflows.tools.cli_agent.asyncio.create_subprocess_exec", new=AsyncMock(return_value=proc)):
        with patch("fichero_server.workflows.tools.cli_agent.asyncio.wait_for", side_effect=_fake_wait_for):
            result = await cli_agent(inputs, state, llm_config)

    proc.kill.assert_called_once()
    assert result["exit_code"] == 124
    assert "timed out" in result["error"]


@pytest.mark.asyncio
async def test_cli_agent_denied_for_non_owner_under_multiuser(monkeypatch):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    inputs = {"task": "Run host code", "_config": {"cli": "claude"}}
    state: State = {"user": {"is_owner": False}}
    llm_config = LLMConfig(provider="openai", model="gpt-4o-mini")

    with patch("fichero_server.workflows.tools.cli_agent.asyncio.create_subprocess_exec", new=AsyncMock()) as sp:
        result = await cli_agent(inputs, state, llm_config)

    sp.assert_not_awaited()
    assert result["exit_code"] == 126
    assert "requires owner" in result["error"]


@pytest.mark.asyncio
async def test_cli_agent_available_when_multiuser_flag_off(monkeypatch):
    monkeypatch.delenv("FICHERO_MULTIUSER", raising=False)
    monkeypatch.delenv("FICHERO_BIND_HOST", raising=False)
    inputs = {"task": "Summarize this text", "_config": {"cli": "claude"}}
    state: State = {"user": {"is_owner": False}}
    llm_config = LLMConfig(provider="openai", model="gpt-4o-mini")

    proc = Mock()
    proc.returncode = 0
    proc.communicate = AsyncMock(return_value=(b"ok", b""))

    with patch("fichero_server.workflows.tools.cli_agent.asyncio.create_subprocess_exec", new=AsyncMock(return_value=proc)) as sp:
        result = await cli_agent(inputs, state, llm_config)

    sp.assert_awaited_once()
    assert result["stdout"] == "ok"
    assert result["exit_code"] == 0

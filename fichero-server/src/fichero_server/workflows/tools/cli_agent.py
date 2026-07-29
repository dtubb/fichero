"""CLI Agent workflow tool (#341).

Runs a supported local CLI agent command (initially Claude/Codex) and
returns stdout/stderr for downstream workflow nodes.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any

from fichero_server.workflows.registry import register_tool
from fichero_server.workflows.types import DataType, PortDef, State
from fichero_server.llm import LLMConfig

logger = logging.getLogger(__name__)


def _truthy_env(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _networked_deployment() -> bool:
    host = os.getenv("FICHERO_BIND_HOST") or os.getenv("FICHERO_REMOTE_BACKEND_BIND_HOST") or ""
    return host.strip() not in {"", "127.0.0.1", "localhost", "::1"}


def _has_cli_agent_capability(inputs: dict[str, Any], state: State) -> bool:
    config = inputs.get("_config") or {}

    def capability_set(value: Any) -> set[str]:
        if isinstance(value, str):
            return {value}
        return {str(item) for item in (value or [])}

    capability_sources = [
        config.get("capabilities"),
        config.get("user_capabilities"),
        state.get("capabilities"),
        state.get("user_capabilities"),
    ]
    has_capability = any(
        bool({"cli_agent", "workflow.cli_agent"} & capability_set(source))
        for source in capability_sources
    )
    is_owner = bool(
        config.get("is_owner")
        or config.get("owner")
        or state.get("is_owner")
        or state.get("owner")
        or (state.get("actor") or {}).get("is_owner")
        or (state.get("user") or {}).get("is_owner")
    )
    return is_owner or has_capability


def _cli_agent_denied(inputs: dict[str, Any], state: State) -> bool:
    if not (_truthy_env("FICHERO_MULTIUSER") or _networked_deployment()):
        return False
    return not _has_cli_agent_capability(inputs, state)


def _render_prompt(
    cli: str,
    task: str,
    context: Any,
    prompt_template: str | None,
) -> str:
    if prompt_template:
        context_text = context if isinstance(context, str) else json.dumps(context or {}, ensure_ascii=False)
        return prompt_template.format(task=task, context=context_text, cli=cli)
    if context:
        context_text = context if isinstance(context, str) else json.dumps(context, ensure_ascii=False)
        return f"Task:\n{task}\n\nContext:\n{context_text}"
    return task


def _build_command(
    *,
    cli: str,
    prompt: str,
    use_ollama_launch: bool,
    ollama_model: str,
) -> list[str]:
    if use_ollama_launch:
        return ["ollama", "run", ollama_model, prompt]
    if cli == "claude":
        return ["claude", "-p", prompt]
    if cli == "codex":
        return ["codex", "exec", prompt]
    raise ValueError(f"Unsupported cli_agent '{cli}'")


@register_tool(
    name="cli_agent",
    display_name="CLI Agent",
    description="Run a local agent CLI (Claude/Codex) and capture stdout/stderr.",
    category="agent",
    icon="terminal",
    color="indigo",
    uses_llm=False,
    input_ports=[
        PortDef(
            id="task",
            name="Task",
            port_type="input",
            data_type=DataType.TEXT,
            required=True,
            description="Prompt/task for the CLI agent.",
        ),
        PortDef(
            id="context",
            name="Context",
            port_type="input",
            data_type=DataType.ANY,
            required=False,
            description="Optional structured context included in prompt template.",
        ),
    ],
    output_ports=[
        PortDef(id="text", name="Text", port_type="output", data_type=DataType.TEXT),
        PortDef(id="stdout", name="Stdout", port_type="output", data_type=DataType.TEXT),
        PortDef(id="stderr", name="Stderr", port_type="output", data_type=DataType.TEXT),
        PortDef(id="exit_code", name="Exit Code", port_type="output", data_type=DataType.NUMBER),
    ],
    config_schema={
        "cli": {
            "type": "string",
            "enum": ["claude", "codex"],
            "default": "claude",
            "description": "CLI to invoke.",
        },
        "prompt_template": {
            "type": "string",
            "default": "",
            "description": "Template using {task}, {context}, {cli}.",
        },
        "timeout_seconds": {
            "type": "integer",
            "default": 120,
            "description": "Execution timeout in seconds.",
        },
        "use_ollama_launch": {
            "type": "boolean",
            "default": False,
            "description": "Route execution via 'ollama run <model> <prompt>'.",
        },
        "ollama_model": {
            "type": "string",
            "default": "qwen2.5-coder",
            "description": "Model to use when use_ollama_launch=true.",
        },
    },
)
async def cli_agent(
    inputs: dict[str, Any],
    state: State,
    llm_config: LLMConfig,
) -> dict[str, Any]:
    del llm_config
    task = str(inputs.get("task", "")).strip()
    if not task:
        return {
            "error": "No task provided to cli_agent",
            "text": "",
            "stdout": "",
            "stderr": "",
            "exit_code": 1,
        }

    if _cli_agent_denied(inputs, state):
        return {
            "error": "cli_agent requires owner or explicit cli_agent capability in multi-user/networked deployments",
            "text": "",
            "stdout": "",
            "stderr": "",
            "exit_code": 126,
        }

    config = inputs.get("_config") or {}
    cli = str(config.get("cli") or "claude").strip().lower()
    timeout_seconds = int(config.get("timeout_seconds") or 120)
    use_ollama_launch = bool(config.get("use_ollama_launch", False))
    ollama_model = str(config.get("ollama_model") or "qwen2.5-coder")
    prompt_template = (config.get("prompt_template") or "").strip() or None

    prompt = _render_prompt(cli, task, inputs.get("context"), prompt_template)
    command = _build_command(
        cli=cli,
        prompt=prompt,
        use_ollama_launch=use_ollama_launch,
        ollama_model=ollama_model,
    )
    logger.info("cli_agent running: %s", command[0])

    proc = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_seconds)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.communicate()
        return {
            "error": f"CLI timed out after {timeout_seconds}s",
            "text": "",
            "stdout": "",
            "stderr": "",
            "exit_code": 124,
            "command": command,
        }

    stdout_text = (stdout or b"").decode("utf-8", errors="replace").strip()
    stderr_text = (stderr or b"").decode("utf-8", errors="replace").strip()
    exit_code = int(proc.returncode or 0)
    result: dict[str, Any] = {
        "text": stdout_text,
        "stdout": stdout_text,
        "stderr": stderr_text,
        "exit_code": exit_code,
        "command": command,
    }
    if exit_code != 0:
        result["error"] = f"CLI exited with code {exit_code}"
    return result

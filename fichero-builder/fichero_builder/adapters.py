"""The harness adapter interface (agent-profiles.adapter.interface, #6623): six answers, each a value or `Unsupported(reason)`.

An adapter that cannot read a session (no cost cap) or load the index servers cannot take a lane; one with no policy hook
point starts and journals `policy: none (OS jail only)`. Only Claude Code is built here; the others are Stage 3.
"""
from __future__ import annotations

from dataclasses import dataclass

_QUESTIONS = ("system_prompt", "mcp", "model", "permission", "policy", "session_read")


@dataclass(frozen=True)
class Unsupported:
    reason: str


class AdapterRefused(Exception):
    pass


class Adapter:
    name = ""

    def answer(self, question: str):
        raise NotImplementedError


class ClaudeCode(Adapter):
    name = "claude-code"
    harness = "Claude Code"  # the HARNESS words of the trailer
    effort_key = "effortLevel"  # the settings.json key that takes a [models] row's effort (low|medium|high|xhigh)

    def answer(self, question: str):
        return {"system_prompt": "--append-system-prompt <text>", "mcp": "--strict-mcp-config --mcp-config=<scratch>/mcp.json",
                "model": "--model <name>", "permission": "--dangerously-skip-permissions (OS jail)",
                "policy": "PreToolUse hook and commit-msg hook", "session_read": "session.parse_session (Claude Code JSONL)"}[question]


def questions() -> tuple[str, ...]:
    return _QUESTIONS


def get(name: str) -> Adapter:
    adapters = {a.name: a for a in (ClaudeCode(),)}
    if name not in adapters:
        raise AdapterRefused(f"unknown harness {name!r}; known: {', '.join(sorted(adapters))}")
    return adapters[name]


def require_lane_capable(adapter: Adapter) -> None:
    for q, why in (("session_read", "no cost cap"), ("mcp", "no index")):
        ans = adapter.answer(q)
        if isinstance(ans, Unsupported):
            raise AdapterRefused(f"{adapter.name} cannot take a lane ({why}): {ans.reason}")


def policy_line(adapter: Adapter) -> str:
    ans = adapter.answer("policy")
    return "policy: none (OS jail only)" if isinstance(ans, Unsupported) else f"policy: {ans}"

"""What a worker's session file says (dev-workflows.node.worker: one adapter per kind, read from the file, never from the
pane). Ported from pipeline/coder.py 2026-11-01. A Pi JSONL carries a price per turn; a Claude Code JSONL carries none."""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

EMPTY = {"cost_usd": 0.0, "tokens": 0, "tool_calls": Counter(), "idle": False, "last_text": "", "rate_limited": False,
         "model": "", "turns": 0, "prompts": 0, "started": False, "error": "", "transient": False,
         "cache_read": 0, "cache_write": 0, "fresh": 0, "cache_hit": 0.0, "proxy_calls": 0, "context": 0}


def cache_hit(s: dict) -> float:
    """Cached-read tokens over all prompt tokens read this session (the page's hit rate)."""
    total = s["cache_read"] + s["cache_write"] + s["fresh"]
    return round(s["cache_read"] / total, 3) if total else 0.0
QUOTA = re.compile(r"\b(402|429|rate.?limit|usage limit|insufficient|quota|credit)|limit reached|hit your (\w+ )?limit|resets \d", re.I)
TRANSIENT = re.compile(r"\b5\d\d\b|overloaded|timed? ?out|temporarily|connection", re.I)  # passing: back off, then look again


def session_files(session_dir: Path) -> list[Path]:
    return sorted(session_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime) if session_dir.exists() else []



def uses_tools(s: dict, *prefixes: str) -> dict:
    return {p: sum(n for name, n in s["tool_calls"].items() if p in name) for p in prefixes}

def parse_session(path: Path) -> dict:
    """cost_usd, tokens, tool_calls (Counter by name), turns (assistant messages), idle, last_text, rate_limited,
    model — from a Pi JSONL, or a Claude Code JSONL (no price; usage limit => rate_limited). A session with no
    assistant turn is not idle: it has not answered anything yet."""
    out = dict(EMPTY, tool_calls=Counter(), started=True)
    for line in path.read_text().splitlines():
        try:
            o = json.loads(line)
        except ValueError:
            continue
        m = o.get("message") if isinstance(o.get("message"), dict) else None
        if not m or not isinstance(m.get("content"), (list, str)):
            continue
        role = m.get("role") or o.get("type")
        content = m["content"] if isinstance(m["content"], list) else [{"type": "text", "text": m["content"]}]
        if role == "assistant":
            out["turns"] += 1
            u = m.get("usage") or {}
            out["cost_usd"] += ((u.get("cost") or {}).get("total") or 0.0)
            out["tokens"] += u.get("totalTokens") or sum(u.get(k, 0) or 0 for k in (
                "input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"))
            # cached tokens, provider-neutral (pipeline.prompt-cache): Pi's cacheRead/cacheWrite, Anthropic's
            # cache_read/cache_creation, OpenRouter's prompt_tokens_details.cached_tokens; a provider that reports none => 0
            details = u.get("prompt_tokens_details") or {}
            out["cache_read"] += u.get("cacheRead") or u.get("cache_read_input_tokens") or details.get("cached_tokens") or 0
            out["cache_write"] += u.get("cacheWrite") or u.get("cache_creation_input_tokens") or 0
            out["fresh"] += u.get("input") or u.get("input_tokens") or u.get("prompt_tokens") or 0
            out["context"] = (u.get("input") or u.get("input_tokens") or 0) + (u.get("cacheRead") or u.get("cache_read_input_tokens") or 0) + (
                u.get("cacheWrite") or u.get("cache_creation_input_tokens") or 0)  # the latest turn's prompt: what the window holds now
            out["model"] = m.get("model") or out["model"]
            stop = m.get("stopReason") or m.get("stop_reason") or ""
            out["idle"] = stop in ("stop", "end_turn", "endTurn", "stop_sequence") and not any(
                c.get("type") in ("toolCall", "tool_use") for c in content)
            # a quota or credit failure is read ONLY from structured error shapes of the LATEST turn (Pi: stopReason
            # "error" + errorMessage; Claude Code: isApiErrorMessage), never from what the model wrote (review MED C)
            # Claude Code reports a limit as an isApiErrorMessage line, or as a `<synthetic>`-model turn with the limit
            # wording ("5-hour limit reached ∙ resets 2am", "You've hit your limit"); both count, prose from a real turn never
            synthetic = o.get("isApiErrorMessage") or m.get("model") == "<synthetic>"
            err = m.get("errorMessage") if stop == "error" else (m.get("content") if synthetic else "")
            out["rate_limited"] = bool(err) and bool(QUOTA.search(str(err)))
            out["error"] = str(err)[:300] if err and not out["rate_limited"] else ""  # any other API error, latest turn
            out["transient"] = bool(out["error"]) and bool(TRANSIENT.search(out["error"]))
            for c in content:
                if c.get("type") in ("toolCall", "tool_use"):
                    name, args = c.get("name", "?"), c.get("arguments") or c.get("input") or {}
                    if name == "mcp" and isinstance(args, dict):  # the adapter's generic call: the real tool is inside
                        name = args.get("tool") or f"mcp:{args.get('server', '?')}"
                        out["proxy_calls"] += 1  # the wide set: a brief miss
                    out["tool_calls"][name] += 1
                elif c.get("type") == "text" and c.get("text"):
                    out["last_text"] = c["text"]
        elif role == "user":
            out["idle"] = False  # a prompt or a tool result is in, the answer is not
            # a human prompt is a string or a text block; Claude Code also files tool results as `user` lines
            if isinstance(m["content"], str) or any(c.get("type") == "text" for c in content) and not any(
                    c.get("type") == "tool_result" for c in content):
                out["prompts"] += 1
    out["cache_hit"] = cache_hit(out)
    return out



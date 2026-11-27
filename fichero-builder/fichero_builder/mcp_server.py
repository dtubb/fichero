"""`builder mcp`: the builder's MCP server (builder-console.mcp.same-reads-and-controls). stdio, one JSON-RPC 2.0 message a line,
standard library only. Its tools are the console's reads and controls, called from the console's own functions: a control runs the
verb the page's button runs (`console.act`) and writes the same `console` row, with who `mcp`.
ponytail: tools only; resources and prompts when a client needs them."""
from __future__ import annotations

import json
import sys

from fichero_builder import console, journal, queue, review_page

PROTOCOL = "2025-06-18"  # answered when the client names none
WHO = "mcp"
ACT_WAIT_S = 120  # how long a control waits for its verb before it returns the `started` row


def _schema(required: tuple = (), optional: tuple = ()) -> dict:
    return {"type": "object", "properties": {k: {"type": "string"} for k in (*required, *optional)}, "required": list(required)}


def _act(verb: str, args: dict) -> dict:
    """The page's action, waited for: the verb's `ended` console row (ok, rc, the tail of its output), or the refusal."""
    r = console.act(verb, args, WHO)
    if not r["ok"]:
        return r
    r["thread"].join(ACT_WAIT_S)
    return next(({"ok": bool(x.get("ok")), **{k: x.get(k) for k in ("verb", "state", "rc", "detail")}} for x in reversed(journal.read())
                 if x.get("event") == "console" and x.get("who") == WHO and x.get("verb") == verb), {"ok": False, "error": f"no console row for {verb}"})


# name -> (description, input schema, the call). Reads return the console's own documents.
TOOLS = {
    "status": ("The builder's status as the console shows it: lanes, last check, review and landing, spend today, open alerts, trains.",
               _schema(), lambda a: console.status_cached()),
    "lanes": ("Each lane with its step, state, why it waits, its queued steps and its last action.", _schema(), lambda a: console.status_cached()["lanes"]),
    "alerts": ("The open alerts grouped by kind, the ones over a day old apart, the owner's marked, and the resolved ones of the last days.",
               _schema(), lambda a: console.alerts_view(console.rows_of(console.ROOT))),
    "now": ("What is running now, in order: lanes with each step's state and age, the last trains, the check slots and what holds each.",
            _schema(), lambda a: console.now_view(console.rows_of(console.ROOT), queue.load())),
    "review_list": ("The owner's review list: every item with its status and note.", _schema(), lambda a: review_page.load()),
    "thread": ("The owner's messages to the manager and the manager's replies, by time.", _schema(), lambda a: {"messages": console.thread()}),
    "lane_pause": ("Pause a lane: no new step is fed to it.", _schema(("lane",)), lambda a: _act("pause", {"lane": a["lane"]})),
    "lane_resume": ("Resume a lane; its blocked steps go again as queued.", _schema(("lane",)), lambda a: _act("resume", {"lane": a["lane"]})),
    "alert_answer": ("Answer one alert with an action it offers (retry, park, ask-owner, approve, send-back, dismiss).",
                     _schema(("id", "action")), lambda a: _act("alert", {"id": a["id"], "action": a["action"]})),
    "review_verdict": ("Set one review item's status (to-test, works, polish, bug, n/a), its note, or both.",
                       _schema(("id",), ("status", "note")), lambda a: console.review_verdict(a["id"], a.get("status"), a.get("note"), WHO)),
    "message_manager": ("Send the manager a message: one line in its inbox and one owner-message row.",
                        _schema(("text",)), lambda a: console.message(a["text"], WHO)),
}


def call(name, args) -> dict:
    """One tools/call result. An unknown tool, a missing argument, a refusal or a verb that failed is `isError`, with why."""
    def result(text: str, error: bool) -> dict:
        return {"content": [{"type": "text", "text": text}], "isError": error}
    if name not in TOOLS:
        return result(f"no tool {name!r}: one of {', '.join(TOOLS)}", True)
    _desc, schema, fn = TOOLS[name]
    if not isinstance(args, dict):
        return result(f"{name}: arguments must be an object", True)
    if missing := [k for k in schema["required"] if args.get(k) in (None, "")]:
        return result(f"{name} needs {', '.join(missing)}", True)
    try:
        out = fn(args)
    except (ValueError, OSError) as e:
        return result(f"{name}: {e}", True)
    return result(json.dumps(out, default=str), isinstance(out, dict) and out.get("ok") is False)


def handle(msg) -> dict | None:
    """The reply to one JSON-RPC message; None for a notification."""
    if not isinstance(msg, dict):
        return {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "a request is a JSON object"}}
    mid, method, params = msg.get("id"), msg.get("method"), msg.get("params") or {}
    if mid is None:
        return None
    if method == "initialize":
        res = {"protocolVersion": params.get("protocolVersion") or PROTOCOL, "capabilities": {"tools": {}}, "serverInfo": {"name": "fichero-builder", "version": "0.1.0"}}
    elif method == "ping":
        res = {}
    elif method == "tools/list":
        res = {"tools": [{"name": n, "description": d, "inputSchema": s} for n, (d, s, _f) in TOOLS.items()]}
    elif method == "tools/call":
        res = call(params.get("name"), params.get("arguments") or {})
    else:
        return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"no method {method!r}"}}
    return {"jsonrpc": "2.0", "id": mid, "result": res}


def serve(stdin, stdout) -> None:
    for line in stdin:
        if not line.strip():
            continue
        try:
            reply = handle(json.loads(line))
        except ValueError:
            reply = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "not JSON"}}
        if reply is not None:
            stdout.write(json.dumps(reply) + "\n")
            stdout.flush()


def main(a) -> int:
    console.configure(a.root)
    serve(sys.stdin, sys.stdout)
    return 0

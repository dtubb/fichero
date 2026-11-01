"""A fake OpenAI-completions provider for the Pi tests: the first request answers with a `bash` tool call, every
later one with the text `done`. Streams SSE the way Pi 0.75.5 reads it (chunk.choices[0].delta, finish_reason,
chunk.usage). No key, no network, no cost."""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer


def serve(command: str):
    """Returns (base_url, server, calls); `calls` collects every request body."""
    calls: list[dict] = []

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):  # quiet
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
            calls.append(body)
            tool_done = any(m.get("role") == "tool" for m in body.get("messages", []))
            if tool_done:
                chunks = [{"choices": [{"index": 0, "delta": {"role": "assistant", "content": "done"}, "finish_reason": None}]},
                          {"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                           "usage": {"prompt_tokens": 20, "completion_tokens": 1}}]
            else:
                call = {"index": 0, "id": "call_1", "type": "function",
                        "function": {"name": "bash", "arguments": json.dumps({"command": command})}}
                chunks = [{"choices": [{"index": 0, "delta": {"role": "assistant", "tool_calls": [call]}, "finish_reason": None}]},
                          {"choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}],
                           "usage": {"prompt_tokens": 10, "completion_tokens": 5}}]
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            for c in chunks:
                self.wfile.write(f"data: {json.dumps({'id': 'x', 'object': 'chat.completion.chunk', 'model': 'fake-1', **c})}\n\n".encode())
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{srv.server_port}/v1", srv, calls


def agent_dir(path, base_url) -> None:
    """A Pi agent dir (PI_CODING_AGENT_DIR) whose models.json names the fake provider only."""
    path.mkdir(parents=True, exist_ok=True)
    (path / "models.json").write_text(json.dumps({"providers": {"fake": {
        "baseUrl": base_url, "api": "openai-completions", "apiKey": "x",
        "compat": {"supportsDeveloperRole": False, "supportsReasoningEffort": False},
        "models": [{"id": "fake-1", "name": "fake", "contextWindow": 100000, "maxTokens": 1000, "reasoning": False,
                    "input": ["text"], "cost": {"input": 1, "output": 2, "cacheRead": 0, "cacheWrite": 0}}]}}}))
    (path / "settings.json").write_text(json.dumps({"quietStartup": True}))

"""A fake OpenAI-compatible model server for the harness dry runs (stage 0): stdlib, localhost only, no key, no cost.
It answers each POST /v1/chat/completions with the next scripted step, streamed as the real API does, and records
every request. A step is a dict:
  text   the assistant's words            tools  [(name, args-dict), ...] tool calls
  usage  {"prompt": n, "cached": n, "out": n}  what the turn reports (drives the 85 % handoff)
  fail   "500" (any status) an HTTP error | "drop" the connection closed mid-stream | "hang" no answer | "error:<text>" a 400 with that body
or a callable(request_body) -> step, so a step can read the brief the runner sent. Past the end of the script every
request gets `idle` (a short text, tiny usage): a worker with nothing left to do just stops."""
from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

IDLE = {"text": "Nothing left to do.", "usage": {"prompt": 100, "out": 5}}


class FakeModel:
    def __init__(self, steps=()):
        self.steps, self.requests, self.lock = list(steps), [], threading.Lock()
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self.url = f"http://127.0.0.1:{self.srv.server_port}/v1"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def script(self, *steps):
        with self.lock:
            self.steps += steps

    def close(self):
        self.srv.shutdown()
        self.srv.server_close()

    def next_step(self, body: dict) -> dict:
        with self.lock:
            self.requests.append(body)
            step = self.steps.pop(0) if self.steps else IDLE
        return step(body) if callable(step) else step

    def _handler(fm):
        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers.get("content-length", 0))) or b"{}")
                step = fm.next_step(body)
                fail = step.get("fail", "")
                if fail.isdigit():  # an HTTP error status: "429", "500", "503"
                    return self._send(int(fail), {"error": {"message": f"fake server error {fail}", "type": "server_error"}})
                if fail.startswith("error:"):
                    return self._send(400, {"error": {"message": fail[6:], "type": "invalid_request_error"}})
                if fail == "hang":
                    time.sleep(3600)
                    return
                self.send_response(200)
                self.send_header("content-type", "text/event-stream")
                self.end_headers()
                for chunk in fm.chunks(step, body):
                    self.wfile.write(b"data: " + json.dumps(chunk).encode() + b"\n\n")
                    self.wfile.flush()
                    if fail == "drop" and chunk["choices"] and chunk["choices"][0]["delta"].get("content"):
                        self.close_connection = True  # the stream stops mid-turn, no finish chunk
                        return
                self.wfile.write(b"data: [DONE]\n\n")

            def _send(self, code, obj):
                data = json.dumps(obj).encode()
                self.send_response(code)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
        return H

    @staticmethod
    def chunks(step: dict, body: dict):
        base = {"id": "chatcmpl-fake", "object": "chat.completion.chunk", "created": int(time.time()), "model": body.get("model", "fake")}
        tools = step.get("tools", [])
        yield dict(base, choices=[{"index": 0, "delta": {"role": "assistant", "content": step.get("text", "")}, "finish_reason": None}])
        for i, (name, args) in enumerate(tools):
            call = {"index": i, "id": f"call_{time.time_ns()}_{i}", "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}
            yield dict(base, choices=[{"index": 0, "delta": {"tool_calls": [call]}, "finish_reason": None}])
        yield dict(base, choices=[{"index": 0, "delta": {}, "finish_reason": "tool_calls" if tools else "stop"}])
        u = step.get("usage", {})
        yield dict(base, choices=[], usage={"prompt_tokens": u.get("prompt", 100), "completion_tokens": u.get("out", 10),
                                            "total_tokens": u.get("prompt", 100) + u.get("out", 10),
                                            "prompt_tokens_details": {"cached_tokens": u.get("cached", 0)}})

"""dev-workflows.node.worker: the RPC client correlates responses by id, splits records on LF only, and reads
Pi's session stats and the worker's session file."""
from __future__ import annotations

import sys

from fichero_builder import pi_rpc, session
from tests.test_pi_live_helpers import live

FAKE_PI = r'''
import json, sys
for line in sys.stdin:
    o = json.loads(line)
    sys.stdout.write(json.dumps({"type": "agent_start"}) + "\n")
    data = {"tokens": {"input": 5, "output": 1, "cacheRead": 2, "cacheWrite": 0}, "cost": 0.01,
            "text": "a b"} if o["type"] == "get_session_stats" else {}
    sys.stdout.write(json.dumps({"type": "response", "id": o["id"], "command": o["type"], "success": True, "data": data}) + "\n")
    sys.stdout.flush()
'''


def test_responses_match_by_id_and_events_queue_separately(tmp_path):
    f = tmp_path / "fake_pi.py"
    f.write_text(FAKE_PI)
    pi = pi_rpc.Pi([sys.executable, str(f)], cwd=tmp_path, env={}, timeout_s=10)
    try:
        assert pi.prompt("hi")["command"] == "prompt"
        st = pi.stats()
        assert st["cost"] == 0.01 and st["text"] == "a b", "U+2028 inside a string is not a record end"
        assert pi.events.get(timeout=2)["type"] == "agent_start"
    finally:
        pi.stop()


def test_the_policy_argv_runs_the_module_with_the_three_paths():
    argv = pi_rpc.policy_argv("/r", "/w", "/s")
    assert argv[1:4] == ["-m", "fichero_builder.pi_rpc", "policy"] and "/w" in argv and "/s" in argv


def test_live_pi_answers_stats_and_writes_a_session_file_the_parser_reads(tmp_path):
    pi, srv, calls = live(tmp_path, "echo hi")
    try:
        pi.prompt("go")
        pi.wait(timeout_s=90)
        st = pi.stats()
        assert st["tokens"]["input"] >= 1 and st["assistantMessages"] >= 2, st
        files = session.session_files(tmp_path / "sessions")
        assert files, "Pi wrote a session file under --session-dir"
        parsed = session.parse_session(files[-1])
        assert parsed["turns"] >= 2 and parsed["idle"], parsed
    finally:
        pi.stop(), srv.shutdown()

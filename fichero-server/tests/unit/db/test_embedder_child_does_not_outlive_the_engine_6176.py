"""`engine.orphan-child-lets-go` (#6176): the forked embedder child must not outlive its engine or keep the engine's listening
socket. Opus review 2026-10-26: the child inherited the listening socket and both pipe ends, so after the app killed the engine
the socket stayed live and the new engine could not start (Ann's 'two Fichero Server' processes).
WHY: a SIGKILLed engine cannot reap its daemon child; the child must notice and exit, and must never hold the engine's sockets."""
from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
import time

ENGINE = r"""
import os, socket, sys
os.environ["FICHERO_EMBED_FAKE_INIT_SECONDS"] = "0.1"
from fichero_server.db import embed_process
from fichero_server.db.embed_process import RemoteEmbedder
embed_process._cached = lambda *_a: True  # the fake model is "in the cache"
import onnxruntime  # as in the engine, whose real cache check loads fastembed before any fork
listener = socket.socket()
listener.bind(("127.0.0.1", 0))
listener.listen()
embedder = RemoteEmbedder("fake-model", sys.argv[1], 1)
print(listener.getsockname()[1], embedder._process.pid, flush=True)
import time
time.sleep(120)
"""


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def test_a_killed_engines_embedder_child_exits_and_lets_go_of_the_listening_socket(tmp_path):
    engine = subprocess.Popen([sys.executable, "-c", ENGINE, str(tmp_path)], stdout=subprocess.PIPE, text=True)
    child = 0
    try:
        port, child = (int(x) for x in engine.stdout.readline().split())
        assert _alive(child)
        engine.send_signal(signal.SIGKILL)  # the app's second kill: nothing reaps the daemon child
        engine.wait(10)
        deadline = time.monotonic() + 5
        while _alive(child) and time.monotonic() < deadline:
            time.sleep(0.1)
        assert not _alive(child), "the embedder child outlived its engine"
        with socket.socket() as probe:
            probe.settimeout(1)
            assert probe.connect_ex(("127.0.0.1", port)) != 0, "the engine's listening socket is still live"
    finally:
        if child and _alive(child):
            os.kill(child, signal.SIGKILL)
        if engine.poll() is None:
            engine.kill()

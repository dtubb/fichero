"""The forked embedder child stops LanceDB's loop before it lets go of the engine's files (#6237).

WHY: on the M4 106-page run the log showed, twice, "Exception in thread LanceDBBackgroundEventLoop -> selectors.select ->
OSError: [Errno 9] Bad file descriptor". lancedb starts a fresh loop thread in every forked child (its after-fork hook),
and the embedder child then closes every inherited descriptor (#6176), that loop's kqueue among them. The child never
uses LanceDB, so it stops the loop first, and nothing dies in its stderr.
"""
from __future__ import annotations

import subprocess
import sys

ENGINE = r"""
import os, sys, time
os.environ["FICHERO_EMBED_FAKE_INIT_SECONDS"] = "0.1"
import lancedb  # the engine has LanceDB's loop running before the embedder forks
from fichero_server.db import embed_process
embed_process._cached = lambda *_a: True  # the fake model is "in the cache"
import onnxruntime  # as in the engine, whose real cache check loads fastembed before any fork
embedder = embed_process.RemoteEmbedder("fake-model", sys.argv[1], 1)
assert embedder.embed(["one"]) == [[3.0, 1.0]]
time.sleep(1)  # the child's loop thread would die here
embedder.close()
print("done", flush=True)
"""


def test_the_embedder_child_leaves_no_dead_lancedb_loop_6237(tmp_path):
    ran = subprocess.run([sys.executable, "-W", "ignore", "-c", ENGINE, str(tmp_path)], capture_output=True, text=True,
                         timeout=60)
    assert ran.returncode == 0 and "done" in ran.stdout, ran.stderr
    assert "LanceDBBackgroundEventLoop" not in ran.stderr and "Bad file descriptor" not in ran.stderr, ran.stderr

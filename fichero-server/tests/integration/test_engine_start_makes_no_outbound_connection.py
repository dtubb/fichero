"""#5188, the engine half: starting the engine, answering /api/health, opening a library and a
minute of idle background queues reach nothing off this machine.

WHY: a test must never fetch, and neither should an engine a person has only opened. The seed guard
(test_seeding_makes_no_outbound_connection.py) covers building the library; this covers the ENGINE
-- its startup, its warm-ups, its background queues -- which is where a model download, an update
feed, a gazetteer or a licence check would hide. A new reach fails here naming the host and the
engine frame that made it, instead of silently slowing every live fixture or phoning home.

Recorded two ways, because plain sockets bypass a proxy: HTTP(S)_PROXY and ALL_PROXY point at a
recording dead proxy on loopback (it logs the CONNECT or absolute URL and closes), and a
`sitecustomize` shim on the spawned process's PYTHONPATH logs -- and refuses -- every non-loopback
connect and DNS lookup, with the frame. The engine is spawned the way `_cli_live` spawns it, with a
COLD home (no shared model cache) and this suite's environment (HF_HUB_OFFLINE=1 from the conftest).
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import threading
import time

import httpx
import pytest

from tests.integration._cli_live import REPO_ROOT, VENV_UVICORN, _free_port, _wait_healthy

pytestmark = [pytest.mark.load_sensitive, pytest.mark.slow]

IDLE_SECONDS = 60

_SHIM = r'''
import json, os, socket, traceback
_LOG = os.environ["FICHERO_TEST_CONNECT_LOG"]
_LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost", "0.0.0.0", ""}

def _local(host):
    host = str(host)
    return host in _LOOPBACK_HOSTS or host.startswith("127.") or host.startswith("/")

def _frame():
    frames = [f for f in traceback.extract_stack()[:-2] if "fichero_server" in f.filename]
    f = (frames or traceback.extract_stack()[:-2])[-1]
    return f"{f.filename.rsplit('/', 3)[-1]}:{f.lineno} {f.name}"

def _record(kind, target):
    with open(_LOG, "a") as out:
        out.write(json.dumps({"kind": kind, "target": str(target), "frame": _frame()}) + "\n")

_connect = socket.socket.connect
def connect(self, address):
    if self.family in (socket.AF_INET, socket.AF_INET6) and not _local(address[0]):
        _record("connect", address)
        raise OSError("offline test: outbound connect refused")
    return _connect(self, address)
socket.socket.connect = connect

_getaddrinfo = socket.getaddrinfo
def getaddrinfo(host, *args, **kwargs):
    if host is not None and not _local(host if isinstance(host, str) else host.decode()):
        _record("dns", host)
        raise socket.gaierror("offline test: DNS refused")
    return _getaddrinfo(host, *args, **kwargs)
socket.getaddrinfo = getaddrinfo
with open(_LOG, "a") as _out:
    _out.write(json.dumps({"kind": "loaded", "pid": os.getpid()}) + "\n")
'''


class _RecordingDeadProxy:
    """A loopback proxy that answers nothing: it records what it was asked to reach and closes."""

    def __init__(self):
        self.asked: list[str] = []
        self._server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server.bind(("127.0.0.1", 0))
        self._server.listen(16)
        self.port = self._server.getsockname()[1]
        self._stop = False
        threading.Thread(target=self._serve, daemon=True).start()

    def _serve(self):
        self._server.settimeout(0.5)
        while not self._stop:
            try:
                conn, _ = self._server.accept()
            except OSError:
                continue
            with conn:
                conn.settimeout(2)
                try:
                    first = conn.recv(2048).split(b"\r\n", 1)[0].decode(errors="replace")
                except OSError:
                    first = "(no request line)"
                self.asked.append(first)

    def close(self):
        self._stop = True
        self._server.close()


def test_an_engine_start_and_a_minute_idle_reach_nothing_off_the_machine(tmp_path):
    if not VENV_UVICORN.exists():
        pytest.skip(f"venv uvicorn not found at {VENV_UVICORN}")
    from tests.integration._seedlib import seed

    library = tmp_path / "library.fichero"
    seed(library)
    shim_dir = tmp_path / "shim"
    shim_dir.mkdir()
    (shim_dir / "sitecustomize.py").write_text(_SHIM)
    connect_log = tmp_path / "connects.jsonl"
    connect_log.touch()
    proxy = _RecordingDeadProxy()
    proxy_url = f"http://127.0.0.1:{proxy.port}"
    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    env = {
        **os.environ,
        "HOME": str(tmp_path),                                  # COLD: no shared model cache
        "PYTHONPATH": os.pathsep.join([str(shim_dir), str(REPO_ROOT / "fichero-server" / "src")]),
        "FICHERO_DISABLE_AUTH": "1",
        "FICHERO_FEATURE_TIER": "dev",
        "FICHERO_SKIP_DEFAULT_WORKFLOWS": "1",
        "FICHERO_BASE_PATH": str(tmp_path / "base"),
        "FICHERO_PARENT_PID": str(os.getpid()),
        "FICHERO_TEST_CONNECT_LOG": str(connect_log),
        **{name: proxy_url for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy")},
        "NO_PROXY": "127.0.0.1,localhost,::1", "no_proxy": "127.0.0.1,localhost,::1",
    }
    engine_log = tmp_path / "engine.log"
    with open(engine_log, "w") as log_handle:
        process = subprocess.Popen(
            [str(VENV_UVICORN), "fichero_server.api.main:app", "--host", "127.0.0.1", "--port", str(port)],
            env=env, stdout=subprocess.DEVNULL, stderr=log_handle,
        )
        try:
            why = _wait_healthy(base_url, process)
            assert why is None, f"{why}\n" + engine_log.read_text(errors="replace")[-3000:]
            assert httpx.get(f"{base_url}/api/health", timeout=10).status_code == 200
            opened = httpx.get(f"{base_url}/api/documents", headers={"X-Fichero-Library-Path": str(library)}, timeout=30)
            assert opened.status_code == 200, opened.text[:300]
            time.sleep(IDLE_SECONDS)                            # the background queues' idle minute
            quiet = (list(proxy.asked), connect_log.read_text())
            # POSITIVE CONTROL: the one sanctioned reach -- an explicit authority refresh behind its
            # switch -- must be SEEN, or a silent recorder would pass anything.
            headers = {"X-Fichero-Library-Path": str(library)}
            switched = httpx.put(f"{base_url}/api/kg/entity-curation/authority/settings",
                                 json={"external_authority_enabled": True}, headers=headers, timeout=30)
            assert switched.status_code == 200, switched.text[:300]
            refreshed = httpx.post(f"{base_url}/api/kg/entity-curation/authority/refresh",
                                   json={"query": "Paris", "authorities": ["wikidata"]}, headers=headers, timeout=60)
            assert refreshed.status_code == 502, refreshed.text[:300]      # it tried, and was refused
        finally:
            process.terminate()
            try:
                process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                process.kill()
            proxy.close()
    records = [json.loads(line) for line in connect_log.read_text().splitlines() if line.strip()]
    # Not vacuous: the shim ran inside the engine process (a missing sitecustomize would record nothing).
    assert any(r["kind"] == "loaded" and r["pid"] == process.pid for r in records), records[:5]
    reached = [r for r in records if r["kind"] != "loaded"]
    control = [line for line in proxy.asked if "wikidata.org" in line] + \
              [r for r in reached if "wikidata.org" in r["target"]]
    assert control, f"the recorders missed the deliberate refresh: proxy {proxy.asked}, direct {reached}"
    # Everything BEFORE the control: nothing at all.
    quiet_proxy, quiet_log = quiet
    quiet_reached = [json.loads(line) for line in quiet_log.splitlines() if line.strip()
                     and json.loads(line)["kind"] != "loaded"]
    proxy.asked, reached = quiet_proxy, quiet_reached
    assert proxy.asked == [] and reached == [], (
        "the engine reached off the machine:\n  via the proxy: " + "\n    ".join(proxy.asked or ["nothing"])
        + "\n  directly: " + "\n    ".join(f"{r['kind']} {r['target']} from {r['frame']}" for r in reached or [])
    )

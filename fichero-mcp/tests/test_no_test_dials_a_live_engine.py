"""The conftest's autouse guard: a test that dials the default engine address fails loudly instead of reaching an engine that may
be live, the owner's included (the MCP launcher's startup probe did, 2026-10-18 to 10-24)."""
import importlib.util
import os
import socket
import tempfile
from pathlib import Path

import pytest


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost"])
def test_a_connect_to_the_default_engine_address_is_refused_by_the_test_seam(host):
    with socket.socket() as sock:
        with pytest.raises(AssertionError, match="a live engine may answer"):
            sock.connect((host, 8765))
        with pytest.raises(AssertionError, match="a live engine may answer"):
            sock.connect_ex((host, 8765))


def test_the_app_containers_unix_socket_is_refused_too(tmp_path):
    container_socket = Path.home() / "Library" / "Containers" / "app.fichero.fichero" / "Data" / "tmp" / "fichero.sock"
    with socket.socket(socket.AF_UNIX) as sock:
        with pytest.raises(AssertionError, match="Unix socket"):
            sock.connect(str(container_socket))
        with pytest.raises(AssertionError, match="Unix socket"):
            sock.connect_ex(str(container_socket))


def test_a_socket_the_developers_own_fichero_uds_names_is_refused_and_the_env_is_off(monkeypatch, tmp_path):
    """The guard is built from the shell's FICHERO_UDS before the seam turns it off: with a path set, that path is refused."""
    assert os.environ.get("FICHERO_UDS") == "0", "the seam must turn the socket off for every test"
    short = Path(tempfile.mkdtemp(dir="/tmp"))  # a socket path is limited to about 100 characters: tmp_path is longer
    own = str(short / "engine.sock")
    monkeypatch.setenv("FICHERO_UDS", own)
    spec = importlib.util.spec_from_file_location("conftest_probe", Path(__file__).with_name("conftest.py"))
    probe = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(probe)
    probe._forbid_the_default_engine(monkeypatch)
    with socket.socket(socket.AF_UNIX) as sock, pytest.raises(AssertionError, match="Unix socket"):
        sock.connect(own)
    with socket.socket(socket.AF_UNIX) as sock, pytest.raises(FileNotFoundError):
        sock.connect(str(short / "some-other.sock"))  # a socket of a test's own is not refused
    short.rmdir()

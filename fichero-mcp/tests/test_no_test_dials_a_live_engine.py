"""The conftest's autouse guard: a test that dials the default engine address fails loudly instead of reaching an engine that may
be live, the owner's included (the MCP launcher's startup probe did, 2026-10-18 to 10-24)."""
import socket

import pytest


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost"])
def test_a_connect_to_the_default_engine_address_is_refused_by_the_test_seam(host):
    with socket.socket() as sock:
        with pytest.raises(AssertionError, match="a live engine may answer"):
            sock.connect((host, 8765))
        with pytest.raises(AssertionError, match="a live engine may answer"):
            sock.connect_ex((host, 8765))


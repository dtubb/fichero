"""`sharing.stale-server-holding-the-port` (docs/contributor_manual/specs/source/sharing-two-macs.md §4, Step 1.5).

An old engine on the sharing port ends the new one with a plain sentence the app can show, not "engine failed to start".
"""
from __future__ import annotations

import socket

from fichero_server.security.bind_host import port_in_use_message

SENTENCE = "Another copy of Fichero's server is using port 8765. Quit it (Activity Monitor › Fichero Server) or restart this Mac."


def test_the_sentence_names_the_port_and_what_to_do():
    assert port_in_use_message(8765) == SENTENCE


def test_an_engine_that_finds_the_port_held_says_the_sentence_after_the_line_the_harness_reads():
    from fichero_server.__main__ import _port_held_line

    held = socket.socket()
    held.bind(("127.0.0.1", 0))
    held.listen()
    port = held.getsockname()[1]
    try:
        line = _port_held_line("127.0.0.1", port)
    finally:
        held.close()
    assert line.startswith(f"Port {port} is already in use on 127.0.0.1.")
    assert f"Another copy of Fichero's server is using port {port}." in line


def test_a_free_port_is_no_line():
    from fichero_server.__main__ import _port_held_line

    free = socket.socket()
    free.bind(("127.0.0.1", 0))
    port = free.getsockname()[1]
    free.close()
    assert _port_held_line("127.0.0.1", port) is None

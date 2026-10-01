"""A stream command prints each event as it arrives (#5321).

A live SSE stream never ends. `changes stream-library` waited for the whole response and
`request_stream` collected every line first, so watching a shared library from the terminal
printed nothing, ever. Here the stream delivers one event and then never finishes (it raises,
standing in for "still open"): the event must already be on screen.
"""

from __future__ import annotations

import httpx
import pytest
from typer.testing import CliRunner

from fichero_cli import FicheroClient
from fichero_cli import __main__ as cli_main


class _StillOpen(Exception):
    """The server has not closed the stream."""


class _OneEventThenOpen(httpx.SyncByteStream):
    def __iter__(self):
        yield b'id: 7\ndata: {"type": "note.created"}\n\n'
        raise _StillOpen


@pytest.fixture
def open_stream(monkeypatch):
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200, headers={"content-type": "text/event-stream"}, stream=_OneEventThenOpen()
        )
    )
    real_client = FicheroClient
    monkeypatch.setattr(cli_main, "FicheroClient", lambda **kw: real_client(transport=transport, **kw))


@pytest.mark.parametrize("args", [["changes", "stream-library"], ["activity-stream"]])
def test_an_event_prints_before_the_stream_ends(open_stream, args):
    result = CliRunner().invoke(cli_main.app, ["--token", "t", "--json", "-l", "/lib.fichero", *args])
    assert isinstance(result.exception, _StillOpen)
    assert "note.created" in result.output

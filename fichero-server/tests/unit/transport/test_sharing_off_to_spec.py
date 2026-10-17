"""sharing.off-closes-the-guest (#5731), the engine half.

When the host stops sharing the engine shuts down; a guest's change stream ends with a typed
`sharing.stopped` event first, so the guest can say so once instead of looping on reconnects.
The host's own windows (loopback) get no such event.
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

from fichero_server.api import change_stream
from fichero_server.api.routes.system import changes


class _Request:
    def __init__(self, host: str) -> None:
        self.state = SimpleNamespace(bootstrap_auth=True, user=None)
        self.scope: dict = {}
        self.client = SimpleNamespace(host=host)
        self.headers: dict = {}

    async def is_disconnected(self) -> bool:
        return False


async def _frames_at_shutdown(test_package, host: str) -> list[str]:
    change_stream.reset_sse_shutdown()
    response = await changes.stream_library_changes(_Request(host), x_fichero_library_path=str(test_package))
    stream = response.body_iterator
    frames = [await anext(stream)]
    change_stream.signal_sse_shutdown()
    try:
        while True:
            frames.append(await asyncio.wait_for(anext(stream), timeout=1))
    except StopAsyncIteration:
        pass
    finally:
        change_stream.reset_sse_shutdown()
        await stream.aclose()
    return frames


async def test_a_guest_stream_ends_with_a_typed_sharing_stopped_event(test_package):
    frames = await _frames_at_shutdown(test_package, "198.51.100.20")
    assert len(frames) == 2, frames
    payload = json.loads(frames[1].split("data: ", 1)[1])
    assert payload["type"] == "sharing.stopped"


async def test_the_hosts_own_stream_just_ends(test_package):
    assert await _frames_at_shutdown(test_package, "127.0.0.1") == [": connected\n\n"]

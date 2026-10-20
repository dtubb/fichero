"""A revoked device's stream gets its last `sharing.revoked` frame even though the hub marks it inactive at once (## 738).

In the engine every subscriber has a running loop, so the frame is scheduled with call_soon_threadsafe and lands after
`active = False`; it must still be queued, or the stream never ends (keepalives forever, no data)."""

import asyncio

import pytest

from fichero_server.api.change_stream import ChangeEvent, _ChangeHub


@pytest.mark.asyncio
async def test_a_looped_subscriber_gets_the_revoked_frame_and_nothing_after():
    hub = _ChangeHub()
    sub = hub.connect("/tmp/lib.fichero", device_id="dev-1")
    other = hub.connect("/tmp/lib.fichero", device_id="dev-2")

    assert hub.revoke_devices(["dev-1"]) == 1
    event = await asyncio.wait_for(sub.queue.get(), timeout=1)
    assert event.type == "sharing.revoked"

    hub._dispatch_to_subscriber(hub._canonical_key("/tmp/lib.fichero"), hub._subscriber_by_queue[sub.queue], ChangeEvent(type="page.updated"))
    await asyncio.sleep(0)
    assert sub.queue.empty()  # nothing more reaches the revoked device
    assert other.queue.empty()  # the other device was untouched

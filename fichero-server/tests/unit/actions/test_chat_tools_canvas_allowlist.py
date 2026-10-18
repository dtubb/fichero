"""Red pin for research.canvas-actions-are-agent-tools (#3093).

The five canvas.* audited actions should be agent-operable through the chat-tools
write allowlist, the same way entity.create and claim.create already are. Today
none of them is on CHAT_WRITE_ALLOWLIST: a strict xfail, so it turns red the day #3093 lands and the
mark must come off.
"""

from __future__ import annotations

import pytest

from fichero_server.actions.chat_tools import CHAT_WRITE_ALLOWLIST

CANVAS_WRITE_ACTIONS = [
    "canvas.layout.save",
    "canvas.arrange",
    "canvas.item.create",
    "canvas.item.update",
    "canvas.item.delete",
]


@pytest.mark.xfail(strict=True, reason="#3093: canvas actions are not on the chat write allowlist yet")
@pytest.mark.parametrize("action", CANVAS_WRITE_ACTIONS)
def test_canvas_write_action_is_on_chat_allowlist(action: str) -> None:
    assert action in CHAT_WRITE_ALLOWLIST

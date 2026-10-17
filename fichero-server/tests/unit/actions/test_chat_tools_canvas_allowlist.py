"""Red pin for research.canvas-actions-are-agent-tools (#3093).

The five canvas.* audited actions should be agent-operable through the chat-tools
write allowlist, the same way entity.create and claim.create already are. Today
none of them is on CHAT_WRITE_ALLOWLIST, so this fails until #3093 lands.
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


@pytest.mark.research
@pytest.mark.parametrize("action", CANVAS_WRITE_ACTIONS)
def test_canvas_write_action_is_on_chat_allowlist(action: str) -> None:
    assert action in CHAT_WRITE_ALLOWLIST

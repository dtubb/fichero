"""The conftest resets the workflow node after every test: a node one sync test stamps is gone in the next (ordered pair)."""

from __future__ import annotations

from fichero_server.workflows import node_context


def test_a_test_may_stamp_a_node():
    node_context.set_current_node("n1", "Reflow", "wf1", "run-1", "text_reflow")
    assert node_context.get_current_node() is not None


def test_the_next_test_sees_no_node():
    assert node_context.get_current_node() is None

"""requires_vision can say "unknown" when a sub-workflow cannot be resolved (#4506).

Spec: docs/contributor_manual/specs/ui/workflows.md, `workflows.requires-vision-unknown`.
WHY: an unresolvable sub-workflow was skipped and the answer came back False, "does not need vision",
when the honest answer is "could not determine". False is the permissive default, so it must not be spent on a guess.
"""
from __future__ import annotations

from fichero_server.workflows.validation import workflow_requires_vision_or_unknown

_PARENT = [{"id": "s", "tool": "sub_workflow", "config": {"workflow_ref": "child"}}]


def test_an_unresolvable_child_is_unknown_not_false():
    assert workflow_requires_vision_or_unknown(_PARENT, workflow_resolver=lambda _ref: None) is None


def test_a_resolver_that_raises_is_unknown_too():
    def boom(_ref):
        raise RuntimeError("db down")

    assert workflow_requires_vision_or_unknown(_PARENT, workflow_resolver=boom) is None


def test_a_workflow_with_no_sub_workflows_is_still_a_plain_false_or_true():
    assert workflow_requires_vision_or_unknown([{"tool": "summarize_file"}]) is False
    assert workflow_requires_vision_or_unknown([{"tool": "transcribe"}]) is True

"""The audited action layer (EPIC #1848 / keystone #2013).

Every state-changing app capability becomes ONE named, typed *action* in a
process-global :data:`registry`. The same action is reachable five ways — UI
buttons, chat tools (#1847), App Intents (#1837), tests, and the audit log —
from a single definition.

``registry.invoke`` is the ONE write choke point: it validates params, runs the
action's ``execute``, writes an :class:`fichero_server.models.ActionAudit` row, and
broadcasts a :class:`fichero_server.api.change_stream.ChangeEvent` to the observable
data layer (#1863). ``before``/``after`` captured by the action ARE the undo
payload — ``invert(before, after)`` derives the inverse action.

This package exposes the contract that #2014's per-domain workers copy:

    from fichero_server.actions import action, registry, ActionContext, ChangeSpec

    @action("entity.merge", MergeParams, domains=["entity", "claim"], undoable=True,
            invert=_invert_merge)
    def merge(db, params, ctx) -> tuple[Any, ChangeSpec]:
        ...
        return result, ChangeSpec(domains=["entity", "claim"], target_ids=[...], ...)
"""

from __future__ import annotations

from fichero_server.actions.registry import (
    Action,
    ActionContext,
    ActionNotFoundError,
    ActionRegistration,
    ActionRegistry,
    ActionResult,
    ChangeSpec,
    action,
    registry,
)

__all__ = [
    "Action",
    "ActionContext",
    "ActionNotFoundError",
    "ActionRegistration",
    "ActionRegistry",
    "ActionResult",
    "ChangeSpec",
    "action",
    "registry",
]

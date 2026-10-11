"""Taking back recorded steps: one, or a set all-or-none (`safety.undo.*`, #5242, #5658).

The one engine path behind ``POST /api/actions/audit/{audit_id}/undo`` and
``POST /api/actions/audit/undo``. A single undo is a set of one.

* **A set is undone whole** (`safety.undo.a-set-is-undone-whole`): the rows are taken back
  newest first inside ONE ``db.transaction()``; if any row is refused, the database rolls the
  whole set back and the refusal names that row.
* **Marked inside the transaction** (`safety.undo.marked-inside-the-transaction`): a row's
  ``undone`` mark is written in the same transaction as its inverse.
* **Never over later work** (`safety.undo.refuses-when-changed`, the record's lock): a row is
  taken back only while no later step that is still in effect touched any of the same ids.
* **Refusals are sentences with a machine reason** (`safety.undo.refusal-loses-nothing`):
  ``changed`` (try again later), ``already-undone`` and ``gone`` (final: drop the step), and
  ``not-undoable``. A message never carries an id or a status code; the ids are fields.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from fastapi import HTTPException
from pydantic import ValidationError

from fichero_server.actions.registry import (
    ActionContext,
    ActionNotFoundError,
    ActionRefused,
    registry,
)

UndoRefusalReason = Literal["changed", "already-undone", "gone", "not-undoable"]

#: Later audit rows, by the database's append order (`chain_seq`) or, on rows the chain has not
#: numbered, by time. Constant fragments: `Database._query_where` binds every value.
_LATER_BY_SEQ = "chain_seq > $seq"
_LATER_BY_TIME = "created_at > $at"


class UndoRefused(HTTPException):
    """A step that cannot be taken back, said in a sentence, with a machine ``reason``.

    An ``HTTPException`` so every caller that already expects one keeps working; the app's
    exception handler answers ``{detail, reason, audit_id}`` (see ``refusal_body``).
    """

    def __init__(
        self,
        status_code: int,
        reason: UndoRefusalReason,
        detail: str,
        audit_id: str | None = None,
    ) -> None:
        super().__init__(status_code=status_code, detail=detail)
        self.reason = reason
        self.audit_id = audit_id

    @property
    def refusal_body(self) -> dict[str, Any]:
        return {"detail": self.detail, "reason": self.reason, "audit_id": self.audit_id}


@dataclass
class UndoneSet:
    """What a set undo wrote: the new rows, newest-first order of the rows they reversed."""

    audit_ids: list[str] = field(default_factory=list)
    changed_domains: list[str] = field(default_factory=list)
    results: list[Any] = field(default_factory=list)


def _when(audit: Any) -> str:
    created = getattr(audit, "created_at", None)
    return created.strftime("%d %b %Y at %H:%M UTC") if created else "earlier"


def _chain_depth(db: Any, audit: Any) -> int:
    """0 for a forward step, 1 for its undo, 2 for its redo, and so on."""
    from fichero_server.models import ActionAudit

    depth, current, seen = 0, audit, set()
    while current is not None and current.inverse_of and current.id not in seen:
        seen.add(current.id)
        depth += 1
        current = db.get(ActionAudit, current.inverse_of)
    return depth


def later_step_in_effect(db: Any, audit: Any) -> Any | None:
    """The first later step still in effect that touched any id ``audit`` touched, or None.

    A later row is in effect when it is not undone and is a forward step or a redo (even depth
    in its chain); a live undo (odd depth) cancels its original and so is not a change.
    """
    from fichero_server.models import ActionAudit

    touched = set(audit.target_ids or [])
    if not touched:
        return None
    if audit.chain_seq is not None:
        later = db._query_where(ActionAudit, _LATER_BY_SEQ, {"seq": audit.chain_seq})
    else:
        later = db._query_where(ActionAudit, _LATER_BY_TIME, {"at": audit.created_at})
    later.sort(key=lambda row: (row.chain_seq is None, row.chain_seq or 0, row.created_at))
    for row in later:
        if row.id == audit.id or row.undone or not touched.intersection(row.target_ids or []):
            continue
        if _chain_depth(db, row) % 2 == 0:
            return row
    return None


def _keeps_later_work(audit: Any) -> bool:
    """The step's action declares that its inverse keeps work done since (`undo_keeps_later_work`): no refusal."""
    try:
        return registry.get(audit.action_name).undo_keeps_later_work
    except ActionNotFoundError:
        return False


def _replay_for(db: Any, audit: Any, ctx: ActionContext) -> tuple[str, dict]:
    """The action and params that take ``audit`` back (undo, or redo when it is an inverse)."""
    from fichero_server.models import ActionAudit

    not_undoable = UndoRefused(
        409, "not-undoable", "This step cannot be taken back.", audit.id
    )
    if audit.inverse_of is not None:
        acting_reg = None
        try:
            acting_reg = registry.get(audit.action_name)
        except ActionNotFoundError:
            pass
        if acting_reg is not None and acting_reg.redo_via_own_invert and acting_reg.invert is not None:
            # #4957: an action that mints a new row on a plain replay redoes through its OWN
            # invert, from its own recorded `after`.
            derived = acting_reg.invert(audit.before, audit.after, ctx)
            if derived is None:
                raise UndoRefused(409, "not-undoable", "This step cannot be redone.", audit.id)
            return derived
        original = db.get(ActionAudit, audit.inverse_of)
        if original is None:
            raise UndoRefused(
                404, "gone",
                "The step this one took back is no longer in the project's history, so it cannot be redone.",
                audit.id,
            )
        from fichero_server.api.routes.system.actions_registry import (
            _refresh_replay_expected_versions,
        )

        return original.action_name, _refresh_replay_expected_versions(original.params, audit.after)
    try:
        reg = registry.get(audit.action_name)
    except ActionNotFoundError:
        raise not_undoable
    if not reg.undoable or reg.invert is None:
        raise not_undoable
    inverse = reg.invert(audit.before, audit.after, ctx)
    if inverse is None:
        raise not_undoable
    return inverse


def _undo_one(db: Any, audit_id: str, ctx: ActionContext) -> Any:
    from fichero_server.models import ActionAudit

    audit = db.get(ActionAudit, audit_id)
    if audit is None:
        raise UndoRefused(
            404, "gone",
            "This step is no longer in the project's history, so it cannot be taken back.",
            audit_id,
        )
    if audit.undone:
        raise UndoRefused(409, "already-undone", "This step was already taken back.", audit_id)
    later = None if _keeps_later_work(audit) else later_step_in_effect(db, audit)
    if later is not None:
        raise UndoRefused(
            409, "changed",
            f"This was changed afterwards by {later.actor} on {_when(later)}. "
            "Taking the earlier step back would overwrite that later work.",
            audit_id,
        )
    replay_name, replay_params = _replay_for(db, audit, ctx)
    try:
        result = registry.invoke(db, replay_name, replay_params, ctx, inverse_of=audit.id)
    except ActionNotFoundError:
        raise UndoRefused(409, "not-undoable", "This step cannot be taken back.", audit_id)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors())
    except ActionRefused as exc:
        raise UndoRefused(409, "changed", str(exc), audit_id) from exc
    except UndoRefused:
        raise
    except HTTPException as exc:
        if exc.status_code == 409:
            # A version lock inside the inverse (`safety.undo.version-is-the-second-lock`).
            words = exc.detail if isinstance(exc.detail, str) else (
                "This has changed since, so the step cannot be taken back."
            )
            raise UndoRefused(409, "changed", words, audit_id) from exc
        raise
    audit.undone = True
    db.save(audit)
    return result


def undo_set(db: Any, audit_ids: list[str], ctx: ActionContext) -> UndoneSet:
    """Take back every row in ``audit_ids``, newest first, all or none."""
    from fichero_server.models import ActionAudit

    unique = list(dict.fromkeys(audit_ids))
    rows = [(db.get(ActionAudit, audit_id), audit_id) for audit_id in unique]

    def newest_first(pair: tuple[Any, str]) -> tuple:
        row = pair[0]
        if row is None:
            return (0, 0, "")
        return (1, row.chain_seq if row.chain_seq is not None else -1, row.created_at.isoformat())

    ordered = [audit_id for _row, audit_id in sorted(rows, key=newest_first, reverse=True)]
    done = UndoneSet()
    with db.transaction():
        for audit_id in ordered:
            result = _undo_one(db, audit_id, ctx)
            done.audit_ids.append(result.audit_id)
            done.results.append(result.result)
            for domain in result.changed_domains:
                if domain not in done.changed_domains:
                    done.changed_domains.append(domain)
    return done

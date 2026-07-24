"""ActionRegistry — the single audited write path (EPIC #1848 / keystone #2013).

See ``docs/contributor/architecture/action_layer.md``. The shapes here are the interface
contract the per-domain sweep (#2014) builds on; do not fork them.

Snapshot approach (design choice **(a)**): the action's ``execute`` returns
``(result, ChangeSpec)`` and the ChangeSpec carries ``before``/``after`` itself.
``invoke`` does NOT call a separate ``snapshot(db, params)`` callable. This is
the cleaner of the two options offered by the plan because ``execute`` can embed
ids it *produced* (e.g. the ``EntityMergeAudit`` id that the merge undo needs)
into ``after`` — a blind before/after snapshot taken by ``invoke`` could not.

``invoke`` contract:
  1. resolve the action (unknown name -> :class:`ActionNotFoundError`)
  2. validate ``raw_params`` into the action's Pydantic ``params_model``
  3. run ``execute(db, params, ctx)`` -> ``(result, ChangeSpec)``
  4. write an :class:`fichero.models.ActionAudit` row — **NOT best-effort**
     (if the audit cannot be written the action fails)
  5. ``emit_change`` to the observable layer — **best-effort** (never raises)
  6. return an :class:`ActionResult`
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol, runtime_checkable

from pydantic import BaseModel

logger = logging.getLogger(__name__)

EmitFn = Callable[["ActionContext", "ChangeSpec"], None]


# =============================================================================
# Context, result, and the change spec returned by execute()
# =============================================================================


@dataclass
class ActionContext:
    """Who/where/why an action is running.

    ``library_path`` is required for ``emit_change`` (the observable layer is
    keyed by library); routes populate it from the ``X-Fichero-Library-Path``
    header. ``actor``/``origin_window`` flow straight into the audit + change
    event. ``run_id`` ties the action to an AI run (#1832).

    ``on_progress`` / ``on_document`` are OPTIONAL streaming hooks a route can
    attach so a long-running action (folder ingest) can report progress and
    per-item results back to the caller WHILE it runs — not only in the trailing
    ``ChangeSpec``. The action layer stays the one audited write path; these
    callbacks are read-only side-channels for live UI updates (#4065/#4067).
    Default ``None`` so chat-tools / App Intents / tests that don't care about
    streaming are untouched.
    """

    actor: str = "system"
    origin_window: str | None = None
    run_id: str | None = None
    library_path: str | None = None
    is_bootstrap: bool = False
    on_progress: "Callable[[int, int], None] | None" = None
    on_document: "Callable[[Any], None] | None" = None


@dataclass
class ActionResult:
    """What ``invoke`` returns to a caller (route / chat tool / test)."""

    ok: bool
    result: Any
    audit_id: str
    changed_domains: list[str]


@dataclass
class ChangeSpec:
    """What ``execute`` hands back to ``invoke`` so it can audit + broadcast.

    ``before``/``after`` are JSON-able dicts (``model_dump(mode="json")``) and
    become the audit's undo payload. ``emit_type`` + the typed id-lists feed a
    single :class:`fichero.api.change_stream.ChangeEvent`; carrying every touched
    domain's ids in one typed event matches the proven observable-layer pattern
    (the existing merge emits one ``entity.merged`` carrying both entity + claim
    ids). ``domains`` populates :attr:`ActionResult.changed_domains`.
    """

    domains: list[str]
    target_ids: list[str] = field(default_factory=list)
    before: dict | None = None
    after: dict | None = None
    emit_type: str | None = None
    entity_ids: list[str] = field(default_factory=list)
    claim_ids: list[str] = field(default_factory=list)
    document_ids: list[str] = field(default_factory=list)
    artifact_ids: list[str] = field(default_factory=list)
    citation_ids: list[str] = field(default_factory=list)
    reference_ids: list[str] = field(default_factory=list)
    interpretation_ids: list[str] = field(default_factory=list)
    emit_fn: EmitFn | None = None


# Type aliases for the action callables.
ExecuteFn = Callable[[Any, BaseModel, ActionContext], "tuple[Any, ChangeSpec]"]
# invert(before, after, ctx) -> (inverse_action_name, inverse_raw_params) | None
InvertFn = Callable[
    [dict | None, dict | None, ActionContext], "tuple[str, dict] | None"
]


@runtime_checkable
class Action(Protocol):
    """Structural type for a registered action (the execute callable)."""

    def __call__(
        self, db: Any, params: BaseModel, ctx: ActionContext
    ) -> tuple[Any, ChangeSpec]: ...


@dataclass
class ActionRegistration:
    """One entry in the registry."""

    name: str
    params_model: type[BaseModel]
    execute: ExecuteFn
    domains: list[str]
    undoable: bool = False
    invert: InvertFn | None = None
    atomic: bool = True
    # Whether this action only READS state (no domain mutation). The action layer
    # is otherwise the write path — every registered action is assumed to mutate
    # unless it explicitly opts in here. The chat-tools agent loop (#1847) uses
    # this bit to expose/dispatch ONLY read-only actions while mutations stay
    # gated behind a later write-policy review (EPIC #1848). Default False =
    # mutating, so existing actions are untouched and fail safe.
    read_only: bool = False


class ActionNotFoundError(KeyError):
    """Raised by ``invoke``/``get`` for an unregistered action name."""


# =============================================================================
# The registry
# =============================================================================


class ActionRegistry:
    """Process-global map of ``<domain>.<verb>`` -> :class:`ActionRegistration`."""

    def __init__(self) -> None:
        self._actions: dict[str, ActionRegistration] = {}

    def register(self, reg: ActionRegistration) -> ActionRegistration:
        """Register (or overwrite) an action. Overwrite is intentional so a
        module re-imported under test re-registers idempotently."""
        self._actions[reg.name] = reg
        logger.debug("action registered: %s (undoable=%s)", reg.name, reg.undoable)
        return reg

    def get(self, name: str) -> ActionRegistration:
        try:
            return self._actions[name]
        except KeyError as exc:
            raise ActionNotFoundError(name) from exc

    def names(self) -> list[str]:
        return sorted(self._actions)

    def all(self) -> list[ActionRegistration]:
        return [self._actions[n] for n in self.names()]

    # -- the one write choke point -------------------------------------------

    def invoke(
        self,
        db: Any,
        name: str,
        raw_params: dict,
        ctx: ActionContext,
        *,
        inverse_of: str | None = None,
    ) -> ActionResult:
        """Validate -> execute -> audit -> emit. The single mutation path.

        ``inverse_of`` is set by the undo endpoint when this invocation IS the
        inverse of an earlier action: it records the original audit's id on the
        new row so that undoing THIS row (undo-of-undo / redo) can replay the
        original forward action. Ordinary callers leave it ``None``.
        """
        from fichero.actions.audit_chain import save_chained_audit
        from fichero.models import ActionAudit  # local import: avoid cycle at module load

        reg = self.get(name)  # ActionNotFoundError if unknown
        params = reg.params_model.model_validate(raw_params)

        from fichero.security import authz

        target_ids = authz.target_ids_from_params(params)
        if not ctx.is_bootstrap:
            if not target_ids:
                authz.assert_can_write(ctx.actor, ctx.library_path)
            for target_id in target_ids:
                authz.assert_can_write(ctx.actor, ctx.library_path, target_id)

        if reg.atomic:
            with db.transaction():
                result, spec = reg.execute(db, params, ctx)

                # Audit write is NOT best-effort: if it fails the action fails. The
                # before/after captured by execute ARE the undo payload.
                audit = ActionAudit(
                    action_name=name,
                    actor=ctx.actor,
                    target_ids=list(spec.target_ids),
                    params=params.model_dump(mode="json"),
                    before=spec.before,
                    after=spec.after,
                    run_id=ctx.run_id,
                    inverse_of=inverse_of,
                )
                save_chained_audit(db, audit)
        else:
            result, spec = reg.execute(db, params, ctx)
            audit = ActionAudit(
                action_name=name,
                actor=ctx.actor,
                target_ids=list(spec.target_ids),
                params=params.model_dump(mode="json"),
                before=spec.before,
                after=spec.after,
                run_id=ctx.run_id,
                inverse_of=inverse_of,
            )
            save_chained_audit(db, audit)

        # Broadcast to the observable layer — best-effort, never breaks the action.
        self._emit(ctx, spec)

        return ActionResult(
            ok=True,
            result=result,
            audit_id=audit.id,
            changed_domains=list(spec.domains),
        )

    def _emit(self, ctx: ActionContext, spec: ChangeSpec) -> None:
        if spec.emit_fn is not None:
            try:
                spec.emit_fn(ctx, spec)
            except Exception as exc:  # pragma: no cover - emit is already best-effort
                logger.debug("action custom emit_change failed (ignored): %s", exc)
            return
        if not ctx.library_path or not spec.emit_type:
            return
        from fichero.api.change_stream import (
            emit_change,
        )  # local: avoid cycle at module load

        try:
            emit_change(
                ctx.library_path,
                type=spec.emit_type,
                entity_ids=spec.entity_ids,
                claim_ids=spec.claim_ids,
                document_ids=spec.document_ids,
                artifact_ids=spec.artifact_ids,
                citation_ids=spec.citation_ids,
                reference_ids=spec.reference_ids,
                interpretation_ids=spec.interpretation_ids,
                run_id=ctx.run_id,
                actor=ctx.actor,
                origin_window=ctx.origin_window,
                origin_user=ctx.actor,
            )
        except Exception as exc:  # pragma: no cover - emit is already best-effort
            logger.debug("action emit_change failed (ignored): %s", exc)


# Process-global singleton — THE registry.
registry = ActionRegistry()


def action(
    name: str,
    params_model: type[BaseModel],
    *,
    domains: list[str],
    undoable: bool = False,
    invert: InvertFn | None = None,
    atomic: bool = True,
    read_only: bool = False,
) -> Callable[[ExecuteFn], ExecuteFn]:
    """Decorator: register ``fn`` as the action ``name``.

    ``fn`` must have signature ``(db, params, ctx) -> (result, ChangeSpec)``.

    ``read_only=True`` marks an action that only reads state; the chat-tools
    agent loop (#1847) only exposes/dispatches these while mutations stay gated.
    """

    def decorator(fn: ExecuteFn) -> ExecuteFn:
        registry.register(
            ActionRegistration(
                name=name,
                params_model=params_model,
                execute=fn,
                domains=list(domains),
                undoable=undoable,
                invert=invert,
                atomic=atomic,
                read_only=read_only,
            )
        )
        return fn

    return decorator

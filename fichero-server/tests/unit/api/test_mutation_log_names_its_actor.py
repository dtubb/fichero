"""Every mutation record must name who made it (#4415).

`MutationLog.created_by` defaults to `"human"`. Five construction sites never
passed it, so those rows said `human` because of a field default — not because
anything established a human did it. Right by luck.

That matters more than ordinary attribution sloppiness, because #4415's
incremental catalogue uses "has a mutation-log entry" as the signal for *this
row was curated, do not regenerate over it*. A wrong actor there does not
mislead a reader; it decides whether the user's work survives a re-run.

The second half is the MCP path. An agent editing an entity's name or aliases
is doing curation, and the architecture says an agent is a user account making
audited edits — but the upsert route updated in place with no mutation record
at all, so that edit was invisible to exactly the check meant to protect it.
The row's `created_by` names the CREATOR, not the editor, so it could not
stand in.

Nothing here skips.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path


SRC = Path(__file__).parents[3] / "src" / "fichero_server"


def _mutation_log_calls(tree: ast.AST):
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
        if name == "MutationLog":
            yield node


class TestEveryCallSiteNamesItsActor:
    """The guardrail. Parsed, not grepped — a substring check would match the
    prose in these very docstrings and fail for the wrong reason."""

    def test_no_mutation_log_is_written_without_created_by(self):
        offenders: list[str] = []
        for path in sorted(SRC.rglob("*.py")):
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except SyntaxError:  # pragma: no cover - defensive
                continue
            for call in _mutation_log_calls(tree):
                if not any(k.arg == "created_by" for k in call.keywords):
                    offenders.append(
                        f"{path.relative_to(SRC)}:{call.lineno}"
                    )

        assert offenders == [], (
            "MutationLog written without naming its actor at "
            f"{offenders}. `created_by` defaults to 'human', so these rows "
            "claim a human edit whoever made it — and #4415's incremental "
            "runner reads a mutation-log entry as 'curated, do not "
            "regenerate'. If a call site cannot name its actor, that is a bug "
            "at that site."
        )

    def test_the_guardrail_would_catch_an_omission(self):
        """Proving the check fires, rather than trusting a green run."""
        tree = ast.parse(
            "MutationLog(entity_type='X', entity_id='1', operation=op)"
        )
        calls = list(_mutation_log_calls(tree))
        assert len(calls) == 1
        assert not any(k.arg == "created_by" for k in calls[0].keywords), (
            "the detector does not recognise an omitted actor, so a green run "
            "of the test above would prove nothing"
        )


class TestTheCurationHelpersRequireAnActor:
    """Required parameter, not an optional one with a default — an optional
    actor is the same defect with extra steps."""

    def test_entity_curation_helper_requires_actor(self):
        from fichero_server.api.routes.kg.entity_curation import (
            _log_entity_curation_mutation,
        )

        parameter = inspect.signature(_log_entity_curation_mutation).parameters["actor"]
        assert parameter.default is inspect.Parameter.empty, (
            "`actor` has a default, so a caller can still omit it and get a "
            "silently-wrong attribution"
        )

    def test_claim_curation_helper_requires_actor(self):
        from fichero_server.api.routes.claim.curation import (
            _log_claim_curation_mutation,
        )

        parameter = inspect.signature(_log_claim_curation_mutation).parameters["actor"]
        assert parameter.default is inspect.Parameter.empty

    def test_the_claim_impls_require_an_actor_too(self):
        """These are called from the audited action layer, which already
        carries `ctx.actor` — so the mutation log and the audit record agree
        by construction rather than by coincidence."""
        from fichero_server.api.routes.claim.curation import (
            batch_set_claim_curation_state_impl,
            prune_trivial_claims_impl,
        )

        for func in (batch_set_claim_curation_state_impl, prune_trivial_claims_impl):
            assert "actor" in inspect.signature(func).parameters, (
                f"{func.__name__} does not take an actor, so the mutation log "
                "it writes cannot name one"
            )


class TestTheAgentPathIsAudited:
    def test_the_mcp_entity_upsert_takes_an_actor(self):
        from fichero_server.api.routes.mcp import tools

        parameters = inspect.signature(tools.mcp_knowledge_entity_upsert).parameters
        assert "actor" in parameters, (
            "the MCP upsert cannot name who edited, so an agent's curation is "
            "indistinguishable from generated output (#4415)"
        )

    def test_the_mcp_upsert_calls_registry_invoke_not_a_bespoke_log(self):
        """#4866: the in-place update used to be the dangerous branch --
        real curation (canonical_name, aliases, description) via a
        best-effort `MutationLog` row and nothing else. It is now a thin
        caller of the SAME audited `entity.create`/`entity.update` actions
        the typed HTTP route uses, so `ActionAudit` (not a bespoke helper)
        is the trail -- see `test_mcp_kg_write_attribution.py` for the
        behavioral proof (audit row, real actor, undo)."""
        from fichero_server.api.routes.mcp import tools

        source = inspect.getsource(tools.mcp_knowledge_entity_upsert)
        assert "registry.invoke(" in source
        assert "_log_mcp_entity_mutation" not in source, (
            "the bespoke MutationLog helper was removed -- ActionAudit is "
            "the one trail now, not two"
        )

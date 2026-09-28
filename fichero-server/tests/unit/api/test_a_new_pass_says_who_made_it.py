"""A new pass's maker comes from how the request arrived -- the ONE rule (`provenance_kind_from_ctx`)
every source-model write uses -- not from a run id the caller happened to put in the params.

WHY: `segment.pass_create` had its own copy of the rule that read only `params.run_id`. A run that
created a pass under its OWN context (ctx.run_id, the way workflows call actions) got a pass
stamped `human` -- the "machine claims stored as human" class (#4868/#4869) -- and that pass then
ranked as a person's work: its segments counted as touched by a person, and a machine's
georeference outranked an imported one (found building maps C1, #5122). An agent's pass through
MCP was never `agent`. If this regresses, a machine's pass is a person's again.
"""

from __future__ import annotations

import fichero_server.api.main  # noqa: F401  (registers every action)
from fichero_server.actions.registry import ActionContext, registry
from fichero_server.models import DocType, Document, FileType, SegmentPass, Status


def _pass(db, ctx, **params) -> SegmentPass:
    doc = Document(name="p.jpg", doc_type=DocType.file, file_type=FileType.image, path="/p/p.jpg",
                   status=Status.completed)
    db.save(doc)
    result = registry.invoke(db, "segment.pass_create", {"document_id": doc.id, "name": "a pass", **params}, ctx)
    return db.get(SegmentPass, result.result["id"])


def test_a_run_creating_a_pass_under_its_own_context_is_a_machine(db):
    row = _pass(db, ActionContext(actor="kraken", run_id="run-7", is_bootstrap=True))
    assert (row.provenance_kind.value, row.run_id) == ("workflow", "run-7")


def test_an_agent_through_mcp_is_an_agent(db):
    assert _pass(db, ActionContext(actor="assistant", via_mcp=True, is_bootstrap=True)).provenance_kind.value == "agent"


def test_a_person_is_a_person_and_a_named_run_is_still_a_machine(db):
    person = ActionContext(actor="historian", is_bootstrap=True)
    assert _pass(db, person).provenance_kind.value == "human"
    assert _pass(db, person, run_id="run-8").provenance_kind.value == "workflow"

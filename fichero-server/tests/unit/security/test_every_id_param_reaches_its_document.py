"""Every `*_id` an action or route accepts reaches its document for access control, or says why it
has none (#5177).

WHY: `authz` checks the ids a request names. A document id walks up its folders; an id of a kind in
`_DOCUMENT_ID_RESOLVERS` is resolved to its document first; ANY OTHER id is checked as itself -- so a
deny on a page silently never reaches it. That is how an editor denied a page could still withdraw
its hand attribution (b75cac9ef), and it was the whole class: a reading, a reading order and its
entries, a pass choice, an annotation, a note, a typed link... each could be changed by naming its id.
This guard fails on a NEW `*_id` nobody has declared, on a declared record kind with no resolver, and
on a schema model that points at a document and is neither resolved nor declared library-scoped --
so the next kind cannot reopen it quietly.

Its own fixtures prove it fires (a guard that cannot fail is not a guard).
"""

from __future__ import annotations

import re
import typing

from fastapi.routing import APIRoute
from pydantic import BaseModel

import fichero_server.api.main as api_main
from fichero_server.actions.registry import registry
from fichero_server.db import Database
from fichero_server.security import authz
from fichero_server.security.authz_kinds import ID_PARAMS, LIBRARY, LIBRARY_SCOPED_MODELS, RECORD

#: A field of one of these names means the model belongs to (or may belong to) a document.
DOCUMENT_POINTERS = ("document_id", "segment_id", "page_id", "pass_id", "order_id", "match_id",
                     "source_document_id", "folder_id", "target_id", "from_id")


def _is_id(name: str) -> bool:
    return name == "id" or name.endswith("_id") or name.endswith("_ids")


def id_params_in_use() -> dict[str, set[str]]:
    """Every `*_id` name in a registered action's params (nested models too) or a route's path/query."""
    names: dict[str, set[str]] = {}

    def walk(model: type[BaseModel], where: str, depth: int = 0) -> None:
        if depth > 6:
            return
        for name, field in model.model_fields.items():
            if _is_id(name):
                names.setdefault(name, set()).add(where)
            for arg in (field.annotation, *typing.get_args(field.annotation)):
                for inner in (typing.get_args(arg) or (arg,)):
                    if isinstance(inner, type) and issubclass(inner, BaseModel):
                        walk(inner, where, depth + 1)

    for action_name, spec in registry._actions.items():
        params = getattr(spec, "params_model", None) or getattr(spec, "params", None)
        if isinstance(params, type) and issubclass(params, BaseModel):
            walk(params, f"action {action_name}")
    from tests.route_inventory import served_routes

    for route in served_routes(api_main.app):  # every served route, not app.routes (FastAPI 0.141, #5674)
        if isinstance(route, APIRoute):
            for param in route.dependant.path_params + route.dependant.query_params:
                if _is_id(param.name):
                    names.setdefault(param.name, set()).add(f"route {route.path}")
    return names


def problems(
    in_use: dict[str, set[str]],
    declared: dict[str, tuple[str, object]],
    resolved: set[str],
    schema: dict[str, set[str]],
    library_models: dict[str, str],
) -> list[str]:
    """What is wrong, as sentences. `resolved` = model names with a resolver (plus `Document`);
    `schema` = model name -> its field names."""
    out: list[str] = []
    for name in sorted(set(in_use) - set(declared)):
        out.append(f"`{name}` ({', '.join(sorted(in_use[name])[:3])}) is not declared in security/authz_kinds.py")
    for name, (how, what) in sorted(declared.items()):
        if how == RECORD:
            for model in what:  # type: ignore[union-attr]
                if model != "*" and model not in resolved:
                    out.append(f"`{name}` names {model}, which has no resolver to its document")
        elif how == LIBRARY and not str(what).strip():
            out.append(f"`{name}` is declared library-scoped with no reason")
    for model, fields in sorted(schema.items()):
        if model in resolved or model == "Document" or not (set(fields) & set(DOCUMENT_POINTERS)):
            continue
        if model not in library_models:
            out.append(f"{model} points at a document ({', '.join(sorted(set(fields) & set(DOCUMENT_POINTERS)))}) "
                       "but has no resolver and is not declared library-scoped")
    return out


def _resolved_names() -> set[str]:
    return {model.__name__ for model, _ in authz._DOCUMENT_ID_RESOLVERS} | {"Document"}


def _schema() -> dict[str, set[str]]:
    return {model.__name__: set(model.model_fields) for model in Database._all_schema_models(None)}


def test_every_id_reaches_its_document_or_says_why_not():
    found = problems(id_params_in_use(), ID_PARAMS, _resolved_names(), _schema(), LIBRARY_SCOPED_MODELS)
    assert found == [], "\n".join(found)


def test_the_enumeration_sees_the_ids_it_must():
    """A guard over an empty list passes vacuously: these are real ids in real actions and routes."""
    in_use = id_params_in_use()
    assert {"segment_id", "representation_id", "order_id", "fact_id", "attribution_id", "pass_id"} <= set(in_use)
    assert len(in_use) > 100


class TestTheGuardFires:
    """Negative fixtures: each kind of hole is reported. Positive: a clean declaration is clean."""

    RESOLVED = {"Document", "Segment"}
    SCHEMA = {"Segment": {"id", "document_id"}, "Widget": {"id", "name"}}

    def test_a_clean_declaration_is_clean(self):
        assert problems({"segment_id": {"a"}}, {"segment_id": (RECORD, ("Segment",))},
                        self.RESOLVED, self.SCHEMA, {}) == []

    def test_an_undeclared_id_is_reported(self):
        found = problems({"gadget_id": {"action gadget.poke"}}, {}, self.RESOLVED, self.SCHEMA, {})
        assert found and "`gadget_id`" in found[0] and "not declared" in found[0]

    def test_a_record_kind_without_a_resolver_is_reported(self):
        found = problems({"reading_id": {"a"}}, {"reading_id": (RECORD, ("ContentRepresentation",))},
                         self.RESOLVED, self.SCHEMA, {})
        assert found == ["`reading_id` names ContentRepresentation, which has no resolver to its document"]

    def test_a_model_pointing_at_a_document_must_be_resolved_or_declared(self):
        schema = {**self.SCHEMA, "Stamp": {"id", "document_id"}}
        assert problems({}, {}, self.RESOLVED, schema, {}) == [
            "Stamp points at a document (document_id) but has no resolver and is not declared library-scoped"]
        assert problems({}, {}, self.RESOLVED, schema, {"Stamp": "a reason"}) == []


def test_revert_copys_documents_are_write_checked_by_their_ids():
    """`classification.revert_copy` names the documents it re-assigns inside `documents` (dumped rows): the write check collects
    the `id` of every row, so a person denied one of them cannot revert a copy that would change it."""
    from fichero_server.api.routes.document.classifications import ClassificationRevertCopyParams
    from fichero_server.security.authz import target_ids_from_params

    params = ClassificationRevertCopyParams(value_ids=["v1"], documents=[{"id": "d1", "parent_id": "f1"}, {"id": "d2"}])
    assert {"d1", "f1", "d2"} <= set(target_ids_from_params(params))


#: A route handler whose source holds one of these asks authz about the ids it was given (or runs an audited action, whose registry check
#: reads every id in the params). A word in the source is NOT proof it works: each such route has a denial test through the real stack
#: (`test_body_id_routes_check_their_documents_6320.py`, `test_read_exports_check_the_body_ids_6320.py`).
_CHECKS = ("registry.invoke", "assert_library_", "readable_documents", "_read_checked", "read_check", "write_check")

#: Routes whose body holds an id and whose handler shows no check above, each CLEARED by someone who read it, with the mechanism. A new
#: route is not on this list: it fails until it checks its ids or is read and cleared here (#6320).
BODY_IDS_CLEARED: dict[str, str] = {
    "/api/actions/audit/undo": "undo re-runs the recorded inverse through the action layer, which checks every id; an AuthorizationError is refused in words",
    "/api/actions/import": "`new_id` names the action being imported, not a document",
    "/api/agents/write": "no library and no database: adds an in-memory PolicyEngine record nothing else reads (reviewed 2026-11-01)",
    "/api/auth/challenge": "`client_id` is a device, not a document",
    "/api/auth/local-clients/register": "`request_id` is a pairing request, not a document",
    "/api/auth/sign-in": "`client_id` is a device, not a document",
    "/api/bibliography/export.bib": "listed in authz.SCOPED_LIBRARY_READ_ROUTES: the handler filters its documents through readable_rows",
    "/api/documents/relink-originals/plan": "`_checked_root` requires the ingest owner (403 for an editor, with or without a decoy)",
    "/api/documents/transfer/incoming": "`transfer_id` is a transfer offer; the copy itself runs through the action layer",
    "/api/find-documents/proposals/{proposal_id}/split": "the helper `_adjust` runs registry.invoke (403 for an editor with a deny on the page)",
    "/api/folders/{entity_type}/move": "moves workflows, searches and conversations between folder paths; no document id",
    "/api/hands/attributions": "the helper `_answer` runs registry.invoke (403 for an editor with a deny and for a scoped editor with a decoy)",
    "/api/hands/attributions/many": "the helper `_answer` runs registry.invoke; the segments resolve to their documents",
    "/api/hands/attributions/withdraw-many": "the helper `_answer` runs registry.invoke; attribution ids resolve to their documents",
    "/api/hpc/clusters": "`cluster_id` names a cluster, not a document",
    "/api/hpc/clusters/{cluster_id}/dry-run-submit": "a dry run: `run_id` and `workflow_id` are workflow machinery, no document is read",
    "/api/ingest/files": "`_require_ingest_owner`: the ingest owner only",
    "/api/local-inference/profiles/validate": "a model profile, not a document",
    "/api/migrations/rollback": "`run_id` is a migration's audit id (library maintenance, no document id); NOTE: the handler has no owner check of its own",
    "/api/notes/{note_id}/links": "links two note records and returns the ids; no document text comes back",
    "/api/pair/code": "`_owner_for_pairing`: the owner only",
    "/api/policies/orchestration/{rule_id}": "an orchestration policy rule: configuration",
    "/api/search/saved/reorder": "saved-search order: configuration",
    "/api/settings/model-profiles": "a model profile: configuration",
    "/api/chat/conversations/reorder": "conversation order: configuration",
    "/api/integrations/{app_name}/import": "`external_id` is the other app's item; the handler imports into a path on the machine, no library document is named",
    "/api/kg/entity-curation/enrich/preview": "`entity_id` is a knowledge entity; it fetches statements from Wikidata and writes nothing",
    "/api/kg/predictions/heuristic": "no body id is read as a document: the library's claims, which a scoped person is refused (library-level read) -- an editor with a deny sees them all: OPEN, #6325",
    "/api/model-comparison/compare-node/apply": "writes a model choice into a workflow node: configuration",
    "/api/providers/refs": "`provider_id` names a provider: configuration",
    "/api/providers/{provider_id}/models": "`model_id` and `provider_id` name a model and a provider: configuration",
    "/api/research/tools/document-fetch": "fetches a URL; `project_id` is a project, and what it saves goes through the ingest owner's import",
    "/api/research/tools/web-search": "a web search; `source_ids` only filter the answer's citations",
    "/api/schedules": "`workflow_id` names the workflow to schedule: configuration (a schedule's inputs: OPEN, #6325)",
    "/api/schedules/{schedule_id}": "`workflow_id` names the workflow to schedule: configuration (a schedule's inputs: OPEN, #6325)",
    "/api/triggers": "`workflow_id` names the workflow to trigger: configuration (a trigger's inputs: OPEN, #6325)",
    "/api/triggers/{trigger_id}": "`workflow_id` names the workflow to trigger: configuration (a trigger's inputs: OPEN, #6325)",
    "/api/workflows": "`id` is the new workflow's own id: a recipe, not a document",
    "/api/workflows/import": "imports a workflow file: a recipe, not a document",
    "/api/workflows/reorder": "workflow order: configuration",
    "/api/workflows/{workflow_id}": "`id` is the workflow's own id: a recipe, not a document",
}


def _body_ids(annotation) -> set[str] | None:
    """The id-like fields of the model(s) a route's body is (unwrapping Optional/list/Annotated); None when the body is no model."""
    found: set[str] = set()
    seen_model = False
    stack = [annotation]
    while stack:
        item = stack.pop()
        if isinstance(item, type) and issubclass(item, BaseModel):
            seen_model = True
            found |= {f for f in item.model_fields if _is_id(f)}
        else:
            stack.extend(typing.get_args(item))
    return found if seen_model else None


def body_routes_without_a_check() -> set[str]:
    """Routes whose BODY holds an id (any `*_id`/`*_ids`, or a body that is no model at all): the read/write dependency reads only
    the path and query, so a body id is checked only if the handler does it."""
    import inspect

    from tests.route_inventory import served_routes

    found: set[str] = set()
    for route in served_routes(api_main.app):
        if not isinstance(route, APIRoute) or not route.body_field:
            continue
        ids = _body_ids(route.body_field.field_info.annotation)
        if ids is not None and not ids:
            continue
        try:
            source = inspect.getsource(route.endpoint)
        except (OSError, TypeError):
            continue
        if not any(mark in source for mark in _CHECKS):
            found.add(route.path)
    return found


def test_a_route_with_an_id_in_its_body_checks_it_or_says_why_it_need_not():
    found = body_routes_without_a_check()
    unread = found - set(BODY_IDS_CLEARED)
    assert unread == set(), (
        "a route holds an id in its body and its handler shows no check (the dependency sees only path and query). Check it with "
        f"read_check / write_check (api/main.py) and add a denial test, or read it and clear it in BODY_IDS_CLEARED: {sorted(unread)}")
    served = {r.path for r in served_routes_all()}
    gone = {p for p in BODY_IDS_CLEARED if p not in served}
    assert gone == set(), f"cleared routes that are no longer served: {sorted(gone)}"


def served_routes_all():
    from tests.route_inventory import served_routes

    return [r for r in served_routes(api_main.app) if isinstance(r, APIRoute)]


def test_an_open_entry_names_its_issue():
    """A route cleared as OPEN is a known hole, not a pass: it must say which issue holds it."""
    bare = [path for path, why in BODY_IDS_CLEARED.items() if "OPEN" in why and not re.search(r"#\d{4,}", why)]
    assert bare == [], bare

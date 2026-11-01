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


#: What a handler's CODE (no comment, no docstring) must call, or depend on, to count as checking the ids it is given. A word in a
#: comment proves nothing (it did: `execute`, `chat` and `compare-workflow` held the mark and an unchecked id, review 3).
_CHECKS = re.compile(
    r"\b(?:registry\.invoke|assert_library_\w+_every|assert_library_\w+\(.{0,200}?named=|_check_chain|readable_documents|readable_rows|_read_checked|read_check|write_check|owner_check|"
    r"_owner_only|_require_owner_or_bootstrap|get_action_store_for_write|get_scheduler_for_write|get_file_watcher_for_write|_check_documents)(?![A-Za-z_])")

#: The checks written by hand in a handler (the registry's own check on an action's params has its tests where the action lives).
_HAND_CHECKS = re.compile(r"\b(?:read_check|write_check|owner_check|assert_library_\w+_every|assert_library_\w+\(.{0,200}?named=|_check_chain|_owner_only|get_action_store_for_write|get_scheduler_for_write|get_file_watcher_for_write|_check_documents)(?![A-Za-z_])")

#: A body field that names documents, whatever it is called: `*_id`/`*_ids`, and the containers a workflow, a chat or a recipe
#: carries them in (the old scan saw only `*_id`, so `ids`, `inputs`, `selection` and `pages` went unread).
_DOCUMENT_CONTAINERS = {"ids", "inputs", "selection", "pages", "items", "documents", "batch_items", "pinned_inputs", "inputs_template"}

NOT_DOC, VIA, OPEN, PUBLIC = "NOT_DOC", "VIA", "OPEN", "PUBLIC"

#: Routes whose body holds an id-like field and whose handler shows no check, each CLEARED by someone who read it:
#:   NOT_DOC (reason): no document is named; the reason says what the field is.
#:   VIA (reason, helper): the check is in a helper the handler calls; the guard looks for the helper's name in the route's module.
#:   OPEN (reason): a known hole; the reason names its issue (#nnnn).
#: A new route is not on this list: it fails until it checks its ids or is read and cleared here. An entry whose route gains a check
#: fails too (take it off). Every route that checks needs a denial test through the real stack: see `DENIAL_TEST_FILES`.
BODY_IDS_CLEARED: dict[str, tuple] = {
    "/api/actions/audit/undo": (VIA, "undo re-runs the recorded inverse through the action layer, which checks every id; an AuthorizationError is refused in words", "registry.invoke"),
    "/api/agents/write": (NOT_DOC, "no library and no database: adds an in-memory PolicyEngine record nothing else reads (reviewed 2026-11-01)"),
    "/api/auth/challenge": (NOT_DOC, "`client_id` is a device, not a document"),
    "/api/auth/local-clients/register": (NOT_DOC, "`request_id` is a pairing request, not a document"),
    "/api/auth/sign-in": (NOT_DOC, "`client_id` is a device, not a document"),
    "/api/documents/relink-originals/plan": (VIA, "`_checked_root` requires the ingest owner (403 for an editor, with or without a decoy)", "_checked_root"),
    "/api/documents/transfer/incoming": (VIA, "`transfer_id` is a transfer offer; the copy itself runs through the action layer", "registry.invoke"),
    "/api/find-documents/proposals/{proposal_id}/split": (VIA, "the helper `_adjust` runs registry.invoke (403 for an editor with a deny on the page)", "registry.invoke"),
    "/api/folders/{entity_type}/move": (NOT_DOC, "moves workflows, searches and conversations between folder paths; no document id"),
    "/api/hands/attributions": (VIA, "the helper `_answer` runs registry.invoke (403 for an editor with a deny and for a scoped editor with a decoy)", "registry.invoke"),
    "/api/hands/attributions/many": (VIA, "the helper `_answer` runs registry.invoke; the segments resolve to their documents", "registry.invoke"),
    "/api/hands/attributions/withdraw-many": (VIA, "the helper `_answer` runs registry.invoke; attribution ids resolve to their documents", "registry.invoke"),
    "/api/ingest/files": (VIA, "`_require_ingest_owner`: the ingest owner only", "_require_ingest_owner"),
    "/api/local-inference/profiles/validate": (NOT_DOC, "a model profile, not a document"),
    "/api/notes/{note_id}/links": (NOT_DOC, "links two note records and returns the ids; no document text comes back"),
    "/api/pair/code": (VIA, "`_owner_for_pairing`: the owner only", "_owner_for_pairing"),
    "/api/search/saved/reorder": (NOT_DOC, "saved-search order: configuration"),
    "/api/chat/conversations/reorder": (NOT_DOC, "conversation order: configuration"),
    "/api/kg/entity-curation/enrich/preview": (NOT_DOC, "`entity_id` is a knowledge entity; it fetches statements from Wikidata and writes nothing"),
    "/api/kg/predictions/heuristic": (VIA, "every route under /api/kg depends on `whole_library_reader_only`: refused (403) to a caller whose reads differ page by page", "whole_library_reader_only"),
    "/api/model-comparison/compare-node/apply": (NOT_DOC, "writes a model choice into a workflow node: configuration"),
    "/api/providers/refs": (NOT_DOC, "`provider_id` names a provider: configuration"),
    "/api/research/tools/web-search": (NOT_DOC, "a web search; `source_ids` only filter the answer's citations"),
    "/api/agent-memory": (OPEN, "found unread by the widened scan (nested `document_id`): not read, #6325", ),
    "/api/agent-memory/{note_id}": (OPEN, "found unread by the widened scan (nested `document_id`): not read, #6325"),
    "/api/documents/{document_id}/readings/compare": (OPEN, "found unread by the widened scan: not read, #6325"),
    "/api/recipes/assemble": (OPEN, "found unread by the widened scan (`pages`): not read, #6325"),
    "/api/workflows": (NOT_DOC, "`id` is the new workflow's own id: a recipe, not a document"),
    "/api/workflows/import": (NOT_DOC, "imports a workflow file: a recipe, not a document"),
    "/api/workflows/reorder": (NOT_DOC, "workflow order: configuration"),
    "/api/workflows/{workflow_id}": (NOT_DOC, "`id` is the workflow's own id: a recipe, not a document"),
}


#: Where a route's denial test lives: a route that checks must be named in one of these (an editor with a deny, and a person shared one
#: folder with a decoy id in the query, both refused). The match is on the route's last fixed segment: weak, so the test is read, not trusted.
DENIAL_TEST_FILES = ("test_body_id_routes_check_their_documents_6320.py", "test_read_exports_check_the_body_ids_6320.py",
                     "test_holds_close_6320.py")


def _body_fields(annotation) -> set[str] | None:
    """The id-like or document-holding fields of the model(s) a body is, nested ones too; None when the body is no model."""
    found: set[str] = set()
    seen_model = False
    stack, done = [annotation], set()
    while stack:
        item = stack.pop()
        if isinstance(item, type) and issubclass(item, BaseModel):
            seen_model = True
            if item in done:
                continue
            done.add(item)
            found |= {f for f in item.model_fields if _is_id(f) or f in _DOCUMENT_CONTAINERS}
            stack.extend(item.model_fields[f].annotation for f in item.model_fields)
        else:
            stack.extend(typing.get_args(item))
    return found if seen_model else None


def _code_of(endpoint) -> str:
    """The handler's signature and body as code: comments and the docstring gone."""
    import ast
    import inspect
    import textwrap

    tree = ast.parse(textwrap.dedent(inspect.getsource(endpoint)))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and ast.get_docstring(node) is not None:
            node.body = node.body[1:] or [ast.Pass()]
    return ast.unparse(tree)


def body_routes() -> dict[str, tuple[bool, str, bool]]:
    """Every route whose body holds an id-like or document-holding field (or is no model): path -> (its code checks, its module source, it has a hand-written check)."""
    import inspect

    found: dict[str, tuple[bool, str, bool]] = {}
    for route in served_routes_all():
        if not route.body_field:
            continue
        fields = _body_fields(route.body_field.field_info.annotation)
        if fields is not None and not fields:
            continue
        try:
            code, module = _code_of(route.endpoint), inspect.getsource(inspect.getmodule(route.endpoint))
        except (OSError, TypeError):
            continue
        found[route.path] = (bool(_CHECKS.search(code)), module, bool(_HAND_CHECKS.search(code)))
    return found


def test_a_route_with_an_id_in_its_body_checks_it_or_says_why_it_need_not():
    routes = body_routes()
    unread = {p for p, (checks, *_) in routes.items() if not checks} - set(BODY_IDS_CLEARED)
    assert unread == set(), (
        "a route holds an id (or inputs, selection, ids, pages) in its body and its code shows no check (the dependency sees only path "
        "and query). Check it with read_check / write_check (api/main.py) and add a denial test, or read it and clear it in "
        f"BODY_IDS_CLEARED: {sorted(unread)}")
    served = set(routes) | {r.path for r in served_routes_all()}
    assert not {p for p in BODY_IDS_CLEARED if p not in served}, "cleared routes that are no longer served"
    stale = sorted(p for p in BODY_IDS_CLEARED if routes.get(p, (False,))[0])
    assert stale == [], f"these routes now check their ids: take them off BODY_IDS_CLEARED: {stale}"


def test_a_via_clearance_names_a_helper_the_module_has():
    routes = body_routes()
    missing = [p for p, (kind, *rest) in BODY_IDS_CLEARED.items() if kind == VIA and p in routes and rest[1] not in routes[p][1]]
    assert missing == [], missing


def test_a_route_that_checks_has_a_denial_test():
    """The code check is not the proof: each checking route is named in a denial test through the real stack."""
    from pathlib import Path

    text = "\n".join((Path(__file__).parent / name).read_text() for name in DENIAL_TEST_FILES if (Path(__file__).parent / name).exists())
    untested = []
    for path, (_, _, by_hand) in body_routes().items():
        tail = [seg for seg in path.split("/") if seg and not seg.startswith("{")][-1]
        if by_hand and tail not in text:
            untested.append(path)
    assert untested == [], f"these routes check their ids and no denial test names them: {sorted(untested)}"


def served_routes_all():
    from tests.route_inventory import served_routes

    return [r for r in served_routes(api_main.app) if isinstance(r, APIRoute)]


def test_a_cleared_entry_has_a_kind_and_an_open_one_names_its_issue():
    """A route cleared as OPEN is a known hole, not a pass: it must say which issue holds it. Any note of a hole counts as one."""
    bad = [p for p, (kind, why, *_) in BODY_IDS_CLEARED.items()
           if kind not in (NOT_DOC, VIA, OPEN) or ((kind == OPEN or re.search(r"OPEN|NOTE|no .* check", why)) and not re.search(r"#\d{4,}", why))]
    assert bad == [], bad


#: A route that changes something must depend on its caller (a library or owner dependency) or check in its code. These do neither, each
#: either PUBLIC (read and cleared: it has no caller yet, or touches nothing) or OPEN (a known gap, named issue). The list may only
#: shrink: a route that gains a dependency fails until it is taken off (the sweep that found /api/storage/snapshots and /api/registry).
NO_CALLER_CLEARED: dict[str, tuple[str, str]] = {
    "DELETE /api/chains/executions/{execution_id}": (OPEN, "no dependency on the caller and no check in its code (found by the sweep, not fired): #6325"),
    "POST /api/integrations/tinderbox/notes": (OPEN, "no dependency on the caller and no check in its code (found by the sweep, not fired): #6325"),
    "POST /api/integrations/{app_name}/open/{external_id}": (OPEN, "no dependency on the caller and no check in its code (found by the sweep, not fired): #6325"),
    "POST /api/integrations/{app_name}/refresh": (OPEN, "no dependency on the caller and no check in its code (found by the sweep, not fired): #6325"),
    "POST /api/model-comparison/compare": (OPEN, "no dependency on the caller and no check in its code (found by the sweep, not fired): #6325"),
    "POST /api/model-comparison/estimate-cost": (OPEN, "no dependency on the caller and no check in its code (found by the sweep, not fired): #6325"),
    "POST /api/model-comparison/recommend-models": (OPEN, "no dependency on the caller and no check in its code (found by the sweep, not fired): #6325"),
    "POST /api/research/tools/browser-navigate": (OPEN, "no dependency on the caller and no check in its code (found by the sweep, not fired): #6325"),
    "POST /api/research/tools/web-search": (OPEN, "no dependency on the caller and no check in its code (found by the sweep, not fired): #6325"),
    "POST /api/workflows/tools/{tool_name}/prompt": (OPEN, "no dependency on the caller and no check in its code (found by the sweep, not fired): #6325"),
    "PUT /api/integrations/tinderbox/notes/{external_id}/attributes": (OPEN, "no dependency on the caller and no check in its code (found by the sweep, not fired): #6325"),
    "DELETE /api/libraries/{lib:path}/entity-types/{entity_type_key}": (OPEN, "no dependency on the caller and no check in its code (found by the sweep, not fired): #6325"),
    "DELETE /api/pair/invites/{invite_id}": (OPEN, "no dependency on the caller and no check in its code (found by the sweep, not fired): #6325"),
    "POST /api/agents/write": (PUBLIC, "no caller to check yet (it signs in, pairs or answers a question) or it reads and writes nothing of the library; read 2026-11-01"),
    "POST /api/agents/write/approve": (OPEN, "no dependency on the caller and no check in its code (found by the sweep, not fired): #6325"),
    "POST /api/auth/challenge": (PUBLIC, "no caller to check yet (it signs in, pairs or answers a question) or it reads and writes nothing of the library; read 2026-11-01"),
    "POST /api/auth/first-run": (PUBLIC, "no caller to check yet (it signs in, pairs or answers a question) or it reads and writes nothing of the library; read 2026-11-01"),
    "POST /api/auth/invites/redeem": (PUBLIC, "no caller to check yet (it signs in, pairs or answers a question) or it reads and writes nothing of the library; read 2026-11-01"),
    "POST /api/auth/local-clients/register": (PUBLIC, "no caller to check yet (it signs in, pairs or answers a question) or it reads and writes nothing of the library; read 2026-11-01"),
    "POST /api/auth/local-clients/request": (PUBLIC, "no caller to check yet (it signs in, pairs or answers a question) or it reads and writes nothing of the library; read 2026-11-01"),
    "POST /api/auth/local-clients/requests/{request_id}/decision": (OPEN, "no dependency on the caller and no check in its code (found by the sweep, not fired): #6325"),
    "POST /api/auth/login": (PUBLIC, "no caller to check yet (it signs in, pairs or answers a question) or it reads and writes nothing of the library; read 2026-11-01"),
    "POST /api/auth/migrate-owner": (OPEN, "no dependency on the caller and no check in its code (found by the sweep, not fired): #6325"),
    "POST /api/auth/sign-in": (PUBLIC, "no caller to check yet (it signs in, pairs or answers a question) or it reads and writes nothing of the library; read 2026-11-01"),
    "POST /api/libraries/{lib:path}/entity-types": (OPEN, "no dependency on the caller and no check in its code (found by the sweep, not fired): #6325"),
    "POST /api/pair": (PUBLIC, "no caller to check yet (it signs in, pairs or answers a question) or it reads and writes nothing of the library; read 2026-11-01"),
    "POST /api/pair/devices/renew": (PUBLIC, "no caller to check yet (it signs in, pairs or answers a question) or it reads and writes nothing of the library; read 2026-11-01"),
    "POST /api/pair/devices/revoke-self": (PUBLIC, "no caller to check yet (it signs in, pairs or answers a question) or it reads and writes nothing of the library; read 2026-11-01"),
    "POST /api/pair/devices/{device_id}/revoke": (OPEN, "no dependency on the caller and no check in its code (found by the sweep, not fired): #6325"),
    "POST /api/pair/enroll": (PUBLIC, "no caller to check yet (it signs in, pairs or answers a question) or it reads and writes nothing of the library; read 2026-11-01"),
    "POST /api/policies/orchestration/evaluate": (PUBLIC, "no caller to check yet (it signs in, pairs or answers a question) or it reads and writes nothing of the library; read 2026-11-01"),
    "POST /api/recipes/assemble": (PUBLIC, "no caller to check yet (it signs in, pairs or answers a question) or it reads and writes nothing of the library; read 2026-11-01"),
    "POST /api/recipes/check": (PUBLIC, "no caller to check yet (it signs in, pairs or answers a question) or it reads and writes nothing of the library; read 2026-11-01"),
    "POST /api/sandbox/security-scoped-access": (OPEN, "no dependency on the caller and no check in its code (found by the sweep, not fired): #6325"),
    "PUT /api/auth/local-clients/switches": (OPEN, "no dependency on the caller and no check in its code (found by the sweep, not fired): #6325"),
}
_CALLER_DEPS = {"require_library_path", "get_library_database", "get_library_database_for_write", "optional_library_path", "get_action_store",
                "get_action_store_for_write", "_require_owner_or_bootstrap", "_require_owner_for_writes", "action_context", "request_actor", "_owner_only", "get_scheduler",
                "get_scheduler_for_write", "get_file_watcher", "get_file_watcher_for_write", "readable_rows"}
_CALLER_CODE = re.compile(r"\b(?:registry\.invoke|assert_library_\w+|read_check|write_check|owner_check|require_owner|_require_\w*owner\w*|"
                          r"request\.state|http_request\.state)\b")


def mutating_routes_without_a_caller() -> set[str]:
    import inspect

    def names(dep, out):
        out.add(getattr(dep.call, "__name__", ""))
        for sub in dep.dependencies:
            names(sub, out)
        return out

    found = set()
    for route in served_routes_all():
        verbs = set(route.methods) & {"POST", "PUT", "PATCH", "DELETE"}
        if not verbs or names(route.dependant, set()) & _CALLER_DEPS:
            continue
        try:
            if _CALLER_CODE.search(inspect.getsource(route.endpoint)):
                continue
        except (OSError, TypeError):
            continue
        found.add(f"{sorted(verbs)[0]} {route.path}")
    return found


def test_a_route_that_changes_something_depends_on_its_caller_or_is_cleared():
    found = mutating_routes_without_a_caller()
    assert found - set(NO_CALLER_CLEARED) == set(), f"a mutating route with no dependency on the caller and no check: {sorted(found - set(NO_CALLER_CLEARED))}"
    stale = sorted(set(NO_CALLER_CLEARED) - found)
    assert stale == [], f"these now depend on their caller: take them off NO_CALLER_CLEARED: {stale}"
    bad = [k for k, (kind, why) in NO_CALLER_CLEARED.items() if kind not in (PUBLIC, OPEN) or (kind == OPEN and not re.search(r"#\d{4,}", why))]
    assert bad == [], bad


def test_a_call_that_ignores_the_ids_is_not_a_check():
    """`assert_library_read_authorized(request, path)` names no id: it is the library-level answer (the chain routes passed on it)."""
    assert not _CHECKS.search("assert_library_read_authorized(http_request, x_fichero_library_path)")
    assert _CHECKS.search("assert_library_read_authorized(request, path, named=[i])")
    assert _CHECKS.search("assert_library_reads_every(request, path, ids, scope)")


def test_a_comment_or_docstring_is_not_a_check():
    def handler(x):
        """read_check(x)"""
        pass  # read_check(x)

    assert not _CHECKS.search(_code_of(handler))

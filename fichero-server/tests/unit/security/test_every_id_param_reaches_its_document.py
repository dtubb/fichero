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
    for route in api_main.app.routes:
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

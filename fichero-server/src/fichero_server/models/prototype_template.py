"""A template is a prototype's columns (attributes-and-prototypes.md §3): never a setting of its own.

``template_for_prototype`` is one prototype's effective declarations in ``order``; ``template_for_rows``
is the template of a scope of rows (their effective prototypes: one, or the union in first-seen order);
``apply_choice`` narrows it by a person's per-scope column choice, which is a saved view, not a change
to any prototype.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .node_prototypes import resolve_node_prototype, resolve_prototype_attributes
from .prototype_schema import attribute_declarations, ordered_field_keys


@dataclass(frozen=True)
class Column:
    key: str
    #: ``attribute`` (a stored field) or ``computed`` (read-only, from ``source``).
    kind: str
    type: str = "text"
    source: str | None = None
    labels: dict[str, str] = field(default_factory=dict)
    label: str | None = None
    help: dict[str, str] = field(default_factory=dict)
    join: str | None = None
    format: str | None = None
    name_order: str | None = None
    inherits: bool = False
    months: dict[str, list[str]] = field(default_factory=dict)
    option_labels: dict[str, dict[str, str]] = field(default_factory=dict)
    options: list[str] = field(default_factory=list)
    #: The prototype that gave the column (the group heading in a mixed scope).
    group: str | None = None


@dataclass
class Template:
    columns: list[Column]
    #: True when the rows had more than one effective prototype.
    mixed: bool = False
    #: Effective prototype keys in first-seen order.
    prototypes: list[str] = field(default_factory=list)


def template_for_prototype(db, key: str) -> list[Column]:
    attributes = resolve_prototype_attributes(db, key)
    decls = attribute_declarations(attributes)
    columns = []
    for name in ordered_field_keys(attributes):
        d = decls[name]
        if d.hidden:
            continue
        columns.append(Column(
            key=name, kind="computed" if d.source else "attribute", type=d.type, source=d.source,
            labels=dict(d.labels), label=d.label, help=dict(d.help), join=d.join, format=d.format,
            name_order=d.name_order, inherits=d.inherits, months=dict(d.months),
            option_labels=dict(d.option_labels), options=list(d.options), group=key,
        ))
    return columns


def template_for_rows(db, rows: list[Any]) -> Template:
    kinds = [resolve_node_prototype(db, row).key for row in rows]
    protos = list(dict.fromkeys(k for k in kinds if k))
    if not protos:
        # "Todos los atributos": every catalogue_* key seen, alphabetically (today's export).
        seen = sorted({k for row in rows for k in (row.attributes or {}) if k.startswith("catalogue_")})
        return Template([Column(key=k, kind="attribute") for k in seen])
    columns: dict[str, Column] = {}
    for proto in protos:
        for column in template_for_prototype(db, proto):
            columns.setdefault(column.key, column)
    return Template(list(columns.values()), mixed=len(protos) > 1, prototypes=protos)


def apply_choice(db, template: Template, choice: dict[str, Any] | None) -> Template:
    """A scope's saved column choice: ``hide`` keys, and/or ``only_kind`` (that kind's columns only)."""
    if not choice:
        return template
    columns = template.columns
    only = choice.get("only_kind")
    if only:
        keep = {c.key for c in template_for_prototype(db, only)}
        columns = [c for c in columns if c.key in keep]
    hide = set(choice.get("hide") or [])
    columns = [c for c in columns if c.key not in hide]
    return Template(columns, mixed=template.mixed, prototypes=template.prototypes)

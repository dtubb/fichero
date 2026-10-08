"""Where a node's attribute value came from (#5600, `source.extract.attributes-cite`).

`Document.attributes` holds the values; `Document.metadata["attribute_sources"]` says, per attribute
key, who set each one. The node's kind (its `prototype_key`) is the key ``prototype``
(`source.extract.kinds-proposed-as-prototypes`):

    {"<key>": {"by": "person"}}                       a person's value: cites nothing, outranks a machine's
    {"<key>": {"by": "machine", "tool": "scene",      a run's value: the run (its record's kind, the step,
               "step": ..., "run_id": ...,            the record and the model), and what it read the
               "artifact_id": ...,                    value from (`cites`: a segment, a
               "provider": ..., "model": ...,         mention or a text span; for a tool that looks at
               "said": "<the model's answer>",        the whole page, its answer is the evidence)
               "cites": {"kind": "segment", "id": ...} | None}}

The sources sit in `metadata`, not in `attributes`, so a grid or the effective-attributes values never
show them as fields. A run sets a key only when it is empty and nobody set it, or a machine set it: a
person's value (and any value already there that no run claims) is never overwritten by a run. The
page's kind from sorting keeps its own `material_set_by` (#5578).
"""
from __future__ import annotations

from typing import Any

SOURCES = "attribute_sources"
#: The key for the node's kind: `Document.prototype_key`, not an entry of `attributes`.
PROTOTYPE = "prototype"
BY_PERSON, BY_MACHINE = "person", "machine"


def sources(doc: Any) -> dict[str, dict]:
    meta = doc.metadata if isinstance(getattr(doc, "metadata", None), dict) else {}
    found = meta.get(SOURCES)
    return dict(found) if isinstance(found, dict) else {}


def _current(doc: Any, key: str) -> Any:
    if key == PROTOTYPE:
        return doc.prototype_key
    attrs = doc.attributes if isinstance(doc.attributes, dict) else {}
    return attrs.get(key)


def machine_may_set(doc: Any, key: str) -> bool:
    """Whether a run may write `key` on `doc`: a machine set it last, or it is empty and nobody set it."""
    source = sources(doc).get(key)
    if source is not None:
        return source.get("by") == BY_MACHINE
    return _current(doc, key) in (None, "", [], {})


def with_sources(metadata: Any, updates: dict[str, dict]) -> dict:
    """`metadata` with `updates` merged into its attribute sources (a new dict)."""
    meta = dict(metadata) if isinstance(metadata, dict) else {}
    meta[SOURCES] = {**(meta.get(SOURCES) if isinstance(meta.get(SOURCES), dict) else {}), **updates}
    return meta


def person_changed(before_attrs: Any, after_attrs: Any) -> dict[str, dict]:
    """{key: person source} for each attribute a person's edit added, changed or removed."""
    before = before_attrs if isinstance(before_attrs, dict) else {}
    after = after_attrs if isinstance(after_attrs, dict) else {}
    return {key: {"by": BY_PERSON} for key in {*before, *after} if before.get(key) != after.get(key)}


def machine_source(
    *, tool: str | None, run_id: str | None, artifact_id: str | None, step: str | None = None,
    provider: str | None = None, model: str | None = None, said: str | None = None, cites: dict | None = None,
) -> dict:
    return {"by": BY_MACHINE, "tool": tool, "step": step, "run_id": run_id, "artifact_id": artifact_id,
            "provider": provider, "model": model, "said": (said or "")[:500] or None, "cites": cites}


def scene_fields(value: Any) -> dict[str, Any]:
    """A scene answer as page attributes: the scene type under ``scene``, each detail as ``scene_<field>``."""
    if isinstance(value, dict):
        out = {"scene": value.get("scene")}
        out.update({f"scene_{k}": v for k, v in value.items() if k != "scene"})
        return {k: v for k, v in out.items() if v not in (None, "", [], {})}
    text = str(value or "").strip()
    return {"scene": text} if text else {}


def write_from_run(
    db: Any, doc: Any, *, key: str, value: Any, source: dict, library_path: str | None,
) -> list[str]:
    """Write a run's answer onto `doc` as attribute values (or, for `prototype`, as the node's kind),
    each citing `source`. Keys a person set are left alone. Returns the keys written."""
    if key == PROTOTYPE:
        return [PROTOTYPE] if propose_prototype(db, doc, value, source, library_path=library_path) else []
    fields = scene_fields(value) if key == "scene" else (
        {key: value} if value not in (None, "", [], {}) else {}
    )
    written = [k for k in fields if machine_may_set(doc, k)]
    if not written:
        return []
    from fichero_server.core.timeutil import utc_now

    attrs = doc.attributes if isinstance(doc.attributes, dict) else {}
    doc.attributes = {**attrs, **{k: fields[k] for k in written}}
    doc.metadata = with_sources(doc.metadata, {k: source for k in written})
    doc.updated_at = utc_now()
    db.save(doc)
    return written


def propose_prototype(db: Any, doc: Any, label: Any, source: dict, *, library_path: str | None) -> bool:
    """The node's kind, `label`, assigned as its prototype through the audited `document.assign_prototype`
    (the prototype made first through `classification.create` when the project has none of that name),
    citing `source`. A kind a person chose, or one already on the node that no run set, is kept."""
    if isinstance(label, (list, tuple)):
        label = next((item for item in label if str(item or "").strip()), None)
    label = str(label or "").strip()
    if not label:
        return False
    from fichero_server.finddocs.propose import prototype_key

    key = prototype_key(label)
    if not key or not machine_may_set(doc, PROTOTYPE):
        return False
    import fichero_server.api.routes.document.classifications  # noqa: F401  (classification.create)
    import fichero_server.api.routes.document.documents  # noqa: F401  (document.assign_prototype)
    from fichero_server.actions.registry import ActionContext, registry
    from fichero_server.models.knowledge import ClassificationDimension, ClassificationValue

    ctx = ActionContext(actor="workflow", run_id=source.get("run_id"), library_path=library_path,
                        is_bootstrap=True)
    known = {v.key for v in db.query(ClassificationValue)
             if v.dimension in {ClassificationDimension.document_prototype, ClassificationDimension.node_class}}
    if key not in known:
        registry.invoke(db, "classification.create", {
            "dimension": ClassificationDimension.document_prototype.value, "key": key, "label": label,
            "description": f"Proposed by {source.get('tool') or 'a run'}"}, ctx)
    registry.invoke(db, "document.assign_prototype", {
        "doc_id": doc.id, "request": {"prototype_key": key}, "source": source}, ctx)
    return True

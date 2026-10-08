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

A run's KIND is not assigned: it is proposed for a person to accept (ruled 2026-10-08, #5600).
`Document.metadata["proposed_attributes"]["prototype"]` holds it, citing the run as a value would:

    {"value": "<prototype key>", "label": "<what the model named it>", "state": "proposed",
     "source": <machine_source(...)>, "proposed_at": "<iso time>"}

Accepting it assigns the prototype through the audited `document.assign_prototype`, its source the
run with ``accepted_by`` the person (the kind is then the person's: no run proposes over it);
rejecting it (`document.reject_proposed_kind`) sets its state to ``rejected``, and that kind is not
proposed again. A later run's proposal replaces one nobody answered, never a kind a person chose.
Like Find the Documents' proposals (`finddocs.*`), each answer is one audited action, undone as one.
"""
from __future__ import annotations

from typing import Any

SOURCES = "attribute_sources"
PROPOSED = "proposed_attributes"
PROPOSED_STATE, ACCEPTED, REJECTED = "proposed", "accepted", "rejected"
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
    """Whether a run may write (or propose) `key` on `doc`: a machine set it last and no person accepted
    it, or it is empty and nobody set it."""
    source = sources(doc).get(key)
    if source is not None:
        return source.get("by") == BY_MACHINE and not source.get("accepted_by")
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


def proposals(doc: Any) -> dict[str, dict]:
    meta = doc.metadata if isinstance(getattr(doc, "metadata", None), dict) else {}
    found = meta.get(PROPOSED)
    return dict(found) if isinstance(found, dict) else {}


def pending(doc: Any, key: str) -> dict | None:
    """The proposal for `key` on `doc` that nobody has answered, or None."""
    found = proposals(doc).get(key)
    return found if isinstance(found, dict) and found.get("state") == PROPOSED_STATE else None


def answered(metadata: Any, key: str, state: str, *, by: str | None) -> dict:
    """`metadata` with its unanswered proposal for `key` (if any) answered `state` by `by` (a new dict)."""
    meta = dict(metadata) if isinstance(metadata, dict) else {}
    found = meta.get(PROPOSED) if isinstance(meta.get(PROPOSED), dict) else {}
    current = found.get(key)
    if not isinstance(current, dict) or current.get("state") != PROPOSED_STATE:
        return meta
    meta[PROPOSED] = {**found, key: {**current, "state": state, "answered_by": by}}
    return meta


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
    """Write a run's answer onto `doc` as attribute values (for `prototype`, a proposed kind waiting for a
    person), each citing `source`. Keys a person set are left alone. Returns the keys written."""
    if key == PROTOTYPE:
        return [PROTOTYPE] if propose_prototype(db, doc, value, source) else []
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


def propose_prototype(db: Any, doc: Any, label: Any, source: dict) -> bool:
    """The node's kind, `label`, recorded as a proposed prototype citing `source`, for a person to accept
    or reject (`source.extract.kinds-proposed-as-prototypes`, ruled 2026-10-08). Nothing is assigned and no
    prototype is made until a person accepts. A kind a person chose (or one already on the node that no
    run set) is never proposed over; a kind the person rejected is not proposed again; a later run's
    proposal replaces one nobody answered."""
    if isinstance(label, (list, tuple)):
        label = next((item for item in label if str(item or "").strip()), None)
    label = str(label or "").strip()
    if not label:
        return False
    from fichero_server.core.timeutil import utc_now
    from fichero_server.finddocs.propose import prototype_key

    key = prototype_key(label)
    if not key or not machine_may_set(doc, PROTOTYPE) or doc.prototype_key == key:
        return False
    current = proposals(doc).get(PROTOTYPE)
    if isinstance(current, dict) and current.get("state") == REJECTED and current.get("value") == key:
        return False
    meta = dict(doc.metadata) if isinstance(doc.metadata, dict) else {}
    meta[PROPOSED] = {**proposals(doc), PROTOTYPE: {
        "value": key, "label": label, "state": PROPOSED_STATE, "source": source,
        "proposed_at": utc_now().isoformat()}}
    doc.metadata = meta
    doc.updated_at = utc_now()
    db.save(doc)
    return True

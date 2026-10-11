"""The transfer's PLAN: what travels, under which new ids, what is cut, what vocabulary and which
merges it needs — computed without writing anything (#5657, build order 2, `transfer.action.dry-run`).

The plan is complete: it holds every target row already built (new ids, every id inside re-pointed
through the map), so a dry run answers exactly what a copy would write, and the copy (`copy.py`)
only saves what the plan built, then reads it back.

What the remapping does with each field is read from `id_map_classification.CLASSIFICATION`
(MAPPED, RECOMPUTED, PROJECT_VOCAB, CUT, NOT_DOCUMENT_SCOPED); which rows come along is read from
`membership.JOINS`. Neither is restated here.
"""

from __future__ import annotations

import typing
import unicodedata
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from fichero_server.models.transfer import (
    TransferCount,
    TransferCut,
    TransferEntityProposal,
    TransferLeftBehind,
    TransferVocabulary,
)
from fichero_server.transfer import membership
from fichero_server.transfer.id_map_classification import (
    CLASSIFICATION,
    MAPPED,
    PROJECT_VOCAB,
    RECOMPUTED,
)

#: Names in a result, in the order a person reads them.
_READABLE = ("name", "canonical_name", "label", "text", "content")


def _new_id() -> str:
    return uuid.uuid4().hex


def _readable(row: BaseModel) -> str | None:
    for attr in _READABLE:
        value = getattr(row, attr, None)
        if isinstance(value, str) and value.strip():
            return value.strip()[:80]
    return None


def _is_list_field(model: type[BaseModel], name: str) -> bool:
    annotation = model.model_fields[name].annotation
    for arg in (annotation, *typing.get_args(annotation)):
        if typing.get_origin(arg) is list or arg is list:
            return True
    return False


def _allows_none(model: type[BaseModel], name: str) -> bool:
    annotation = model.model_fields[name].annotation
    return annotation is None or type(None) in typing.get_args(annotation)


def _norm(name: str | None) -> str:
    return unicodedata.normalize("NFC", (name or "")).strip().casefold()


@dataclass
class PlannedFile:
    """An in-package original to copy byte for byte (`transfer.page.files`)."""

    document: str
    source_path: Path
    relative: Path
    size: int


@dataclass
class EntityMatch:
    carried: str
    name: str
    entity_type: str
    target_entity: str
    target_name: str
    reason: str


@dataclass
class TransferPlan:
    transfer_id: str
    source_package: Path
    target_package: Path
    target_parent_id: str
    #: The audit row this transfer's target audit will be; RECOMPUTED audit pointers point at it.
    audit_id: str
    items: list[str]
    #: Source rows that travel, by model name, by source id.
    rows: dict[str, dict[str, BaseModel]] = field(default_factory=dict)
    models: dict[str, type[BaseModel]] = field(default_factory=dict)
    id_map: dict[str, str] = field(default_factory=dict)
    #: The target rows, built: (model name, row). Documents first, parents before children.
    built: list[tuple[str, BaseModel]] = field(default_factory=list)
    vocabulary: list[TransferVocabulary] = field(default_factory=list)
    #: Vocabulary records the copy makes in the target (built, not saved).
    vocabulary_to_make: list[BaseModel] = field(default_factory=list)
    matches: list[EntityMatch] = field(default_factory=list)
    cuts: list[TransferCut] = field(default_factory=list)
    left_behind: list[TransferLeftBehind] = field(default_factory=list)
    files: list[PlannedFile] = field(default_factory=list)
    linked_files: list[str] = field(default_factory=list)
    source_audits: dict[str, str] = field(default_factory=dict)

    @property
    def copies(self) -> list[str]:
        return [self.id_map[item] for item in self.items if item in self.id_map]

    def counts(self) -> list[TransferCount]:
        out: dict[str, int] = {}
        for name, _row in self.built:
            out[name] = out.get(name, 0) + 1
        return [TransferCount(kind=kind, planned=count) for kind, count in sorted(out.items())]

    def proposals(self) -> list[TransferEntityProposal]:
        return [
            TransferEntityProposal(
                carried_entity=m.carried, name=m.name, entity_type=m.entity_type,
                target_entity=m.target_entity, target_name=m.target_name, reason=m.reason,
            )
            for m in self.matches
        ]

    @property
    def entities_new(self) -> int:
        matched = {m.carried for m in self.matches}
        return len([e for e in self.rows.get("KnowledgeEntity", {}) if e not in matched])


# ---------------------------------------------------------------------------------------------
# Gathering the set
# ---------------------------------------------------------------------------------------------


def _schema_models(db) -> dict[str, type[BaseModel]]:
    return {model.__name__: model for model in db._all_schema_models()}


def _rows_naming(db, model: type[BaseModel], name: str, ids: set[str]) -> list[BaseModel]:
    """Rows of `model` whose `name` names one of `ids` (a list field: any element)."""
    if not ids:
        return []
    if _is_list_field(model, name):
        # ponytail: a list column is read whole and filtered here; a JSON contains-query in db/ if this is slow.
        return [row for row in db.all(model) if set(getattr(row, name, None) or ()) & ids]
    return db.query_in(model, name, sorted(ids))


def _walk_documents(plan: TransferPlan, source_db, models) -> None:
    """Each item and its live descendants; trashed descendants stay and are listed (`transfer.page.whole-subtree`)."""
    Document = models["Document"]
    docs: dict[str, BaseModel] = {}
    stack = list(plan.items)
    while stack:
        doc_id = stack.pop()
        doc = source_db.get(Document, doc_id)
        if doc is None or doc_id in docs:
            continue
        docs[doc_id] = doc
        for child in source_db.query(Document, parent_id=doc_id):
            if child.deleted_at is not None:
                plan.left_behind.append(TransferLeftBehind(
                    item=child.id, name=child.name, reason="in the source's Trash; trashed items stay there"))
                continue
            stack.append(child.id)
    # An alias travels only with its target (`transfer.alias.inside-set-rewritten`).
    for doc_id, doc in list(docs.items()):
        target = getattr(doc, "alias_target_id", None)
        if doc.node_kind == "alias" and target and target not in docs:
            del docs[doc_id]
            plan.cuts.append(TransferCut(
                kind="Document", row=doc_id, field="alias_target_id", points_to=target, name=doc.name,
                whole_row=True, reason="an alias whose original is not transferred would point at nothing; it stays"))
    plan.rows["Document"] = docs


def _set_ids(plan: TransferPlan) -> set[str]:
    return {row_id for rows in plan.rows.values() for row_id in rows}


def _end_is_external(row: BaseModel, key: str) -> bool:
    external = membership.EXTERNAL_ENDS.get(key)
    return bool(external and getattr(row, external[0], None) == external[1])


def _values(row: BaseModel, name: str) -> list[str]:
    value = getattr(row, name, None)
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [v for v in value if isinstance(v, str) and v]
    return [value] if isinstance(value, str) and value else []


def _holds(model_name: str, row: BaseModel, in_set: set[str]) -> bool:
    """Whether a gathered row still belongs: an owner in the set, and every `whole` end in it."""
    join = membership.JOINS[model_name]
    if join.owners and not any(v in in_set for n in join.owners for v in _values(row, n)):
        return False
    for name in join.whole:
        if _end_is_external(row, f"{model_name}.{name}"):
            continue
        if any(v not in in_set for v in _values(row, name)):
            return False
    return True


def _entity_ids_named(plan: TransferPlan) -> set[str]:
    named: set[str] = set()
    for key in membership.ENTITY_REFERENCES:
        model_name, name = key.split(".")
        for row in plan.rows.get(model_name, {}).values():
            named.update(_values(row, name))
    for link in plan.rows.get("TypedLink", {}).values():
        if link.to_kind == membership.ENTITY_LINK_KIND:
            named.add(link.to_id)
    return named


def _gather(plan: TransferPlan, source_db, models) -> None:
    """Grow the set to a fixpoint, then prune what lost its owner or an end, until stable."""
    candidates: dict[str, dict[str, BaseModel]] = {name: {} for name in membership.JOINS}
    entities: dict[str, BaseModel] = {}
    Entity = models["KnowledgeEntity"]
    seen: set[str] = set()
    while True:
        in_set = set(plan.rows["Document"]) | {i for rows in candidates.values() for i in rows} | set(entities)
        fresh = in_set - seen
        if not fresh:
            break
        seen |= fresh
        for model_name, join in membership.JOINS.items():
            model = models.get(model_name)
            if model is None:
                continue
            for name in (*join.owners, *([] if join.owners else join.whole)):
                for row in _rows_naming(source_db, model, name, fresh):
                    candidates[model_name].setdefault(row.id, row)
        # Links from a set row to an entity (a segment that `names` a place) bring the entity.
        for key in membership.ENTITY_REFERENCES:
            model_name, name = key.split(".")
            for row in candidates[model_name].values():
                for entity_id in _values(row, name):
                    if entity_id not in entities and (entity := source_db.get(Entity, entity_id)) is not None:
                        entities[entity_id] = entity
        for link in candidates["TypedLink"].values():
            if link.to_kind == membership.ENTITY_LINK_KIND and link.from_id in in_set and link.to_id not in entities:
                entity = source_db.get(Entity, link.to_id)
                if entity is not None:
                    entities[link.to_id] = entity

    # Prune to a stable set: a row stays while its owner is in the set and every whole end is.
    kept = {name: dict(rows) for name, rows in candidates.items()}
    dropped: dict[str, tuple[str, BaseModel, str, str]] = {}
    while True:
        plan.rows.update({name: rows for name, rows in kept.items() if rows})
        named = _entity_ids_named(plan)
        plan.rows["KnowledgeEntity"] = {e: entity for e, entity in entities.items() if e in named}
        in_set = _set_ids(plan)
        changed = False
        for model_name, rows in kept.items():
            for row_id, row in list(rows.items()):
                if not _holds(model_name, row, in_set):
                    del rows[row_id]
                    dropped[row_id] = (model_name, row, *_first_missing(model_name, row, in_set))
                    changed = True
        if not changed:
            break
    for model_name, rows in list(plan.rows.items()):
        if not rows:
            del plan.rows[model_name]
    in_set = _set_ids(plan)
    for row_id, (model_name, row, name, value) in dropped.items():
        if row_id in in_set:
            continue
        plan.cuts.append(TransferCut(
            kind=model_name, row=row_id, field=name, points_to=value, name=_readable(row), whole_row=True,
            reason="names something that is not transferred; it stays in the source and is not carried"))


def _first_missing(model_name: str, row: BaseModel, in_set: set[str]) -> tuple[str, str]:
    join = membership.JOINS[model_name]
    for name in join.whole:
        if _end_is_external(row, f"{model_name}.{name}"):
            continue
        for value in _values(row, name):
            if value not in in_set:
                return name, value
    name = join.owners[0] if join.owners else (join.whole or ("id",))[0]
    return name, (_values(row, name) or [""])[0]


# ---------------------------------------------------------------------------------------------
# Allocating ids
# ---------------------------------------------------------------------------------------------


def _allocate(plan: TransferPlan) -> None:
    from fichero_server.models.anchors import LEGACY_ID_PREFIX
    from fichero_server.models.segments import legacy_pass_id, legacy_segment_id

    for model_name, rows in plan.rows.items():
        for row_id in rows:
            if row_id.startswith(LEGACY_ID_PREFIX) and model_name in ("SegmentPass", "Segment"):
                continue
            plan.id_map.setdefault(row_id, _new_id())
    # RECOMPUTED (`SegmentPass.id`, `Segment.id`): derived again from the new artifact id, never a string map.
    for model_name in ("SegmentPass", "Segment"):
        for row_id in plan.rows.get(model_name, {}):
            if not row_id.startswith(LEGACY_ID_PREFIX):
                continue
            artifact, _, index = row_id[len(LEGACY_ID_PREFIX):].partition(":")
            new_artifact = plan.id_map.get(artifact)
            if new_artifact is None:
                plan.id_map[row_id] = _new_id()
            elif model_name == "SegmentPass":
                plan.id_map[row_id] = legacy_pass_id(new_artifact)
            else:
                plan.id_map[row_id] = legacy_segment_id(new_artifact, int(index))


# ---------------------------------------------------------------------------------------------
# Vocabulary (PROJECT_VOCAB, and the keyed vocabularies rows name by key)
# ---------------------------------------------------------------------------------------------


class _Vocabulary:
    """Matches each vocabulary record the set uses in the target by its key; makes it if missing."""

    def __init__(self, plan: TransferPlan, source_db, target_db) -> None:
        self.plan, self.source_db, self.target_db = plan, source_db, target_db
        self._done: dict[tuple[str, str], str | None] = {}

    def _record(self, vocabulary: str, key: str, made: bool, difference: str | None) -> None:
        self.plan.vocabulary.append(TransferVocabulary(vocabulary=vocabulary, key=key, made=made, difference=difference))

    def _diff(self, vocabulary: str, key: str, here: BaseModel, there: BaseModel, fields: tuple[str, ...]) -> str | None:
        parts = [
            f"{name} here is {getattr(here, name)!r}; in the source {getattr(there, name)!r}"
            for name in fields
            if getattr(here, name, None) != getattr(there, name, None)
        ]
        return f"{vocabulary} {key!r}: " + "; ".join(parts) if parts else None

    def keyed(self, vocabulary: str, key: str | None) -> str | None:
        """Reading kinds and levels, link types, document types: matched by key; the key is kept."""
        if not key:
            return key
        token = (vocabulary, key)
        if token in self._done:
            return key
        self._done[token] = key
        from fichero_server.models import LibraryReadingKind
        from fichero_server.models.knowledge import ClassificationDimension, ClassificationValue
        from fichero_server.models.readings import LibraryReadingLevel
        from fichero_server.models.typed_links import LibraryLinkType

        if vocabulary == "document_type":
            def find(db, k):
                rows = db.query(ClassificationValue, dimension=ClassificationDimension.document_prototype, key=k)
                return rows[0] if rows else None
            fields = ("label", "parent_key", "attributes")
        else:
            model = {"reading_kind": LibraryReadingKind, "reading_level": LibraryReadingLevel,
                     "link_type": LibraryLinkType}[vocabulary]

            def find(db, k, model=model):
                rows = db.query(model, key=k)
                return rows[0] if rows else None
            fields = ("label",)
        here, there = find(self.target_db, key), find(self.source_db, key)
        if here is not None:
            self._record(vocabulary, key, False, self._diff(vocabulary, key, here, there, fields) if there else None)
            return key
        if there is None:
            # The source names a key with no record of its own (an older row): nothing to copy, nothing to make.
            return key
        made = there.model_copy(update={"id": _new_id(), **({"builtin": False} if hasattr(there, "builtin") else {}),
                                        **({"is_builtin": False} if hasattr(there, "is_builtin") else {})})
        self.plan.vocabulary_to_make.append(made)
        self._record(vocabulary, key, True, None)
        if vocabulary == "document_type" and getattr(there, "parent_key", None):
            self.keyed("document_type", there.parent_key)  # the parent chain comes too
        return key

    def by_id(self, key: str, source_id: str | None) -> str | None:
        """PROJECT_VOCAB ids: a hand by label, an allograph by character and name, a framework by name."""
        if not source_id:
            return source_id
        token = (key, source_id)
        if token in self._done:
            return self._done[token]
        from fichero_server.models.hands import Hand
        from fichero_server.models.hermeneutics import InterpretiveFramework
        from fichero_server.models.letterforms import Allograph

        target_kind = {"HandAttribution.hand_id": "hand", "LetterformDescription.hand_id": "hand",
                       "Campaign.hand_id": "hand", "LetterformDescription.allograph_id": "allograph",
                       "Interpretation.framework_id": "framework"}.get(key)
        if target_kind is None:
            self._done[token] = None
            return None
        model, match_on, fields = {
            "hand": (Hand, ("label",), ("scribe", "date", "place", "style")),
            "allograph": (Allograph, ("character", "name"), ("notes",)),
            "framework": (InterpretiveFramework, ("name",), ("key_concepts",)),
        }[target_kind]
        there = self.source_db.get(model, source_id)
        if there is None:
            self._done[token] = None
            return None
        label = " / ".join(str(getattr(there, m)) for m in match_on)
        here = next((row for row in self.target_db.query(model, **{m: getattr(there, m) for m in match_on})
                     if getattr(row, "deleted_at", None) is None and getattr(row, "withdrawn_at", None) is None), None)
        if here is None:
            # Made in the target once, shared by every carried row that names it.
            made_id = next((m.id for m in self.plan.vocabulary_to_make if isinstance(m, model)
                            and all(getattr(m, f) == getattr(there, f) for f in match_on)), None)
            if made_id is None:
                made = there.model_copy(update={"id": _new_id()})
                self.plan.vocabulary_to_make.append(made)
                self._record(target_kind, label, True, None)
                made_id = made.id
            self._done[token] = made_id
            return made_id
        if not any(v.vocabulary == target_kind and v.key == label for v in self.plan.vocabulary):
            self._record(target_kind, label, False, self._diff(target_kind, label, here, there, fields))
        self._done[token] = here.id
        return here.id


# ---------------------------------------------------------------------------------------------
# Building the target rows
# ---------------------------------------------------------------------------------------------


class _Builder:
    def __init__(self, plan: TransferPlan, vocabulary: _Vocabulary) -> None:
        self.plan = plan
        self.vocabulary = vocabulary
        self.pairs: dict[str, str] = {}
        self.row_cuts: list[TransferCut] = []

    def _cut(self, kind: str, row: BaseModel, path: str, value: str, reason: str) -> None:
        self.row_cuts.append(TransferCut(kind=kind, row=getattr(row, "id", ""), field=path, points_to=value,
                                         name=_readable(row), reason=reason))

    def _deep(self, value: Any) -> Any:
        """A dict or list holding ids (metadata, curated items, line runs): every id in the map is re-pointed."""
        if isinstance(value, str):
            return self.plan.id_map.get(value, value)
        if isinstance(value, dict):
            return {k: self._deep(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self._deep(v) for v in value]
        if isinstance(value, BaseModel):
            return self.build(type(value).__name__, value, value, nested=True)
        return value

    def _mapped(self, kind: str, row: BaseModel, holder: BaseModel, key: str, path: str, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, str):
            if _end_is_external(holder, key) or key == "PageLineMap.id":
                return self.plan.id_map.get(value, value)
            if value in self.plan.id_map:
                return self.plan.id_map[value]
            self._cut(kind, row, path, value, "names something that is not transferred; the edge is cut")
            return None
        if isinstance(value, list) and all(isinstance(v, str) for v in value):
            kept = []
            for v in value:
                if v in self.plan.id_map:
                    kept.append(self.plan.id_map[v])
                else:
                    self._cut(kind, row, path, v, "names something that is not transferred; the edge is cut")
            return kept
        return self._deep(value)

    def build(self, kind: str, row: BaseModel, holder: BaseModel, *, nested: bool = False, prefix: str = "") -> BaseModel:
        model = type(holder)
        cls_name = model.__name__
        update: dict[str, Any] = {}
        for name in model.model_fields:
            key = f"{cls_name}.{name}"
            value = getattr(holder, name)
            path = f"{prefix}{name}"
            bucket = CLASSIFICATION.get(key, (None, ""))[0]
            if name == "id" and not nested:
                if bucket == RECOMPUTED and cls_name == "CanvasLayout":
                    continue  # rebuilt below from the mapped pair
                update["id"] = self.plan.id_map[value]
                continue
            if bucket == MAPPED:
                update[name] = self._mapped(kind, row, holder, key, path, value)
            elif bucket == RECOMPUTED:
                if name == "audit_id":
                    update[name] = self.plan.audit_id
                elif name == "pair_id" and value:
                    update[name] = self.pairs.setdefault(value, _new_id())
                elif name == "id" and nested:
                    update[name] = self.plan.id_map.get(value, value)
            elif bucket == PROJECT_VOCAB:
                if key in ("ContentRepresentation.sign_map", "LetterformDescription.character", "Allograph.character",
                           "DeclaredSign.picture_segment_id"):
                    continue  # code points and characters are kept as written (declared signs: not carried yet)
                resolved = self.vocabulary.by_id(key, value)
                if value and resolved is None:
                    self._cut(kind, row, path, value, "project vocabulary that is not matched between projects yet")
                update[name] = resolved
            elif isinstance(value, BaseModel):
                update[name] = self.build(kind, row, value, nested=True, prefix=f"{path}.")
            elif isinstance(value, list) and value and all(isinstance(v, BaseModel) for v in value):
                update[name] = [self.build(kind, row, v, nested=True, prefix=f"{path}.") for v in value]
        built = holder.model_copy(update=update)
        if cls_name == "CanvasLayout" and not nested:
            built = built.model_copy(update={"id": f"{built.folder_id}::{built.item_id}"})
        return built


def _keyed_vocabulary(vocabulary: _Vocabulary, kind: str, row: BaseModel) -> None:
    if kind == "Document":
        vocabulary.keyed("document_type", getattr(row, "prototype_key", None))
    elif kind == "ContentRepresentation":
        vocabulary.keyed("reading_kind", row.kind)
        vocabulary.keyed("reading_level", row.level)
    elif kind == "TypedLink":
        vocabulary.keyed("link_type", row.link_type)


def _document_order(plan: TransferPlan) -> list[str]:
    """Parents before children, so every written node's parent exists when it is written."""
    docs = plan.rows["Document"]
    order: list[str] = []
    placed: set[str] = set()

    def place(doc_id: str) -> None:
        if doc_id in placed:
            return
        parent = docs[doc_id].parent_id
        if parent in docs:
            place(parent)
        placed.add(doc_id)
        order.append(doc_id)

    for doc_id in docs:
        place(doc_id)
    return order


def _build_rows(plan: TransferPlan, source_db, target_db, models, actor: str, source_name: str) -> None:
    from fichero_server.core.timeutil import utc_now

    vocabulary = _Vocabulary(plan, source_db, target_db)
    builder = _Builder(plan, vocabulary)
    when = utc_now().isoformat()
    tops = set(plan.items)
    ordered: list[tuple[str, BaseModel]] = [("Document", plan.rows["Document"][d]) for d in _document_order(plan)]
    for model_name in models:
        if model_name != "Document" and model_name in plan.rows:
            ordered.extend((model_name, row) for row in plan.rows[model_name].values())
    for kind, row in ordered:
        _keyed_vocabulary(vocabulary, kind, row)
        builder.row_cuts = []
        built = builder.build(kind, row, row)
        if kind == "Document":
            built = _with_provenance(plan, row, built, tops, actor, when, source_name)
        if kind in ("SegmentVersion", "SegmentForwarding"):
            plan.source_audits[built.id] = row.audit_id
        # A required field whose only value was cut: the row cannot travel without it.
        try:
            built = type(row).model_validate(built.model_dump())
        except ValidationError:
            missing = builder.row_cuts[0] if builder.row_cuts else None
            plan.cuts.append(TransferCut(
                kind=kind, row=row.id, field=missing.field if missing else "", points_to=missing.points_to if missing else "",
                name=_readable(row), whole_row=True,
                reason="a field it needs names something that is not transferred; it stays in the source"))
            continue
        if kind == "Document" and row.id in tops:
            # The top items' parent is replaced by the target folder: not a cut.
            builder.row_cuts = [c for c in builder.row_cuts if c.field != "parent_id"]
        plan.cuts.extend(builder.row_cuts)
        plan.built.append((kind, built))


def _with_provenance(plan, row, built, tops, actor, when, source_name):
    """The top items land in the target folder; every node records where it came from (`transfer.action.provenance`)."""
    metadata = dict(built.metadata or {})
    metadata["transferred_from"] = {
        "project": source_name, "project_path": str(plan.source_package), "node": row.id,
        "transfer": plan.transfer_id, "when": when, "who": actor,
    }
    update: dict[str, Any] = {"metadata": metadata}
    if row.id in tops:
        update["parent_id"] = plan.target_parent_id
    path = _package_relative(plan.source_package, row.path)
    if path is not None:
        new_path = _target_file_path(plan, path)
        update["path"] = str(new_path)
        for key in ("source_path", "full_path", "local_path"):
            if metadata.get(key) == row.path:
                metadata[key] = str(new_path)
        for key in [k for k in metadata if "bookmark" in k.lower()]:
            metadata.pop(key)  # a bookmark resolves to the SOURCE's file; the copy is the target's own
        size = Path(row.path).stat().st_size
        plan.files.append(PlannedFile(document=row.id, source_path=Path(row.path), relative=new_path.relative_to(plan.target_package), size=size))
    elif row.path:
        plan.linked_files.append(row.id)
    return built.model_copy(update=update)


def _package_relative(package: Path, path: str | None) -> Path | None:
    if not path:
        return None
    candidate = Path(path)
    try:
        relative = candidate.resolve().relative_to(package.resolve())
    except ValueError:
        return None
    return relative if candidate.is_file() else None


def _target_file_path(plan: TransferPlan, relative: Path) -> Path:
    """`files/<…>` under the target; a name already there goes under `files/transfer-<id>/` instead."""
    target = plan.target_package / relative
    if target.exists() or any(f.relative == relative for f in plan.files):
        target = plan.target_package / "files" / f"transfer-{plan.transfer_id[:8]}" / relative.relative_to(relative.parts[0])
    return target


# ---------------------------------------------------------------------------------------------
# Entities: matched by authority id, then by name (`transfer.entities.match-authority-then-name`)
# ---------------------------------------------------------------------------------------------


def _match_entities(plan: TransferPlan, source_db, target_db) -> None:
    from fichero_server.knowledge.authorities import SAME_AS, authority_of_uri
    from fichero_server.models.knowledge import KnowledgeEntity
    from fichero_server.models.typed_links import TypedLink

    def live(entity) -> bool:
        return entity is not None and entity.merged_into_id is None and getattr(entity, "curation_state", None) != "merged"

    for entity in plan.rows.get("KnowledgeEntity", {}).values():
        found: list[tuple[str, str]] = []
        for link in source_db.query(TypedLink, from_id=entity.id):
            if link.link_type != SAME_AS or link.to_kind != "uri" or link.deleted_at is not None:
                continue
            for theirs in target_db.query(TypedLink, to_id=link.to_id):
                if theirs.link_type == SAME_AS and theirs.from_kind == "entity" and theirs.deleted_at is None:
                    authority = authority_of_uri(link.to_id)
                    label = f"{authority[0]} {authority[1]}" if authority else link.to_id
                    found.append((theirs.from_id, f"same {label}"))
        if not found:
            names = {_norm(entity.canonical_name), *(_norm(a) for a in entity.aliases),
                     *(_norm(n.text) for n in entity.names)} - {""}
            for candidate in target_db.query(KnowledgeEntity, entity_type=entity.entity_type):
                theirs = {_norm(candidate.canonical_name), *(_norm(a) for a in candidate.aliases)}
                if names & theirs:
                    found.append((candidate.id, "same name and type"))
        seen: set[str] = set()
        for target_id, reason in found:
            target_entity = target_db.get(KnowledgeEntity, target_id)
            if target_id in seen or not live(target_entity):
                continue
            seen.add(target_id)
            plan.matches.append(EntityMatch(
                carried=entity.id, name=entity.canonical_name, entity_type=str(getattr(entity.entity_type, "value", entity.entity_type)),
                target_entity=target_id, target_name=target_entity.canonical_name, reason=reason))


# ---------------------------------------------------------------------------------------------
# The plan
# ---------------------------------------------------------------------------------------------


def build_plan(
    source_db, target_db, *, items: list[str], target_parent_id: str, transfer_id: str, audit_id: str, actor: str,
) -> TransferPlan:
    """Everything a copy would write, built and checked; nothing is written to either project."""
    source_package = Path(source_db.path).parent
    plan = TransferPlan(
        transfer_id=transfer_id, source_package=source_package, target_package=Path(target_db.path).parent,
        target_parent_id=target_parent_id, audit_id=audit_id, items=list(items),
    )
    models = _schema_models(source_db)
    plan.models = models
    _walk_documents(plan, source_db, models)
    _gather(plan, source_db, models)
    _allocate(plan)
    _build_rows(plan, source_db, target_db, models, actor, source_package.stem)
    _match_entities(plan, source_db, target_db)
    return plan

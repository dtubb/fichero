"""Helpers for workflow tools that should feed the image preview editor.

Two things live here, sharing one document resolver on purpose: edit-chain
operations (what the editor replays) and RENDITIONS (the pixels a workflow
actually produced). Two resolvers would eventually disagree about which
documents a run applied to.
"""

from __future__ import annotations

from fichero_server.core.timeutil import utc_now
from typing import Any, Callable

import logging
from pathlib import Path

from fichero_server.db import db_manager
from fichero_server.models import Document, ImageEditChain, Rendition
from fichero_server.models.anchors import NodeRegion, RegionConfidence
from fichero_server.workflows.types import State

logger = logging.getLogger(__name__)


def _candidate_document_ids(inputs: dict[str, Any], state: State) -> list[str]:
    ids: list[str] = []
    for source in (inputs.get("documents"), state.get("documents")):
        for doc in source or []:
            if isinstance(doc, dict) and isinstance(doc.get("id"), str):
                ids.append(doc["id"])
    for doc_id in state.get("selected_doc_ids") or []:
        if isinstance(doc_id, str):
            ids.append(doc_id)

    seen: set[str] = set()
    unique: list[str] = []
    for doc_id in ids:
        if doc_id in seen:
            continue
        seen.add(doc_id)
        unique.append(doc_id)
    return unique


def append_image_edit_operations(
    inputs: dict[str, Any],
    state: State,
    build_operation: Callable[[Document], dict[str, Any]],
) -> list[dict[str, Any]]:
    """Persist edit-chain operations for workflow-selected documents.

    Workflow image tools still return derived files for pipeline chaining, but
    the preview editor only reflects operations stored in ImageEditChain rows.
    This helper bridges selected-document workflow runs into that editor state.
    """
    library_path = state.get("library_path") or inputs.get("library_path")
    if not library_path:
        return []

    db = db_manager.get_database(library_path)
    records: list[dict[str, Any]] = []
    for doc_id in _candidate_document_ids(inputs, state):
        doc = db.get(Document, doc_id)
        if doc is None:
            continue
        operation = build_operation(doc)
        operation.setdefault("created_at", utc_now().isoformat())

        rows = list(db.query(ImageEditChain, document_id=doc.id))
        if rows:
            chain = rows[0]
            chain.operations.append(operation)
            chain.updated_at = utc_now()
        else:
            chain = ImageEditChain(document_id=doc.id, operations=[operation])
        db.save(chain)
        records.append({"document_id": doc.id, "operation": operation})
    return records


def _document_by_source_path(db, doc_ids: list[str]) -> dict[str, Document]:
    """Map every path a document is known by onto that document.

    A workflow tool is handed FILE PATHS and knows nothing about document ids,
    so pairing an output back to its node has to go through the path it was
    derived from. Both ``path`` and ``metadata["source_path"]`` are indexed
    because LINK imports record the original location while COPY records the
    library one, and a workflow may have been handed either.
    """
    by_path: dict[str, Document] = {}
    for doc_id in doc_ids:
        doc = db.get(Document, doc_id)
        if doc is None:
            continue
        for candidate in (doc.path, (doc.metadata or {}).get("source_path")):
            if candidate:
                by_path[str(Path(candidate))] = doc
    return by_path


def persist_workflow_renditions(
    inputs: dict[str, Any],
    state: State,
    *,
    role: str,
    results: list[dict[str, Any]],
) -> dict[str, Any]:
    """Persist a workflow's image outputs as Renditions on their documents.

    Before this, the image tools did real per-file work, wrote PNGs to a temp
    directory and returned the paths — and NOTHING persisted. No artifact, no
    rendition, no document change. A run "completed successfully" with no
    user-visible effect, which is absence-read-as-success wearing a green tick.

    Outputs are paired to documents by the ``source`` path each result records,
    never by list position: index-pairing silently mis-attributes every output
    the moment one file fails or is skipped, and a rendition on the wrong page
    is precisely the defect this whole program exists to remove.

    Bytes are copied under library storage. The tools write to
    ``$TMPDIR``, which is swept — a Rendition row pointing into a temp
    directory is a promise the library cannot keep.

    Returns a report, including what it could NOT place and why, so a caller
    can be honest about a no-op instead of reporting success.
    """
    from fichero_server.importers.ingest import _copy_to_library

    report: dict[str, Any] = {
        "renditions": [],
        "unmatched_outputs": [],
        "skipped_no_document": 0,
    }

    library_path = state.get("library_path") or inputs.get("library_path")
    if not library_path:
        # Not an error: plenty of runs are pipeline-only and never touch a
        # library. Reported so "nothing persisted" is a stated fact rather
        # than an absence the caller has to infer.
        report["skipped_reason"] = "no library_path in scope — nothing persisted"
        return report

    db = db_manager.get_database(library_path)
    package_path = Path(library_path)
    doc_ids = _candidate_document_ids(inputs, state)
    by_path = _document_by_source_path(db, doc_ids)

    for result in results:
        source = result.get("source")
        outputs = result.get("outputs") or []
        if not outputs:
            continue
        doc = by_path.get(str(Path(source))) if source else None
        if doc is None:
            # The output exists but we cannot say WHICH node it belongs to.
            # Recorded rather than attached to a guess.
            report["unmatched_outputs"].extend(str(o) for o in outputs)
            report["skipped_no_document"] += 1
            continue

        for output in outputs:
            # Idempotence is checked BEFORE the copy, and keyed on what the
            # workflow PRODUCED rather than where it landed: _copy_to_library
            # generates a unique destination name every call, so a stored-path
            # key could never match a re-run and every run would stack another
            # row. Checking first also avoids copying bytes we would discard.
            if any(
                row.role == role and row.produced_from == str(output)
                for row in db.query(Rendition, document_id=doc.id)
            ):
                continue
            try:
                stored = _copy_to_library(Path(output), package_path)
            except Exception as exc:
                logger.warning(
                    "rendition %s for %s: could not store %s (%s)",
                    role, doc.id, output, exc,
                )
                report["unmatched_outputs"].append(str(output))
                continue

            width, height = _pixel_size(stored)
            rendition = Rendition(
                document_id=doc.id,
                role=role,
                path=str(stored),
                produced_from=str(output),
                pixel_width=width,
                pixel_height=height,
                # NOT primary. A workflow producing a new rendition must not
                # silently change what the reader opens on — that is the
                # user's call, and a pass that quietly reassigns the primary
                # is how someone ends up reading an enhanced crop believing it
                # is the archival scan.
                is_primary=False,
                producer_tool=str(state.get("tool_name") or inputs.get("tool_name") or ""),
                producer_run_id=str(state.get("run_id") or ""),
                note=f"produced by the {role} workflow",
            )
            db.save(rendition)
            report["renditions"].append(
                {"document_id": doc.id, "rendition_id": rendition.id, "path": str(stored)}
            )

    return report


def describe_no_effect(
    files: list[Any],
    output_files: list[Any],
    report: dict[str, Any],
) -> str | None:
    """One sentence naming why a run had no user-visible effect, or ``None``.

    Lives here, not copied into each tool, so every image workflow reports a
    no-op the SAME way. Six hand-written variants would drift, and the whole
    reason this exists is that "completed successfully" over a no-op is
    absence-read-as-success — a green tick on a run that changed nothing is
    worse than an error, because nobody investigates a success.
    """
    if not files:
        return "no input files were supplied — nothing to do"
    if not output_files:
        return f"{len(files)} input file(s) produced no output"
    if report.get("renditions"):
        return None
    already = report.get("already_children", 0)
    if already:
        # The reuse narration (S11): a re-run that found every part already
        # persisted did exactly what it should — say THAT, not a warning.
        return (
            f"already split — {already} part(s) exist from an earlier run; "
            "nothing new to attach"
        )
    reason = report.get("skipped_reason")
    if reason:
        return f"{len(output_files)} file(s) written but not persisted: {reason}"
    if report.get("skipped_no_document"):
        return (
            f"{len(output_files)} file(s) written but "
            f"{report['skipped_no_document']} could not be matched to a "
            "document — no rendition was attached"
        )
    return f"{len(output_files)} file(s) written but no rendition was attached"


def persist_workflow_child_regions(
    inputs: dict[str, Any],
    state: State,
    *,
    results: list[dict[str, Any]],
    part_key: str,
    role: str,
    method: str,
    name: str,
) -> dict[str, Any]:
    """Turn a workflow's cut-up parts into CHILD NODES of the page they came from.

    split_images and segment_images did real work and created nothing: they
    wrote part files to a temp directory and returned the paths, so a run
    "completed" with no node, no geometry and no user-visible effect — the same
    disease remove_background had.

    Children carry `region_in_parent`, the SAME geometry the in-app split
    writes since ca1ed6b25. That convergence is the point: a page cut up by a
    workflow and a page cut up by hand are now the same shape, so one library
    view, one unsplit, one set of coordinate maths serves both.

    The parent is the SOURCE DOCUMENT — it is already a node, so unlike the
    staged-import path there is no opening to adopt. Deliberately does NOT
    attach any archival original: whether previously-deferred originals get
    attached is a scope decision still parked with Daniel, and a workflow must
    not pre-empt it.

    Each part gets its own rendition, because a workflow part HAS bytes —
    unlike an in-app split child, which is a virtual region of its parent.
    The converged model allows both: a child either has renditions or falls
    back to rendering its region of the parent.
    """
    from fichero_server.importers.ingest import _copy_to_library
    from fichero_server.models import DocType

    report: dict[str, Any] = {
        "children": [],
        "unmatched_sources": [],
        "skipped_no_region": 0,
        "already_children": 0,
        # Parts whose bytes could not be stored. A failure here MUST reach the
        # caller: a part that silently vanishes is a page the user cut and
        # never got, reported as success.
        "failed_outputs": [],
    }

    library_path = state.get("library_path") or inputs.get("library_path")
    if not library_path:
        report["skipped_reason"] = "no library_path in scope — no nodes created"
        return report

    db = db_manager.get_database(library_path)
    package_path = Path(library_path)
    by_path = _document_by_source_path(db, _candidate_document_ids(inputs, state))

    for result in results:
        source = result.get("source")
        parts = result.get(part_key) or []
        if not parts:
            continue
        parent = by_path.get(str(Path(source))) if source else None
        if parent is None:
            report["unmatched_sources"].append(str(source))
            continue

        for index, part in enumerate(parts, start=1):
            output = part.get("output_file")
            if not output:
                continue
            # Idempotent: a re-run must not create a second child for the same
            # part. Keyed on the produced file, for the same reason the
            # rendition path is — the stored path is renamed on copy.
            if any(
                (child.metadata or {}).get("produced_from") == str(output)
                for child in db.query(Document, parent_id=parent.id)
            ):
                # Idempotent re-run (S11, 2026-08-23): COUNTED, so the
                # narration can say "already split" instead of the false
                # "no rendition was attached".
                report["already_children"] += 1
                continue

            region = _region_from_part(part, method)
            if region is None:
                # A part whose frame we cannot name gets NO region rather than
                # a guessed one. Counted so the caller can say so.
                report["skipped_no_region"] += 1

            try:
                stored = _copy_to_library(Path(output), package_path)
            except Exception as exc:
                # Routed into the report, not just logged. An only-log broad
                # handler influences nothing downstream (#4395): the caller
                # would report success while a cut page quietly went missing.
                logger.warning(
                    "child region for %s: could not store %s (%s)", parent.id, output, exc
                )
                report["failed_outputs"].append(
                    {"output": str(output), "parent_id": parent.id, "error": str(exc)}
                )
                continue

            child = Document(
                parent_id=parent.id,
                doc_type=DocType.chunk,
                file_type=parent.file_type,
                name=f"{parent.name} {name} {index}",
                path=str(stored),
                sequence=index,
                region_in_parent=region,
                metadata={
                    "derived_from": parent.id,
                    # The same discovery key the in-app split uses, so
                    # `_split_children` and therefore unsplit find these too.
                    "split_source_id": parent.id,
                    "produced_from": str(output),
                },
                source_authority=parent.source_authority,
                source_metadata=parent.source_metadata,
                provenance_chain=list(parent.provenance_chain or []),
                image_provenance=parent.image_provenance,
            )
            db.save(child)
            child_width, child_height = _pixel_size(stored)
            db.save(
                Rendition(
                    document_id=child.id,
                    role=role,
                    path=str(stored),
                    produced_from=str(output),
                    pixel_width=child_width,
                    pixel_height=child_height,
                    is_primary=True,
                    producer_tool=str(state.get("tool_name") or ""),
                    producer_run_id=str(state.get("run_id") or ""),
                    note=f"cut from {parent.name} by the {role} workflow",
                )
            )
            report["children"].append({"document_id": child.id, "parent_id": parent.id})

    return report


def _pixel_size(path: Path) -> tuple[int | None, int | None]:
    """The stored image's own frame, or (None, None) if it cannot be read.

    A rendition that does not record its pixel dimensions cannot be checked
    against the node it belongs to, and the whole "same frame = rendition,
    different frame = node" rule becomes unverifiable — a rotated rendition
    (width and height swapped) is then indistinguishable from a same-frame
    one, and any child region measured against "the parent" is ambiguous.
    `Rendition` has carried these two fields all along; nothing filled them.

    Unreadable dimensions are recorded as absent, never guessed: an unknown
    frame is a fact, and inventing one would recreate the defect this program
    removes.
    """
    try:
        from PIL import Image

        with Image.open(path) as image:
            return image.width, image.height
    except Exception as exc:  # pragma: no cover - depends on the stored file
        logger.warning("could not read pixel size of %s: %s", path, exc)
        return None, None


def _region_from_part(part: dict[str, Any], method: str) -> NodeRegion | None:
    """Normalize a part's pixel bbox against the frame it was cut from."""
    bbox = part.get("bbox")
    # `rendition_id` is deliberately left unset here, and that is currently
    # CORRECT rather than an omission: the split tools cut the document's own
    # source file, so `source_size` IS the node's original frame and None
    # means exactly that. This is the seam that must start setting it when a
    # tool cuts from a RENDITION instead — the entry-scoped-run work, where a
    # crop is taken from a rotated or enhanced picture.
    size = part.get("source_size")
    if not (isinstance(bbox, list) and len(bbox) == 4):
        return None
    if not (isinstance(size, list) and len(size) == 2):
        return None
    width, height = float(size[0] or 0), float(size[1] or 0)
    if width <= 0 or height <= 0 or float(bbox[2]) <= 0 or float(bbox[3]) <= 0:
        return None
    return NodeRegion(
        rect=[
            float(bbox[0]) / width,
            float(bbox[1]) / height,
            float(bbox[2]) / width,
            float(bbox[3]) / height,
        ],
        # MEASURED: a workflow cut the pixels at these coordinates. It is not
        # a nominal guess at where a fold might be.
        confidence=RegionConfidence.measured,
        method=method,
    )

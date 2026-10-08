"""`Document.page_content` as a CACHE of the page's derived text, with ONE writer (#5077).

A page's text is worked out from its working pass and each line's counting reading
(`source.point.text-is-derived`). `page_content` is the stored copy every consumer reads (Reader,
search, embeddings, extraction, chat, export). Before this, a reading correction changed the derived
text and left the copy alone, so corrections went to a text nobody reads.

The refresh lives here, called from `ActionRegistry.invoke` -- the one place every action lands,
undo and redo included -- and NOT from the individual reading actions. Two halves:

* `refresh_in_transaction` runs inside the action's transaction, so the reading change and the
  cache commit or roll back together;
* `queue_reembed` queues, in the same transaction, one durable re-embed job per page on the
  engine's job scheduler (`execution/jobs.py`), so search matches the corrected text without a
  correction waiting for the embedder, and one re-read of the page's names (`queue_reread_names`).

Not refreshed: a page whose `page_content` a person edited directly (`page_content_is_user_edited`)
-- the direct edit route is a second writer, still open -- and a page with no working pass.
The cache is the derived text, BYTE FOR BYTE (`document_text(...).text`): one text, not two that
differ by a separator. If lines should be joined with a newline, that is a change to the derived
text and its pinned behaviour, made there.

Triggers: reading changes, the working-pass choice, and every segment action that can change which
lines the derived text has (`_MEMBERSHIP_ACTIONS`). A plain geometry edit does not: `segment.update`
counts only when it sets `is_furniture`.
"""
from __future__ import annotations

import logging
import hashlib
from typing import Any


logger = logging.getLogger(__name__)

#: Domains whose actions change what a line reads.
_TEXT_DOMAINS = frozenset({"representation"})
#: `ChangeSpec.emit_type`s outside those domains that change which pass is the page's text.
_TEXT_EMIT_TYPES = frozenset({"pass.working_chosen"})
#: Segment actions that add, remove, merge, split, restore or re-parent the lines of a pass.
#: Moves in a reading order: the page's text follows its `as-written` order (Q5), so a move there
#: changes the text. A move in another named order derives the same text and writes nothing.
_ORDER_ACTIONS = frozenset({"reading_order.place", "reading_order.restore_place", "reading_order.remove"})

_MEMBERSHIP_ACTIONS = frozenset({
    "segment.create", "segment.create_many", "segment.delete", "segment.undelete",
    "segment.merge", "segment.unmerge", "segment.split", "segment.unsplit",
    "segment.uncombine", "segment.restore_version", "segment.restore_versions",
    "segment.pass_create", "segment.pass_delete", "segment.pass_restore",
})


#: The actions whose named pass may NOT be the pass that ends up working, so "is the working pass among
#: those touched?" is the wrong question to ask of it.
#:
#: Deleting the working pass names the pass being REMOVED; the page's text then comes from a
#: surviving pass that the action never named, so the skip fired and the cache kept the deleted
#: pass's text. Found by `test_working_pass_across_surfaces`, which failed against the committed
#: code — the defect was in the #5086 skip, a few hours old.
#:
#: `segment.pass_restore` was in this set and is NOT needed, proven by removing it and watching 23
#: tests stay green: a restored pass that becomes working IS the pass the action names, so it is
#: already in `touched` and the skip never fires; one that does not become working leaves the
#: working pass alone, so skipping is correct. An entry nobody needs is a permission sitting
#: unspent, and the next person to need one finds it already granted.
#:
#: A NAME SET IS A LIABILITY and this one is deliberately as small as the evidence allows. A third
#: action with this property would be silently wrong — the property-based form is "a pass this
#: action named is now deleted", which needs no list; it is worth doing when there is a second
#: entry, and not before.
#:
#: `segment.pass_ground_truth` (#5513) is the second entry: UNMARKING the working pass names the pass
#: that stops being the person's, and the page's text then comes from a pass the action never named.
_CHANGES_WHICH_PASS_IS_WORKING = frozenset({"segment.pass_delete", "segment.pass_ground_truth"})


def _document_ids(spec: Any, action_name: str, params: Any) -> list[str]:
    triggered = (
        bool(_TEXT_DOMAINS & set(spec.domains))
        or spec.emit_type in _TEXT_EMIT_TYPES
        or action_name in _ORDER_ACTIONS
        or (action_name in _MEMBERSHIP_ACTIONS and _restore_may_change_text(spec, action_name))
        or (action_name == "segment.update" and getattr(params, "is_furniture", None) is not None)
        # A deletion changes the page's STANDING text, which search reads (#5179). A withdraw or a
        # restore names no kind, and is rare: it always refreshes.
        or (action_name == "editorial.record" and str(getattr(params, "kind", "")) in {"deleted", "EditorialFactKind.deleted"})
        or action_name in ("editorial.withdraw", "editorial.restore")
        # Every box move from the app is a `convert_and_edit`; only a delete or a combine changes
        # which lines the page has (an add has no reading yet).
        or (
            action_name == "segment.convert_and_edit"
            and str(getattr(getattr(params, "edit", None), "op", "")) in {"delete", "combine", "RegionEditOp.DELETE", "RegionEditOp.COMBINE"}
        )
    )
    return list(dict.fromkeys(spec.document_ids)) if triggered else []


def _restore_may_change_text(spec: Any, action_name: str) -> bool:
    """A restore refreshes only when it put back something that decides the text (slice 12).

    `segment.restore_version(s)` is the UNDO of a box move as well as of a re-parent. The move
    is exempt as an edit (`segment.update` counts only with `is_furniture`); its undo was not,
    and on a 20,000-shape page one undo re-derived the whole page: 14 s against the editor's
    100 ms. The action records `text_relevant` from the two rows it held. ABSENT means refresh
    -- an older row, or an action that does not say, is never skipped on a guess.
    """
    if action_name not in ("segment.restore_version", "segment.restore_versions"):
        return True
    after = spec.after if isinstance(spec.after, dict) else {}
    return after.get("text_relevant", True) is not False


def _touched_passes(db: Any, spec: Any) -> set[str]:
    """The passes an action changed, from what it already carries: the passes it names, else the
    passes of the segments it names (one `get` each, not a page read). EMPTY when it cannot tell,
    and empty means "do not skip"."""
    passes = set(spec.pass_ids)
    if passes:
        return passes
    from fichero_server.models import Segment

    for segment_id in spec.segment_ids:
        row = db.get(Segment, segment_id)
        if row is not None:
            passes.add(row.pass_id)
    return passes


def _working_pass_id(db: Any, document_id: str) -> str | None:
    """The document's working pass, the one answer every surface reads (`working_pass`, #5467),
    without deriving text."""
    from fichero_server.api.routes.document.segment_readings import working_pass

    return working_pass(db, document_id).pass_id


def _derives_text(pass_id: str | None) -> bool:
    """Whether a working pass has rows to derive the page's text from. An unconverted result does
    not (its words become rows when it converts): the stored text stands, never replaced by ""."""
    from fichero_server.api.routes.document.segment_readings import is_unconverted_pass

    return pass_id is not None and not is_unconverted_pass(pass_id)


def cache_text(derived: Any) -> str:
    return derived.text


#: `Document.metadata` key holding the page's STANDING text (`source.sure.search-finds-what-stands`,
#: #5179): the page text with every live `deleted` stretch left out, kept only when it differs.
#: Search matches it beside `page_content`, so a `<subst>` read "XY" (Y struck) is found by X alone.
STANDING_TEXT = "page_text_standing"


def standing_text(db: Any, derived: Any) -> str | None:
    """The derived text with every live `deleted` editorial fact's stretch removed, or None when the
    page has none. A fact's offsets are code points into its reading, which sits in the derived text
    at its span; a fact naming no reading applies to its segment's span."""
    from fichero_server.models.editorial import EditorialFact, EditorialFactKind

    if not derived.spans:
        return None
    segment_ids = sorted({span.segment_id for span in derived.spans})
    facts = [
        f for f in db.query_in(EditorialFact, "segment_id", segment_ids)
        if f.kind == EditorialFactKind.deleted and f.withdrawn_at is None
        and f.char_start is not None and f.char_end is not None and f.char_end > f.char_start
    ]
    if not facts:
        return None
    cut: list[tuple[int, int]] = []
    for span in derived.spans:
        for f in facts:
            if f.segment_id != span.segment_id:
                continue
            if f.representation_id is not None and f.representation_id != span.representation_id:
                continue
            start = min(span.end, span.start + f.char_start)
            end = min(span.end, span.start + f.char_end)
            if end > start:
                cut.append((start, end))
    if not cut:
        return None
    keep, position = [], 0
    for start, end in sorted(cut):
        if start > position:
            keep.append(derived.text[position:start])
        position = max(position, end)
    keep.append(derived.text[position:])
    return "".join(keep)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def line_map(db: Any, derived: Any) -> list[dict[str, Any]]:
    """The derived text's spans folded to LINES: a word's span joins its line's, because a line is
    what an order moves and what a caret on it names. No direction is stored here: the Reader
    resolves each line's at render (`views._with_directions`), because a direction setting changes
    no text and so would never refresh a stored one (#5171)."""
    from fichero_server.models import Segment

    if not derived.spans:
        return []
    ids = sorted({span.segment_id for span in derived.spans})
    segments = {row.id: row for row in db.query_in(Segment, "id", ids)}
    parent_ids = sorted({row.parent_segment_id for row in segments.values() if row.parent_segment_id})
    parents = {row.id: row for row in db.query_in(Segment, "id", parent_ids)} if parent_ids else {}
    lines: list[dict[str, Any]] = []
    for span in derived.spans:
        segment = segments.get(span.segment_id)
        line_id = span.segment_id
        if segment is not None and segment.kind != "line":
            parent = parents.get(segment.parent_segment_id or "")
            if parent is not None and parent.kind == "line":
                line_id = parent.id
        if lines and lines[-1]["segment_id"] == line_id:
            lines[-1]["char_end"] = span.end
            lines[-1]["representation_id"] = None   # read from its words: no ONE reading to correct
        else:
            lines.append({
                "segment_id": line_id, "char_start": span.start, "char_end": span.end,
                # The counting reading the line's text came from (#5154): what a correction typed
                # in the Reader corrects (`basedOn`). None when the text came from its words.
                "representation_id": span.representation_id if span.segment_id == line_id else None,
            })
    return lines


def cached_line_map(db: Any, document_id: str, text: str) -> list[dict[str, Any]] | None:
    """The stored map for this exact text; [] when the text is not the one it maps; None when the
    page has never been refreshed since maps were stored."""
    from fichero_server.models import PageLineMap

    row = db.get(PageLineMap, document_id)
    if row is None:
        return None
    return row.lines if row.text_sha == _sha(text) else []


#: `Document.metadata` key holding the `DERIVATION_VERSION` the stored `page_content` was derived
#: under. Absent means "before stamping existed": as stale as any older number.
DERIVATION_STAMP = "page_text_derivation"


def _save_line_map(db: Any, doc: Any, text: str, derived: Any) -> None:
    """Store the page's line map for ``text``; when a line's text changed, marks made on it follow
    their words (#5077). The old map and text are read BEFORE they are replaced."""
    from fichero_server.actions.highlight_reanchor import reanchor_mark_targets
    from fichero_server.models import PageLineMap

    old_text = doc.page_content or ""
    old_lines = cached_line_map(db, doc.id, old_text) or []
    new_lines = line_map(db, derived)
    db.save(PageLineMap(id=doc.id, text_sha=_sha(text), lines=new_lines))
    if old_lines and old_text != text:
        reanchor_mark_targets(db, doc.id, old_text, old_lines, text, new_lines)


def _store(db: Any, doc: Any, text: str, now: Any, standing: str | None = None) -> bool:
    """Write the cache and stamp it with the derivation that produced it. True when the TEXT, or the
    standing text search reads beside it, changed (a page to re-embed); a stamp-only update is
    saved but is not a text change."""
    from fichero_server.api.routes.document.segment_readings import DERIVATION_VERSION

    metadata = dict(doc.metadata or {})
    standing_changed = metadata.get(STANDING_TEXT) != standing
    text_changed = text != (doc.page_content or "") or standing_changed
    if not text_changed and metadata.get(DERIVATION_STAMP) == DERIVATION_VERSION:
        return False
    metadata[DERIVATION_STAMP] = DERIVATION_VERSION
    if standing is None:
        metadata.pop(STANDING_TEXT, None)
    else:
        metadata[STANDING_TEXT] = standing
    doc.metadata = metadata
    if text_changed:
        old_text = doc.page_content or ""
        if text != old_text:
            # Highlights quote the old text by offset; re-find them in the new one (#5077).
            from fichero_server.actions.highlight_reanchor import reanchor_highlights

            reanchor_highlights(db, doc.id, old_text, text)
        doc.page_content = text
        doc.updated_at = now
    db.save(doc)
    return text_changed


def ensure_current(db: Any, document_ids: list[str]) -> list[str]:
    """Re-derive, ONCE, any of these pages whose cached text predates the current derivation.

    Called on read (the Reader's page, #5148 follow-up). A changed derivation used to leave every
    page cached under the old one wrong until something else happened to touch it: the doubled
    Chinese text stayed doubled in libraries imported before the fix. The stamp makes a cache say
    which derivation wrote it; a read that finds an older one refreshes it, stamps it, and the
    next read costs one dict lookup. Pages that are not a derived cache -- no working pass, or a
    person's own edit of `page_content` -- are left alone. Returns the ids whose text changed."""
    from fichero_server.api.routes.document.segment_readings import DERIVATION_VERSION, document_text
    from fichero_server.core.timeutil import utc_now
    from fichero_server.models import Document
    from fichero_server.workflows.curation_guard import page_content_is_user_edited

    changed: list[str] = []
    for document_id in document_ids:
        doc = db.get(Document, document_id)
        if doc is None or (doc.metadata or {}).get(DERIVATION_STAMP) == DERIVATION_VERSION:
            continue
        if page_content_is_user_edited(doc) or not _derives_text(_working_pass_id(db, document_id)):
            continue
        derived = document_text(db, document_id)
        if not _derives_text(derived.pass_id):
            continue
        text = cache_text(derived)
        # The map is re-stored with the text: a stale stamp means a stale map too.

        _save_line_map(db, doc, text, derived)
        if _store(db, doc, text, utc_now(), standing_text(db, derived)):
            changed.append(document_id)
    return changed


def refresh_in_transaction(db: Any, spec: Any, action_name: str = "", params: Any = None) -> list[str]:
    """Rewrite `page_content` for the pages this action changed the text of. Returns the ids whose
    stored text actually changed (the ones to re-embed)."""
    from fichero_server.api.routes.document.segment_readings import document_text
    from fichero_server.models import Document
    from fichero_server.core.timeutil import utc_now
    from fichero_server.workflows.curation_guard import page_content_is_user_edited

    changed: list[str] = []
    document_ids = _document_ids(spec, action_name, params)
    if not document_ids:
        return changed  # most actions: nothing below may cost anything (no per-segment walk)
    touched = _touched_passes(db, spec)
    for document_id in document_ids:
        doc = db.get(Document, document_id)
        if doc is None or page_content_is_user_edited(doc):
            continue
        if touched and action_name not in _CHANGES_WHICH_PASS_IS_WORKING and _working_pass_id(db, document_id) not in touched:
            # The change is on a pass nobody is reading (an import is not the working pass), so
            # the derived text cannot have changed. THIS SKIP HAS A PREMISE: a newly imported pass
            # cannot quietly become the working pass behind a person's earlier choice (an
            # explicit `pass.choose_working` records a `chosen` basis that outranks recency). If
            # that ruling ever changed, this would start dropping real refreshes.
            #
            # Reading the whole page to find that out cost 38 s inside a dense import (#5086). Not a
            # check by action name: any future action with this property is covered.
            continue
        derived = document_text(db, document_id)
        if not _derives_text(derived.pass_id):
            continue  # no working pass, or an unconverted result: nothing derives, so nothing is cached
        text = cache_text(derived)
        # Stored even when the text is unchanged: two lines that read alike can swap places.
        _save_line_map(db, doc, text, derived)
        if _store(db, doc, text, utc_now(), standing_text(db, derived)):
            changed.append(document_id)
    return changed


#: The job kind, named as the recipe job registry names it (`recipes/jobs.py`).
REEMBED_KIND = "make-a-vector"


def queue_reembed(db: Any, document_ids: list[str]) -> None:
    """Queue the re-embed of each changed page as a durable job, in the action's own transaction
    (`activity.correction-reembed-visible`, `activity.durable.enqueue-with-the-change`).

    Measured on a 300-line page: the embed alone was ~8 s per correction, and a scholar correcting
    line after line pays it every time, so it runs OFF the request path, on the engine's job
    scheduler. The job reads the page's CURRENT text when it runs, so corrections that arrive while
    one is waiting are covered by it: one waiting job per page. Being a row, it shows in Activity,
    obeys the global pause, and survives quit (it used to be a daemon thread, lost on quit)."""
    from fichero_server.execution import jobs

    for document_id in document_ids:
        jobs.enqueue(db, REEMBED_KIND, document_id, started_by="correction")
    queue_reread_names(db, document_ids)


#: The re-read of a corrected page's names and claims: a job of its own (#5361), so it shows in
#: Activity, obeys the pause, survives a quit, and an embed failure never takes it down with it.
REREAD_NAMES_KIND = "read-names-again"


def queue_reread_names(db: Any, document_ids: list[str]) -> None:
    """Queue, in the change's own transaction, one re-read of each corrected page's names
    (`activity.auto.reextract-on-change`). Only where the library reads names automatically:
    nothing is queued that the library did not ask for. The job reads the page's current text
    when it runs, so a run of corrections to one page makes one job."""
    if not document_ids:
        return
    from fichero_server.importers.nlp_draft import auto_nlp_enabled

    if not auto_nlp_enabled():
        return
    from fichero_server.execution import jobs

    for document_id in document_ids:
        jobs.enqueue(db, REREAD_NAMES_KIND, document_id, started_by="correction")


def _reembed(db: Any, document_id: str) -> None:
    """The job: embed the page's current text (behind the same gate as every other embed, so a
    correction and an import never stack two all-core ONNX passes)."""
    from fichero_server.importers.derivatives import _embed_gate
    from fichero_server.models import Document

    doc = db.get(Document, document_id)
    if doc is not None and doc.page_content:
        with _embed_gate:
            db.embed(doc)


def _register() -> None:
    from fichero_server.execution import jobs

    jobs.register_kind(REEMBED_KIND, _reembed, model="embedder")
    jobs.register_kind(REREAD_NAMES_KIND, lambda db, doc_id: reread_names_after_commit(db, doc_id), model="spacy",
                       name="Read names again after a correction")


_register()


def reread_names_after_commit(db: Any, document_id: str) -> None:
    """Where the library reads names automatically, read the corrected page again so its
    entities and claims follow the new text (#5361). Off where NLP is off: nothing is run that
    the library did not ask for."""
    from pathlib import Path

    from fichero_server.importers.nlp_draft import auto_nlp_enabled

    if not auto_nlp_enabled():
        return
    from fichero_server.importers.derivatives import _nlp_stage

    # Never raises: a failure is recorded on the page as `nlp_error`.
    _nlp_stage(document_id, str(Path(db.path).parent), after_correction=True)

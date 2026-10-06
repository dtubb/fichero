"""Extract Historical Date tool (#3322, plan #3319).

Deterministic (no LLM): parses the date a document was WRITTEN and fills the
``date_original`` / ``date_jdn`` / ``date_jdn_end`` / ``date_meta`` columns
plus a ``dates`` artifact — the storage the sort/filter layer reads.

Priority per #3309:
  1. explicit on-document date (head of ``page_content``, rule patterns)
  2. ``source_metadata`` date fields (``date``, ``year``, ``issued``)
  3. none → columns stay NULL and ``date_meta`` records ``none_found``.

``created_at`` (import time) is NEVER substituted into ``date_original`` —
that would be a silent fallback lying about a manuscript. "The document says
it is undated" (n.d. / s.f.) is recorded as ``undated_explicit``: a different
fact from "we found nothing", and both are different from "never extracted"
(``date_meta`` NULL).
"""

from __future__ import annotations

import logging
from typing import Any

import ftfy

from fichero_server.core.timeutil import utc_now
from fichero_server.db import db_manager
from fichero_server.histdate import (
    STATUS_NONE_FOUND,
    STATUS_UNDATED_EXPLICIT,
    HistoricalDate,
    PageDate,
    find_page_date,
    is_explicitly_undated,
    parse_historical_date,
    years_from_name,
)
from fichero_server.llm import LLMConfig
from fichero_server.models import Artifact, Document
from fichero_server.workflows.registry import register_tool
from fichero_server.workflows.tools._workflow_change_emit import (
    emit_workflow_artifact_changes,
    emit_workflow_document_changes,
)
from fichero_server.workflows.types import DataType, PortDef, State

logger = logging.getLogger(__name__)

_METADATA_DATE_KEYS = ("date", "issued", "year", "date_original", "iffy_original_date")


def _from_source_metadata(doc: Document) -> HistoricalDate | None:
    meta = doc.source_metadata or {}
    for key in _METADATA_DATE_KEYS:
        raw = meta.get(key)
        if raw is None:
            continue
        parsed = parse_historical_date(str(raw))
        if parsed is not None:
            parsed.meta["source"] = "metadata"
            return parsed
    return None


def _first_line(text: str | None) -> str:
    for line in (text or "").splitlines():
        if line.strip():
            return line.strip()
    return ""


def volume_years_for(db: Any, doc: Document) -> list[int]:
    """The years the page's volume covers, read from the nearest ancestor whose name has them.

    WHY the ancestors and not the page: a diary page is "IMG_0123"; its volume
    is the folder "NCM_Diary_19150108-19180628". A heading with no year takes
    its year from here (marked inferred), and the weekday chooses among a
    multi-year volume's years (#5514). Up to four levels; [] when none says.
    """
    seen: set[str] = set()
    parent_id = getattr(doc, "parent_id", None)
    for _ in range(4):
        if not parent_id or parent_id in seen:
            break
        seen.add(parent_id)
        parent = db.get(Document, parent_id)
        if not isinstance(parent, Document):
            break
        years = years_from_name(parent.name)
        if years:
            return years
        parent_id = parent.parent_id
    return []


def resolve_page_date(
    doc: Document,
    *,
    year_start_march: bool = False,
    assume_julian: bool = False,
    volume_years: list[int] | None = None,
    day_first: bool = False,
) -> tuple[HistoricalDate | None, str, PageDate]:
    """(parsed date | None, status, what the heading said). Pure — no DB access.

    The third value carries what a bare date cannot: a heading REFUSED (an
    impossible day, a year out of range) and a non-entry page's marker, so
    the tool can record them instead of reporting a plain "none found".
    """
    if is_explicitly_undated(_first_line(doc.page_content)):
        return None, STATUS_UNDATED_EXPLICIT, PageDate()
    finding = find_page_date(
        doc.page_content and ftfy.fix_text(doc.page_content) or "",
        year_start_march=year_start_march,
        assume_julian=assume_julian,
        volume_years=volume_years,
        day_first=day_first,
    )
    parsed = finding.date
    if parsed is None:
        parsed = _from_source_metadata(doc)
    if parsed is None:
        return None, STATUS_NONE_FOUND, finding
    return parsed, "dated", finding


def resolve_document_date(
    doc: Document,
    *,
    year_start_march: bool = False,
    assume_julian: bool = False,
    volume_years: list[int] | None = None,
    day_first: bool = False,
) -> tuple[HistoricalDate | None, str]:
    """(parsed date | None, status). Pure — no DB access."""
    parsed, status, _finding = resolve_page_date(
        doc, year_start_march=year_start_march, assume_julian=assume_julian,
        volume_years=volume_years, day_first=day_first,
    )
    return parsed, status


@register_tool(
    name="date_extract",
    display_name="Extract Date",
    description=(
        "Extract the historical date a document was written (Gregorian, "
        "Julian, French Republican, Old Style, regnal, era names) and store "
        "it as a Julian Day Number range for sorting and filtering."
    ),
    category="transform",
    icon="calendar",
    color="brown",
    uses_llm=False,
    supports_batch=False,
    input_ports=[
        PortDef(
            id="documents",
            name="Documents",
            port_type="input",
            data_type=DataType.JSON,
            required=False,
            description="Documents from the source selector",
        ),
    ],
    output_ports=[
        PortDef(
            id="dates",
            name="Dates",
            port_type="output",
            data_type=DataType.JSON,
            description="Per-document extraction results",
        ),
        PortDef(
            id="text",
            name="Summary",
            port_type="output",
            data_type=DataType.TEXT,
            description="Human-readable extraction summary",
        ),
    ],
    sort_order=37,
)
async def date_extract_tool(
    inputs: dict[str, Any],
    state: State,
    llm_config: LLMConfig,
) -> dict[str, Any]:
    library_path = state.get("library_path") or inputs.get("library_path")
    if not library_path:
        # No library = nothing this tool can honestly do; fail loud (#4467).
        raise ValueError("date_extract: no library_path in workflow state")

    raw_documents = inputs.get("documents") or state.get("documents") or []
    if not raw_documents:
        raise ValueError(
            "date_extract: no documents resolved from the source node — "
            "refusing to complete a run that would process nothing (#4467)"
        )

    config = (inputs.get("config") or {}) if isinstance(inputs.get("config"), dict) else {}
    year_start_march = bool(config.get("year_start_march", False))
    assume_julian = bool(config.get("assume_julian", False))
    # Numeric dates read month/day unless the corpus says day/month (histdate rules).
    day_first = bool(config.get("day_first", False))

    db = db_manager.get_database(library_path)
    results: list[dict[str, Any]] = []
    dated = undated = none_found = 0
    changed_ids: list[str] = []
    # #4890: this tool already announced the DOCUMENTS whose date columns moved and
    # said nothing about the `dates` artifacts it writes beside them, so a view
    # showing a page's artifacts stayed stale. The ids were never captured -- each
    # artifact was constructed inside its own `db.save(...)` call -- which is why
    # this needed more than a key on the return.
    dated_artifact_ids: list[str] = []
    dated_artifact_doc_ids: list[str] = []

    pinned = conflicts = 0

    for raw in raw_documents:
        doc_id = raw.get("id") if isinstance(raw, dict) else getattr(raw, "id", None)
        if not doc_id:
            continue
        doc = db.get(Document, doc_id)
        if doc is None:
            logger.warning("date_extract: document %s not found — skipping", doc_id)
            continue

        parsed, status, finding = resolve_page_date(
            doc,
            year_start_march=year_start_march,
            assume_julian=assume_julian,
            volume_years=volume_years_for(db, doc),
            day_first=day_first,
        )

        # A user assertion is a persistent curation rule, stored on the row
        # it governs (`date_meta.source == "user"`) — one mechanism, not a
        # side table that must stay in agreement with the columns. The
        # extractor still RUNS (an improved extractor may have something to
        # say) but it may not overwrite: agreement clears any earlier
        # conflict; disagreement is RECORDED, visibly, in date_meta and the
        # artifact — neither the user's value nor the new candidate is
        # silently discarded (a disagreement the user cannot see is a fact
        # destroyed).
        existing_meta = doc.date_meta or {}
        if existing_meta.get("source") == "user":
            pinned += 1
            candidate = None
            if parsed is not None:
                candidate = {
                    "date_original": parsed.original,
                    "date_jdn": parsed.jdn,
                    "date_jdn_end": parsed.jdn_end,
                    "meta": parsed.as_meta(),
                }
            agrees = (
                # user asserted a date and extraction found the same range
                (parsed is not None
                 and doc.date_jdn == parsed.jdn
                 and doc.date_jdn_end == parsed.jdn_end)
                # user asserted undated and extraction found nothing/undated
                or (parsed is None
                    and existing_meta.get("status") == STATUS_UNDATED_EXPLICIT)
                # user cleared/asserted nothing dated and nothing found
                or (parsed is None and doc.date_jdn is None
                    and existing_meta.get("status") != STATUS_UNDATED_EXPLICIT
                    and status == STATUS_NONE_FOUND
                    and "extraction_conflict" not in existing_meta)
            )
            new_meta = dict(existing_meta)
            if agrees:
                new_meta.pop("extraction_conflict", None)
            else:
                conflicts += 1
                new_meta["extraction_conflict"] = {
                    "candidate": candidate,  # None = extraction now finds NO date
                    "found_at": utc_now().isoformat(),
                }
            if new_meta != existing_meta:
                doc.date_meta = new_meta
                doc.updated_at = utc_now()
                db.save(doc)

            record = {
                "document_id": doc.id,
                "status": "user_pinned",
                "conflict": not agrees,
                "date_original": doc.date_original,
                "date_jdn": doc.date_jdn,
                "date_jdn_end": doc.date_jdn_end,
                "meta": doc.date_meta,
            }
            results.append(record)
            pinned_artifact = Artifact(
                document_id=doc.id,
                artifact_type="dates",
                content=doc.date_original or "",
                data=record,
                provider="rule",
                model="histdate",
            )
            db.save(pinned_artifact)
            dated_artifact_ids.append(pinned_artifact.id)
            dated_artifact_doc_ids.append(doc.id)
            changed_ids.append(doc.id)
            continue
        if parsed is not None:
            doc.date_original = parsed.original
            doc.date_jdn = parsed.jdn
            doc.date_jdn_end = parsed.jdn_end
            doc.date_meta = parsed.as_meta()
            dated += 1
        else:
            # Columns stay NULL (sort falls back to created_at); date_meta
            # records WHICH kind of nothing this is.
            doc.date_original = None
            doc.date_jdn = None
            doc.date_jdn_end = None
            # source distinguishes "the MANUSCRIPT says n.d." read by
            # extraction from the same status asserted by a user in
            # document.set_date (source: user) — different claims, kept apart.
            doc.date_meta = {
                "status": status,
                "source": "extracted",
                "extracted_at": utc_now().isoformat(),
            }
            # A refused heading ("Feb 31") or a non-entry page is a finding the
            # person can see, not the same as finding nothing (#5514).
            if finding.invalid:
                doc.date_meta["invalid"] = finding.invalid
            if finding.non_entry:
                doc.date_meta["non_entry"] = finding.non_entry
            if status == STATUS_UNDATED_EXPLICIT:
                undated += 1
            else:
                none_found += 1
        doc.updated_at = utc_now()
        db.save(doc)
        changed_ids.append(doc.id)

        record = {
            "document_id": doc.id,
            "status": doc.date_meta.get("status"),
            "date_original": doc.date_original,
            "date_jdn": doc.date_jdn,
            "date_jdn_end": doc.date_jdn_end,
            "meta": doc.date_meta,
        }
        results.append(record)
        dates_artifact = Artifact(
            document_id=doc.id,
            artifact_type="dates",
            content=doc.date_original or "",
            data=record,
            provider="rule",
            model="histdate",
        )
        db.save(dates_artifact)
        dated_artifact_ids.append(dates_artifact.id)
        dated_artifact_doc_ids.append(doc.id)

    if changed_ids:
        emit_workflow_document_changes(str(library_path), document_ids=changed_ids)
    if dated_artifact_ids:
        # Separate from the document emit and not folded into it: a page whose date
        # columns did not move still gets a new `dates` artifact recording WHICH kind
        # of nothing was found, and that artifact is what an inspector shows. Folding
        # the two would have tied the artifact event to a column change -- the exact
        # mistake #4890 was.
        emit_workflow_artifact_changes(
            str(library_path),
            artifact_ids=dated_artifact_ids,
            document_ids=dated_artifact_doc_ids,
        )

    summary = (
        f"{dated} dated, {undated} explicitly undated, {none_found} with no "
        f"date found, {pinned} user-pinned ({conflicts} with a conflicting "
        f"new extraction), of {len(results)} documents"
    )
    return {"dates": results, "value": results, "text": summary, "cached": False}

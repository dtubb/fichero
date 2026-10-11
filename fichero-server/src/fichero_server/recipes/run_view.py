"""A recipe run as the person follows it, and what it made when it ends (#5576, #5577).

`source.onboard.auto.lands-on-the-run`: after Start the project shows the run: each stage, its pages done and
left, the time left, and what it waits for. Each stage that is a workflow run carries that run's own account
(`workflows/run_account.py`, #5555), the one its status and Activity show, so the stage, the run's row and its
details cannot disagree. The recipe run itself waits for another recipe run (they go one at a time) or, while a
stage runs, for whatever that stage's pages wait for (memory, a model loading).

`source.onboard.auto.results-summary`: when a run ends, one read says what it made over the pages it ran on:
pages that have a reading, names by kind and dates (the document knowledge graph's own grouping, the one the
Inspector shows), statements, the pages that failed in each stage with the offer to read them again (the run
account's), and the steps the plan skipped with their fixes.
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field

from fichero_server.workflows.run_account import PageFailure, RunAccount


class StageReader(BaseModel):
    """One reader's workflow run in a stage with a reader per kind (#5578)."""

    material: Optional[str] = Field(default=None, description="the kind it read; null: the stage's own reader, for "
                                    "pages of a kind the recipe has no reader for")
    pages: int
    model: Optional[str] = None
    child_id: Optional[str] = None
    state: str
    why: Optional[str] = None


class StageEntries(BaseModel):
    """What a stage that splits a diary or register into its dated entries did (#5581)."""

    pages: int = Field(description="the pages it split: those that had text")
    without_text: int = Field(description="the pages it left alone because they had no text")
    created: int = Field(default=0, description="entries it made")
    unchanged: int = Field(default=0, description="entries a run before made, found again as they were")
    updated: int = Field(default=0, description="entries a run before made, found again changed")
    removed: int = Field(default=0, description="entries a run before made that it no longer finds (kept, hidden)")


class StagePrepared(BaseModel):
    """What a stage that prepares faded pages did (#5580)."""

    prepared: int = Field(description="faded pages given a prepared rendition, their contrast raised")
    clear: int = Field(description="pages left alone: clear enough, or blank")
    no_image: int = Field(description="pages with no image to look at (a PDF's page, a text file)")


class StageRegions(BaseModel):
    """What a stage that finds regions with a YOLO layout model did (`prep.yolo.regions-card`, #5525)."""

    pages: int = Field(description="page images whose regions were found and saved")
    regions: int = Field(description="regions found on them")
    no_image: int = Field(description="pages with no image to look at (a PDF's page, a text file)")


class RecipeRunStep(BaseModel):
    """One stage of a recipe run: the card that carries one or more recipe steps."""

    steps: list[str]
    card: str
    job: Optional[str] = Field(default=None, description="the stage's last job (read-a-line, find-names-tag-words)")
    state: str = Field(description="waiting, running, done, failed or not run")
    child_id: Optional[str] = Field(default=None, description="the step's own job: a workflow run or a check run")
    why: Optional[str] = None
    account: Optional[RunAccount] = Field(default=None, description=(
        "a workflow stage's run account (#5555): its pages done, failed and left, the time left and what its "
        "pages wait for; null for a stage that has not started or is not a workflow run"))
    blank_versos: Optional[int] = Field(default=None, description=(
        "pages a lining or reading stage left out as blank (the back of a written leaf, or a page a person called "
        "blank, #5579); null when none"))
    recordings_left_out: Optional[int] = Field(default=None, description=(
        "recordings a stage that reads page images left out: a recording is not a page (2026-10-10); null when "
        "none"))
    kinds: Optional[dict[str, int]] = Field(default=None, description=(
        "a stage with a reader per kind: the pages it read, by kind (handwriting, print, typescript; 'unsorted' "
        "for a page with no image to sort, #5578)"))
    readers: Optional[list[StageReader]] = Field(default=None, description=(
        "a stage with a reader per kind: one workflow run per reader (#5578)"))
    entries: Optional[StageEntries] = Field(default=None, description=(
        "a stage that splits a diary or register into its dated entries: its pages and entries (#5581)"))
    prepared: Optional[StagePrepared] = Field(default=None, description=(
        "a stage that prepares faded pages before lines: how many it prepared and left alone (#5580)"))
    regions_found: Optional[StageRegions] = Field(default=None, description=(
        "a stage that finds regions with a YOLO layout model: its pages and regions (#5525)"))


class SkippedStep(BaseModel):
    step: str
    why: str
    fix: Optional[str] = Field(default=None, description=(
        "the button that fixes it, as a step problem's `fix` (choose-model, allow-cloud); null when nothing "
        "in setup fixes it"))


async def with_accounts(db: Any, status: dict[str, Any]) -> dict[str, Any]:
    """The run's status with each started workflow stage's account, and `waiting_for` and
    `estimate_seconds_left` for the run: what it waits for now, and the running stage's time left."""
    from fichero_server.workflows.run_account import run_account

    running = None
    for step in status["steps"]:
        step["account"] = None
        if step.get("card") == "workflow" and step.get("child_id"):
            step["account"] = await run_account(db, step["child_id"])
        if step["state"] == "running":
            running = step
    waiting = status["reason"] if status["state"] == "waiting" else None
    account = running.get("account") if running else None
    from fichero_server.execution.jobs import STOPPING

    # A run asked to stop says so, never what its running step's pages still wait for (#5609, #5654).
    if waiting is None and account is not None and status["state"] == "running" and status["reason"] != STOPPING:
        waiting = account.waiting_reason
    status["waiting_for"] = waiting
    status["estimate_seconds_left"] = account.estimate_seconds_left if account is not None else None
    return status


class NamesOfAKind(BaseModel):
    kind: str = Field(description="person, location, organization, event, concept, other (the KG's kinds)")
    label: str = Field(description="People, Places, …: the knowledge graph's own label")
    count: int


class StageFailures(BaseModel):
    """The pages one workflow stage could not do, and its offer to read them again."""

    steps: list[str]
    thread_id: str = Field(description="the stage's workflow run: POST /api/workflow-execution/threads/{thread_id}"
                           "/read-again reads its failed pages again")
    pages_failed: int
    failures: list[PageFailure]
    offer: Optional[str] = Field(default=None, description='"Read the 3 pages that failed"; null: nothing to offer')


class RecipeRunSummary(BaseModel):
    """What a recipe run made (`source.onboard.auto.results-summary`, #5577)."""

    job_id: str
    state: str
    finished: bool = Field(description="false while it runs: the figures are what is there so far")
    pages: int = Field(description="the pages the run ran over")
    pages_read: int = Field(description="of those, the pages that have a reading (lines read, or a page text)")
    names: list[NamesOfAKind] = Field(description="the names found on those pages, by kind, as the KG groups them")
    dates: int = Field(description="the dates named on those pages (the KG's Dates group)")
    pages_dated: int = Field(default=0, description=(
        "of those pages, the ones Work out dates gave a date (their date columns): the step's own output, which "
        "the KG's Dates group does not count"))
    statements: int = Field(description="the statements (claims) on those pages")
    documents_proposed: Optional[int] = Field(default=None, description=(
        "the documents Find the Documents proposed; null when it did not run in this run"))
    documents_accepted: Optional[int] = Field(default=None, description=(
        "of those, the ones accepted (by the run's own setting, or by a person since); null as above"))
    groups_proposed: Optional[int] = Field(default=None, description=(
        "the groups (a case, a correspondence) Find the Documents proposed; null as above"))
    entries: Optional[int] = Field(default=None, description=(
        "the dated entries the entries stage split the pages into (made, or found again); null when it did not "
        "run in this run"))
    pages_with_lines: Optional[int] = Field(default=None, description=(
        "of the run's pages, the ones with lines; null when the run had no Find Lines (#5668)"))
    pages_with_regions: Optional[int] = Field(default=None, description=(
        "of the run's pages, the ones with regions; null when the run had neither Find Regions nor Find Lines (whose "
        "segmenter finds regions too)"))
    lines: list[str] = Field(default_factory=list, description=(
        "the summary in the engine's words, one line per figure, shown as given"))
    failed: list[StageFailures] = Field(description="each stage's failed pages, with Read Again")
    pages_failed: int = Field(description="the failed pages over every stage")
    skipped: list[SkippedStep] = Field(description="the steps the plan skipped, each with why and its fix")
    not_run: list[RecipeRunStep] = Field(description="the stages that did not run, failed or were stopped, with why")


def _pages(db: Any, documents: Optional[list[str]], folder_id: Optional[str] = None) -> list[str]:
    """The pages the run ran over: an import's, a folder's (`source.recipe.folder-scoped-start`), or the project's."""
    from fichero_server.recipes.done import pages_for
    from fichero_server.recipes.runner import folder_scope

    pages = pages_for(db, {}, documents)
    if folder_id is None:
        return pages
    try:
        within = folder_scope(db, folder_id)
    except LookupError:  # the folder was deleted since: none of its pages are live
        return []
    return [p for p in pages if p in within]


def _has_reading(db: Any, doc_id: str) -> bool:
    from fichero_server.recipes.done import _has_line_readings, _has_page_reading

    return _has_page_reading(db, doc_id, None) or _has_line_readings(db, doc_id, None)


def _pages_dated(db: Any, pages: list[str]) -> int:
    """The pages Work out dates gave a date (`date_jdn` set), out of these."""
    from fichero_server.models import Document

    return sum(1 for p in pages if (d := db.get(Document, p)) is not None and d.date_jdn is not None)


def _knowledge(db: Any, pages: list[str]) -> tuple[list[NamesOfAKind], int, int]:
    """(names by kind, dates, statements) on these pages, by the document KG's own grouping."""
    from fichero_server.api.routes.document.inspector import _build_knowledge_graph
    from fichero_server.models.knowledge import KnowledgeClaim, KnowledgeEntity

    scope = set(pages)
    if not scope:
        return [], 0, 0
    claims = [c for c in db.query(KnowledgeClaim) if c.source_document_id in scope]
    linked = [e for e in db.query(KnowledgeEntity) if scope & set(e.source_document_ids or [])]
    graph = _build_knowledge_graph(db, "", claims, False, [], linked_entities=linked, scope_doc_ids=scope)
    names = [NamesOfAKind(kind=g.kind, label=g.label, count=len(g.items)) for g in graph.groups if g.kind != "date"]
    dates = sum(len(g.items) for g in graph.groups if g.kind == "date")
    return names, dates, graph.claim_count


def _found_documents(db: Any, steps: list[dict[str, Any]]) -> tuple[Optional[int], Optional[int], Optional[int]]:
    """(documents proposed, accepted, groups proposed) by the run's Find the Documents stages, as their proposals
    stand now; (None, None, None) when the run had no such stage that started."""
    import json

    from fichero_server.execution import jobs
    from fichero_server.finddocs import store

    children = [s["child_id"] for s in steps if s.get("card") == "find-documents" and s.get("child_id")]
    if not children:
        return None, None, None
    proposed = accepted = groups = 0
    for child in children:
        row = jobs.read_job(db, child)
        ids = (json.loads((row or {}).get("detail") or "{}").get("result") or {}).get("proposal_ids") or []
        for proposal_id in ids:
            try:
                proposal = store.read(db, proposal_id)
            except LookupError:  # the proposal was withdrawn since
                continue
            proposed += len(proposal.documents)
            accepted += sum(1 for d in proposal.documents if d.state == "accepted")
            groups += len(proposal.groups)
    return proposed, accepted, groups


def _entries(steps: list[dict[str, Any]]) -> tuple[Optional[int], int]:
    """(entries, pages split) by the run's entries stages; entries None when it had none that ran."""
    made = [s["entries"] for s in steps if s.get("entries")]
    if not made:
        return None, 0
    return (sum(e.get("created", 0) + e.get("unchanged", 0) + e.get("updated", 0) for e in made),
            sum(e.get("pages", 0) for e in made))


def _jobs_of_the_run(db: Any, steps: list[dict[str, Any]]) -> set[str]:
    """The jobs of the steps this run had, by the project's recipe (a step's id names it there)."""
    from pathlib import Path

    from fichero_server.recipes.project import read_project_setup

    try:
        recipe = read_project_setup(Path(db.path).parent)["recipe"] or {}
    except Exception:  # noqa: BLE001 -- no setup to read: the jobs the run's steps carry themselves
        recipe = {}
    job_of = {str(s.get("id")): str(s.get("job")) for s in recipe.get("steps") or []}
    ids = {sid for step in steps for sid in step.get("steps") or []}
    return {job_of.get(sid, sid) for sid in ids} | {str(step.get("job")) for step in steps if step.get("job")}


def _pages_with(db: Any, pages: list[str], kind: str) -> int:
    from fichero_server.models.segments import Segment

    return sum(1 for p in pages if any(seg.kind == kind for seg in db.query(Segment, document_id=p)))


def _plural(count: int, noun: str, nouns: str | None = None) -> str:
    return f"{count} {noun if count == 1 else (nouns or noun + 's')}"


def _lines(s: RecipeRunSummary, pages_split: int, ran: set[str] | None = None) -> list[str]:
    """The summary in words, one line per figure (#5577): the app shows them as given. `ran`: the run's jobs; a
    figure for a stage the run did not have has no line (#5668). None: every figure, as before."""
    lines = []
    shapes = []
    if s.pages_with_lines is not None:
        shapes.append(f"Lines on {s.pages_with_lines} of {_plural(s.pages, 'page')}")
    if s.pages_with_regions is not None:
        shapes.append(f"regions on {s.pages_with_regions} of {_plural(s.pages, 'page')}")
    if shapes:
        said = " · ".join(shapes)
        lines.append(said[0].upper() + said[1:])
    lines.append(f"Read {s.pages_read} of {_plural(s.pages, 'page')}")
    names = [n for n in s.names if n.count > 0]
    if ran is None or "find-names-tag-words" in ran or names:
        lines.append("Names: " + " · ".join(f"{n.count} {n.label}" for n in names) if names else "No names found")
    # Work out dates writes each page's own date, not a named date; a Spanish spaCy pipeline names no dates at
    # all, so "0 dates" read as a step that did nothing while 92 pages had their date (2026-10-11). A figure is
    # said when the run had its stage, or when it is not zero (#5668: "0 pages dated · 0 dates named · 0
    # statements" on a run with none of those stages).
    knowledge = [words for job, count, words in (
        ("work-out-dates", s.pages_dated, f"{_plural(s.pages_dated, 'page')} dated"),
        ("find-names-tag-words", s.dates, f"{_plural(s.dates, 'date')} named"),
        ("find-statements", s.statements, _plural(s.statements, "statement"))) if ran is None or job in ran or count]
    if knowledge:
        lines.append(" · ".join(knowledge))
    if s.documents_proposed is not None:
        lines.append(f"{_plural(s.documents_proposed, 'document')} proposed, {s.documents_accepted} accepted")
        lines.append(f"{_plural(s.groups_proposed or 0, 'group')} proposed")
    if s.entries is not None:
        lines.append(f"{_plural(s.entries, 'entry', 'entries')} from {_plural(pages_split, 'page')}")
    return lines


async def summary(db: Any, job_id: str) -> RecipeRunSummary:
    """The summary of one recipe run; LookupError when there is none."""
    from fichero_server.recipes import runner

    status = await with_accounts(db, runner.status(db, job_id))
    pages = _pages(db, status.get("documents"), status.get("folder_id"))
    names, dates, statements = _knowledge(db, pages)
    from fichero_server.workflows import run_account as accounts

    failed: list[StageFailures] = []
    for step in status["steps"]:
        # Each batch the stage failed pages of, its run carried past (#5540), then the stage's own run.
        children = [b["child_id"] for b in step.get("failed_batches") or [] if b.get("child_id")]
        if step.get("child_id") and step["child_id"] not in children:
            children.append(step["child_id"])
        for child in dict.fromkeys(children) if step.get("card") == "workflow" else ():
            account: Optional[RunAccount] = (step.get("account") if child == step.get("child_id")
                                             else await accounts.run_account(db, child))
            if account is None or not account.pages_failed:
                continue
            failed.append(StageFailures(steps=step["steps"], thread_id=child, pages_failed=account.pages_failed,
                                        failures=account.failures,
                                        offer=account.offer.label if account.offer else None))
    proposed, accepted, groups = _found_documents(db, status["steps"])
    entries, pages_split = _entries(status["steps"])
    made = RecipeRunSummary(
        job_id=job_id, state=status["state"], finished=status["state"] in ("done", "failed", "cancelled"),
        pages=len(pages), pages_read=sum(1 for p in pages if _has_reading(db, p)),
        names=names, dates=dates, statements=statements, pages_dated=_pages_dated(db, pages),
        documents_proposed=proposed, documents_accepted=accepted, groups_proposed=groups, entries=entries,
        failed=failed, pages_failed=sum(f.pages_failed for f in failed),
        skipped=[SkippedStep(**s) for s in status.get("skipped", [])],
        not_run=[RecipeRunStep(**s) for s in status["steps"] if s["state"] in ("failed", "not run", "cancelled")],
    )
    ran = _jobs_of_the_run(db, status["steps"])
    if "find-lines" in ran:
        made.pages_with_lines = _pages_with(db, pages, "line")
    if ran & {"find-lines", "find-regions"}:
        made.pages_with_regions = _pages_with(db, pages, "region")
    made.lines = _lines(made, pages_split, ran)
    return made

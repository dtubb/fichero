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


class LeftOutPage(BaseModel):
    """A page a stage left out, by name, with why (#5691)."""

    page_id: str
    page: str = Field(description="the page's name, as Items shows it")
    why: str = Field(description="why it was left out, in words: 'a blank page: its image holds almost no ink'")


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
        "pages a lining or reading stage left out as blank (its image holds almost no ink, or a person called it "
        "blank, #5579); null when none"))
    left_out: Optional[list[LeftOutPage]] = Field(default=None, description=(
        "the pages a lining or reading stage left out, each named with why (#5691); null when none"))
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


#: The verb a stage's offer says (#5706: "Read the 92 pages not done" on a names step).
_OFFER_VERBS = {"find-names-tag-words": "Find names on", "work-out-dates": "Work out dates on",
                "find-statements": "Find statements on", "correct": "Correct",
                "prepare-the-image": "Prepare", "split-into-entries": "Split into entries"}


def offer_words(job: str | None, label: str) -> str:
    """The account's offer ("Read the 3 pages that failed") in the stage's own verb."""
    verb = _OFFER_VERBS.get(job or "")
    return f"{verb} {label[len('Read '):]}" if verb and label.startswith("Read ") else label


async def with_accounts(db: Any, status: dict[str, Any]) -> dict[str, Any]:
    """The run's status with each started workflow stage's account, and `waiting_for` and
    `estimate_seconds_left` for the run: what it waits for now, and the running stage's time left."""
    from fichero_server.workflows.run_account import run_account

    running = None
    for step in status["steps"]:
        step["account"] = None
        if step.get("card") == "workflow" and step.get("child_id"):
            step["account"] = await run_account(db, step["child_id"])
            if step["account"] is not None and step["account"].offer is not None:
                offer = step["account"].offer.model_copy(
                    update={"label": offer_words(step.get("job"), step["account"].offer.label)})
                step["account"] = step["account"].model_copy(update={"offer": offer})
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
    if (status["state"] == "running" and running is not None and account is not None and account.pages_total
            and (status["reason"] or "").startswith("Running step")):
        # The step reading and its pages, never "0 of 1 folder" while its pages are read (#5685).
        from fichero_server.recipes.regions import progress_words

        pages = progress_words(account.pages_done, account.pages_total, seconds_left=account.estimate_seconds_left)
        if account.waiting_reason and status["waiting_for"]:
            # Held by the throttle: the row says it waits and why, with the pages it has (#5685).
            said = account.waiting_reason
            status["reason"] = f"{said if said.startswith('Waiting') else 'Waiting: ' + said} ({pages})"
        else:
            status["reason"] = f"{running.get('doing') or 'Running'}: {pages}"
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
    pages_read: int = Field(description="of those, the pages that have a reading (lines read, or a page text), "
                            "not counting a page the run left out as blank (#5705)")
    lines_unread: int = Field(default=0, description="the lines found on those pages that have no reading (#5758)")
    lines_seen_blank: int = Field(default=0, description="lines the reader looked at and found no writing on, on pages that also have text (#5758)")
    pages_read_nothing: int = Field(default=0, description="pages the reader returned nothing for, line by line: failed reads (#5758)")
    next_reader: Optional[dict[str, Any]] = Field(default=None, description="when the reader left a page empty or mostly blank: the next candidate of the step's chain, with needs_permission for a cloud one (#5758)")
    lines_unread_why: dict[str, int] = Field(default_factory=dict, description="why those lines have none: each reason with its count (#5758)")
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
    left_out: list[LeftOutPage] = Field(default_factory=list, description=(
        "the pages the run's stages left out, each named with why (#5691)"))
    pages_with_regions: Optional[int] = Field(default=None, description=(
        "of the run's pages, the ones with regions; null when the run had neither Find Regions nor Find Lines (whose "
        "segmenter finds regions too)"))
    pages_reviewed: Optional[int] = Field(default=None, description=(
        "of the run's pages, the ones the review step answered for; null when the run had no review step"))
    lines_reviewed: Optional[int] = Field(default=None, description=(
        "the lines the review answered, each by its id; null as above"))
    lines_corrected: Optional[int] = Field(default=None, description=(
        "of those, the lines the review gave a new reading; null as above"))
    lines_review_unreadable: Optional[int] = Field(default=None, description=(
        "of those, the lines the review could not read, left as they were read; null as above"))
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


def _fully_read(db: Any, doc_id: str) -> bool:
    from fichero_server.recipes.done import lines_state

    found, unread, _blank = lines_state(db, doc_id)
    return not unread and (found > 0 or _has_reading(db, doc_id))


def lines_unread(db: Any, pages: list[str]) -> int:
    from fichero_server.recipes.done import unread_on

    """The lines found on these pages that have no reading: a run that left 63 of 114 unread did not read them."""
    return sum(unread_on(db, p) for p in pages)


def lines_unread_why(db: Any, pages: list[str]) -> dict[str, int]:
    """Why the unread lines are unread, each reason with how many lines it covers."""
    from fichero_server.recipes.done import unread_reasons

    out: dict[str, int] = {}
    for p in pages:
        for why in unread_reasons(db, p).values():
            out[why] = out.get(why, 0) + 1
    return out


def lines_seen_blank(db: Any, pages: list[str]) -> int:
    """Lines a reader looked at and found no writing on, on pages that also have text: counted read, but shown, so
    a person can judge a reader that sees half a page as blank."""
    from fichero_server.recipes.done import lines_state

    return sum(lines_state(db, p)[2] for p in pages)


def next_reader(recipe: dict | None, *, lines_found: int, lines_blank: int, pages_read_nothing: int,
                cloud_allowed: bool) -> dict[str, Any] | None:
    """When the reader left a page empty or more than half the lines blank, the next candidate of the reading step's
    chain: the first local one (free), else the first cloud one, offered and needing permission until pages may
    leave this Mac. None when the read was good or the chain has nothing."""
    if not pages_read_nothing and not (lines_found and lines_blank * 2 > lines_found):
        return None
    step = next((s for s in (recipe or {}).get("steps") or [] if s.get("job") == "read-a-line"), None)
    chain = (step or {}).get("chain") or []
    nxt = next((c for c in chain if c.get("runs_on", "this-mac") == "this-mac"), None) or next(iter(chain), None)
    if nxt is None:
        return None
    cloud = nxt.get("runs_on", "this-mac") != "this-mac"
    return {"id": nxt["id"], "model": nxt.get("model"), "runs_on": nxt.get("runs_on", "this-mac"),
            "needs_permission": cloud and not cloud_allowed,
            "why": "the reader left the hand mostly blank; this is the next reader in the chain"}


def pages_read_nothing(db: Any, pages: list[str]) -> int:
    """The pages whose reader returned empty for every line: failed reads, read again by a second Start."""
    from fichero_server.recipes.done import NOTHING_FOR_PAGE, unread_reasons

    return sum(1 for p in pages if (r := set(unread_reasons(db, p).values())) and r == {NOTHING_FOR_PAGE})


def pages_fully_read(db: Any, pages: list[str]) -> list[str]:
    """The pages with a reading and none of their lines left without one."""
    return [p for p in pages if _fully_read(db, p)]


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


def reviewed(db: Any, pages: list[str]) -> dict[str, int]:
    """What the review step did on these pages (R3's run summary): each page's newest review, the lines it answered
    by id, those it gave a new reading, and those it could not read (`source.job.review-is-segment-native`). Three
    queries over all the pages, however many there are (review 153): the summary is read on every GET."""
    import json

    from fichero_server.llm.working_lines import answer_line

    counted = {"pages": 0, "lines": 0, "corrected": 0, "unreadable": 0}
    if not pages:
        return counted
    newest: dict[str, tuple[str, str | None, Any]] = {}
    # Oldest first, so the last a page sees is its newest; a review with no time counts as the oldest (review 156).
    for review_id, page, content, data in db.execute_fetchall(
            "SELECT id, document_id, content, data FROM artifacts WHERE artifact_type = 'transcription_review' "
            "AND document_id IN (SELECT unnest(?::VARCHAR[])) "
            "ORDER BY COALESCE(created_at, TIMESTAMP '1970-01-01'), id", [list(pages)]):
        newest[page] = (review_id, content, data)
    if not newest:
        return counted
    lines: dict[str, set[str]] = {}
    for segment_id, page in db.execute_fetchall(
            "SELECT id, document_id FROM segments WHERE kind = 'line' AND document_id IN "
            "(SELECT unnest(?::VARCHAR[]))", [list(newest)]):
        lines.setdefault(page, set()).add(segment_id)
    corrected = dict(db.execute_fetchall(
        "SELECT derived_from_artifact_id, count(DISTINCT segment_id) FROM contentrepresentations WHERE "
        "retracted_at IS NULL AND derived_from_artifact_id IN (SELECT unnest(?::VARCHAR[])) GROUP BY 1",
        [[review[0] for review in newest.values()]]))
    for page, (review_id, content, data) in newest.items():
        answered = {answer_line(text)[0] for text in (content or "").splitlines()} & lines.get(page, set())
        if not answered:  # not tied to the lines: the page's review, not a review of its lines
            continue
        data = json.loads(data) if isinstance(data, str) else (data or {})
        counted["pages"] += 1
        counted["lines"] += len(answered)
        counted["corrected"] += int(corrected.get(review_id, 0))
        counted["unreadable"] += len(set(data.get("unreadable_lines") or []) & answered)
    return counted


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
    if s.pages_with_lines is not None and s.pages_with_lines < s.pages:
        lines.append(f"No lines found on {_plural(s.pages - s.pages_with_lines, 'page')}")
    lines.append(f"Read {s.pages_read} of {_plural(s.pages, 'page')}")
    if s.lines_reviewed is not None:
        said = f"Reviewed {_plural(s.lines_reviewed, 'line')} on {_plural(s.pages_reviewed or 0, 'page')}"
        if s.lines_reviewed:
            said += f": {s.lines_corrected or 0} corrected"
            if s.lines_review_unreadable:
                said += f", {s.lines_review_unreadable} it could not read and left as read"
        lines.append(said)
    if s.pages_read_nothing:
        lines.append(f"{_plural(s.pages_read_nothing, 'page')} the reader returned nothing for")
    if s.lines_seen_blank:
        lines.append(f"{_plural(s.lines_seen_blank, 'line')} the reader found no writing on")
    if s.lines_unread:
        lines.append(f"{_plural(s.lines_unread, 'line')} {'has' if s.lines_unread == 1 else 'have'} no reading")
    if s.left_out:
        lines.append("Left out: " + "; ".join(f"{p.page}, {p.why}" for p in s.left_out))
        uncertain = sum(1 for p in s.left_out if "too uncertain to find names" in p.why)
        if uncertain:  # a warning of its own: names found on the rest are only as good as their reading (#5694)
            lines.append(f"Names not looked for on {_plural(uncertain, 'page')}: their reading is too uncertain")
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
    from fichero_server.recipes import runner, sorting

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
                                        offer=offer_words(step.get("job"), account.offer.label)
                                        if account.offer else None))
    proposed, accepted, groups = _found_documents(db, status["steps"])
    # The pages a stage left out as blank: not read by this run, whatever an earlier one gave them (#5705: "Read 92
    # of 92 pages" with 5 left out).
    blank = {e["page_id"] for step in status["steps"] for e in step.get("left_out") or []
             if e.get("why") in (sorting.BLANK_WHY, sorting.PERSON_BLANK_WHY)}
    entries, pages_split = _entries(status["steps"])
    made = RecipeRunSummary(
        job_id=job_id, state=status["state"], finished=status["state"] in ("done", "failed", "cancelled"),
        pages=len(pages), pages_read=len([p for p in pages_fully_read(db, pages) if p not in blank]),
        lines_unread=lines_unread(db, [p for p in pages if p not in blank]),
        lines_unread_why=lines_unread_why(db, [p for p in pages if p not in blank]),
        lines_seen_blank=lines_seen_blank(db, [p for p in pages if p not in blank]),
        pages_read_nothing=pages_read_nothing(db, [p for p in pages if p not in blank]),
        names=names, dates=dates, statements=statements, pages_dated=_pages_dated(db, pages),
        documents_proposed=proposed, documents_accepted=accepted, groups_proposed=groups, entries=entries,
        failed=failed, pages_failed=sum(f.pages_failed for f in failed),
        skipped=[SkippedStep(**s) for s in status.get("skipped", [])],
        not_run=[RecipeRunStep(**s) for s in status["steps"] if s["state"] in ("failed", "not run", "cancelled")],
    )
    seen: set[str] = set()
    for step in status["steps"]:  # each page once, though both a lining and a reading stage left it out
        for entry in step.get("left_out") or []:
            if entry["page_id"] not in seen:
                seen.add(entry["page_id"])
                made.left_out.append(LeftOutPage(**entry))
    ran = _jobs_of_the_run(db, status["steps"])
    if "find-lines" in ran:
        made.pages_with_lines = _pages_with(db, pages, "line")
    if ran & {"find-lines", "find-regions"}:
        made.pages_with_regions = _pages_with(db, pages, "region")
    if "correct" in ran:
        did = reviewed(db, pages)
        made.pages_reviewed, made.lines_reviewed = did["pages"], did["lines"]
        made.lines_corrected, made.lines_review_unreadable = did["corrected"], did["unreadable"]
    from fichero_server.recipes.done import lines_state
    from fichero_server.recipes.project import read_project_setup

    setup = read_project_setup(runner._library(db))
    states = [lines_state(db, p) for p in pages if p not in blank]
    made.next_reader = next_reader(setup["recipe"], lines_found=sum(s[0] for s in states),
                                   lines_blank=sum(s[2] for s in states), pages_read_nothing=made.pages_read_nothing,
                                   cloud_allowed=bool((setup["answers"] or {}).get("cloud_allowed")))
    made.lines = _lines(made, pages_split, ran)
    return made

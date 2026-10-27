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

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
import statistics
from typing import Any, Optional

from pydantic import BaseModel, Field, model_validator

from fichero_server.workflows.run_account import PageFailure, RunAccount

logger = logging.getLogger(__name__)


class StageReader(BaseModel):
    """One reader's workflow run in a stage with a reader per kind (#5578)."""

    material: Optional[str] = Field(default=None, description="the kind it read; null: the stage's own reader, for "
                                    "pages of a kind the recipe has no reader for")
    pages: int
    model: Optional[str] = None
    child_id: Optional[str] = None
    state: str
    why: Optional[str] = None
    card_id: Optional[str] = Field(default=None, description="its model card's id, when the plan knew a card")
    note: Optional[str] = Field(default=None, description="its model card's name for a person")
    runs_on: Optional[str] = Field(default=None, description="where it runs: this-mac or cloud:<provider>")
    sentence: Optional[str] = Field(default=None, description=(
        "who this reader is, as the plan said it: 'Also reads print pages with Apple Vision'; the same text as "
        "`RecipeStep.readers[].sentence`, shown as it stands (#6134); null for pages read by the stage's own reader"))


class StageEntries(BaseModel):
    """What a stage that splits a diary or register into its dated entries did (#5581)."""

    pages: int = Field(description="the pages it split: those that had text")
    without_text: int = Field(description="the pages it left alone because they had no text")
    created: int = Field(default=0, description="entries it made")
    unchanged: int = Field(default=0, description="entries a run before made, found again as they were")
    updated: int = Field(default=0, description="entries a run before made, found again changed")
    removed: int = Field(default=0, description="entries a run before made that it no longer finds (kept, hidden)")


class StageLeaveOut(BaseModel):
    """What the Leave Out stage did (`designer.clean.leaves-out-non-text`, #6070): lines marked left out, never deleted."""

    pages: int = Field(description="the pages whose lines it judged")
    left_out: int = Field(description="the lines it marked left out (specks, off the page, bleed-through)")
    why: dict[str, int] = Field(default_factory=dict, description="the lines left out, counted by reason")
    refused: int = Field(default=0, description="lines a concurrent edit kept from being marked")


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


class FailedPage(BaseModel):
    """A page a step lost, and why."""

    page: str = Field(description="The page's file name.")
    reason: str


class StepTiming(BaseModel):
    """A stage's time (`recipes-run.timing.per-step-recorded`, #6215): read from its job's row and its pages' own times
    as the run stored them, never kept in memory, so it is the same after a restart."""

    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    seconds: Optional[float] = Field(default=None, description="ended (or now, while it runs) less started")
    pages_done: int = Field(default=0, description="the pages with a time of their own")
    seconds_per_page: Optional[float] = Field(default=None, description=(
        "the median of its pages' own times (each from its slot to its end, every node of the page added)"))
    folder: Optional[str] = Field(default=None, description="a batch's folder; null on a step's own timing")
    job_id: Optional[str] = Field(default=None, description="a batch's job (its row in the Activity tree); null as above")
    batches: list["StepTiming"] = Field(default_factory=list, description=(
        "each batch the step ran on, in order, with its own figures; the step's span the first batch's start to the "
        "last's end, its pages' median over all of them"))


def page_seconds(progress_timeline: Optional[dict]) -> list[float]:
    """Each page's own time in a workflow run's stored timeline: its file entries that finished, by page, summed over the
    run's nodes. A file's time counts from its slot (`execution.runner.file_duration_ms`), never the fan-out's start."""
    by_page: dict[str, float] = {}
    for e in (progress_timeline or {}).get("steps") or []:
        if e.get("type") == "file" and e.get("status") == "success" and isinstance(e.get("duration_ms"), (int, float)):
            key = str(e.get("document_id") or e.get("page_id") or e.get("file_path"))
            by_page[key] = by_page.get(key, 0.0) + e["duration_ms"] / 1000
    return list(by_page.values())


def step_timing(started: Optional[datetime], ended: Optional[datetime], pages: list[float],
                now: datetime) -> StepTiming:
    from fichero_server.core.timeutil import ensure_utc

    seconds = None if started is None else round((ensure_utc(ended or now) - ensure_utc(started)).total_seconds(), 1)
    return StepTiming(started_at=started, ended_at=ended, seconds=seconds, pages_done=len(pages),
                      seconds_per_page=round(statistics.median(pages), 1) if pages else None)


def _timings(db: Any, status: dict[str, Any]) -> tuple[Optional[float], dict[str, StepTiming]]:
    """The run's seconds and each step's timing, by its job, from the rows: the jobs table and a workflow step's stored
    timeline (#6215). Bookkeeping: a library that cannot be read gives none, never a failed status."""
    import json

    from fichero_server.core.timeutil import utc_now
    from fichero_server.execution import jobs
    from fichero_server.db import activity_records as records

    try:
        jobs_of = {s["child_id"]: [b for b in s.get("batch_jobs") or [] if b.get("child_id")]
                   or [{"folder": None, "child_id": s["child_id"]}] for s in status["steps"] if s.get("child_id")}
        cards = {s["child_id"]: s.get("card") for s in status["steps"] if s.get("child_id")}
        batch_ids = [b["child_id"] for bs in jobs_of.values() for b in bs]
        times = jobs.times(db, [status["job_id"], *batch_ids])
        now = utc_now()

        wf = list(dict.fromkeys(b["child_id"] for c, bs in jobs_of.items() if cards[c] == "workflow" for b in bs))
        rows = (db.execute_fetchall(f"SELECT id, progress_timeline FROM {records.RUNS} "  # the timeline only, never the log
                                    f"WHERE id IN ({', '.join('?' * len(wf))})", wf) if wf else [])
        timelines = {r[0]: r[1] for r in rows}  # one read for every batch of every step

        def pages_of(child: str, card: Any) -> list[float]:
            timeline = timelines.get(child) if card == "workflow" else None
            timeline = json.loads(timeline) if isinstance(timeline, str) and timeline else timeline
            return page_seconds(timeline if isinstance(timeline, dict) else None)

        out = {}
        for child, batches in jobs_of.items():
            timed = [(b, times[b["child_id"]], pages_of(b["child_id"], cards[child]))
                     for b in batches if b["child_id"] in times]
            if not timed:
                continue
            starts = [t[0] for _b, t, _p in timed if t[0] is not None]
            ends = [t[1] for _b, t, _p in timed]
            step = step_timing(min(starts) if starts else None, None if None in ends else max(ends),
                               [x for _b, _t, p in timed for x in p], now)
            if len(timed) > 1:  # one batch is the step itself
                step.batches = [step_timing(*t, p, now).model_copy(update={"folder": b.get("folder"), "job_id": b["child_id"]})
                                for b, t, p in timed]
            out[child] = step
        run = times.get(status["job_id"])
        return (step_timing(*run, [], now).seconds if run else None), out
    except Exception as exc:  # noqa: BLE001
        logger.debug("no timings for run %s: %s", status.get("job_id"), exc)
        return None, {}


def slowest_words(steps: list["RecipeRunStep"]) -> Optional[str]:
    """'Slowest step: Read each line: 48 s a page on 20 pages' (or its whole time, for a stage with no pages of its own)."""
    timed = [s for s in steps if s.timing is not None and s.timing.seconds is not None]
    if not timed:
        return None
    per_page = [s for s in timed if s.timing.seconds_per_page is not None]
    if per_page:
        s = max(per_page, key=lambda s: s.timing.seconds_per_page)
        return (f"Slowest step: {s.title}: {s.timing.seconds_per_page:g} s a page on "
                f"{_plural(s.timing.pages_done, 'page')}")
    s = max(timed, key=lambda s: s.timing.seconds)
    return f"Slowest step: {s.title}: {s.timing.seconds:g} s"


class RecipeRunStep(BaseModel):
    """One stage of a recipe run: the card that carries one or more recipe steps."""

    steps: list[str]
    #: The stage in words, from the job registry's names ("Find lines and Read each line"), never its job ids
    #: (`source.activity.run.stage-named-in-words`). Filled from `steps` when the status does not carry it.
    title: Optional[str] = None
    card: str
    job: Optional[str] = Field(default=None, description="the stage's last job (read-a-line, find-names-tag-words)")
    state: str = Field(description="waiting, running, done, partial (some pages lost; `why` and `failed_pages` say which), failed or not run")
    child_id: Optional[str] = Field(default=None, description="the step's own job: a workflow run or a check run")
    why: Optional[str] = None
    failed_pages: Optional[list[FailedPage]] = Field(default=None, description=(
        "a partial step: the pages it lost, each with why (`activity.run.step-honest-about-lost-pages`); null otherwise"))
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
    leave_out: Optional[StageLeaveOut] = Field(default=None, description=(
        "the Leave Out stage: the pages it judged and the lines it left out, by reason (#6070); a field of its own, not "
        "`left_out`, which lists the pages a lining or reading stage left out (#5691)"))
    prepared: Optional[StagePrepared] = Field(default=None, description=(
        "a stage that prepares faded pages before lines: how many it prepared and left alone (#5580)"))
    regions_found: Optional[StageRegions] = Field(default=None, description=(
        "a stage that finds regions with a YOLO layout model: its pages and regions (#5525)"))
    timing: Optional[StepTiming] = Field(default=None, description=(
        "when the stage started and ended, its seconds, pages and seconds a page; null before it has a job (#6215)"))
    batch_jobs: list[dict[str, Optional[str]]] = Field(default_factory=list, description=(
        "each batch's job of the stage, in order: {folder, child_id} (#6215)"))

    @model_validator(mode="after")
    def _name_the_stage(self) -> "RecipeRunStep":
        if self.title is None:
            from fichero_server.execution.jobs import kind_name

            self.title = " and ".join(kind_name(step) for step in self.steps) or None
        return self


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

    status["seconds"], timings = await asyncio.to_thread(_timings, db, status)  # the rows: off the loop (#6178)
    running = None
    for step in status["steps"]:
        step["account"] = None
        if step.get("child_id") in timings:
            step["timing"] = timings[step["child_id"]]
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
    if status["state"] == "running":  # the gate's number and its hold, as fields (#6217)
        from fichero_server.execution.jobs import BACKGROUND_STARTERS
        from fichero_server.llm import kraken_runtime

        status["pages_at_once"], status["pages_at_once_reason"] = await asyncio.to_thread(  # memory probes: off the loop (#6178)
            kraken_runtime.pages_at_once_and_why, (status.get("started_by") or "automatic") not in BACKGROUND_STARTERS)
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


class NextCandidate(BaseModel):
    """The next entry of a step's chain, offered in place of a model that could not be had (#5352, #5758)."""

    id: str = Field(description="the candidate's card id, as POST /api/recipes/project/steps/use-candidate takes it")
    name: str = Field(description="what to call it on screen: the catalogue's name for it, else its model's name, else its id")
    model: Optional[dict[str, Any]] = Field(default=None, description="its pin")
    runs_on: str = Field(description="this-mac, or cloud:<provider>")
    needs_permission: bool = Field(description="a cloud candidate while pages may not leave this Mac")


class DownloadFailed(BaseModel):
    """A step waiting on a model download that failed or was cancelled (`source.recipe.download-failure-waits`)."""

    steps: list[str]
    model: str = Field(description="the model that did not download")
    reason: str
    retry_job_id: str = Field(description="the download's job: POST /api/activity/jobs/{id}/retry")
    next_candidate: Optional[NextCandidate] = Field(default=None, description="null: the chain has nothing else")


class Missed(BaseModel):
    """What a finished run did not finish, and the one action that runs it (`source.recipe.run-again-on-what-was-missed`,
    #6170): plain Start on `folder_id`, which runs only what is not done (`source.recipe.done-is-not-redone`)."""

    words: str = Field(description="what was not finished, in words, shown as given")
    offer: str = Field(default="Run again on what was missed", description="the action's label")
    folder_id: Optional[str] = Field(description="the run's scope, as POST /api/recipes/project/start takes it; null: the project")


_UNFINISHED = ("failed", "not run", "cancelled", "partial")


def missed(steps: list[RecipeRunStep], pages: int, folder_id: Optional[str]) -> Optional[Missed]:
    """Each stage that left pages not done (its account's pages not done, a failed page included, as a stage "done" with
    failures has; all the run's pages when a stage that did not finish has no account); None when none did."""
    said = []
    for s in steps:
        if s.account and s.account.pages_total:
            left = s.account.pages_total - s.account.pages_done
        else:
            left = pages if s.state in _UNFINISHED else 0
        if left:
            said.append(f"{_plural(left, 'page')} not done by {s.title or ', '.join(s.steps)}")
    return Missed(words="; ".join(said), folder_id=folder_id) if said else None


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
    lines_vision_could_not_read: int = Field(default=0, description="lines Apple Vision returned nothing for twice in one run: final, with a reason, not counted as lines the reader found no writing on (#5901)")
    pages_read_nothing: int = Field(default=0, description="pages the reader returned nothing for, line by line: failed reads (#5758)")
    next_reader: Optional[dict[str, Any]] = Field(default=None, description="when the reader left a page empty or mostly blank: the next candidate of the step's chain, with needs_permission for a cloud one (#5758)")
    download_failed: list[DownloadFailed] = Field(default_factory=list, description="steps waiting on a model download that failed, each with Retry (the download's job) and the next candidate of the step's chain (#5352)")
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
    missed: Optional[Missed] = Field(default=None, description=(
        "a finished run's stages left unfinished, with Run again on what was missed; null while it runs or when it "
        "finished everything (#6170)"))


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
    from fichero_server.recipes.done import lines_state, vision_gave_up

    return sum(lines_state(db, p)[2] - vision_gave_up(db, p) for p in pages)


def lines_vision_could_not_read(db: Any, pages: list[str]) -> int:
    """Lines Apple Vision returned nothing for twice (#5901), on pages that are otherwise read."""
    from fichero_server.recipes.done import vision_gave_up

    return sum(vision_gave_up(db, p) for p in pages)


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


def candidate_name(entry: dict[str, Any]) -> str:
    """A chain entry's name on screen: the catalogue's name for its MLX model, else the pin's own name, else its id."""
    from fichero_server.llm.mlx_model_store import MANAGED_MLX_MODELS
    from fichero_server.recipes.cards import mlx_model_for

    pin = entry.get("model") or {}
    repo = mlx_model_for(pin) if pin else None
    named = next((m.display_name for i, m in MANAGED_MLX_MODELS.items() if repo and repo in (i, m.repo_id)), None)
    return named or pin.get("name") or entry["id"]


def download_failures(awaited: list[dict[str, Any]], states: dict[str, dict[str, Any] | None],
                      recipe: dict | None, *, cloud_allowed: bool) -> list[dict[str, Any]]:
    """The downloads a run's steps wait on that failed or were cancelled (`states`: download job id -> its row), each
    with Retry (that job) and the next candidate of the step's chain: the first local one other than the failed
    model, else the first cloud one, needing permission until pages may leave (#5352)."""
    out: list[dict[str, Any]] = []
    for entry in awaited:
        row = states.get(entry["job_id"])
        if not row or row["state"] not in ("failed", "cancelled"):
            continue
        step = next((s for s in (recipe or {}).get("steps") or [] if s.get("id") in entry["steps"]), None)
        chain = [c for c in (step or {}).get("chain") or []
                 if entry["name"] not in (c.get("id"), (c.get("model") or {}).get("name"))]
        nxt = next((c for c in chain if c.get("runs_on", "this-mac") == "this-mac"), None) or next(iter(chain), None)
        cloud = nxt is not None and nxt.get("runs_on", "this-mac") != "this-mac"
        out.append({"steps": entry["steps"], "model": entry["name"], "reason": row["reason"] or row["state"],
                    "retry_job_id": entry["job_id"],
                    "next_candidate": None if nxt is None else {
                        "id": nxt["id"], "name": candidate_name(nxt), "model": nxt.get("model"),
                        "runs_on": nxt.get("runs_on", "this-mac"), "needs_permission": cloud and not cloud_allowed}})
    return out


def pages_read_nothing(db: Any, pages: list[str]) -> int:
    """The pages whose reader returned empty for every line, or most (the rate rule): failed reads, read again by a second Start."""
    from fichero_server.recipes.done import failed_reads

    return len(failed_reads(db, pages))


def pages_fully_read(db: Any, pages: list[str]) -> list[str]:
    """The pages with a reading and none of their lines left without one."""
    return [p for p in pages if _fully_read(db, p)]


@dataclass
class ReadingCounts:
    pages_fully_read: list[str]
    lines_unread: int
    lines_unread_why: dict[str, int]
    lines_seen_blank: int
    lines_vision_could_not_read: int
    lines_found: int
    pages_read_nothing: int
    pages_dated: int


def reading_counts(db: Any, pages: list[str], blank: set[str]) -> ReadingCounts:
    """The summary's counts over `pages` (`blank`: pages the run left out, which no count includes, except the dates), from two
    set-based reads of the pages' lines and readings (`done.lines_by_page`) and one of their dates, instead of ten calls a page
    (`activity.summary.counts-in-two-queries`, #6001). Only a page with no lines keeps its own check, for a page-level reading."""
    from fichero_server.models import Document
    from fichero_server.recipes.done import FAILED_READ_REASONS, lines_by_page, pages_with_readings

    kept = [p for p in pages if p not in blank]
    by_page = lines_by_page(db, kept)
    why: dict[str, int] = {}
    for info in by_page.values():
        for reason, n in info.why.items():
            why[reason] = why.get(reason, 0) + n
    # A page with no lines is read when it has a page-level reading, found with the other such pages in two reads.
    lineless = [p for p in kept if not by_page[p].found and not by_page[p].unread]
    have = pages_with_readings(db, lineless) if lineless else set()
    fully = [p for p in kept if not by_page[p].unread and (by_page[p].found > 0 or p in have)]
    failed = sum(1 for info in by_page.values() if info.why and set(info.why) <= FAILED_READ_REASONS)
    dated = sum(1 for d in db.query_in(Document, "id", pages) if d.date_jdn is not None)
    return ReadingCounts(
        pages_fully_read=fully, lines_unread=sum(i.unread for i in by_page.values()), lines_unread_why=why,
        lines_seen_blank=sum(i.blank for i in by_page.values()),
        lines_vision_could_not_read=sum(i.vision for i in by_page.values()), lines_found=sum(i.found for i in by_page.values()),
        pages_read_nothing=failed, pages_dated=dated)


async def counts_off_the_loop(db: Any, pages: list[str], blank: set[str]) -> ReadingCounts:
    """`reading_counts` on a worker thread: it waits for the database's transaction gate behind the writers (Kraken saves, a
    kept-text export, an import), and the event loop must not (`activity.summary.off-the-loop`, #6001)."""
    return await asyncio.to_thread(reading_counts, db, pages, blank)


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

    return len({seg.document_id for seg in db.query_in(Segment, "document_id", pages) if seg.kind == kind})


def reviewed(db: Any, pages: list[str]) -> dict[str, int]:
    """What the review step did on these pages (R3's run summary): each page's newest review, the lines it answered
    by id, those it gave a new reading, and those it could not read (`source.job.review-is-segment-native`). Three
    queries over all the pages, however many there are (review 153): the summary is read on every GET."""
    import json

    from fichero_server.db.run_reviews import line_ids_by_page, lines_corrected_by, reviews_oldest_first
    from fichero_server.llm.working_lines import answer_line

    counted = {"pages": 0, "lines": 0, "corrected": 0, "unreadable": 0}
    if not pages:
        return counted
    newest: dict[str, tuple[str, str | None, Any]] = {}
    for review_id, page, content, data in reviews_oldest_first(db, pages):
        newest[page] = (review_id, content, data)
    if not newest:
        return counted
    lines = line_ids_by_page(db, list(newest))
    corrected = lines_corrected_by(db, [review[0] for review in newest.values()])
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
        from fichero_server.recipes.done import MOSTLY_NOTHING_FOR_PAGE, NOTHING_FOR_PAGE

        # Most lines empty (the rate rule) is not "nothing": say which it was.
        mostly = MOSTLY_NOTHING_FOR_PAGE in s.lines_unread_why and NOTHING_FOR_PAGE not in s.lines_unread_why
        lines.append(f"{_plural(s.pages_read_nothing, 'page')} the reader "
                     f"{'came back empty on most lines for' if mostly else 'returned nothing for'}")
    if s.lines_seen_blank:
        lines.append(f"{_plural(s.lines_seen_blank, 'line')} the reader found no writing on")
    if s.lines_vision_could_not_read:
        lines.append(f"{_plural(s.lines_vision_could_not_read, 'line')} Vision could not read")
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


def _head(db: Any, status: dict[str, Any]) -> tuple[list[str], tuple, tuple]:
    """The summary's first database reads (the run's pages, their names, dates and statements, the documents found), for one
    worker thread: the event loop never waits on the connection's transaction gate (`activity.summary.off-the-loop`, #6001)."""
    pages = _pages(db, status.get("documents"), status.get("folder_id"))
    return pages, _knowledge(db, pages), _found_documents(db, status["steps"])


def _tail(db: Any, made: RecipeRunSummary, status: dict[str, Any], pages: list[str], counts: "ReadingCounts") -> set[str]:
    """The summary's last database reads (pages with lines or regions, the review, the project's setup, the downloads), filled
    into `made` on one worker thread; returns the jobs the run ran."""
    from fichero_server.recipes import places, runner
    from fichero_server.recipes.project import read_project_setup

    ran = _jobs_of_the_run(db, status["steps"])
    if "find-lines" in ran:
        made.pages_with_lines = _pages_with(db, pages, "line")
    if ran & {"find-lines", "find-regions"}:
        made.pages_with_regions = _pages_with(db, pages, "region")
    if "correct" in ran:
        did = reviewed(db, pages)
        made.pages_reviewed, made.lines_reviewed = did["pages"], did["lines"]
        made.lines_corrected, made.lines_review_unreadable = did["corrected"], did["unreadable"]
    setup = read_project_setup(runner._library(db))
    made.next_reader = next_reader(setup["recipe"], lines_found=counts.lines_found,
                                   lines_blank=counts.lines_seen_blank + counts.lines_vision_could_not_read, pages_read_nothing=made.pages_read_nothing,
                                   cloud_allowed=places.may_leave_to(setup["answers"], "cloud"))
    from fichero_server.execution import jobs

    awaited = status.get("awaited") or []
    made.download_failed = download_failures(awaited, {e["job_id"]: jobs.read_job(db, e["job_id"]) for e in awaited},
                                             setup["recipe"], cloud_allowed=places.may_leave_to(setup["answers"], "cloud"))
    return ran


async def summary(db: Any, job_id: str) -> RecipeRunSummary:
    """The summary of one recipe run; LookupError when there is none."""
    from fichero_server.recipes import runner, sorting

    status = await with_accounts(db, await asyncio.to_thread(runner.status, db, job_id))  # reads the library's rows
    pages, (names, dates, statements), (proposed, accepted, groups) = await asyncio.to_thread(_head, db, status)
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
    # The pages a stage left out as blank: not read by this run, whatever an earlier one gave them (#5705: "Read 92
    # of 92 pages" with 5 left out).
    blank = {e["page_id"] for step in status["steps"] for e in step.get("left_out") or []
             if e.get("why") in (sorting.BLANK_WHY, sorting.PERSON_BLANK_WHY)}
    entries, pages_split = _entries(status["steps"])
    counts = await counts_off_the_loop(db, pages, blank)
    made = RecipeRunSummary(
        job_id=job_id, state=status["state"], finished=status["state"] in ("done", "failed", "cancelled"),
        pages=len(pages), pages_read=len(counts.pages_fully_read),
        lines_unread=counts.lines_unread, lines_unread_why=counts.lines_unread_why,
        lines_seen_blank=counts.lines_seen_blank, lines_vision_could_not_read=counts.lines_vision_could_not_read, pages_read_nothing=counts.pages_read_nothing,
        names=names, dates=dates, statements=statements, pages_dated=counts.pages_dated,
        documents_proposed=proposed, documents_accepted=accepted, groups_proposed=groups, entries=entries,
        failed=failed, pages_failed=sum(f.pages_failed for f in failed),
        skipped=[SkippedStep(**s) for s in status.get("skipped", [])],
        not_run=[RecipeRunStep(**s) for s in status["steps"] if s["state"] in _UNFINISHED],
    )
    seen: set[str] = set()
    for step in status["steps"]:  # each page once, though both a lining and a reading stage left it out
        for entry in step.get("left_out") or []:
            if entry["page_id"] not in seen:
                seen.add(entry["page_id"])
                made.left_out.append(LeftOutPage(**entry))
    ran = await asyncio.to_thread(_tail, db, made, status, pages, counts)
    made.lines = _lines(made, pages_split, ran)
    if made.finished:
        made.missed = missed([RecipeRunStep(**s) for s in status["steps"]], len(pages), status.get("folder_id"))
    slowest = slowest_words([RecipeRunStep(**s) for s in status["steps"]])
    if slowest:
        made.lines.append(slowest)
    return made

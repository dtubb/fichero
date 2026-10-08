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
    kinds: Optional[dict[str, int]] = Field(default=None, description=(
        "a stage with a reader per kind: the pages it read, by kind (handwriting, print, typescript; 'unsorted' "
        "for a page with no image to sort, #5578)"))
    readers: Optional[list[StageReader]] = Field(default=None, description=(
        "a stage with a reader per kind: one workflow run per reader (#5578)"))
    entries: Optional[StageEntries] = Field(default=None, description=(
        "a stage that splits a diary or register into its dated entries: its pages and entries (#5581)"))
    prepared: Optional[StagePrepared] = Field(default=None, description=(
        "a stage that prepares faded pages before lines: how many it prepared and left alone (#5580)"))


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
    if waiting is None and account is not None and status["state"] == "running":
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
    dates: int = Field(description="the dates on those pages (the KG's Dates group)")
    statements: int = Field(description="the statements (claims) on those pages")
    documents_proposed: Optional[int] = Field(default=None, description=(
        "the documents Find the Documents proposed; null when it did not run in this run"))
    failed: list[StageFailures] = Field(description="each stage's failed pages, with Read Again")
    pages_failed: int = Field(description="the failed pages over every stage")
    skipped: list[SkippedStep] = Field(description="the steps the plan skipped, each with why and its fix")
    not_run: list[RecipeRunStep] = Field(description="the stages that did not run, failed or were stopped, with why")


def _pages(db: Any, documents: Optional[list[str]]) -> list[str]:
    from fichero_server.recipes.done import pages_for

    return pages_for(db, {}, documents)


def _has_reading(db: Any, doc_id: str) -> bool:
    from fichero_server.recipes.done import _has_line_readings, _has_page_reading

    return _has_page_reading(db, doc_id, None) or _has_line_readings(db, doc_id, None)


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


async def summary(db: Any, job_id: str) -> RecipeRunSummary:
    """The summary of one recipe run; LookupError when there is none."""
    from fichero_server.recipes import runner

    status = await with_accounts(db, runner.status(db, job_id))
    pages = _pages(db, status.get("documents"))
    names, dates, statements = _knowledge(db, pages)
    failed: list[StageFailures] = []
    for step in status["steps"]:
        account: Optional[RunAccount] = step.get("account")
        if account is None or not account.pages_failed:
            continue
        failed.append(StageFailures(steps=step["steps"], thread_id=step["child_id"], pages_failed=account.pages_failed,
                                    failures=account.failures, offer=account.offer.label if account.offer else None))
    return RecipeRunSummary(
        job_id=job_id, state=status["state"], finished=status["state"] in ("done", "failed", "cancelled"),
        pages=len(pages), pages_read=sum(1 for p in pages if _has_reading(db, p)),
        names=names, dates=dates, statements=statements,
        documents_proposed=None,  # Find the Documents has no card yet (#5574); its stage fills this in
        failed=failed, pages_failed=sum(f.pages_failed for f in failed),
        skipped=[SkippedStep(**s) for s in status.get("skipped", [])],
        not_run=[RecipeRunStep(**s) for s in status["steps"] if s["state"] in ("failed", "not run", "cancelled")],
    )

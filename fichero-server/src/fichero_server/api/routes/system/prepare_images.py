"""Prepare Images' read routes: the card's facts and the Pages to check worklist (`prep.setup.*`,
`prep.check.worklist-of-proposals-and-a-sample`). Moved out of `recipes.py`, which is over a thousand lines; the paths,
tag and operation ids are the same (`/api/recipes/prepare-images/...`, tag `recipes`). Read-only.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from fichero_server.api.main import get_library_database
from fichero_server.db import Database

router = APIRouter(prefix="/recipes")


class PrepareSuggestion(BaseModel):
    value: Any = Field(description="the suggested answer")
    agree: str = Field(description='how many of the sample pages agree, e.g. "3 of 5"')
    why: str


class PrepareImagesFacts(BaseModel):
    suggestions: dict[str, PrepareSuggestion] = Field(
        default_factory=dict, description="by question key: the answers five sample pages suggest (three of five agree)")
    estimate: str = Field(description="the time line under the questions: the seed figure, marked as an estimate")
    how_it_works: str = Field(description="the engine's sentence naming the operations")
    to_check: int = Field(default=0, description="Pages to check: pages with a proposal plus the sample (`/prepare-images/check`)")


class PrepareCheckItem(BaseModel):
    id: str
    name: str
    kinds: list[str] = Field(description="the proposals open on the page: page_box, turn, blank; none for a sample page")
    words: list[str] = Field(description="what is unsure, in words")
    sample: bool = Field(description="a confident page checked as a sample")


class PrepareCheckList(BaseModel):
    items: list[PrepareCheckItem]
    count: int
    proposed: int = Field(description="how many items are proposals (they come first); the rest are the sample")


@router.get("/prepare-images/check", response_model=PrepareCheckList)
async def prepare_images_check(db: Database = Depends(get_library_database)) -> PrepareCheckList:
    """Pages to check (`prep.check.worklist-of-proposals-and-a-sample`): every page with an open proposal, then one
    confident page in twenty."""
    from fichero_server.recipes.prepare_check import worklist

    items = worklist(db)
    return PrepareCheckList(items=[PrepareCheckItem(**i) for i in items], count=len(items),
                            proposed=sum(1 for i in items if not i["sample"]))


@router.get("/prepare-images/facts", response_model=PrepareImagesFacts)
async def prepare_images_facts(db: Database = Depends(get_library_database)) -> PrepareImagesFacts:
    """What the Prepare Images card shows besides its questions (`prep.setup.three-questions-suggested-from-a-sample`,
    `prep.estimate.time-on-this-mac-before-start`): answers suggested from five sample pages, and the time line."""
    import asyncio

    from fichero_server.recipes import topics
    from fichero_server.recipes.prepare_check import to_check
    from fichero_server.recipes.prepare_suggest import estimate, suggest

    suggestions = await asyncio.to_thread(suggest, db)
    return PrepareImagesFacts(suggestions={k: PrepareSuggestion(**v) for k, v in suggestions.items()},
                              estimate=estimate(len(db.unit_of_work_ids())),
                              how_it_works=topics.how_it_works("prepare-the-image"),
                              to_check=to_check(db))

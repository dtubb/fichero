"""Topics: each topic's and each recipe job's explanation, written once and read by every surface.

Spec: `source/models-chains-and-projects.md` (`source.onboard.topics-written-once`,
`source.onboard.teaches-the-method`, #5471). Setup, the Inspector and Activity read the same text
from here through the generated client; the text lives only in `recipes/seed/topics.yaml`.
Read-only.
"""
from __future__ import annotations

from typing import Any, Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/topics")


def _all_topics() -> Any:
    # Loaded on first use, not at app start (#3950).
    from fichero_server.recipes.topics import all_topics

    return all_topics()


class TopicInfo(BaseModel):
    """One explanation, as setup, the Inspector and Activity show it."""

    id: str = Field(description="the topic's id; for a recipe job, the job's id")
    kind: Literal["job", "topic"] = Field(description="a recipe job, or a topic setup teaches")
    title: str
    short: str = Field(description="one sentence")
    long: str = Field(description="a paragraph that follows the short sentence, never repeating it")
    example: Optional[str] = Field(default=None, description="what to show from the person's own pages")
    manual: Optional[str] = Field(default=None, description="the user manual page, when one exists")


class TopicListResponse(BaseModel):
    items: list[TopicInfo]
    count: int


def _info(topic: Any) -> TopicInfo:
    return TopicInfo(id=topic.id, kind=topic.kind, title=topic.title, short=topic.short,
                     long=topic.long, example=topic.example, manual=topic.manual)


@router.get("", response_model=TopicListResponse)
async def list_topics() -> TopicListResponse:
    """Every topic and every recipe job, each explained once."""
    items = [_info(t) for t in _all_topics()]
    return TopicListResponse(items=items, count=len(items))


@router.get("/{topic_id}", response_model=TopicInfo)
async def get_topic(topic_id: str) -> TopicInfo:
    """One topic or recipe job's explanation."""
    from fichero_server.recipes.topics import get_topic as lookup

    topic = lookup(topic_id)
    if topic is None:
        raise HTTPException(status_code=404, detail=f"no topic {topic_id!r}")
    return _info(topic)

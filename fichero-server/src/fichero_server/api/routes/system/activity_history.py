"""`GET /api/activity/history`: the Activity Monitor's graphs (#6588, `activity.window.bottom-panel`, decisions 22-25).

One typed answer, derived from what the engine already keeps: the page jobs' `finished_at` and `state` in the jobs table, and
each job's calls (`detail["usage"]`, priced by `llm.usage.price_call` as `_job_cost` does). Nothing is recorded for it.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta
from enum import Enum

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from fichero_server.api.main import get_library_database
from fichero_server.core.timeutil import ensure_utc, utc_now
from fichero_server.db import Database, committed

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/activity", tags=["activity"])


class Runtime(str, Enum):
    """Where a page was read: the closed set the graph keys its series by."""

    this_mac = "this-mac"
    other_mac = "other-mac"
    cloud = "cloud"
    cluster = "cluster"


#: A call's recorded place (`llm/places.py`) -> its runtime.
_PLACES = {"this_mac": Runtime.this_mac, "own_machine": Runtime.other_mac, "provider": Runtime.cloud}


class HistoryBucket(BaseModel):
    start: datetime = Field(description="the minute's start, aware UTC")
    pages_done: int = 0
    pages_failed: int = 0
    spend_usd: float = Field(0.0, description="dollars of the priced cloud calls of pages finished in this minute; 0.0 when none")
    tokens: int = Field(0, description="tokens of those pages' calls")


class ActivityHistory(BaseModel):
    buckets: list[HistoryBucket] = Field(description="one per minute, oldest first, the last the current minute")
    by_runtime: dict[Runtime, int] = Field(default_factory=dict, description="pages done in the window by where they ran; a runtime with none is absent")
    today_spend_usd: float = Field(0.0, description="dollars of priced cloud calls of pages finished today (UTC)")
    today_spend_by_provider: dict[str, float] = Field(default_factory=dict, description="provider name -> today's dollars")


def _runtime(call_places: list[str], target: str | None) -> Runtime:
    for place in call_places:
        if place in _PLACES:
            return _PLACES[place]
    return Runtime.cluster if target else Runtime.this_mac


def history(db: Database, minutes: int, now: datetime | None = None) -> ActivityHistory:
    """The window's buckets, runtimes and today's spend, read from the page jobs finished since the older of the two starts."""
    from fichero_server.execution.jobs import RUN_KINDS, _ensure
    from fichero_server.llm.usage import price_call

    now = now or utc_now()
    this_minute = now.replace(second=0, microsecond=0)
    first = this_minute - timedelta(minutes=minutes - 1)
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    buckets = [HistoryBucket(start=first + timedelta(minutes=i)) for i in range(minutes)]
    result = ActivityHistory(buckets=buckets)
    _ensure(db)
    # A page job: a job of a page kind under a run's step; the run and step rows themselves are not pages.
    rows = db.execute_fetchall(
        "SELECT finished_at, state, detail, target FROM jobs WHERE parent_id IS NOT NULL "
        f"AND kind NOT IN ({', '.join('?' * len(RUN_KINDS))}) AND state IN ('done', 'failed') AND finished_at >= ?",
        [*RUN_KINDS, min(first, midnight).replace(tzinfo=None)], committed=True)
    today: dict[str, float] = {}
    runtimes: dict[Runtime, int] = {}
    for finished, state, detail, target in rows:
        at = ensure_utc(finished)
        try:
            usage = [price_call(u) for u in (json.loads(detail) if detail else {}).get("usage", [])]
        except Exception as exc:  # noqa: BLE001 -- a page with unreadable calls still counts, without them
            logger.warning("activity history: unreadable calls of a page job: %s", exc)
            usage = []
        spend = [c for c in usage if c.priced and not c.free and c.cost_usd]
        index = int((at.replace(second=0, microsecond=0) - first).total_seconds() // 60)
        if 0 <= index < minutes:
            bucket = buckets[index]
            if state == "done":
                bucket.pages_done += 1
                kind = _runtime([c.place for c in usage if c.place], target)
                runtimes[kind] = runtimes.get(kind, 0) + 1
            else:
                bucket.pages_failed += 1
            bucket.spend_usd += sum(c.cost_usd for c in spend)
            bucket.tokens += sum(c.total_tokens for c in usage)
        if at >= midnight:
            for c in spend:
                today[c.provider] = today.get(c.provider, 0.0) + c.cost_usd
    for bucket in buckets:
        bucket.spend_usd = round(bucket.spend_usd, 6)
    result.by_runtime = runtimes
    result.today_spend_by_provider = {p: round(v, 6) for p, v in today.items()}
    result.today_spend_usd = round(sum(today.values()), 6)
    return result


@router.get("/history", response_model=ActivityHistory)
async def get_activity_history(
    db: Database = Depends(get_library_database),
    minutes: int = Query(60, ge=5, le=1440, description="the window, in minutes ending now"),
) -> ActivityHistory:
    """Pages done and failed, dollars and tokens per minute, pages by runtime, and today's spend by provider
    (`activity.window.bottom-panel`). Read-only; the reads are of what was committed and run off the loop."""
    def read() -> ActivityHistory:
        with committed(db):
            return history(db, minutes)

    return await asyncio.to_thread(read)

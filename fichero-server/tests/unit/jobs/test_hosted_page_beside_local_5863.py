"""`activity.lane.each-unit-its-own-lane`: a hosted model's call starts while a local page runs on the model lane,
because `llm.model_call_slot` puts it on the network lane (#5863). Real lanes and rows; work faked."""
from __future__ import annotations

import asyncio
import threading
import time

import pytest

from fichero_server import llm
from fichero_server.execution import jobs

KRAKEN = "kraken-page-hb"


def test_a_hosted_call_starts_while_a_local_page_runs(db, test_package, monkeypatch):
    local_started, release = threading.Event(), threading.Event()

    def work(db_, subject):
        local_started.set()
        release.wait(30)

    monkeypatch.setitem(jobs.KINDS, KRAKEN, jobs.Kind(run=work, model="kraken:blla", lane="local-ml", name="Read a page"))
    monkeypatch.setenv("FICHERO_JOB_THROTTLE", "0")
    try:
        jobs.enqueue(db, KRAKEN, "k", started_by="owner")
        assert local_started.wait(30), "the local page never started"
        entered = []

        async def hosted_call():
            config = llm.LLMConfig(provider="openai", model="gpt-x")
            async with llm.model_call_slot(config, library=test_package, subject="a hosted page"):
                entered.append(time.monotonic())

        asyncio.run(asyncio.wait_for(hosted_call(), 30))
        assert entered, "the hosted call waited behind a local page"
    finally:
        release.set()

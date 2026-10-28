"""A recipe run a person started begins at once while they use the Mac, slower, never waiting for idle (#6263,
`activity.throttle.in-use-slows-to-half`). The run-a-recipe row is on the real scheduler; the Mac's signals are faked."""
from __future__ import annotations

import time

import pytest

from fichero_server.execution import jobs, throttle
from fichero_server.recipes import runner
from tests.unit.jobs.test_start_stop_mode import _wait_for, mac  # noqa: F401  (fixture)


@pytest.mark.parametrize("starter", ["owner", "owner on Air"])
def test_a_started_run_begins_while_the_mac_is_in_use_and_on_battery(db, mac, monkeypatch, starter):  # noqa: F811
    ran: list[str] = []
    monkeypatch.setitem(jobs.KINDS, runner.KIND, jobs.Kind(run=lambda d, s: ran.append(s), model=None, lane="recipes"))
    mac["in_use"] = True
    mac["battery"] = True
    jobs.enqueue_remote(db, runner.KIND, "recipe:one", target="this-mac", detail="{}", reason="w", started_by=starter)
    assert _wait_for(lambda: "recipe:one" in ran, 5), "the person's run began while the Mac is in use"

"""A project's cap on what cloud calls may spend (`ai.where.cloud-spend-cap`, #5943).

EVERY project has a cap (owner's ruling 2026-10-20): US$10 a month unless Set Up's `cloud_spend_cap_usd` answer says
otherwise, as high as the person likes. A call's worst case is RESERVED when the call is about to be sent (inside its lane
slot, so a page still queued holds nothing); when it ends the reservation is released and what the provider reported is
booked. A call that would not fit what is already booked is refused, in words, and a workflow run it belongs to is asked to
pause; a call that fits only once other calls in flight have finished waits for them. A call under a model with no listed
price is held at an assumed price, never free.

Booked spend is kept in the project (`recipe/cloud-spend.json`, one UTC month at a time, kept across restarts);
reservations live only in this engine, so a crash frees them and never loses what was booked.
"""

from __future__ import annotations

import asyncio
import contextlib
import contextvars
import json
import os
import threading
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from pathlib import Path

CAP_KEY = "cloud_spend_cap_usd"
#: The cap of a project that has not set one (owner's ruling 2026-10-20: every project has a cap).
DEFAULT_CAP_USD = 10.0
#: What one call to a model with no listed price is held at, and booked at when it reports no priced usage.
UNPRICED_CALL_USD = 0.50
LEDGER = "cloud-spend.json"
#: What a call is assumed to send when its caller does not say: a page image and its instruction, generously.
DEFAULT_INPUT_TOKENS = 30_000

_LOCK = threading.Lock()
_RESERVED: dict[str, float] = {}  # library -> worst cases of the calls in flight
_TICKET: contextvars.ContextVar[list[float] | None] = contextvars.ContextVar("cloud_spend_ticket", default=None)


class CloudSpendRefusedError(RuntimeError):
    """A cloud call refused because its worst case does not fit the project's cap. Nothing was sent."""


def _recipe_dir(library: str) -> Path:
    from fichero_server.recipes.project import FOLDER

    return Path(library) / FOLDER


def cap_usd(library: str | None) -> float | None:
    """The project's monthly cloud cap: its Set Up answer, else US$10. None only for a call under no project (the egress gate
    refuses a cloud call there before it reaches the cap)."""
    if not library:
        return None
    try:
        import yaml

        answers = yaml.safe_load((_recipe_dir(library) / "setup.yaml").read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 -- no setup, the default cap
        return DEFAULT_CAP_USD
    cap = answers.get(CAP_KEY) if isinstance(answers, dict) else None
    ok = isinstance(cap, (int, float)) and not isinstance(cap, bool) and cap >= 0
    return float(cap) if ok else DEFAULT_CAP_USD


def _month(now: datetime | None = None) -> str:
    return (now or datetime.now(timezone.utc)).strftime("%Y-%m")


def booked_usd(library: str, now: datetime | None = None) -> float:
    """What cloud calls have been booked this (UTC) month."""
    try:
        data = json.loads((_recipe_dir(library) / LEDGER).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return 0.0
    return float(data.get("usd", 0.0)) if data.get("month") == _month(now) else 0.0


def _book(library: str, usd: float, now: datetime | None = None) -> None:
    total = booked_usd(library, now) + usd
    path = _recipe_dir(library) / LEDGER
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"month": _month(now), "usd": round(total, 6)}), encoding="utf-8")
    os.replace(tmp, path)


def worst_case_usd(config, input_tokens: int | None = None) -> float:
    """The most one call can cost: its input (`input_tokens`, else the default) and the full output the config allows (the
    model's catalogue maximum when that is smaller), at the model's listed prices. A model with no listed price is held
    at `UNPRICED_CALL_USD`."""
    from fichero_server.llm.usage import _registry_entry, price_call

    out = min(int(getattr(config, "max_tokens", 0) or 8192), 1_000_000)
    entry = _registry_entry(getattr(config, "model", ""), getattr(config, "provider", "")) or {}
    catalogue = entry.get("max_output_tokens")
    if isinstance(catalogue, (int, float)) and catalogue > 0:
        out = min(out, int(catalogue))
    priced = price_call({"provider": config.provider, "model": config.model,
                         "input_tokens": input_tokens or DEFAULT_INPUT_TOKENS, "output_tokens": out})
    return priced.cost_usd if priced.priced else UNPRICED_CALL_USD


def note_actual(cost_usd: float | None) -> None:
    """The cost the provider's report gave one call under the open reservation (None: it could not be priced)."""
    ticket = _TICKET.get()
    if ticket is not None:
        ticket.append(float("nan") if cost_usd is None else cost_usd)


def _ask_run_to_pause() -> str | None:
    """Ask the workflow run this call belongs to to pause at its next boundary; its id, or None outside a run."""
    from fichero_server.workflows.node_context import get_current_node

    node = get_current_node()
    run_id = (node.run_id or None) if node else None
    if run_id:
        from fichero_server.execution.cancellation import request_pause

        request_pause(run_id)
    return run_id


@contextlib.asynccontextmanager
async def holding(config, library: str | None, *, input_tokens: int | None = None) -> AsyncIterator[None]:
    """Hold the call's worst case against the project's cap from the moment it is about to be sent until it ends, then
    release it and book the cost. Waits while the cap is reachable only because of calls in flight; refuses (and asks a
    run to pause) when the booked spend plus this call's worst case does not fit. A call under no library and a call that
    costs nothing (on this Mac) pass."""
    from fichero_server.llm.usage import provider_is_free

    cap = cap_usd(library)
    if cap is None or (config is not None and provider_is_free(config.provider, None)):
        yield
        return
    worst = worst_case_usd(config, input_tokens) if config is not None else UNPRICED_CALL_USD
    while True:
        with _LOCK:
            booked, reserved = booked_usd(library), _RESERVED.get(library, 0.0)
            if booked + worst > cap + 1e-9:
                paused = _ask_run_to_pause()
                raise CloudSpendRefusedError(
                    f"This project's cloud spend is capped at ${cap:.2f} a month; ${booked:.2f} is spent this month and this "
                    f"call could cost up to ${worst:.2f}, so it was not sent"
                    + (" and the run is pausing" if paused else "")
                    + ". Raise the cap in the project's Set Up to go on, or wait for the month to turn.")
            if booked + reserved + worst <= cap + 1e-9:
                _RESERVED[library] = reserved + worst
                break
        await asyncio.sleep(0.2)  # the cap is reachable only through calls in flight: they will end
    ticket: list[float] = []
    token = _TICKET.set(ticket)
    outcome = "failed"  # a provider error: it answered, nothing is owed beyond what it reported
    try:
        yield
        outcome = "answered"
    except asyncio.CancelledError:
        outcome = "cancelled"  # sent, and nobody knows what the provider billed
        raise
    finally:
        _TICKET.reset(token)
        known = [c for c in ticket if c == c]  # not NaN
        priced_all = len(known) == len(ticket)
        if outcome == "failed":
            spent = sum(known) if priced_all else worst
        else:  # answered or cancelled: what was reported, else the worst case, never free
            spent = sum(known) if (known and priced_all) else worst
        with _LOCK:
            _RESERVED[library] = max(0.0, _RESERVED.get(library, 0.0) - worst)
            if spent:
                _book(library, spent)

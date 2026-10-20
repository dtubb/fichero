"""A project's cap on what cloud calls may spend (`ai.where.cloud-spend-cap`, #5943).

Set Up's `cloud_spend_cap_usd` answer is a monthly cap on the model calls the project sends to a cloud provider (beside
`hf_spend_cap_usd`, which caps Hugging Face Jobs). Before a call is sent its worst case is RESERVED against the cap; when
it ends the reservation is released and what the provider reported is booked. A call whose worst case does not fit is
refused, in words, and nothing is sent. No answer is no cap; an answer of 0 is a project that spends nothing in the cloud.

Booked spend is kept in the project (`recipe/cloud-spend.json`, one month at a time, kept across restarts); reservations
live only in this engine, so a crash frees them and never loses what was booked.
"""

from __future__ import annotations

import contextlib
import contextvars
import json
import os
import threading
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from pathlib import Path

CAP_KEY = "cloud_spend_cap_usd"
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
    """The project's monthly cloud cap, None when it has not set one (or the answer is not a number >= 0)."""
    if not library:
        return None
    try:
        import yaml

        answers = yaml.safe_load((_recipe_dir(library) / "setup.yaml").read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 -- no setup, no cap
        return None
    cap = answers.get(CAP_KEY) if isinstance(answers, dict) else None
    return float(cap) if isinstance(cap, (int, float)) and not isinstance(cap, bool) and cap >= 0 else None


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


def worst_case_usd(config, input_tokens: int | None = None) -> float | None:
    """The most one call can cost: its input (`input_tokens`, else the default) and the full output the config allows,
    at the model's listed prices. None when the model has no listed price: such a call cannot be held to a cap."""
    from fichero_server.llm.usage import price_call

    out = min(int(getattr(config, "max_tokens", 0) or 8192), 1_000_000)
    priced = price_call({"provider": config.provider, "model": config.model,
                         "input_tokens": input_tokens or DEFAULT_INPUT_TOKENS, "output_tokens": out})
    return priced.cost_usd if priced.priced else None


def note_actual(cost_usd: float | None) -> None:
    """The cost the provider's report gave one call under the open reservation (None: it could not be priced)."""
    ticket = _TICKET.get()
    if ticket is not None:
        ticket.append(float("nan") if cost_usd is None else cost_usd)


@contextlib.asynccontextmanager
async def holding(config, library: str | None, *, input_tokens: int | None = None) -> AsyncIterator[None]:
    """Reserve the call's worst case against the project's cap before it is sent; release it and book the actual cost
    when it ends. A project with no cap, a call under no library and a call that costs nothing (on this Mac) pass."""
    from fichero_server.llm.usage import provider_is_free

    cap = cap_usd(library)
    if cap is None or provider_is_free(config.provider, None):
        yield
        return
    worst = worst_case_usd(config, input_tokens)
    if worst is None:
        raise CloudSpendRefusedError(
            f"This project caps its cloud spend at ${cap:.2f} a month, and {config.provider}/{config.model} has no listed "
            "price, so the call was not sent: its cost cannot be held to the cap. Choose a model with a price, or lift the cap.")
    with _LOCK:
        booked, reserved = booked_usd(library), _RESERVED.get(library, 0.0)
        if booked + reserved + worst > cap + 1e-9:
            raise CloudSpendRefusedError(
                f"This project caps its cloud spend at ${cap:.2f} a month; ${booked:.2f} is booked this month and "
                f"${reserved:.2f} is held for calls in flight, and this call could cost up to ${worst:.2f}, so it was not "
                "sent. Raise the cap in the project's Set Up, or wait for the month to turn.")
        _RESERVED[library] = reserved + worst
    ticket: list[float] = []
    token = _TICKET.set(ticket)
    failed = True
    try:
        yield
        failed = False
    finally:
        _TICKET.reset(token)
        known = [c for c in ticket if c == c]  # not NaN
        # A failed call books what the provider reported (usually nothing); an answer with no priced usage books its
        # worst case, never free.
        spent = sum(known) if (known or failed) and len(known) == len(ticket) else worst
        with _LOCK:
            _RESERVED[library] = max(0.0, _RESERVED.get(library, 0.0) - worst)
            if spent:
                _book(library, spent)

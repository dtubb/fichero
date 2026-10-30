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
import math
import os
import threading
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from pathlib import Path

CAP_KEY = "cloud_spend_cap_usd"
#: The most the project may spend on cloud calls in all, across months (maintainer's ruling 2026-10-30); unset: no such limit.
PROJECT_CAP_KEY = "cloud_project_cap_usd"
#: The cap of a project that has not set one (owner's ruling 2026-10-20: every project has a cap).
DEFAULT_CAP_USD = 10.0
#: What one call to a model with no listed price is held at, and booked at when it reports no priced usage.
UNPRICED_CALL_USD = 0.50
LEDGER = "cloud-spend.json"
#: What a call is assumed to send when its caller does not say: a page image and its instruction, generously.
DEFAULT_INPUT_TOKENS = 30_000

_LOCK = threading.Lock()
_RESERVED: dict[str, float] = {}  # library -> worst cases of the calls in flight
_TIMEOUTS = (TimeoutError, asyncio.TimeoutError)  # one class from Python 3.11, two on 3.10 (pyproject allows it)
_TICKET: contextvars.ContextVar[list[float] | None] = contextvars.ContextVar("cloud_spend_ticket", default=None)


class RefusedForTheRun(RuntimeError):
    """A refusal that holds for every call the run would make: a page loop stops at the first, says it once, in words
    (`workflows/builder.py`, `refused_for_all`), instead of failing each page with the same sentence."""


class CloudSpendRefusedError(RefusedForTheRun):
    """A cloud call refused because its worst case does not fit the project's cap. Nothing was sent."""


class CloudModelUnpriced(RefusedForTheRun):
    """A cloud call refused because the model has no listed price, so its cost cannot be held to the cap, and this project has
    not accepted it. The words are for people; the way out is in fields (`action`, `route`, `provider`, `model`) for a client
    to offer (`ai.where.accept-unpriced-cloud-model`, #5987)."""

    action = "cloud.accept_unpriced"
    route = "/api/recipes/cloud/accept-unpriced"

    def __init__(self, message: str, provider: str = "", model: str = ""):
        super().__init__(message)
        self.provider, self.model = provider, model


#: The `provider/model` keys this project accepted to call without a listed price: a file in the project folder, not Set Up's
#: answers (a project with no Set Up must be able to accept, and accepting must not make one).
ACCEPTED_FILE = "cloud_unpriced_accepted.json"


def model_key(provider: str, model: str) -> str:
    return f"{provider}/{model}"


def accepted_models(library: str | Path) -> list[str]:
    """The `provider/model` keys this project accepted to call without a listed price."""
    try:
        value = json.loads((Path(library) / ACCEPTED_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [str(m) for m in value] if isinstance(value, list) else []


def set_accepted(library: str | Path, provider: str, model: str, accepted: bool) -> list[str]:
    """Accept (or withdraw the acceptance of) one cloud model with no listed price; the whole list kept, atomically written.
    Callers go through the audited action `cloud.accept_unpriced`, never here."""
    with _LOCK:
        kept = set(accepted_models(library))
        (kept.add if accepted else kept.discard)(model_key(provider, model))
        return _write_accepted(library, kept)


def _write_accepted(library: str | Path, kept: set[str]) -> list[str]:
    path = Path(library) / ACCEPTED_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(sorted(kept)), encoding="utf-8")
    tmp.replace(path)
    return sorted(kept)


def has_listed_price(provider: str, model: str) -> bool:
    """Whether the price list has both an input and an output rate for this cloud model (`llm/usage.price_call`'s own rule)."""
    from fichero_server.llm.usage import _registry_entry

    entry = _registry_entry(model, provider) or {}
    return entry.get("input_cost_per_token") is not None and entry.get("output_cost_per_token") is not None


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


def project_cap_usd(library: str | None) -> float | None:
    """The most the project may spend on cloud calls in all (`answers.cloud_project_cap_usd`); None: no such limit. A
    malformed answer is no limit here too, since the monthly cap still holds."""
    if not library:
        return None
    try:
        import yaml

        answers = yaml.safe_load((_recipe_dir(library) / "setup.yaml").read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 -- no setup, no project limit
        return None
    cap = answers.get(PROJECT_CAP_KEY) if isinstance(answers, dict) else None
    ok = isinstance(cap, (int, float)) and not isinstance(cap, bool) and cap >= 0
    return float(cap) if ok else None


def _past_a_cap(library: str, reserved: float, worst: float) -> str | None:
    """Why `worst` more, beside what is booked and `reserved`, does not fit the monthly cap or the project's total cap, in words
    naming that cap; None when it fits both. Called with the lock held."""
    cap, project_cap = cap_usd(library), project_cap_usd(library)
    booked, total = booked_usd(library), total_booked_usd(library)
    if cap is not None and booked + reserved + worst > cap + 1e-9:
        return f"this project's cloud spend is capped at ${cap:.2f} a month, of which ${booked:.2f} is spent this month"
    if project_cap is not None and total + reserved + worst > project_cap + 1e-9:
        return f"this project's cloud spend is capped at ${project_cap:.2f} in all, of which ${total:.2f} is spent"
    return None


def _month(now: datetime | None = None) -> str:
    return (now or datetime.now(timezone.utc)).strftime("%Y-%m")


def booked_usd(library: str, now: datetime | None = None) -> float:
    """What cloud calls have been booked this (UTC) month."""
    try:
        data = json.loads((_recipe_dir(library) / LEDGER).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return 0.0
    return float(data.get("usd", 0.0)) if data.get("month") == _month(now) else 0.0


def total_booked_usd(library: str) -> float:
    """What cloud calls have been booked in all, across months. A ledger from before the total was kept counts its month's spend."""
    try:
        data = json.loads((_recipe_dir(library) / LEDGER).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return 0.0
    return float(data.get("total_usd", data.get("usd", 0.0))) if isinstance(data, dict) else 0.0


def _ledger(library: str, now: datetime | None = None) -> dict:
    try:
        data = json.loads((_recipe_dir(library) / LEDGER).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) and data.get("month") == _month(now) else {}


def assumed(library: str, now: datetime | None = None) -> tuple[int, float]:
    """(calls, dollars) this month that were booked at the assumed price of a model with no listed price: counted against the
    cap, and listed apart so a person sees which spend is an assumption."""
    data = _ledger(library, now)
    return int(data.get("assumed_calls", 0)), float(data.get("assumed_usd", 0.0))


def _book(library: str, usd: float, now: datetime | None = None, *, assumed_price: bool = False) -> None:
    data = _ledger(library, now)
    calls, assumed_usd = int(data.get("assumed_calls", 0)), float(data.get("assumed_usd", 0.0))
    if assumed_price:
        calls, assumed_usd = calls + 1, assumed_usd + usd
    path = _recipe_dir(library) / LEDGER
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"month": _month(now), "usd": round(float(data.get("usd", 0.0)) + usd, 6),
                               "total_usd": round(total_booked_usd(library) + usd, 6),
                               "assumed_calls": calls, "assumed_usd": round(assumed_usd, 6)}), encoding="utf-8")
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
async def holding(config, library: str | None, *, input_tokens: int | None = None, calls: int = 1) -> AsyncIterator[None]:
    """Hold the call's worst case against the project's cap from the moment it is about to be sent until it ends, then
    release it and book the cost. Waits while the cap is reachable only because of calls in flight; refuses (and asks a
    run to pause) when the booked spend plus this call's worst case does not fit. A call under no library and a call that
    costs nothing (on this Mac) pass. A batch holds `calls` worst cases at once, like the calls it is."""
    from fichero_server.llm.usage import provider_is_free

    cap = cap_usd(library)
    if cap is None or (config is not None and provider_is_free(config.provider, None)):
        yield
        return
    unpriced = config is not None and not has_listed_price(config.provider, config.model)
    if unpriced and model_key(config.provider, config.model) not in accepted_models(library):
        raise CloudModelUnpriced(
            f"{config.model} ({config.provider}) has no listed price, so its cost cannot be held to this project's cloud "
            "spending cap. Accept running it in this project (it is counted at an assumed price, and listed apart), or choose "
            "a model with a price.", config.provider, config.model)
    worst = (worst_case_usd(config, input_tokens) if config is not None else UNPRICED_CALL_USD) * max(1, calls)
    while True:
        with _LOCK:
            reserved = _RESERVED.get(library, 0.0)
            if why := _past_a_cap(library, 0.0, worst):
                paused = _ask_run_to_pause()
                raise CloudSpendRefusedError(
                    f"This call could cost up to ${worst:.2f} and {why}, so it was not sent"
                    + (" and the run is pausing" if paused else "")
                    + ". Raise the cap in the project's Set Up to go on.")
            if not _past_a_cap(library, reserved, worst):
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
    except Exception as exc:
        if isinstance(exc, _TIMEOUTS) or isinstance(exc.__cause__, _TIMEOUTS):  # the "provider hang" wrappers chain it
            outcome = "timed out"  # sent, the wall clock gave up: the provider may still bill it, so the reservation is booked
        raise
    finally:
        _TICKET.reset(token)
        known = [c for c in ticket if c == c]  # not NaN
        priced_all = len(known) == len(ticket)
        if outcome == "failed":
            spent = sum(known) if priced_all else worst
        else:  # answered, cancelled or timed out: what was reported, else the worst case, never free
            spent = sum(known) if (known and priced_all) else worst
        with _LOCK:
            _RESERVED[library] = max(0.0, _RESERVED.get(library, 0.0) - worst)
            if spent:
                _book(library, spent, assumed_price=unpriced)


def plan_line(library: str, *, estimate_usd: float | None, cloud_models: list[tuple[str, str]] | None = None,
              pages: int = 0) -> dict:
    """Start's plan: the monthly cap and the project's total cap, what is booked against each, what each leaves, and the
    run's estimate beside them. `over` asks before the run starts, naming which cap (`over_month`, `over_project`) and the cap
    that would let the estimate through (`needed_*`); `fewer_pages` is left for the caller to find (it needs the plan's own pricing: `recipes._first_pages_that_fit`). An
    unknown estimate (a model with no listed price) is `unpriced`, never a $0. Models with no price the project has not
    accepted are named in `unpriced_models` and the `note`, never a refusal (#6259); spend booked at an assumed price is
    listed apart."""
    cap = cap_usd(library) or 0.0
    done = booked_usd(library)
    remaining = max(0.0, cap - done)
    project_cap, total = project_cap_usd(library), total_booked_usd(library)
    project_remaining = None if project_cap is None else max(0.0, project_cap - total)
    accepted = accepted_models(library)
    to_accept = sorted({model_key(provider, model) for provider, model in cloud_models or []
                        if not has_listed_price(provider, model) and model_key(provider, model) not in accepted})
    calls, usd = assumed(library)
    note = (f"No listed price for {', '.join(to_accept)}: counted at an assumed US${UNPRICED_CALL_USD:.2f} a call and listed "
            "apart; pressing Start accepts running them." if to_accept else None)
    known = estimate_usd is not None
    over_month = known and estimate_usd > remaining + 1e-9
    over_project = known and project_remaining is not None and estimate_usd > project_remaining + 1e-9
    return {"note": note, "cap_usd": cap, "spent_usd": done, "remaining_usd": remaining, "estimate_usd": estimate_usd,
            "over": over_month or over_project, "unpriced": estimate_usd is None,
            "over_month": over_month, "over_project": over_project,
            "needed_cap_usd": needed_cap_usd(done, estimate_usd) if over_month else None,
            "project_cap_usd": project_cap, "project_spent_usd": total,
            "needed_project_cap_usd": needed_cap_usd(total, estimate_usd) if over_project else None,
            "fewer_pages": None, "pages": pages,
            "unpriced_models": to_accept, "assumed_calls": calls, "assumed_usd": usd}


def needed_cap_usd(spent_usd: float, estimate_usd: float) -> float:
    """The smallest whole-cent cap under which this run's estimate fits what is already booked.
    The best estimate itself, no margin (maintainer's ruling 2026-10-30; the estimate's own accuracy is #6294)."""
    return math.ceil(round((spent_usd + estimate_usd) * 100, 6)) / 100


# --- a provider batch (`compute.recipe.cloud-batch-consent-and-cost`, #5940) ----------------------------------------
#: The providers bill a batch at half the listed price; used when the price list names no batch price for the model.
BATCH_SHARE = 0.5


def batch_cost_usd(provider: str, model: str, input_tokens: int, output_tokens: int) -> float | None:
    """What a batch line costs: the price list's batch rates, else half the listed rates; None for a model with no price."""
    from fichero_server.llm.usage import _registry_entry, price_call

    entry = _registry_entry(model, provider) or {}
    rate_in, rate_out = entry.get("input_cost_per_token_batches"), entry.get("output_cost_per_token_batches")
    if rate_in is not None and rate_out is not None:
        return input_tokens * float(rate_in) + output_tokens * float(rate_out)
    priced = price_call({"provider": provider, "model": model, "input_tokens": input_tokens,
                         "output_tokens": output_tokens})
    return priced.cost_usd * BATCH_SHARE if priced.priced else None


def batch_worst_usd(provider: str, model: str, *, max_tokens: int, input_tokens: int | None = None) -> float:
    """The most one batch request can cost: the plain call's worst case at the batch share (an unpriced model at the
    assumed price, as a plain call is)."""
    from types import SimpleNamespace

    worst = worst_case_usd(SimpleNamespace(provider=provider, model=model, max_tokens=max_tokens), input_tokens)
    return worst * BATCH_SHARE if has_listed_price(provider, model) else worst


def reserve_batch(library: str, provider: str, model: str, *, requests: int, max_tokens: int) -> float:
    """Hold a batch's worst case against the cap from submission until it ends (it may answer a day later); refused in
    words, before anything is sent, when the booked spend, what is held and this batch do not fit. The amount held."""
    worst = batch_worst_usd(provider, model, max_tokens=max_tokens) * max(1, requests)
    with _LOCK:
        reserved = _RESERVED.get(library, 0.0)
        if why := _past_a_cap(library, reserved, worst):
            raise CloudSpendRefusedError(
                f"This batch of {requests} could cost up to ${worst:.2f} (${reserved:.2f} more is held for calls out) and {why}, "
                "so it was not sent. Raise the cap in the project's Set Up, or send fewer pages.")
        _RESERVED[library] = reserved + worst
    return worst


def hold_again(library: str, usd: float) -> None:
    """A batch adopted after a restart: its hold, kept on its row, is held again (the hold lives in this process)."""
    with _LOCK:
        _RESERVED[library] = _RESERVED.get(library, 0.0) + usd


def settle_batch(library: str, held: float, spent_usd: float) -> None:
    """A batch ended: let go of its hold and book what its lines were billed."""
    with _LOCK:
        _RESERVED[library] = max(0.0, _RESERVED.get(library, 0.0) - held)
        if spent_usd:
            _book(library, spent_usd)

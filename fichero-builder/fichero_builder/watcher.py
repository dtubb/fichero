"""The watcher's judgement (dev-workflows.run.watch-tick): from what a session file says and what the journal has spent,
decide handoff, park, alert or nothing. Plain functions, no process control here; `builder run` (next slice) calls them.

Caps come from `harness.toml [spend]`; a missing cap or an unknown price REFUSES to start (audit 2026-11-01 H6)."""
from __future__ import annotations

import re

import json
import tomllib
from dataclasses import dataclass, field
from pathlib import Path


KEYS = {"window", "handoff_at", "handoff_tokens", "session_usd", "day_usd", "silent_s", "prices", "metered", "week_usd"}
ALWAYS_METERED = ("openrouter",)  # bills by use whatever the file says: a role on it never starts without a weekly figure


@dataclass(frozen=True)
class Spend:
    window: int = 200_000          # the model's context window, tokens
    handoff_at: float = 0.85       # hand off when the latest prompt reaches this share of the window
    handoff_tokens: int = 0        # or at this many tokens, when set (dev-workflows.run.loop-handoff-tokens: a 1M window cost 17M tokens a lane)
    session_usd: float = 0.0       # read and ignored: owner ruling B2 (2026-11-21) dropped the dollar session cap
    day_usd: float = 0.0           # 0 = no cap declared = refuse to start
    silent_s: int = 1800           # a session file unchanged this long while not idle = alert
    prices: dict = field(default_factory=dict)  # model name or prefix -> [usd per M input tokens, usd per M output tokens]
    metered: tuple = ()            # [spend].metered: providers that bill by use (local.spend.metered-provider-needs-a-cap)
    week_usd: dict = field(default_factory=dict)  # [spend.week_usd]: provider -> its cap per ISO week (Monday to Sunday), USD


LOCAL = Path.home() / ".config" / "fichero-builder" / "harness.local.toml"


def local_file(root) -> Path | None:
    """The machine's own override, only when it is the owner's: it lives under the running user's home, is owned by whoever owns the
    checkout (a jailed worker's own home file is owned by the worker, so its copy is ignored: review 2026-11-02, `builder run` sets
    journal.STATE to a folder the worker writes), and is not group- or world-writable."""
    try:
        st = LOCAL.stat()
        owner = Path(root).stat().st_uid
    except OSError:
        return None
    return LOCAL if LOCAL.is_file() and st.st_uid == owner and not st.st_mode & 0o022 else None


def load(root) -> Spend:
    """`<root>/harness.toml` [spend]; no table = the zero caps, which refuse. Unknown keys and bad prices refuse."""
    return parse(table(root))


def table(root) -> dict:
    """The raw [spend] table of `<root>/harness.toml` with this machine's own override merged over it."""
    f = Path(root) / "harness.toml"
    t = tomllib.loads(f.read_text()).get("spend", {}) if f.is_file() else {}
    if (local := local_file(root)) is not None:  # this machine's own caps (manager 2026-11-02)
        t = {**t, **tomllib.loads(local.read_text()).get("spend", {})}
    return t


def parse(t: dict) -> Spend:
    """A raw [spend] table as a Spend; unknown keys and bad prices raise ValueError."""
    if unknown := sorted(set(t) - KEYS):
        raise ValueError(f"harness.toml [spend]: unknown keys {unknown}")
    prices = t.get("prices", {})
    for k, v in prices.items():
        if not (isinstance(v, list) and len(v) == 2 and all(isinstance(x, (int, float)) and x >= 0 for x in v)):
            raise ValueError(f"harness.toml [spend].prices.{k}: two numbers, usd per million input and output tokens")
    metered, week = t.get("metered", []), t.get("week_usd", {})
    if not (isinstance(metered, list) and all(isinstance(x, str) and x for x in metered)):
        raise ValueError("harness.toml [spend].metered: a list of provider names")
    if not isinstance(week, dict) or not all(isinstance(v, (int, float)) and v >= 0 for v in week.values()):
        raise ValueError("harness.toml [spend.week_usd]: provider = USD a week, a number")
    if missing := [p for p in metered if not week.get(p)]:  # a metered provider with no figure refuses the rules file
        raise ValueError(f"harness.toml [spend].metered lists {missing} with no [spend.week_usd] figure: a metered provider needs a weekly cap")
    d = Spend()
    return Spend(metered=tuple(metered), week_usd={k: float(v) for k, v in week.items()}, window=int(t.get("window", d.window)), handoff_at=float(t.get("handoff_at", d.handoff_at)), handoff_tokens=int(t.get("handoff_tokens", 0)),
                 session_usd=float(t.get("session_usd", 0)), day_usd=float(t.get("day_usd", 0)),
                 silent_s=int(t.get("silent_s", d.silent_s)), prices=dict(prices))


def threshold(spend: Spend) -> int:
    """The context size at which a session hands off: `handoff_tokens` when set, else the share of the window."""
    return spend.handoff_tokens or int(spend.window * spend.handoff_at)


def price_for(model: str, spend: Spend):
    """[in, out] for the model: an exact key, else the longest key the model name contains; None if unknown."""
    if model in spend.prices:
        return spend.prices[model]
    model = re.sub(r"\[[^\]]*\]$", "", model)  # 2026-11-27: `claude-fable-5-2[1m]` is claude-fable-5-2 with a 1M context: its rates
    if model in spend.prices:
        return spend.prices[model]
    hits = sorted((k for k in spend.prices if k and k in model), key=len)
    return spend.prices[hits[-1]] if hits else None


def is_metered(spend: Spend, provider: str) -> bool:
    """The provider bills by use: listed in [spend].metered, or one of ALWAYS_METERED. A subscription login (claude-code) is not."""
    return bool(provider) and (provider in spend.metered or provider in ALWAYS_METERED)


def week_of(ts: str) -> tuple:
    """The ISO (year, week) of a journal timestamp (`YYYY-MM-DDTHH:MM:SS`); () when it does not parse."""
    import datetime
    try:
        return tuple(datetime.date.fromisoformat(str(ts)[:10]).isocalendar()[:2])
    except ValueError:
        return ()


def spent_week(rows: list[dict], provider: str, now_ts: str) -> float:
    """Sum of the journal's `cost` rows that name `provider`, in the ISO week of `now_ts`: a row with no provider is not counted."""
    wk = week_of(now_ts)
    return sum(float(r.get("usd", 0)) for r in rows
               if r.get("event") == "cost" and r.get("provider") == provider and week_of(r.get("ts", "")) == wk)


def price_key(model: str) -> str:
    return re.sub(r"\[[^\]]*\]$", "", model)


def price_message(model: str) -> str:
    return (f"harness.toml [spend].prices has no price for {model!r}: add `{price_key(model)} = [<in>, <out>]` (USD per million "
            "tokens); no session on it starts")


def price_problems(root) -> list[tuple[str, str]]:
    """[(model, message)] for each Claude Code model a [models] role names that [spend].prices cannot price (2026-11-27: the role
    maintainer-fable moved to claude-fable-5-2[1m] with no price, and three lanes died 'gone' three times each)."""
    from fichero_builder import models
    spend, mdl = load(root), models.load(root)
    out = {}
    for role, row in mdl.items():
        if isinstance(row, dict) and row.get("provider") == "claude-code" and row.get("model") and price_for(row["model"], spend) is None:
            out[row["model"]] = price_message(row["model"])
    return sorted(out.items())


def refusals(spend: Spend, kind: str, model: str, provider: str = "") -> list[str]:
    """Every reason not to start a worker of this kind and model; empty = go."""
    out = []
    if is_metered(spend, provider) and spend.week_usd.get(provider, 0) <= 0:
        out.append(f"provider {provider!r} bills by use and harness.toml [spend.week_usd] gives it no weekly cap: no cap, no start")
    if spend.day_usd <= 0:
        out.append("harness.toml [spend] must set day_usd above 0: no cap, no start")
    if kind != "pi" and price_for(model, spend) is None:  # a Pi session file carries its own price per turn
        out.append(f"harness.toml [spend].prices has no price for {model!r}: unknown price, no start")
    return out


def cost_of(state: dict, spend: Spend, model: str) -> float:
    """What the session has cost: the file's own figure when it has one, else from its token counts at the model's
    price: fresh and cache-written input at the input price, cache reads at a tenth of it, and the rest (output) at the
    output price. ponytail: the tenth is Anthropic's cache-read rate; a provider table per price comes with the Pi kind."""
    if state.get("cost_usd"):
        return float(state["cost_usd"])
    p = price_for(model, spend)
    if not p:
        return 0.0
    fresh, cache_w, cache_r = state.get("fresh", 0), state.get("cache_write", 0), state.get("cache_read", 0)
    output = max(0, state.get("tokens", 0) - fresh - cache_w - cache_r)
    return ((fresh + cache_w) * p[0] + cache_r * p[0] / 10 + output * p[1]) / 1e6


def spent_today(rows: list[dict], today: str) -> float:
    """Sum of the journal's `cost` rows dated `today` (YYYY-MM-DD)."""
    return sum(float(r.get("usd", 0)) for r in rows if r.get("event") == "cost" and str(r.get("ts", "")).startswith(today))


LIVE_STALE_S = 300  # ponytail: a crashed run's live file stops counting after this; a pid check is the upgrade


def live_spend(d, today: str, exclude: str, now: float) -> float:
    """local.perf.day-cap-counts-live-sessions (#6871): the running cost of every other live session, from the files
    `<d>/<name>.json` = {"usd", "day"} each run rewrites every tick; only today's, changed within LIVE_STALE_S, not `exclude`'s."""
    total = 0.0
    for f in Path(d).glob("*.json") if Path(d).is_dir() else ():
        try:  # another run deletes its file when it ends: a vanished or unreadable file is not a spend
            if f.stem == exclude or now - f.stat().st_mtime > LIVE_STALE_S:
                continue
            doc = json.loads(f.read_text())
        except (OSError, ValueError):
            continue
        if doc.get("day") == today:
            total += float(doc.get("usd", 0))
    return total


def assess(state: dict, spend: Spend, model: str, *, spent_today: float, silent_for_s: float, provider: str = "",
           spent_week: float = 0.0) -> list[str]:
    """Decisions in the order the watcher acts on them; [] = leave the worker alone. `spent_week`: the metered `provider`'s
    cost rows this week (not this session's), which with the session's cost reaching its [spend.week_usd] figure parks."""
    out = []
    if state.get("rate_limited"):
        out.append("park: the provider refused for quota or credit")
    elif state.get("error") and not state.get("transient"):
        out.append(f"park: provider error: {state['error'][:120]}")
    cost = cost_of(state, spend, model)
    if spent_today + cost >= spend.day_usd:  # the only dollar cap: owner ruling B2 (2026-11-21) dropped the session cap
        out.append(f"park: today's spend {spent_today + cost:.2f} USD reached the cap {spend.day_usd:.2f}")
    elif is_metered(spend, provider) and spent_week + cost >= spend.week_usd.get(provider, 0):
        out.append(f"park: this week's {provider} spend {spent_week + cost:.2f} USD reached the cap {spend.week_usd.get(provider, 0):.2f}")
    elif state.get("context", 0) >= threshold(spend):
        out.append(f"handoff: context {state['context']} of {threshold(spend) if spend.handoff_tokens else spend.window}")
    if not state.get("idle") and state.get("started") and silent_for_s >= spend.silent_s:
        out.append(f"alert: no change in the session file for {int(silent_for_s)} s")
    return out

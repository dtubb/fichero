"""The watcher's judgement (dev-workflows.run.watch-tick): from what a session file says and what the journal has spent,
decide handoff, park, alert or nothing. Plain functions, no process control here; `builder run` (next slice) calls them.

Caps come from `harness.toml [spend]`; a missing cap or an unknown price REFUSES to start (audit 2026-11-01 H6)."""
from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

KEYS = {"window", "handoff_at", "session_usd", "day_usd", "silent_s", "prices"}


@dataclass(frozen=True)
class Spend:
    window: int = 200_000          # the model's context window, tokens
    handoff_at: float = 0.85       # hand off when the latest prompt reaches this share of the window
    session_usd: float = 0.0       # 0 = no cap declared = refuse to start
    day_usd: float = 0.0
    silent_s: int = 1800           # a session file unchanged this long while not idle = alert
    prices: dict = field(default_factory=dict)  # model name or prefix -> [usd per M input tokens, usd per M output tokens]


def load(root) -> Spend:
    """`<root>/harness.toml` [spend]; no table = the zero caps, which refuse. Unknown keys and bad prices refuse."""
    f = Path(root) / "harness.toml"
    t = tomllib.loads(f.read_text()).get("spend", {}) if f.is_file() else {}
    if unknown := sorted(set(t) - KEYS):
        raise ValueError(f"harness.toml [spend]: unknown keys {unknown}")
    prices = t.get("prices", {})
    for k, v in prices.items():
        if not (isinstance(v, list) and len(v) == 2 and all(isinstance(x, (int, float)) and x >= 0 for x in v)):
            raise ValueError(f"harness.toml [spend].prices.{k}: two numbers, usd per million input and output tokens")
    d = Spend()
    return Spend(window=int(t.get("window", d.window)), handoff_at=float(t.get("handoff_at", d.handoff_at)),
                 session_usd=float(t.get("session_usd", 0)), day_usd=float(t.get("day_usd", 0)),
                 silent_s=int(t.get("silent_s", d.silent_s)), prices=dict(prices))


def price_for(model: str, spend: Spend):
    """[in, out] for the model: an exact key, else the longest key the model name contains; None if unknown."""
    if model in spend.prices:
        return spend.prices[model]
    hits = sorted((k for k in spend.prices if k and k in model), key=len)
    return spend.prices[hits[-1]] if hits else None


def refusals(spend: Spend, kind: str, model: str) -> list[str]:
    """Every reason not to start a worker of this kind and model; empty = go."""
    out = []
    if spend.session_usd <= 0 or spend.day_usd <= 0:
        out.append("harness.toml [spend] must set session_usd and day_usd above 0: no cap, no start")
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


def assess(state: dict, spend: Spend, model: str, *, spent_today: float, silent_for_s: float) -> list[str]:
    """Decisions in the order the watcher acts on them; [] = leave the worker alone."""
    out = []
    if state.get("rate_limited"):
        out.append("park: the provider refused for quota or credit")
    elif state.get("error") and not state.get("transient"):
        out.append(f"park: provider error: {state['error'][:120]}")
    cost = cost_of(state, spend, model)
    if cost >= spend.session_usd:
        out.append(f"park: session spend {cost:.2f} USD reached the cap {spend.session_usd:.2f}")
    elif spent_today + cost >= spend.day_usd:
        out.append(f"park: today's spend {spent_today + cost:.2f} USD reached the cap {spend.day_usd:.2f}")
    if state.get("context", 0) >= spend.window * spend.handoff_at:
        out.append(f"handoff: context {state['context']} of {spend.window}")
    if not state.get("idle") and state.get("started") and silent_for_s >= spend.silent_s:
        out.append(f"alert: no change in the session file for {int(silent_for_s)} s")
    return out

"""`builder run`: one process starts a worker through the start path and watches its session file
(dev-workflows.run.worker-start-stop, run.watch-tick). Runs AS the worker user: the session file is in that user's home
and the start path refuses anyone else. Process control is a small `Procs` so a dry run swaps in fakes
(dev-workflows.rollout.dry-run); nothing here types into a pane."""
from __future__ import annotations

import dataclasses
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from fichero_builder import client, journal, models, session, watcher

HERE = Path(__file__).resolve().parent
START = client.scripts_dir() / "harness_start.py"


def slug(worktree) -> str:
    """Claude Code keeps a project's session files under ~/.claude/projects/<cwd with / as ->."""
    return str(Path(worktree).resolve()).replace("/", "-")


def session_dir(home, worktree) -> Path:
    return Path(home) / ".claude" / "projects" / slug(worktree)


def newest_session(home, worktree) -> Path | None:
    files = session.session_files(session_dir(home, worktree))
    return files[-1] if files else None


@dataclass
class Procs:
    """What the loop does to the world; a dry run replaces each one."""
    start: Callable[..., str]                 # (root, worktree, brief, name, model, tmux_session) -> pane id
    alive: Callable[[str], bool]              # pane id -> still there
    stop: Callable[[str], None]               # pane id -> gone
    read: Callable[[], dict | None]           # the newest session file parsed, or None before the first turn
    head: Callable[[], str] = lambda: ""      # the worktree's HEAD sha; a DONE line must name it and it must have moved
    tell: Callable[[str, str], None] = lambda pane, words: None  # a word to the worker (Pi: steer; Claude: the hook tells)
    redeliver: Callable[[str, str], None] | None = None  # a message that started no turn: Enter if its words sit in the input box, else typed again; None = tell
    sleep: Callable[[float], None] = time.sleep
    now: Callable[[], float] = time.time


def _start(root, worktree, brief, name, model, tmux_session, effort: str | None = None) -> str:
    r = subprocess.run([sys.executable, str(client.script(root, "harness_start.py", START)), "--root", str(root), "--worktree", str(worktree), "--brief", str(brief),
                        "--name", name, "--model", model, "--session", tmux_session, *(["--effort", effort] if effort else [])], capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(r.stderr.strip() or "harness_start failed")
    return r.stdout.strip()


def _alive(pane: str) -> bool:
    out = subprocess.run(["tmux", "list-panes", "-a", "-F", "#{pane_id}"], capture_output=True, text=True).stdout.split()
    return pane in out


def _stop(pane: str, grace_s: float = 10.0) -> None:
    """TERM the pane's process group, wait the grace, then kill the pane (an interactive session never exits on its own)."""
    pid = subprocess.run(["tmux", "display-message", "-p", "-t", pane, "#{pane_pid}"], capture_output=True, text=True).stdout.strip()
    if pid.isdigit():
        subprocess.run(["kill", "-TERM", "--", f"-{pid}"], capture_output=True)
        for _ in range(int(grace_s * 10)):
            if not _alive(pane):
                return
            time.sleep(0.1)
    subprocess.run(["tmux", "kill-pane", "-t", pane], capture_output=True)


def _unsent(pane: str, words: str) -> bool:
    """The words still sit in the pane's input line (the ❯ box), i.e. the Enter was swallowed."""
    r = subprocess.run(["tmux", "capture-pane", "-p", "-t", pane], capture_output=True, text=True)
    out = getattr(r, "stdout", "") or ""
    box = next((ln for ln in reversed(out.splitlines()) if "❯" in ln), "")
    return bool(words) and words[:40] in box


def _tell(pane: str, words: str) -> None:
    """Into a Claude pane: the words literally, then Enter as its own call (one send-keys with both loses the Enter).
    #6589 2026-11-19: Claude Code takes a long typed message as a paste and swallows the first Enter, so briefs sat
    unsent for hours; the Enter is sent again (up to 3 times) while the words are still in the input line."""
    subprocess.run(["tmux", "send-keys", "-t", pane, "-l", words], capture_output=True)
    time.sleep(0.5)
    subprocess.run(["tmux", "send-keys", "-t", pane, "Enter"], capture_output=True)
    for _ in range(3):
        time.sleep(2)
        if not _unsent(pane, words):
            return
        subprocess.run(["tmux", "send-keys", "-t", pane, "Enter"], capture_output=True)


def _redeliver(pane: str, words: str) -> None:
    """The words still sit in the input line: only Enter. Not there (swallowed, or never typed): the words again."""
    if _unsent(pane, words):
        subprocess.run(["tmux", "send-keys", "-t", pane, "Enter"], capture_output=True)
    else:
        _tell(pane, words)


def _head(worktree) -> str:
    return subprocess.run(["git", "-C", str(worktree), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()


def real_procs(home, worktree) -> Procs:
    def read():
        f = newest_session(home, worktree)
        return session.parse_session(f) if f else None
    return Procs(start=_start, alive=_alive, stop=_stop, read=read, head=lambda: _head(worktree), tell=_tell, redeliver=_redeliver)


WAITING = re.compile(r"^WAITING:[ \t]*(\S.*)$", re.M)  # #6855: a worker's end line when it needs an answer, not more work
DONE = re.compile(r"^DONE ([0-9a-f]{7,40})\b", re.M)  # the brief's end line: DONE <short sha of the branch head>
HANDOFF_READY = "HANDOFF READY"
PART_LEFT = re.compile(r"(?m)^PART (\d+) left:[ \t]*(\S.*)$")  # a batch's end lines for parts the worker did not finish: PART 2 left: why
REDELIVER_S, REDELIVERIES = 60.0, 3  # a message with no turn started after this long is delivered again, up to this many times


def register(name: str, worktree, handoff, model: str, window: int, tmux_session: str, reg_dir=None, handoff_tokens: int = 0, feed=None) -> Path:
    """The registry entry the in-session handoff hook reads (scripts/harness_handoff_hook.py): with it the hook tells the
    worker at 85 % and nudges an idle one on; `successor: watcher` leaves ending and the successor to this loop."""
    d = Path(reg_dir or os.environ.get("FICHERO_HARNESS_REG") or Path.home() / ".claude" / "builders")
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{name}.json"
    p.write_text(json.dumps({"worktree": str(worktree), "handoff": str(handoff), "model": model, "window": window, "handoff_tokens": handoff_tokens,
                             "session": tmux_session, "successor": "watcher", **({"feed": str(feed), "turn_file": str(d / f"{name}.turn.json")} if feed else {})}, indent=1))
    return p


def hook_turn(name: str, since: float, reg_dir=None) -> str:
    """The last message of a turn the Stop hook wrote (`<name>.turn.json` in the registry folder: at, text) after `since`; '' when none."""
    d = Path(reg_dir or os.environ.get("FICHERO_HARNESS_REG") or Path.home() / ".claude" / "builders")
    try:
        d = json.loads((d / f"{name}.turn.json").read_text())
        return str(d["text"]) if float(d["at"]) >= since else ""
    except (OSError, ValueError, KeyError, TypeError):
        return ""


def reading_of(first_commit: dict | None) -> dict:
    return first_commit or {"turns_before_first_commit": None, "tokens_before_first_commit": None}


DONE_INSTRUCTION = "When every item is committed, end your turn with the exact line DONE <short sha of the branch head>."


def with_done_line(brief, worktree, name: str):
    """A brief that does not say how to end (a hand brief; cluster and successor briefs do) is copied into the worktree as
    `.builder-brief-<name>-1.txt` with the DONE instruction appended, and the worker is started on the copy."""
    p = Path(brief)
    if not p.is_file() or "DONE <" in p.read_text():
        return p
    copy = Path(worktree) / f".builder-brief-{name}-1.txt"
    copy.write_text(p.read_text().rstrip("\n") + "\n\n" + DONE_INSTRUCTION + "\n")
    return copy


def successor_brief(name: str, gen: int, worktree, handoff) -> str:
    """The successor's whole brief: read the handoff, carry on, same rules, same end line (dev-workflows.worker.handoff)."""
    return (f"You succeed long-running worker {name} (generation {gen}). Work in {worktree}. Read {handoff} first, then continue "
            f"the work it lists, in order, under the rules it gives. When told your context is at 85%, finish the step, commit, "
            f"update {handoff}, and end your turn with the exact line {HANDOFF_READY}. When every item is done, end with the DONE line.")


def rules_of(root, rules, role: str) -> watcher.Spend:
    """The caps now (local.perf.caps-reread-each-tick, #6851): from `rules` (the JSON the queue's loop publishes into the feed,
    `{"spend": <raw [spend]>, "models": <[models]>}`) when given, else from `<root>/harness.toml`; with a role, its window."""
    if rules:
        doc = json.loads(Path(rules).read_text())
        spend, mdl = watcher.parse(doc["spend"]), doc["models"]
    else:
        spend, mdl = watcher.load(root), models.load(root) if role else {}
    if role:  # a lane's model role: its window, and the share of it where the handoff fires, are the role's (the absolute mark is the default role's)
        spend = dataclasses.replace(spend, window=models.for_role(mdl, role).context, handoff_tokens=0)
    return spend


def _live(name: str, usd: float | None) -> Path:
    """This run's running cost for the other runs' day cap (#6871), rewritten whole each tick; None removes it."""
    f = journal.STATE / "live" / f"{name}.json"
    if usd is None:
        f.unlink(missing_ok=True)
        return f
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps({"usd": round(usd, 4), "day": time.strftime("%Y-%m-%d")}))
    tmp.replace(f)
    return f


def _spent_week(provider: str) -> float:
    """This ISO week's journal cost rows of `provider` (local.spend.metered-provider-needs-a-cap)."""
    return watcher.spent_week(journal.read(), provider, time.strftime("%Y-%m-%dT%H:%M:%S"))


def provider_of(root, rules, role: str, default: str) -> str:
    """The provider a run bills to: its [models] role's when it has one, else `default` (claude-code for a Claude session)."""
    if not role:
        return default
    mdl = json.loads(Path(rules).read_text())["models"] if rules else models.load(root)
    return models.for_role(mdl, role).provider


def _spent_today(name: str) -> float:
    """Today's journal cost rows plus every other live session's running cost (#6871)."""
    today = time.strftime("%Y-%m-%d")  # the journal stamps rows with the wall clock
    return watcher.spent_today(journal.read(), today) + watcher.live_spend(journal.STATE / "live", today, name, time.time())


def run(root, worktree, brief, *, name: str, model: str = "sonnet", kind: str = "claude", tmux_session: str = "harness",
        tick_s: float = 30.0, procs: Procs, out=print, done=DONE, handoff=None, max_generations: int = 20, feed=None, seq: int = 0, role: str = "",
        rules=None, provider: str = "", attach: str = "", outstanding: bool = True, base_sha: str = "") -> str:
    """Start, then watch until the worker is done (idle, its last text ends with the brief's `DONE <sha>` line, and the
    worktree's HEAD is that sha and has moved from the start: a worker's words alone never end a run),
    parked (a cap or a provider refusal) or gone. Returns the end as a word.
    Handoff: the in-session hook tells the worker at 85 %; when the worker is then idle with HANDOFF READY in its last text,
    the loop ends it (TERM, grace, kill) and starts a successor through the same start path with a brief that names the
    handoff file (`<worktree>/HANDOFF.md` unless given); the successor is the same name, generation plus one.
    `feed` (the queue's long-running lane, a folder only the owner writes): a good DONE ends the step, not the session: one
    `step` row (task, seq, sha, moved) for the owner, then the worker idles until `msg-<seq+1>.txt` appears and is typed into
    the same pane, or `stop` appears (end "lane-done").
    `rules` (the queue's `<feed>/rules.json`): the caps are read from it at every tick, never from `root`; an unreadable read keeps
    the last figures and says so once.
    `attach` (local.run.sessions-survive-watchers): watch a live session in that pane instead of starting one (its watcher died; the
    session did not). `outstanding`: its step is still out, so a DONE line already on screen is read at the first idle tick;
    `base_sha`: the head the step was sent at, so its commits count as moved."""
    spend = rules_of(root, rules, role)
    provider = provider_of(root, rules, role, provider or ("claude-code" if kind == "claude" else ""))
    effort = models.for_role(json.loads(Path(rules).read_text())["models"] if rules else models.load(root), role).effort if role else None
    if effort and kind != "claude":  # the adapter cannot take a level: a question, never a silent drop
        out(f"builder run refuses: [models].{role} asks for effort {effort!r}, which a {kind} session cannot take")
        return "refused"
    xs = {"effort": effort} if effort else {}  # passed and journalled only when a row sets it: no row, the call and the row are as before
    label = {"role": role, **xs} if role else {}  # the journal rows of a role's worker say which role
    bad = watcher.refusals(spend, kind, model, provider)
    if bad:
        for b in bad:
            out("builder run refuses: " + b)
        return "refused"
    if (spent := _spent_today(name)) >= spend.day_usd:
        journal.append("watch", task=name, what=f"park: today's spend {spent:.2f} USD reached the cap {spend.day_usd:.2f} before the start")
        out(f"{name}: parked before the start, today's spend {spent:.2f} of {spend.day_usd:.2f} USD")
        return "parked"
    if watcher.is_metered(spend, provider) and (wk := _spent_week(provider)) >= spend.week_usd.get(provider, 0):
        journal.append("watch", task=name, what=f"park: this week's {provider} spend {wk:.2f} USD reached the cap {spend.week_usd[provider]:.2f} before the start")
        out(f"{name}: parked before the start, this week's {provider} spend {wk:.2f} of {spend.week_usd[provider]:.2f} USD")
        return "parked"
    handoff = Path(handoff) if handoff else Path(worktree) / "HANDOFF.md"
    register(name, worktree, handoff, model, spend.window, tmux_session, handoff_tokens=watcher.threshold(spend), feed=feed)
    gen = 1
    base = base_sha or procs.head()
    pane = attach or procs.start(root, worktree, with_done_line(brief, worktree, name), name, model, tmux_session, **xs)
    journal.append("worker", task=name, pane=pane, model=model, kind=kind, worktree=str(worktree), generation=gen, **label, **({"attached": True} if attach else {}))
    started = last_change = procs.now()
    seen = None
    told: set[str] = set()
    state: dict = {}
    base0, first_commit = base, None
    rules_bad = False  # the last read of the rules failed (one alert per spell)
    ended_ticks = 0  # ticks a delivered message's turn ended with no DONE, WAITING or handoff line (local.run.turn-ended-without-done-alerts)
    unsaid, nudged = 0, False  # ticks idle with the branch moved and no good DONE line (defect 2: a worker that commits and never says it)
    outstanding, sent_turn = (outstanding if attach else True), -1  # feed: a step is out; and the turn it went in at, so the last step's DONE text is not read as this one's
    # #6589 2026-11-20: a DONE counts only if printed after THIS message was delivered: a prompt arrived since it was sent (the session
    # file's `prompts`; a state without the count falls back to the turn count) and the last text is not the one on screen when it went out
    sent = {"prompts": -1, "text": "", "at": started, "words": "", "again": 0}

    def step_done(sha: str, moved: bool, **more) -> None:
        nonlocal outstanding, base, unsaid, nudged, ended_ticks
        journal.append("step", task=name, seq=seq, sha=sha, moved=moved, context=state.get("context", 0), window=spend.window, model=model,
                       **({"left": [{"part": int(n), "why": w[:300]} for n, w in PART_LEFT.findall(state.get("last_text", ""))]} if PART_LEFT.search(state.get("last_text", "")) else {}), **more)
        out(f"{name}: step {seq} {'done at ' + sha[:9] if moved else 'ended with no commit'}")
        outstanding, base, unsaid, nudged, ended_ticks = False, sha, 0, False, 0
    while True:
        procs.sleep(tick_s)
        now = procs.now()
        st = procs.read()
        if st is not None:
            key = (st.get("turns"), st.get("tokens"), st.get("idle"))
            if key != seen:
                seen, last_change = key, now
            state = st
        if first_commit is None and base0 and (now_head := procs.head()) and now_head != base0:  # the reading metric: what it took to get to a first commit
            first_commit = {"turns_before_first_commit": state.get("turns", 0), "tokens_before_first_commit": state.get("tokens", 0)}
            journal.append("reading", task=name, generation=gen, **first_commit)
        if not procs.alive(pane):
            end = "gone"
            break
        try:
            spend, rules_bad = rules_of(root, rules, role), False
        except (OSError, ValueError, KeyError, models.Question) as e:
            if not rules_bad:
                journal.append("watch", task=name, what=f"alert: rules unreadable: {e}"[:300])
                out(f"{name}: rules unreadable, keeping the last caps: {e}")
            rules_bad = True
        try:
            _live(name, watcher.cost_of(state, spend, model))
        except OSError as e:  # the other runs miss this run's figure for a tick; the watch goes on
            journal.append("watch", task=name, what=f"alert: live spend not written: {e}"[:300])
        decisions = watcher.assess(state, spend, model, spent_today=_spent_today(name), silent_for_s=now - last_change, provider=provider,
                                   spent_week=_spent_week(provider) if watcher.is_metered(spend, provider) else 0.0)
        for d in decisions:
            kind_of = d.split(":")[0]  # one row per kind of decision, not one per tick
            if kind_of not in told:
                journal.append("watch", task=name, what=d)
                out(f"{name}: {d}")
                told.add(kind_of)
                if kind_of == "handoff":  # the watcher delivers the word itself where it can (Pi); Claude's hook does it at the context mark
                    procs.tell(pane, f"Hand off now ({d.split(': ', 1)[1]}). Finish this step, commit, update {handoff.name} so a successor "
                                     f"can continue without asking, and end your turn with the exact line {HANDOFF_READY}.")
        if any(d.startswith("park") for d in decisions):
            procs.stop(pane)
            end = "parked"
            break
        if feed is not None:
            if (Path(feed) / "stop").exists():
                procs.stop(pane)
                end = "lane-done"
                break
            nxt = Path(feed) / f"msg-{seq + 1}.txt"
            if not outstanding and nxt.exists():
                seq, base, sent_turn, outstanding = seq + 1, procs.head(), state.get("turns", 0), True
                words = f"Read {nxt} and do what it says; end your turn with the DONE line it names."
                sent = {"prompts": state.get("prompts", -1), "text": state.get("last_text", ""), "at": now, "words": words, "again": 0}
                journal.append("watch", task=name, what=f"sent: message {seq}")
                procs.tell(pane, words)
        delivered = state.get("prompts", 0) > sent["prompts"] if "prompts" in state else state.get("turns", 0) > sent_turn
        if outstanding and sent["words"] and not delivered and now - sent["at"] >= REDELIVER_S * (sent["again"] + 1) and sent["again"] < REDELIVERIES:
            sent["again"] += 1  # the Enter was swallowed or the paste lost: the loop delivers again, for any session
            journal.append("watch", task=name, what=f"redeliver: message {seq} started no turn in {int(now - sent['at'])} s (attempt {sent['again']})")
            (procs.redeliver or procs.tell)(pane, sent["words"])
        idle = state.get("idle") and outstanding and state.get("turns", 0) > sent_turn and delivered and state.get("last_text", "") != sent["text"]
        m = done.search(state.get("last_text", "")) if idle else None
        head = procs.head() if idle else ""
        said = bool(m and head and head.startswith(m.group(1)))
        if idle and not m and feed is not None and (w := WAITING.search(state.get("last_text", ""))):
            step_done(head, head != base, waiting=w.group(1)[:500])  # #6855: the queue raises the ask alert from this row; the session stays
            continue
        ended = (hook_turn(name, sent["at"]) or (state.get("last_text", "") if idle else "")) if feed is not None and outstanding and delivered else ""
        if ended and not DONE.search(ended) and not WAITING.search(ended) and HANDOFF_READY not in ended:
            hd = procs.head()
            tail, ended_ticks = ended.strip()[-300:], ended_ticks + 1
            if ended_ticks == 1:
                journal.append("watch", task=name, what=f"turn-ended-no-done: {tail}")
                if tail.endswith("?"):  # a question: the same ask alert as WAITING, answered by send-back into this session
                    step_done(hd, hd != base, waiting=tail)
                    continue
                words = f"Your turn ended without the DONE line: end your turn with the exact line DONE {hd[:7]}"
                journal.append("watch", task=name, what=f"nudge: {words}")
                procs.tell(pane, words)
                sent["at"] = now  # the hook's file from before the nudge says nothing about the reply
            elif ended_ticks >= 3:
                step_done(hd, hd != base, waiting=f"the turn ended with no DONE or WAITING line: {tail}")
                continue
        elif ended_ticks:
            ended_ticks = 0  # a turn that went on after the nudge starts the count again
        unsaid = unsaid + 1 if head and head != base and not said and not ended_ticks else 0
        if unsaid == 2 and not nudged:
            words = f"Your branch has commits and your turn ended without the DONE line: end your turn with the exact line DONE {head[:7]}"
            journal.append("watch", task=name, what=f"nudge: {words}")
            out(f"{name}: nudged for the DONE line ({head[:7]})")
            procs.tell(pane, words)
            unsaid, nudged = 0, True
        elif unsaid >= 2:  # one nudge only: a reply with no line must not reset it into a nudge loop
            journal.append("watch", task=name, what=f"done-unsaid: the branch is at {head[:9]}, idle, no DONE line after a nudge")
            if feed is not None:
                step_done(head, True, unsaid=True)
                continue
            procs.stop(pane)
            end = "done-unsaid"
            break
        if said and feed is not None:
            step_done(head, head != base)
        elif m:
            if said and head != base:
                procs.stop(pane)
                end = "done"
                break
            if "false-done" not in told:  # the worker's word is not the record: the branch did not move, or names another sha
                journal.append("watch", task=name, what=f"false done: the branch head is {head[:9] or 'unknown'}, the DONE line says {m.group(1)}")
                out(f"{name}: false done ({m.group(1)} vs {head[:9]})")
                told.add("false-done")
        if state.get("idle") and HANDOFF_READY in state.get("last_text", ""):
            if gen >= max_generations:
                procs.stop(pane)
                end = "parked"
                journal.append("watch", task=name, what=f"park: {gen} generations, the cap")
                break
            procs.stop(pane)
            journal.append("cost", task=name, model=model, provider=provider, usd=round(watcher.cost_of(state, spend, model), 4),
                           tokens=state.get("tokens", 0), turns=state.get("turns", 0), seconds=int(now - started), end="handoff",
                           generation=gen, **label, **reading_of(first_commit))
            _live(name, 0.0)  # the cost row now holds it; the successor starts from nothing
            gen += 1
            b = Path(worktree) / f".builder-brief-{name}-{gen}.txt"
            b.write_text(successor_brief(name, gen, worktree, handoff))
            pane = procs.start(root, worktree, b, name, model, tmux_session, **xs)
            journal.append("worker", task=name, pane=pane, model=model, kind=kind, worktree=str(worktree), generation=gen, **label)
            out(f"{name}: handoff, generation {gen} started")
            started = last_change = procs.now()
            seen, state, told, unsaid, nudged, sent_turn = None, {}, set(), 0, False, -1
            sent = {"prompts": -1, "text": "", "at": procs.now(), "words": "", "again": 0}
            base0, first_commit = procs.head(), None
            continue
    journal.append("cost", task=name, model=model, provider=provider, usd=round(watcher.cost_of(state, spend, model), 4),
                   tokens=state.get("tokens", 0), turns=state.get("turns", 0), seconds=int(procs.now() - started), end=end,
                   generation=gen, **label, **reading_of(first_commit))
    _live(name, None)
    out(f"{name}: {end}")
    return end

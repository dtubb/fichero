#!/usr/bin/env python3
"""Fail when a WARNING-or-worse template repeats past a ceiling in an engine.log (`engine.silent.scan-script`).

One embedding warning was written 380,611 times into a tester's log while the app looked fine. Pure: stdlib only, no
network, streams the file. A "... — repeated N times in the last minute" line (the log collapse) carries the raw
template (`%s` where the id and cause were); its N is added to the written template it matches (the most-written one when
several do), or counted alone when none was written.

    python scripts/scan_engine_log.py engine.log [engine.log.1 ...] [--ceiling 50] [--allow REGEX ...] [--level WARNING]

Exit 0 clean, 1 ONLY when an unallowed template is over the ceiling, 2 for anything else (bad arguments, a bad --allow
regex, not a readable log, a crash).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

LINE = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d),\d+ - (\S+) - (DEBUG|INFO|WARNING|ERROR|CRITICAL) - (.*)$")
DATED = re.compile(r"^\d{4}-\d\d-\d\d")  # starts like a log line; if LINE misses it, the format changed
SEVERE = re.compile(r"\b(WARNING|ERROR|CRITICAL)\b")  # a non-engine-format line that still says it is a problem
REPEATED = re.compile(r" — repeated (\d+) times in the last minute$")
_FORMAT = re.compile(r"%(?:\([^)]*\))?[-+ #0]*(?:\d+|\*)?(?:\.(?:\d+|\*))?[sdirfxXeEgGc]")
LEVELS = {"WARNING": 1, "ERROR": 2, "CRITICAL": 3}
_SUBS = [(re.compile(p), r) for p, r in (
    (r"\b[0-9a-fA-F]{8}-[0-9a-fA-F-]{27}\b", "<uuid>"),
    (r"\b(?:[0-9a-fA-F]{12,}|(?=[0-9a-fA-F]*\d)[0-9a-fA-F]{8,})\b", "<hex>"),
    # A quoted path runs to its closing quote; an unquoted one, which may hold spaces, runs to the end of the message.
    # ponytail: that can MERGE two different failures that share a prefix (a false FAIL, never a false pass, and an
    # --allow on "<path>" then hides both), and a path holding an apostrophe leaks its tail. Upgrade: a per-site path rule.
    (r"(?<![\w<>])/(?=[\w.~-])[^'\"]*", "<path>"), (r"\d+(\.\d+)?", "<n>"))]


def normalise(message: str) -> str:
    for pattern, replacement in _SUBS:
        message = pattern.sub(replacement, message[:300])
    return message


def scan(paths: list[Path], level: str) -> dict[str, list]:
    """template -> [count, first, last, level, loggers, group], summed over the files (a rotated `engine.log.1` is one
    log; an empty one is skipped). `group` holds the other templates a collapse summary could have belonged to.
    Raises ValueError when no file has a log line, or a file's lines mostly miss the engine format."""
    floor = LEVELS[level]
    found: dict[str, list] = {}
    collapsed: list[tuple[str, int, str, str, str]] = []
    if not sum(_read(path, floor, found, collapsed) for path in paths):
        raise ValueError(f"{', '.join(map(str, paths))} has no engine log lines")
    for item in collapsed:
        _fold(found, *item)
    return found


def _read(path: Path, floor: int, found: dict[str, list], collapsed: list) -> bool:
    """True when the file had log lines; an empty file (a just-rotated log) is False without being an error."""
    parsed = parsed_severe = unparsed = unparsed_severe = 0
    with path.open(encoding="utf-8", errors="replace") as handle:
        for raw in handle:
            match = LINE.match(raw.rstrip("\n"))
            if not match:
                unparsed += bool(DATED.match(raw))
                unparsed_severe += bool(SEVERE.search(raw))
                continue
            parsed += 1
            when, logger, lvl, message = match.groups()
            if LEVELS.get(lvl, 0) < floor:
                continue
            parsed_severe += 1
            held = REPEATED.search(message)
            if held:
                collapsed.append((message[: held.start()], int(held.group(1)), when, lvl, logger))
                continue
            entry = found.setdefault(normalise(message), [0, when, when, lvl, set(), set()])
            entry[0] += 1
            entry[1], entry[2] = min(entry[1], when), max(entry[2], when)
            entry[4].add(logger)
    if not parsed:
        if path.stat().st_size == 0:
            return False
        raise ValueError(f"{path} has no engine log lines")
    # A format change must fail loudly, not read as a clean log: dated lines, or lines saying WARNING/ERROR, that miss
    # the engine format must not outnumber the ones that match.
    if unparsed > parsed or unparsed_severe > parsed_severe + 10:
        raise ValueError(f"{path}: {max(unparsed, unparsed_severe)} lines miss the engine log format, {parsed} match")
    return True


def _fold(found: dict[str, list], raw: str, extra: int, when: str, lvl: str, logger: str) -> None:
    """Add a collapse summary's N to a written template of the same logger that its raw `%s` template stands for.

    Matched on the text before the first (or after the last) format spec, so an unquoted path's swallowed tail cannot
    split them. When several templates match, the count goes to the most-written one and `group` remembers the rest, so
    an --allow must cover all of them to hide it."""
    pieces = _FORMAT.split(raw)
    head, tail = normalise(pieces[0]) if pieces[0].strip() else "", normalise(pieces[-1]) if pieces[-1].strip() else ""
    matches = [
        t for t, e in found.items()
        if logger in e[4] and ((head and t.startswith(head)) or (not head and tail and t.endswith(tail)))
    ]
    key = max(matches, key=lambda t: found[t][0]) if matches else normalise(raw)
    entry = found.setdefault(key, [0, when, when, lvl, {logger}, set()])
    entry[0] += extra
    entry[2] = max(entry[2], when)
    entry[5].update(matches)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("log", type=Path, nargs="+", help="one or more files, e.g. engine.log engine.log.1")
    parser.add_argument("--ceiling", type=int, default=50)
    parser.add_argument("--allow", action="append", default=[], metavar="REGEX")
    parser.add_argument("--level", choices=sorted(LEVELS), default="WARNING")
    args = parser.parse_args(argv)
    try:
        found = scan(args.log, args.level)
    except (OSError, ValueError) as exc:
        print(f"scan_engine_log: {exc}", file=sys.stderr)
        return 2
    try:
        allowed = [re.compile(a) for a in args.allow]
    except re.error as exc:
        parser.error(f"--allow is not a regex: {exc}")  # exits 2
    over = sorted(
        ((e[0], t, e[1], e[2], e[3]) for t, e in found.items()
         if e[0] > args.ceiling and not all(any(a.search(x) for a in allowed) for x in {t} | e[5])),
        reverse=True,
    )
    for count, template, first, last, lvl in over:
        print(f"{count:>9}  {lvl:<8} {first} .. {last}  {template[:160]}")
    if over:
        print(f"FAIL: {len(over)} template(s) repeat more than {args.ceiling} times", file=sys.stderr)
        return 1
    print(f"ok: no {args.level}+ template repeats more than {args.ceiling} times ({len(found)} distinct)")
    return 0


def _entry() -> int:
    sys.stdout.reconfigure(errors="backslashreplace")  # a non-UTF-8 byte in a template must not crash the report
    try:
        return main()
    except Exception as exc:  # noqa: BLE001 -- exit 1 is reserved for "over the ceiling"
        print(f"scan_engine_log: crashed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(_entry())

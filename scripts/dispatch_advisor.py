#!/usr/bin/env python3
"""Issue-complexity advisor for worker selection.

This helper classifies a GitHub issue as `mini`, `regular`, or `frontier` using
simple heuristics over labels, title, and body keywords. It advises a worker
class rather than a token budget: a live session-token budget is not reliably
readable from a standalone script, so the manager combines this advice with its
own remaining budget.

Signals:
  - mini: tooling, docs, typo, line-wrap, guardrail, rename
  - regular: refactor, store, endpoint
  - frontier: new-architecture, cross-cutting, EPIC

Usage:
    scripts/dispatch_advisor.py 1954
    scripts/dispatch_advisor.py "Fix tooltip guardrail for toolbar buttons"
    scripts/dispatch_advisor.py --help
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class IssueSignals:
    title: str
    body: str
    labels: tuple[str, ...]


MINI_MARKERS = ("tooling", "docs", "doc", "typo", "line-wrap", "line wrap", "guardrail", "rename")
REGULAR_MARKERS = ("refactor", "store", "endpoint")
FRONTIER_MARKERS = ("new-architecture", "new architecture", "cross-cutting", "cross cutting", "epic")

RECOMMENDATIONS = {
    "mini": "codex gpt-5.4-mini or Haiku",
    "regular": "codex gpt-5.4 or Sonnet",
    "frontier": "codex gpt-5.5 or Opus",
}


def _haystack(*parts: str) -> str:
    return " ".join(part for part in parts if part).lower()


def _matches(text: str, markers: Iterable[str]) -> list[str]:
    hits: list[str] = []
    for marker in markers:
        if marker.lower() in text:
            hits.append(marker)
    return hits


def classify(signals: IssueSignals) -> tuple[str, list[str]]:
    text = _haystack(signals.title, signals.body, *signals.labels)

    frontier_hits = _matches(text, FRONTIER_MARKERS)
    if frontier_hits:
        return "frontier", frontier_hits

    regular_hits = _matches(text, REGULAR_MARKERS)
    if regular_hits:
        return "regular", regular_hits

    mini_hits = _matches(text, MINI_MARKERS)
    if mini_hits:
        return "mini", mini_hits

    return "regular", ["defaulted to regular when no strong mini/frontier markers were found"]


def load_issue(issue_ref: str) -> IssueSignals:
    gh = subprocess.run(
        [
            "gh",
            "issue",
            "view",
            issue_ref,
            "--json",
            "title,body,labels,number,url",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(gh.stdout)
    labels = tuple(label["name"] for label in payload.get("labels", []))
    return IssueSignals(
        title=payload.get("title", ""),
        body=payload.get("body", ""),
        labels=labels,
    )


def print_help() -> None:
    print(__doc__.rstrip())


def main() -> int:
    if any(arg in ("-h", "--help") for arg in sys.argv[1:]):
        print_help()
        return 0

    args = [arg for arg in sys.argv[1:] if not arg.startswith("-")]
    if not args:
        print_help()
        return 2

    input_ref = " ".join(args)
    issue_ref = args[0] if len(args) == 1 and re.fullmatch(r"\d+", args[0]) else None

    if issue_ref is not None:
        try:
            signals = load_issue(issue_ref)
        except (subprocess.CalledProcessError, FileNotFoundError, json.JSONDecodeError) as exc:
            print(f"dispatch_advisor: failed to load issue {issue_ref}: {exc}", file=sys.stderr)
            return 1
        ref_label = f"#{issue_ref}"
    else:
        signals = IssueSignals(title=input_ref, body="", labels=())
        ref_label = "title"

    bucket, hits = classify(signals)
    worker = RECOMMENDATIONS[bucket]

    print(f"{ref_label}: {bucket}")
    print(f"recommended worker: {worker}")
    print(f"title: {signals.title}")
    if signals.labels:
        print(f"labels: {', '.join(signals.labels)}")
    if hits:
        print(f"signals: {', '.join(hits)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

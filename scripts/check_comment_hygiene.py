#!/usr/bin/env python3
"""Comment hygiene guardrail.

Rule: no commented-out code blocks and TODO/FIXME must cite an issue; see agents/ROADMAP.md.

Flags 3+ consecutive ordinary comment lines that look like Swift code, plus
TODO/FIXME comments without a #NNN issue reference. Doc comments, MARK headers,
and architecture/rule reminder prose are ignored. KNOWN_VIOLATIONS is today's
cleanup backlog, so the script passes today and fails only on new offenders.

Usage:
    scripts/check_comment_hygiene.py
    scripts/check_comment_hygiene.py --list
    scripts/check_comment_hygiene.py --help
"""
from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SWIFT_DIR = ROOT / "fichero" / "fichero"
RULE_DOC = "agents/ROADMAP.md"

KNOWN_VIOLATIONS: dict[str, str] = {
    # One entry, and it is the guard's OTHER rule: an untracked `TODO:` with no issue number.
    # The fourteen this replaced were all the code-like rule firing on prose; eleven of them
    # said so ("false positive (prose)"). Tightening the rule cleared thirteen at once and
    # flagged nothing new (2026-09-27). If this grows again, read the block before adding a
    # line — an allowlist that is mostly workaround is measuring the guard, not the code.
    "fichero/fichero/Views/Library/DocumentPickerSheet.swift#727654079f": (
        "#1916 baseline — TODO with no issue: navigate to the batches sidebar and execute "
        "a batch with SSE streaming"
    ),
}
_TODO = re.compile(r"\b(?:TODO|FIXME)\b")
_ISSUE = re.compile(r"#\d+")
#: A comment line is code-like when it reads as a STATEMENT, not merely because it contains a
#: keyword or a brace somewhere. The old rule matched any of `= ; { }` anywhere and any keyword
#: after whitespace, which flags this codebase's own documented commenting style: prose that
#: cites identifiers, names a caller by `File.swift:169-181`, ends a sentence in a parenthetical,
#: lists enum cases as `.widescreen → …`, or uses the words "for", "class" or "import" in an
#: ordinary sentence. Eleven of the fourteen allowlist entries said exactly that in prose —
#: "false positive (prose)" — which is eleven people writing down the missing rule instead of
#: adding it. Tightened 2026-09-27: 15 offenders -> 1, and nothing newly flagged.
#:
#: Validated in both directions by test, because a hygiene rule that cannot tell a commented-out
#: `store.reload()` from a sentence about reloading is worse than none: it teaches people to
#: stop explaining their decisions.
_CODEISH_KEYWORD_START = re.compile(
    r"^(?:@|\}|func|let|var|if|else|guard|for|while|switch|case|return|import|struct|class|enum|"
    r"try|await|async|public|private|internal|final|static|override|extension|init|deinit|self\b)"
)
#: `{`, `}` and `;` only. NOT `)` or `,`: prose here ends in a parenthetical constantly.
_CODEISH_STATEMENT_END = re.compile(r"[{};]\s*$")
_CODEISH_ASSIGN = re.compile(r"^[A-Za-z_][A-Za-z0-9_.\[\]]*\s*(?:=|\+=|-=)\s*\S")
_CODEISH_CALL = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*\s*\(")


class _CodeishRule:
    """Kept regex-shaped (`.search`) so the two call sites in this module read unchanged."""

    @staticmethod
    def search(line: str) -> bool:
        stripped = line.strip()
        if not stripped:
            return False
        return bool(
            _CODEISH_KEYWORD_START.match(stripped)
            or _CODEISH_STATEMENT_END.search(stripped)
            or _CODEISH_ASSIGN.match(stripped)
            or _CODEISH_CALL.match(stripped)
        )


_CODEISH = _CodeishRule
_RULE_PROSE = re.compile(
    r"\b(?:rule|guardrail|architecture|default|workaround|because|without|should|must|TODO: convert port\\.default_ if needed)\b",
    re.IGNORECASE,
)


def _normalized_snippet(snippet: str) -> str:
    return re.sub(r"\s+", " ", snippet).strip()


def _signature_key(rel: str, snippet: str) -> str:
    digest = hashlib.sha1(_normalized_snippet(snippet).encode("utf-8")).hexdigest()[:10]
    return f"{rel}#{digest}"


def _window_snippet(lines: list[str], line_no: int, radius: int = 1) -> str:
    start = max(0, line_no - 1 - radius)
    end = min(len(lines), line_no + radius)
    return "\n".join(lines[start:end])


def _ordinary_comment(line: str) -> str | None:
    stripped = line.lstrip()
    if not stripped.startswith("//"):
        return None
    if stripped.startswith("///") or stripped.startswith("// MARK:") or stripped.startswith("// TODO(#"):
        return None
    return stripped[2:].strip()


def _flush_block(
    path: Path,
    start_line: int,
    block: list[str],
    found: dict[str, str],
) -> None:
    if len(block) < 3:
        return
    codeish = [line for line in block if _CODEISH.search(line)]
    prose = [line for line in block if _RULE_PROSE.search(line)]
    if len(codeish) >= 3 and len(prose) < len(block):
        rel = path.relative_to(ROOT).as_posix()
        found[_signature_key(rel, "\n".join(block))] = "3+ consecutive code-like comment lines"


def scan() -> dict[str, str]:
    found: dict[str, str] = {}
    for path in sorted(SWIFT_DIR.rglob("*.swift")):
        try:
            lines = path.read_text(errors="ignore").splitlines()
        except OSError:
            continue
        rel = path.relative_to(ROOT).as_posix()
        block: list[str] = []
        block_start = 0
        for line_no, line in enumerate(lines, 1):
            comment = _ordinary_comment(line)
            if comment is None:
                _flush_block(path, block_start, block, found)
                block = []
                block_start = 0
                continue

            if _TODO.search(comment) and not _ISSUE.search(comment):
                found[_signature_key(rel, _window_snippet(lines, line_no))] = comment

            if _CODEISH.search(comment):
                if not block:
                    block_start = line_no
                block.append(comment)
            else:
                _flush_block(path, block_start, block, found)
                block = []
                block_start = 0

        _flush_block(path, block_start, block, found)
    return found


def main() -> int:
    if any(arg in ("-h", "--help") for arg in sys.argv[1:]):
        print(__doc__)
        return 0

    found = scan()
    known = set(KNOWN_VIOLATIONS)

    if "--list" in sys.argv[1:]:
        print(f"Comment hygiene guardrail offenders ({len(found)} locations):\n")
        for key, reason in found.items():
            tag = "known" if key in known else "NEW"
            print(f"  [{tag}] {key}  <-  {reason}")
        return 0

    new = sorted(set(found) - known)
    stale = sorted(known - set(found))

    print(f"Comment hygiene guardrail: scanned {SWIFT_DIR.relative_to(ROOT)}")
    print(f"  {len(found)} offender location(s); {len(known)} known.")

    if stale:
        print(f"\n  {len(stale)} KNOWN_VIOLATIONS entries are now clean; remove them:")
        for key in stale:
            print(f"      {key}")

    if new:
        print(f"\n  {len(new)} new comment hygiene offender(s):")
        for key in new:
            print(f"      {key}  <-  {found[key]}")
        print(
            "\nFix: delete commented-out code, or attach TODO/FIXME to a tracked issue "
            f"(#NNN). Rule pointer: {RULE_DOC}."
        )
        return 1

    if stale:
        print("\n(KNOWN_VIOLATIONS has stale entries; clean them up when convenient.)")
    print("\nOK: no new commented-out code or untracked TODO/FIXME comments.")
    return 0


def _require_scan_roots_4382(*roots):
    """#4382: a guardrail must know when it has gone blind, and say so.

    A missing scan root means "I could not check" (exit 2) -- never a silent
    exit 0. Distinct from exit 1 ("I checked and found violations"), so a
    moved or renamed directory can never disable this guardrail while the
    gate stays green.
    """
    import sys as _sys

    flat = []
    for root in roots:
        flat.extend(root if isinstance(root, (tuple, list)) else [root])
    missing = [str(r) for r in flat if not r.exists()]
    if missing:
        print(
            f"{__file__.rsplit('/', 1)[-1]}: BLIND -- scan root(s) missing: "
            + ", ".join(missing)
            + " (the tree moved; update this guardrail's paths)",
            file=_sys.stderr,
        )
        _sys.exit(2)


if __name__ == "__main__":
    _require_scan_roots_4382(SWIFT_DIR)
    raise SystemExit(main())

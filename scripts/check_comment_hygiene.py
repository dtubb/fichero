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
"fichero/fichero/Services/ChatServiceGenerated.swift#9190295867": "#1916 baseline",
    "fichero/fichero/Services/ProviderServiceGenerated.swift#42e66be4ac": "#1916 baseline",
    "fichero/fichero/Services/WorkflowStreamService+Parsing.swift#a55c320098": "#1916 baseline",
    "fichero/fichero/Views/Library/ImageViewer/ImageWithCursorTracking.swift#b359bd483c": "#1916 baseline",
    "fichero/fichero/Views/Library/ImageViewerComponents.swift#c7669329ed": "#1916 baseline",
    "fichero/fichero/Views/Library/LibraryView+KeyboardShortcuts.swift#d5e49f726d": "#1916 baseline",
    "fichero/fichero/Views/Library/PDFPageView.swift#21f2204213": "#1916 baseline",
    "fichero/fichero/Views/Sheets/DocumentPickerSheet.swift#727654079f": "#1916 baseline",
}
_TODO = re.compile(r"\b(?:TODO|FIXME)\b")
_ISSUE = re.compile(r"#\d+")
_CODEISH = re.compile(
    r"(^|\s)(?:func|let|var|if|else|guard|for|while|switch|case|return|import|struct|class|enum)\b|[=;{}]"
)
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


if __name__ == "__main__":
    raise SystemExit(main())

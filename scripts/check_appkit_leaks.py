#!/usr/bin/env python3
"""macOS-only-API leak guardrail for the multiplatform SwiftUI app (#3018).

fichero/fichero/** is compiled for macOS AND iOS/iPadOS (and visionOS). AppKit
is macOS-only, and a handful of SwiftUI view modifiers (the keyboard-command
family: onDeleteCommand/onExitCommand/onMoveCommand/onCommand + cut/copy/paste)
are macOS-only too — so any of them used OUTSIDE a macOS `#if` guard breaks the
iOS build (the class of regression behind "iPad/iPhone not working", #2098).
This scans for both and fails on NEW unguarded leaks.

Rule: an AppKit-only symbol (`import AppKit`, `NSApplication`, `NSEvent`,
`NSWorkspace`, `NSPasteboard`, `NSWindow`, `NSPanel`, `NSMenu`, `NSStatusBar`,
`NSViewRepresentable`, `NSViewController…`) must appear only inside a region
guarded by `#if os(macOS)` or `#if canImport(AppKit)` (and not that region's
non-macOS `#else`/`#elseif`). Comments and `#Preview` blocks are stripped first.

Existing macOS-only files are grandfathered in KNOWN_APPKIT_FILES (a ratchet):
they still pass, but any NEW shared-code leak fails. Remove a file from the
allowlist once its AppKit is `#if`-guarded or moved behind a representable.

Usage:
    scripts/check_appkit_leaks.py            # gate mode
    scripts/check_appkit_leaks.py --list     # list every unguarded hit (incl. allowlisted)
    scripts/check_appkit_leaks.py --help

Exit codes:
    0  no NEW unguarded AppKit
    1  one or more NEW leaks (outside the allowlist)
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SWIFT_DIR = ROOT / "fichero" / "fichero"

_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_LINE_COMMENT = re.compile(r"(?<!:)//.*")

# AppKit-only symbols. Deliberately excludes cross-platform-aliased types
# (NSColor/NSFont/NSImage/NSAttributedString) which the app bridges via
# PlatformColor etc. — flagging those would be noise, not iOS breakage.
_APPKIT_TOKENS = [
    r"\bimport\s+AppKit\b",
    r"\bNSApplication\b",
    r"\bNSEvent\b",
    r"\bNSWorkspace\b",
    r"\bNSPasteboard\b",
    r"\bNSWindow\b",
    r"\bNSPanel\b",
    r"\bNSStatusBar\b",
    r"\bNSMenu\b",
    r"\bNSViewRepresentable\b",
    r"\bNSViewControllerRepresentable\b",
    r"\bNSHostingController\b",
    r"\bNSOpenPanel\b",
    r"\bNSSavePanel\b",
]
_APPKIT_RE = re.compile("|".join(_APPKIT_TOKENS))

# macOS-only SwiftUI view modifiers (unavailable on iOS/iPadOS/visionOS). Same
# rule and same breakage as an AppKit symbol: used OUTSIDE a `#if os(macOS)`
# guard they fail the iOS build. The keyboard-command family — ⌫ delete, ⎋
# exit, arrow-key move, ⌘ command, and the cut/copy/paste responder modifiers —
# is macOS-only in SwiftUI. (Extends #3018 after two ungated leaks — #1928 lane
# — broke Daniel's iPhone build: onDeleteCommand + onExitCommand.)
_MACOS_MODIFIER_TOKENS = [
    r"\.onDeleteCommand\b",
    r"\.onExitCommand\b",
    r"\.onMoveCommand\b",
    r"\.onCommand\b",
    r"\.onCutCommand\b",
    r"\.onCopyCommand\b",
    r"\.onPasteCommand\b",
]

# The combined macOS-only surface the guard enforces.
_MACOS_ONLY_RE = re.compile("|".join(_APPKIT_TOKENS + _MACOS_MODIFIER_TOKENS))

# Files that legitimately hold macOS-only AppKit today (sanctioned bridges +
# macOS-only shell). Grandfathered so the guard only catches NEW leaks. Paths
# are relative to fichero/fichero/.
KNOWN_APPKIT_FILES: set[str] = set()  # populated below after first scan


def _strip_noise(text: str) -> str:
    text = _BLOCK_COMMENT.sub("", text)
    text = "\n".join(_LINE_COMMENT.sub("", line) for line in text.splitlines())
    # Drop #Preview { ... } blocks (brace-matched) — previews compile per
    # platform but are not product code; keep the signal on shipping views.
    out, i, n = [], 0, len(text)
    while i < n:
        m = re.search(r"#Preview\b[^{]*\{", text[i:])
        if not m:
            out.append(text[i:])
            break
        out.append(text[i : i + m.start()])
        depth, j = 1, i + m.end()
        while j < n and depth:
            if text[j] == "{":
                depth += 1
            elif text[j] == "}":
                depth -= 1
            j += 1
        i = j
    return "".join(out)


def _classify(cond: str) -> str:
    """MACOS / NONMACOS / UNKNOWN for the positive branch of a #if condition."""
    c = cond.strip()
    # Negated macOS/AppKit guards are the NON-macOS branch — check first, else
    # `"os(macOS)" in "!os(macOS)"` would wrongly read as MACOS and let AppKit
    # leak through an `#if !os(macOS)` (iOS-only) block undetected.
    if "!os(macOS)" in c or "!canImport(AppKit)" in c:
        return "NONMACOS"
    if "||" not in c and ("os(macOS)" in c or "canImport(AppKit)" in c):
        return "MACOS"
    non_macos = ("os(iOS)", "os(visionOS)", "os(watchOS)", "os(tvOS)", "canImport(UIKit)")
    if any(tok in c for tok in non_macos) and "os(macOS)" not in c and "canImport(AppKit)" not in c:
        return "NONMACOS"
    return "UNKNOWN"


def _complement(if_state: str) -> str:
    if if_state == "MACOS":
        return "NONMACOS"
    if if_state == "NONMACOS":
        return "MACOS"
    return "UNKNOWN"


def unguarded_hits(source: str) -> list[tuple[int, str]]:
    """Line numbers + text where a macOS-only API (AppKit symbol or macOS-only
    SwiftUI command modifier) is not macOS-guarded."""
    text = _strip_noise(source)
    hits: list[tuple[int, str]] = []
    # Stack frames: {"state": current-branch state, "if_state": #if positive state}
    stack: list[dict[str, str]] = []
    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if line.startswith("#if "):
            st = _classify(line[4:])
            stack.append({"state": st, "if_state": st})
            continue
        if line.startswith("#elseif "):
            if stack:
                stack[-1]["state"] = _classify(line[8:])
            continue
        if line == "#else":
            if stack:
                stack[-1]["state"] = _complement(stack[-1]["if_state"])
            continue
        if line.startswith("#endif"):
            if stack:
                stack.pop()
            continue
        if _MACOS_ONLY_RE.search(raw):
            guarded = any(f["state"] == "MACOS" for f in stack)
            if not guarded:
                hits.append((lineno, raw.strip()))
    return hits


def scan() -> dict[str, list[tuple[int, str]]]:
    result: dict[str, list[tuple[int, str]]] = {}
    for path in sorted(SWIFT_DIR.rglob("*.swift")):
        if "/fichero-tests/" in str(path) or "/fichero-ui-tests/" in str(path):
            continue
        rel = str(path.relative_to(SWIFT_DIR))
        hits = unguarded_hits(path.read_text(encoding="utf-8"))
        if hits:
            result[rel] = hits
    return result


def _assert_guard_logic() -> None:
    """Assert the preprocessor tracker + classifier behave. Raises on regression;
    run on every gate invocation so a broken guard fails loudly, not silently."""
    assert _classify("os(macOS)") == "MACOS"
    assert _classify(" canImport(AppKit) && DEBUG ") == "MACOS"
    assert _classify("os(iOS)") == "NONMACOS"
    assert _classify("!os(macOS)") == "NONMACOS"
    assert _classify("os(macOS) || os(iOS)") == "UNKNOWN"  # || → not guaranteed

    # Top-level (unguarded) AppKit → flagged.
    assert unguarded_hits("import AppKit\n_ = NSApplication.shared\n")

    # Guarded by os(macOS) → clean.
    assert not unguarded_hits(
        "#if os(macOS)\nimport AppKit\n_ = NSApplication.shared\n#endif\n"
    )
    # The non-macOS #else branch of a macOS guard → flagged.
    assert unguarded_hits(
        "#if os(macOS)\nlet x = 1\n#else\n_ = NSEvent()\n#endif\n"
    )
    # The #else of a `!os(macOS)` guard IS the macOS branch → clean.
    assert not unguarded_hits(
        "#if !os(macOS)\nlet x = 1\n#else\n_ = NSApplication.shared\n#endif\n"
    )
    # Nested: AppKit deep inside an os(macOS) region → clean.
    assert not unguarded_hits(
        "#if os(macOS)\n#if DEBUG\n_ = NSWorkspace.shared\n#endif\n#endif\n"
    )
    # #Preview blocks are stripped, so AppKit in a preview isn't flagged.
    assert not unguarded_hits("#Preview {\n_ = NSApplication.shared\n}\n")

    # macOS-only SwiftUI command modifiers are enforced like AppKit symbols:
    # ungated → flagged, macOS-guarded → clean. (The #1928-lane regression that
    # broke the iPhone build was exactly an ungated .onDeleteCommand.)
    assert unguarded_hits('Text("x").onDeleteCommand(perform: f)\n')
    assert unguarded_hits('Text("x").onExitCommand(perform: f)\n')
    assert not unguarded_hits(
        '#if os(macOS)\nText("x").onDeleteCommand(perform: f)\n#endif\n'
    )
    # A macOS-only modifier in the non-macOS #else branch → still flagged.
    assert unguarded_hits(
        '#if os(macOS)\nlet x = 1\n#else\nText("x").onMoveCommand { _ in }\n#endif\n'
    )


def main(argv: list[str]) -> int:
    if "--help" in argv or "-h" in argv:
        print(__doc__)
        return 0
    if "--self-test" in argv:
        _assert_guard_logic()
        print("check_appkit_leaks self-test: OK")
        return 0

    # Fail loudly if the guard's own logic regressed — a silently-broken guard
    # would let real leaks through.
    _assert_guard_logic()

    found = scan()
    list_mode = "--list" in argv

    new_leaks = {f: h for f, h in found.items() if f not in KNOWN_APPKIT_FILES}

    if list_mode:
        for rel, hits in found.items():
            tag = "ALLOWLISTED" if rel in KNOWN_APPKIT_FILES else "LEAK"
            for lineno, snippet in hits:
                print(f"[{tag}] {rel}:{lineno}: {snippet[:100]}")
        print(f"\n{len(found)} file(s) with unguarded AppKit "
              f"({len(KNOWN_APPKIT_FILES)} allowlisted, {len(new_leaks)} new).")

    stale = sorted(KNOWN_APPKIT_FILES - set(found))

    if not new_leaks and not stale:
        print(f"AppKit-leak guardrail: scanned {SWIFT_DIR}")
        print(f"  0 new unguarded-AppKit leaks ({len(KNOWN_APPKIT_FILES)} files grandfathered).")
        return 0

    if new_leaks:
        print("AppKit-leak guardrail FAILED — unguarded AppKit in shared code "
              "(breaks the iOS build). Wrap in `#if os(macOS)` / move behind an "
              "NSViewRepresentable, or grandfather in KNOWN_APPKIT_FILES if the "
              "whole file is macOS-only:\n")
        for rel, hits in sorted(new_leaks.items()):
            for lineno, snippet in hits:
                print(f"  {rel}:{lineno}: {snippet[:100]}")
    if stale:
        print("\nStale allowlist entries (no longer leak — remove from "
              "KNOWN_APPKIT_FILES to keep the ratchet tight):")
        for rel in stale:
            print(f"  {rel}")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

#!/usr/bin/env python3
"""Shell-chrome guardrail — machine-enforces §6b of the shell reform (#3040).

Three rules over fichero/fichero/Views/:
  1. No app-internal NotificationCenter — `NotificationCenter.default.post`/
     `.publisher(for:)` on a custom `.fichero*` Notification.Name. Use direct
     @Observable calls / @Environment instead (#3034 line of work). System
     notifications (NSApplication/UIApplication/scenePhase/etc.) are fine.
  2. No `@ObservedObject`/`@StateObject var x = Type.shared` in a View — inject
     via @EnvironmentObject/@Environment so the view's deps are testable (#3033).
  3. Shell files (ContentView* / Sidebar*) must stay <= 1000 lines.

Rules 1 & 2 use a content-hash ratchet: every current offender is grandfathered
in KNOWN_VIOLATIONS by a hash of its normalized line. A NEW offender (unknown
hash) fails; a grandfathered line that changes gets a new hash and must be fixed
or re-approved; a KNOWN hash that disappears is reported as stale so the
allowlist can only shrink. Rule 3 has no allowlist.

Seed/refresh the allowlist with `--generate` after the injection / NotificationCenter
slices land (the allowlist should be near-empty).

Usage:
    scripts/check_shell_chrome.py            # gate
    scripts/check_shell_chrome.py --list      # every current offender
    scripts/check_shell_chrome.py --generate  # emit KNOWN_VIOLATIONS literal
    scripts/check_shell_chrome.py --self-test
    scripts/check_shell_chrome.py --help

Exit codes: 0 clean; 1 a new offender, an oversize shell file, or a stale entry.
"""
from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VIEWS_DIR = ROOT / "fichero" / "fichero" / "Views"
SHELL_LINE_LIMIT = 1000

_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_LINE_COMMENT = re.compile(r"(?<!:)//.*")

# Rule 1: app-internal NotificationCenter on a custom `.fichero*` name.
_NC_APP_RE = re.compile(
    r"NotificationCenter\s*\.\s*default\s*\.\s*(?:post\s*\(\s*name:|publisher\s*\(\s*for:)\s*\.fichero\w+"
)
# Rule 2: @ObservedObject / @StateObject bound to a `.shared` singleton.
_SHARED_RE = re.compile(r"@(?:ObservedObject|StateObject)\b[^=\n]*=\s*\w+\s*\.\s*shared\b")

RULES = (("notif", _NC_APP_RE), ("shared", _SHARED_RE))

# Grandfathered offenders (hash -> human location). Seed with --generate (#3040).
KNOWN_VIOLATIONS: dict[str, str] = {
    "c9065d74dcce": '[notif] fichero/fichero/Views/Shell/ContentView/ContentView.swift:587: .onReceive(NotificationCenter.default.publisher(for: .ficheroSelectDocumentRequested)) { n',
    "211b47ab4e9c": '[notif] fichero/fichero/Views/Shell/ContentView/ContentView.swift:590: .onReceive(NotificationCenter.default.publisher(for: .ficheroShowPanelRequested)) { note i',
    "0fbc3922252c": '[shared] fichero/fichero/Views/Library/LibraryView.swift:83: @ObservedObject var featureManager = FeatureManager.shared',
    "a89c78a261e7": '[shared] fichero/fichero/Views/Onboarding/FirstRunWindow.swift:10: @ObservedObject private var featureManager = FeatureManager.shared',
    "2cf26c6b1a60": '[shared] fichero/fichero/Views/Settings/AISettingsView.swift:16: @ObservedObject var featureManager = FeatureManager.shared',
    "85ec0df2648e": '[shared] fichero/fichero/Views/Shell/Menu/AddItemMenu.swift:10: @ObservedObject var featureManager = FeatureManager.shared',
    "97525f1e35bf": '[shared] fichero/fichero/Views/Shell/Menu/FocusedCommandButtons.swift:517: @ObservedObject var featureManager = FeatureManager.shared',
    "79b1c1bacc70": '[shared] fichero/fichero/Views/Shell/Menu/ViewMenuCommands.swift:428: @ObservedObject var featureManager = FeatureManager.shared',
    "15fbb889e15b": '[shared] fichero/fichero/Views/Sidebar/Sections/SidebarViewExtensions.swift:28: @ObservedObject var featureManager = FeatureManager.shared',
    "ce6eb77c9655": '[shared] fichero/fichero/Views/Workflow/WorkflowInspector.swift:26: @ObservedObject var featureManager = FeatureManager.shared',
    "ee5a9796cfb1": '[shared] fichero/fichero/Views/Workflow/WorkflowLibraryView.swift:67: @ObservedObject var featureManager = FeatureManager.shared',
    "02e8d70f454e": '[shared] fichero/fichero/Views/Workflow/WorkflowLibraryView/WorkflowDetailView.swift:13: @ObservedObject var featureManager = FeatureManager.shared',
}


def _code(text: str) -> str:
    text = _BLOCK_COMMENT.sub(lambda m: "\n" * m.group(0).count("\n"), text)
    return "\n".join(_LINE_COMMENT.sub("", line) for line in text.splitlines())


def _hash(rule: str, rel: str, snippet: str) -> str:
    # Includes the file so each (file, offending line) is distinct — a NEW file
    # with an identical offending line is a NEW hash. Excludes the line number so
    # unrelated edits that shift lines don't churn the allowlist.
    norm = re.sub(r"\s+", " ", snippet).strip()
    return hashlib.sha1(f"{rule}|{rel}|{norm}".encode()).hexdigest()[:12]


def violations() -> dict[str, str]:
    """hash -> "[rule] rel:line: snippet" for every rule-1/2 offender."""
    found: dict[str, str] = {}
    for path in sorted(VIEWS_DIR.rglob("*.swift")):
        s = str(path)
        if "/fichero-tests/" in s or "/fichero-ui-tests/" in s:
            continue
        rel = path.relative_to(ROOT).as_posix()
        for idx, line in enumerate(_code(path.read_text(errors="ignore")).splitlines(), start=1):
            for rule, rx in RULES:
                if rx.search(line):
                    found[_hash(rule, rel, line)] = f"[{rule}] {rel}:{idx}: {line.strip()[:90]}"
    return found


def oversize_shell_files() -> list[tuple[str, int]]:
    bad: list[tuple[str, int]] = []
    for path in sorted(VIEWS_DIR.rglob("*.swift")):
        if path.name.startswith(("ContentView", "Sidebar")):
            n = len(path.read_text(errors="ignore").splitlines())
            if n > SHELL_LINE_LIMIT:
                bad.append((path.relative_to(ROOT).as_posix(), n))
    return bad


def _self_test() -> None:
    assert _NC_APP_RE.search("NotificationCenter.default.post(name: .ficheroOpenClaimSource, object: nil)")
    assert _NC_APP_RE.search(".onReceive(NotificationCenter.default.publisher(for: .ficheroEntityUpdated))")
    # System notifications are not app-internal → not flagged.
    assert not _NC_APP_RE.search("NotificationCenter.default.publisher(for: NSApplication.willTerminateNotification)")
    assert _SHARED_RE.search("@ObservedObject var featureManager = FeatureManager.shared")
    assert _SHARED_RE.search("@StateObject private var f = FeatureManager.shared")
    # Injected deps are not `.shared` → not flagged.
    assert not _SHARED_RE.search("@EnvironmentObject var featureManager: FeatureManager")
    assert not _SHARED_RE.search("let x = Foo.sharedThing")  # word-boundary: not `.shared`
    # Same offender text in the same file hashes stably regardless of indentation…
    assert _hash("shared", "F.swift", "  @ObservedObject var a = A.shared") == \
        _hash("shared", "F.swift", "@ObservedObject var a = A.shared")
    # …but the SAME line in a DIFFERENT file is a distinct hash (per-file ratchet).
    assert _hash("shared", "F.swift", "@ObservedObject var a = A.shared") != \
        _hash("shared", "G.swift", "@ObservedObject var a = A.shared")


def main(argv: list[str]) -> int:
    if "--help" in argv or "-h" in argv:
        print(__doc__)
        return 0
    if "--self-test" in argv:
        _self_test()
        print("check_shell_chrome self-test: OK")
        return 0

    _self_test()
    found = violations()
    oversize = oversize_shell_files()

    if "--generate" in argv:
        print("KNOWN_VIOLATIONS: dict[str, str] = {")
        for h, loc in sorted(found.items(), key=lambda kv: kv[1]):
            print(f'    "{h}": {loc!r},')
        print("}")
        return 0

    if "--list" in argv:
        for h, loc in sorted(found.items(), key=lambda kv: kv[1]):
            tag = "known" if h in KNOWN_VIOLATIONS else "NEW"
            print(f"[{tag}] {loc}")
        for rel, n in oversize:
            print(f"[OVERSIZE] {rel}: {n} lines")
        print(f"\n{len(found)} rule-1/2 offender(s), {len(KNOWN_VIOLATIONS)} grandfathered; "
              f"{len(oversize)} oversize shell file(s).")

    new = sorted(h for h in found if h not in KNOWN_VIOLATIONS)
    stale = sorted(set(KNOWN_VIOLATIONS) - set(found))

    if not new and not stale and not oversize:
        print("Shell-chrome guardrail (§6b, #3040):")
        print(f"  {len(KNOWN_VIOLATIONS)} grandfathered; 0 new; 0 oversize shell files. Clean.")
        return 0

    if new:
        print("Shell-chrome guardrail FAILED — new §6b violation(s). Use a direct "
              "@Observable call / @Environment injection instead of NotificationCenter "
              "or `= .shared` (see #3033/#3034); if genuinely unavoidable, re-seed with "
              "--generate:\n")
        for h in new:
            print(f"  {found[h]}")
    if oversize:
        print("\nOversize shell file(s) (> 1000 lines) — extract a cohesive slice:")
        for rel, n in oversize:
            print(f"  {rel}: {n} lines")
    if stale:
        print("\nStale KNOWN_VIOLATIONS (a slice cleaned these) — re-run --generate to "
              "shrink the allowlist:")
        for h in stale:
            print(f"  {h}  ({KNOWN_VIOLATIONS[h]})")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

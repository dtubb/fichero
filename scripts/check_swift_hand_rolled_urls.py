#!/usr/bin/env python3
"""Hand-rolled engine URL / transport guardrail (§6b reform master plan).

Rule (one transport: the generated client):

    > SwiftUI code must reach the Fichero engine through the generated
    > `FicheroAPIClient` and the sanctioned `*Generated` service wrappers under
    > `Services/`. It must NOT hand-build an engine URL or HTTP request — raw
    > `URLSession`, `URLRequest(url:)`, a `URL(string:)` pointed at the engine
    > host, or a literal `"/api/..."` path — anywhere outside the transport
    > layer. Those bypass auth headers, typed models, and the OpenAPI contract.

Scope: `fichero/fichero/**/*.swift`, EXCLUDING the sanctioned transport layer
(`Services/` — that is where request-building legitimately lives, including the
`*Generated` wrappers and `APIClient`). Comments and `#Preview {}` blocks are
stripped before scanning.

What is flagged (each match is one violation, keyed by content hash):
  - `URLSession`                       — raw HTTP session in app/model/view code
  - `URLRequest(url:`                  — hand-built request
  - `URL(string: ...)` whose literal targets the engine
    (`localhost`, `127.0.0.1`, `:8765`, `/api/`)
  - a string literal beginning `"/api/..."` — hand-built engine path

NOT flagged: `URL(string: "https://ollama.com/...")` and other EXTERNAL links
(provider download pages, docs) — those are not the engine. WebView loads that
hand-build a request still count and are baselined (a webview should be handed a
store-provided URL).

`KNOWN_VIOLATIONS` is the current migration backlog (keyed by
`relpath#sha1(normalized-line)` — a stable content signature, never a line
number). The guardrail PASSES today and FAILS when NEW app/view/model code
hand-rolls engine transport, and flags stale entries when one is fixed.

Usage:
    scripts/check_swift_hand_rolled_urls.py
    scripts/check_swift_hand_rolled_urls.py --list
    scripts/check_swift_hand_rolled_urls.py --help

Exit codes:
    0  every hand-rolled-transport site is in KNOWN_VIOLATIONS
    1  a new site appeared, or a known entry is stale
"""
from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SWIFT_DIR = ROOT / "fichero" / "fichero"
RULE_DOC = "docs/contributor/architecture/swiftui/reform_masterplan_2026-06.md"

# The sanctioned transport layer — request-building lives here by design.
SANCTIONED_DIR_PARTS = ("Services",)

# Engine markers that make a `URL(string: ...)` literal an engine URL.
_ENGINE_MARKERS = ("localhost", "127.0.0.1", ":8765", "/api/")

_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
# Negative lookbehind for ':' so we don't treat the '//' in `http://` as a comment.
_LINE_COMMENT = re.compile(r"(?<!:)//.*")

# Detectors, each (label, predicate over a single code line).
_URLSESSION_RE = re.compile(r"\bURLSession\b")
_URLREQUEST_RE = re.compile(r"\bURLRequest\s*\(\s*url\s*:")
_URLSTRING_RE = re.compile(r"\bURL\s*\(\s*string\s*:\s*([^)]*)")
_APIPATH_RE = re.compile(r'"/api/')

# Current migration backlog. Populated from the baseline scan (§6b).
# Keys are `relpath#sha1(normalized-line)[:10]`. Several call sites share an
# identical line (and thus hash) within a file — that is expected.
KNOWN_VIOLATIONS: dict[str, str] = {
    "Models/DocumentStore+CRUD.swift#842cbd3a0a": "§6b baseline — hand-built URLRequest(url:)",
    "Views/Components/FicheroWebView.swift#72bc3c3d1f": "§6b baseline — hand-built URLRequest(url:)",
    "Views/Components/FicheroWebView.swift#b0f6d9c546": (
        "WKNavigationDelegate server-trust challenge signature names "
        "URLSession.AuthChallengeDisposition (an enum type, not a raw session); "
        "the handler forwards to RemoteCertificatePinning.resolveServerTrustChallenge — "
        "the shared pinned transport — so the generic web view validates the "
        "engine's pinned HTTPS cert like every other call site (#2601)."
    ),
    "Views/Library/DocumentKGWebPane.swift#10ac98dccd": "§6b baseline — hand-built URLRequest(url:)",
    "Views/Library/DocumentKGWebPane.swift#b0f6d9c546": (
        "WKNavigationDelegate server-trust challenge signature names "
        "URLSession.AuthChallengeDisposition (an enum type, not a raw session); "
        "the handler forwards to RemoteCertificatePinning.resolveServerTrustChallenge — "
        "the shared pinned transport — so the KG/reader WKWebView validates the "
        "engine's pinned HTTPS cert like every other call site (#2538)."
    ),
    "Views/Library/QuickLookComponents.swift#59d9159ae2": "§6b baseline — hand-built URLRequest(url:)",
}


def _strip_preview_blocks(text: str) -> str:
    out: list[str] = []
    i, n = 0, len(text)
    while i < n:
        m = text.find("#Preview", i)
        if m == -1:
            out.append(text[i:])
            break
        out.append(text[i:m])
        brace = text.find("{", m)
        if brace == -1:
            out.append(text[m:])
            break
        depth, j = 0, brace
        while j < n:
            c = text[j]
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    j += 1
                    break
            j += 1
        out.append("\n" * text[m:j].count("\n"))
        i = j
    return "".join(out)


def code_lines(text: str) -> list[str]:
    text = _BLOCK_COMMENT.sub(lambda m: "\n" * m.group(0).count("\n"), text)
    text = _strip_preview_blocks(text)
    return [_LINE_COMMENT.sub("", line) for line in text.splitlines()]


def _line_matches(line: str) -> str | None:
    """Return a short reason if the line hand-rolls engine transport, else None."""
    if _URLSESSION_RE.search(line):
        return "raw URLSession"
    if _URLREQUEST_RE.search(line):
        return "hand-built URLRequest(url:)"
    if _APIPATH_RE.search(line):
        return 'literal "/api/..." engine path'
    m = _URLSTRING_RE.search(line)
    if m and any(mark in m.group(1) for mark in _ENGINE_MARKERS):
        return "URL(string:) targeting the engine"
    return None


def _key(rel: str, line: str) -> str:
    normalized = re.sub(r"\s+", " ", line.strip())
    digest = hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:10]
    return f"{rel}#{digest}"


def scan(swift_dir: Path = SWIFT_DIR) -> dict[str, str]:
    found: dict[str, str] = {}
    for path in sorted(swift_dir.rglob("*.swift")):
        if "Tests" in path.parts:
            continue
        if any(part in path.parts for part in SANCTIONED_DIR_PARTS):
            continue
        try:
            source = path.read_text(errors="ignore")
        except OSError:
            continue
        rel = path.relative_to(swift_dir).as_posix()
        for idx, line in enumerate(code_lines(source)):
            reason = _line_matches(line)
            if reason is None:
                continue
            found[_key(rel, line)] = f"{reason} (line {idx + 1})"
    return found


def main() -> int:
    if any(arg in ("-h", "--help") for arg in sys.argv[1:]):
        print(__doc__)
        return 0

    found = scan()
    known = set(KNOWN_VIOLATIONS)

    if "--list" in sys.argv[1:]:
        print(f"Hand-rolled engine transport sites ({len(found)}):\n")
        for key, reason in sorted(found.items()):
            tag = "known" if key in known else "NEW"
            print(f"  [{tag}] {key}  <-  {reason}")
        return 0

    new = sorted(set(found) - known)
    stale = sorted(known - set(found))

    print(f"Hand-rolled engine URL guardrail: scanned {SWIFT_DIR.relative_to(ROOT)} (excl. Services/)")
    print(f"  {len(found)} hand-rolled-transport site(s); {len(known)} known.")

    if stale:
        print(f"\n  ✓ {len(stale)} KNOWN_VIOLATIONS entry now clean — drop from the set:")
        for key in stale:
            print(f"      {key}")

    if new:
        print(f"\n  ✗ {len(new)} new hand-rolled engine-transport site(s):")
        for key in new:
            print(f"      {key}  ←  {found[key]}")
        print(
            "\nFix: route engine calls through an @Observable store / the generated "
            "FicheroAPIClient (or a sanctioned Services/*Generated wrapper). If this "
            "is genuinely transport-layer code, move it under Services/ or add it to "
            f"KNOWN_VIOLATIONS with a reason. Rule: {RULE_DOC} §6b."
        )
        return 1

    if stale:
        print("\n(KNOWN_VIOLATIONS has stale entries — clean them up when convenient.)")
        return 1

    print("\n✓ No new hand-rolled engine-transport sites beyond the known backlog.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

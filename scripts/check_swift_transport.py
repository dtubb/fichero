#!/usr/bin/env python3
"""Transport/TLS guardrail for Swift engine call sites (#2606).

Rule:
  1. Every engine-bound URLSession must be the pinned
     RemoteCertificatePinning session. Raw URLSession.shared or
     URLSession(configuration:) hitting the engine is a regression.
  2. Every WKWebView that loads engine content must implement
     webView(_:didReceive:completionHandler:) with the exact pinned signature:

         @escaping @MainActor @Sendable (URLSession.AuthChallengeDisposition, URLCredential?) -> Void

     A plain signature (missing @MainActor/@Sendable) must FAIL.
  3. Engine URLs must be HTTPS; literal http:// to an engine host is not allowed.

Scope: fichero/fichero/**/*.swift, excluding test files and #Preview blocks.
Comments and preview blocks are stripped before scanning.

Usage:
    scripts/check_swift_transport.py
    scripts/check_swift_transport.py --list
    scripts/check_swift_transport.py --help

Exit codes:
    0  no transport violations
    1  one or more violations found
"""
from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SWIFT_DIR = ROOT / "fichero" / "fichero"
RULE_DOC = "docs/architecture/swiftui/api_client.md"

_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_LINE_COMMENT = re.compile(r"(?<!:)//.*")

# Raw URLSession construction.
_URLSESSION_CTOR_RE = re.compile(r"\bURLSession\s*\(")
_URLSESSION_SHARED_RE = re.compile(r"\bURLSession\s*\.\s*shared\b")

# Pinned session is the only allowed engine-bound constructor.
_PINNED_SESSION_RE = re.compile(r"\bRemoteCertificatePinning\s*\.\s*configuredSession\s*\(")

# Literal http:// to an engine host.
_HTTP_ENGINE_MARKERS = ("127.0.0.1", ":8765", "/api/")
_HTTP_ENGINE_RE = re.compile(
    r'"http://[^"]*',
    re.IGNORECASE,
)

# Exact pinned WKWebView challenge completion-handler signature.
_CHALLENGE_COMPLETION_RE = re.compile(
    r"completionHandler\s*:\s*@escaping\s+@MainActor\s+@Sendable\s+\(\s*"
    r"URLSession\s*\.\s*AuthChallengeDisposition\s*,\s*"
    r"URLCredential\?\s*\)\s*->\s*Void",
    re.DOTALL,
)

# The canonical typealias is also acceptable because it expands to the exact
# pinned signature.
_CHALLENGE_TYPEALIAS_RE = re.compile(
    r"completionHandler\s*:\s*URLAuthenticationChallengeCompletionHandler",
    re.DOTALL,
)

# Locate a webView(_:didReceive:completionHandler:) declaration.
_WEBVIEW_FUNC_RE = re.compile(r"\bfunc\s+webView\s*\(", re.DOTALL)


# Deliberately allowed exceptions. Empty on the current codebase; kept as an
# escape hatch for sanctioned low-level transport files.
KNOWN_VIOLATIONS: dict[str, str] = {}


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


def _key(rel: str, line: str) -> str:
    normalized = re.sub(r"\s+", " ", line.strip())
    digest = hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:10]
    return f"{rel}#{digest}"


def _is_engine_url_literal(value: str) -> bool:
    return any(mark in value for mark in _HTTP_ENGINE_MARKERS)


def _collect_signature(lines: list[str], start: int) -> str:
    """Return the full func webView(... parameter list starting at start."""
    parts = [lines[start]]
    depth = lines[start].count("(") - lines[start].count(")")
    j = start
    while depth > 0 and j + 1 < len(lines):
        j += 1
        parts.append(lines[j])
        depth += lines[j].count("(") - lines[j].count(")")
    return "\n".join(parts)


def _webview_signature_ok(signature: str) -> bool:
    """True if the webView challenge handler has a pinned signature."""
    if "didReceive challenge" not in signature and "didReceiveChallenge" not in signature:
        return True  # Not the challenge overload; irrelevant.
    return bool(
        _CHALLENGE_COMPLETION_RE.search(signature)
        or _CHALLENGE_TYPEALIAS_RE.search(signature)
    )


def scan(swift_dir: Path = SWIFT_DIR) -> dict[str, str]:
    found: dict[str, str] = {}
    for path in sorted(swift_dir.rglob("*.swift")):
        if "Tests" in path.parts:
            continue
        try:
            source = path.read_text(errors="ignore")
        except OSError:
            continue
        rel = path.relative_to(swift_dir).as_posix()
        lines = code_lines(source)

        for idx, line in enumerate(lines):
            # Raw URLSession construction that is not the pinned factory.
            if (_URLSESSION_CTOR_RE.search(line) or _URLSESSION_SHARED_RE.search(line)) and not _PINNED_SESSION_RE.search(line):
                key = _key(rel, line)
                found[key] = f"raw unpinned URLSession to the engine (line {idx + 1})"
                continue

            # Plain http:// to an engine host.
            http_m = _HTTP_ENGINE_RE.search(line)
            if http_m and _is_engine_url_literal(http_m.group(0)):
                key = _key(rel, line)
                found[key] = f"plain http:// URL to the engine (line {idx + 1})"
                continue

        # WKWebView challenge signature check.
        for idx, line in enumerate(lines):
            if not _WEBVIEW_FUNC_RE.search(line):
                continue
            signature = _collect_signature(lines, idx)
            if not _webview_signature_ok(signature):
                key = _key(rel, signature.splitlines()[0])
                found[key] = f"WKWebView challenge handler lacks the pinned signature (line {idx + 1})"

    return found


def main() -> int:
    if any(arg in ("-h", "--help") for arg in sys.argv[1:]):
        print(__doc__)
        return 0

    found = scan()
    known = set(KNOWN_VIOLATIONS)

    if "--list" in sys.argv[1:]:
        print(f"Swift transport/TLS violations ({len(found)}):\n")
        for key, reason in sorted(found.items()):
            tag = "known" if key in known else "NEW"
            print(f"  [{tag}] {key}  <-  {reason}")
        return 0

    new = sorted(set(found) - known)
    stale = sorted(known - set(found))

    print(f"Swift transport/TLS guardrail: scanned {SWIFT_DIR.relative_to(ROOT)}")
    print(f"  {len(found)} violation(s); {len(known)} known.")

    if stale:
        print(f"\n  ✓ {len(stale)} KNOWN_VIOLATIONS entry now clean — drop from the set:")
        for key in stale:
            print(f"      {key}")

    if new:
        print(f"\n  ✗ {len(new)} new transport/TLS violation(s):")
        for key in new:
            print(f"      {key}  ←  {found[key]}")
        print(
            "\nFix: engine-bound URLSession must use "
            "RemoteCertificatePinning.configuredSession(). "
            "WKWebView challenge handlers must use the exact pinned signature. "
            f"Rule: {RULE_DOC} / #2606."
        )
        return 1

    if stale:
        print("\n(KNOWN_VIOLATIONS has stale entries — clean them up when convenient.)")
        return 1

    print("\n✓ No unpinned engine transport or WKWebView signature regressions.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

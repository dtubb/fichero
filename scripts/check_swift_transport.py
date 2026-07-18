#!/usr/bin/env python3
"""Transport/TLS guardrail for Swift engine call sites (#2606, #2608).

Rules:
  1. Every engine-bound URLSession must be the pinned
     RemoteCertificatePinning session. Raw URLSession.shared or
     URLSession(configuration:) that may be engine-bound is a regression.
  2. Every WKWebView that loads engine content must implement
     webView(_:didReceive:completionHandler:) with the exact pinned signature:

         @escaping @MainActor @Sendable (URLSession.AuthChallengeDisposition, URLCredential?) -> Void

     A plain signature (missing @MainActor/@Sendable) must FAIL.
  3. Engine URLs must be HTTPS; literal http:// to an engine host is not allowed.
  4. A certificate-pinned session used with URLSession.bytes( for SSE streaming
     must be retained as a class-level stored property. A per-call local that
     is created and then immediately used with .bytes( drops the delegate and
     fails with -9807 (#2605 / #2608).

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
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SWIFT_DIR = ROOT / "fichero" / "fichero"
RULE_DOC = "docs/contributor/architecture/fichero/api_client.md"

_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_LINE_COMMENT = re.compile(r"(?<!:)//.*")

# Raw URLSession construction.
_URLSESSION_CTOR_RE = re.compile(r"\bURLSession\s*\(")
_URLSESSION_SHARED_RE = re.compile(r"\bURLSession\s*\.\s*shared\b")

# Pinned session is the only allowed engine-bound constructor.
_PINNED_SESSION_RE = re.compile(r"\bRemoteCertificatePinning\s*\.\s*configuredSession\s*\(")

# Binding a pinned session to a local let/var.
_PINNED_SESSION_BIND_RE = re.compile(
    r"\b(let|var)\s+(\w+)\s*=\s*RemoteCertificatePinning\s*\.\s*configuredSession\s*\("
)

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

# The bare typealias historically did NOT carry @MainActor @Sendable, so it is
# no longer accepted as a shorthand for the pinned signature (#2608).

# Locate a webView(_:didReceive:completionHandler:) declaration.
_WEBVIEW_FUNC_RE = re.compile(r"\bfunc\s+webView\s*\(", re.DOTALL)


# Deliberately allowed exceptions. Empty on the current codebase; kept as an
# escape hatch for sanctioned low-level transport files.
KNOWN_VIOLATIONS: dict[str, str] = {}


@dataclass
class Scope:
    kind: str
    open_line: int
    close_line: int | None = field(default=None)


# Access / inheritance / attribute modifiers that can precede declarations.
_FUNC_MODIFIERS = (
    r"private\s+",
    r"public\s+",
    r"internal\s+",
    r"fileprivate\s+",
    r"open\s+",
    r"final\s+",
    r"static\s+",
    r"class\s+",
    r"override\s+",
    r"@.*\s+",
)
_TYPE_MODIFIERS = (
    r"private\s+",
    r"public\s+",
    r"internal\s+",
    r"fileprivate\s+",
    r"open\s+",
    r"final\s+",
    r"@.*\s+",
)
_INIT_MODIFIERS = (
    r"private\s+",
    r"public\s+",
    r"internal\s+",
    r"fileprivate\s+",
    r"open\s+",
    r"override\s+",
    r"convenience\s+",
    r"required\s+",
    r"@.*\s+",
)
_COMPUTED_MODIFIERS = _FUNC_MODIFIERS

_FUNC_DECL_RE = re.compile(rf"^(?:{'|'.join(_FUNC_MODIFIERS)})*func\b")
_INIT_DECL_RE = re.compile(rf"^(?:{'|'.join(_INIT_MODIFIERS)})*init\b")
_TYPE_DECL_RE = re.compile(rf"^(?:{'|'.join(_TYPE_MODIFIERS)})*(?:class|struct|actor|extension|enum)\b")
_COMPUTED_DECL_RE = re.compile(
    rf"^(?:{'|'.join(_COMPUTED_MODIFIERS)})*(?:var|let)\s+\w+\s*[^=]*\{{"
)


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
    return bool(_CHALLENGE_COMPLETION_RE.search(signature))


def _analyze_scopes(lines: list[str]) -> list[list[Scope]]:
    """Return the stack of active scopes for each line.

    Scope kinds:
      type     - class / struct / actor / extension / enum body
      func     - func body
      init     - init body
      computed - computed var/let body
      other    - everything else (closures, if/else, do, etc.)
    """
    scopes: list[Scope] = []
    stack: list[Scope] = []
    pending: tuple[str, int] | None = None

    for i, line in enumerate(lines):
        stripped = line.lstrip()

        # Check func before type so "class func" is treated as a func body,
        # not a nested type.
        opener: str | None = None
        if _FUNC_DECL_RE.match(stripped):
            opener = "func"
        elif _INIT_DECL_RE.match(stripped):
            opener = "init"
        elif _TYPE_DECL_RE.match(stripped):
            opener = "type"
        elif _COMPUTED_DECL_RE.match(stripped):
            opener = "computed"

        opens = line.count("{")
        closes = line.count("}")

        # If a scope opener was on the previous line, its brace is the first
        # brace on this line.
        if pending and opens > 0:
            scope = Scope(kind=pending[0], open_line=pending[1])
            stack.append(scope)
            scopes.append(scope)
            pending = None
            opens -= 1

        # If the current line has an opener keyword, assign it to the first
        # remaining brace.
        if opener and opens > 0:
            scope = Scope(kind=opener, open_line=i)
            stack.append(scope)
            scopes.append(scope)
            opens -= 1
            opener = None

        # Any remaining braces are generic scopes.
        for _ in range(opens):
            scope = Scope(kind="other", open_line=i)
            stack.append(scope)
            scopes.append(scope)

        # If the opener keyword had no brace on this line, the brace must be
        # on the next line.
        if opener:
            pending = (opener, i)

        # Close braces at the end of the line (naive but sufficient for this
        # style-checker; strings/comments are already stripped).
        for _ in range(closes):
            if stack:
                scope = stack.pop()
                scope.close_line = i

    # Anything left open ends at the last line.
    eof = max(0, len(lines) - 1)
    for scope in stack:
        scope.close_line = eof

    # Build per-line active stacks.
    per_line: list[list[Scope]] = []
    for i in range(len(lines)):
        active = [s for s in scopes if s.open_line <= i <= (s.close_line or i)]
        per_line.append(active)
    return per_line


def _check_local_pinned_session_bytes(
    lines: list[str], rel: str, found: dict[str, str]
) -> None:
    """Flag a pinned session bound locally and then used with .bytes( ."""
    scopes = _analyze_scopes(lines)
    for i, line in enumerate(lines):
        m = _PINNED_SESSION_BIND_RE.search(line)
        if not m:
            continue
        var_name = m.group(2)
        active = scopes[i]

        # It is a stored property only if it lives directly inside a type body,
        # not inside a func/init/computed property.
        inside_func = any(s.kind in ("func", "init", "computed") for s in active)
        if not inside_func:
            continue

        # Find the enclosing func/init/computed scope; the .bytes( call must be
        # inside that same scope to be the same per-call usage.
        enclosing = next(
            (s for s in reversed(active) if s.kind in ("func", "init", "computed")),
            None,
        )
        end = enclosing.close_line if enclosing else len(lines) - 1
        bytes_re = re.compile(rf"\b{re.escape(var_name)}\s*\.\s*bytes\s*\(")
        for j in range(i + 1, min(end + 1, len(lines))):
            if bytes_re.search(lines[j]):
                key = _key(rel, line)
                found[key] = (
                    f"local pinned URLSession used with .bytes( "
                    f"— must be a class-level stored property (line {i + 1})"
                )
                break


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
            # Raw URLSession construction that is not the pinned factory. The
            # message is intentionally conditional: some call sites (e.g. general
            # web views) are not engine-bound, but any engine-bound raw session
            # must use the pinned factory.
            if (
                _URLSESSION_CTOR_RE.search(line) or _URLSESSION_SHARED_RE.search(line)
            ) and not _PINNED_SESSION_RE.search(line):
                key = _key(rel, line)
                found[key] = f"raw unpinned URLSession that may be engine-bound (line {idx + 1})"
                continue

            # Plain http:// to an engine host.
            http_m = _HTTP_ENGINE_RE.search(line)
            if http_m and _is_engine_url_literal(http_m.group(0)):
                key = _key(rel, line)
                found[key] = f"plain http:// URL to the engine (line {idx + 1})"
                continue

        # Per-call pinned session + .bytes SSE regression (#2605 / #2608).
        _check_local_pinned_session_bytes(lines, rel, found)

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
            "RemoteCertificatePinning.configuredSession() and, for SSE streaming, "
            "be retained as a class-level stored property. "
            "WKWebView challenge handlers must use the exact pinned signature. "
            f"Rule: {RULE_DOC} / #2606 / #2608."
        )
        return 1

    if stale:
        print("\n(KNOWN_VIOLATIONS has stale entries — clean them up when convenient.)")
        return 1

    print("\n✓ No unpinned engine transport or WKWebView signature regressions.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Engine-transport ratchet for the APP: no local FicheroClient without transportMode.

## The bug this catches (confirmed at runtime, WorkflowStore)

When the engine runs EMBEDDED it binds a Unix-domain socket (UDS), NOT TCP
`:8765`. The shared transport layer (`FicheroClient.makeTransport` /
`EngineConfig.transportMode`) picks UDS when embedded and HTTPS when remote.
`FicheroClient.init(...)` defaults `transportMode` to `.https`, so ANY app-side
store/service that builds a client for the LOCAL/default engine *without* passing
`transportMode: EngineConfig.transportMode` silently dials TCP `https://127.0.0.1:8765`
where nothing listens — failing with "Could not connect to the server" (errno 61)
even though the app is connected.

The confirmed symptom:
    Failed to load workflows: ... baseURL: https://127.0.0.1:8765 ...
    operationID: list_workflows_api_workflows_get   (Category: WorkflowStore)

Root cause: `LibraryManager` built the per-library shared `ficheroClient` with
`FicheroClient(baseURL: host.url, libraryPath: url.path)` — no `transportMode` —
so every generated service on that client (WorkflowService, etc.) dialed HTTPS.
The sibling legacy `APIClient` did it right (`transportMode: EngineConfig.transportMode`),
which is why `DocumentStore` (built on `APIClient`) worked and `WorkflowStore` did not.

## The rule

Any `FicheroClient(baseURL: ...)` construction in the app that targets the
LOCAL/default engine MUST pass `transportMode:` (normally
`EngineConfig.transportMode`). Legitimately-REMOTE constructions are exempt:
  * the cert-pinning initializer (`expectedSPKIPin:`) is HTTPS by design — a
    remote paired device is never reached over a local UDS;
  * failover-candidate / pairing probes to a DIFFERENT host (see ALLOWLIST).

Preview/test constructions use `FicheroClient(libraryPath:)` with no `baseURL:`
and are not matched (they never dial a real engine).

Usage:
    scripts/check_no_hardcoded_engine_base.py            # gate mode
    scripts/check_no_hardcoded_engine_base.py --list     # every construction, classified
    scripts/check_no_hardcoded_engine_base.py --self-test
    scripts/check_no_hardcoded_engine_base.py --help

Exit codes:
    0  no local FicheroClient missing transportMode (and no stale allowlist entries)
    1  an offender that would fail over UDS, or a stale allowlist entry to drop
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP_DIR = ROOT / "fichero" / "fichero"

_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_LINE_COMMENT = re.compile(r"(?<!:)//.*")

# `FicheroClient(` opening a constructor call.
_CTOR_OPEN = re.compile(r"\bFicheroClient\s*\(")

# Legitimately-REMOTE constructions that MUST stay HTTPS (never local UDS).
# Keyed by "relpath:line" of the `FicheroClient(` token, with a reason.
REMOTE_ALLOWLIST: dict[str, str] = {
    # Failover probe of a DIFFERENT paired host (not the local engine); the
    # default pinned session resolves that host's SPKI trust over HTTPS.
    "App/AppState+Heartbeat.swift:126": "remote failover-candidate probe (HTTPS pinned)",
    # Pairing to a remote device's apiRoot; UDS is meaningless off-box.
    "Services/PairingTypes.swift:111": "remote pairing apiRoot (HTTPS)",
}


def _code(text: str) -> str:
    text = _BLOCK_COMMENT.sub(lambda m: "\n" * m.group(0).count("\n"), text)
    return "\n".join(_LINE_COMMENT.sub("", line) for line in text.splitlines())


def _balanced_call(code: str, open_paren_idx: int) -> str:
    """Return the substring from '(' to its matching ')', inclusive."""
    depth = 0
    for i in range(open_paren_idx, len(code)):
        c = code[i]
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return code[open_paren_idx : i + 1]
    return code[open_paren_idx:]


def constructions(app_dir: Path = APP_DIR) -> list[tuple[str, int, str]]:
    """(relpath, line, call_text) for every FicheroClient(...) construction."""
    out: list[tuple[str, int, str]] = []
    for path in sorted(app_dir.rglob("*.swift")):
        s = str(path)
        if "/fichero-tests/" in s or "/fichero-ui-tests/" in s:
            continue
        rel = path.relative_to(app_dir).as_posix()
        code = _code(path.read_text(errors="ignore"))
        for m in _CTOR_OPEN.finditer(code):
            open_idx = m.end() - 1  # index of '('
            call = _balanced_call(code, open_idx)
            line = code.count("\n", 0, m.start()) + 1
            out.append((rel, line, call))
    return out


def offenders(app_dir: Path = APP_DIR) -> list[tuple[str, int, str]]:
    """Local-engine constructions missing transportMode (excluding allowlist)."""
    found: list[tuple[str, int, str]] = []
    for rel, line, call in constructions(app_dir):
        if "baseURL:" not in call:
            continue  # preview/test clients (libraryPath-only) never dial real engine
        if "transportMode:" in call:
            continue  # correctly routed
        if "expectedSPKIPin:" in call:
            continue  # cert-pinning initializer is HTTPS by design (remote)
        if f"{rel}:{line}" in REMOTE_ALLOWLIST:
            continue
        found.append((rel, line, " ".join(call.split())))
    return found


def _assert_logic() -> None:
    # The root-cause pattern is flagged.
    assert "transportMode:" not in "FicheroClient(baseURL: host.url, libraryPath: url.path)"
    # A correctly-routed construction is NOT an offender.
    good = "FicheroClient(baseURL: baseURL, libraryPath: libraryPath, transportMode: EngineConfig.transportMode)"
    assert "transportMode:" in good
    # Balanced-call parser handles nested parens / multi-line.
    code = "let c = FicheroClient(\n  baseURL: URL(string: \"x\")!,\n  libraryPath: p\n)"
    m = _CTOR_OPEN.search(code)
    call = _balanced_call(code, m.end() - 1)
    assert call.endswith(")") and "libraryPath" in call and "transportMode" not in call
    # A cert-pinned remote init is exempt.
    assert "expectedSPKIPin:" in "FicheroClient(baseURL: apiRoot, expectedSPKIPin: pin)"


def main(argv: list[str]) -> int:
    if "--help" in argv or "-h" in argv:
        print(__doc__)
        return 0
    if "--self-test" in argv:
        _assert_logic()
        print("check_no_hardcoded_engine_base self-test: OK")
        return 0

    _assert_logic()

    if "--list" in argv:
        for rel, line, call in constructions():
            if "baseURL:" not in call:
                tag = "preview/test (no baseURL)"
            elif "transportMode:" in call:
                tag = "OK (routed)"
            elif "expectedSPKIPin:" in call:
                tag = "OK (pinned/remote)"
            elif f"{rel}:{line}" in REMOTE_ALLOWLIST:
                tag = "allowlisted remote"
            else:
                tag = "OFFENDER"
            print(f"[{tag}] {rel}:{line}")
        print()

    bad = offenders()
    stale = sorted(
        k for k in REMOTE_ALLOWLIST
        if k not in {f"{rel}:{line}" for rel, line, _ in constructions()}
    )

    if not bad and not stale:
        print("Engine-transport ratchet (app): 0 local FicheroClient missing "
              "transportMode. All local clients follow EngineConfig.transportMode "
              "(UDS when embedded, HTTPS when remote).")
        return 0

    if bad:
        print("Engine-transport ratchet FAILED — local FicheroClient(baseURL:) built "
              "WITHOUT transportMode. These dial https://127.0.0.1:8765 and FAIL over "
              "UDS when the engine is embedded (errno 61 'Could not connect'). Pass "
              "`transportMode: EngineConfig.transportMode` (mirror APIClient / AppState), "
              "or route through the shared client. If the target is genuinely a REMOTE "
              "host, add it to REMOTE_ALLOWLIST with a reason:\n")
        for rel, line, call in bad:
            print(f"  {rel}:{line}\n      {call}")
    if stale:
        print("\nStale REMOTE_ALLOWLIST entries (construction moved/changed) — update them:")
        for k in stale:
            print(f"  {k}")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

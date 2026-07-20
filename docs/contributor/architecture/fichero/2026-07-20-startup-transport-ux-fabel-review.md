# Startup, Transport & UX — Fabel Review (2026-07-20)

Status: **approved direction, mapping for parallel build**. Owner: Daniel.

## Why

Two problems, one root. (1) The engine-connection state **takes over the whole
window** — `BackendRootGate` swaps the real UI for a full-window
`BackendConnectionView` splash/failure screen on every non-`.ready` phase. (2)
The embedded engine always binds **loopback TCP + TLS**, which (a) exposes a
port (→ `portConflict` failure class), (b) pays a TLS handshake on every local
connect, and (c) means a network listener is always up even with sharing off.

Measured (2026-07-20): engine **cold import is 2.11s**, not the stale 10.9s —
the lazy-import work already landed. So the startup bottleneck has **moved** off
the Python import and onto the spawn → uvicorn-ready → TLS-connect → readiness
chain, which UDS directly shortens.

## Goals

- **Never a full-window takeover.** Real UI renders immediately; engine status
  and activity live in the **toolbar** (Xcode-style), with failures shown as a
  toolbar error + recovery popover.
- **UDS-for-embedded, HTTPS-only-when-sharing.** Default = a Unix-domain socket,
  no port, no TLS, no network listener at rest. Sharing toggle brings up
  TCP+TLS (loopback / `tailscale serve`) for cross-device clients.
- **Portable & pythonic.** One FastAPI app; transport is uvicorn config only. No
  XPC (Apple-only, not HTTP, same-device-only). An Android/web/Linux front-end
  is "just another HTTPS client," identical to iPhone. Embedded and testing
  engines connect the same way.
- **Fast + honest.** Profile the *whole* path, cut the measured bottleneck.

## Transport decision (why UDS, not XPC)

Both UDS and XPC are **same-machine only**; anything cross-**device** must be
TCP/HTTPS. XPC additionally is Apple-only and is *not HTTP* — adopting it forks
the API off the OpenAPI contract and strands every non-Apple client. UDS keeps
one HTTP/FastAPI/OpenAPI contract and works on macOS + Linux (Windows falls back
to TCP loopback). So the split is by **locality**, not OS:

| Client | Transport |
|--------|-----------|
| Mac app ↔ local Mac engine | UDS (default) |
| Linux/web front-end ↔ local engine | UDS |
| iPhone / Android / remote → engine | TCP+TLS, only when **sharing on** |

The only new cost is on the Mac app's *local* path: `URLSession` can't dial a
UDS, so the Swift client needs a UDS-capable HTTP transport (custom
`URLProtocol` / SwiftNIO / a UDS↔loopback shim). Remote clients are unaffected.

## Sub-projects (built in parallel, disjoint lanes)

### S1 — Frontend startup UX (`fichero/…/Views`, SwiftUI)
- **Gate change** (`Views/Components/BackendRootGate.swift:36-50`): route
  `.starting` (and, once transport lands, the transient non-ready phases) to
  `content()` — the real `LibraryWindow` — instead of `BackendConnectionView`.
  Keep the `windowBackgroundColor` base layer (`FicheroApp.swift:210`) so there's
  no white flash.
- **Left toolbar status**: new `ToolbarItem(.navigation)` reading
  `appState.engine.phase` — spinner while `.starting/.checking`, error glyph on
  failure; click → popover with phase detail + Retry/reset/port-conflict actions
  (reuse `BackendConnectionView+Actions`). This replaces the full-window failure
  screen.
- **Right toolbar activity**: extend the existing `activityStatus` item
  (`ContentView+Toolbar.swift:85-99`) into a task popover aggregating
  `WorkflowExecutionObserver.activeExecutions` (N workflows) + per-library
  `ActivityStore.backendWork` (imports/batches/indexing) + ContentView import
  state. Reuse `BackendWorkPill` for rows.
- **Immediate-UI behaviour while `.starting`**: the shell renders; library data
  loads when `.ready` fires (`refreshAfterBackendBecameReady()` already exists).
  Actions that need the backend show a lightweight "starting…" affordance, not a
  blocking screen.
- **Hazard**: #3163 — the NSToolbar's first layout must not race a sheet
  presentation in the cycle the phase flips (`LibraryWindow.swift:35-45`,
  `firstRunSheetArmed`). Rendering the real UI on `.starting` means the toolbar
  lays out before `.ready`; the settle-beat guard must be preserved/extended.

### S2 — UDS transport (`fichero-engine` + `fichero/…/Services`)
- **Engine (Python)**: uvicorn binds a UDS by default
  (`--uds $XDG_RUNTIME/…/fichero-<lib>.sock`, 0600, user-owned). `remote_access`
  additionally binds loopback TCP + TLS (or `tailscale serve`) **only when the
  sharing toggle is on**. Delete the `portConflict` phase for the UDS path (no
  port → no conflict). One FastAPI app, transport chosen by config.
  Files: `remote_access_tls.py`, `discovery.py`, engine spawn env, and the
  sharing gate.
- **Swift client**: a UDS-capable HTTP transport for the local path — pick the
  smallest that keeps the OpenAPI/URLSession surface intact (evaluate: custom
  `URLProtocol` over `AF_UNIX`, SwiftNIO HTTP/1 client, or an in-process
  UDS↔127.0.0.1 shim). Client picks UDS when embedded+local, TCP+TLS when
  sharing/remote. Files: the client transport in `Services/` +
  `EmbeddedBackendService` / `EngineLifecycleController`.
- **Failure-model payoff**: removes `portConflict` from `EngineSession.Phase`,
  simplifying S1's error UX (design the failure UX once, post-S2).

### S3 — Full-path profiling + speedup (`fichero-engine`, then app)
- **Engine**: spawn-to-first-response timer + `py-spy`/`cProfile` on the real
  startup path (not just import). Defer the remaining eager heavy imports
  (`langchain_core` ~87ms, `apscheduler` ~85ms, the 2 eager tool modules) to
  first-use. UDS (S2) removes the TLS handshake from the connect leg.
- **App**: Xcode Instruments (App Launch template) — **needs Daniel at the
  machine**; I prep the engine-side numbers and the profiling checklist.

## Parallel execution & lane isolation

- **Lane E (engine transport, S2)**: `fichero-engine` uvicorn/remote_access/spawn.
- **Lane C (Swift client transport, S2)**: `fichero/…/Services` client + lifecycle.
- **Lane U (frontend UX, S1)**: `fichero/…/Views` gate + toolbar.
- **Lane P (profiling+imports, S3)**: `fichero-engine` imports (disjoint files
  from Lane E — imports vs bind), + app-profiling checklist for Daniel.

Lanes E/P both touch the engine but different concerns (bind vs imports) — keep
files disjoint or serialize the `api/main.py` edits. Every lane gates on the
full guardrail suite + both-platform build (Swift lanes) / full pytest (engine
lanes) before push, per house rules.

## Testing / invariants
- Transport: a test that the engine binds UDS by default and **no TCP port** is
  opened with sharing off; TCP+TLS appears only with sharing on. Fail-closed.
- Failure model: `portConflict` gone for UDS; `unreachable`/`authRejected` still
  surface (now in the toolbar).
- UX: `BackendRootGate` routes `.starting` → content (guardrail/snapshot).
- Speed: record before/after startup numbers in the PR.

## Deferred (separate)
- #19 login modal + iOS↔Mac PIN connect.
- #4029 Sparkle appcast 404 (private-repo raw URL) — infra, unrelated.

## Critic review — resolutions (2026-07-20)

A critic pass raised blockers that reshape S2's implementation. Resolutions:

- **[CRITICAL] Auth over UDS must NOT key off `request.client is None`.** Both the
  UDS server and the TCP+TLS server share one ASGI app + auth middleware, which
  can't tell which server delivered a request — and a misconfigured proxy /
  stripping middleware / ASGI test transport can produce `client is None` on the
  TCP path, which would then be mis-granted bootstrap-owner. **Fix:** wrap ONLY
  the UDS server's ASGI app to stamp `scope["fichero.transport"] = "uds"`;
  `_is_loopback_request` checks that positive marker, never `client is None`. TCP
  requests never carry the marker, so `test_posture_parity_matrix.py:77`
  (non-loopback → 401) still holds. This is the safe realization of the approved
  "trust UDS as loopback-owner" decision.
- **[CRITICAL] macOS App Store is BLOCKED for UDS** — no `application-groups`
  entitlement, so the sandboxed app + engine helper have disjoint containers and
  can't share a socket path; engine sandbox is on HOLD (#3340); and `sun_path`
  is capped at **104 bytes** (App Group paths exceed it). **Decision: ship UDS on
  the DMG (Dev-ID, non-sandboxed) target FIRST** at a fixed short path
  (`~/Library/Application Support/Fichero/fichero.sock`); MAS UDS is DEFERRED
  behind an App Group entitlement + #3340. Keep the MAS TCP entitlements until
  the App-Group UDS path is proven end-to-end.
- **[CRITICAL] Socket path channel spawner→engine is unspecified.** Add
  `FICHERO_UDS_PATH` (Swift spawner decides a short path, passes it in
  `buildChildEnvironment`); add `backendUDSPath: String?` to
  `EmbeddedBackendService`; the Swift transport dials it.
- **[HIGH] Lifespan fires twice with two servers.** Wrap the TCP+TLS server's app
  in a no-lifespan shim (intercept `lifespan.*`); only the UDS/primary server
  runs the real lifespan (DB open, Bonjour, migrations) — exactly once.
- **[HIGH] Stale UDS socket after a crash → respawn `EADDRINUSE`.** `unlink` the
  socket path before bind — engine-side (`Path(uds).unlink(missing_ok=True)`)
  AND a Swift respawn backstop. Both tested.
- **[HIGH] Swift UDS transport = SwiftNIO `ClientTransport`** over a
  `UnixSocketAddress`, injected at the `Client(transport:)` seam (+ a NIO SSE
  loop). The loopback-shim option is **ruled out** (re-introduces a local port).
- **[MED] Crash-loop guard = 5 crashes / 60s** (named constants; `CrashRecord`
  with timestamps, not a bare counter). Clear `intentionalStop` only AFTER the
  new PID is stored. On guard-fire, SIGTERM the last PID before surfacing
  `.failed`.
- **[MED] Mid-request socket drop:** the Swift UDS adapter maps
  `ECONNRESET`/`EPIPE` to retryable `.starting` (relaunch in progress) or
  `.unreachable`, surfacing "engine restarting", not a raw network error.
- **[LOW] Claim tightened:** UDS+relaunch removes `portConflict`, shortens the
  connect leg, and adds crash recovery — it is NOT a general fix for all launch
  failures (Briefcase import, missing bundle, DuckDB-open, bookmark denial
  remain).
- **iOS/iPad:** confirmed correct as-is — `allowsEmbeddedLocalDefault = false`;
  no UDS work needed. An in-process iOS engine (future) would use in-memory ASGI,
  not a socket.

### Build order (revised)
Lane E ships the engine UDS bind + auth marker + unlink + no-lifespan-shim +
`FICHERO_UDS_PATH`, gated by the FULL pytest suite (security/parity tests), as an
OPTION — the app keeps using TCP+TLS until Lane C (SwiftNIO transport) lands, so
nothing breaks mid-migration. Then flip the DMG default to UDS. MAS stays TCP
until App-Group + #3340.

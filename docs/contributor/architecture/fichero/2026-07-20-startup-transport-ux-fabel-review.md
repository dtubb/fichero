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

## Correction — macOS App Store is NOT blocked (2026-07-20)

The critic's "[CRITICAL] MAS blocked / needs App Group" is WRONG. The embedded
engine is launched as a real subprocess (`Process().run()`, engine at
`Contents/Helpers/Fichero Engine.app`) and `FicheroEngineAppStore.entitlements`
uses `com.apple.security.inherit` — the child inherits the parent's sandbox and
therefore runs in the **same sandbox container** as the main app. So the UDS
socket in the shared container is reachable by both processes with **NO App
Group entitlement**. UDS ships on DMG and MAS from the same design.

Remaining real constraint: `sun_path` ~104 bytes on macOS. Put the socket at a
SHORT container path — e.g. `<container>/Data/tmp/f.sock` (~62 chars) — not under
`Data/Library/Application Support/…`. Caveat (from the entitlements note):
sandbox inheritance passes only STATIC rights; the dynamic Powerbox / security-
scoped-bookmark grants for opening library files outside the container are NOT
inherited — but that's FILE access (already handled by bookmarks), not the
socket, which lives inside the container. Supersedes the App-Group line above.

## DECISION — pluggable ClientTransport, build all three (2026-07-20)

Resolved (Daniel): rather than pick one local transport, build a `ClientTransport`
abstraction with THREE pluggable implementations, selected by where the engine
is, and A/B-testable:

1. **UDS** — Mac local, works identically for an EMBEDDED (bundled subprocess)
   or a NON-EMBEDDED (external/dev/test) engine on the same machine. Crash-
   isolated, GIL-independent, SSE-native over HTTP.
2. **In-memory ASGI (PythonKit)** — Mac / iOS / iPad in-process. REQUIRED on iOS
   (no subprocesses). Swift embeds Python, calls the FastAPI ASGI app directly.
   No socket. Trade-off: in-process = engine crash → app crash, GIL shared with
   UI-serving calls, and SSE must be driven across the FFI. Building it lets us
   MEASURE those costs on macOS instead of assuming them, and macOS can switch to
   it by config in future.
3. **HTTPS** — remote / sharing. Portable baseline (URLSession + SPKI pinning,
   tailscale serve / loopback+TLS). Kept because Android/web/remote clients need
   it. Apple-specific alternatives (Network.framework, MultipeerConnectivity)
   exist but would strand non-Apple clients, so HTTPS stays the sharing default.

The APP code stays uniform (it talks to `ClientTransport`); only the impl differs
per context. Sharing is additive on top of any local transport (open the TCP+TLS
listener when sharing is on) — the engine never restarts to toggle it. This
supersedes the "UDS-only" framing above; UDS is transport #1 of three.

Lanes: E (engine UDS bind + TCP+TLS-when-sharing + auth marker) proceeds as-is —
UDS is transport #1. Swift Lane C becomes the `ClientTransport` protocol + the
three adapters (NIO-UDS, PythonKit-ASGI, URLSession-HTTPS); PythonKit adds a
dependency to evaluate. Each transport gets an interop/streaming(SSE) test so we
can compare them empirically.

## CONVERGED DECISION — UDS(Mac) + HTTPS(iOS/remote); PythonKit deferred (2026-07-20)

Three reviews (Claude critic, Claude red-team, codex/gpt). They split on one
premise: "does iOS force in-process?" The CODE settles it —
`EngineConfig.allowsEmbeddedLocalDefault` is `true` on macOS, **`false` on iOS**
→ iOS does NOT embed the engine; it connects to a Mac/remote engine over HTTPS.
So the red-team's "iOS forces in-process, build PythonKit anyway" premise is
false, and in-process becomes a net-new major project (embed CPython + native
wheels, Hardened Runtime / Library Validation / binary size / App Store), not a
free reuse. Codex + critic + the code converge.

**Decision — build `ClientTransport` with TWO production transports now:**
- macOS local → **subprocess + UDS** (Lane E, engine side done)
- iOS / remote / sharing → **HTTPS** (existing URLSession + SPKI pinning)
- **PythonKit + in-memory ASGI → deferred experiment**, revisited only if a
  real-device prototype proves the engine embeds acceptably AND the measurement
  below shows it wins.

**Retractions (were wrong above):** "iOS REQUIRED in-memory ASGI/PythonKit" — no,
iOS is HTTPS-to-remote. "PythonKit loses the OpenAPI typed client" — no: in-memory
ASGI returns JSON that decodes into the same generated Codable types (contract is
at the schema layer, not transport).

**Keepers (all reviews agree):** the `scope["fichero.transport"]` auth marker,
sharing-as-additive-toggle (no restart), the crash-loop guard, and the
`ClientTransport` abstraction.

**Landmines to honor:** `sun_path` is a BYTE limit + private parent dir; a UDS is
NOT authentication by itself — pair the marker with `0600` + ownership check +
stale-socket/replacement-race handling; verify helper signing/sandbox-inherit/
bundle-location on MAS AND DevID; `httpx.ASGITransport` may BUFFER SSE (gotcha if
PythonKit is ever tried); the transport abstraction must model streaming
(SSE/WebSocket) explicitly, not just request/response.

**Deciding experiment if PythonKit is revisited:** 20 clean release-build
launches; measure p95 launch-to-first-authenticated-API-response; any
crash/termination is a hard-fail gate. If in-process doesn't win materially,
don't carry it.

**Lane C (Swift) scope (revised):** `ClientTransport` protocol + a SwiftNIO UDS
adapter + the existing URLSession HTTPS adapter (streaming modeled explicitly).
NOT PythonKit now.

## DIRECTION LOCKED — build all three; default = in-memory shared Mac+iOS + HTTPS-on-sharing (Daniel, 2026-07-20)

Daniel's call: **build all three transports behind `ClientTransport`, decide the
Mac default later by measurement.** Preferred target model:
- **macOS + iOS share the SAME local transport: in-memory ASGI, in-process**
  (embedded CPython + `httpx.ASGITransport` against the FastAPI `app`). One local
  code path for both platforms.
- **Sharing toggle just ADDS a network transport (HTTPS/TCP+TLS)** — it switches
  nothing; the local in-memory path stays. When sharing is on, CLI/MCP/other
  local clients connect via that same HTTPS endpoint the app exposes.
- **UDS (subprocess) is built as the measured crash-isolation alternative** — the
  fallback if in-process crash-coupling proves unacceptable on the measurement.

The final Mac default (in-memory vs subprocess+UDS) is decided by: (1) the
iOS-wheel spike (is in-memory-on-iOS even possible), and (2) the 20-launch p95 +
crash-rate measurement. Until then, all three are first-class behind the seam.

### Honest trade recorded (what in-process costs)
in-memory wins: max security (no socket until sharing), shared iOS/Mac code, no
spawn/port/socket-path startup cost. It loses: crash-isolation (engine crash =
app crash, no restart — worst for duckdb/torch/onnxruntime which ABORT not
raise); independent CLI/MCP/headless (they need app running + sharing on);
memory-pressure coupling (iOS jetsam). And it can't DELETE the standalone engine
(sharing/remote/headless still need it) — so in-process is additive, not a
simplification. Net: elegance + security vs isolation + independence; measured.

### Implementation lanes (all additive behind the seam)
- **Seam:** `ClientTransport` Swift protocol that models STREAMING explicitly
  (SSE/WebSocket), not just request/response (codex landmine). One `send()` for
  unary + one `stream()` returning `AsyncThrowingStream`.
- **Adapter 1 — HTTPS** (cheapest): wrap the existing URLSession + SPKI-pinned
  client. Proves the seam. Also the sharing/remote transport.
- **Adapter 2 — UDS** (engine side landed, Lane E `89ae0fb85`): SwiftNIO UDS
  client. The crash-isolation option + measurement baseline.
- **Adapter 3 — in-memory ASGI via PythonKit** (the spike): embed CPython, load
  the FastAPI app, drive it with `httpx.ASGITransport`; bridge Python async-gen →
  Swift `AsyncThrowingStream` for SSE (verify ASGITransport doesn't BUFFER SSE —
  codex flag; if it buffers, stream via a direct app-call generator, not the test
  transport). Mac-buildable now (Briefcase wheels exist); iOS gated on the
  wheel spike.
- **iOS-wheel spike (running):** can duckdb/lance(Rust)/onnxruntime/torch build
  for iOS arm64. Vetoes or unlocks iOS in-process.

## iOS-WHEEL SPIKE RESULT — VETO: iOS in-process is NOT feasible (2026-07-20)

Research spike verdict: **iOS cannot embed the engine in-process.** The core
(non-prunable) native deps have NO iOS arm64 Python wheels and no realistic path
(6–12mo upstream porting each):
- **duckdb** — no iOS wheel; iOS DuckDB only via native Swift SDK (not callable from Python).
- **lancedb / pylance** (Rust) — no iOS wheel.
- **fastembed → onnxruntime** — no iOS *Python* wheel; iOS onnxruntime is a native C++/ObjC SDK only.
- **PyMuPDF** — no iOS wheel.
- pydantic-core / cryptography (Rust) — no iOS wheels either, but most tractable.

Useful side-finding: **pykeen/torch are already pruned** (commented out of the
Briefcase `requires`, in optional `.kg`/`.image` extras; all `import torch`/
`import pykeen` are lazy with 503 fallbacks). So torch was never the blocker —
the DB/vector/embed/PDF core is.

### What the veto changes
The headline benefit of the in-memory/PythonKit transport was **one shared local
code path across Mac + iOS**. That benefit is now DEAD — iOS physically cannot
run the engine in-process. So:
- **iOS = remote-HTTPS, permanently** (Tailscale serve / local network to a Mac
  or remote engine). Not a temporary limitation — it's iOS's dynamic-code +
  POSIX-process restrictions on the native extensions.
- **in-memory ASGI is macOS-ONLY** and no longer unifies anything.

### Reshaped recommendation (post-veto)
On Mac, the choice is in-memory vs UDS, and in-memory just lost its main reason
to exist. Remaining in-memory edge: no spawn latency + no socket (security).
Remaining UDS edge: **crash-isolation** (engine abort ≠ app crash — matters for
duckdb/onnxruntime which abort, not raise), independent CLI/MCP/headless, no
native-dep signing envelope, and it REUSES the standalone engine sharing needs
anyway. Post-veto, **UDS is the stronger Mac default.**

**Recommendation: ship UDS (Mac local) + HTTPS (iOS/remote/sharing). HOLD the
PythonKit in-memory lane** — build it only if UDS's measured startup/security
disappoints. Its cost (embed CPython, ASGITransport, SSE bridge, all native deps
in the app signing envelope) no longer buys the cross-platform win that justified
it. Awaiting Daniel's reconfirm before spending that lane — his "build all three,
iOS shares in-memory" instruction rested on the now-false iOS-in-process premise.

UDS Swift transport lane: IN PROGRESS (unblocked, needed in every scenario).

## DESIGN CONSTRAINT — transport is PER-LIBRARY-CONNECTION, not per-platform (Daniel, 2026-07-20)

The transport is NOT one-per-platform. A single app instance may hold multiple
open libraries, each with its own transport, concurrently:
- a local library (in-memory / UDS) AND a remote-shared library (HTTPS) at once;
- future: an iOS app with a *partial* in-process engine (only the deps that
  embed) for some capabilities + remote HTTPS for the heavy duckdb/onnxruntime
  path — "various things."

This maps onto the two-axis ownership model (app owns one engine PROCESS; each
LIBRARY owns its CONNECTION). The `ClientTransport` seam already supports it
because `FicheroClient` is per-instance — the transport is chosen when the client
for a library is built, not app-globally.

**Invariant:** `transportMode` is a per-instance property, never a static/global
switch. Build none of the variants now (YAGNI), but keep the seam per-connection
so local+remote-simultaneously and partial-local-iOS are not designed out.

## iOS PARTIAL-ENGINE EXPERIMENT — empirical boundary (2026-07-20)

Built + traced empirically (no simulator; static trace + live PyPI + throwaway venvs):

**Wheel nuance the survey missed:** it's not only the 4 heavy deps. pydantic-core,
cryptography, numpy (the *embeddable core*) have NO PyPI iOS wheels either — they
come from BeeWare's iOS wheel INDEX (not PyPI), which covers those three but NOT
duckdb/lancedb/onnxruntime/pymupdf. Pillow now ships official iOS wheels (PEP 730).

**Hard boot blocker:** `api/main.py:68 → from fichero.db import Database` →
`db.py:57 → import duckdb` (top-level, unguarded). The FastAPI app CANNOT import
without duckdb. PyMuPDF/fastembed are lazy (prunable); **duckdb is a top-level
hard requirement**. So a reduced bundle won't even boot until that import is made
lazy.

**Partial-engine map:** DuckDB is the spine of BOTH library data (`fichero.db`)
AND app state (`fichero.app_db`). 76 of 88 route modules touch DuckDB. Only ~10
duckdb-free routes (provider keys/models, orchestration, integrations, sandbox,
batch, research config) — the control plane, nothing persisted. So a partial iOS
in-process engine serves only "configure providers / talk to a remote engine" —
it buys almost nothing useful on its own.

**Briefcase multi-backend (Daniel's refinement) = correct mechanism:** a second
`[tool.briefcase.app.engineios]` app definition with reduced `requires` is the
clean expression; sketch captured. Not buildable today (top-level duckdb import +
numpy pins).

**iOS transport set = {in-memory-partial, HTTPS-remote}, NO UDS** — confirmed
(iOS can't spawn the subprocess UDS needs).

### Verdict + the real unlock
iOS is effectively **remote-only near-term.** A useful iOS in-process engine needs
TWO changes, neither built (both left as documented future work, NOT done now):
1. make `fichero.db`'s `import duckdb` lazy/optional so the app boots without it;
2. an in-memory / iOS persistence path — realistically **duckdb → sqlite** (LARGE:
   rewrite the data layer + FTS; the biggest cost and the true unlock), plus
   fastembed→CoreML (medium), pymupdf→PDFKit (medium), lance→sqlite-vec (medium-large).

Door held open (per Daniel: "maybe we pull the heavy deps up in future") — the
architecture (2nd Briefcase app + FeatureManager gating + per-connection transport)
expresses it; the cost is a data-layer swap, tracked not taken.

## PythonKit-Mac IN-PROCESS ASGI PROBE — VIABLE for unary, SSE cannot stream (2026-07-20)

Headless SwiftPM probe (throwaway, nothing added to repo). Swift → libpython →
imported the REAL `fichero.api.main` app → drove it with `httpx.ASGITransport` →
**200 with real health JSON, no subprocess, no socket.** Proven end-to-end.

- Cold import of the app in-process: **2.08s** (matches pure-Python ~2s — confirms
  the 10.9s figure was a red herring; the 2s import happens in-process OR
  subprocess either way, so in-memory's startup edge is only the spawn+socket
  handshake it avoids, NOT the import).
- Single in-memory request: **5.8ms**.
- duckdb (native C-ext) dlopen's fine inside the in-process interpreter on Mac.
  numpy/lance/pyarrow/torch are lazy (not loaded at app-import).

### THE caveat (codex's flag, now empirically confirmed with data)
`httpx.ASGITransport` (0.28.1, the engine's pin) **BUFFERS the whole response —
it does not stream.** Measured twice: an app emitting 3 chunks at 0.15s/0.4s
intervals delivered all 3 simultaneously only after full completion. So in-memory
ASGITransport **cannot back the engine's live SSE endpoints** (`change_stream.py`
— the reactive spine — plus activity/changes/batch/workflow_execution). Unbounded
streams (change stream) are effectively broken; bounded ones just buffer to the end.

### Signing
Headless worked via `PYTHON_LIBRARY`/`PYTHONHOME` to a homebrew framework Python.
A shipped app under hardened runtime needs the Python framework + all native wheels
embedded and signed with the app (Briefcase already does this — Daniel confirmed
"Briefcase signs them, it works") OR `disable-library-validation` (NOT viable for
MAS sandbox). GIL/asyncio was a non-issue (`asyncio.run` in a Python helper).

### Verdict
In-process ASGI-via-PythonKit is **viable and clean for request/response** (fast,
correct, no port/socket, max security). It **cannot serve SSE with
`httpx.ASGITransport` as-is** — that needs either (a) a bespoke in-memory transport
that pumps the ASGI `send` events incrementally into the Swift `HTTPBody` stream
(medium work), or (b) keeping a real socket (UDS/TCP) for streaming endpoints.
Because the change stream is the app's reactive spine, in-memory-only is
insufficient without (a).

## DECISION — UDS Mac-local (MAS+DMG) + HTTPS sharing/remote; in-memory = side experiment (Daniel, 2026-07-20)

"UDS for Mac (TestFlight/MAS + DMG), HTTPS for sharing, access by CLI/MCP —
user opens app, then the CLI works." Firm.

- **Mac local (both MAS/TestFlight and DMG): UDS.** App spawns+owns the engine
  (via Lane E `FICHERO_UDS_PATH`); app talks to it over UDS. **CLI/MCP connect to
  the SAME UDS socket locally** — Python `httpx` supports `transport=HTTPTransport(uds=...)`
  natively, so no HTTPS needed for local CLI. "Open app → CLI works."
- **Sharing / remote / iOS: HTTPS.** When sharing is ON, engine ALSO binds TCP/TLS;
  remote clients + iOS connect over HTTPS. Sharing is additive (does not switch the
  local UDS off).
- **iOS: HTTPS-to-remote** near-term. NOT a duckdb-move-off: DuckDB runs on iOS via
  `duckdb-swift` (native, same file format) — only the Python *binding* lacks an iOS
  wheel. Future iOS-local path = duckdb-swift native data layer ("duck→Swift shim"),
  tracked not taken. LanceDB→sqlite-vec/Apple vector on iOS.
- **In-memory / PythonKit: SIDE EXPERIMENT, kept alive.** Proven viable for unary on
  Mac. Key insight (Daniel): in-process you DON'T need HTTP-SSE — subscribe to the
  change stream directly via a PythonKit callback; the `httpx.ASGITransport` buffering
  is a client limitation, not fundamental. So the streaming "blocker" has a clean
  way around it in-process. Revisit as an optimization; not on the ship path.

### Transport → platform matrix (decided)
| Surface | Transport |
|---|---|
| Mac app ↔ its engine (MAS + DMG) | UDS |
| Local CLI/MCP ↔ engine | UDS (same socket) |
| Sharing / remote clients | HTTPS (TCP/TLS, additive) |
| iOS ↔ engine | HTTPS to a Mac/remote engine |
| (experiment) Mac in-process | in-memory ASGI via PythonKit + direct change-stream callback |

### UDS Swift lane status
Landed GREEN at the package level (branch `33b742366`: `TransportMode {.https/.uds}`
per-instance seam, `AsyncHTTPClientTransport` over `http+unix://`, 7 tests pass,
`swift build` clean). **HELD from main** pending an app-level Xcode build gate — it
adds the SwiftNIO stack (async-http-client/nio/nio-http2/nio-ssl) transitively; the
app build with those deps must be verified before merge. Nothing uses `.uds` yet
(default stays `.https`), so no rush.

## CONSTRAINT — maximal shared code + debuggable transport (Daniel, 2026-07-20)

"We really want to share code as well, for debugging." The `ClientTransport` seam
already delivers this: the transport is a thin bottom layer; EVERYTHING above it is
shared across all transports — generated OpenAPI `Client`, `AuthTokenMiddleware`,
library-path middleware, all Stores/Services — and the Python FastAPI engine is ONE
app driven identically over UDS / HTTP / in-process ASGI. A bug therefore reproduces
and debugs identically on any transport; you debug one path, not three.

**Debug workflow (keep #3042 Debug-external / Release-embedded, as a transport choice):**
| Build / context | Transport | Why |
|---|---|---|
| **Debug** | `.https` → external engine on `:8765` | most debuggable: separate process, attach Py debugger, live logs, independent restart |
| Release macOS | `.uds` (embedded engine) | production local |
| Local CLI/MCP | `.uds` (same socket) | "open app → CLI works" |
| iOS | `.https` (remote) | can't embed engine |
| Sharing/remote | `.https` (TCP/TLS, additive) | |
| Mac in-memory | in-process ASGI (PythonKit) | opt-in experiment |

Integration wiring MUST select the transport by build config + context (Debug ⇒
external HTTP), NOT hardcode one — so debugging always runs through the shared
stack against the most debuggable transport.

# Engine Startup & Shutdown Lifecycle — Design Spec (#TBD)

> Milestone: engine-startup-lifecycle
> Manual: TBD — contributor-facing only for now (this is app architecture, not a user-visible
> surface beyond "the app launches fast and never loses the engine").

> Design-led (Testing Constitution). Creative director owns intent; tests enforce it; code
> makes them pass. **Status: DRAFT — awaiting approval.** Legacy milestone "Engine - Connection
> & Startup Bulletproofing" (#110) accumulated 13 open issues, most descending from one 2026-07
> design review (#3947, "the app owns the engine"). This is Pass 1: the spec that review never
> got, written against the code as it stands today. Most of #3947's own design landed; this spec
> states precisely what did and what didn't, rather than restating the EPIC as still-future.
> Tags: **[OK]** built and tested · **[PARTIAL]** built, unproven or partly wired ·
> **[GAP]** intended, never built (needs an issue) · **[BROKEN]** regression, code
> contradicts the intent (needs an issue).
>
> **Territory this spec does NOT own — read first, cited not restated:**
> - `transport/transport-http-uds.md` — which TRANSPORT (`.https`/`.uds`/`.inMemory`) a client
>   dials and why. This spec assumes a transport is already chosen; it owns what happens before
>   and after that dial (spawn, readiness, respawn, shutdown).
> - `testing/test-environment-contract.md` and `testing/xcode-build-configs.md` — the UI-test
>   harness's own environment contract and Debug/Release/Dev-Embedded build-configuration rules.
>   This spec cites specific launch-path bugs the harness exposed, without restating the harness
>   contract itself.
> - `ai/provider-keys.md` — API-key persistence, verification, and the Keychain-and-engine sync
>   fix. This spec notes only that keys are pushed to the engine as part of the connect sequence
>   (`EngineLifecycleController+ProviderKeys.swift`), not how keys themselves are stored/verified.

## Why a new spec, not a fold

Read all four existing specs above before writing this one. None of them owns the subject #110's
13 issues are actually about: **the engine process's own start/respawn/stop lifecycle and who
drives it.** Transport is "which pipe"; the harness contract is "how a test's environment
differs from a real launch"; provider-keys is "how a credential is stored." None describes
`EngineLifecycleController` itself, the ownership model that decides which recovery buttons a
user may see, or the readiness handshake that gates change streams — that subject has no spec.
This is a genuinely new spec, not a thin wrapper that should have folded elsewhere.

## Intent (the design)

Exactly one object, owned by the app (not any window or scene), controls the engine process's
entire life: start it once at launch, know when it is ready, respawn it within a bounded budget
if it drops, and stop it once at quit. A window never triggers a connection event and never
decides whether it may show a "Restart" button — that decision is a pure function of **how this
engine came to exist** (spawned locally vs. adopted vs. remote), computed once and read
everywhere. The two ownership axes stay separate and don't leak into each other: **the app owns
the process** (is it alive, should it respawn); **the library owns the connection** (is a
specific library's own state loaded, granted, and safe to use). A user of the app's own local
engine is never asked to sign in, never sees a login gate, and is never shown a control for a
capability they don't have (a "Restart" button on an engine they didn't spawn is a lie).
Deterministic, typed failure everywhere: a denial from the engine carries its reason to the
screen that shows it; nothing "fails healthy."

**Two facts from this week, recorded as evidence for why this discipline matters, not as
history:**
- A missing *undeclared* dependency (`pytz`) made every workflow run-status read fail with a 500
  while the engine's own health probe stayed green (fixed 670772e77) — proving "healthy" can mean
  nothing more than "the process is alive and answering `/health`," never "every route works."
  The readiness handshake this spec documents answers "is the engine up," not "is every route
  correct" — that gap is real and worth naming rather than assuming health-checks cover it.
- The engine imports `knowledge/readable.py` at load time, reached transitively through the
  render routes wired into `api/main.py` — so a broken import anywhere in that module's chain
  stops the ENTIRE engine from starting, not just the KG-readable-representation feature. A
  single feature module's import error is a full-startup failure, an architectural fact worth
  stating explicitly rather than discovering it live.

## Grounding: what #3947's design actually built (verified against HEAD, 2026-09-19)

`EngineLifecycleController` (`fichero/fichero/Services/EngineLifecycleController.swift`) exists,
is `@MainActor`/`@Observable`, and is owned by `FicheroAppDelegate` (`FicheroApp.swift:26`) — an
app-scoped singleton, not a window or scene property. It composes:
- `backendService: EmbeddedBackendService` — the process half (spawn/watch/stop).
- `appState: AppState` — the connection half (readiness probe, auth, heartbeat).
- `libraryManager: LibraryManager` — the open-library manager.

**Started from `applicationDidFinishLaunching`, stopped from `applicationWillTerminate`**
(confirmed by direct comment and code at `FicheroApp.swift:15`, `:28`) — exactly #3947's
structural ask, not a window's `.task`. `shouldReuseExistingConnection`
(`EmbeddedBackendService+Lifecycle.swift:85`) — the reuse guard #3947 explicitly said to delete
— still exists in source but has **zero call sites** outside its own definition (confirmed by
grep): dead code, not a live bug, but not physically removed either.

**Ownership** is a pure, derived-once function (`EngineOwnership`,
`EmbeddedBackendService+Ports.swift:11`) — `.ownedEmbedded` / `.adoptedExternal` — computed from
`(strategy, transportMode, portResolution)`, not `#if os` or a UI heuristic. This is a SIMPLER
two-case model than #3947's proposed three-way `.supervised | .externalLocal | .remote`, but it
achieves the same governing property: "which buttons may exist" is read from one derived value,
not scattered per-view guesses.

**Auto-respawn with a bounded, backing-off budget** is built:
`handleSupervisedBackendDropped` (`EngineLifecycleController.swift:96-153`),
`supervisedAutoRestartAttempts = 3`, exponential backoff (`1 << (attempt - 1)` seconds), a
crash-budget check (`shouldAutoRestartAfterCrash`), and a pure decision function
(`shouldShowBackendDropModal`) deciding when the Retry/Quit modal may appear. Tested:
`BackendDropAutoRestartTests` (7 `@Test` cases, `fichero/Tests/Unit/general/App/
BackendDropAutoRestartTests.swift`) — covers auto-restart with no diagnosis, dev-command
visibility per strategy, modal suppression while ready, modal suppression before the retry
budget is exhausted, and modal surfaced immediately on crash-budget exhaustion.

**Port conflict stays an in-window decision** (`handlePortConflict`,
`EngineLifecycleController.swift:338-346`) — matches #3947's explicit "keep it" ruling (#3111).

**Main-thread blocking during launch is fixed**, not merely claimed: `waitForPortToClear`,
`resolvePortConflict`, and the TLS-material prep path are all `async`, running their actual
blocking `Process`/`waitUntilExit`/poll work inside `Task.detached(priority: .userInitiated)`
(`EmbeddedBackendService+Ports.swift`, `EmbeddedBackendService+TLS.swift`) — the TLS file's own
comment states the intent directly: "so it can run off the @MainActor in a detached task without
blocking first frame" (citing #3936, the fix issue for #3928's defect).

**The embedded-launch UI-test carve-out is fixed and unified**: `FicheroApp.swift:182-190`'s own
comment names #3968 directly and describes the fix — the two competing predicates (an inline
check here, a second one in `currentEngineProvisioningInputs`) were replaced with ONE shared
predicate, `suppressesBootSideEffectsForUITesting()`, so embedded-engine UI-test mode is no
longer accidentally caught by the general `isUITesting()` carve-out that used to suppress the
very engine spawn those tests exist to exercise.

## What did NOT land

- **Transactional library open/close** (#3989) — **NOT built.** `LibraryManager` still tracks
  `loadedLibraryIds`/`loadingLibraryIds` as separate `Set<UUID>` properties
  (`LibraryManager.swift:46-47`, `LibraryManager+Helpers.swift`), the exact anti-pattern #3989
  describes ("ready→loaded→closed... is not transactional... separate, unsequenced steps").
  `grantedLibraryIds` (a third set #3989's own text names) was not found at all — either already
  consolidated away or never existed under that name; not independently confirmed either way
  this pass. No single `loadState` enum exists.
- **182-site dropped error body** (#3931) — **BROKEN, and worse than filed.** The issue's own
  count (182 call sites discarding the engine's error detail via `case .undocumented(let
  statusCode, _)`) is now **216** (`grep -c` against `fichero/fichero/`, run fresh this pass) —
  the class grew, it did not shrink.
- **UDS-default at rest** (#4037) — **NOT built.** `transport/transport-http-uds.md`'s own
  behavior table lists `.https` as the DEFAULT transport; UDS is an explicit override
  (`FICHERO_FORCE_UDS`/`FICHERO_FORCE_UDS_PATH`) used for Dev Local and the UI-test harness, not
  the engine's own at-rest listen socket. uvicorn binding a Unix-domain socket by default (no TCP
  port, no `portConflict` failure class at all) — this issue's actual ask — has not landed.
- **Byte-identical DMG/MAS engine parity guard** (#3982) — **NOT built.** No script under
  `scripts/` implements the "add a parity guard" ask (a release/preflight check asserting both
  targets embed matching `.pyc` sets from the same staged source). The issue's own text says the
  underlying goal is "already mostly met" structurally (both targets stage from the same bundle)
  — this spec did not re-verify that structural claim, only that no automated guard exists.
- **Bundle trim: litellm/botocore** (#3929) — **NOT built.** `litellm` remains a declared
  dependency in `fichero-server/pyproject.toml`; it was not vendored down to a pricing-only JSON
  table or made a lazy import as the issue proposed.
- **Launch Time-Profiler hangs** (#3979, #3980) — **unverified, not gradable from source alone.**
  Both are Instruments-trace findings (two main-thread hangs ~601ms/991ms; a 729ms atfork static
  init; a deferrable 384ms Sparkle-framework map) that need a fresh profiling run to confirm
  fixed or still present — reading the launch-path source cannot establish whether a specific
  hang backtrace still fires. Recorded as open, pending re-profiling, not asserted either way.
- **Sandboxed "Dev Embedded" App Store footgun** (#3993) — **not independently re-verified this
  pass.** Confirming whether the `Fichero (App Store)` target still lists a "Dev Embedded"
  buildable configuration (the reported footgun) requires parsing `project.pbxproj`'s target→
  configuration-list mapping precisely; this pass did not complete that check and states so
  rather than guessing from a partial grep.
- **Live-updates-paused reconnect UX** (#3403) — **partially this spec's territory, partially
  not.** The readiness/reconnect BACKEND loop (heartbeat, backoff, when the engine is considered
  "up") is `EngineLifecycleController`'s job and IS built (see `HeartbeatLowersAlarmTests`,
  `SpawnedEngineLivenessWaitTests`). The UI-visible pause banner itself
  (`LiveUpdatesPausedPill.swift`) and the per-store pause/resume state live in
  `ObservableDomainStore` and its change-stream extensions — that half belongs to the
  not-yet-written `harness/observable-data-layer.md` (row 17, queued). This issue likely needs
  splitting across both specs once both exist; not decided here.
- **New-window re-authentication / spinning connection screen** (#3362) — **likely fixed as a
  side effect of the app-scope move, not independently pinned.** Since the engine connects once
  at `applicationDidFinishLaunching` and windows only observe (`EngineSession` is the shared
  observable phase, `EngineLifecycleController`'s sole writer), a new window opening can no
  longer itself trigger a reconnect or token rotation — the mechanism the issue describes no
  longer exists in the code. No test specifically pins "opening a second window does not
  re-authenticate," so this is stated as a strong structural inference, not a verified fact.

## Behaviors

### A. Ownership and the app-scoped controller

- `engine.owned-by-app-not-window` — **[OK]** (→ #3945) `EngineLifecycleController` is
  owned by `FicheroAppDelegate`, started from `applicationDidFinishLaunching`, stopped from
  `applicationWillTerminate`; no `WindowGroup`/scene owns or triggers it. Pinned:
  `StartupWorkGateTests` ("engine spawn is triggered from the AppDelegate, not a window .task",
  "main WindowGroup observes UI without owning backend lifecycle"). The historical reuse-guard
  workaround (`shouldReuseExistingConnection`) is confirmed dead code (zero call sites), not
  deleted — see `engine.dead-reuse-guard-not-removed` below.
- `engine.ownership-is-a-pure-function` — **[PARTIAL]** (→ #3947, → #4057) `EngineOwnership`
  (`.ownedEmbedded`/`.adoptedExternal`) is derived once from `(strategy, transportMode,
  portResolution)`, not `#if os` or a view-level heuristic — the governing property the EPIC
  wanted is real. Pinned: `PortConflictDecisionTests` ("release embedded spawn is owned and stopped on
  quit", "release embedded user-approved adoption is external and left running", "dev UDS engine
  is owned so app quit tears it down", "adopted Debug HTTPS engine remains external", "configured
  and inert strategies never own lifecycle"). Not full parity with the EPIC's own proposed shape:
  two cases, not the three-way `.supervised | .externalLocal | .remote` split (which would also
  encode a genuinely remote Mac/iOS client, not just local-embedded-vs-adopted). Whether a third
  case is still needed for the remote-client class of "which buttons may exist" decisions was not
  re-checked this pass.
- `engine.dead-reuse-guard-not-removed` — **[GAP]** (→ #3947) `shouldReuseExistingConnection`
  still exists in source with zero callers — the EPIC's own explicit instruction ("Delete the
  WindowGroup `.task` and `shouldReuseExistingConnection` with it") is half-done: the `.task`
  trigger is gone (confirmed), the dead function it left behind is not.

### B. Respawn, port conflict, and the crash budget

- `engine.auto-respawn-bounded-backoff` — **[OK]** (descends from the app-owns-the-engine EPIC
  above, whose own tracking issue stays open — not cited here for that reason) a supervised
  backend drop
  auto-restarts within a bounded budget (3 attempts, exponential backoff), with a pure function
  deciding when the Retry/Quit modal may show. Pinned: `BackendDropAutoRestartTests` (7 cases:
  `releaseEmbeddedDropAutoRestarts`, `releaseEmbeddedCannotConnectDiagnosisNoDevCommand`,
  `debugExternalKeepsDevHint`, `remoteAndInertDropsHaveNoDevCommand`, `modalSuppressedWhenReady`,
  `modalSuppressedUntilAttemptsExhausted`, `modalSurfacedWhenCrashBudgetExhausted`).
- `engine.port-conflict-is-a-user-decision` — **[OK]** (→ #3111) a process holding the
  engine's port that this app didn't spawn surfaces as an in-window decision
  (`handlePortConflict`), never silently adopted or silently killed. Pinned:
  `PortConflictDecisionTests` ("foreign holder + no decision → surface the portConflict phase,
  never adopt or spawn", "portConflict is a non-ready phase with a PID-bearing diagnosis (renders
  the connection view, not blank)").
- `engine.launch-path-never-blocks-main` — **[OK]** (fixed via → #3936) the port-clear
  poll, orphan-engine sweep, and TLS-material preparation all run inside
  `Task.detached(priority: .userInitiated)`, off the `@MainActor`, during launch. Pinned:
  `StartupWorkGateTests` ("the TLS-prep subprocess is dispatched off the main actor", "the launch
  TLS-prep function is nonisolated, keeping its blocking wait off-main"). The shutdown path's own
  synchronous wait (`applicationWillTerminate` must block for graceful shutdown) is deliberately
  unchanged and out of scope for this behavior.
- `engine.embedded-uitest-carve-out-unified` — **[PARTIAL]** (→ #3968) the boot-side-effect
  suppression predicate for UI tests is now ONE function,
  `suppressesBootSideEffectsForUITesting()`, so embedded-engine UI-test mode is no longer
  accidentally caught by the general test carve-out that used to suppress its own engine spawn —
  confirmed by direct code read (`FicheroApp.swift:182-190`) but no dedicated unit test for this
  specific predicate was found this pass, and the issue's own UI tests
  (`ColdLaunchReachesLibraryUITests`, `LaunchPerformanceUITests`) were not re-run to confirm they
  now pass end to end.

### C. Readiness, health, and the change-stream handshake

- `engine.health-green-does-not-mean-every-route-works` — **[BROKEN, ongoing risk, no single
  fix]** (→ #4874, filed this pass) recorded as a standing architectural fact, evidenced this
  week: a missing declared dependency (`pytz`) made every workflow run-status read return 500
  while the top-level health probe stayed green (fixed 670772e77). No behavior in this spec
  claims the readiness handshake validates more than "the process is up and answering" — stated
  here so a future reader doesn't assume health-green implies route-correct.
- `engine.readable-py-import-is-a-startup-single-point-of-failure` — **[GAP, architectural fact]**
  (→ #4875, filed this pass) the engine imports `knowledge/readable.py` transitively through the
  render routes wired into `api/main.py` at load time — a broken import anywhere in that
  module's own dependency chain stops the ENTIRE engine from starting, not just the
  KG-readable-representation feature. Whether this deserves import isolation (lazy-import per
  route group) or is an acceptable cost of a monolithic FastAPI app is an open question for
  whoever owns this spec's approval, not decided here.
- `engine.provider-keys-pushed-every-connect` — **[PARTIAL, cross-referenced, not restated]**
  (→ #4534; see `ai/provider-keys.md` for the pinning, not duplicated here) `finishSuccessfulConnect`
  pushes app-owned provider keys to the engine on every successful connect
  (`supplyProviderKeysToEngine`, `EngineLifecycleController+ProviderKeys.swift`) — the mechanics
  of key storage/verification, and that spec's own test citation, are that spec's territory.
- `engine.reconnect-heartbeat` — **[OK]** (pre-existing) heartbeat-driven liveness with alarm
  suppression on recovery. Pinned: `HeartbeatLowersAlarmTests`,
  `SpawnedEngineLivenessWaitTests` (`fichero/Tests/Unit/general/App/`,
  `fichero/Tests/Unit/general/Transport/`).
- `engine.live-updates-pause-ux` — **[GAP, split territory]** (→ #3403) the connection-level
  reconnect loop above is built; the UI-visible "Live updates paused" banner and per-store
  pause/resume state (`LiveUpdatesPausedPill.swift`, `ObservableDomainStore`) are NOT this
  spec's own behaviors — they belong to `harness/observable-data-layer.md` (queued, not yet
  written). Recorded here only so this issue isn't silently dropped from every spec's view.
- `engine.new-window-does-not-reauthenticate` — **[PARTIAL, structural inference, not pinned]**
  (→ #3362) since only the app-scoped controller writes `EngineSession` and windows merely
  observe, a new window opening cannot itself trigger reconnect or token rotation by
  construction — but no test specifically exercises "open a second window, assert no
  reconnect/no token change," so this is inferred from the architecture, not proven by a named
  test.

### D. The library connection axis (separate from the engine process axis)

- `engine.library-load-not-transactional` — **[GAP]** (→ #3989) the library open/load/close
  lifecycle is still ad-hoc: `LibraryManager` tracks `loadedLibraryIds`/`loadingLibraryIds` as
  separate `Set<UUID>` properties (`LibraryManager.swift:46-47`) rather than one explicit
  per-library `loadState` (`unopened → granting → loading → loaded | failed(Error) → closing →
  closed`). This is the LIBRARY half of the two-axis ownership ruling — the app owns the
  process (built, see section A above); the library owns its own connection state (not built).
  A `grantedLibraryIds`-style third set, named in the issue's own text, was not found under that
  name this pass — not confirmed consolidated away or never existing.

### E. Typed errors, not silent fallbacks

- `engine.error-detail-reaches-the-caller` — **[BROKEN]** (→ #3931) 216 call sites (up from the
  issue's own count of 182, re-measured fresh this pass) discard the engine's error body via
  `case .undocumented(let statusCode, _)` — the underlying taxonomy
  (`AccessError.classify(statusCode:body:)`, `DenialBody.decode`) exists and works; these sites
  simply never feed it. A 403 with a `detail` explaining exactly why (e.g. "Library path is not
  in an allowed location") is unreportable at these sites — the user gets a generic failure. The
  issue's own guidance (fix the shared generator/helper seam, not a 216-site hand-sweep) still
  stands.

### F. Distribution and bundle hygiene (P3, not urgent)

- `engine.dmg-mas-byte-identical-guard` — **[GAP]** (→ #3982) both app targets stage from the
  same bundle path today (structurally sound per the issue's own read), but no automated parity
  guard exists to keep a future config change from silently shipping two different engines; not
  built.
- `engine.bundle-trim-litellm` — **[GAP]** (→ #3929) `litellm` (+ the AWS SDK it drags in via
  `botocore`, ~84 MB) remains a full dependency though project policy says LLM calls route
  through langchain providers and litellm is used for pricing-lookup ONLY; not vendored down or
  made lazy.
- `engine.launch-profiler-hangs` — **[GAP, unverified without re-profiling]** (→ #3979, → #3980)
  two main-thread hangs (~601ms, ~991ms) and a 729ms atfork static-init cost were measured by
  Instruments 2026-07-17; whether they still fire needs a fresh trace, not a source read.
- `engine.sandboxed-dev-embedded-footgun` — **[GAP, unverified this pass]** (→ #3993) whether the
  `Fichero (App Store)` target still exposes a sandboxed "Dev Embedded" configuration (the
  reported footgun — selecting it silently rejects `~/code` libraries) was not conclusively
  re-checked against `project.pbxproj`'s current target/configuration mapping this pass.
- `engine.uds-default-at-rest` — **[GAP]** (→ #4037) the engine's own at-rest listen socket is
  still HTTPS/TCP by default (per `transport/transport-http-uds.md`'s own behavior table); the
  uvicorn-binds-UDS-by-default design (removing the `portConflict` failure class entirely at
  the source) has not been adopted. This is the one item in this milestone that most overlaps
  `transport-http-uds.md`'s territory — cited there, not duplicated as a competing claim; that
  spec's own maintainers should decide which spec's milestone eventually owns the fix.

## Fold plan for the 13 issues (Pass 2 — plan only, NOT executed this pass)

**Move onto #318 (engine-startup-lifecycle):**
- #3945 (referenced throughout, not itself one of the 13 — the earlier PR1 issue #3947 sequences
  from) — not applicable, not on this milestone.
- #3928 → `engine.launch-path-never-blocks-main`
- #3931 → `engine.error-detail-reaches-the-caller`
- #3947 → `engine.owned-by-app-not-window`, `.ownership-is-a-pure-function`,
  `.dead-reuse-guard-not-removed`, `.auto-respawn-bounded-backoff`,
  `.port-conflict-is-a-user-decision` — the umbrella EPIC, cited from every behavior descending
  from it rather than one line of its own.
- #3968 → `engine.embedded-uitest-carve-out-unified`
- #3979, #3980 → `engine.launch-profiler-hangs`
- #3982 → `engine.dmg-mas-byte-identical-guard`
- #3929 → `engine.bundle-trim-litellm`
- #3989 → `engine.library-load-not-transactional`
- #3993 → `engine.sandboxed-dev-embedded-footgun`
- #4037 → `engine.uds-default-at-rest` (cross-referenced against `transport-http-uds.md`)

**Redirect / split, not moved outright:**
- #3403 → half stays here (`engine.live-updates-pause-ux`, cross-reference only), half waits on
  `harness/observable-data-layer.md` once written — do not move the issue itself until that
  spec exists and can take a real citation.
- #3362 → tentatively this spec (`engine.new-window-does-not-reauthenticate`), but as a
  PARTIAL/inferred behavior with no pinning test — a Pass 2 executor should decide whether to
  write that test before moving the issue, or move it now and note the test as follow-up work.

**Net effect if Pass 2 executes as planned:** #110 would drop from 13 open to 0 — every issue
either fits directly or is a deliberate split/cross-reference, unlike prior folds in this
program. No issue here is recommended for closure by this pass; several (#3928, #3947's own
respawn/ownership/main-thread pieces, #3968) are strong verify-close candidates once Pass 2 runs
and posts evidence.

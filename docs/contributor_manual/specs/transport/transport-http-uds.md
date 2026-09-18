# Engine Transport: HTTPS / UDS / in-memory — Design Spec (#4486)

> Milestone: transport-http-uds
> Manual: docs/contributor_manual/guide/16-the-embedded-engine.md

> Design-led (Testing Constitution). **Status: APPROVED — 2026-09-09.** Rewritten into
> template format from `agent-work/status/2026-08-04-uds-harness-4437.md` and the code contract
> in `Services/EngineConfig+Launch.swift`. Tags: [OK] built · [PARTIAL] built/unproven · [MISSING].

## Intent (the design)

The app dials its local engine over exactly one of three transports, chosen once at client
construction, and every transport delivers the SAME result for the same request — reads, writes,
and change-stream events. A developer or a test can redirect the local transport by env var
without code changes; a hermetic UI test's explicit transport wins even over a saved remote host.
The contract lives in `EngineConfig.transportMode` / `localDebugTransportOverride`
(`fichero/fichero/Services/EngineConfig+Launch.swift`) and the engine side in
`fichero-server/src/fichero_server/api/uds_transport.py`.

## The three transports (verified in code)

| Transport | Selector | Trust | Use |
|-----------|----------|-------|-----|
| `.https` (default) | none — URLSession, cert-pinned where configured | TLS / token | normal launch, remote host |
| `.uds(path:)` | `FICHERO_FORCE_UDS_PATH=/path` or `FICHERO_FORCE_UDS=1` (app-computed socket) | owner-trusted, no TLS | Dev Local, the UI-test harness |
| `.inMemory` | `FICHERO_FORCE_INMEMORY` (macOS) — PythonKit in-process | in-process | `⌘R` embedded-engine dev |

Rules: in-memory wins if both env flags are set; a configured remote host keeps `.https` EXCEPT
under `--uitesting`, where the test's explicit transport owns the launch (so a developer's saved
remote host can't redirect a hermetic test).

## Behaviors

- `transport.default-https` [OK] — no override → `.https`, cert-pinned where configured.
  Pinned: `EngineTransportModeTests.noOverrideReturnsNil`.
- `transport.uds-path` [OK] — `FICHERO_FORCE_UDS_PATH` → `.uds(path:)`; owner-trusted, no token.
  Pinned: `EngineTransportModeTests.forceUDSPathDialsUDSLocally`.
- `transport.uds-computed` [OK] — `FICHERO_FORCE_UDS=1` → app-computed container socket.
  Pinned: `EngineTransportModeTests.forceUDSFlagUsesComputedPath`.
- `transport.inmemory-wins` [OK] — both flags set → `.inMemory`.
  Pinned: `EngineTransportModeTests.inMemoryWinsOverUDS`.
- `transport.uitest-owns` [OK] — `--uitesting` transport beats a saved remote host.
  Pinned: `EngineTransportModeTests.uiTestUDSOverrideWinsOverRemoteHost`.
- `transport.same-result` [PARTIAL] (#4789, → #2383) — engine gives identical read/write results across transports.
  Verified 2026-09-09: the gated suite's **equivalence sweep only parametrizes `uds_engine` +
  `https_engine`** (`test_transport_round_trips.py:179-200`); **in-memory is NOT in the sweep**. So
  the cross-transport invariant is proven for UDS+HTTPS but NOT extended to in-memory. → #2383:
  a THIRD gap in the same family — `WKWebView` (the KG web panes) does not participate in
  Fichero's pinned remote transport at all, so remote KG panes are disabled fail-closed rather
  than routed through the same pinned transport every other surface uses.
- `transport.inmemory-contract` [MISSING] (#4790) — the `.inMemory` transport the app actually uses is
  **PythonKit in-process**, and it has **no contract test**. `test_in_memory_asgi_round_trip()`
  (:209) exercises an ASGI in-memory app and its own comment admits it does NOT cover the
  Swift/PythonKit in-process claim. This is the gap the creative director flagged: bind a test that
  puts in-memory into the same equivalence sweep (ASGI level, gated) and, separately, a Swift-side
  test for the real PythonKit path.
- `transport.event-delivery` [MISSING] — a `claim.updated` change-stream event reaches the **Swift**
  client over each transport; the engine round-trip proves the engine, not the Swift client's
  stream. **Corrected citation (2026-09-18): the tracking issue is #4511** ("no Swift test executes
  here: the FicheroTests host dials a live engine at launch"), replacing a previous mis-citation to
  an unrelated, already-closed ClaimStore-write-path survey (caught by `spec_pipeline.py`'s rule
  b). #4511 is still OPEN, so this remains blocked until it lands.

## Test matrix

| Leg | This surface? | Pins | File |
|-----|---------------|------|------|
| Pure rule (Swift) | y | `localDebugTransportOverride` precedence table | `fichero/Tests/Unit/general/Transport/EngineTransportModeTests.swift` (corrected 2026-09-18 — the file was renamed since this row was written) |
| Backend (pytest) | y | same read/write result across UDS/HTTPS/in-memory | `fichero-server/tests/integration/test_transport_round_trips.py` (exists, 7 passed) |
| Swift event-delivery | y | change-stream event arrives at the Swift client per transport | `fichero/Tests/Unit/**/…StreamTests.swift` (#4511) |

Hard-gate: `transport.same-result` (the cross-transport invariant) + `transport.uitest-owns`
(the harness depends on it).

## Housekeeping (from the agent-work source)

- The superseded standalone `transport-tests/` duplicate is **already removed** (after
  `f915441f7`), so there is no dead copy to delete — the gated
  `fichero-server/tests/integration/test_transport_round_trips.py` is the one that runs.

## Open questions

1. `transport.event-delivery` (#4511): write the Swift change-stream test — is the MainActor
   default-isolation fix (landed for `FicheroTests`, MEMORY
   `test-target-needs-mainactor-default-isolation`) enough to unblock #4511, or does #4511 need
   its own re-verification first? (Tracked; not this pass.)

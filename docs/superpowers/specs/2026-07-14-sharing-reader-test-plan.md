# Test Plan: Sharing / Pairing / Reader (2026-07-14)

**Deliverable of the research pass. A worker executes this plan; this document contains no test code.**
Scope: milestone #263 issues #3769, #3772, #3774–#3778, #3787–#3791, plus #3765 (Reader).
Everything below was verified against the tree at `3f091fbb4` (integrate worktree) on 2026-07-14. All `file:line` citations were read, not assumed. The Python suites named in §2 were **run** (results inline).

---

## 0. The standard: "would this have caught #2399?"

Issue #2399 ("tappable pair link") was closed while completely dead. The app minted `fichero://` links (`fichero/fichero/Models/SessionStore.swift:45,177,191`), had Copy/ShareLink buttons, and had full receive handlers on both platforms (`FicheroApp.swift:123-142,329-330`, `FicheroApp_iOS.swift:117-127`) — but `CFBundleURLTypes` was registered nowhere, so the OS never delivered a tapped link. Every piece was individually plausible; the **coupling** was dead. Nobody exercised the round trip.

The fix (PR #3793) shipped with `fichero/fichero-tests/URLSchemeRegistrationTests.swift`, which asserts against `Bundle.main` in the test host — i.e. against the **built product's merged Info.plist**, the thing the OS actually reads — not against source. That is the correct shape, and this plan generalises it.

**Acceptance rule for every test proposed here:** state what breaking looks like, and answer *"if the feature were silently dead the way #2399 was, would this test go red?"* Three classes of test pass that bar:

1. **Runtime/product assertions** — assert what the *built artifact* claims (plist keys, entitlements, bundled resources), because the OS acts on the artifact, not the source.
2. **Cross-boundary contract tests** — one test that spans a seam (Swift↔engine, template↔injected JS, mint↔redeem), using the *production* code on both ends, so the two sides cannot drift apart with each side's own suite still green.
3. **True end-to-end** — real process, real transport, real OS delivery. Expensive, so used sparingly and gated; but this is the only layer that fully proves "a tapped link opens the app". Be honest where only this layer can catch a failure.

Tests that assert "the code says what the code says" (mocking both sides of the seam, or restating a constant) are explicitly rejected below where they were tempting.

---

## 1. Ground truth: what exists and works today

### 1.1 Verified state of the features under test

| Fact | Evidence |
|---|---|
| `fichero://` scheme IS now registered (both a URL type with scheme `fichero` and `NSBonjourServices` `_fichero._tcp`) | `fichero/fichero/Info.plist:20-29,41` (post-#3793) |
| macOS receive path handles pairing links now | `FicheroApp.swift:123-142` ("pairing link received"), `:329-330` |
| iOS receive path shows a confirm sheet before pairing | `FicheroApp_iOS.swift:75,117-127` |
| iOS manual-entry path exists ("Enter Link Manually") | `FicheroApp_iOS.swift:399,703` |
| Pair persists four values: token→Keychain, SPKI pin, host→UserDefaults, library path→UserDefaults (+ token expiry for renewal) | `RemoteClientPairing.persistPairedHost`, `fichero/fichero/Services/RemoteClientPairing.swift:166-186` |
| **Keychain write sets NO `kSecAttrAccessible`** (candidate cause of #3772) | grep of `fichero/fichero-api-client/Sources/FicheroAPIClient/AuthTokenMiddleware.swift` — zero hits |
| Device-token auth is fail-closed: unknown/revoked/expired token or inactive user → error string → 401 | `fichero-engine/src/fichero/api/auth.py:435-456` (`_authenticate_device_token`) |
| Last-owner guarantee: sole owner cannot revoke own role; a second owner can remove the first | `fichero-engine/src/fichero/authz.py:128-142` |
| Invite TTL is a single global 15-minute constant; no channel concept; **no redemption notification exists** | `fichero-engine/src/fichero/api/routes/auth_accounts.py:31` (`INVITE_TTL`), endpoints at `:463-609` (mint/list/redeem/revoke only) |
| `PairingBlocker` (#3769 fix) exists with 7 cases, each carrying its own headline/detail/action — but it is **`private`**, hence currently untestable | `fichero/fichero/Views/Settings/Engine/BackendSettingsRemoteAccessSection.swift:374-438` |
| The Backend settings pane's existence hangs on a feature flag that **defaults to `false`** and is flipped only by `resetToV001()` | `fichero/fichero/Models/FeatureManager.swift:84-85,209,334` |
| Reader fix (#3765) landed: the Page tab now renders the real multi-page WebKit transcript | `fichero/fichero/Views/Reader/Page/ReadingPaneView.swift:372-387` (`surfaceView(tab: .transcript)`) |
| Transcript HTML is built **client-side by JS in the engine's template** — `<div class="transcript">` wrapping `<article class="transcript-page" data-page=…>` | `fichero-engine/src/fichero/api/templates/document_view.html:649-663` (`renderTranscript`) |
| Swift injects JS that queries the selector `.transcript [data-page]` for scroll↔page sync | `fichero/fichero/Views/Reader/Knowledge/DocumentKGWebPane.swift:339,412-416` |
| Multi-page concatenation lives in the engine | `fichero-engine/src/fichero/api/routes/views.py:37-49` (`_transcript_for_document`) |

### 1.2 Run infrastructure facts that constrain this plan

- **CI is Ubuntu-only**: Python lint + unit tests (ML skipped) + OpenAPI/feature-tier drift (`.github/workflows/ci.yml:22-27,54-63`). **No Swift test runs anywhere automatically.** Swift tests run only when the manager runs `RunAllTests` via the Xcode MCP.
- The Swift unit-test bundle uses `TEST_HOST = Fichero.app` (stated in `URLSchemeRegistrationTests.swift` header) — running it **launches the app GUI**. Standing rule: never on Daniel's active desktop; manager-gated, or a future macOS CI leg (§8 Q6).
- Backend pytest needs `PYTHONPATH=fichero-engine/src` from the worktree being tested (`AGENTS.md:24,158`); the shared venv is editable-installed elsewhere.
- Only one xcodebuild at a time on this machine; iOS builds happen in a worktree (memory: iOS build gate).

---

## 2. Where the existing suites are blind

### 2.1 Engine suite (`fichero-engine/tests/`) — strong on policy, blind at the transport and the client

**Run on 2026-07-14** from the integrate worktree:

```
PYTHONPATH=…/integrate/fichero-engine/src pytest tests/unit/test_invites.py \
  tests/unit/test_pairing_self_service.py tests/unit/test_device_auth_boundary.py \
  tests/integration/test_device_pairing_e2e.py -q
→ 18 passed in 48.53s
```

What it genuinely covers (all green today):

| File | Covers |
|---|---|
| `tests/integration/test_device_pairing_e2e.py` | remote pair → browse library; reject pairing without HTTPS; reject without SPKI env; reject revoked & expired device tokens; reject non-loopback bootstrap (`:88-238`) |
| `tests/unit/test_device_auth_boundary.py` | pair-code rejects missing/invalid/expired tokens without secret leak; malformed requests stay 4xx; Bonjour TXT hints do not authenticate (`:59-133`) |
| `tests/unit/test_invites.py` | mint is owner-only; redeem creates account + session; **single-use**; **expiry**; invalid token; list + revoke (`:65-203`) |
| `tests/unit/test_pairing_self_service.py` | non-owner pairs own device / owner revokes; deactivated user cannot mint; non-owner cannot revoke another's device |
| `tests/unit/test_authz_revoke_edge_cases.py` | revoke→denied immediately; idempotent; **sole owner cannot self-revoke; second owner can remove the first** (`:69-118`) |
| ~20 further `test_authz_*` adversarial suites | escalation, ACL, concurrency, snapshot leaks |

**Where it merely *appears* to cover:** the file named `test_device_pairing_e2e.py` is **not end-to-end**. It uses FastAPI `TestClient` — in-process ASGI with a synthetic `base_url="https://paired.example"` and a spoofed `client_addr` (`:53-59,73-79`). The "SPKI pin" is a literal env string `"c3BraS1waW4="` (`:33`). **No socket is opened, no TLS handshake happens, no certificate exists.** It proves route *policy* (excellent), and proves nothing about whether a real server starts, binds loopback, presents the right certificate, or whether the app's payload format matches what these routes parse. That is precisely the layer where #2399-class bugs live.

Additional engine blind spots:
- `test_routes_views.py:90` asserts transcript **text** appears in the response; nothing asserts the `documentData` page structure the client-side `renderTranscript` consumes, nor the `.transcript`/`data-page` markup contract the Swift-injected JS depends on.
- No test of invite **rate limiting** in `test_invites.py` (grep "rate" → zero hits; `_check_invite_rate_limit` exists at `auth_accounts.py:287`). Verify whether another suite covers it; if not, it's a gap (a 6-digit/short token without tested rate limiting is a paper control — same concern #3778 raises).
- No test that an **inactive user's still-valid device token** is denied (`auth.py:452-454` implements it; confirm coverage in `test_multiuser_accounts_dont_flip.py`, else add — see T-D4).

### 2.2 Swift suite (`fichero/fichero-tests/`) — surprisingly strong per-component, zero cross-boundary

Genuinely good, verified by reading the test lists:
- `RemoteCertificatePinningTests.swift:32-251` — **real self-signed certificates**: accepts pinned cert, rejects wrong pin, host-scoped pins, session-delegate trust paths, loopback pin bootstrap/refresh. This is real security testing, not mocks.
- `RemoteAccessConfigTests.swift:27-412` — QR payload round trip, invite-link fields, rejects localhost payloads / missing SPKI / missing library path, `persistPairedHost` stores library path, host-switch rollback restores previous host.
- `PairedHostEndpointsTests.swift:21-192` — endpoint ordering, failover, "absent pin yields nil trust, not a fallback".
- `RemoteClientPairingInviteLinkTests.swift` — invite link mint/parse, malformed rejection.
- `URLSchemeRegistrationTests.swift` — the built-product scheme claim (the model for §3-R).
- `AuthTokenMiddlewareStorageTests.swift`, `DeviceTokenRenewalTests.swift`.

**Blind spots:**
1. **Nothing ever talks to the engine.** Every Swift test runs against fixtures. The payload the Mac mints and the payload `pairing.py` parses are each tested against their *own* idea of the format. If they drift, both suites stay green — the exact #2399 topology.
2. **No restore-after-relaunch test** (#3772). `persistPairedHost` writes are tested; no test reconstructs paired state *purely from persisted values* through the production read paths.
3. **No Keychain attribute assertion.** Nothing pins `kSecAttrAccessible` — and indeed the production code sets none (§1.1).
4. **`PairingBlocker` is untested and untestable** (private).
5. **URL parse→act routing untested**: no test feeds `fichero://pair?...` / `fichero://invite?token=...` through the handlers' routing logic (the logic is embedded in `handleOpenURL` / `.onOpenURL` closures — no seam).
6. **Only the macOS host product is asserted.** `URLSchemeRegistrationTests` runs in the macOS test host; nothing asserts the **iOS** product or the **Mac App Store target** (three distribution targets exist) claims the scheme.
7. **Reader reachability untested**: nothing pins "the Page tab renders `KGSurfaceTab.transcript`" — the regression #3765 describes (transcript unreachable for months while the engine kept building it) had no tripwire, and the fresh fix at `ReadingPaneView.swift:387` has none now.

---

## 3. Layered strategy

Five layers. Each behaviour lands in the *lowest* layer that would actually catch its failure mode — and the plan says explicitly when a lower layer would lie.

### Layer P — Python engine tests (pytest, runs in CI on every push)
Policy and contract: auth decisions, invite lifecycle, authz, route payload shapes. Cheap, deterministic, already the strongest layer. **Additions here are mostly consolidation + a few named regressions.**

### Layer PL — Python *live-server* tests (pytest, marked `live_server`, manager/CI-gated)
NEW. Spawn a **real uvicorn process** the way the product does (mirror `start_backend.sh` env / the embedded-spawn path, per `check_swift_transport.py`'s invariants and memory "connection transport invariants"), on an ephemeral loopback port, with **real TLS material from `remote_access_tls.py`**. Then do mint→redeem→authenticated-call over a **real HTTPS socket with SPKI verification computed from the actual served certificate**. This is what the misnamed `test_device_pairing_e2e.py` is not. Headless, no GUI — safe on this machine, but slow; keep it out of the default unit run (marker + `FICHERO_RUN_LIVE_SERVER=1`, matching the existing write-suite flag convention, `AGENTS.md:158`).

### Layer S — Swift XCTest unit tests (manager-gated `RunAllTests`; test host launches the app GUI)
State machines, parsers, persistence read/write paths, copy tables. **Constraint acknowledged:** these do not run on every push anywhere; they run when the manager gates. Anything here is therefore "caught at gate time", not "caught at commit time" — fine for regressions, not a substitute for Layer P where the logic could live engine-side.

### Layer R — Runtime/product assertions (Swift XCTest against `Bundle.main` / the process, inside Layer S runs)
The generalised #3793 pattern — assert the **built artifact**:
- `CFBundleURLTypes` claims `fichero` (exists — `URLSchemeRegistrationTests`).
- `NSBonjourServices` contains `_fichero._tcp` (`Info.plist:41`) — without it, iOS local-network Bonjour browsing dies silently: same disease, different key.
- iOS: `NSLocalNetworkUsageDescription` present (Bonjour prompts require it; absence = silent discovery failure).
- Entitlements of the running host via `SecTaskCopyValueForEntitlement(SecTaskCreateFromSelf…)`: sandbox network-client; when #3789 lands, the keychain sharing prerequisites (`kSecUseDataProtectionKeychain` behaviour, access group).
- Release-config only: the embedded engine payload is present in the bundle (builds on `EmbeddedBackendServiceStartGuardTests.swift`; Debug intentionally runs the engine externally — memory "Debug engine external, Release embedded").
- **Fresh-install reachability of the pairing surface**: with empty `UserDefaults`, the pane that hosts pairing must be enabled — today `settings_backend_tab` defaults `false` (`FeatureManager.swift:84-85`), i.e. a failed migration hides the whole surface (#3776's finding). Write this test alongside #3776's flag deletion; it fails on today's code, which is correct — it encodes the decided behaviour.
- **Multi-target guardrail (script, not XCTest):** `Bundle.main` only ever tests the TEST_HOST target. Add `scripts/check_product_plist_keys.py` (pattern: `check_swift_transport.py`) asserting every shipped target's Info.plist/pbxproj carries `CFBundleURLTypes`+`fichero`, `NSBonjourServices`, and the iOS usage strings. Honesty: a source-level check alone would NOT have caught #2399 in principle (a plist that never reaches the build), so this script is a *complement* to the runtime test (which proves one target end-to-end), covering the targets the runtime test can't reach.

### Layer X — Cross-stack contract tests (Swift XCTest against a live engine; env-gated)
NEW, and **the centrepiece — this is the layer that would have caught #2399's class.** A small `XCTestCase` family (working name `PairingRoundTripContractTests`) that is `XCTSkip`ped unless `FICHERO_CONTRACT_ENGINE_URL` is set, and that the manager runs during the cross-stack gate he already performs "one Xcode, the backend on :8765" (`AGENTS.md:16`). It uses **production code on both ends**: the real payload builder, the real decoder, the real `PairingService` exchange, the real engine. See T-A1.

### Layer E — OS-delivery end-to-end (gated; the only honest proof of "tap a link → app acts")
- **iOS:** `xcrun simctl openurl booted "fichero://pair?..."` against the app installed in a Simulator, then assert the app reached the confirm-pair state (launch-argument-controlled probe or XCUITest). Requires a booted Simulator = GUI; **must run in the iOS build-gate worktree arrangement or a CI macOS runner — never on Daniel's active desktop.**
- **macOS:** `open "fichero://invite?token=…"` → app activates and shows the redeem gate. Launches the GUI; same constraint.
- Until that leg exists, these two are items 1–2 of the **manual checklist (§6.4)** — stated as manual, not pretended to be covered by Layer S.

### Layer M — Manual checklist (what cannot honestly be automated)
Kept deliberately short; every item names *why* it can't be automated. §6.4.

---

## 4. Behaviour → test table

Legend: layer P / PL / S / R / X / E / M per §3. "Breaks like" = what a red run means. Every row's final column answers the #2399 question.

### A. Pairing round trip (behaviour 1)

| # | Behaviour | Layer | File (new unless noted) | Asserts | Breaks like | Catches #2399-class? |
|---|---|---|---|---|---|---|
| T-A1 | **Full round trip**: owner mints pair code → production QR/link payload built (`RemoteAccessConfig` builder) → production decoder parses it → `RemoteClientPairing` exchanges it at the live engine → `persistPairedHost` → a client built **from the persisted values only** calls `/api/health` + lists documents, 200 | X | `fichero/fichero-tests/PairingRoundTripContractTests.swift` | every seam at once: payload format, scheme, engine route, pin canonicalisation, persistence, authenticated call | payload/format drift between Swift and `pairing.py`; route rename; pin normalisation change; persistence key drift | **YES — this is the test #2399 never had.** If any link in the chain is dead, it's red |
| T-A2 | Same round trip at the transport level: real uvicorn + real TLS from `remote_access_tls.py`, mint→redeem→authed call over a real HTTPS socket, pin computed from the served cert | PL | `fichero-engine/tests/live/test_pairing_live_server.py` | server actually starts, binds loopback only, serves the advertised cert; redeem works over real TLS; **wrong pin → handshake refused**; no token → 401 | startup wiring, middleware order, TLS material generation — everything `TestClient` fakes | YES for the server half — a server that never starts or serves the wrong cert is exactly "dead on arrival" |
| T-A3 | Device appears in `/api/pairing/devices` after redeem; revoke from that list kills the token immediately | P (mostly exists: `test_pairing_self_service.py:42`) + X (assert via T-A1 harness) | existing + T-A1 file | list/revoke round trip from the client's perspective | revocation UI acting on a stale/different store | Partially — the X leg adds the client's view |

### B. URL scheme round trip (behaviour 2)

| # | Behaviour | Layer | File | Asserts | Breaks like | Catches #2399-class? |
|---|---|---|---|---|---|---|
| T-B1 | Built app claims `fichero` scheme | R | **exists**: `URLSchemeRegistrationTests.swift` | `Bundle.main` CFBundleURLTypes | someone deletes the plist entry | YES (it is the #2399 fix's own test) |
| T-B2 | All shipped targets (macOS DMG, Mac App Store, iOS) claim the scheme + Bonjour keys | R-script | `scripts/check_product_plist_keys.py` | per-target plist/pbxproj keys | registration added to one target only (#3788 requires both) | Mostly — source-level, but multi-target; paired with T-B1 |
| T-B3 | URL → action routing: `fichero://pair?payload=…` → pair action; `fichero://invite?token=…` → invite action; garbage/`FICHERO://`/percent-encoded → correct or safely ignored, never crash; **macOS routes `pair` (the #3788 gap 5)** | S | `DeepLinkRoutingTests.swift` — **requires extracting the routing from the `handleOpenURL`/`.onOpenURL` closures into a pure `DeepLinkRouter` (prod change, see §8 Q1)** | URL→enum mapping, both platforms' tables | "macOS ignores fichero://pair" regression; parser drift from minted format | Partially — it pins parse+act, but not OS delivery |
| T-B4 | Minted link and router agree: feed `SessionStore`'s minted invite link and the pairing card's minted link **strings** into the router from T-B3 | S | same file | mint side and parse side use one format | mint format changes without the parser (or vice versa) | YES for the format seam — the two sides can no longer drift silently |
| T-B5 | **OS actually delivers a tapped link** | E | gated E2E leg / manual §6.4 | `simctl openurl` / `open` reaches the confirm state | anything between LaunchServices and the sheet | **YES — the only full proof.** Everything above narrows the gap; this closes it |

### C. Persistence across relaunch — #3772, live bug (behaviour 3)

| # | Behaviour | Layer | File | Asserts | Breaks like | Catches #2399-class? |
|---|---|---|---|---|---|---|
| T-C1 | **Cold-start restore**: write the four values via the production persist path (scratch `UserDefaults` suite + test keychain), then reconstruct paired state using **only the production read paths** (`EngineConfig.orderedConnectionCandidates` — already injectable, `EngineConfig.swift:127-137` — token read, pin read, library path read). Assert all four independently — the issue's four-value diagnostic, as a test | S | `PairedStateRestoreTests.swift` | restore chain end to end within the process; failure names the missing value | key rename, keychain query mismatch, candidate-ordering regression that discards the saved host | YES within process scope — it exercises write→read as a round trip, not each half against its own fixture |
| T-C2 | Keychain item attributes: after `persistRemoteToken`, `SecItemCopyMatching` with `kSecReturnAttributes` shows an **explicit** `kSecAttrAccessible` (recommend `AfterFirstUnlock`, §8 Q5) | S | `AuthTokenMiddlewareStorageTests.swift` (extend existing) | the attribute is set deliberately | **fails on today's code** (no attribute set — §1.1); written first, red, then the #3772 fix makes it green | YES — it asserts the artifact-level property (what iOS will actually enforce), not the code's intent |
| T-C3 | Re-probe/rollback never clobbers a healthy saved host; `rollbackFailedHostSwitch` already tested (`RemoteAccessConfigTests.swift:241`) — add: failed probe of the saved host must not erase the four values (unreachable ≠ unpaired) | S | `PairedStateRestoreTests.swift` | offline relaunch keeps paired state | "can't reach host → wipe pairing" class of bug | Partially |
| T-C4 | Real-device relaunch (incl. reboot-then-launch-before-first-unlock) | M | §6.4 | the OS actually returns the token under real lock states | pre-unlock read failure the simulator can't reproduce faithfully | honest manual |

### D. Fail-closed security (behaviour 4)

| # | Behaviour | Layer | File | Asserts | Breaks like | Catches #2399-class? |
|---|---|---|---|---|---|---|
| T-D1 | Unknown token → 401; revoked → 401; expired → 401; non-loopback bootstrap refused; no-HTTPS pairing refused | P | **exists**: `test_device_pairing_e2e.py:130-238`, `test_device_auth_boundary.py` | the `auth.py:435-456` ladder | any rung removed | n/a (already good) — action: tag all with a `fail_closed` pytest marker so the pack is runnable/auditable as one gate |
| T-D2 | Empty device set / unpaired remote → 401 (the `auth.py:439-441` behaviour the brief cites) | P | verify named coverage in `test_fresh_launch_authz.py`; add an explicitly-named regression if it's only incidental | fresh engine + remote caller with no devices → 401 | a default-open regression | n/a |
| T-D3 | Wrong SPKI pin → connection refused, at **real TLS** level | PL + S | T-A2 case + **exists**: `RemoteCertificatePinningTests.swift:145` | handshake fails; no fallback trust | pin check weakened/bypassed | YES (PL leg): a client that "works anyway" with a wrong pin is a silently-dead security control |
| T-D4 | Deactivated user's still-valid device token → 401 (`auth.py:452-454`) | P | confirm in `test_multiuser_accounts_dont_flip.py`, else add to boundary suite | user-deactivation reaches device auth | account disable not propagating | n/a |
| T-D5 | Guardrails stay in gate: `check_swift_transport.py` (pinned sessions, HTTPS-only, SSE delegate retention) | R-script | **exists**: `scripts/check_swift_transport.py` | no raw URLSession to engine, etc. | transport regressions | n/a |
| ⚠ | Note the standing memory rule: if any new gate-red **conflicts with a shipped adversarial auth test, HOLD for Daniel** — do not flip an auth-perimeter assertion to make a suite green | — | — | — | — | — |

### E. Pairing card never blank — #3769 (behaviour 5)

| # | Behaviour | Layer | File | Asserts | Breaks like | Catches #2399-class? |
|---|---|---|---|---|---|---|
| T-E1 | Every `PairingBlocker` case has a non-empty, **distinct** headline and detail; recoverable cases (`engineNotRunning`, `sharingNotStarted`, `pinNotDerived` — `BackendSettingsRemoteAccessSection.swift:435-437`) have an action label. Make the enum `CaseIterable` and iterate, so a new case cannot ship copy-less | S | `PairingBlockerTests.swift` — **requires `private` → `internal` + `CaseIterable` (prod change, §8 Q1)** | copy table completeness; no case reuses the old lie ("needs HTTPS" while the engine is down) | new blocker case added with placeholder/duplicate copy | Partially — copy alone can't prove visibility |
| T-E2 | **Totality of the gate matrix**: extract the blocker-derivation into a pure function `(engineRemote?, engineRunning?, hostingStarted?, address-state, pin-state) → PairingBlocker?` and table-test **all combinations**: every non-ready combination yields a *specific* blocker (never nil-and-hidden), and the fully-ready combination yields nil (card shows QR). Assert precedence (engine down beats address problems — the honest headline requirement) | S | same file — requires the extraction (§8 Q1) | the card is structurally incapable of "silently absent": nil is only reachable in the ready state | re-introduction of a gate that hides instead of explains (#3769's original disease) | **YES** — #3769 was a silent-absence bug; this makes silent absence unrepresentable in the derivation. Residual risk (view ignores the derivation) covered by one manual/E check |

### F. Reader transcript — #3765 (behaviour 6)

| # | Behaviour | Layer | File | Asserts | Breaks like | Catches #2399-class? |
|---|---|---|---|---|---|---|
| T-F1 | Multi-page assembly: parent doc with N pages → `_transcript_for_document` concatenates all pages in sequence order (partially exists: `test_routes_views.py:90`); extend to assert the **embedded `documentData`** carries per-page structure with correct page numbers/order (that JSON is what `renderTranscript` consumes) | P | extend `test_routes_views.py` | the data contract feeding the JS renderer | ordering regression, page filtering bug | Partially |
| T-F2 | **Template↔Swift selector contract**: the engine template's `renderTranscript` emits `class="transcript"` wrapper + `data-page="…"` articles (`document_view.html:656-661`) and the Swift-injected JS queries `.transcript [data-page]` (`DocumentKGWebPane.swift:339,412`). A guardrail script extracts both literals and fails if either side drifts | R-script | `scripts/check_transcript_anchor_contract.py` | the cross-repo-half coupling that scroll↔page sync (#3226) hangs on | someone restyles the template (recently: #3683/#3684 CSS work) and the anchors vanish while both suites stay green | **YES** — this is a #2399 topology (two live halves, dead coupling), caught cheaply. Honest limit: only a WKWebView run proves the *behaviour*; this proves the contract can't silently drift |
| T-F3 | **Reachability**: the Reader's Page tab renders `KGSurfaceTab.transcript` (the fix at `ReadingPaneView.swift:387`), and the Knowledge-tab clamp (`:367`) can never clamp the Page tab's transcript away. Needs the tab-mapping expressed as a testable value (small extraction, §8 Q1) | S | `ReaderSurfaceMappingTests.swift` | the transcript surface is wired into a reachable tab; the clamp's domain excludes it | the exact regression #3765 documents (transcript orphaned for months, engine still building it) | **YES in spirit**: the audit doc §6 showed capability intact + client orphaned = dead feature, nobody noticed. This is the tripwire that was missing |
| T-F4 | WebKit actually renders anchors + scroll sync follows | E/M | manual §6.4 (or a future WKWebView harness — non-goal for now, §7) | real DOM behaviour | JS errors at runtime | honest manual |
| T-F5 | Scale smoke: `_transcript_for_document` with ~1,000 pages stays linear/fast (guard against accidental quadratic string building) | P | extend `test_routes_views.py` (bounded, no ML) | the 10,000-file promise doesn't rot | O(n²) concat creeping in | No (perf, not liveness) — optional, cheap |

### G. Invites — #3790 (behaviour 7)

| # | Behaviour | Layer | File | Asserts | Breaks like | Catches #2399-class? |
|---|---|---|---|---|---|---|
| T-G1 | Single-use, expiry, revoke, owner-only mint, invalid token | P | **exists**: `test_invites.py:65-203` (ran green) | lifecycle policy | — | n/a |
| T-G2 | Invite mint **rate limiting** (`auth_accounts.py:263-306`) — verify coverage exists; add if not | P | `test_invites.py` extend | repeated redeem attempts locked out | brute-force window opens silently | n/a |
| T-G3 | **When #3790 lands**: per-channel TTL — mint(channel=email) → 24h, mint(channel=qr/messages) → 15m; redeem at +16m succeeds for email, fails for qr; channel stored on the invite | P | `test_invites.py` extend | the TTL is per-channel, not a raised global | "just raise INVITE_TTL" shortcut (explicitly forbidden by the issue) | n/a |
| T-G4 | **When #3790 lands**: redemption **notification** — redeeming produces an observable notification record (activity/event API), and the email-TTL path cannot be enabled without it. Encode Daniel's condition as one test: mint(email) succeeds **iff** the notification wiring is active | P | `test_invites.py` extend | the 24h window ships only with its compensating control | notification quietly dropped while 24h TTL stays | **YES** — this is a "condition attached to a decision" that would otherwise erode silently |
| T-G5 | Fresh-install invite payload carries host + SPKI (the #3788 secondary gap: today `SessionStore.swift:191-198` redeems against the *current* client, which a fresh install lacks) — contract-test the link payload once implemented | S + X | `RemoteClientPairingInviteLinkTests.swift` extend + T-A1 harness | an invite can onboard a device with no prior state | invite that only works where it's not needed | YES — that gap *is* a dead-on-arrival feature today |

### H. Users — #3787 (behaviour 8)

| # | Behaviour | Layer | File | Asserts | Breaks like | Catches #2399-class? |
|---|---|---|---|---|---|---|
| T-H1 | Last-owner guarantee at the engine | P | **exists**: `test_authz_revoke_edge_cases.py:111,118` | `authz.py:128-142` | — | n/a |
| T-H2 | Add/edit/remove user via the API surface the UI will call (routes exist: `auth_accounts.py:436-609` + `test_user_edit_route_stamp.py`) — verify each mutation has a route test incl. authz (non-owner cannot edit others) | P | extend as needed | UI has a tested contract to build on | route drift under the UI | n/a |
| T-H3 | **UI error mapping**: the People pane's store maps "cannot revoke your own library role" (`authz.py:141`) to a visible explanation — never a disabled button, never a silent no-op (the milestone's bar). Test the store/view-model against a mocked transport returning the real error shape | S | `UsersStoreTests.swift` (or extend the store's existing tests) | dead-simple UX rule holds for the guarantee case | error swallowed → silent no-op (the "blank space" disease) | Partially — the seam is mocked, but the error *shape* should be captured from a P-layer snapshot so it can't drift (assert the same JSON in both suites) |
| T-H4 | From the UI's client through a live engine: create → edit → remove a user; removing the last owner is refused with the explanation | X | T-A1 harness file | the whole chain incl. serialisation | generated-client drift after OpenAPI regen | YES |
| ⚠ | #3787 also notes the duplicate-owner-identity latent bug (`auth.py:568` `"owner"` vs `pairing.py:79` `"__paired_device_owner__"`). When fixed, add a P-layer regression: exactly one canonical owner account after migration | P | with that fix | idempotent fold | — | — |

---

## 5. The "#2399 test", applied — proposals rejected or downgraded

Honesty section: things that looked like tests but would have passed while the feature was dead.

1. **"Assert `Info.plist` (source file) contains the scheme" as the only check** — rejected as primary. #2399's world had plausible-looking source; the OS reads the merged product plist. Runtime `Bundle.main` (T-B1) is primary; the source-level multi-target script (T-B2) is a complement for targets the runtime test can't host.
2. **"Mock the engine in Swift and assert `pairDevice` sends the right JSON"** — rejected. The mock encodes *our* belief about the format; `pairing.py` encodes *its* belief. Both suites green while incompatible = #2399. Replaced by T-A1 (live engine) and kept only as fast inner-loop tests where they already exist.
3. **"Unit-test that `persistPairedHost` writes four keys"** — insufficient alone (half exists at `RemoteAccessConfigTests.swift:212`). Writing is not restoring; #3772 is a *restore* bug. Replaced by T-C1 (write via production path, read via production path, assert reconstruction).
4. **"Snapshot-test the PairingBlocker card view"** — rejected. A snapshot of a card that's conditionally *absent* passes trivially when the condition hides it. Replaced by T-E2 (totality: non-ready states cannot map to "no card").
5. **"Engine test asserts transcript text in response HTML"** (existing `test_routes_views.py:90`) — kept but flagged as **appears-to-cover**: the transcript DOM is built client-side by JS (`document_view.html:649`), so text-in-response proves the data arrived, not that anchors render or that the Swift-injected selector finds them. Complemented by T-F2 (selector contract) and honest manual F4.
6. **"Test that the QR image renders"** — rejected outright. The QR is a CIFilter over a payload string; the payload string is the contract (tested in T-A1/T-B4). One manual scan (§6.4) covers Apple's QR encoder, which we do not test.
7. **"`test_device_pairing_e2e.py` already covers the round trip"** — the name lies (§2.1). Kept as the excellent policy suite it is; the transport claim moves to T-A2, the client claim to T-A1.

---

## 6. Priorities — what a worker writes, in order

### 6.1 P0 — the live bugs and the seam (write first)

1. **T-C2** Keychain accessibility attribute test — red today, drives the #3772 fix (TDD: failing test first, per repo rule).
2. **T-C1 / T-C3** cold-start restore + offline-relaunch tests (with the four-value diagnostic shape).
3. **T-B3 / T-B4** DeepLinkRouter extraction + routing/format-agreement tests (needs Q1 approval; the extraction is small and behaviour-preserving).
4. **T-A1** `PairingRoundTripContractTests` (env-gated). Manager wires it into the existing cross-stack gate.

### 6.2 P1 — fail-closed pack + blocker card + live server

5. **T-D2 / T-D4** named fail-closed regressions + `fail_closed` marker sweep over the existing suite.
6. **T-E1 / T-E2** PairingBlocker copy + totality tests (needs Q1).
7. **T-A2 / T-D3-PL** live-uvicorn TLS suite (`FICHERO_RUN_LIVE_SERVER=1`).
8. **T-B2** multi-target plist guardrail script (register in the gate next to `check_swift_transport.py`).

### 6.3 P2 — Reader + users + product-integrity pack

9. **T-F2** transcript anchor-contract script; **T-F3** reachability test; **T-F1** documentData extension.
10. **T-H2/T-H3** user-management route verification + UI error mapping; **T-H4** into the T-A1 harness.
11. **Layer R pack** (`ProductIntegrityTests.swift`): Bonjour keys, usage strings, entitlements, Release-embedded engine; fresh-install pane reachability lands **with** #3776.

### 6.4 Manual checklist (replaces what cannot be automated — run at gate/release)

| Check | Why manual |
|---|---|
| Tap a real `fichero://pair` link on an iPhone (Messages) → confirm sheet appears → pair completes | OS delivery on hardware; Layer E automates the Simulator half only, and that leg doesn't exist yet |
| `open "fichero://invite?token=…"` on the Mac → app activates, redeem gate shows | launches GUI — forbidden on the active desktop |
| Force-quit + relaunch, and reboot-without-unlock-then-launch, on a paired iPhone → still paired (#3772 acceptance) | real lock-state Keychain behaviour |
| Scan the Settings QR with a real camera once per release | Apple's QR encoder + camera pipeline are outside our test surface |
| iCloud Keychain sync (#3789, when built): pair Mac, wait, fresh iPhone same Apple ID sees the enrollment secret; **also** the degraded path with iCloud Keychain OFF falls back to QR | Apple-hosted sync cannot be driven by tests; latency is nondeterministic |
| 100-page document: transcript scrolls, page indicator follows, click page → transcript jumps (#3226 sync) | real WKWebView DOM behaviour (T-F2 guards the contract, not the pixels) |
| Bonjour discovery across a real LAN (phone sees Mac) | multicast on real networks; the unit layer covers TXT parsing only |

---

## 7. Non-goals (do not gold-plate)

- **No WKWebView JS-execution harness** for the transcript. The selector-contract script + manual scroll check is the right cost/benefit today; build a harness only if F-class regressions recur.
- **No QR image decode tests**, no screenshot/pixel tests of the pairing card, no VoiceOver assertions here (accessibility has its own lane, `check_accessibility.py`).
- **No testing of Apple frameworks' own promises**: that `ShareLink` presents, that `kSecAttrSynchronizable` items sync, that `simctl openurl` calls LaunchServices correctly. Test *our* claims on *our* artifacts.
- **No brute-force timing-precision tests** on rate limits (assert locked-out vs not; don't assert milliseconds).
- **No universal-links/AASA automation until the domain exists** (#3791). When it does: a curl-based script asserting HTTPS-no-redirect + content-type + team/bundle IDs, plus one real-device tap — per the issue, never closed on "the file is deployed".
- **No load tests beyond T-F5's bounded smoke.** The 10,000-file scenario is a design property (single scroll, engine-side concat), not a benchmark to run per-commit.
- **No new UI-automation framework.** The two GUI-touching E2E checks stay manual until a CI macOS runner or the iOS worktree gate hosts them (Q6/Q3).
- **Do not rewrite the existing suites.** `RemoteCertificatePinningTests` and the authz pack are genuinely good; everything here is additive (memory: iterate, never replace).

---

## 8. Questions for Daniel (each with a recommendation)

1. **Test-enabling production changes.** Three tiny, behaviour-preserving changes are prerequisites: (a) `PairingBlocker` `private` → `internal` + `CaseIterable` (`BackendSettingsRemoteAccessSection.swift:378`); (b) extract the URL routing out of `handleOpenURL`/`.onOpenURL` closures into a pure `DeepLinkRouter`; (c) express the Reader Page-tab → `KGSurfaceTab.transcript` mapping and the blocker-derivation as testable functions. **Recommendation: approve all three** — they add no behaviour and are the difference between testing these bugs and narrating them. (Notes for the worker: new Swift *test* files need `project.pbxproj` membership — recurring failure; and `LibraryWindow.body` type-check limits mean extractions go in the right bounded property.)
2. **Where does the cross-stack contract suite (T-A1) run?** Recommendation: `XCTSkip` unless `FICHERO_CONTRACT_ENGINE_URL` is set; the manager exports it during the existing "backend on :8765" gate. No new infrastructure, no accidental runs on your desktop.
3. **iOS E2E leg (simctl `openurl` + iOS-side `Bundle.main` assertions).** Needs a booted Simulator, so it can't run on your active desktop mid-build. Recommendation: fold into the existing iOS build-gate worktree arrangement as an opt-in step; until then the two delivery checks stay on the manual checklist — explicitly, not silently.
4. **#3790 coupling test (T-G4).** OK to encode "email-channel 24h TTL cannot be enabled without the redemption notification" as a *blocking* test, so the condition you set can't erode? Recommendation: **yes** — that condition was the whole basis of the decision.
5. **Keychain accessibility class for device tokens (T-C2).** Recommendation: `kSecAttrAccessibleAfterFirstUnlock` (background-capable app must read it post-reboot; `ThisDeviceOnly` variants would block the #3789 sync item, which is a *separate* item anyway). Confirm before the assertion is written, since the test pins the choice.
6. **A macOS CI runner for the Swift suite?** Today Swift tests run only when the manager gates on your machine (CI is Ubuntu-only — `ci.yml:23`). A GitHub-hosted `macos-15` runner could run `xcodebuild test` headlessly (their runners have no "active desktop"), catching Swift regressions per-push instead of per-gate. Costs Actions minutes; needs the scheme's test plan to exclude XCUITest launch-stress legs. Recommendation: **worth a spike** — it is the single biggest structural fix to "the Swift suite exists but nothing runs it automatically."
7. **T-A2 process-spawn scope.** The live-server suite spawns uvicorn the way `start_backend.sh`/the embedded path does. One heavy lane at a time is your standing rule; marked `live_server` + env-flag so it never joins the default unit run. Confirm that placement. Recommendation: yes, run it in the same slot as the other `FICHERO_RUN_*` write-suites.

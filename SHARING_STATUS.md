# Sharing & Pairing lane — Swift-side hardening — STATUS

Worktree: `~/code/fichero-worktrees/sharing`, branch `lane/sharing-ux`. Engine
(`fichero-engine/`) untouched, per task. Commits authored, not pushed.

_Last updated: 2026-07-21._

## TL;DR

Triaged all six assigned issues against the code. **Five were already built and
tested** on this branch — only **#3372 had a genuine gap**, now fixed. Also
prototyped the **#1847 Xcode-style consent prompt** (UI only). Two commits, not
pushed:

- `29e51bc7f` fix(pairing #3372): confirm library path against server before persisting
- `e79244379` feat(sharing #1847): Xcode-style agent/MCP consent-prompt UI (prototype)

## Per-issue triage

| Issue | Verdict | Evidence / what remains |
|---|---|---|
| **#3372** QR/deep-link must confirm library path before persisting | **FIXED (this lane)** | Real gap: `persistPairedHost` wrote the QR's `libraryPath` to UserDefaults with no server confirmation (`RemoteClientPairing.swift:182`). Now confirmed against `GET /api/authz/libraries` after the token exchange; forged/unconfirmed path is rejected + the just-written token cleared. |
| **#3374** SPKI pin mismatch recovery + re-pin | **ALREADY DONE — verify/close** | Mismatch fails closed (`RemoteCertificatePinning.resolveServerTrustChallenge` → cancel; `serverIdentityMismatch`). Surfaces as `AccessError.tlsPinFailure` → `.recovery == .resetPin` → `resetCertificateButton` ("The engine's security certificate didn't match the pinned one"). Reset clears the pin (`clearPersistedSPKIPin`); a remote host still won't TOFU a new identity — re-pair (fresh QR carrying the new SPKI) is required. Covered by `RemoteCertificatePinningTests`, `PairingRestoreDiagnosticsTests`. |
| **#3373** Device tokens in Keychain + renewal + reset UX | **ALREADY DONE — verify/close** | Keychain-only (`AuthTokenMiddleware.persistRemoteToken` → generic password, `kSecAttrAccessibleAfterFirstUnlock`, never UserDefaults). Renewal: `DeviceTokenRenewal` + `/api/pair/devices/renew` + stored expiry. Reset: `forgetPairing()` + `forgetPairingButton`. Missing-state UI: `PairingRestoreDiagnostics` + `BackendConnectionView`. Tests: `KeychainTokenAccessibilityTests`, `DeviceTokenRenewalTests`, `AuthTokenMiddlewareStorageTests`. |
| **#3371** Discover Mac-hosted engine candidates on iOS | **ALREADY DONE — verify/close** | `BonjourDiscoveryService` browses `_fichero._tcp`, resolves, exposes reachable candidates; `DiscoveredMacsSection` shows them and disappears stale ones (`didRemove`). Minor optional polish only (see below). |
| **#2666** iPhone can't open document preview/reader | **ALREADY MERGED — out of active scope** | GitHub label `status:ready-for-test` (merged, awaiting human QA). No code gap found on this branch; do not re-implement. Needs Daniel's device QA to close. |
| **#3791** Universal links: fichero.app + AASA | **NOT STARTED — mostly ops, partly out of Swift scope** | Requires (a) the `fichero.app` domain + a static `apple-app-site-association` on HTTPS-no-redirect hosting + a landing page (ops, needs the domain purchased), and (b) an `applinks:fichero.app` Associated Domains **entitlement** (needs the real Team ID) + an `https` deep-link handler mirroring the existing `fichero://` one. Deferred — see Decisions. |

## What I changed (#3372)

`fichero/Services/RemoteClientPairing.swift`, `fichero/Services/PairingTypes.swift`:
- After the device-token exchange, `pairAndPersistHost` now calls
  `confirmLibraryAccess` before `persistPairedHost`. It fetches the server's
  accessible-library set (`PairingService.accessibleLibraryPaths()` →
  `GET /api/authz/libraries`, authenticated with the fresh device token) and
  rejects any advertised path not in it (`RemoteClientPairingError.libraryPathNotConfirmed`).
- The token is persisted first (the confirm call needs it in the Keychain) and
  cleared on failure, so a rejected pairing leaves nothing half-written.
- `isLibraryConfirmed(advertised:in:)` is a pure, unit-tested decision (forged
  reject, empty-set reject, trailing-slash/whitespace tolerance, nil-skip for
  manual host entry).
- Tests: `fichero-tests/RemoteClientPairingLibraryConfirmTests.swift`.

## What I built (#1847 prototype)

`fichero/Views/Sharing/AgentConsent/` (2 new files) + `fichero-tests/AgentConsentStoreTests.swift`:
- `AgentConsentStore` — `@Observable @MainActor` session-scoped broker.
  `requestConsent(_:) async -> Bool` suspends on a continuation until the user
  decides; remembered decisions short-circuit it. **In-memory only** — that is
  the whole "relaunch re-prompts" mechanism.
- `AgentConsentSheet` + `.agentConsentPrompt(store:)` — the Xcode-style prompt
  (icon, headline "<client> wants to connect", explanation, "Don't ask again
  this session" checkbox, Deny/Approve). Dismissal-without-a-decision disabled;
  external close falls back to deny.
- Not wired to any live connection event (engine wiring comes later, per task).
  A `#Preview` drives the real connect → prompt → decide path.

## Build-verify needs (manager owns the gate)

I did **not** build or run tests (builds serialized machine-wide; manager owns
the `xcodebuild` gate). Please, on the gate:
1. Build the `Fichero` app target (both new files are in the synchronized folder;
   no `project.pbxproj` edits were needed).
2. Run the app-target suite, especially the two new files:
   `RemoteClientPairingLibraryConfirmTests`, `AgentConsentStoreTests`.
3. Run the guardrail suite (`scripts/check_*.py`) — new files + a new error case.

SourceKit showed only "No such module" / cross-file "cannot find type" noise
(expected without a build); no real errors after switching the sheet to an
`isPresented:` (concrete-`Bool`) binding to avoid a `Binding` overload ambiguity.

## Decisions for Daniel

1. **Authorship deviation (FYI).** The task said author as `Claude (Sonnet 5)`,
   but the running model is Opus 4.8 — I authored both commits as
   `Claude (Opus 4.8)` (accurate) with the `Co-Authored-By: Claude Opus 4.8`
   trailer as specified. Say if you want them re-authored as Sonnet 5.
2. **#3372 confirmation vs. multiuser-OFF (#3335).** The confirm call fails
   **closed** — if `GET /api/authz/libraries` errors (e.g. the multiuser-OFF 500
   in #3335), pairing is rejected with an actionable message. This is the secure
   choice and matches the issue ("forged/unconfirmed → rejected"), but if you
   ever want to pair a device to a shared-but-multiuser-OFF engine, that engine
   path (#3335) must return a clean list first. Flagging in case that combination
   is intended to work.
3. **#3374 / #3373 / #3371 are already done.** Recommend verifying on-device and
   closing rather than scheduling further work. Only real remaining nit: #3371's
   candidate list doesn't visually distinguish a *resolve-failed* Mac from a
   resolved one (both say "scan its QR code"). The candidate is still usable
   (selecting it opens the QR scanner, which grants trust), so I left it — say if
   you want a explicit "unreachable" state.
4. **#3791 sequencing.** It's ~90% ops (domain + static AASA + landing page) and
   needs the real Team ID for the Associated Domains entitlement. Not startable
   as pure Swift here. Recommend it stays with whoever owns the `fichero.app`
   domain + signing config; I can add the `https` deep-link handler + AASA static
   file once the domain/Team ID are decided.

## Next (if this lane continues)

- Nothing blocking. All actionable Swift-side pairing hardening is either fixed
  (#3372) or verified-done (#3374/#3373/#3371). Await manager build-gate result.

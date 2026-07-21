# Sharing & Pairing lane — Swift-side hardening — STATUS

Worktree: `~/code/fichero-worktrees/sharing`, branch `lane/sharing-ux`. Engine
(`fichero-engine/`) untouched, per task. Commits authored as `Claude (Opus 4.8)`
(Daniel confirmed: keep — accurate to the running model). **Not pushed** —
manager gates/integrates.

_Last updated: 2026-07-21._

## TL;DR

Triaged all six assigned issues. **#3374 and #3373 were already done → CLOSED.**
Fixed the one real gap (#3372), added the two polish items Daniel approved
(#3371, #3791 Swift side), and prototyped the #1847 consent prompt.

Lane commits (oldest → newest), not pushed:

- `29e51bc7f` fix(pairing #3372): confirm library path against server before persisting
- `e79244379` feat(sharing #1847): Xcode-style agent/MCP consent-prompt UI (prototype)
- `4dc6c8a69` docs(sharing): triage + status
- `f9b2081b4` fix(pairing #3371): fail visibly when a discovered Mac won't resolve
- `f8358d842` feat(pairing #3791): accept https://fichero.app/pair universal links + AASA assets

## Per-issue triage

| Issue | Verdict |
|---|---|
| **#3374** SPKI pin mismatch recovery | **CLOSED** — already built + tested (fail-closed + `resetCertificateButton` + `AccessError.tlsPinFailure`→`.resetPin`). Closed with evidence. |
| **#3373** Device tokens in Keychain + renewal + reset | **CLOSED** — already built + tested (Keychain-only `persistRemoteToken`, `DeviceTokenRenewal`, `forgetPairing`). Closed with evidence. |
| **#3372** QR/deep-link confirm library path before persisting | **FIXED (open — gated).** Real gap: `persistPairedHost` wrote the QR's `libraryPath` with no server confirmation. Now confirmed vs `GET /api/authz/libraries` after the token exchange; forged/unconfirmed → rejected + token cleared. Fail-closed on confirm error (Daniel confirmed correct). |
| **#3371** Discover Mac candidates on iOS | **CORE done + polish added (open — gated).** Discovery was built; added the approved "fail visibly" state so a resolve-failed candidate shows a warning row instead of looking usable. |
| **#3791** Universal links / AASA | **Swift side done (open — gated).** `isPairingInviteLink` now accepts `https://fichero.app/pair`; both `onOpenURL` handlers route through it. Static `web/` assets (AASA + landing page + README). Still needs the real Team ID + the Associated Domains entitlement (see below). |
| **#2666** iPhone can't open preview/reader | **OPEN — awaiting your device QA** (`status:ready-for-test`). No code gap on this branch; not mine to close. |
| **#1847** Xcode-style consent prompt | **Prototype done (open — gated).** UI only; engine wiring later. |

## What I changed

- **#3372** — `RemoteClientPairing.swift`, `PairingTypes.swift`: `confirmLibraryAccess`
  before `persistPairedHost`; pure unit-tested `isLibraryConfirmed`. Tests:
  `RemoteClientPairingLibraryConfirmTests`.
- **#3371** — `BonjourDiscoveryService.swift` (`didFailResolve` flag),
  `ConnectDiscoveredMacsSectionIOS.swift` (warning row + glyph for unreachable).
- **#3791** — `RemoteClientPairing.swift` (`isPairingInviteLink` accepts both
  forms), `FicheroApp.swift` + `FicheroApp_iOS.swift` (route both). Tests:
  `PairingUniversalLinkTests`. Static assets: `web/.well-known/apple-app-site-association.template`,
  `web/index.html`, `web/README.md`.
- **#1847** — `fichero/Views/Sharing/AgentConsent/` (store + sheet). Tests:
  `AgentConsentStoreTests`.

## Build-verify needs (manager owns the gate)

Did not build or run tests. On the gate:
1. Build the `Fichero` app target (all new `.swift` are in the synchronized
   folder; no `project.pbxproj` edits).
2. Run the app-target suite, especially the new files:
   `RemoteClientPairingLibraryConfirmTests`, `PairingUniversalLinkTests`,
   `AgentConsentStoreTests`.
3. Run `scripts/check_*.py` guardrails.

SourceKit showed only "No such module" / cross-file "cannot find type" noise
(expected without a whole-module build); no real errors.

## Remaining non-Swift steps for #3791 (need you / signing config)

1. Replace `TEAMID` in `web/.well-known/apple-app-site-association.template` with the real
   Apple Developer Team ID (bundle id `app.fichero.fichero` is already correct).
2. Add the Associated Domains entitlement (`applinks:fichero.app`) to
   `Fichero.entitlements` / `FicheroAppStore.entitlements` /
   `FicheroRelease.entitlements` **and** enable the capability on each
   provisioning profile. Deliberately NOT edited here — editing entitlements
   without matching profiles breaks the signing gate. Snippet in `web/README.md`.
3. Host `web/` on HTTPS (no redirects, `application/json` for the AASA) and
   **test the round trip on a real device** before closing #3791 (#2399 lesson).

## Self-review (2026-07-21)

Ran a code-reviewer on `main...lane/sharing-ux` before the gate (couldn't build
locally). Verdict: **APPROVE, no criticals** — the #3372 security path is
correct and fail-closed. Two warnings fixed in `23ea0652e`:
- #3372 path match was case-sensitive → now standardized + case-insensitive
  (APFS is case-insensitive; the old check could fail-closed-reject a legit
  pairing). Test added.
- #3791 AASA had a literal `TEAMID` → renamed to `...association.template` so a
  naive `web/` deploy can't serve a broken, CDN-cached (~24h) record.
Third warning (device token written twice on the success path) is idempotent
with a correct rollback — left as-is (out of scope).

## Decisions (resolved by Daniel, 2026-07-21)

- Authorship: keep `Claude (Opus 4.8)`. ✅
- #3372 fail-closed: correct. ✅ (If pairing a shared-but-multiuser-OFF engine is
  ever wanted, engine #3335 must return a clean `/api/authz/libraries` first.)
- #3371 unreachable-state + #3791 Swift scaffold: build them → done. ✅

## Next

Nothing blocking. All actionable Swift-side pairing work is fixed, polished, or
verified-closed. Await the manager build-gate; #2666 awaits your device QA.

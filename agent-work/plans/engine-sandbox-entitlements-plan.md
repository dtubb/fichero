# P0 plan — embedded engine cannot reach any library outside its container

Plan only; no signing changes made. Everything below is labeled VERIFIED
(read in this tree) or INFERRED (needs an empirical check).

## The current signing matrix (VERIFIED, pbxproj + scripts)

| Config | App entitlements | App sandboxed? | Engine signing |
|---|---|---|---|
| Debug / Dev Local | `Fichero.entitlements` (keychain group only) | YES (`ENABLE_APP_SANDBOX=YES`) | engine not embedded (external) |
| **Dev Embedded** | `Fichero.entitlements` (keychain group only) | YES | **embed phase COPIES, never signs** — engine keeps Briefcase's signature: hardened-runtime `cs.*` only, no sandbox, no inherit |
| Alpha/Beta Embedded, Release, Release Local | `FicheroRelease.entitlements` (`files.user-selected.read-write` only) | YES | same copy-only embed; the DMG re-sign (`build-release-dmg.sh:112`) applies `FicheroEngine.entitlements` = 4 `cs.*` keys, no sandbox |
| MAS (App Store) | `FicheroAppStore.entitlements` (sandbox + network client/server + user-selected + both bookmark keys) | YES | MAS embed phase signs engine with `FicheroEngineAppStore.entitlements` = exactly `{app-sandbox, inherit}` — WORKS |

## Why it fails (VERIFIED mechanism, matches the team-lead's diagnosis)

The app became sandboxed in every config on 2026-07-29; only the MAS engine
was ever given `{app-sandbox, inherit}`. An engine child without `inherit`
runs confined to the container but is NOT part of the app's sandbox:
`Path.home()` = the container (killing every literal allowed root — the
roots in `_is_allowed_library_path` are `~`-relative), and the app-scoped
bookmarks the app mints cannot be decrypted by a process outside its
sandbox → the NSCocoaError 259 on every resolve. `security_scoped_access.py`'s
docstring states the design premise: *"the engine runs inside the app's App
Sandbox via `com.apple.security.inherit`"*. Three configs violate the premise.

**A second app-side gap (VERIFIED):** `FicheroRelease.entitlements` and
`Fichero.entitlements` carry NEITHER `files.bookmarks.app-scope` nor
`files.bookmarks.document-scope`. The MAS file carries both, with a comment
saying they exist to persist and hand off library access. Even with the
engine fixed, the non-MAS apps likely cannot mint durable app-scoped
bookmarks. (INFERRED severity — the app may fall back to fresh Powerbox
grants per launch; dump the built app's entitlements to confirm:
`codesign -d --entitlements - Fichero.app`.)

## Proposal

**1. Dev/Alpha/Beta Embedded (no notarization): sign the engine with the
MAS pair, verbatim.** Extend the non-MAS "Embed Fichero Server" phase to
re-sign the embedded engine (deep, same identity as the build) with
`FicheroEngineAppStore.entitlements` — the exact file the working MAS
config uses, proven by the #3746 spike to run the full 1.0 GB engine with
no hardened runtime and no `cs.*` keys. No new entitlements file, no new
combination to validate. Dev builds don't notarize, so dropping the
Briefcase `cs.*` signature costs nothing.

**2. Release DMG (notarized): a combined 6-key file,
`FicheroEngineSandboxed.entitlements`** = `{app-sandbox, inherit}` + the
four existing `cs.*` hardened-runtime exceptions; `build-release-dmg.sh`
signs the engine with it (still Developer ID + `-o runtime`).
- INFERRED, must be verified before any release: Apple's "exactly two keys"
  rule is about App-Sandbox-family entitlements; `cs.*` keys are
  hardened-runtime entitlements, and shipping helpers (Chromium/Electron
  helper apps) combine `inherit` with `cs.allow-jit` /
  `allow-unsigned-executable-memory` / `disable-library-validation` in
  production. But OUR engine is a Briefcase CPython, not a Chromium helper.
  Verification ladder, cheapest first: (a) sign locally, launch Dev-config
  app against it, confirm the engine boots and a bookmark resolves;
  (b) `spctl`/`stapler` on a locally notarized one-off BEFORE the next real
  release. If (a) aborts on launch, fallback: the app carries the `cs.*`
  exceptions and the engine keeps exactly the MAS pair — establish whether
  the inherited posture covers the CPython needs (also empirical).
- Notarization itself does not reject sandboxed executables; DMG apps may
  be sandboxed (INFERRED from policy, low risk; (b) confirms).

**3. App side: add the two bookmark keys** (`files.bookmarks.app-scope`,
`document-scope`) to `FicheroRelease.entitlements`, and decide whether
Dev Embedded keeps signing with `Fichero.entitlements` (keychain-only) or
moves to the Release file + keychain group. Recommend the latter — one
entitlements story for every embedded config.

**4. MAS: untouched.** `FicheroEngineAppStore.entitlements` keeps exactly
two keys; `check_mac_app_store_target.py` and
`test_check_mac_app_store_target.py` keep passing unchanged.

## Guardrail changes

- `test_check_mac_app_store_target.py`: NO change (MAS untouched).
- NEW check (same shape as the MAS one): the non-MAS embed phase must sign
  with `FicheroEngineAppStore.entitlements`, and `build-release-dmg.sh`
  must sign with `FicheroEngineSandboxed.entitlements` — each with a
  fixture that FAILS when the signing line is removed (guardrails prove
  they fire).
- `release-all.sh` pin (must pass the MAS file to
  `resign_engine_in_archive.sh`): unchanged.

## The second defect: New Library cannot be created in the app's own container

VERIFIED: the New Library flow writes `<container>/Data/tmp/Untitled-….fichero`;
`_is_allowed_library_path` (api/main.py:961) allows the container's
`Data/Library/Application Support` (scoped via
`_is_sandbox_container_app_support`) but NOT `Data/tmp`. Two options:
- (a) Allow `<container>/Data/tmp` with the same single-container scoping —
  smallest change, keeps the app's create-then-move flow.
- (b) Change the app to create directly in the container's Application
  Support — no server change, but touches the Swift create flow and loses
  the atomic move-into-place.
Recommend (a), with a test that the WHOLE Containers tree stays rejected.

## What Daniel decides

1. Approve engine signing per configs (proposal 1 + 2), including the
   6-key file for the DMG channel with the empirical ladder before release.
2. Approve the app-side bookmark keys (proposal 3) and whether Dev Embedded
   adopts the Release entitlements file.
3. Approve (a) for the container-tmp defect.

Nothing here is committed; a wrong signing move breaks notarization with no
cheap discovery, so every step above lands only after the (a)-rung check
passes on this machine.

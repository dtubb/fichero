(AI generated. Not reviewed.)

> **HISTORICAL CHECKLIST — audited 2026-06-27.** This page is a point-in-time
> release-prep snapshot with concrete versions, cert IDs, and blocking items
> from that date. Use [release-lane.md](./release-lane.md) for the current
> release runbook; keep this page for provenance.

# Release Readiness Checklist

Manager-executable checklist for cutting **both** outputs in one sitting:

- **GitHub DMG / Sparkle** — Developer ID signed app, notarized + stapled,
  Sparkle EdDSA-signed, attached to a GitHub release, appcast updated.
- **Mac TestFlight** — Apple Distribution archive uploaded to App Store Connect
  for internal TestFlight.

This worker did the SAFE prep + audit. The manager runs every codesign /
notarize / upload step below (those need the real Keychain + certs). Companion
runbook with full detail: `docs/contributor/release/release-lane.md`.

Audited against the repo on **2026-06-27**. Version in `project.pbxproj`:
`MARKETING_VERSION = 2026.06.26-beta`, `CURRENT_PROJECT_VERSION = 20260626`.

---

## 1. Release scripts (in `scripts/`)

| Script | What it does | Inputs / credentials |
|---|---|---|
| `release-all.sh` | One-command wrapper for both tracks. Flags: `--skip-backend --skip-dmg --skip-notarize --skip-testflight --github --draft`. Builds + signs the DMG, notarizes, then (TestFlight lane) archives `arm64`-only with conservative Swift settings and `xcodebuild -exportArchive` uploads to App Store Connect; optionally runs the GitHub/Sparkle step. | Developer ID + Apple Distribution certs; ASC API key `.p8` (ID `2MGYUR786H`, issuer `6d2cfad9-…`); provisioning profile at `~/Downloads/Mac_App_Store_Connect.provisionprofile`; baked `SPARKLE_FEED_URL`. |
| `build-release-dmg.sh` | Canonical DMG builder. Builds Release app (`build-release.sh`), stages `Fichero.app` + `/Applications` symlink, **overrides `SUFeedURL` in the staged Info.plist** to the canonical feed, runs the load-bearing **[2b/6] inside-out Developer ID re-sign**, styles + compresses to `Fichero.dmg`, writes `release-manifest.txt`. | `Developer ID Application: … (QAPB6CWYR6)` (or `FICHERO_DEV_IDENTITY`); `icon.png`. |
| `build-release.sh` | Builds the Release `Fichero.app` (incl. embedded engine) into `fichero/build/xcode/Products/Release/`. | Xcode toolchain; signing identity. |
| `notarize.sh` | Submits the DMG to Apple notary (`xcrun notarytool submit --wait`) then `xcrun stapler staple`. Tries the `notarytool` Keychain profile first, falls back to the ASC API key. | `notarytool` keychain profile **or** ASC API key `.p8`; Developer ID cert. |
| `create-github-release.sh` | **Preflight asserts built app `SUFeedURL` == canonical appcast URL.** Sparkle EdDSA-signs the DMG (`sign_update`, key read from Keychain), `gh release create vX` + uploads DMG, inserts a new `<item>` into `fichero/appcast.xml`, tags + pushes the source repo. Flags `--draft --prerelease --dry-run`. | `gh` auth (`dtubb`); `~/code/sparkle-tools/bin/sign_update`; Sparkle Ed25519 key in Keychain (`account=ed25519`, `service=https://sparkle-project.org`). |
| `set-release-version.sh` | Sets `MARKETING_VERSION` / `CURRENT_PROJECT_VERSION` in the project. | — (writes `project.pbxproj`). |
| `release-notes-gen.sh` | Generates `RELEASE_NOTES.md` Apple-style per-day prose via local ollama (zero Claude cost). Separate from the literal dated changelog. | ollama; `gh`. |
| `notarize.sh --dry-run` / `create-github-release.sh --dry-run` | Print every step without executing — use to rehearse. | none. |
| `launch-release.sh`, `release.sh`, `smoke-release-embedded-backend.sh` | Launch the built release app / thin wrappers / embedded-backend smoke test. | built app. |

## 2. GitHub DMG / Sparkle path

1. `scripts/build-release-dmg.sh --skip-backend` → Release app → staged →
   **[2b/6] inside-out Developer ID re-sign**. This signs **every Mach-O
   individually** (`--options runtime --timestamp`), then re-seals every bundle
   innermost-first. **Do NOT replace with `codesign --deep`** — `--deep` skips
   the 800+ loose `.so`/`.dylib` Python extensions inside the embedded
   `Fichero Engine.app`, and Apple rejects them as ad-hoc (#2662).
2. Spot-check (engine binary, a `_duckdb…so`, `Sparkle.framework`): expect
   `Developer ID` authority, `flags=0x10000(runtime)`, a timestamp.
3. `scripts/notarize.sh build/releases/Fichero.dmg` → `status: Accepted` →
   staple → `xcrun stapler validate`.
4. `scripts/create-github-release.sh --prerelease` → preflight feed-URL match →
   **Sparkle EdDSA sign** (`sign_update`, key from Keychain) → `gh release
   create v2026.06.26-beta` + DMG upload → append `<item>` to
   `fichero/appcast.xml` → tag + push.
5. Commit + push the updated `fichero/appcast.xml` so the raw-GitHub feed serves
   the new enclosure.

Appcast feed (canonical, baked by the scripts):
`https://raw.githubusercontent.com/dtubb/fichero/main/fichero/appcast.xml`

## 3. Mac TestFlight path

`scripts/release-all.sh --skip-dmg --skip-notarize` →

1. Converts marketing version → numeric ASC version
   (`2026.06.26-beta` → `2026.6.26`, build `20260626`).
2. Installs the provisioning profile into `~/Library/MobileDevice/Provisioning Profiles/`.
3. `xcodebuild archive` — `arm64` only, `ONLY_ACTIVE_ARCH=YES`,
   `SWIFT_COMPILATION_MODE=singlefile`, `SWIFT_OPTIMIZATION_LEVEL=-Onone`
   (avoids the Xcode 26 archive stall).
4. `xcodebuild -exportArchive` with a generated
   `ExportOptions-mac-testflight.plist`: `method=app-store-connect`,
   `destination=upload`, `teamID=QAPB6CWYR6`, manual signing with cert SHA
   `7CD87BA09F2DA8A79652710DE0F5E3C5DCD2CC35`, profile `Mac App Store Connect`
   (App ID `QAPB6CWYR6.app.fichero.fichero`), `testFlightInternalTestingOnly`.

Referenced by ID only: ASC API key ID `2MGYUR786H`, issuer
`6d2cfad9-6a3d-48a0-bdcc-9c75c308f812`, profile UUID
`fe5c4814-a644-4d7a-a00a-ea93937a589e`, team `QAPB6CWYR6`.

## 4. DONE vs BLOCKING

| Item | State | Notes |
|---|---|---|
| Build green | DONE | recent compile fixes merged (PR #2671/#2672/#2673). |
| Developer ID Application cert (QAPB6CWYR6) | DONE | present in `security find-identity`. |
| Apple Distribution cert (QAPB6CWYR6) | DONE | installed; SHA matches `release-all.sh` `MAC_APP_STORE_SIGNING_CERT`. |
| `notarytool` keychain profile | DONE | usable (verified `notarytool history`). |
| ASC API key `.p8` (ID `2MGYUR786H`) | DONE | present (fallback for notarize + TestFlight auth). |
| Mac App Store provisioning profile | DONE | present at `~/Downloads/Mac_App_Store_Connect.provisionprofile`. |
| Sparkle `sign_update` tool | DONE | present at `~/code/sparkle-tools/bin/`. |
| Sparkle Ed25519 private key (Keychain) | DONE | present (`account=ed25519`). |
| Sparkle EdDSA **public** key in app | DONE | `SUPublicEDKey=$(SPARKLE_PUBLIC_ED_KEY)` → `z3UPbmGi74NGSqTQL25E2WFD1yulIzYRvtDitbIZvNY=`. |
| `gh` authenticated for `dtubb/fichero` | DONE | logged in as `dtubb`. |
| `appcast.xml` | DONE (skeleton) | placeholder with no `<item>`; first release seeds it. |
| Earlier DMG notarized + stapled | DONE | a notarized/stapled submission exists from an earlier run. |
| **Fresh archive after recent compile fixes** | BLOCKING | re-run `build-release-dmg.sh` so the shipped DMG includes the latest `main`. |
| **DMG notarize + staple of the fresh build** | BLOCKING | manager-only (`notarize.sh`). |
| **Sparkle-sign + appcast publish** | BLOCKING | `create-github-release.sh`; then commit/push `fichero/appcast.xml`. |
| **GitHub release upload** | BLOCKING | no `v*` tags / releases exist yet — this is the first. |
| **TestFlight archive + upload** | BLOCKING | manager-only; needs Keychain approval for signing. |
| **`SPARKLE_FEED_URL` in `project.pbxproj`** | ⚠️ STALE (non-blocking via scripts) | baked default still points at the retired `fichero-releases` repo — see Audit §6. Scripts override it at build time, so a script-built release is correct; a plain Xcode build is not. |
| `docs/contributor/release/sparkle-release.md` | ⚠️ STALE doc | still cites the old `fichero-releases` feed + a `0.0.1` placeholder key story; superseded by `release-lane.md`. |

## 5. Manager run order (today)

```bash
# DMG/Sparkle/GitHub (Developer ID)
scripts/build-release-dmg.sh --skip-backend
# spot-check signing (see release-lane.md §DMG Details), then:
scripts/notarize.sh build/releases/Fichero.dmg
scripts/create-github-release.sh --prerelease     # or --draft to stage
git add fichero/appcast.xml && git commit -m "chore(release): publish appcast" && git push   # via PR

# Mac TestFlight (separate lane)
scripts/release-all.sh --skip-dmg --skip-notarize
```

Rehearse first with `--dry-run` on `notarize.sh` and `create-github-release.sh`.
Do not run `xcodebuild test` / `verify_all.sh` on Daniel's desktop for this lane.

## 6. Audit findings (Sparkle #2582 / code-signing #2581)

- **Sparkle appcast feed URL — wired, with one stale default.** Scripts +
  `release-lane.md` use the canonical
  `https://raw.githubusercontent.com/dtubb/fichero/main/fichero/appcast.xml`,
  and `create-github-release.sh` *asserts* the built app matches it. But
  `project.pbxproj` still bakes `SPARKLE_FEED_URL =
  https://raw.githubusercontent.com/dtubb/fichero-releases/main/appcast.xml`
  (retired repo). `build-release-dmg.sh`/`release-all.sh` override it at build
  time so a script-built release is fine; a plain Xcode ⌘R/archive is not.
  **Proposed fix (manager, `project.pbxproj` is off-limits to this worker):**
  set `SPARKLE_FEED_URL = "https://raw.githubusercontent.com/dtubb/fichero/main/fichero/appcast.xml";`
  in both build configs so the default matches the scripts.
- **EdDSA public key — present in Info.plist (via build setting).**
  `SUPublicEDKey=$(SPARKLE_PUBLIC_ED_KEY)` resolves to
  `z3UPbmGi74NGSqTQL25E2WFD1yulIzYRvtDitbIZvNY=`, matching the runbook and the
  Keychain private key. No fix needed.
- **Signing identities (`security find-identity -v -p codesigning`, NAMES
  only):** `Developer ID Application: … (QAPB6CWYR6)` (DMG),
  `Apple Distribution: … (QAPB6CWYR6)` ×2 (TestFlight),
  `Apple Development: … (4H486QMRQP)` (local). The TestFlight cert SHA
  hardcoded in `release-all.sh` matches an installed Apple Distribution
  identity. Nothing missing for signing.
- **What's missing for a clean publish:** nothing credential-wise — every
  cert/key/profile/tool is present. Remaining work is **execution**: fresh
  build → notarize/staple → Sparkle-sign + appcast → GitHub upload → TestFlight
  upload (+ Keychain approval). The only config nit is the stale
  `SPARKLE_FEED_URL` default above.

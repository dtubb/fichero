---
name: fichero-release
description: Build, notarize, and publish a Fichero release — DMG + Sparkle/GitHub, or Mac TestFlight. Wraps scripts/release-all.sh. Only Daniel publishes.
---

# /fichero-release

One skill for the whole release lane. The commands here are thin wrappers around
`scripts/release-all.sh`; the authoritative runbook (certificates, profiles,
signing internals, troubleshooting) is **`docs/contributor/release/release-lane.md`** — read it
before doing anything unusual.

**Hard rules**

- Never run `xcodebuild test` or `scripts/verify_all.sh` on Daniel's desktop for
  this lane. Build/archive only.
- One `xcodebuild` at a time, machine-wide. The machine is slow.
- Only Daniel publishes. Agents may build, notarize, and stage; the GitHub release
  and the site deploy wait for his say-so.

## Version

`release-all.sh` auto-stamps **today's date** (CalVer, `-beta` channel) across the
Xcode project and the engine before any build runs; a second build the same day
bumps a sub-number. Override with `FICHERO_RELEASE_VERSION=…`, or
`FICHERO_RELEASE_BETA=0` for a stable stamp. Don't hand-edit `MARKETING_VERSION` —
`scripts/set-release-version.sh` owns it.

## 1. Build + notarize the DMG

```bash
scripts/release-all.sh --skip-testflight
```

Builds the Briefcase engine bundle → Xcode Release → styled DMG → notarize →
staple. Add `--skip-backend` to reuse an already-built engine bundle.

Artifacts land in `build/releases/`:

- `Fichero.dmg`
- `release-manifest.txt` (the stamped version)

Verify the staple:

```bash
xcrun stapler validate build/releases/Fichero.dmg
```

If notarization returns `Invalid`, do **not** retry blindly — the `[2b/6]` step in
`scripts/build-release-dmg.sh` signs each Mach-O inside the embedded engine
individually. See `docs/contributor/release/release-lane.md` → *DMG Details* for the spot-check
commands and why `codesign --deep` is forbidden here.

## 2. Smoke-test before Daniel sees it

```bash
scripts/smoke-launch-crash.sh              # launches, catches launch-time crashes
scripts/smoke-release-embedded-backend.sh  # embedded engine actually starts
```

Release builds embed and spawn the engine (Debug runs it externally on `:8765`).
The smoke script launches from `~/Applications` on purpose — launching from the
build directory shows the installer prompt first.

Then open the DMG by hand and check: app icon, `Applications` symlink,
move-to-Applications prompt, app launches, engine comes up.

## 3. Release notes

Newest-first, Apple "what's new" style (**New / Improved / Security / Fixed**), in
`RELEASE_NOTES.md` at the repo root. `scripts/release-notes-gen.sh` drafts sections
from git history + closed issues using a local ollama model — draft with it, then
edit by hand. Every claim must match what actually shipped.

## 4. Publish (Daniel's call)

```bash
scripts/create-github-release.sh --prerelease
```

Creates the GitHub release on `dtubb/fichero`, uploads the DMG, EdDSA-signs it with
the Sparkle key from the Keychain, and updates `fichero/appcast.xml`. If it hangs,
approve the Keychain prompt for the Sparkle private key — never print or export it.

Commit and push the updated `fichero/appcast.xml`, then deploy the site:

```bash
scripts/deploy-site.sh
```

Do not change `SPARKLE_FEED_URL` without a rebuild — it is baked into `Info.plist`.

## Mac TestFlight (separate track, not the DMG)

```bash
scripts/release-all.sh --skip-dmg --skip-notarize
```

Archives `arm64` only and converts the dated version to a numeric App Store version
(`2026.06.26-beta` → `2026.6.26`, build `20260626`). Internal TestFlight only.

## Report

```
FICHERO RELEASE — <version> — <date>

DMG:        [PASS/FAIL]  (<size>)
Notarized:  [PASS/FAIL]  (stapler validate: …)
Smoke:      [PASS/FAIL]  (launch + embedded engine)

Artifacts:  build/releases/Fichero.dmg
            build/releases/release-manifest.txt

Release notes: RELEASE_NOTES.md updated? [yes/no]

Waiting on Daniel: review the DMG + notes, then step 4 (publish).
```

(AI generated. Not reviewed.)

# Release Lane Runbook

This is the current release path for Fichero. It covers two separate outputs:

- **DMG/Sparkle/GitHub**: Developer ID signed app in a DMG, notarized by Apple,
  Sparkle-signed, then attached to a GitHub release.
- **Mac TestFlight**: macOS archive uploaded to App Store Connect for internal
  TestFlight. This is not the DMG path.

Do not run `xcodebuild test` or `scripts/verify_all.sh` on Daniel's desktop for
this lane. Build/archive only.

## One Command

Default full lane:

```bash
scripts/release-all.sh --skip-backend
```

Useful partial lanes:

```bash
# Mac TestFlight only
scripts/release-all.sh --skip-dmg --skip-notarize

# DMG build + notarize only
scripts/release-all.sh --skip-backend --skip-testflight

# GitHub/Sparkle only, after the DMG is already notarized
scripts/release-all.sh --skip-dmg --skip-notarize --skip-testflight --github --draft
```

The script writes artifacts to `build/releases/`.

## Required Local Assets

Developer ID DMG:

- Developer ID Application certificate for team `QAPB6CWYR6`.
- Notarytool credentials. `scripts/notarize.sh` tries the keychain profile first
  and falls back to the App Store Connect API key.

Sparkle/GitHub:

- Sparkle private Ed25519 key in Keychain:
  - service: `https://sparkle-project.org`
  - account: `ed25519`
- Sparkle public key baked into the app:
  `z3UPbmGi74NGSqTQL25E2WFD1yulIzYRvtDitbIZvNY=`
- `gh` authenticated for `dtubb/fichero`.

Mac TestFlight:

- Apple Distribution certificate for team `QAPB6CWYR6`.
- Mac App Store Connect provisioning profile for bundle id
  `app.fichero.fichero`.
- Current profile path expected by `scripts/release-all.sh`:
  `$MAC_APP_STORE_PROFILE_PATH` (default `$HOME/Downloads/Mac_App_Store_Connect.provisionprofile`)

That profile currently decodes as:

```text
Name: Mac App Store Connect
UUID: fe5c4814-a644-4d7a-a00a-ea93937a589e
App ID: QAPB6CWYR6.app.fichero.fichero
Team: QAPB6CWYR6
```

The matching Apple Distribution identity SHA-1 is:

```text
7CD87BA09F2DA8A79652710DE0F5E3C5DCD2CC35
```

`release-all.sh` copies the profile into
`~/Library/MobileDevice/Provisioning Profiles/` on every TestFlight run. Xcode's
Signing & Capabilities pane may still show `Provisioning Profile: None Required`
for local `My Mac` builds; that is not the TestFlight export path.

## DMG Details

`scripts/build-release-dmg.sh` is the canonical DMG builder. Its `[2b/6]` step is
load-bearing:

1. Find every Mach-O file inside the staged app, including the embedded Briefcase
   engine bundle.
2. Sign each Mach-O individually with Developer ID, hardened runtime, and a
   timestamp.
3. Re-seal bundles from innermost to outermost.
4. Verify before creating the DMG.

Do not replace this with `codesign --deep`; Apple previously rejected the loose
`.so`/`.dylib` files inside the embedded engine when they stayed ad-hoc signed.

Spot-check before notarizing:

```bash
STAGE="build/releases/dmg-stage/Fichero.app/Contents/Resources/Fichero Engine.app"
codesign -dv --verbose=4 "$STAGE/Contents/MacOS/Fichero Engine" 2>&1 | grep -E 'Authority|flags|Timestamp'
codesign -dv --verbose=4 "$STAGE/Contents/Resources/app_packages/_duckdb.cpython-312-darwin.so" 2>&1 | grep -E 'Authority|flags|Timestamp'
codesign -dv --verbose=4 "build/releases/dmg-stage/Fichero.app/Contents/Frameworks/Sparkle.framework" 2>&1 | grep -E 'Authority|flags|Timestamp'
```

Expected: Developer ID authority, `flags=0x10000(runtime)`, and a timestamp.

## Notarization

```bash
scripts/notarize.sh build/releases/Fichero.dmg
```

A successful notarization run should end with `status: Accepted`, staple the
DMG, and pass local staple validation.

Validate:

```bash
xcrun stapler validate build/releases/Fichero.dmg
```

## Sparkle And GitHub

The current appcast URL is:

```text
https://raw.githubusercontent.com/dtubb/fichero/main/fichero/appcast.xml
```

Do not change `SPARKLE_FEED_URL` without a rebuild; it is baked into the app
Info.plist.

Create the GitHub/Sparkle release:

```bash
scripts/create-github-release.sh --prerelease
```

or as a draft through the wrapper:

```bash
scripts/release-all.sh --skip-dmg --skip-notarize --skip-testflight --github --draft
```

If it hangs at Sparkle signing, unlock/approve Keychain access for the Sparkle
private key. Do not print or export the private key.

## Mac TestFlight

Run:

```bash
scripts/release-all.sh --skip-dmg --skip-notarize
```

The wrapper converts the project marketing version to a numeric App Store
version for TestFlight. For example:

```text
Project MARKETING_VERSION: 2026.06.26-beta
TestFlight MARKETING_VERSION: 2026.6.26
CURRENT_PROJECT_VERSION: 20260626
```

The wrapper currently archives `arm64` only and uses conservative Swift archive
settings to avoid Xcode 26 archive stalls:

```text
ARCHS=arm64
ONLY_ACTIVE_ARCH=YES
SWIFT_COMPILATION_MODE=singlefile
SWIFT_ENABLE_BATCH_MODE=NO
SWIFT_OPTIMIZATION_LEVEL=-Onone
```

This is for internal TestFlight builds. Revisit before a public Mac App Store
submission.

## Troubleshooting

DMG notarization:

- If notarization returns `Invalid`, fetch the notary log, identify the flagged
  binaries, fix the `[2b/6]` signing step in `scripts/build-release-dmg.sh`, and
  rebuild before submitting again.
- If any spot-check is ad-hoc signed, missing hardened runtime, or missing a
  timestamp, do not notarize. Rebuild and fix signing first.

Mac TestFlight:

- If the archive fails before export, parse the latest log and fix only the
  build-blocking compile/archive issue:

```bash
scripts/release-all.sh --skip-dmg --skip-notarize 2>&1 | tee build/releases/testflight-final-$(date +%Y%m%d-%H%M%S).log
rg -n "error:|ARCHIVE FAILED|EXPORT FAILED|uploaded|Upload|Done" build/releases/testflight-final-*.log
```

- If export fails with signing or provisioning errors, confirm the provisioning
  profile App ID, profile name, team ID, and Apple Distribution SHA-1 in this
  runbook still match the installed profile and certificate.
- Do not debug unrelated product behavior in this lane. Fix build, archive,
  export, upload, and release-script failures only.

Sparkle/GitHub:

- If `sign_update` blocks, Daniel must approve Keychain access.
- Do not print, export, or paste the Sparkle private key.

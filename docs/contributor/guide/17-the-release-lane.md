# 17. The Release Lane


The app ships through three separate outputs: a **notarized DMG** (Developer ID signed, Sparkle-signed, attached to a GitHub release), **Mac TestFlight** (macOS archive uploaded to App Store Connect), and **iPhone/iPad TestFlight** (one universal iOS archive; iOS is remote-only — no embedded engine, no Sparkle). This lane is build/archive-only — do not run test suites on the release machine while it runs.

### One command

    scripts/release-all.sh          # full lane: engine once, then DMG + Mac TF + iOS TF

The lane runs **unattended** end-to-end. Notable behavior:

- The wrapper builds the Briefcase engine once at the top and internally passes `--skip-backend` to the DMG sub-script so it reuses that engine — it is internal plumbing, not a flag you pass (the top-level parser rejects it).
- A **codesign preflight** test-signs a throwaway binary with each signing identity up front, failing fast with the one-time `security set-key-partition-list …` fix instead of hanging mid-build.
- `scripts/notarize.sh` **submits WITHOUT** `--wait` and polls `notarytool info` instead — the `--wait` mode hits deadline-exceeded failures. It staples once Apple returns Accepted. Do not “simplify” it back to `--wait`.
- TestFlight: `xcodebuild -exportArchive` returns on *upload*, not processing. By default the lane stops at a successful upload and lets Apple email the team; `--wait-for-processing` opts into polling the App Store Connect API (non-fatal — a failed poll warns and the lane still finishes).

Useful partial lanes:

    scripts/release-all.sh --skip-dmg --skip-notarize              # Mac + iOS TestFlight only
    scripts/release-all.sh --skip-testflight                       # DMG build + notarize only
    scripts/release-all.sh --skip-dmg --skip-notarize --mac-only   # Mac TestFlight only
    scripts/release-all.sh --skip-dmg --skip-notarize --ios-only   # iOS TestFlight only
    scripts/release-all.sh --skip-dmg --skip-notarize --skip-testflight --github --draft

Artifacts land in `build/releases/`.

### Required local assets

Developer ID DMG: a Developer ID Application certificate and notarytool credentials (keychain profile, falling back to an App Store Connect API key). Sparkle/GitHub: the Sparkle private Ed25519 key in the Keychain (the matching public key is baked into the app) and `gh` authenticated for the repo. TestFlight (both platforms): an Apple Distribution certificate and the platform’s App Store Connect provisioning profile at the path `release-all.sh` expects (`$MAC_APP_STORE_PROFILE_PATH` / `$IOS_APP_STORE_PROFILE_PATH`); the wrapper copies profiles into `~/Library/MobileDevice/Provisioning Profiles/` on every run. The iOS export uses manual signing — do not add `-allowProvisioningUpdates`.

### DMG signing details

`scripts/build-release-dmg.sh` is the canonical DMG builder. It stamps today’s dated version (`YYYY.MM.DD-beta`; override with `FICHERO_RELEASE_VERSION`), builds the Release app with the embedded engine, and — the load-bearing step — finds every Mach-O inside the staged app (including the embedded engine bundle’s loose `.so`/`.dylib` files), signs each individually with Developer ID, hardened runtime, and a timestamp, and re-seals bundles innermost-out. **Do not replace this with** `codesign --deep` — Apple previously rejected ad-hoc-signed engine libraries. Spot-check before notarizing with `codesign -dv --verbose=4` on the engine binary, a `.so` inside it, and the Sparkle framework: expect a Developer ID authority, `flags=0x10000(runtime)`, and a timestamp.

### Notarize, Sparkle, GitHub, TestFlight

    scripts/notarize.sh build/releases/Fichero.dmg     # ends status: Accepted, staples
    xcrun stapler validate build/releases/Fichero.dmg
    scripts/create-github-release.sh --prerelease      # Sparkle-sign + GitHub release

The appcast URL is baked into the app’s Info.plist — do not change the feed URL without a rebuild. If Sparkle signing hangs, approve Keychain access for the private key; never print or export it. The TestFlight leg converts the dated marketing version to a numeric App Store version and archives `arm64` with conservative Swift archive settings (internal-TestFlight expedient; revisit before a public Mac App Store submission).

Troubleshooting stays in-lane: on an `Invalid` notarization, fetch the notary log, fix the signing step, rebuild, resubmit. On export signing/provisioning errors, confirm the profile and certificate identities still match. Do not debug unrelated product behavior in the release lane — fix build, archive, export, upload, and release-script failures only. The version date is stamped at build time; it does not auto-update later.

------------------------------------------------------------------------

*Sources:* `docs/contributor/` *top-level pages,* `CONTRIBUTING.md`*, and* `AGENTS.md`*, consolidated and corrected against the code on the* `integration` *branch, 2026-08-27.*

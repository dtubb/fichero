# Xcode Build/Test/Run Configs — Design Spec (#TBD)

> Milestone: xcode-build-configs
> Manual: docs/contributor_manual/guide/10-setup-and-day-to-day-development.md

> Design-led (Testing Constitution). **Status: APPROVED — 2026-09-09** (invariants verified from
> the project this session). A guardrail pins them so config drift is a red test, not a debugging
> session. Tags: [OK] built · [MISSING] not built.

## Why this spec exists

The UI-test harness bug ([`ui-test-harness.md`](ui-test-harness.md)) was, at root, a **config
that had drifted from its own comments**: a source comment asserted "Dev Local is sandboxed"
while the actual build setting says the opposite — and that stale belief sent the test socket
into the real app container. Config truth currently lives only in prose comments that nothing
checks. This spec turns the build/test/run matrix into **executable invariants**.

## Intent (the design)

There is ONE authoritative statement of what each build config is for and what security/arch/
deployment shape it carries, and a guardrail (`scripts/check_xcode_config_invariants.py`) that
asserts it against `fichero.xcodeproj/project.pbxproj`, the `*.entitlements` files, the shared
`.xcscheme`s, and the `Tests/plans/*.xctestplan`s. A drifted comment or a flipped setting fails
the gate.

## The matrix (verified 2026-09-09)

| Scheme | Build config | Sandbox | Entitlements | Purpose |
|--------|--------------|---------|--------------|---------|
| Dev Local | `Debug` | **OFF** (`ENABLE_APP_SANDBOX = NO`) | `Fichero.entitlements` | day-to-day dev + the UI-test host; unsandboxed so tests reach temp-dir fixtures |
| Dev Embedded | `Dev Embedded` | ON | `Fichero.entitlements` | embedded-engine dev parity |
| Release Embedded / App Store | `Release` | ON | `FicheroRelease` / `FicheroAppStore` | DMG + MAS |

Cross-cutting invariants (all configs):
- **arm64-only** — `EXCLUDED_ARCHS = x86_64` on the project configs (Golden Gate, Apple silicon).
- **Deployment floor macOS 26 / iOS 27** — macOS supports 26 (Tahoe) and 27 (Golden Gate), requires 26; iOS and
  iPadOS stay 27 only (ruled 2026-10-17, reversing the 2026-10-10 "27 only" for macOS only; #5730). macOS 27-only
  APIs are availability-gated.
- **FicheroTests** carries `SWIFT_DEFAULT_ACTOR_ISOLATION = MainActor` (else ~575 SIGTRAPs —
  see [[test-target-needs-mainactor-default-isolation]]).
- The **embedded test plan** is attached to the Release Embedded scheme; dead plans stay deleted.

## Behaviors

- `config.dev-local-unsandboxed` [OK] — `Fichero (Dev Local)` → `Debug` → `ENABLE_APP_SANDBOX=NO`.
  Pinned: `test_check_xcode_config_invariants.py::test_real_project_is_clean`,
  `::test_debug_sandbox_flip_is_caught`.
- `config.release-sandboxed` [OK] — Release + App Store + Dev Embedded → sandbox ON.
  Pinned: `test_check_xcode_config_invariants.py::test_real_project_is_clean`,
  `::test_debug_sandbox_flip_is_caught`.
- `config.arm64-only` [OK] — every project config excludes `x86_64`. Pinned:
  `test_check_xcode_config_invariants.py::test_missing_excluded_archs_is_caught`.
- `config.deployment-floor-26` [OK] — `MACOSX_DEPLOYMENT_TARGET` is 26.x and `IPHONEOS_DEPLOYMENT_TARGET` is 27.x in
  the project, and `fichero-api-client/Package.swift` says macOS 26.0, iOS 27.0 (#5730). Pinned:
  `test_platform_floor_to_spec.py::test_real_project_floor_is_26`, `::test_a_target_left_at_27_is_caught`,
  `::test_an_ios_target_at_26_is_caught`.
- `platform.supports-tahoe-and-golden-gate` — **[GAP]** (#5730) the app builds, launches and works on macOS 26
  and 27, and on iOS 27 (iOS 26 is not supported). Test: `fichero-server/tests/unit/scripts/test_platform_floor_to_spec.py`.
- `platform.27-only-api-gated` — **[PARTIAL]** (#5730; audited 2026-10-20 against the macOS 27.0 SDK on this branch; the guard is built, unrun until an M4 pass) every 27-only API (Foundation Models image input and OCR tool,
  Core AI, 27 adapters) sits behind an availability check, with a 26 path where one exists. AUDIT RESULT: (1) the Mac app is
  compiled at floor 26.0, so an ungated 27-only API fails to compile there (no source-scan test is needed or built); the app
  imports neither FoundationModels nor CoreAI, and has no `#available` for 27 because none is used. (2) The one place the
  compiler did NOT enforce the floor was the helper compiled by a bare `swiftc` (the fm-bridge: `bin/fm-bridge/build.sh` and
  `bundle_python_backend.sh` built it for the host's OS, minos 27; only `build_fm_bridge.sh` named the floor): both now pass
  `-target arm64-apple-macos26.0`, and `scripts/check_swiftc_floor.py` fails any `swiftc` that builds the bridge without it
  (`fichero-server/tests/unit/scripts/test_check_swiftc_floor.py`). (3) The engine reads no OS version for any 27 path. (4)
  The 27-only features themselves (#5716 the on-device model as a reader, Core AI) are not built, so nothing is ungated; when one is built
  its code is `@available(macOS 27, *)` / `#available`, and it is named "needs macOS 27" where there is no 26 path
  (`platform.needs-27-said-plainly`). *Not built: a launch on a macOS 26 Mac or VM (the builder's / owner's, needs a 26 machine).*
- `platform.needs-27-said-plainly` — **[GAP]** (#5730) where no 26 path exists the UI says "needs macOS 27"
  rather than failing or hiding the control. Test: none yet (no 27-only feature exists).
- `config.mas-is-a-configuration` — **[PARTIAL]** (#5730, #3982; ruled 2026-10-17) the Mac App Store build is an
  `App Store` build configuration of the one `Fichero` target, not a second target (one embed phase). That
  configuration is sandboxed, uses `FicheroAppStore.entitlements`, defines `FICHERO_APP_STORE`, embeds the engine
  in `Contents/Helpers`, and is the one the `Fichero (App Store)` scheme archives; no other configuration defines
  `FICHERO_APP_STORE`. Guard: `scripts/check_mac_app_store_target.py`. Test:
  `fichero-server/tests/unit/scripts/test_check_mac_app_store_target.py`. Built 2026-10-17 by text edit: the
  `App Store` configuration (project and target, Release-derived, deployment macOS 26.0 / iOS 27.0), the App Store
  section of the one `Embed Fichero Server` phase (selected by `CONFIGURATION`), the strip and validate phases, and
  the scheme's archive action. The guard passes; no Mac build or archive has run yet (tester, one at a time).
- `config.mas-has-no-sparkle` — **[PARTIAL]** (#5730; App Review 2.4.5(vii)) Sparkle.framework is not inside the App
  Store build. With one target Sparkle is linked everywhere, so a `Remove Sparkle (App Store)` build phase deletes
  the framework for the `App Store` configuration only (after the frameworks and the engine are embedded), on top
  of the Info.plist key strip. The `Remove Sparkle (App Store)` phase is in the pbxproj (a no-op unless the
  configuration is `App Store`). The binary weak-links Sparkle (the build file carries `ATTRIBUTES = (Weak, )`), so it
  launches with the framework removed, and `SparkleUpdater.swift` is gated on `!FICHERO_APP_STORE`, never
  `canImport(Sparkle)` (which is true wherever the package resolves). Still owed: the `App Store` configuration
  itself. Guard: `check_mac_app_store_target.py`. Test:
  `test_check_mac_app_store_target.py::test_sparkle_is_removed_from_the_app_store_build`.
- `config.tests-mainactor-isolation` [OK] — FicheroTests configs set the MainActor default.
  Pinned: `test_check_xcode_config_invariants.py::test_missing_mainactor_isolation_is_caught`,
  `::test_mainactor_dropped_from_ficherotests_only_is_caught`.
- `config.embedded-testplan-attached` — **[PARTIAL]** (#4807) the embedded plan is referenced
  by its scheme, but re-checked 2026-09-18: `check_xcode_config_invariants.py` never actually
  asserts this — neither the guardrail's source nor its test file mentions "testplan" or
  "embedded" plan attachment at all. The other five invariants in this spec really are
  checked and tested; this one just isn't yet.
- `config.no-stale-sandbox-comments` [MISSING] (#4778) — no source comment asserts a config's sandbox
  state (the drift that caused the harness bug): the guardrail asserts the settings themselves, and
  the stale comments are deleted. Comment-checking is added only if the drift recurs (ruled
  2026-10-04, design lead).

## Test matrix

| Leg | This surface? | Pins | File |
|-----|---------------|------|------|
| Config guardrail (py) | y | every invariant above, parsed from project files | `scripts/check_xcode_config_invariants.py` |
| Gate wiring | y | the guardrail runs in `verify_all.sh` | `scripts/verify_all.sh` |

Hard-gate: all of `config.*`. These are cheap (file parse, no build) and catch the exact drift
class that stranded the harness.

## Rulings

- **Ruled 2026-10-04 (design lead, applying the spec's own lean):** assert the settings and delete
  the stale sandbox comments; add comment-checking only if the drift recurs
  (`config.no-stale-sandbox-comments`).

## Open questions

None outstanding.
- `config.no-stale-sandbox-comments`: ~~worth the parsing complexity?~~ **Answered 2026-10-04:**
  no; assert settings, delete stale comments (see Rulings).

## Triaged from the backlog (2026-10-04)
- `config.shipping-configuration-is-tested` — **[GAP]** (#4226) a check exercises the configuration users get (DMG/App Store: UDS, sandbox, bookmarks), and the Swift gate and scripts/check_*.py guards are run together so neither can go red unseen.
- `build.swiftlint-phase-reruns-on-change` — **[GAP]** (#5096) the SwiftLint build phase declares file inputs that change when a source changes, so a fixed lint error stops being reported.
- `build.ios-target-compiles-without-macos-only-types` — **[PARTIAL]** (#5322) the iOS target compiles: EmbeddedBackendService.backendProcess (Process) is guarded `#if os(macOS)` in the property and both uses on this branch (read, 2026-10-17); a generic iOS Simulator build has not run, so it stays PARTIAL until one is green. Test: `fichero/Tests/Unit/general/Services/IOSTargetMacOnlyTypesGuardrailTests.swift`.

## Triaged from the older signing plans (2026-10-17)
The signing-ladder and engine-entitlements plans are retired into these entries. Ruling 2026-10-17 wins over those plans: the Mac App Store build is a CONFIGURATION and scheme of the one Fichero target sharing one embed phase (#3982), not a separate target, so the ladder's "App Store target untouched" no longer applies.
- `signing.dmg-engine-sandboxed-entitlements` — **[GAP]** (#5741) the DMG signs the embedded engine with `FicheroEngineSandboxed.entitlements` (sandbox + inherit + the cs.* keys the engine needs), not `FicheroEngine.entitlements` as `scripts/build-release-dmg.sh:114` does today; the file does not exist yet. Test: `fichero-server/tests/unit/scripts/test_resign_engine_entitlement_keys.py` (extend to the 6-key file).
- `signing.rung-2-proved-by-one-notarization` — **[GAP]** (#5741) before a release the sandboxed engine is notarized once and launched under the sandbox on Tahoe and Golden Gate; the result is recorded, not assumed. Test: `fichero-server/tests/unit/scripts/test_resign_engine_entitlement_keys.py` (guards the keys; the notarization run is a release-checklist step).
- `signing.one-embed-phase-all-configurations` — **[PARTIAL]** (#3982) DMG and App Store configurations share one embed phase and so one signed engine. Pinned: `fichero-server/tests/unit/scripts/test_embed_phase_one_engine_for_dmg_and_mas_3982.py`; the sandboxed-entitlements half is #5741.
- `signing.bookmark-keys-in-every-shipping-entitlements` — **[PARTIAL]** (#5741) the security-scoped bookmark keys are in the Fichero, FicheroRelease and FicheroAppStore entitlements; the container-tmp allowance is documented at `api/main.py:1403`. Test: `fichero-server/tests/unit/scripts/test_check_xcode_config_invariants.py`.

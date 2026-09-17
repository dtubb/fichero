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
- **Deployment floor macOS 26** — support 26 + 27, require 26.
- **FicheroTests** carries `SWIFT_DEFAULT_ACTOR_ISOLATION = MainActor` (else ~575 SIGTRAPs —
  see [[test-target-needs-mainactor-default-isolation]]).
- The **embedded test plan** is attached to the Release Embedded scheme; dead plans stay deleted.

## Behaviors

- `config.dev-local-unsandboxed` [OK] — `Fichero (Dev Local)` → `Debug` → `ENABLE_APP_SANDBOX=NO`.
- `config.release-sandboxed` [OK] — Release + App Store + Dev Embedded → sandbox ON.
- `config.arm64-only` [OK] — every project config excludes `x86_64`.
- `config.deployment-floor-26` [OK] — `MACOSX_DEPLOYMENT_TARGET` floor is 26.
- `config.tests-mainactor-isolation` [OK] — FicheroTests configs set the MainActor default.
- `config.embedded-testplan-attached` [OK] — the embedded plan is referenced by its scheme.
- `config.no-stale-sandbox-comments` [MISSING] — a source comment asserting a config's sandbox
  state must match the actual setting (the drift that caused the harness bug).

## Test matrix

| Leg | This surface? | Pins | File |
|-----|---------------|------|------|
| Config guardrail (py) | y | every invariant above, parsed from project files | `scripts/check_xcode_config_invariants.py` |
| Gate wiring | y | the guardrail runs in `verify_all.sh` | `scripts/verify_all.sh` |

Hard-gate: all of `config.*`. These are cheap (file parse, no build) and catch the exact drift
class that stranded the harness.

## Open questions

- `config.no-stale-sandbox-comments`: worth the parsing complexity, or is asserting the *settings*
  enough and we just delete the stale comments? (Lean: assert settings; delete stale comments as
  part of the harness fix; add comment-checking only if drift recurs.)

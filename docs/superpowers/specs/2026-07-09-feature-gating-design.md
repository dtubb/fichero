# Feature Gating — 4-Tier Design (dev / alpha / beta / release)

**Status:** approved 2026-07-09. **Builds ON the existing gate** — `FeatureManager.swift`,
`FICHERO_FEATURE_TIER`, `resolve_feature_tier()`, `get_route_specs_for_tier()`,
`register_tiered_routes()`, `docs/user/features.md`. No parallel system.

## Decisions (locked)

1. **One build at a time** — single `Fichero` target; tier via build config, no side-by-side bundle IDs.
2. **Hybrid baked + env** — `FICHERO_FEATURE_TIER` baked per build config into the binary; shipped app reads baked first, env fallback (conftest / CI / local-override keep working).
3. **Maturity floor** — `build tier T shows features with maturity >= T` (release=release only; beta=beta+release; alpha=alpha+beta+release; dev=all).
4. **Declarative source of truth** — `features.yaml` → codegen emits Swift tier map + backend route sets + `docs/user/features.md`. One input, three outputs.

## Tier model

Maturity rank, least → most mature:

| rank | tier   | meaning                                          | who sees it (build tier) |
|------|--------|--------------------------------------------------|--------------------------|
| 1    | dev    | AI has done it (rawest)                          | dev build only           |
| 2    | alpha  | Daniel needs to go through (review queue)        | alpha + dev              |
| 3    | beta   | users / testers can use                          | beta + alpha + dev       |
| 4    | release| public                                           | all builds               |

Visibility predicate: `isVisible(key) = key.tier.rank >= activeBuildTier.rank`.

## A. Source of truth + codegen (worker lane)

New `features.yaml` at repo root. One entry per feature:

```yaml
- key: research
  name: Research
  tier: release
  swift_flag: fichero.features.research          # existing @AppStorage key, or null
  routes: ["/api/research"]                       # backend route prefixes, or []
  ux_group: Library
  notes: "KG-backed research surface"
```

`scripts/gen_feature_tiers.py` reads `features.yaml` and emits:

1. `fichero/fichero/Models/FeatureTiers.generated.swift`
   - `enum FeatureTier: Int, Comparable { case dev = 1, alpha = 2, beta = 3, release = 4 }`
   - `enum FeatureKey: String { case research, knowledgeGraph, workflows, chat, agents, ... }`
   - `struct FeatureTiers` with `static let map: [FeatureKey: FeatureTier]` + per-feature UX label.
2. `fichero-server/src/fichero_server/api/feature_tiers_generated.py`
   - route-prefix → tier map; `main.py` builds cumulative route-spec lists:
     `_RELEASE ⊆ _BETA ⊆ _ALPHA ⊆ _DEV` (each adds the next tier's routes).
3. `docs/user/features.md` — the matrix, sorted by tier, regenerated.

CI freshness gate (mirror the existing openapi freshness check in
`scripts/verify_python.sh` + `.github/workflows/ci.yml`): if `features.yaml`
changed without regen → exit 1.

## B. Tier mechanism (baked + env, hybrid)

- `FICHERO_FEATURE_TIER` is a Swift build setting per build config → baked into the
  binary. `FeatureManager.activeBuildTier` reads baked first, env `FICHERO_FEATURE_TIER`
  fallback (so `conftest.py` `os.environ.setdefault(..., "dev")`, CI, and local dev
  override keep working exactly as today).
- `EmbeddedBackendService` passes `activeBuildTier` to the engine subprocess as the
  `FICHERO_FEATURE_TIER` env → engine tier == app tier automatically (no separate config).
- Backend `resolve_feature_tier()` extends its valid set from `{release, dev}` →
  `{release, beta, alpha, dev}`, default `release`, same warning-on-unknown behavior.

## C. Visibility predicate (maturity floor) — extend `FeatureManager`

- `FeatureManager.activeBuildTier: FeatureTier` (baked-first, env fallback).
- `func isVisible(_ key: FeatureKey) -> Bool { FeatureTiers.map[key]!.rank >= activeBuildTier.rank }`.
- Each existing `@AppStorage` flag stays. Each `isXEnabled` computed property becomes
  `isVisible(.x) && (allFeaturesEnabled || xEnabledInternal)`.
- **`allFeaturesEnabled` only reveals features within your build tier — it cannot cross
  the floor.** A release build physically cannot show dev/alpha/beta features even with
  `FICHERO_ALL_FEATURES=1`. (This is the safety property Daniel asked for.)
- `isDevFeatureTier` deprecated → replaced by `activeBuildTier == .dev`.
- `releaseProfileVersion` / `resetToV001()` unchanged — they still seed the `@AppStorage`
  defaults; tier visibility is layered on top.

## D. Xcode schemes / targets / destinations (manager does this first)

Single `Fichero` target — no new targets. Build configurations are the full
**tier x backend-mode grid** (8 Mac configs). The existing 4 keep their names
(`release-all.sh` / `build-and-validate.sh` hardcode `-configuration Release`),
each now carrying `FICHERO_EMBED_ENGINE` alongside `FICHERO_FEATURE_TIER`;
4 new configs are cloned for the Embedded / Local variants:

| config            | FICHERO_FEATURE_TIER | FICHERO_EMBED_ENGINE | role                  |
|-------------------|----------------------|----------------------|-----------------------|
| Debug             | dev                  | NO                   | Dev Local             |
| Dev Embedded      | dev                  | YES                  | Dev Embedded          |
| Alpha             | alpha                | NO                   | Alpha Local           |
| Alpha Embedded    | alpha                | YES                  | Alpha Embedded        |
| Beta              | beta                 | NO                   | Beta Local            |
| Beta Embedded     | beta                 | YES                  | Beta Embedded         |
| Release           | release              | YES                  | Release Embedded (DMG)|
| Release Local     | release              | NO                   | Release Local         |

- The engine embed run-script gates on `FICHERO_EMBED_ENGINE != YES` (was
  `CONFIGURATION != Release`), so the Local variants skip embedding and expect
  an external engine on `:8765`; the Embedded variants bundle + spawn it.
- Schemes follow the strict `(Tier, Mode)` convention - 8 Mac + 4 iOS (iOS is
  always Local; the Python engine can't run on-device, so no iOS Embedded):
  `Fichero (Dev Local|Dev Embedded|Alpha Local|Alpha Embedded|Beta Local|Beta
  Embedded|Release Local|Release Embedded)` on Mac, and
  `Fichero (Dev|Alpha|Beta|Release Local iOS)` on iOS. Every build action
  (Test/Launch/Profile/Analyze/Archive) is set to the scheme's tier config, so
  the baked tier/embed flow through - no per-scheme `FICHERO_FEATURE_TIER` env
  var (the config bakes it; the app reads baked-first).
- `FicheroTests` + `FicheroUITests (Debug) iOS` schemes untouched.
- `FICHERO_FEATURE_TIER` build setting per config -> Info.plist `FicheroFeatureTier`
  key (read by `Bundle.main.infoDictionary`).

## E. UX flagging (dev / alpha / beta only; release shows nothing)

- Menu items for non-release features get a tier suffix: `Research [BETA]`, `Agent Chat [DEV]`.
- A "Build Tier" status indicator (toolbar label or Help-menu line): *"DEV build —
  features shown at tier ≥ dev."*
- A `Feature Tier Legend…` Help-menu item (non-release only) showing the tier color/label key.
- Release build: no badges, no legend, no indicator — clean public UI.

## F. Matrix doc + checklist + promotion

- `docs/user/features.md` (generated from `features.yaml`) — user-facing matrix, sorted by tier.
- `docs/contributor/feature-tiers.md` (hand-written, stable) — tier definitions, promotion
  workflow, per-tier test/review checklist:
  - **dev:** AI added; tests pass; swiftlint clean.
  - **alpha:** Daniel reviewed (UX, edge cases, undo, side-effects).
  - **beta:** smoke-tested on clean install + TestFlight build checklist.
  - **release:** full pytest + adversarial/security tests green + docs updated + appcast/DMG signed.
- Promotion = edit `features.yaml` (bump `tier:`), regen, commit.
- Optional `scripts/promote_feature.py` validates the target tier's checklist is satisfied
  before allowing the bump (lint-strict; no network).

## Execution split

1. **Manager (this session) — Xcode setup.** Fix `(Debug) Mac` scheme; add `Alpha`/`Beta`
   build configs + schemes; wire `FICHERO_FEATURE_TIER` per config; build-prove (serial,
   compile-only — **no `xcodebuild test`** on Daniel's active desktop). Owns: `project.pbxproj`,
   all `*.xcscheme`, `Info.plist`.
2. **One codex worker** — fresh worktree reset to `origin/main=99cb5191a`,
   `codex -m gpt-5.4 --dangerously-bypass-approvals-and-sandbox`. Builds A, B, C, F + tests.
   Disjoint files from deferred pure-Python lanes (#3185/#3186/#3193). Commits authored as Codex.
3. **Manager gates in `~/code/fichero-worktrees/integrate`** — backend pytest with
   `PYTHONPATH=<integrate>/fichero-server/src`; Swift compile-only + swiftlint; fix codex
   compile errors; add `FeatureTiers.generated.swift` to the Fichero target's Sources build
   phase (pbxproj membership — worker writes file to disk, manager adds membership);
   build-prove serially. Green → `git push origin HEAD:main` + `gh issue close`.

### File ownership (disjoint)

| owner    | files                                                                                |
|----------|--------------------------------------------------------------------------------------|
| manager  | `project.pbxproj`, `*.xcscheme`, `Info.plist`                                         |
| worker   | `features.yaml` (new), `scripts/gen_feature_tiers.py` (new), `scripts/promote_feature.py` (new, optional), `fichero/fichero/Models/FeatureTiers.generated.swift` (new, generated — **manager adds to target**), `fichero/fichero/Models/FeatureManager.swift` (extend), `fichero-server/src/fichero_server/api/main.py` (extend tier fns), `fichero-server/src/fichero_server/api/feature_tiers_generated.py` (new, generated), `docs/user/features.md` (regenerate), `docs/contributor/feature-tiers.md` (new), `fichero-server/tests/unit/test_feature_tier_routing.py` (extend), `fichero/fichero/Services/EmbeddedBackendService.swift` (extend env passthrough), `.github/workflows/ci.yml` + `scripts/verify_python.sh` (freshness gate) |

## Gate criteria (worker lane, before push)

- `python scripts/gen_feature_tiers.py` runs clean; regenerated outputs match committed.
- Freshness gate exits 0 after regen; exits 1 if `features.yaml` changed without regen.
- Backend: `PYTHONPATH=<integrate>/fichero-server/src pytest fichero-server/tests/unit/test_feature_tier_routing.py` green; extend it to cover all 4 tiers + cumulative route sets + unknown-tier→release.
- `test_integration_security.py::TestFeatureTierSecurity` still green (dev routes 404 in release; now also alpha/beta routes 404 in release+beta respectively).
- Swift: `swiftlint` clean; `FeatureTiers.generated.swift` compiles; `FeatureManager` changes compile.
- No `xcodebuild test` on Daniel's machine — compile-only gate only.
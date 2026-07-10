# Feature Tiers

Fichero's contributor-facing feature tier system has one source of truth: [`features.yaml`](/Users/danieltubb/code/fichero-worktrees/scripts-tier/features.yaml). `python scripts/gen_feature_tiers.py` regenerates three derived artifacts from it: the Swift tier map in [`fichero/fichero/Models/FeatureTiers.generated.swift`](/Users/danieltubb/code/fichero-worktrees/scripts-tier/fichero/fichero/Models/FeatureTiers.generated.swift), the backend route-tier data in [`fichero-engine/src/fichero/api/feature_tiers_generated.py`](/Users/danieltubb/code/fichero-worktrees/scripts-tier/fichero-engine/src/fichero/api/feature_tiers_generated.py), and the public matrix in [`docs/user/features.md`](/Users/danieltubb/code/fichero-worktrees/scripts-tier/docs/user/features.md).

## Tiers

[`FeatureTier`](/Users/danieltubb/code/fichero-worktrees/scripts-tier/fichero/fichero/Models/FeatureTiers.generated.swift:5) defines four ordered ranks:

| Rank | Tier | Meaning |
|---|---|---|
| 1 | `dev` | AI added; rawest tier. |
| 2 | `alpha` | Daniel review queue. |
| 3 | `beta` | Tester-facing candidate. |
| 4 | `release` | Publicly shipped. |

The generated backend route sets implement a maturity floor: a build tier `T` exposes features and routes whose maturity rank is greater than or equal to `T`. [`CUMULATIVE_ROUTE_PREFIXES`](/Users/danieltubb/code/fichero-worktrees/scripts-tier/fichero-engine/src/fichero/api/feature_tiers_generated.py:190) shows that rule directly:

- `release` includes `release` routes only.
- `beta` includes `beta` and `release` routes.
- `alpha` includes `alpha`, `beta`, and `release` routes.
- `dev` includes every tier.

On the app side, the baked tier key is [`FicheroFeatureTier`](/Users/danieltubb/code/fichero-worktrees/scripts-tier/fichero/fichero/Info.plist:20) and the environment override name is `FICHERO_FEATURE_TIER`. The backend resolves `FICHERO_FEATURE_TIER` in [`resolve_feature_tier()`](/Users/danieltubb/code/fichero-worktrees/scripts-tier/fichero-engine/src/fichero/api/main.py:1554) with valid values `release`, `beta`, `alpha`, and `dev`, defaulting to `release` on missing or unknown input. In this branch, [`FeatureManager.swift`](/Users/danieltubb/code/fichero-worktrees/scripts-tier/fichero/fichero/Models/FeatureManager.swift:23) still stores individual `@AppStorage` flags and only checks `FICHERO_FEATURE_TIER == "dev"` for `isProvidersEnabled`, so contributors should treat `features.yaml` plus the generated outputs as the canonical tier map when promoting features.

## Promotion

Promotion is a source edit plus regeneration:

1. Change that feature's `tier:` in [`features.yaml`](/Users/danieltubb/code/fichero-worktrees/scripts-tier/features.yaml).
2. Run `python scripts/gen_feature_tiers.py`.
3. Commit the YAML change and the regenerated outputs together.

Use [`docs/user/features.md`](/Users/danieltubb/code/fichero-worktrees/scripts-tier/docs/user/features.md) to verify the generated user-facing matrix after the bump.

`scripts/promote_feature.py` is a read-only validator for this workflow. It checks that the feature exists, the tier change is a real promotion unless `--allow-demote` is set, the generated files are fresh, and beta-or-higher route promotions still match the backend cumulative route data.

## Checklist

Promotion should satisfy the target tier before you bump `tier:`:

| Target tier | Minimum contributor checklist |
|---|---|
| `dev` | AI added; tests pass; `swiftlint` clean. |
| `alpha` | Daniel reviewed UX, edge cases, undo behavior, and side-effects. |
| `beta` | Smoke-tested on a clean install and through the TestFlight build checklist. |
| `release` | Full `pytest` and adversarial/security tests green; docs updated; appcast/DMG signed. |

## Ownership

Promotion spans disjoint lanes:

- Scripts/docs lane edits [`features.yaml`](/Users/danieltubb/code/fichero-worktrees/scripts-tier/features.yaml), runs [`scripts/gen_feature_tiers.py`](/Users/danieltubb/code/fichero-worktrees/scripts-tier/scripts/gen_feature_tiers.py), updates this page, and validates with [`scripts/promote_feature.py`](/Users/danieltubb/code/fichero-worktrees/scripts-tier/scripts/promote_feature.py).
- The generated user matrix lives in [`docs/user/features.md`](/Users/danieltubb/code/fichero-worktrees/scripts-tier/docs/user/features.md); do not hand-edit it.
- Manager-owned Xcode files such as `Info.plist`, schemes, and `project.pbxproj` stay out of the promotion lane even though they carry the baked `FicheroFeatureTier` build setting.

# Feature Tiers

Fichero's contributor-facing feature tier system has one source of truth: [`features.yaml`](../../features.yaml). `python scripts/gen_feature_tiers.py` regenerates three derived artifacts from it: the Swift tier map in [`fichero/fichero/Models/FeatureTiers.generated.swift`](../../fichero/fichero/Models/FeatureTiers.generated.swift), the backend route-tier data in [`fichero-engine/src/fichero/api/feature_tiers_generated.py`](../../fichero-engine/src/fichero/api/feature_tiers_generated.py), and the public matrix in [`docs/user/features.md`](../user/features.md).

## Tiers

[`FeatureTier`](../../fichero/fichero/Models/FeatureTiers.generated.swift:5) defines four ordered ranks:

| Rank | Tier | Meaning |
|---|---|---|
| 1 | `dev` | AI added; rawest tier. |
| 2 | `alpha` | Daniel review queue. |
| 3 | `beta` | Tester-facing candidate. |
| 4 | `release` | Publicly shipped. |

The generated backend route sets implement a maturity floor: a build tier `T` exposes features and routes whose maturity rank is greater than or equal to `T`. [`CUMULATIVE_ROUTE_PREFIXES`](../../fichero-engine/src/fichero/api/feature_tiers_generated.py:190) shows that rule directly:

- `release` includes `release` routes only.
- `beta` includes `beta` and `release` routes.
- `alpha` includes `alpha`, `beta`, and `release` routes.
- `dev` includes every tier.

On the app side, the baked tier key is [`FicheroFeatureTier`](../../fichero/fichero/Info.plist:20) and the environment override name is `FICHERO_FEATURE_TIER`. The backend resolves `FICHERO_FEATURE_TIER` in [`resolve_feature_tier()`](../../fichero-engine/src/fichero/api/main.py:1554) with valid values `release`, `beta`, `alpha`, and `dev`, defaulting to `release` on missing or unknown input. In this branch, [`FeatureManager.swift`](../../fichero/fichero/Models/FeatureManager.swift:23) reads `activeBuildTier` from the baked `FicheroFeatureTier` Info.plist key, then `FICHERO_FEATURE_TIER`, then defaults to `.dev`. `isVisible(_:)` enforces the maturity floor with `FeatureTiers.map[key]!.tier.rank >= activeBuildTier.rank`, and each `isXEnabled` property gates its stored flag behind `isVisible(key) && (allFeaturesEnabled || flag)`, so `allFeaturesEnabled` still cannot surface features below the active build tier. [`isDevFeatureTier`](../../fichero/fichero/Models/FeatureManager.swift:170) is now deprecated shorthand for `activeBuildTier == .dev`.

## Promotion

Promotion is a source edit plus regeneration:

1. Change that feature's `tier:` in [`features.yaml`](../../features.yaml).
2. Run `python scripts/gen_feature_tiers.py`.
3. Commit the YAML change and the regenerated outputs together.

Use [`docs/user/features.md`](../user/features.md) to verify the generated user-facing matrix after the bump.

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

- Scripts/docs lane edits [`features.yaml`](../../features.yaml), runs [`scripts/gen_feature_tiers.py`](../../scripts/gen_feature_tiers.py), updates this page, and validates with [`scripts/promote_feature.py`](../../scripts/promote_feature.py).
- The generated user matrix lives in [`docs/user/features.md`](../user/features.md); do not hand-edit it.
- Manager-owned Xcode files such as `Info.plist`, schemes, and `project.pbxproj` stay out of the promotion lane even though they carry the baked `FicheroFeatureTier` build setting.

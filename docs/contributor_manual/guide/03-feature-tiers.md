# 3. Feature Tiers


The tier system has one source of truth: `features.yaml` at the repo root. `python scripts/gen_feature_tiers.py` regenerates three derived artifacts: the Swift tier map (`fichero/fichero/Models/FeatureTiers.generated.swift`), the backend route-tier data (`fichero-server/src/fichero_server/api/feature_tiers_generated.py`), and the public matrix (`docs/user/features.md`). Never hand-edit the generated files.

`FeatureTier` defines four ordered ranks:

| Rank | Tier      | Meaning                  |
|------|-----------|--------------------------|
| 1    | `dev`     | AI added; rawest tier.   |
| 2    | `alpha`   | Maintainer review queue. |
| 3    | `beta`    | Tester-facing candidate. |
| 4    | `release` | Publicly shipped.        |

The generated route sets implement a maturity floor: a build at tier `T` exposes routes whose maturity rank is ≥ `T`. `CUMULATIVE_ROUTE_PREFIXES` and `get_route_specs_for_tier` in `feature_tiers_generated.py` are the source of truth — check them rather than assuming what a tier includes. The **release tier route set is deliberately small**: most knowledge-graph, research, chains, and automation surfaces sit at beta or dev tier. A default (`release`) engine registers only a fraction of the tier-gated route groups; a hand-started engine at the default tier will 404 the entire workflow/KG surface, which reads as “the CLI is broken.” A gated route’s 404 names the tier that would expose it (`install_tier_aware_not_found` in `api/main.py`).

The backend resolves `FICHERO_FEATURE_TIER` in `resolve_feature_tier()` (valid values `release`/`beta`/`alpha`/`dev`, defaulting to `release`). On the app side, `FeatureManager` reads the baked `FicheroFeatureTier` Info.plist key, then the `FICHERO_FEATURE_TIER` environment override. `isVisible(_:)` enforces the maturity floor, and each `isXEnabled` property gates its stored flag behind visibility — `allFeaturesEnabled` cannot surface features below the active build tier.

**Promotion** is a source edit plus regeneration: change the feature’s `tier:` in `features.yaml`, run `python scripts/gen_feature_tiers.py`, commit the YAML change and the regenerated outputs together. `scripts/promote_feature.py` is a read-only validator: it checks the feature exists, the change is a real promotion (unless `--allow-demote`), the generated files are fresh, and beta-or-higher promotions match the backend cumulative route data.

Minimum checklist before bumping `tier:`:

| Target tier | Checklist |
|----|----|
| `dev` | Added; tests pass; `swiftlint` clean. |
| `alpha` | Maintainer reviewed UX, edge cases, undo behavior, side-effects. |
| `beta` | Smoke-tested on a clean install and through the TestFlight checklist. |
| `release` | Full `pytest` and adversarial/security tests green; docs updated; appcast/DMG signed. |

------------------------------------------------------------------------

# STATE.md — Fichero

## Snapshot

**Branch:** `0.0.2`

## Current Focus

All four planned phases complete. Branch `0.0.2` is clean and pushed. Ready for Daniel to test.

## Completed overnight (2026-05-24 → 2026-05-25)

1. ✅ **Phase 1 — Dependabot liquidjs** — bumped to ≥ 10.25.7 via `overrides` in `site/package.json`.
2. ✅ **Phase 2 — SwiftLint** — zero warnings across all 334 Swift files.
3. ✅ **Phase 3 — #1201 OpenAPI freshness gate** — step 7 in `verify_python.sh`; NodeDef-Input schema removed from both contract files and Swift client; issue closed.
4. ✅ **Phase 4 — KG entity library (#1183/#1191)** — `entity inspector` CLI command + `getEntityInspector()` Swift service method + `EntitySourceGroupsView` (dense claim prose grouped by source doc/page) wired into `EntityDetailView` as a mode toggle. Issues closed.

## In Progress

Nothing.

## Next Session — Start Here

Branch is green. Things Daniel may want to test before considering 0.0.2 ready for release:
- Entity inspector source-groups mode: open the KG panel, click an entity, hit the magnifying-glass button in the Claims header.
- `fichero entity inspector <entity-id>` via the CLI.
- OpenAPI freshness gate: `bash scripts/verify_all.sh` should pass end-to-end.

Release checklist items still pending (#157–#165 in GitHub):
- Audit + edit site pages (printouts in hand)
- Set up App Store Connect API key for notarization
- Verify Sparkle EdDSA private key / build signed DMG / notarize / staple / release

## Known issues / gotchas

- `add-swift-file.rb` required a monkey-patch for xcodeproj 1.27.0 incompatibility with Xcode 16+ project format (Array shellScript value). The patch is in the script.
- OpenRouter weekly key quota can hard-stop remote vision/extraction runs (`403 Key limit exceeded`) on some libraries.

## Global rules

- Canonical gate: `bash scripts/verify_all.sh`
- Register every new `.swift` file with `ruby scripts/add-swift-file.rb fichero/fichero/Path/To/File.swift`
- GitHub Issues is the canonical backlog; commit directly to `0.0.2`
- Never hand-edit `openapi.json` or generated `fichero-api-client` sources

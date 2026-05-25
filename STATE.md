# STATE.md — Fichero

## Snapshot

**Branch:** `0.0.2`

## Current Focus

Daniel testing 0.0.2. If passes, release checklist (#157–#165) in order.
Multi-agent split active: frontend Claude (#1202/#1204/#1181), backend Codex (#1054/#1173/#1198), pi CLI (imports).

**Manager triage (2026-05-25 8:13a):** inbox empty, no BLOCK. Labelled 5 orphan issues —
#1175→both, #1145→backend, #1146→frontend.
✅ Verified-and-closed via read-only subagent: **#1147** (contract endpoint-walk test —
`test_contract_endpoint_walk.py`, 2 passed) and **#1148** (CLI = in-process engine consumer,
option b; live `test_cli_engine_contract.py`). Filed **#1205** (chore/backend) to delete the
now-dead generated Python CLI client + its regen step — leftover from #1148's option (b).

## Agent split (2026-05-25)

Issues are labelled `frontend` / `backend` / `both` on GitHub.

| Agent | Does | Filter |
|---|---|---|
| **Claude (this session)** | SwiftUI: entity biography #1202, click-to-sync #1204, JSON inspector #1181, KG polish | `label:frontend` |
| **Backend Claude / Codex** | Python/FastAPI: pronoun coreference #1173, search relevance #1054, entity digest export #1198 | `label:backend` |

Start a backend session with: `gh issue list --label backend --state open`

## Completed this session (2026-05-25 morning)

- ✅ #1186 Navigation history — back/forward chevron buttons + Cmd+' / Cmd+Shift+' in OntologyBrowser
- ✅ OpenAPI freshness gate fixed — NodeDef-Input orphan schema removed from both contract files
- ✅ Chains router promoted to core tier (#1151) — Swift FeatureManager, OpenAPI re-synced
- ✅ Filed #1202 (biography text), #1203 (geo/temporal map), #1204 (click-to-sync)
- ✅ GitHub issues labelled frontend/backend/both
- ✅ 4 specialized session-start skills + .ai/inbox/ messaging infrastructure

## Completed overnight (2026-05-24 → 2026-05-25)

1. ✅ **Phase 1 — Dependabot liquidjs** — bumped to ≥ 10.25.7 via `overrides` in `site/package.json`.
2. ✅ **Phase 2 — SwiftLint** — zero warnings across all 334 Swift files (Codex, 6 commits).
3. ✅ **Phase 3 — #1201 OpenAPI freshness gate** — step 7 in `verify_python.sh`; gate implemented and issue closed.
4. ✅ **Phase 4 — KG entity library (#1183/#1191)** — `entity inspector` CLI command + `getEntityInspector()` Swift service method + `EntitySourceGroupsView` wired into `EntityDetailView`.

## Next Session — Start Here (frontend Claude)

**Daniel is testing 0.0.2.** Fix any bugs found. If testing passes, work release checklist in order.

**Two things to verify first:**
1. Entity source-groups mode: KG panel → pick entity → magnifying-glass icon in Claims header → should show prose grouped by source doc
2. `fichero entity inspector <entity-id>` in the CLI — should return JSON with source-grouped claims

**If 0.0.2 passes testing — release checklist in order:**
- #157 Site pages audit (printouts)
- #158/#159 App Store Connect API key + Sparkle EdDSA key verification  ← likely blocker, tackle first
- #160 Signed Release app + DMG build
- #161 Notarize + staple
- #162 Sparkle-sign + GitHub release + tag
- #163 Deploy site
- #164 Smoke test on clean Mac account
- #165 Merge 0.0.2 → main

**If bugs found — prioritize fixes, then re-verify, then resume checklist.**

Pending frontend issues (lower priority until release checklist clear):
- #1202 Entity biography text view (EntityDetailView.swift, `/api/entities/{id}/claims`)
- #1204 Click-to-sync (claim row onTapGesture → Jump to source page)
- #1181 JSON artifact inspector (verify GenericJSONInspector is still in DocumentInspectorArtifactsTab.swift)

## Next Session — Start Here (backend Claude / Codex)

```bash
gh issue list --label backend --state open --limit 20
```

Top priorities:
- **#1054** search relevance threshold — `fichero-engine/src/fichero/api/search.py`, add min-score filter
- **#1173** KG pronoun coreference — post-extraction resolver in `fichero-engine/src/fichero/kg/`
- **#1198** entity digest export (PDF/MD/text) — new endpoint + CLI command

## Known issues / gotchas

- `add-swift-file.rb` required a monkey-patch for xcodeproj 1.27.0 incompatibility with Xcode 16+ project format (Array shellScript value). The patch is in the script.
- OpenRouter weekly key quota can hard-stop remote vision/extraction runs (`403 Key limit exceeded`) on some libraries.

## Global rules

- Canonical gate: `bash scripts/verify_all.sh`
- Register every new `.swift` file with `ruby scripts/add-swift-file.rb fichero/fichero/Path/To/File.swift`
- GitHub Issues is the canonical backlog; commit directly to `0.0.2`
- Never hand-edit `openapi.json` or generated `fichero-api-client` sources

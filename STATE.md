# STATE.md — Fichero

## Snapshot

**Branch:** `0.0.2`

## Current Focus

Active development on KG inspector and entity biography views (Daniel's May 25 vision).
Release checklist (#157–#165) deferred until Daniel approves 0.0.2 testing.

## Agent split (2026-05-25)

Issues are labelled `frontend` / `backend` / `both` on GitHub.

| Agent | Does | Filter |
|---|---|---|
| **Claude (this session)** | SwiftUI: entity biography #1202, click-to-sync #1204, JSON inspector #1181, KG polish | `label:frontend` |
| **Backend Claude / Codex** | Python/FastAPI: pronoun coreference #1173, search relevance #1054, entity digest export #1198 | `label:backend` |

Start a backend session with: `gh issue list --label backend --state open`

## Completed this session (2026-05-25 morning)

- ✅ OpenAPI freshness gate fixed — NodeDef-Input orphan schema removed from both contract files; gate now passes on every run (commits 90c238a8, 544a1230)
- ✅ Chains router promoted to core tier (#1151) — Swift FeatureManager v25, OpenAPI re-synced
- ✅ Workflow chains promoted in Swift FeatureManager (`isWorkflowChainsEnabled = true` by default)  
- ✅ #1186 Navigation history — back/forward chevron buttons + Cmd+' / Cmd+Shift+' in OntologyBrowser
- ✅ Filed new issues: #1202 (biography text), #1203 (geo/temporal map), #1204 (click-to-sync)
- ✅ GitHub issues labelled frontend/backend/both

## Completed overnight (2026-05-24 → 2026-05-25)

1. ✅ **Phase 1 — Dependabot liquidjs** — bumped to ≥ 10.25.7 via `overrides` in `site/package.json`.
2. ✅ **Phase 2 — SwiftLint** — zero warnings across all 334 Swift files (Codex, 6 commits).
3. ✅ **Phase 3 — #1201 OpenAPI freshness gate** — step 7 in `verify_python.sh`; gate implemented and issue closed.
4. ✅ **Phase 4 — KG entity library (#1183/#1191)** — `entity inspector` CLI command + `getEntityInspector()` Swift service method + `EntitySourceGroupsView` wired into `EntityDetailView`.

## Next Session — Start Here (frontend Claude)

Priority: KG inspector polish + entity biography view.

1. **#1202 Entity biography text view** — render SVO claims as prose paragraphs in the KG inspector Text tab. Entity inspector is `fichero/fichero/Views/KnowledgeGraph/OntologyBrowser/EntityDetailView.swift`. Claims loaded from `/api/entities/{id}/claims`. Needs: group by source doc/page, render as `"[subject] [verb] [object] (Ch.x:y)"` with block-quotes for `quotation_kind` claims.
2. **#1181 JSON artifact inspector** — `DocumentInspectorArtifactsTab.swift` already has `GenericJSONInspector` + `ArtifactContentView` appended (pre-compaction work, check if present). If missing, re-implement.
3. **#1204 Click-to-sync** — claim row click → Jump to source page. The Jump → button already works; wire to row `onTapGesture` in the List tab.

Next after those: run `bash scripts/verify_all.sh` then push.

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

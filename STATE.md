# STATE.md — Fichero

## Current Focus

**Branch:** `0.0.2` — HEAD `76c04822`. Long session today (2026-04-28): morning polish + afternoon typed entity storage rewrite. Foundation shipped; review-ready pending Daniel's hands-on test of the full Catalogue (composable) round trip.

**Goal:** Daniel reviews 0.0.2 → release pipeline (#658-#660 → #661/#662/#665).

## Open Issues (0.0.2 milestone — only release/content remains)

| # | Title | Status |
|---|---|---|
| #658 | Set up fichero-releases GitHub repo | Needs Daniel to create repo |
| #659 | Build, sign, notarize 0.0.2 DMG | Blocked on #658 + Apple notarytool creds |
| #660 | Dry-run install 0.0.2 on Daniel's machine | Blocked on #659 |
| #661 | Add Fichero download page to tubb.ca | Content writing |
| #662 | Update tubb.ca/fichero with release notes | Content writing |
| #665 | Dev blog post — 3 years AI coding | Content writing |

## Filed for 0.0.3 today

- **#729** — KG navigation UI (cross-doc views, entity detail pages, optional graph viz). 2-3 weeks. Most of 0.2.0 KG Entities milestone collapses if landed.
- **#730** — SVO-style claim text + structured triples in metadata. ~1 day. Natural follow-on to per-page extraction.
- **#731** — Apple Intelligence Catalogue (Foundation Models bridge + chunk/for_each/merge primitives). ~3 weeks. Completes the 2×2 transcribe/catalogue × Apple/cloud matrix.

## Earlier-filed 0.0.3 carry-overs

#713 sidebar drag NSOutlineView wrapper, #714 install-defaults undercount (verify-then-close), #715 Inspector RTF shortcuts, #716 Paleography Transcribe, #717 grid icon click highlight (verify-then-close), #719 thumbnail prefetch.

## Blocked

- #658–#660 release pipeline blocked on Daniel creating the `fichero-releases` repo + Apple notarytool credentials.

## Next Session — Start Here

1. **Daniel's review**: rebuild the app, restart backend, Reset Defaults, run Catalogue (composable) on a fresh folder with the now-shipped per-page extraction. Inspect the Knowledge Graph section — claims should now have `source_page_label` populated ("Page 1", "Page 2", …).
2. **If review is approved**: close out 0.0.2 housekeeping (~17 issues completed in code but still open on GitHub) and start #658 → #659 → #660 release pipeline.
3. **If review surfaces issues**: triage. Per-page extraction is the biggest single behavior change today; if results are surprising, the extractor at `fichero-api/src/fichero/workflows/tools/extractors.py:_run_extractor` is the place to look — it now splits the aggregated text on `\n\n---\n\n` and runs N parallel LLM calls.
4. **Apple Intelligence**: registered as a provider but `chat()` has no `apple` branch — `llm.py:599`. Selecting Apple as provider will error with "Unknown provider". This is #731's prerequisite. Tracked, not blocking.
5. **Settings → Defaults Text picker**: now pulls full LiteLLM catalog (not just user-curated). If Daniel decides he prefers user-curated only, revert in `AISettingsView.swift:230`.

## Key constraints carried forward (still hot)

- **KG dual-write pattern**: structured types (people/places/orgs/events/dates/keywords) write KnowledgeEntity + KnowledgeClaim rows AND a markdown Artifact. Free-form types (summary/catalogue narrative) write Artifact only. Both render in Inspector — markdown above, typed view below (#728).
- **Per-page extraction**: extractors split aggregated text on `\n\n---\n\n` (the aggregate node's separator). N pages = N parallel LLM calls. Each claim carries `source_page_label = "Page {i+1}"` and a 500-char `source_excerpt`. Single-chunk text falls through to legacy single-call behavior with no page label. (#728 follow-on, this evening.)
- **EntityType enum**: person, location, organization, event, concept, other. Hard-coded for 0.0.2; user-defined types are the natural extension via #706 phase 3 (0.0.3).
- **EntityType API quirk**: OpenAPI generates two types — `Components.Schemas.FicheroKnowledgeModelsEntityType` (input/query params) and `Components.Schemas.EntityTypeOutput` (response bodies). Same six cases. Use the Output version for KnowledgeEntity.entityType.
- **Swift file additions need pbxproj edits**: main target uses traditional file references, not synchronized groups. New .swift files don't auto-include — append to existing files in the same dir, or split properly later. EntityServiceGenerated lives appended in `ArtifactServiceGenerated.swift`; KnowledgeGraphInspectorSection lives appended in `DocumentInspectorArtifactsTab.swift`.
- **Workflow defaults vision_mode**: cloud Catalogue + Catalogue (composable) now use `vision_mode: "llm"` (uses workflow's provider, falling back to Settings → Defaults → Vision). Apple Vision OCR is via standalone "Transcribe (Apple Vision)" workflow.
- **`inspectorDocument` precedence** (carry from earlier): grid match (only if child of current sidebar folder) → viewMode.library doc → detailDocument. Don't reorder.
- **Inspector V2 strict per-document scope** (carry from earlier): every `getArtifacts` call must pass `includeDescendants: false` (#721).

## Architecture docs to read before resuming

- `docs/architecture/typed_entity_storage.md` — design + locked decisions, revised post-audit. §0 has the as-shipped plan.
- `docs/superpowers/plans/2026-04-28-typed-entity-storage.md` — implementation plan with per-task TDD steps.
- `docs/architecture/swiftui/inspector_redesign.md`, `swiftui/api_client.md`, `api/development_standards.md`, `release-process.md`.

---

*Last updated: 2026-04-28 evening — typed entity storage shipped (Phases 1-6 + per-page) + workflow polish + 3 issues filed for 0.0.3. Daniel reviews tomorrow.*

# STATE.md — Fichero

## Current Focus

**Branch:** `0.0.2` — HEAD `d02afce9`. Long session today (2026-04-28): morning polish + afternoon typed entity storage rewrite + late-night Apple Intelligence integration. Four catalogue workflows now ship; the 2×2 transcribe/catalogue × cloud/Apple matrix is complete.

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
- **#732** — Surface provider-side errors clearly in UI (quota / 429 / model-not-found / auth). 1-2 days. Real-world hit during Daniel's testing tonight.
- (#731 closed — Apple Intelligence shipped end-of-day, ~2hrs of work).

## Earlier-filed 0.0.3 carry-overs

#713 sidebar drag NSOutlineView wrapper, #714 install-defaults undercount (verify-then-close), #715 Inspector RTF shortcuts, #716 Paleography Transcribe, #717 grid icon click highlight (verify-then-close), #719 thumbnail prefetch.

## Blocked

- #658–#660 release pipeline blocked on Daniel creating the `fichero-releases` repo + Apple notarytool credentials.

## Next Session — Start Here

1. **Build fm-bridge first** — Apple Intelligence binary isn't checked in. Run `fichero-api/bin/fm-bridge/build.sh` (2 seconds with `swiftc`). Without it, Catalogue (Apple Intelligence) errors with "fm-bridge binary not found" at runtime.
2. **Restart backend + ⌘B in Xcode + Reset Defaults** in the app. You should now see four catalogue workflows: Catalogue, Catalogue (composable), Catalogue (Apple Intelligence), plus the two Transcribe variants.
3. **Daniel's review**: smoke test all four. Per-page extraction (`source_page_label = "Page N"`) lands on every claim regardless of provider. Apple Intelligence catalogue should run with **zero cloud calls** — quotas don't matter.
4. **If review is approved**: close ~17 issues completed-in-code but open on GitHub, then start #658 → #659 → #660 release pipeline.
5. **Gotchas**:
   - Apple Intelligence requires macOS 26+ on Apple Silicon with Apple Intelligence enabled in System Settings. fm-bridge fails fast with `kind: unavailable` if not.
   - The Settings → Defaults Text picker shows ONLY user-configured models (reverted from the LiteLLM catalog fallback per Daniel's "user has to think about it" call). If a picker is empty, add models in Settings → Models first.
   - Per-page extraction does N parallel LLM calls per extractor on N-page docs. Watch quota on cloud providers — #732 logs the error categorization gap.

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

*Last updated: 2026-04-28 late-night — typed entity storage + workflow polish + Apple Intelligence Catalogue all shipped on 0.0.2. Daniel reviews tomorrow.*

# STATE.md — Fichero

## Current Focus

**Branch:** `0.0.2` — HEAD at 612b0950 (+10 commits today, 2026-05-01). Big session: token-auth sweep across the Swift app (#742 follow-up across 22 raw URLSession callsites), first-launch onboarding wizard with catalog-driven provider list (logos via ProviderLogoView, Apple Intelligence availability probe via fm-bridge --probe + new GET /api/providers/apple-intelligence/probe route, local server "Test connection" button, AI defaults auto-applied for the chosen provider), import-mode picker (Link recommended), RTF page-content save flicker fix, pinch-to-zoom flash fix (#748), folder grid full-width on launch (#749), workflow Reset Defaults wired to actually reinstall (#722 part 1), workflow row 2-line description, OpenAPI sync stepped into release pipeline (step 0/4).

**Goal:** Daniel reviews 0.0.2 → release pipeline (#658-#660 → #661/#662/#665).

**Today's commits (oldest first, all on 0.0.2):**
- `b1425e08` fix(security): apply Bearer token to raw URLSession callsites (#742)
- `50d9f067` feat(apple): availability probe via fm-bridge --probe + GET /providers/apple-intelligence/probe
- `d2babd24` feat(onboarding): first-launch wizard for AI provider + import-mode setup
- `cb1a0ec2` fix(inspector,workflow): RTF page-content save flicker + 2 UI polish
- `e26baf1a` fix(library): folder grid full-width on launch (#749)
- `84d3df56` fix(image-viewer): pinch-to-zoom flash to original on release (#748)
- `f682bb7a` chore(release): sync OpenAPI schema engine -> Swift client before xcodebuild
- `7395d248` chore(lint): suppress wizard's unavoidable line/file-length warnings + rename .ok to .connected
- `612b0950` fix(workflow): wire 'Reset Defaults' to actually reinstall + drop dead Swift templates (#722 part 1)

## Open Issues (0.0.2 milestone — release/content + a few engineering)

**Release pipeline (Daniel-blocked):**
| # | Title | Status |
|---|---|---|
| #658 | Set up fichero-releases GitHub repo | Needs Daniel to create repo |
| #659 | Build, sign, notarize 0.0.2 DMG | Blocked on #658 + Apple notarytool creds |
| #660 | Dry-run install 0.0.2 on Daniel's machine | Blocked on #659 |
| #661 | Add Fichero download page to tubb.ca | Content writing |
| #662 | Update tubb.ca/fichero with release notes | Content writing |
| #665 | Dev blog post — 3 years AI coding | Content writing |

**Engineering — open, deferred or unverified:**
| # | Title | Status |
|---|---|---|
| #720 | Catalogue (composable) doesn't emit combined artifact — per-entity only | Backend / not attempted today |
| #721 | Inspector shows parent's container artifacts on selected child page | Inspector V2 work |
| #718 | Icon list square aspect when only 1 row visible | Layout-cycle issue, deferred |
| #711 | Sidebar drag unify icon/text + row body via .draggable | Larger refactor |
| #702 | Drag-drop folder onto PDF row | Validation matrix |
| #695 | Folder workflow run stores artifacts on folder, not per-file | Task list says fixed but no in-code reference; verify before close |
| #676 | Catalogue workflow per-file → reduce into container | 0.0.3-ish task |
| #667 | Add Selection source node | Task |
| #598 | Sidebar drag drops to selected row, not cursor target | Larger sidebar refactor |

## Filed for 0.0.3 today (2026-05-01)

- **#750** — Test fixtures: starlette TestClient requests rejected by AuthTokenMiddleware. ~700 unit tests fail since #742; needs a session-scoped fixture that injects the Bearer token into every TestClient request. Bug-fix on the test side, not the middleware.
- **#751** — Workflow context menu: group Run Workflow submenu by folder_path (#722 part 2). Touches SidebarItemRow + LibraryView+FilterAndBatch context menus.

Carrying from earlier:
- **#729** — KG navigation UI (cross-doc views, entity detail pages, optional graph viz). 2-3 weeks. Most of 0.2.0 KG Entities milestone collapses if landed.
- **#730** — SVO-style claim text + structured triples in metadata. ~1 day. Natural follow-on to per-page extraction.
- **#732** — Surface provider-side errors clearly in UI (quota / 429 / model-not-found / auth). 1-2 days. Real-world hit during Daniel's testing tonight.
- (#731 closed — Apple Intelligence shipped end-of-day, ~2hrs of work).

## Earlier-filed 0.0.3 carry-overs

#713 sidebar drag NSOutlineView wrapper, #714 install-defaults undercount (verify-then-close), #715 Inspector RTF shortcuts, #716 Paleography Transcribe, #717 grid icon click highlight (verify-then-close), #719 thumbnail prefetch.

## Blocked

- #658–#660 release pipeline blocked on Daniel creating the `fichero-releases` repo + Apple notarytool credentials.

## Next Session — Start Here

1. **Test the new wizard flow.** `defaults delete com.fichero.fichero hasCompletedOnboarding` and relaunch — should see the 4-screen flow. Verify Apple Intelligence probe shows "Ready" on this Mac, that picking a cloud provider with a key + saving creates a provider row in Settings → Models, and that AIDefaults gets populated for text + vision (the wizard's `applyDefaultsForChosenProvider` runs in `finish()`).
2. **Verify pinch-to-zoom no longer flashes** on image preview release.
3. **Verify folder grid is full-width** on launch when a folder selection is restored.
4. **Two unverified GH issues** still open in 0.0.2 — #695 (folder transcribe artifacts) and the #720 catalogue composable artifact emission. Either fixed already (close after verify) or punted to 0.0.3.
5. **Release pipeline** is gated on you handling #158 (App Store Connect API key setup) + verifying #159 (Sparkle EdDSA private key — was missing on this Mac in earlier audit).
6. **fm-bridge --probe** is a new CLI mode added today. The Debug build re-bundles fm-bridge automatically via the "Embed Fichero Engine" run-script phase. Release build needs the engine rebuilt via briefcase to pick up the new `--probe` flag.
7. **Gotchas (carried)**:
   - Apple Intelligence requires macOS 26+ on Apple Silicon with Apple Intelligence enabled in System Settings. fm-bridge --probe returns `{available: false, reason: "..."}` if not.
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

## Session 2026-05-03 (autonomous overnight)

Daniel went to bed mid-session asking for "this and other 0.0.2 issues." Goal for tomorrow: certificates + publish.

**Shipped tonight on 0.0.2 (newest first):**
- `9655fa74` fix(library): single-click navigates into containers when sidebar hidden (#786)
- `2b0306d1` fix(library): split scroll target into minimal vs centered (#769, #784)
- `a6606011` fix(library,nav): per-doc spinner via batch run path + sidebar click collapses preview (#785)
- `66c6ce23` fix(inspector): stop stomping AppKit toggleRuler so Format > Text > Show Ruler updates label (#781)
- `84f73f12` fix(library,menu): clamp pinch zoom to pane width + ruler menu uses Toggle (#781, #782)
- `7a4d990e` fix(inspector,library): wire ruler toggle (#781) + smooth+raise pinch zoom (#782)
- `b3f831a6` fix(library): pinch-to-zoom actually scales icons, not just column count

**Closed (16 issues — verified-fixed in code or duplicate):**
#761, #762, #765, #766, #767 (dup #785), #769, #770, #771, #772, #773, #774, #776, #777, #778, #779, #780, #781, #782, #784

**Remaining open on 0.0.2 (19 issues):**
- **Engineering — likely needs Daniel's eyes:**
  - #785 — per-doc spinner: batch path now wired, but sidebar folder aggregation NOT done. May still need #767-style diagnostic if path matching fails.
  - #786 — sidebar-hidden navigation: single-click navigation done; Cmd+\` back shortcut deferred.
  - #763 — Settings model picker filter: needs ~60 sec manual verification (probably already correct).
  - #764 — workflow startup delay: needs profiling, no clear fix path.
- **Architectural / design (defer to 0.0.3):**
  - #720, #676 — Catalogue map+reduce / combined artifact.
  - #721 — Inspector parent folder artifacts on child page (depends on #720 architecture).
  - #718 — icon list square aspect (couldn't locate component).
  - #711, #702, #598 — sidebar drag-drop family.
  - #667 — Selection source node feature.
- **Release pipeline (Daniel-blocked):**
  - #658 set up fichero-releases repo
  - #659 sign+notarize DMG (needs notarytool creds)
  - #660 dry-run install
  - #661, #662, #665 — content writing

## Next Session — Start Here (2026-05-04)

1. **Test tonight's fixes** in /Applications/Fichero.app (already installed):
   - Format > Text > Show Ruler now toggles + label updates (#781)
   - Pinch-zoom on big grid is smooth + caps at pane width (#782)
   - Sidebar click collapses preview, lands on grid view of folder (#785 nav)
   - Arrow keys do minimal scroll, double-click recenters (#769, #784)
   - Hide sidebar via toolbar → click folder in big grid → navigates in (#786)
   - Per-doc spinner now appears in grid when running workflow via context menu / picker (#785 partial)
2. **Certificates + publish** (Daniel's plan): #158/#159 → #659 → #660 → #661/#662/#665.
3. If tonight's #785 spinner still doesn't fire on some workflow path, check Console.app for the diagnostic warning ("updateProcessingStatus: no document matched path") added in b5e060d8 — if it fires, we have a path-mismatch bug to fix.

*Last updated: 2026-05-03 late-night — autonomous bug-fix sweep. 14 issues closed, 7 commits, 3 new bugs filed and fixed. Down to 19 open on 0.0.2 — most are architectural deferrals or release-cert blockers.*

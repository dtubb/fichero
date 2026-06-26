# Adaptive Apple UI Shell Plan — 2026-06-18

## Goal

Make Fichero feel like the same native app across Mac, iPad, iPhone, and visionOS without turning the iOS/iPad UI into a squeezed desktop window.

The current Mac shell is close and should be preserved. The iOS/iPad/vision issue is structural: the shared entry path lands in the desktop-oriented `ContentView`, which defaults to widescreen layout, persists all split columns, applies hard window minimums, and renders multiple manual panes inside the detail column.

## Current Findings

- `ContentView` uses `NavigationSplitView`, which is the right native container, but `columnVisibility` defaults/restores to `.all` and `showSidebar` is derived from that persisted state.
- `mainContentView` applies `paneAwareWindowMinWidth`, which adds sidebar + detail + inspector minimum widths. This protects Mac window chrome but defeats compact Apple layouts.
- Library/search layout defaults to `.widescreen` when advanced split layouts are off, forcing library + canvas + reading panes into narrow surfaces.
- iOS/iPad/vision enter through `FicheroApp_iOS` → `LibraryWorkspaceRoot` → `DocumentTabView` → `ContentView`, so they inherit the Mac shell.
- `PlatformHSplitView` / `PlatformVSplitView` are compile shims on iOS, not product UI. They preserve desktop layout shape instead of adapting interaction.
- `.inspector` is correct for macOS and regular-width iPad, but compact iPhone should present inspector information as a pushed destination or sheet.
- Several modes create fixed-width inner `HStack` sidebars inside the content column; those need adaptive split/stack behavior too.

## Apple-Native Approach

Use the platform features SwiftUI already provides:

- Keep the existing Mac `ContentView` shell as the desktop path.
- Add an adaptive shell host that chooses layout by platform and horizontal size class.
- Use `NavigationSplitView(columnVisibility:preferredCompactColumn:)` for regular-width iPad/vision and for Mac-compatible shell work.
- Use `NavigationStack` for compact-width iPhone, with one visible surface at a time.
- Keep `.inspector` for macOS/iPad regular; use compact navigation or sheet presentation for inspector content on iPhone.
- Make manual split panes desktop/regular-only. Compact mode should navigate between Browser, Canvas, Reading, and Info instead of squeezing them side by side.

## Proposed Work Packages

1. Define an adaptive shell routing layer.
   - Mac keeps the current persistent shell.
   - iPad/vision regular use split navigation.
   - iPhone/compact uses stack navigation.
   - Existing feature views are reused; this is not a rewrite.

2. Change split-view collapse policy.
   - Prefer `.automatic` as the default column visibility outside Mac-specific restoration.
   - Add `preferredCompactColumn` so compact devices show the useful surface after selection.
   - Stop deriving compact sidebar visibility from persisted desktop split state.

3. Separate Mac window minimums from adaptive content minimums.
   - Keep `paneAwareWindowMinWidth` for macOS.
   - Do not apply sidebar + inspector + widescreen pane minimums in compact/phone contexts.

4. Replace compact widescreen rendering with one-view-at-a-time navigation.
   - Browser opens document canvas.
   - Canvas can open reading/knowledge view.
   - Info/metadata opens as inspector destination or sheet.
   - Preserve the existing Mac widescreen panes.

5. Make inspector presentation adaptive.
   - macOS and iPad regular: native `.inspector`.
   - iPhone compact: pushed Info view or sheet.
   - View-menu/focused command behavior remains Mac-first.

6. Make `SplittablePane` desktop/regular-only.
   - Mac keeps horizontal/vertical pane splitting.
   - Compact iOS collapses to one primary pane and hides split controls.
   - iPad regular can keep split affordances only if touch ergonomics are acceptable.

7. Audit inner mode sidebars.
   - Research, Workflow, Activity, and similar modes should not embed fixed-width `HStack` sidebars on compact surfaces.
   - Convert to split columns on regular width and stack destinations on compact width.

8. Add adaptive verification.
   - Unit-test shell policy decisions: platform/size class → layout mode, column visibility, inspector presentation.
   - Add SwiftUI previews for Mac, iPad regular, iPhone compact, and vision regular where possible.
   - Add a regression check that compact shell never starts in widescreen multi-pane mode.

## Sidebar, Chat, and Drag-Drop Review Addendum

This follow-up review focused on the sidebar/chat setup, document-scope drag/drop, and sidebar folder/file drag/drop. The main conclusion is that Chat is its own important milestone: first-party chat behavior should not be hidden inside generic shell work. Compact platform work still matters, but the chat surface, document scope, and model-comparison entry points belong to the `Chat` milestone.

### Work Order

1. Fix chat routing before polishing UI.
   - `Chat with Docs` currently routes to main content chat and sidebar chat at the same time.
   - Pick one canonical destination, then remove duplicated state mutation.
   - Issue: #2336 — Fix Chat with Docs so it opens exactly one chat surface.

2. Make `Chat with Docs` a command, not sticky selection.
   - It is a repeatable action whose scope should update every time.
   - Do not rely on `List(selection:)` and `lastHandledSelectionId` for repeatable command semantics.
   - Issue: #2337 — Make Chat with Docs a command action instead of a sticky sidebar selection.

3. Standardize document drag/drop payloads for chat.
   - Library rows drag bare IDs; sidebar rows use `SidebarDragID`; chat accepts arbitrary text.
   - Add one decoder/payload path and normalize legacy `doc:<id>` and bare IDs.
   - Issues: #2338 and #2340.

4. Remove stale or unused chat surface hooks.
   - `SidebarChatSurface` is a stale alternate implementation unless it is intentionally rewired.
   - `onCreateChatWithDocuments` appears wired but unused.
   - Issues: #2339 and #2345.

5. Fix chat-related sidebar visibility gates.
   - `Model Comparison` is currently gated by the workflows flag.
   - Issue: #2341.

6. Harden sidebar drag/drop correctness.
   - Cross-folder moves should not reorder optimistically after failed backend moves.
   - Finder temp files should be cleaned up even when import fails.
   - Mixed internal/Finder drops should be classified deterministically.
   - Issues: #2344, #2343, and #2346.

7. Add touch-first compact alternatives.
   - iPhone/iPad should not require Mac-style drag/drop or simultaneous sidebar/chat visibility.
   - Add explicit `Add to Chat`, `Move to Folder...`, and compact scope-editing flows.
   - Issue: #2342.

### GitHub Issue Map

- #2336 — Fix Chat with Docs so it opens exactly one chat surface. Milestone: `Chat`.
- #2337 — Make Chat with Docs a command action instead of a sticky sidebar selection. Milestone: `Chat`.
- #2338 — Normalize document drag/drop payloads for chat document scope. Milestone: `Chat`.
- #2339 — Remove or intentionally rewire stale SidebarChatSurface. Milestone: `Chat`.
- #2340 — Harden chat drop decoding and remove duplicate drop handlers. Milestone: `Chat`.
- #2341 — Fix Model Comparison sidebar row feature flag. Milestone: `Chat`.
- #2345 — Remove or wire unused onCreateChatWithDocuments sidebar callback. Milestone: `Chat`.
- #2343 — Clean up Finder drop temp files on failed sidebar imports. Milestone: `Library & Reading Surface`.
- #2344 — Make sidebar cross-folder drag moves transactional and honest on failure. Milestone: `Library & Reading Surface`.
- #2346 — Make sidebar folder-drop classification robust for mixed providers. Milestone: `Library & Reading Surface`.
- #2342 — Add compact iPad/iPhone alternatives for sidebar and chat drag/drop. Milestone: `Multiplatform — iOS / iPadOS / Mac`.

### Milestone Updates Applied

- `Chat` now explicitly owns first-party chat surface placement, single-surface `Chat with Docs` routing, canonical document drag/drop payloads for chat scope, stale sidebar-chat cleanup, command-vs-navigation semantics, and model-comparison sidebar visibility.
- `Library & Reading Surface` now explicitly owns sidebar/library drag-drop correctness: transactional cross-folder moves, Finder import cleanup/failure states, mixed-provider drop classification, and standard Mac selection.
- `Multiplatform — iOS / iPadOS / Mac` now explicitly owns compact/touch alternatives for sidebar/chat drag/drop.

## Non-Goals

- Do not redesign the Mac shell from scratch.
- Do not replace `NavigationSplitView` with a custom breakpoint layout engine.
- Do not remove Mac split panes, inspector, or zoned toolbar polish.
- Do not build duplicate feature views for iOS; reuse existing views through a smaller adaptive host.

## Related GitHub Scope

- Epic: #1926 — Multiplatform universal app.
- Existing compact issue: #2100 — iPhone compact layout.
- Broader UI reform epic: #2253 — Mac/iPad/iOS UI reform.
- Persistent shell keystone: #2031.

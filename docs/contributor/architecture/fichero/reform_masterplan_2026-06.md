(AI generated. Not reviewed.)

# Fichero UI Reform — Master Plan (2026-06-15)

> Status: **DRAFT for Daniel** — synthesized from 7 parallel ground-truth research passes
> (cross-platform, PDF surfaces, modular/floating inspectors, zoned toolbar + endpoints,
> annotation system, alternative representations, table/window/testing) + Daniel's design
> brief + screenshot notes. This is the capture + ordering. Tracking EPIC: see #REFORM.
> Supersedes the mindPalace-as-lens parts of `mac_shell_design_proposal.md` (now stale).

## 0. Design brief (Daniel's principles — the invariants)

1. **Everything observable** — views observe `@Observable`/`@Published` domain stores; the store is the only endpoint/change-stream accessor (Observable Data Layer, #1863). No view hits HTTP directly.
2. **No hand-rolled URLs** — every call goes through the typed OpenAPI client / generated service wrappers. The endpoint-walker guardrail already enforces this (#1147); extend it.
3. **One codebase, three platforms** — macOS + iPadOS + iOS from one target; SwiftUI-first; AppKit (or the iOS equivalent) only behind a shim where SwiftUI genuinely can't reach.
4. **Proper sidebar | content | inspector** — one persistent shell; chrome never replaced; content swaps per lens (#2031).
5. **Standard SwiftUI elements** — prefer native controls; where we must go custom, prefer a **WebKit view** (like the existing web panes) over hand-rolled AppKit.
6. **Consistent code, no parallel paths** — one code path per concern; no per-lens private duplicates. (Where are Automations/Integrations? do we test that we can import + render everything we import?)
7. **Speed by design** — profiling, async image load, prefetch/cache "what's coming," all observable.
8. **Comparison UI must work** — compare workflows AND their outputs.
9. **SwiftUI SHOWS; logic is BACKEND** — the Swift app is a thin presentation layer. All
   business logic, persistence, AI, and computation live in the Python engine; views render
   observable state + call the typed action layer. Keep Swift logic-light (this is what makes the
   iPad/iOS client a cheap thin remote view). Guardrail: flag non-trivial business logic in Swift.

## 1. Current-state inventory (ground truth — what we have)

- **Backend endpoints: ALL ENABLED.** `_DEV_ROUTE_SPECS == []` (`api/main.py:1309`); every router (KG, hermeneutics, interpretations, research, iiif, actions, chains, integrations, model-comparison, orchestration, schedules, triggers, notes, mind-palace) was promoted to CORE on 2026-05-28. **Nothing to "enable."** CLAUDE.md's "dev tier off by default" is **stale → fix the doc.** Remaining backend work is **removal** (mind-palace, #1455) + **a few new endpoints** (below).
- **App is macOS-only today.** `project.pbxproj`: `SDKROOT=macosx`, no iOS target. ~35 files `import AppKit`; only 1 uses `#if os` (`MindPalaceTheme.swift` — the shim template). The persistent `NavigationSplitView` shell already exists and persists; the inspector is a window-level `HStack` sibling (#1199), not `.inspector()`.
- **Conversions already exist server-side:** `convert.py` → markdown/html/svg; `table_extract.py` → table/csv; geo models (`GeoPoint`/`EvidentialPlace`) exist. Missing: **default presets** to trigger them + a **geo-extraction tool**.
- **Annotation backend is ~70% there:** `Annotation` model with text-span (`char_start/end`) AND region (`bbox [x,y,w,h]` 0..1), full CRUD + undoable action layer, `GET /annotations/{id}/crop` (the "send the LLM just this region" primitive), `annotations_source` workflow node, bbox-anchored claims (#1123), Apple Vision OCR with per-word/line boxes. Missing: the **UI** (text highlight, paragraph-checkmark, PencilKit), reverse **LLM→overlay** driver, ephemeral crop endpoint.

## 2. The reform, by area (vision → current → gap → approach → cross-platform)

### A. Persistent shell + shared inspector — #2031 (keystone)
- Shell already persists. Fix: `inspectorView` (`ContentView+ViewBuilders.swift:486`) switches on `viewMode` only — **blind to `sidebarMode`**. Fold the 4 lenses' private panes into the one shared inspector, routed by `sidebarMode` first: **research** (ResearchTasksPane), **knowledgeGraph** (OntologyBrowser.detailPaneForMode → new `OntologyDetailView`), **activity** (ActivityDetailView), **automation** (metadata). **mindPalace is DROPPED** (it's retired, §B). Add `@SceneStorage("inspector.selectedTab")`.
- **Recommended: replace the window-level inspector `HStack` (#1199) with native `.inspector()`** — gives full-height inspector (#2033) for free AND lets the zoned toolbar reach over the inspector column. Keystone enabler.

### B. Mind Palace retirement → library 2D/3D view modes — #1455 / #1569 (do BEFORE #2031)
- **Spatial = view modes, not a destination** (`thinking-layer.md:119`). The 2D/3D engine EXISTS (`SpatialScene3D`, `Spatial2DCanvas`, `MindPalaceLibraryProjector`) but is wired only inside `MindPalaceContainer`; the library `.realitykit`/`.spatial`/`.map` modes point at **dead/stub/duplicate** code (`FolderRealityKitSurface`, `CollectionSpatialStub`, a non-projector `mapView`).
- **Migrate into library modes:** rebase `.realitykit` onto `MindPalaceLibraryProjector → SpatialScene3D` (keyed off folder/selection, not a room); rebase `.map` (2D) onto `Spatial2DCanvas` (one projector pipeline for 2D+3D); move Arrange▾ + node→navigate into the library spatial toolbar.
- **Delete:** `MindPalaceWindow/Container`, `RoomListView`, `SpatialNodeInspector`, `MindPalaceState` rooms, `MindPalaceService`, `FolderRealityKitSurface`, the two stubs, `SidebarMode.mindPalace` (compiler-guided across ~14 files), backend `mind-palace`/`mindpalace_render` routers. **Keep** the projector + scene + theme.
- **Sequence FIRST** so #2031 doesn't fold-then-delete a mindPalace inspector.

### C. Zoned 3-region toolbar + sidebars-as-tabs + chat-over-sidebar — #2032 #1927 #1968 #2034
- Today: 1 real window toolbar + ~15 `MiniToolbar` bars. Fold the mini-toolbars up into ONE zoned toolbar: **leading/sidebar** (sidebar toggle + chat toggle, constant), **content** (lens-aware: import/run/view-picker), **trailing/inspector** (inspector toggle + inspector controls). Delete dead `MainToolbar.swift`.
- SwiftUI can't pixel-align separators to dividers (no `NSTrackingSeparatorToolbarItem` in SwiftUI). **Strategy A (ship first):** `ToolbarSpacer(.flexible)` groups (macOS 26) + native `.inspector()`. Strategy B (AppKit precise) later if needed.
- **Tabs BETWEEN sidebars** (#1968, Daniel: "sidebar and inspector sandwich tabs/content"): custom tab strip at top of the content column (sidebar | tabs+content | inspector); the strip currently lives atop the inspector → move it to the content column. **Decision: facet-tabs (one doc's Content/KG/…) vs document-tabs (multiple open docs, Xcode-style)** — see decisions.
- **Chat-over-sidebar conflict:** #2034 (chat toggle over the LEFT sidebar, Xcode-style — matches Daniel) vs #1846 (chat RIGHT rail). Build the **left** one; shelve #1846.

### D. Document inspector: attributes-above-content + prototypes (Tinderbox) — #1762 #2081
- `DisplayAttributesStrip` already exists (read-only, inside the Content tab). Hoist it **above** tab content; make rows **editable**; drive the visible set from the prototype.
- **Prototypes need backend (#2081):** today `prototype_key` is a string tag only. Build: `AttributeDefinition`, `Prototype` (with `parentKey` inheritance + `displayedAttributeKeys`), per-doc `attributes` override map, `GET /documents/{id}/attributes/resolved` (merged + provenance), `PATCH /documents/{id}/attributes`, prototype CRUD.

### E. Modular / FLOATING inspectors + results — (after #2031)
- Precedent exists: 5 detachable `WindowGroup` detail scenes observing a shared `@Observable` focus holder (`FocusedArtifact`). Generalize to the whole inspector + result lists.
- **One reusable env-light content view + a platform-adaptive presenter:** `.docked` (column) | `.floating` (macOS `UtilityWindow` floating-above + FocusedValues; iPad secondary scene if `UIApplicationSupportsMultipleScenes`) | `.sheet` (iPhone, `presentationDetents`). Gate every `openWindow` on `@Environment(\.supportsMultipleWindows)`.
- **Stacked panes** (Daniel: "two tabs of the webkit view / document inspector, one above the other"): allow a pane to split vertically into two representation tabs.

### F. PDF / page surfaces
- **2D map of a PDF = page GRID, not one image** (Daniel). New `PDFPageMapView` — `LazyVGrid` of `PDFThumbnailView` cells (client-side render, page count free). Mount via a Page/Grid toggle in `PDFPageWithToolbar`. Selection → existing page-focus sync.
- **PDF editor can't edit the image — reachability bug:** `EditorView.previewRoute` returns `.storageDisplay` for a PDF *before* the `isEditing` check (`:115`), so the edit toggle is dead on a PDF parent. The per-page raster chain already works (`ImageEditorView`); route PDF-in-edit-mode to it. Plus a **PencilKit overlay** for freehand markup (vector annotation, non-destructive).
- **Map image/text toggle** (Daniel): per-tile/global toggle image vs `pageContent` text in the grid.

### G. Annotation mode — (backend ~70% built)
- Highlight (text span), region capture (bbox marquee — exists for images), notes-on-page, **paragraph-checkmark** (the robust cross-platform highlight — sidesteps iOS sub-range-selection limit), **PencilKit handwriting → OCR** (iPad Pencil → Apple Vision local or Qwen remote → text + provenance), **LLM targeting both ways** (user→region/span via crop; LLM→highlight via a generic `FocusedRegion` driver reusing the existing claim-source highlighter + marquee renderer).
- New fields (additive): `anchor_kind`, `paragraph_index`, `metadata.ink_data/ocr_provider`. New endpoints: ephemeral `POST /annotations/crop`, `POST /annotations/{id}/transcribe-ink`.

### H. Alternative representation views
- A document/page has N switchable representations: **image, markdown, HTML, SVG(LLM)→WebKit, spreadsheet(`Table`), 2D world-map(`Map`+pins), 3D globe(SceneKit/RealityKit)**. Conversions exist (`convert.py`, `table_extract.py`); build **presets** + a **geo-extraction tool** + geocoding. UI: a `RepresentationStore` (derived from artifacts) + a representation picker + new `DocumentCanvas.Content` kinds. **World-map (lat/long pins) ≠ spatial node-map (#1455 layout)** — different things.

### I. Hierarchical table/outline — (Daniel: table shows per-page child items)
- Library Table view → expandable outline of children (artifacts/entities/notes/claims). `Table` + `DisclosureTableRow` (macOS 14/iPadOS 17; collapses to list on iPhone). Children aren't Documents — build a `LibraryOutlineNode` tree assembled from the per-library stores; add `GET /documents/{id}/rollup` (cheap counts) for collapsed rows. Also: **horizontal + vertical library layout options** (Daniel).

### J. Window behaviors
- **Duplicate-this-window** (clone library + selection + lens via `openWindow(value: WindowSeed)`; gate on `supportsMultipleWindows`).
- **Bug:** library view sometimes renders BELOW the sidebar (screenshot) — layout bug to fix.

### K. Chrome: breadcrumb + status — (Daniel likes Xcode's)
- **Breadcrumb trail** (where we are / what's selected) in the content header (#2036/#1928).
- **Top-right status** (current activity) + **errors** surfaced (Xcode-style). Ties to the observable activity/change-stream.
- **Activities section rethink** so it can highlight areas (screenshot).

### L. Speed / performance (#1815 #1918 shipped a start)
- Profiling harness + seeded perf benchmarks (shipped #1815); strategic prefetch/prewarm (shipped #1918). Extend: **async image load** everywhere (AsyncImage / cached), prefetch "what's coming," everything observable so the UI never blocks. Instruments passes.

### M. Comparison UI — #8 (Daniel: must compare workflows AND output)
- Verify Model Comparison view works; extend to compare **workflow runs + their outputs** side by side. (Audit needed — see workers.)

### N. Consistency / completeness — #6
- Audit: where are **Automations + Integrations** surfaced? One code path per concern (no per-lens duplicates). **Import-everything / render-everything tests** — a guardrail that every importable type imports and every importable type renders in some representation.

## 3. Sequence (avoid rework)

1. **Cross-platform groundwork WITH the shell** (cheap now, expensive later): `#if os(macOS)`-gate `EmbeddedBackendService` + boot branch (#2098); build shell on `NavigationSplitView(columnVisibility:preferredCompactColumn:)`; replace `VSplitView`/`HSplitView` (12 files) with `HStack`/`VStack`+`ResizableDivider`; stand up the `Platform*` shim skeleton (#2097, mirror `MindPalaceTheme`); route toolbar via semantic placements only.
2. **#1455/#1569** — mind palace → library 2D/3D modes + retire (compiler-guided).
3. **#2031** — persistent shell / shared-inspector router (now 4 lenses) + native `.inspector()`.
4. **#2032 / #1927 / #1968 / #2034** — zoned toolbar + tabs-between-sidebars + chat toggle.
5. **#1762 + #2081** — attributes-above-content + prototypes (backend #2081 in parallel, long pole).
6. **E** — modular/floating inspectors + stacked panes.
7. **F/G/H** — PDF surfaces, annotation mode, representation views (each leans on backend presets/endpoints; can parallelize backend).
8. **I/J/K** — hierarchical table, duplicate-window, breadcrumb/status, activities rethink.
9. **Continuous:** L (perf), N (consistency/tests), M (comparison), the completeness matrices.
10. **iOS/iPad target** (#2096/#2099/#2100/#2101) — after the shell is size-class-clean; then "add a destination + onboarding," not "re-open every view."

## 4. Cross-platform foundation (one codebase)

Single multiplatform target + size-class adaptivity + `#if os(macOS)` for irreducibly-Mac bits (NOT Catalyst, NOT a separate target). Shims (#2097): `PlatformImage`, `PlatformViewRepresentable`, `PlatformPasteboard`, file pickers → `.fileImporter`, window-opening behind `supportsMultipleWindows`. iOS engine is **remote-only** (`EngineConfig` custom host; `engineIsLocal` already hides local-path affordances). Revise `SWIFTUI_PRINCIPLES.md:404` "macOS 26 only" → "macOS 26 + iOS floor."

## 5. Testing (catch bugs across Mac/iPad/iPhone + multi-window)

Pyramid: (1) **unit-test the platform branch DECISIONS** (size class → Table vs OutlineGroup; `!supportsMultipleWindows` → duplicate disabled; `LensSnapshot` Codable round-trip) — cheap, CI-able, highest ROI; (2) **`#Preview` at compact+regular** rendered via scheduled `RenderPreview`; (3) **XCUITest** smoke (extend #1230, seeded fixture, off-session due to GUI-focus rule). iPad/iPhone test destinations need the iOS target first. Plus the existing contract/integration gates. **Import-everything/render-everything** guardrail (#6/#N).

## 6. Backend work (build-new — small/additive)

- **Remove** mind-palace routers (#1455).
- **Presets:** `convert_to_markdown/html/svg.json`, `extract_table.json`, `extract_geo.json`.
- **Geo-extraction tool** + geocoding (place name → lat/long); list-doc-geo endpoint.
- **Prototypes/attributes** (#2081): definitions + inheritance + `…/attributes/resolved` + `PATCH …/attributes`.
- **Annotation:** ephemeral `POST /annotations/crop`; `POST /annotations/{id}/transcribe-ink`; `anchor_kind`/`paragraph_index`/`metadata.ink_*` fields; paragraph offsets on `page_content`.
- **Rollup:** `GET /documents/{id}/rollup` (counts for the outline).
- **Fix doc:** CLAUDE.md "dev tier off by default" is stale.

## 6b. PROGRAMMATIC GUARDRAILS — machine-enforce the design brief (Daniel's #1 theme)

Turn every principle in §0 into a CI guardrail (model on shipped `scripts/check_*.py`
+ the endpoint walker #1147 + comment-hygiene/tooltip guardrails). Each is a script +
a test that fails the suite (with a content-hash `KNOWN_VIOLATIONS` allowlist so the
backlog is explicit, not a wall). Buildable NOW unless marked [design].

1. **No hand-rolled URLs / endpoints** — scan Swift for raw `URLSession`/`URL(string:)`/
   string-built API paths; require the generated client / `*Generated` wrappers. Extend #1147.
2. **OpenAPI models only** — flag manual structs shadowing `Components.Schemas.*`; never guess shapes.
3. **Observables everywhere** — views must not access endpoints/change-streams directly; only
   the `@Observable` store does (Observable Data Layer #1863). Guardrail on view→service calls.
4. **No AppKit/UIKit except sanctioned** — scan `import AppKit`/`import UIKit` against an
   allowlist (PDFKit, magnifier, QL, rich-text, web). New `import` → fail unless allowlisted.
5. **No custom UI** [design] — heuristic flag for hand-rolled controls where a standard SwiftUI
   element exists; if genuinely custom, prefer a **WebKit view**. Needs a definition of "custom."
6. **Completeness matrix** [design] (#1925) — every "thing" (entity/claim/note/annotation/doc/
   workflow/...) must have CRUD + context menu + menu-bar item + keyboard shortcut. Build a
   registry of things + presence checks across action-registry + menus + context menus + shortcuts.
7. **Endpoints enabled** — assert the release tier registers everything the UI calls (extends #1147).
8. **Swift logic AND UI tested** — coverage guardrail: every store/decision has a unit test;
   every view has a `#Preview`; key flows have an XCUITest. Report gaps (non-blocking debt).
9. **Import-everything / render-everything** (#6/#N) — test that every importable type imports and
   every imported type renders in ≥1 representation.

## 6c. Additional feature items (captured 2026-06-15 PM)

- **Folder = workspace/room**: any folder can become a workspace / spatial room (drop the
  separate Mind-Palace room model into the folder; folders host the 2D/3D map). Ties to §B retirement.
- **Folder-tied notes/annotations on the 2D/3D map** — add regular notes/annotations anchored to
  the folder (not just a doc), visible on the spatial view.
- **Aliases** — a node can be an alias to another (Tinderbox/Finder alias); the node model (#2081).
- **Sidebar shows children** — expandable sidebar (folders → docs → PDF pages) like the outline (§I).
- **Sidebar is inspectable** — selecting a sidebar item drives the shared inspector.
- **Table/List row stripes** — alternating-row styling like DEVONthink/Scrivener (standard `.alternatingRowBackgrounds` on Mac; custom on iOS).
- **Export preview in WebKit** — preview the export (Tinderbox-style) rendered in the web view (§5 custom→WebKit).
- **Providers/Models in Settings** — models/providers belong in the **Settings window** (or surface defaults + the **model location** there). Defaults configurable from Settings.
- **Guardrail: models download to the SHARED models folder** — a test asserting every model download lands in the shared models folder (not per-library/scattered). Add to §6b guardrail suite.

## 6d. Capture round 2 (2026-06-15 PM/late) — more requirements

**Platform/OS target:** design for **Tahoe + macOS Golden Gate** (latest macOS/iPadOS/iOS,
~2026–27). Ship **September 2026**. Adopt the newest SwiftUI freely; no back-deployment.
(Updates the old "macOS 26 only" note — now macOS-latest + iPad/iOS-latest, one codebase.)

**Selection / DnD (standard Mac controls EVERYWHERE):**
- Multiple selection + **non-contiguous** selection everywhere (List/Table/grid/sidebar).
- Multi-select **delete / copy / cut / paste** where logical; standard menu + shortcuts.
- **Drag & drop everywhere**, including **between libraries** (cross-window/library DnD).

**Window / state:**
- **Multiple windows + tabs**, **remembered across app quit/relaunch** (state restoration —
  preserve current behavior). Ties to duplicate-window (#2262) + `@SceneStorage`/`Restoration`.

**Chat / Agent surface (ABOVE the sidebar):**
- A **chat interface above the sidebar folders/files** — chat, chat-with-search-results,
  chat-with-an-agent; an **agent can move things around in the UI** (agent-driven actions via
  the action registry #1848). Resolves the chat-placement conflict toward the left/top.
- **Researcher** (tied to a folder or the chat) can **open a web browser** — needs a research
  surface with **tabs / its own window / WebKit tabs** as it drives **MCP web tools**. A
  **manager agent with N worker agents**, each running its **own web browser**, with its
  **to-do + milestones list** — make all of it **visible** (observable agent activity).

**Splittable / re-organizable panes:**
- **Split the WebKit view** (horizontal top/bottom AND vertical); **same for library + image**.
  User can organize these around (library, image, webkit — NOT the workflow inspector).
- **Workflow activity columns belong in the ACTIVITY view**, not the workflow node editor.
- **Workflow inspector step → click → jump to the comparison of that step** (#8 comparison link).

**Observability (hard, everywhere):**
- **Everything observable** — including **positions in the 2D spatial / 3D RealityKit views**,
  and the **workflow inspector** state. No non-observed state.
- **Backend activity must surface to the frontend:** if the backend (e.g. via CLI) opens a
  library or does work, **the frontend must know** (observable backend/library-activity stream).
- **Consistent toolbar items at the top that don't jump around** (stable placement #2032).

**Quality gates (programmatic — add to §6b guardrail suite + testing):**
- **Accessibility + screen-reader (VoiceOver)**, **AppleScript support**, **Localization** —
  designed in AND **programmatically tested** (every control labeled; AppleScript dictionary
  coverage; no hard-coded user-facing strings). One guardrail/test each.

## 6e. Agentic chat as a FIRST-CLASS control surface (2026-06-15)

The chat/agent is a **primary way to drive the whole app**, not a side panel. Three entry
points, ONE backing surface = the audited **action registry (#1848)**:
1. **MCP from outside** — external agents call app capabilities via MCP (the action registry exposed as MCP tools).
2. **Siri / App Intents** — every registry action also an App Intent (system-wide, voice, Shortcuts).
3. **In-app sidebar chat** — the chat-above-the-sidebar (§6d) drives the same actions.
Daniel builds **most workflows via chat** → chat must reach workflow creation/editing + every
CRUD action. This is the in-app **Agent** (#2067): manager-with-workers, web browsers, to-do +
milestones, all observable (§6d). Everything the chat/agent can do must go through the one
audited action layer (no bespoke chat-only paths) — and the completeness matrix (§6b.6) should
assert every action is reachable from UI + chat + App Intents + MCP.

## 7. Open decisions for Daniel (the genuine forks — answer when back)

1. **iOS target now or after the Mac shell?** (Affects whether to stand up the target + shims now vs design-for-degradation.) Min iOS floor (18 or 26 — 26 unlocks `RecognizeDocumentsRequest` paragraph/table structure)?
2. **Tabs between sidebars: facet-tabs (one doc's facets) or document-tabs (multiple open docs, Xcode-style)?** And does the right inspector keep its own tabs or become a pure properties panel?
3. **Floating inspector: one palette (`UtilityWindow`, follows focus, Tinderbox) or many pinned per-doc?** Read-only or editable when floating?
4. **Prototypes scope:** documents only, or full #2081 (folder/workspace/entity all prototypes)?
5. **Highlight granularity on mobile:** paragraph-checkmark primary + char-spans Mac-only, or invest in a `UITextView` wrapper for precise spans everywhere?
6. **Handwriting:** default to Qwen (cloud) for handwriting, Apple Vision for printed? Store re-editable ink + transcription, or transcribe-and-discard?
7. **Representations:** per-page or whole-doc? auto-generate on switch or explicit "Generate"? geo pins = one-per-doc or every extracted place (needs geocoder)?
8. **3D globe engine:** SceneKit textured sphere (lighter) or RealityKit (consistent with spatial)?
9. **Comparison UI:** confirm scope = compare workflow runs + outputs side by side.
10. **Chat placement:** confirm left-sidebar chat toggle (#2034), shelve #1846 right-rail.

## 8. RESOLVED decisions (Daniel, 2026-06-15) — these supersede §7's open forks

1. **iOS/iPad target: build on BOTH platforms NOW** (Mac + iPad/iOS together) so we learn the
   real cross-platform shape and surface design failures early — not Mac-first-then-port. Stand
   up the iOS target alongside the shell work. (Floor = latest / Tahoe + Golden Gate.)
2. **Tabs = DOCUMENT-tabs across the top of the CENTER column** (multiple open docs, Xcode/Safari
   style). The content area under the tabs can show **library / image / document(content)**; the
   **WebKit pane + document inspector relate to the active tab**. (i.e. the "both" model with this
   layout: `sidebar | [doc-tabs → content(library|image|document)] | inspector(+webkit)`.)
3. **Floating inspector: BOTH** — one follow-focus palette (Tinderbox) AND pin-per-document.
4. **Prototypes: FULL container-prototype model now** — folders, workspaces, entities are all
   prototypes with inherited attributes (the full #2081), not documents-only.
5. **Comparison UI: BOTH** — (a) diff two workflows, AND (b) run the **same node across N providers**
   (the model bake-off); clicking a workflow-inspector step jumps to that step's comparison.
6. **Representations: PER-PAGE**, produced by a **default workflow** with an explicit **Generate
   button** — a user can batch-generate across all, or generate on click; cached once made.
7. **Geo: primarily one pin per doc (choosable multiple)**, PLUS a **heat map** and a
   **georeferenced overlay** (drop extracted points onto a real/historical map image — ties to the
   "highlight part of a map and tie locations" idea). Geocode named places.
8. **Highlight is PER-REPRESENTATION** — you highlight on whatever you're viewing: the **PDF/image**
   (region/bbox) AND the **text / HTML** views (span). Not paragraph-checkmark-only; the annotation
   model already supports both anchors.
9. **Handwriting OCR: user-choosable (workflows exist); smart default** — on-device for printed,
   online (Qwen) for handwriting.
10. **Chat: LEFT / over-the-sidebar** (Xcode-navigator style); **shelve #1846** right-rail.

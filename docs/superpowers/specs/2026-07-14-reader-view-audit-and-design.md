# Reader View: Audit and Re-Design (2026-07-14)

Tracking issue: #3765. Written for Daniel by the researcher agent, 2026-07-13/14.
Status: **COMPLETE** — audit + proposed design, research only, no source touched.

**Executive summary.** The Reader's drift is real and worse than a wrong
default: (1) the multi-page WebKit transcript — the surface's whole point — is
**unreachable anywhere in the app** (§6); what's labelled "Transcript" today is
a different, single-page native pane. (2) The Page tab's Source view duplicates
the Preview surface sitting in the same window, down to the same
`PDFPageWithToolbar` component (§5). (3) The approved 2026-07-11 IA doc
**contradicts itself** on the Preview/Reader boundary, and the implementation
followed the wrong half overnight on 07-11→12 (§3, §4). The "reader reads the
source first (Daniel 2026-07-12)" code comment is unverifiable and should not
be treated as authority (§4). Proposed fix (§8): rename Page → **Read**, make
it host the existing WebKit transcript + digest, delete the source/split/
transcript third mode level, and route source-viewing back to Preview. Two mode
levels, no duplication, `@SceneStorage` migrates itself (§10). Seven decisions
for Daniel in §11.

## 0. The brief (Daniel, 2026-07-14)

> "the reader view — you added the image preview, which makes no sense, and you
> removed the transcript view, which is the whole point of the view. We don't
> need to embed the preview in the reader view. The whole point of the reader
> view is it's WebKit, and lets us show a transcript of 10,000 files if we want to."

> "there is a confusion on the reader view plan. so we need to come back to
> that, and really think about it."

Design constraint (hard rule): **Preview, Reader, Inspector are three distinct
surfaces and must never be merged.** Preview = source viewer (images/PDF/DOCX/md,
zoom/loupe/fullscreen/split). Reader = derived knowledge made readable, WebKit.
Inspector = editing.

## 1. What the Reader IS (proposed statement of purpose)

> **The Reader is where Fichero's derived text is made readable at archive
> scale.** It renders in WebKit — that is the point, not an implementation
> detail — because HTML is the only surface that can lay out the assembled
> transcript of an entire document, folder, or 10,000-page corpus as one
> continuous, styled, searchable, scroll-synced text. Its content is what the
> engine *produced* (transcript, digest) and what the engine *extracted*
> (entities, claims, graph), never the source pixels: the source lives in
> Preview, and edits live in the Inspector. If a thing can be shown by opening
> the file, it belongs in Preview; if it can be edited, it belongs in the
> Inspector; if it had to be derived and needs to be *read*, it belongs here.

Derivation: Daniel 2026-07-14 ("the whole point of the reader view is it's
WebKit, and lets us show a transcript of 10,000 files"); the approved IA doc's
own job statement ("Reader = READ + EXPLORE one document visually",
`2026-07-11-reader-ia-design.md:37-44`); the engine's transcript assembly
(`views.py:37-49`); and the three-surfaces rule
(Preview=source / Reader=derived / Inspector=edit).

## 2. Audit: current state of ReadingPaneView

All citations are against `main` at 51f940b1d (2026-07-13) in `~/code/fichero`.
Primary file: `fichero/fichero/Views/Reader/Page/ReadingPaneView.swift`.

### 2.1 The mode tree as shipped

The Reader today carries **three nested levels of modes**:

**Level 1 — top tabs** (`ReadingPaneView.swift:103`, `SurfaceTabBar`):
`Page / Knowledge / Notes`, defined in `ReaderTabBar.swift:19-52` (`enum ReaderTab`).
Persisted per-window: `@SceneStorage("reader.topTab")`, **default `.page`**
(`ReadingPaneView.swift:63`).

**Level 2a — Page-tab layout** (`ReadingPaneView.swift:398-410`, picker):
`Source / Split / Transcript`, defined in `ReaderTabBar.swift:57-87`
(`enum ReaderPageLayout`, from #3502). Persisted per-window:
`@SceneStorage("reader.page.layout")`, **default `.source`**
(`ReadingPaneView.swift:69`) — i.e. the Reader opens showing the page image.

**Level 2b — Knowledge-tab sub-modes** (`ReadingPaneView.swift:326-355`):
segmented picker over `[.entities, .claims, .graph, .timeline, .map]`
(`ReadingPaneView.swift:368`) plus a set-apart **Digest** button
(`ReadingPaneView.swift:344-354`). Backed by `enum KGSurfaceTab`
(`DocumentKGSurface.swift:49-124`), which still declares SEVEN cases
including `.transcript`. Not persisted — plain `@State`, default `.graph`
(`ReadingPaneView.swift:58`).

**Level 2c — Notes-tab sub-modes** (`ReadingPaneView.swift:484-496`):
`Marks / Notes` (`enum ReaderNotesMode`, `ReaderTabBar.swift:92-118`, #3513).
Persisted: `@SceneStorage("reader.notes.mode")` (`ReadingPaneView.swift:45`).

So a user faces: top tab → sub-mode picker → (for Knowledge, also a separate
Digest button that deselects the picker). Additionally, the **View menu**
("Add View", ⌃⌥⌘1-7, #2032) drives `KGSurfaceTab` through the
`documentRepresentation` focused value (`DocumentKGSurface.swift:216-222`,
`ReadingPaneView.swift:139-145` comment) — a FOURTH way to switch modes,
living outside the pane entirely.

### 2.2 What the "source" default actually shows

With defaults untouched, the Reader opens on **Page → Source**, which renders:
- a PDF page via `PDFPageWithToolbar` (`ReadingPaneView.swift:458-462`), or
- an **image via `DocumentCanvas`** (`ReadingPaneView.swift:464-469`) with a
  3D page-turn animation (#2485), or
- `PageContentPane` as fallback for text-only documents (`:470-471`).

That is a **source viewer** — exactly Preview's job under the three-surfaces
rule. The Reader's first paint is an image, not derived knowledge.

### 2.3 The "Transcript" inside the Page tab is NOT the WebKit transcript

`ReaderPageLayout.transcript` renders `PageContentPane`
(`ReadingPaneView.swift:417-418`). `PageContentPane` is **native SwiftUI**
(`PageContentPane.swift:42-163`: `TextEditor` / `AnnotatableTextView`, AppKit
text, no WKWebView anywhere in the file) and is **single-page only**:

- `PageContentPane.swift:29-32` — `pageDoc` returns nil unless
  `doc.docType == .page`; anything else shows the empty state
  *"Select a page / Choose a PDF page to view or edit its content"*
  (`PageContentPane.swift:66-71`).
- It renders one page's `pageContent` string (`PageContentPane.swift:38-40`).

So the thing now labelled "Transcript" in the Reader is a **one-page-at-a-time
native text pane**. It cannot show a document's full transcript, let alone a
folder's, let alone 10,000 files.

### 2.4 Where the real (WebKit) transcript went

`KGSurfaceTab.transcript` is the WebKit transcript
(`DocumentKGSurface.swift:118-123`: only `.transcript` and `.digest` have
`usesWebKit == true`; they render in `DocumentKGWebPane` →
`document_view.html`, `DocumentKGSurface.swift:47-48`).

In the Reader it is now unreachable:
- The Knowledge sub-mode list **excludes** `.transcript`
  (`ReadingPaneView.swift:365-368`: *"Transcript is excluded — it lives in the
  Page tab"* — but as §2.3 shows, what lives in the Page tab is a different,
  weaker component).
- Any stale or menu-driven `.transcript` selection is **clamped to
  `.entities`** (`ReadingPaneView.swift:373-387`,
  `effectiveKnowledgeTab`), so even the View menu's ⌃⌥⌘1 "Transcript"
  representation shortcut (`DocumentKGSurface.swift:102-111`) cannot bring it
  back in this pane. [Verified further in §6.]

## 3. The three nested mode levels — accreted or intentional?

**Verdict: half-intentional, half-accreted — and the intentional half was
approved against a doc that contradicts itself.**

What the approved 2026-07-11 design (`docs/superpowers/specs/2026-07-11-reader-ia-design.md`,
"REVIEWED + APPROVED, Daniel 2026-07-11") actually specified:

- 3 top tabs Page / Knowledge / Notes — **intentional** (doc lines 46-57).
- Knowledge sub-modes (Timeline/Map as sub-modes, Digest as a section) —
  **intentional** (doc lines 119-124, Daniel's Q1/Q2 answers).
- Page tab "Image ↔ transcript (RTF) side-by-side" — **intentional**
  (doc line 55) — this is where #3502's Source/Split/Transcript picker
  came from.
- Notes Marks/Notes toggle (#3513) — plausibly in-scope, not in the doc.

So the three nested levels were each individually approved or defensible.
What was **never designed** is their sum:

1. Top tab (3 options) → sub-mode picker (3, 5+1, or 2 options depending on
   tab) → PLUS the View-menu "Add View" section (7 options, ⌃⌥⌘1-7,
   `ViewMenuCommands.swift:538-564`) which operates on a DIFFERENT enum
   (`KGSurfaceTab`) that only partially overlaps the visible pickers. Four
   entry points, three enums (`ReaderTab`, `ReaderPageLayout`,
   `KGSurfaceTab`), no single source of truth for "what is the reader
   showing right now."
2. The View menu still offers **Transcript** (⌃⌥⌘1) but the Reader clamps
   it to Entities (`ReadingPaneView.swift:385-387`) — a silently broken
   menu item. Nobody designed that; it fell out of excluding `.transcript`
   from `knowledgeVizModes` without updating the menu.
3. Two different components are both called "Transcript" (the Page-tab
   native single-page pane vs. the WebKit `KGSurfaceTab.transcript`) —
   the naming collision is exactly where the confusion lives.

**The internal contradiction in the approved doc** (the seed of the drift):
`2026-07-11-reader-ia-design.md` line 21-23 says *"Preview View is the outer
viewing shell/container (hosts the reader); Reader View is the WebKit content
within it"* and line 76-78 says *"merge Preview View + Preview View - Image
Editing into the Reader (Page tab hosts image editing)"* — while the SAME doc's
review outcome (lines 59-62, 123-124) says *"Preview stays a SEPARATE surface
(Q3) ... a distinct lightweight quick-look, NOT merged into the full WebKit
Reader."* Both statements are marked as decided. The implementation followed
the merge reading (Page tab = full source viewer with image, loupe, page-turn);
Daniel's 2026-07-14 complaint follows the separate reading. The doc licensed
both.

## 4. History: how the drift entered

Reconstructed from the local reflogs (`.git/logs/HEAD`,
`.git/logs/refs/heads/inspector-ia-20260711`, `.git/logs/refs/heads/main`).
I could NOT read the GitHub issues themselves — the repo is private and this
session has no `gh` (see §12) — so issue intent is inferred from the design
doc, commit subjects, and code comments.

Timeline (all local time, -0300):

| When | Event | Evidence |
|---|---|---|
| 2026-07-11 ~09:12 | "docs: Reader View 4-tab IA design (draft)" | `.git/logs/refs/heads/main:254` |
| 2026-07-11 ~11:47 | "docs: Reader IA reviewed+approved — 3 tabs (Page/Knowledge/Notes), Preview separate" | `.git/logs/refs/heads/main:263` |
| 2026-07-11 ~22:58 | "feat(reader): native Page/Knowledge/Notes tab foundation (reader IA fold)" | `inspector-ia-20260711` reflog, ts 1783821919 |
| 2026-07-11 ~23:24 | "wire Page/Knowledge/Notes tabs into the reading pane (#3501)" | ts 1783823089 |
| 2026-07-11/12 ~23:38 | **"Page tab source/split/transcript layout toggle (#3502)"** | ts 1783823897 |
| 2026-07-12 ~00:00 | "Knowledge tab sub-mode switcher — graph/claims/timeline/map/digest (#3504/#3505)" | ts 1783824277 |
| 2026-07-12 ~01:30 | **"default to Page tab + remove dead fivePaneReadingView (consolidation step 1)"** | ts 1783829435 |
| 2026-07-12 | Digest section (#3512), Notes toggle (#3513), native Entities/Graph/Timeline/Map (#3503) | ts 1783830345-1783834414 |
| 2026-07-12 | reveal-source switches to Page tab (#3521); shared SurfaceTabBar (#3530) | ts 1783836919, 1783863789 |
| 2026-07-13 | iPhone split collapse (#3666); Reader settings/typography (#3680-#3684) | ts 1783927047+, gate-3677b3 reflog |

Reading of the timeline: the entire reader IA fold was implemented in **one
overnight session (2026-07-11 ~23:00 → 07-12 early morning)** by the
worker-grind pipeline, ~12 hours after the design doc was approved. The
"default to Page tab" commit landed at ~01:30 local. This matches the known
failure mode of that pipeline (several agents reshaping one surface in rapid
sequence, each commit locally defensible).

**The "source first" comment** (`ReadingPaneView.swift:59-62`): *"Defaults to
Page: the reader reads the source first (Daniel 2026-07-12)"*. What I can and
cannot establish:

- The Page-tab default was introduced by the 01:30 consolidation commit
  ("default to Page tab", ts 1783829435) — i.e. during the overnight grind,
  attributed to something Daniel purportedly said on 07-12.
- I **cannot verify Daniel ever said this** — no design doc, no issue text,
  and no reflog entry records the quote. The approved IA doc does NOT specify
  which tab is the default, and does NOT specify `.source` as the Page-tab
  layout default. Both defaults are implementation-session choices.
- The `.source` layout default (`ReadingPaneView.swift:69`) carries no
  attribution at all — no issue number, no doc citation. It appears to have
  shipped with or shortly after #3502.
- Per the brief, this comment should be treated as **suspect, not authority**.
  Even if Daniel did say something like "the reader reads the source first"
  on 07-12, his 07-14 statement supersedes it, and the comment's function in
  the codebase today is to make agents defend the current default. It should
  be removed/rewritten in whatever fix lands.

## 5. The Preview boundary — what the Reader now duplicates

The Preview surface exists and sits **in the same window, right next to the
Reader**:

- The widescreen layout has a **canvas pane** — `widescreenCanvasPane`,
  `ContentView+ViewBuilders.swift:440-485`, focus id `.preview`
  (`:460-461`) — which renders `PDFPageWithToolbar` for PDFs (`:450`) or
  `EditorView` (image editing / `ZoomableImagePreview`,
  `Views/Preview/ImageViewer/ImageViewerComponents.swift:14,495`) otherwise.
- The standard-layout `previewView` (`ContentView+ViewBuilders.swift:521-549`)
  does the same via `PDFReadingView` (`Views/Preview/PDFViewer/PDFReadingView.swift:25,33`).
- Quick-look/media preview components: `QuickLookPreviewViews.swift:14-135`,
  `MediaStreamPreview.swift:22`.
- There is a Preview settings pane (`SettingsView.swift:160`,
  `PreviewViewSettingsPane`) and a Preview mode section in the View menu
  (`ViewMenuCommands.swift:426`) — Preview is a first-class surface.

The duplication is exact:

| Capability | Preview (canvas pane) | Reader Page→Source |
|---|---|---|
| PDF page render + loupe + page nav | `PDFPageWithToolbar` (`ContentView+ViewBuilders.swift:450`) | `PDFPageWithToolbar` (`ReadingPaneView.swift:459,462`) |
| Image render | `EditorView`/`ZoomableImagePreview` | `DocumentCanvas(.imageStorageDisplay)` (`ReadingPaneView.swift:465`) |
| Page-turn animation | — | #2485 3D page-turn (`ReadingPaneView.swift:74-81,530-539`) |

So with default settings a user with both panes open sees **the same page
image twice** — once in the Preview canvas pane and once in the Reader's Page
tab — and the derived-knowledge content (the point of the Reader) is two
clicks away. This is Daniel's "you added the image preview, which makes no
sense" observation, verified.

## 6. Did the WebKit transcript capability regress?

**YES — the multi-page WebKit transcript is unreachable in the entire app UI.
The engine capability is intact; the client orphaned it.**

Evidence, engine side (capability intact):
- `fichero-server/src/fichero_server/api/routes/views.py:37-49`
  (`_transcript_for_document`): for a parent document it **concatenates the
  `page_content` of ALL child pages, in sequence order**, into one transcript
  string — this is the render-10,000-files-in-one-scroll capability.
- It is served into `document_view.html` (`views.py:156,163,205-213`) and
  rendered in the shared `WKWebView` via `DocumentKGWebPane`
  (`DocumentKGWebPane.swift:495` macOS / `:871` iOS), with per-page anchors
  (`.transcript [data-page]`, `DocumentKGWebPane.swift:339,412-416`) that
  power scroll↔page sync (#3226).

Evidence, client side (unreachable):
- Only `KGSurfaceTab.transcript`/`.digest` still use WebKit
  (`DocumentKGSurface.swift:118-123`); everything else went native in #3503.
- `DocumentKGSurface` has exactly **two** call sites:
  `ReadingPaneView.swift:554` and `ContentView+KnowledgeSurface.swift:19`.
- In `ReadingPaneView`, `.transcript` is excluded from the Knowledge
  sub-modes (`:368`) and clamped to `.entities` (`:373-387`). Unreachable.
- `ContentView+KnowledgeSurface.swift`'s `knowledgeSurface(...)` — the one
  place whose internal default is `.transcript`
  (`DocumentKGSurface.swift:171`) — is **dead code**: a project-wide search
  finds its definition (`ContentView+KnowledgeSurface.swift:5`) and no
  callers. (Likely orphaned by the "remove dead fivePaneReadingView"
  consolidation commit, ts 1783829435.)
- The View menu's "Transcript" item (⌃⌥⌘1, `ViewMenuCommands.swift:547-559`)
  routes into the Reader's clamp and lands on Entities.

What replaced it is strictly weaker: `PageContentPane` is native, shows **one
page at a time**, and shows nothing at all for non-page documents
(`PageContentPane.swift:29-32,66-71` — a folder/parent selection gets
*"Select a page"*). A folder of 10,000 page images has **no readable
transcript anywhere in the app today.**

(Peripheral note: `ImmersiveReaderView` has its own native image/transcript/
translations switcher (`ImmersiveReaderView.swift:166`) — also per-page, also
not WebKit. And recent work #3683/#3684 styled "Reader HTML" CSS — polishing
a WebKit surface users can currently only reach as Digest.)

## 7. PDFPageView — Preview or Reader?

**Preview (source-viewing infrastructure), despite living in
`Views/Reader/`.**

- `PDFPageView` is the PDFKit `NSViewRepresentable` used only by
  `PDFPageWithToolbar` (`PDFPageWithToolbar.swift:234`).
- `PDFPageWithToolbar`'s call sites: the Preview canvas pane
  (`ContentView+ViewBuilders.swift:450`), `DocumentCanvas`
  (`DocumentCanvas.swift:53`), `PDFReadingView` (`PDFReadingView.swift:25,33`
  — the standard-layout preview), and the Reader's Page→Source
  (`ReadingPaneView.swift:459,462` — the very duplication this doc says to
  remove).
- It renders the SOURCE (PDF pages, loupe, thumbnails) — by the three-surface
  rule that is Preview's job. Recommendation for the repo-hygiene plan: when
  the Page-tab source rendering leaves the Reader (§9), `PDFPageView`,
  `PDFPageWithToolbar`, `PDFLoupeOverlay`, `PDFThumbnailView`,
  `PDFReadingView` should be re-homed out of `Views/Reader/` into
  the Preview grouping. File moves only, after the IA fix — not before.

## 8. Proposed IA

### 8.1 The principle

One surface, one mode system, **two levels maximum**: a top tab row, and at
most one sub-mode picker inside a tab. Kill the third level
(`ReaderPageLayout`) entirely. Kill the parallel View-menu enum mismatch.
The Reader never renders source pixels.

### 8.2 The proposed structure

**Top tabs: `Read | Knowledge | Notes`** (rename Page → Read; keep three tabs,
keep `SurfaceTabBar`).

| Tab | Content | Render | Sub-modes |
|---|---|---|---|
| **Read** (default) | The **WebKit transcript** — the engine-assembled, multi-page transcript (`views.py:37-49`) via `DocumentKGWebPane`, with page anchors, scroll↔page sync (#3226), claim highlight, zoom. **Digest** lives here as its second sub-mode: both are "derived text made readable", both are the two remaining WebKit views (`DocumentKGSurface.swift:118-123`). | WebKit | `Transcript / Digest` (2) |
| **Knowledge** | Unchanged from today: Entities / Claims / Graph / Timeline / Map (native, #3503). Digest moves out (to Read), which resolves the awkward "section, not a sub-mode" special-casing (`ReadingPaneView.swift:341-354`). | native | 5-segment picker |
| **Notes** | Unchanged: Marks / Notes (#3513). | native | 2 |

What this fixes, point by point:
- **The transcript is the Reader's first paint again.** Default tab = Read,
  default sub-mode = Transcript. Daniel's complaint resolved at the root, not
  by flipping `ReaderPageLayout`'s default.
- **The 10,000-file capability is live again** — the Read tab hosts the
  engine's whole-document transcript, not `PageContentPane`'s one page.
- **`ReaderPageLayout` (source/split/transcript) is deleted.** Source viewing
  is Preview's job and Preview already does all of it: canvas pane
  (`ContentView+ViewBuilders.swift:440-485`), and source+page-text split
  (`PDFReadingView.swift:33-49`). Side-by-side source-and-transcript reading
  = Preview pane + Reader pane open together — the window already provides
  it (that is what the two panes are FOR).
- **Mode count drops** from 3 levels / 4 entry points to 2 levels: 3 tabs ×
  (2 | 5 | 2) sub-modes. Every visible option is reachable and none is
  duplicated elsewhere.
- **The View menu is reconciled**: "Add View" should be rebuilt on the new
  reality — Transcript/Digest select the Read tab's sub-mode; Entities/Claims/
  Graph/Timeline/Map select Knowledge sub-modes. One enum path, no clamp, no
  dead menu items. (Or retire the section — Daniel's call, §11 Q5.)

### 8.3 Cross-pane flows under the new IA

- **Reveal source** (#2105/#3521, `ReadingPaneView.swift:239-242`): today it
  forces the Reader to Page+split. New behaviour: reveal navigates the
  **Preview** pane to the page (the `.ficheroNavigateToPage` path it already
  uses) and the Reader's Read tab scrolls its WebKit transcript to the page
  anchor (#3226 machinery, `DocumentKGWebPane.swift:412-416`). Same intent,
  each surface doing its own job.
- **Scroll sync**: `DocumentScrollSyncState` (`DocumentKGSurface.swift:20-45`)
  already arbitrates pdf↔web panes; it now genuinely syncs Preview (PDF)
  against Reader (WebKit transcript) instead of two panes inside the Reader.
- **Per-page transcript editing** (`PageContentPane`'s Edit button,
  `PageContentPane.swift:117-123`): editing is the Inspector's job by the
  three-surface rule. Recommend: Reader transcript is read-only; "Edit this
  page's text" routes to the Inspector (or stays available in Preview's
  `PDFReadingView` content pane, which survives untouched). §11 Q3.

### 8.4 Prerequisites to make the default transcript honest at scale

The approved doc already flagged the WebKit debt
(`2026-07-11-reader-ia-design.md:84-93`): #3225 (whole KG serialized into one
HTML response), #3224 (full-table scans), #3226 (anchors — landed). If the
Read tab becomes the default surface for genuinely huge folders,
`_transcript_for_document`'s single concatenated string (`views.py:37-49`)
will need lazy/windowed loading in the same spirit as #3225. Recommend making
that an explicit engine issue in the fix milestone rather than discovering it
as a perf regression. (I could not verify the current status of #3224/#3225
fixes beyond commits named for them on `inspector-engine-codex` reflog
entries — see §12.)

## 9. What moves OUT of the Reader, what stays

**OUT (to Preview, which already owns equivalents):**
- Page-image rendering: `DocumentCanvas(.imageStorageDisplay)` call
  (`ReadingPaneView.swift:464-469`).
- PDF page rendering: `PDFPageWithToolbar` calls
  (`ReadingPaneView.swift:458-462`).
- The 3D page-turn animation + its `@AppStorage("reader.pageTurnAnimated")`,
  `pageTurnForward` tracking (`ReadingPaneView.swift:74-81, 440-442, 528-539`)
  — a source-navigation nicety; belongs with the image sequence in Preview
  (it already ships in the immersive reader too, #2485/#3548).
- `ReaderPageLayout` and its picker (`ReaderTabBar.swift:57-87`,
  `ReadingPaneView.swift:398-436`).
- Longer-term (file moves, hygiene milestone, §7): `PDFPageView`,
  `PDFPageWithToolbar`, `PDFLoupeOverlay`, `PDFThumbnailView`,
  `PDFReadingView` out of `Views/Reader/`.

**STAYS in the Reader:**
- The WebKit transcript + digest (`DocumentKGSurface` / `DocumentKGWebPane`)
  — promoted back to the default.
- Knowledge tab and its five native sub-modes (approved 07-11, no complaint).
- Notes tab (Marks/Notes).
- Pin, zoom, split-pane chrome, active-surface tracking, open-in-tab/window
  (`ReadingPaneView.swift:51-55, 149-176, 180-213`) — pane plumbing, surface-
  agnostic.

**Explicitly NOT proposed** (iterate, never replace): no rewrite of
`ReadingPaneView`; the change is (a) delete the Page tab's source branches,
(b) add a Read tab that hosts the existing `DocumentKGSurface` with
`.transcript`/`.digest`, (c) retarget reveal-source. `PageContentPane` itself
is untouched — it keeps serving `PDFReadingView` (Preview) and any future
Inspector edit flow.

## 10. Migration (including @SceneStorage state)

Current keys (all in `ReadingPaneView.swift`):
- `reader.topTab` (`:63`) — values `page|knowledge|notes`, decoded with
  `ReaderTab(rawValue:) ?? .page` (`:64`).
- `reader.page.layout` (`:69`) — `source|split|transcript`.
- `reader.notes.mode` (`:45`) — unchanged, keep.
- `reader.pageTurnAnimated` (`@AppStorage`, `:77`) — moves with the page-turn
  to Preview; same key, so the user setting survives.

Plan:
1. Rename the enum case `ReaderTab.page` → `ReaderTab.read` with rawValue
   `"read"`. Keep the key `reader.topTab`. Stale persisted `"page"` fails
   `ReaderTab(rawValue:)` and falls into the existing `??` fallback — set the
   fallback to `.read`. Users who were on Page land on Read (the transcript):
   exactly the intended correction, no crash, no migration code.
2. If a stale `"knowledge"`/`"notes"` value is stored, it still decodes —
   those users keep their tab. Nothing breaks.
3. Delete `ReaderPageLayout` + `reader.page.layout`. Orphaned @SceneStorage
   values are inert (never read again); no cleanup required.
4. Read-tab sub-mode: new `@SceneStorage("reader.read.mode")`
   (`transcript|digest`), default `transcript`. The existing
   `@State activeTab: KGSurfaceTab` (`:58`) keeps driving Knowledge; its
   `.graph` default stands.
5. `revealSourceInPageTab()` (`:239-242`) → `revealSourceInTranscript()`:
   switch to Read/transcript + let the #3226 anchor path scroll; drop the
   `pageLayout` mutation.
6. Rewrite `RepresentationSection` (`ViewMenuCommands.swift:538-564`) against
   the new structure; delete the ⌃⌥⌘1 clamp bug by construction.
7. Update/replace the comment block at `ReadingPaneView.swift:56-62` — the
   "reads the source first (Daniel 2026-07-12)" line must not survive to
   justify the old default again. Cite THIS doc and #3765 instead.
8. Tests: `InspectorLayoutTests.swift:484-519` locks `KGSurfaceTab` shape —
   update alongside; add tests that (a) the Reader's default surface is the
   WebKit transcript, (b) `"page"` scene-storage decodes to `.read`, (c) the
   View-menu transcript action actually reaches the transcript (the current
   clamp would have failed such a test — that's the regression test #3765
   deserves).
9. Land as one lane owning `Views/Reader/` + `ViewMenuCommands.swift`
   (disjoint-files rule); no engine change required for step 1-8.

## 11. Questions for Daniel (each with a recommendation)

**Q1. Does the Knowledge tab stay in the Reader?** The 07-11 review approved
it, but a stricter reading of "Reader = derived text made readable" could push
Entities/Claims/Graph/Timeline/Map toward the Inspector/OntologyBrowser and
make the Reader single-purpose (transcript+digest only, no top tabs at all).
**Recommendation: keep Knowledge (and Notes) — they are derived-knowledge
reading, they were explicitly approved, and removing them is churn with no
complaint behind it. Revisit only if the tabs feel heavy after the Read tab
returns.**

**Q2. Where does Digest live?** Today: a "section" bolted onto Knowledge
(#3512). Proposed: second sub-mode of Read (it is derived TEXT, and it is the
other WebKit view). **Recommendation: Read tab. It also simplifies Knowledge's
picker special-case.**

**Q3. Where does per-page transcript editing go?** `PageContentPane` offers
Edit-in-place (#1189). Rule says editing = Inspector. **Recommendation: Reader
transcript read-only; keep the existing edit affordance in Preview's
`PDFReadingView` content pane for now and file a follow-up to consolidate
text-editing into the Inspector — don't grow this fix's blast radius.**

**Q4. Does the split (source beside transcript) need to exist INSIDE any
single pane?** Proposed answer: no — Preview pane + Reader pane side by side
is the split, and `PDFReadingView` already offers page+text within Preview.
**Recommendation: rely on the two panes; if iPhone (no side-by-side panes)
needs it, the compact layout already collapses to single-pane anyway
(#3666).**

**Q5. Keep the View-menu "Add View" section?** It predates the fold (#2032:
"views that can be ADDED — menu items, not icons") but now overlaps the
in-pane pickers and is partly broken. **Recommendation: keep the menu (menus
are Daniel's stated preference and give shortcuts + discoverability) but
regenerate it from the new two-level structure so menu and pane can never
disagree.**

**Q6. Is `.graph` the right Knowledge default?** (`ReadingPaneView.swift:58`,
chosen when transcript left the tab.) **Recommendation: Entities — it's the
cheapest, most legible "what we know" list and matches the picker's first
segment; Graph is the flashiest but least information-dense first paint. Weak
preference; either is fine.**

**Q7. Scale honesty:** if 10,000-page folders are a real near-term corpus
(Marshall Diaries scale), do we gate the Read-tab default on a windowed
transcript endpoint (§8.4), or ship eager-load first? **Recommendation: ship
the IA fix now (correctness), file the windowing issue immediately, and let
real corpora decide its priority.**

## 12. Uncertainties / what I could not verify

- **GitHub issues #3765, #3501-#3513, #3521, #3530, #3502's actual text**: the
  repo is private and this session had no `gh`/Bash. Everything attributed to
  issues here is inferred from commit subjects (reflogs), code comments, and
  the design docs. **Before implementing, someone should `gh issue view 3765
  3502 3504 3505 3512` and check for decisions I couldn't see.**
- **Whether Daniel actually said "the reader reads the source first" on
  2026-07-12** — no artifact records it (§4). I treated it as unverified per
  the brief; if he DID say it, the 07-14 statement still supersedes it.
- **Which exact commit set `ReaderPageLayout`'s default to `.source`** — the
  reflog names commits but I could not diff them (no git CLI). #3502's commit
  (ts 1783823897) is the prime suspect; immaterial to the design either way.
- **Runtime behaviour** — I did not build or run the app (build lock owned by
  another agent). All behaviour claims are static-analysis of `main` at
  51f940b1d. In particular "same page shown twice" (§5) assumes both panes
  visible in the widescreen layout, which the code supports but I did not
  visually confirm.
- **Status of engine perf issues #3224/#3225** — commits named for them exist
  (`inspector-engine-codex` reflog:35-36) but I did not verify they merged to
  main or fully resolve the issues.
- **`ContentView+KnowledgeSurface.swift` dead-code claim** — based on a
  project-wide ripgrep finding zero call sites of `knowledgeSurface(`; a
  compile-level check (or `find_references`) should confirm before deleting.
- The iOS/iPad Reader experience under the new IA (WebKit lazy-host, #2409)
  was not separately analyzed.

# Preview, Reader, Inspector — three surfaces (2026-08-09)

Read-only review for Daniel. These are THREE SURFACES and must never be merged;
reviewed as three. Every mechanism carries `file:line`; anything reasoned to
rather than read is marked **INFERRED**. Paths relative to `fichero/fichero/`.

---

## A correction to last night's diagnosis, before anything else

I reported earlier that five `browserSelection.first` sites were "five
independent draws from hash order" that disagree *with each other*. **The second
half of that is wrong, and I would rather correct it than have the code lane
act on it.**

`Set.first` is deterministic for a given set value within a process. All the
sites read the same `browserSelection` and therefore return the *same* element
as each other at a given moment. What is true, and what matters:

- The element is **arbitrary** — it is whatever hashing put first, not the row
  the user acted on. `LibraryView` knows the right answer
  (`orderedPrimarySelectionId`, `LibraryView+ArrowNavigation.swift:148`) and
  ContentView cannot see it, because the cursor is `@State` private to
  `LibraryView`.
- It is **unstable across launches** (per-process hash seed) and **can change
  when the set mutates**, which is why it reads as intermittent.
- The **inter-surface disagreement is a separate cause**: the surfaces do not
  differ in how they read the set, they differ in the *precedence chain* they
  wrap around it. That is §6 below, and it is the real answer to "four surfaces
  disagree about which page is selected".

Both defects are real. They need different fixes, which is why the distinction
is worth the paragraph.

Six sites, not five — one I had missed:

| site | decides |
|---|---|
| `ContentView+StateEvents.swift:160` | which doc is promoted to `detailDocument` |
| `ContentView+StateEvents.swift:182` | the re-check after an async fetch |
| `ContentView+StatePreview.swift:52` | preview restored on appear |
| `ContentView+StatePreview.swift:150` | preview repopulated when the list reloads |
| `ContentView+StateSelection.swift:31` | `inspectorDocument` |
| `Layout/ContentView+CompactReader.swift:53` | the compact reader's leaf |
| `Models/LayoutMode.swift:295` | **`CanvasDocumentPolicy.documentForCanvas`** — feeds BOTH preview call sites |

---

## The three surfaces, and what each thinks it is showing

This is the spine of every symptom below.

| surface | what it shows | expression |
|---|---|---|
| **Preview** (PDF/canvas) | `documentForCanvas`: `browserSelection.first` → `detailDocument` → `inspectorDocument` | `Models/LayoutMode.swift:289-305`, called at `Layout/ContentView+DetailLayout.swift:112-117` and `:190-195` |
| **Preview** (page index) | `pageFocusDocument ?? detailDocument` | `ContentView+ReadingLayout.swift:145-147` |
| **Reader** | `detailDocument`, directly — never consults selection or page focus | `Layout/ContentView+DetailLayout.swift:147`; `Views/Reader/Page/ReadingPaneView.swift:79` |
| **Inspector** | `browserSelection.first` (folder-scoped) → `pageFocusDocument` → `detailDocument` if `.page` → sidebar folder → `detailDocument` | `ContentView+StateSelection.swift:19-53` |

Four surfaces, four different precedence orders, built from the same three or
four pieces of state. Nothing reconciles them. **This is the root cause of
"the sidebar says page 7, the toolbar says 1, the inspector shows another
page"** — not a bug in any one surface.

---

## The reported symptoms, with mechanisms

### 1. PDF snaps back to page 1 — CONFIRMED, and it needs no user action

The clearest bug in this review.

- `pdfPageIndex(for:)` returns **0** for any document that is not
  `docType == .page` (`ContentView+ReadingLayout.swift:56-59`).
- `selectedPageIndex` is `pdfPageIndex(for: pageFocusDocument ?? detailDocument)`
  (`:145-147`). So the moment `pageFocusDocument` goes nil, the page index
  collapses to 0.
- `handleDetailDocumentChange` sets `pageFocusDocument = nil`
  **unconditionally** on every change of `detailDocument`
  (`ContentView+StateEvents.swift:196`).
- `detailDocument` is reassigned by ordinary background refreshes:
  `handleCurrentDocumentsChange` (`ContentView+StatePreview.swift:156`) and
  `handleDocumentRevisionChange` (`:178-183`).

So: read to page 7, let any workflow write page content or any refresh land, and
if the refreshed `Document` differs by `Equatable` from the old one, `onChange`
fires, page focus is wiped, and the PDF jumps to page 1. The user did nothing.

The clearing is deliberate and correctly motivated — its comment (`:194-195`,
#1463) is "don't show a page from the previous document". The defect is that it
cannot distinguish *a different document* from *the same document, refreshed*.
**Ready to fix:** clear page focus only when the document IDENTITY changes, not
when the snapshot is replaced. `refreshedFocusedDocument`
(`ContentView+StatePreview.swift:164`) already exists to do exactly this kind of
same-identity swap and could be applied to `pageFocusDocument` too.

### 2. Scrolling behaves like a reload — CONFIRMED mechanism, Inspector is the surface

Scrolling the PDF calls `syncGridSelectionToPDFPage` →
`applyReaderPageSignal(.scrolledPast, …)`
(`ContentView+ReadingLayout.swift:63-65, 81-122`), which sets `pageFocusDocument`
to a **new page-scoped `Document`** on every page turn (`:113-115`).

`inspectorDocument` prefers `pageFocusDocument`
(`ContentView+StateSelection.swift:39-41`), so the Inspector's document identity
changes on every page you scroll past. Roughly fifteen inspector panes gate
their network loads on `.task(id: document.id)` — e.g.
`Views/Inspector/Source/DocumentInspectorContentV2.swift:79`,
`Views/Inspector/Artifacts/ArtifactsInspectorPane.swift:190`,
`Views/Inspector/Knowledge/Citations/CitationsInspectorPane.swift:89`,
`Views/Inspector/Document/DocumentInspectorRelatedTab.swift:79`. Every one
re-fires per page turn.

This exact bug class was already found and fixed for the OCR-geometry probe:
`PDFPageWithToolbar.swift:257` keys its task off the page deliberately, with a
comment (`:251-256`) citing *"2026-08-08, 'changing page in PDF feels slow'"*.
**The fix was applied to one call site and the class was never swept.** That is
"fix the instance, not the class" — and it is the same habit named in the
companion review.

**INFERRED:** that the Inspector is what you are perceiving as the reload. The
Reader is *not* affected — its tasks key off `detailDocument`, which scroll
deliberately does not touch (`ContentView+ReadingLayout.swift:119-121`).

### 3. The Reader shows a whole transcript for one page — BY DESIGN, and the design is the problem

Not a bug in the code's own terms. The Reader is handed `detailDocument` — the
parent container, never the page (`Layout/ContentView+DetailLayout.swift:147`).
`ReadingPaneView+Tabs.swift:23-35` documents the intent: the engine assembles
the `page_content` of *every* child page into one transcript, and page selection
only drives scroll position within it (`:225-227`).

So "select page 7, Reader shows the whole book, scrolled to 7" is exactly what
was built. Whether that is what you *want* is a **design question** — and it is
the one that decides the multi-pane model below. My read is that the assembled
transcript is right for reading and wrong for verifying a single page's OCR, and
that the answer is a scope control in the Reader's own toolbar rather than a
change to what it is handed.

### 4. No zoom — the controls exist; something is hiding them

Zoom is fully wired: `PDFZoomController`
(`Views/Preview/PDFViewer/PDFPageControllers.swift:14-52`) into `ReaderToolbar`
via `PDFPageWithToolbar.swift:359-380`, rendered by
`Views/Reader/ReaderToolbar+Controls.swift:90-139`.

The file's own header comment (`PDFPageWithToolbar.swift:5-10`) says it "carries
no zoom controls by design". **That comment is stale and contradicted 350 lines
below in the same file** — worth deleting before it misleads someone into
"fixing" the toolbar by removing the controls.

Two candidate causes, both needing a running app to settle:
- The zoom cluster defaults to collapsed —
  `@AppStorage("readerToolbar.zoomExpanded") private var zoomExpanded = false`
  (`Views/Reader/ReaderToolbar.swift:70`) — and `ReaderToolbarCluster`
  (`:219-258`) uses `ViewThatFits` whose first candidate is an `EmptyView` when
  collapsed. An `EmptyView` fits any width, so `ViewThatFits` may select it over
  the collapsed-icon fallback and render **nothing**. **INFERRED** — this is the
  strongest lead, not a confirmed root cause, and it is cheap to test.
- On compact width the cluster is dropped outright, with no substitute:
  `if !isCompact { zoomCluster }` (`ReaderToolbar.swift:190-192`). Confirmed.

### 5. Duplicate preview panes — most likely persisted split state

`Views/Components/SplittablePane.swift:110-267` persists split counts in
`@SceneStorage("splittablePane.<key>.verticalCount"/".horizontalCount")`
(`:138-139`). When a count exceeds 1, `splitContainer` (`:190-199`) invokes the
**same `content()` closure** two or three times, each instance building its own
`PDFPageWithToolbar` with its own controllers
(`PDFPageWithToolbar.swift:22-23, 56-57`).

Because it is `@SceneStorage`, a split toggled once — deliberately, or by a
stray click on the split buttons the `MiniToolbar` injects — **persists across
relaunches of that window**. It would present exactly as "there are two preview
panes and I did not ask for them". **INFERRED**; I found no code path that
mounts two previews without a split having been recorded.

Ruled out, so nobody re-treads it: the widescreen canvas pane and the
`.none`/`.standard` preview are mutually exclusive by `currentLayoutMode`
(`Layout/ContentView+SidebarLayout.swift:145-238`).

### 6. Four surfaces disagree — see the table above

The cause is four precedence chains, not four readings of the selection. Fixing
`Set.first` alone will make the wrong answer *stable*; it will not make the
surfaces agree.

---

## Smaller things found on the way

- **The same Preview surface shows a title in one layout and not the other.**
  The widescreen canvas passes `documentTitle: detailDocument?.name`
  (`Layout/ContentView+DetailLayout.swift:105`); the `.none`/`.standard`
  `previewView` omits the argument entirely (`:196-206`), so it defaults to
  `nil` (`PDFPageWithToolbar.swift:17`) and the title slot is blank. Confirmed —
  one surface, two call sites, two behaviours.
- **The Inspector never says what it is inspecting.**
  `DocumentInspector.documentDetail`
  (`Views/Inspector/Document/DocumentInspector.swift:119-133`) has no
  header or title row. The document name appears only inside
  `DisplayAttributesStrip`, which lives in the Content tab — so on Knowledge
  Graph, Citations, Info, Notes and Artifacts there is nothing on screen naming
  the document or page. Given §6, this is the surface where "which page am I
  looking at?" is hardest to answer and the only one that never answers it.
- **A PDF that fails to load shows nothing at all.**
  `Views/Preview/PDFViewer/PDFPageView.swift:212-251` (iOS mirror `:711-750`):
  on `catch` it sets `requestedDocumentId = nil` and returns. No
  `ContentUnavailableView`, no retry, no message. The image path has the proper
  treatment (`DocumentCanvas.swift:140-150`) — the PDF path has no equivalent.
  This is the "errors must say why" rule, unmet on the surface Daniel is using
  most.

---

## Recommendation: the multi-pane focus model

**Do not build a new one — there is one, and it is half-wired.**
`ContentView.swift:238` declares `@FocusState var focusedPane: PaneFocus?`, the
panes set it on tap (`Layout/ContentView+DetailLayout.swift:109, :130, :156,
:321`), and `paneFocusIndicator` draws a fading border for the focused pane
(`Layout/ContentView+SidebarLayout.swift:24-27`).

What `focusedPane` does **not** yet do is the two things that matter:

**1. It does not route destructive and scope-bearing commands.** ⌘⌫ goes
unconditionally to the sidebar selection —
`FocusedDeleteButton` calls only `sidebarActions?.deleteItem()`
(`App/Menus/FocusedCommandButtons+SidebarActions.swift:101-117`), bound at
`FicheroApp.swift:426`. With focus in the library grid, ⌘⌫ deletes the sidebar's
selected **parent folder**. That is data loss, and the confirmation says a count
rather than naming what it will delete.

The precedent for the fix is already in the tree and is good:
`SelectAllButton` (`App/Menus/FocusedCommandButtons+SelectAll.swift`) resolves a
route at menu-validation time and — importantly — *disables itself* when it has
no business claiming the key, so the responder chain still works. Delete should
be the same shape, and the confirmation must NAME its targets.

**2. It does not decide what each surface shows.** This is the real proposal.

> **One published primary, one focused pane.**
>
> - `LibraryView` stays the owner of the cursor — it is the surface that knows
>   its ordered list, and that list differs per view mode. It **publishes**
>   `orderedPrimarySelectionId` to a single window-scoped home
>   (`WindowState`, alongside `preservedDocumentSelection`, which exists for
>   exactly this reason).
> - **One accessor** in ContentView reads it, falling back — when the library
>   pane is not mounted — to the topmost selected row in document order. Never
>   `Set.first`. The seven sites above collapse into that accessor.
> - `pageFocusDocument` stays the page cursor, but is cleared on document
>   IDENTITY change only (§1), not on snapshot replacement.
> - Each surface keeps its own *scope* — Preview shows a page, Reader shows the
>   container, Inspector follows the page — but they all derive it from the one
>   published primary, so they can differ **by design and never by accident**.
>   Three surfaces, one answer to "what is selected", three deliberate answers
>   to "what do I show about it".
> - Each pane gets a title that says what it is showing (§ smaller things). With
>   three panes deriving different scopes from one selection, the titles are not
>   decoration — they are how the user tells a deliberate difference from a bug.

That ordering matters: publish the primary first, then the surfaces can be
made to agree. Doing the surfaces first just relocates the disagreement.

---

## Summary for triage

**Cheap and certain:**
- Delete the stale "no zoom controls by design" comment (`PDFPageWithToolbar.swift:5-10`) — it contradicts the same file
- Pass `documentTitle` at the second preview call site (`Layout/ContentView+DetailLayout.swift:196-206`)
- A real empty/error state for PDF load failure (`PDFPageView.swift:212-251`) — the image path is the model

**High value, well understood:**
- §1 page-1 snapback — clear page focus on identity change, not snapshot replacement. Best symptom-to-effort ratio in this review.
- §2 sweep the `.task(id: document.id)` class across the ~15 inspector panes; the one-site fix at `PDFPageWithToolbar.swift:257` is the template
- Delete-by-focused-surface, with a confirmation that names its targets

**Needs a running app:**
- §4 whether `ViewThatFits` is swallowing the collapsed zoom cluster
- §5 whether the duplicate panes are persisted `@SceneStorage` split state (check for a stored `splittablePane.*.verticalCount` > 1)

**Design questions for Daniel:**
- §3 should the Reader be scopeable to one page, or stay whole-transcript-with-scroll? (I suggest a scope control in the Reader's toolbar, not a change to what it is handed)
- Does each pane get a title bar naming what it shows? (I recommend yes — it is what makes three surfaces legible)

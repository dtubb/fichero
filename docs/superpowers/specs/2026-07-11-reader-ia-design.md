# Reader View Information Architecture — Design DRAFT (2026-07-11)

Status: **draft for review** (Daniel away; pre-agreed autonomous playbook —
audit → synthesize 4-tab IA → wireframe; NO Reader source edits until reviewed).
Models the Inspector 10→4 fold (see `2026-07-11-inspector-ia-design.md`).

## Audit — what the Reader is today

The Reader is the **WebKit visual canvas** for one document ("Reader view
(WebKit) + all its options"). Two render paths:

- **Native PDF/image** (`Views/Library/Reading/`): PDFReadingView, PDFPageView,
  PDFThumbnailView, PDFLoupeOverlay, PageImageGrid, DocumentTextReader,
  ImmersiveReaderView — the source page images/text.
- **WebKit HTML views**: transcript, knowledge-graph, entities, claims,
  timeline, map, graph, digest, sources — rendered server-side to HTML and
  shown in a `WKWebView`.

**Preview View** is the outer viewing *shell/container* (hosts the reader,
plus image editing); **Reader View** is the WebKit content within it — they
reconcile (Preview = shell, Reader = content).

Milestone sprawl mirrors the pre-fold Inspector: **Reader View** (11 open) +
near-empty sub-views `WebKit PDF/Document`, `Transcript`, `Entities`, `Claims`,
`Timeline`, `Map`, `Graph`, `Digest`, `Sources`, `Knowledge Graph`; plus
`Preview View` (5), `Preview View - Image Editing` (23), `Library View - Canvas`
(2D), `Library View - Spatial` (3D, 7).

Open Reader issues are mostly **WebKit quality/perf/security**: scroll↔page
anchor mapping (#3226), KG serialized whole into one HTML response (#3225),
full-table scans per page (#3224), Bearer token exposed to page JS (#3223),
page-curl animation (#2485), loupe (#2419), iPad WebView jank (#2409), RTF
escape-code rendering (#2317/#2416), HTR transcript-to-page (#2395).

## The Reader's job (relative to Inspector + Library)

Established by the Inspector design: **Reader = READ + EXPLORE one document
visually; Inspector = EDIT the database; Library = browse/organize.** The
Reader is the explore/visualize counterpart of the Inspector's edit surface.
It reads the source and explores its knowledge *in place*; it does not edit the
database (that routes to the Inspector) — though it hosts reading marks
(annotations) and can reveal a claim's source.

## The 4 tabs (down from ~10 modes) — parallels the Inspector

| Reader tab | Absorbs | Render | Notes |
|---|---|---|---|
| **Page** | WebKit-PDF/Document, Transcript, page image/grid, loupe, page-curl, image edits | native PDFKit + text | "Read the source." Toggle image ↔ transcript (RTF) side-by-side; loupe; page-turn; non-destructive image edits as a tool. Parallels Inspector **Source**. |
| **Knowledge** | Entities, Claims, Graph, KG, **Timeline**, **Map** | WebKit HTML | "Explore what we know." Entity/claim highlights overlaid on the page + a force graph; **Timeline and Map are visualization sub-modes within Knowledge, not top tabs**. Parallels Inspector **Knowledge**. |
| **Digest** | Digest, Sources | WebKit HTML | "The overview." AI synthesis/summary of the document + a sources/provenance overview. Parallels Inspector **Artifacts** (derived outputs). |
| **Notes** | Annotations (highlight/note/bookmark), reading marks | native overlay | The human/reading layer — marks anchored to the page. Parallels Inspector **Notes**. |

**Switcher:** same decision as the Inspector — narrow-friendly native control
(top icon row leaning), decided from the wireframe. Reader is the *center*
pane (sidebar │ Reader │ Inspector), so it has more width than the Inspector.

**What reconciles/leaves:**
- **Preview View** → the Reader is the content of the Preview shell; merge
  `Preview View` + `Preview View - Image Editing` into the Reader (Page tab
  hosts image editing).
- **Canvas (2D) / Spatial (3D)** → these are **Library** view modes (per prior
  decision), not Reader tabs — keep disjoint.
- The visual **force graph** is shared with the OntologyBrowser; the Reader's
  Knowledge tab links/embeds it for exploration (editing stays in Inspector).

## Cross-cutting contracts (all tabs)

- **WebKit performance + security first** (these are the real open issues):
  lazy-load/paginate KG (#3225), indexed queries not full scans (#3224), real
  page anchors for scroll↔page (#3226), and **never expose the engine Bearer
  token to page JS** — proxy auth natively (#3223).
- **Source ↔ Inspector sync**: selecting a claim/entity in the Reader reveals
  it in the Inspector and vice-versa (the #2105 source-nav contract, shared).
- **Native reading affordances**: page-curl (#2485), loupe (#2419), smooth
  iPad WebView (#2409).
- **Cross-platform** Mac/iPad/iOS; all transport OpenAPI; @Observable stores.

## Milestone/issue reconciliation (PROPOSED — execute after review)

Fold the ~10 near-empty Reader sub-view milestones into the 4 tabs (like the
Inspector 23→9): **Reader View - Page** (WebKit-PDF/Document + Transcript +
Preview + Image-Editing), **Reader View - Knowledge** (Entities + Claims +
Graph + KG + Timeline + Map), **Reader View - Digest** (Digest + Sources),
**Reader View - Notes** (Annotation Tools), each with an `- Engine` counterpart
where real API work exists. Retire empties; keep Canvas/Spatial under Library.
Priority-label the 11 real open Reader-View bugs. **Do not execute the
destructive fold until this draft is reviewed.**

## Build order (after reconciliation)

- **P0 foundation:** WebKit security (#3223 token) + perf (#3224 queries,
  #3225 KG lazy-load) + scroll anchors (#3226) — the reader must be solid
  before adding tabs.
- **P1:** the 4-tab switcher + Page tab (image/transcript toggle, loupe,
  page-curl) + Preview reconciliation.
- **P2:** Knowledge tab (overlays + graph + timeline/map sub-modes), Notes tab.
- **P3:** Digest tab, progressive disclosure.

## Open questions for review

1. Is **Digest** a top tab, or a section within Knowledge? (It's thin alone.)
2. Do **Timeline/Map** stay as Knowledge sub-modes, or does the corpus need
   them as top-level exploration tabs?
3. **Preview vs Reader**: confirm full merge (Preview = Reader's shell), or is
   Preview a distinct quick-look surface to keep?

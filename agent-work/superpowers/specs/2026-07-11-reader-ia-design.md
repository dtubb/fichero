# Reader View Information Architecture — Design (2026-07-11)

Status: **REVIEWED + APPROVED** (Daniel 2026-07-11). Reader folds ~10 WebKit
modes → **3 top tabs (Page / Knowledge / Notes)**, native chrome over WebKit
content. Models the Inspector 10→4 fold (see `2026-07-11-inspector-ia-design.md`).
Milestone reconciliation may proceed; Reader source implementation is gated on
Inspector reconciliation completing + a worker freeing up (2-worker cap).

## Audit — what the Reader is today

The Reader is the **WebKit visual canvas** for one document ("Reader view
(WebKit) + all its options"). Two render paths:

- **Native PDF/image** (`Views/Reader/`): PDFReadingView, PDFPageView,
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

## The 3 tabs (down from ~10 modes) — REVIEWED + APPROVED (Daniel 2026-07-11)

Daniel's Q1–Q3 answers fold Digest, Timeline, and Map *into* Knowledge, so the
Reader lands on **3 heavier top tabs** (not 4 — Knowledge does more work here
than the Inspector's Knowledge). If image-vs-text ever needs splitting,
Transcript could become a 4th tab, but it lives inside Page for now.

| Reader tab | Absorbs | Render | Notes |
|---|---|---|---|
| **Page** | WebKit-PDF/Document, Transcript, page image/grid, loupe, page-curl, image edits | native PDFKit + text | "Read the source." Image ↔ transcript (RTF) side-by-side; loupe; page-turn; non-destructive image edits as a tool. |
| **Knowledge** | Entities, Claims, Graph, KG + **Timeline & Map (sub-modes)** + **Digest (section)** + Sources | WebKit HTML | "Explore what we know." Entity/claim highlights on the page + force graph; Timeline/Map are visualization **sub-modes**; the AI **Digest** summary + sources are a **section**, not a tab (Q1/Q2). |
| **Notes** | Annotations (highlight/note/bookmark), reading marks | native overlay | The human/reading layer — marks anchored to the page. |

**Preview stays a SEPARATE surface (Q3):** Preview is a distinct lightweight
quick-look, *not* merged into the full WebKit Reader. Keep `Preview View` +
`Preview View - Image Editing` as their own milestones; do not fold them into
the Reader.

**Switcher (DECIDED, Daniel 2026-07-11): native tabs at the top.** The Reader
is the center pane with room to spare, and top tabs read well.

**Native chrome over WebKit content (DECIDED):** ~75% of Reader elements are
WebKit (the HTML views — transcript, KG, entities, claims, timeline, map,
graph, digest, sources). So the design is **native-OS chrome — top tabs,
toolbar, loupe, page controls, selection — wrapping WebKit content.** The
shell is native SwiftUI; the content pane is `WKWebView`. Native affordances
(page-curl, loupe, tab switching, source-reveal) must not be re-implemented in
HTML; they wrap the web content natively.

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

Fold the ~10 near-empty Reader sub-view milestones into the **3 tabs**:
**Reader View - Page** (WebKit-PDF/Document + Transcript + Image-Editing),
**Reader View - Knowledge** (Entities + Claims + Graph + KG + Timeline + Map +
Digest + Sources), **Reader View - Notes** (Annotation Tools), each with an
`- Engine` counterpart where real API work exists. Retire empties. **Preview
View + Preview View - Image Editing stay separate** (Q3). Keep Canvas/Spatial
under Library. Priority-label the 11 real open Reader-View bugs. Plan is
REVIEWED (Daniel 2026-07-11) — the milestone fold may execute, but **Reader
source implementation waits until Inspector reconciliation completes and a
worker frees up** (2-worker cap).

## Build order (after reconciliation)

- **P0 foundation:** WebKit security (#3223 token) + perf (#3224 queries,
  #3225 KG lazy-load) + scroll anchors (#3226) — the reader must be solid
  before adding tabs.
- **P1:** the 4-tab switcher + Page tab (image/transcript toggle, loupe,
  page-curl) + Preview reconciliation.
- **P2:** Knowledge tab (overlays + graph + timeline/map sub-modes), Notes tab.
- **P3:** Digest tab, progressive disclosure.

## Review outcome (Daniel 2026-07-11) — RESOLVED

1. **Digest** → a **section inside Knowledge** (not a top tab).
2. **Timeline/Map** → **sub-modes inside Knowledge** (not top tabs).
3. **Preview** → **kept separate** (a distinct quick-look surface, not merged
   into the Reader).

Result: **3 top tabs — Page / Knowledge / Notes**, native top tabs, native
chrome over WebKit content. Plan approved for milestone reconciliation now;
Reader source implementation gated on Inspector reconciliation + a free worker.

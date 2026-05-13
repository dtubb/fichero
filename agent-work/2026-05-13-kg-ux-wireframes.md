# KG UX Wireframes — Source-Anchored Knowledge Graph (2026-05-13)

Daniel's principle: **entities + claims + sources always together. Never the entire text — just the relevant text. Click takes you to the source with the relevant part highlighted.**

This document is the wireframe pass before more code.

---

## Core mental model

Three things, always shown in the same window:

```
┌────────────┬──────────────────────────┬──────────────────┐
│            │                          │                  │
│  NAV       │       SOURCE             │   KG INSPECTOR   │
│            │       PREVIEW            │                  │
│ Library    │                          │  Entities        │
│ Workflows  │   (PDF / image / text    │  Claims          │
│ KG         │    with highlights)      │  Source          │
│ Activity   │                          │                  │
│            │                          │                  │
└────────────┴──────────────────────────┴──────────────────┘
   ~220pt          flex / dominant         ~360pt
```

Source preview is the dominant center because that's the audit surface. Inspector floats on the right with the KG affordances. Sidebar is narrow nav.

---

## View 1 — Library (default; reading a document)

```
┌────────────┬─────────────────────────────┬──────────────────┐
│ Inbox      │  ┌─[doc toolbar]──────────┐ │  ▼ Entities      │
│            │  │ ◀ Shifting Livelihoods │ │  ────────────    │
│ ▼ Shifting │  │   Page 12 of 84   ⤴︎🔍 │ │  👤 Carlos       │
│   Liveli.. │  └────────────────────────┘ │  👤 Andrea T.    │
│  📄 t2020  │                             │  📍 Popayán      │
│   .pdf     │  ┌─[page]──────────────┐    │  🏛 LFH Coop.    │
│   ─ p.1    │  │                     │    │  ★ Concept: gold │
│   ─ p.2    │  │ "Carlos served as   │    │                  │
│   ─ p.3 ●  │  │  alcalde of Popayán │    │  ▼ Claims (3)    │
│   ─ p.4    │  │  during the 1933   ←│    │  ────────────    │
│            │  │  reform period."    │    │  Carlos *served  │
│  Workflows │  │                     │    │   as* alcalde of │
│  KG        │  │  Heirs filed a deed │    │   Popayán        │
│  Activity  │  │  with the new       │    │   p.12 • Fact    │
│            │  │  cooperative…       │    │                  │
│            │  │                     │    │  Heirs *filed* a │
│            │  │     ◀ p.11    p.13 ▶│    │   deed with…     │
│            │  └─────────────────────┘    │   p.12 • Fact    │
│            │                             │                  │
│            │                             │  ▼ Source        │
│            │                             │  ────────────    │
│            │                             │  Shifting Liveli │
│            │                             │  hoods, ch. 3    │
│            │                             │  Sánchez (1933)  │
│            │                             │  [bibtex]        │
└────────────┴─────────────────────────────┴──────────────────┘
```

- Center = real PDF page. Highlighted span (yellow underline arrow) is the source of the currently-selected claim on the right.
- Right pane has three sections (Entities / Claims / Source) collapsible.
- Claims show as compact `S *V* O` rows; tap → highlight the span in the center.
- Entities show as icon chips; tap → filter Claims to that entity.

**Daniel's "never the entire text — just the relevant text":** the PDF page is the entire text by necessity, but **the highlight only marks the relevant span**. We don't quote-replicate the excerpt in the inspector — the click takes you to the page and shows it.

---

## View 2 — Knowledge Graph (library-wide explorer)

```
┌────────────┬─────────────────────────────┬──────────────────┐
│ Library    │  ┌─[viz toolbar]──────────┐ │  Carlos          │
│ Workflows  │  │ ◯ Carlos    ⊞ 🌐 📊 ⫶ │ │  ─────────────   │
│ ▼ KG ●     │  └────────────────────────┘ │  Type: Person    │
│   Entities │                             │  Born: 1887 (?)  │
│   Claims   │   Focus-neighborhood view:  │                  │
│   Sources  │                             │  ▼ Claims (5)    │
│            │            Andrea T.        │  ─────────────   │
│ Activity   │              ●              │  Carlos *served  │
│            │       knows /               │   as* alcalde of │
│            │           /                 │   Popayán        │
│            │   ┌──── Carlos ────┐        │   p.12, doc-1    │
│            │   │served as       │served  │                  │
│            │   │                │ as     │  Carlos *founded*│
│            │   ▼                ▼        │   the gold-mine  │
│            │  Popayán       Cooperative  │   coop, p.5 doc2 │
│            │  (alcalde)                  │                  │
│            │                             │  …               │
│            │                             │                  │
│            │  [filter ▾ ☑ served as      │  ▼ Sources (3)   │
│            │           ☑ founded          │  ─────────────   │
│            │           ☐ knows]          │  doc-1 p.12      │
│            │                             │  doc-2 p.5       │
│            │                             │  doc-3 p.12      │
└────────────┴─────────────────────────────┴──────────────────┘
```

- Center = focus-neighborhood graph. Carlos in middle, ~5–10 neighbors, **labeled edges**.
- Click an edge → jumps to that claim's source page in a new tab/split (View 4).
- Click a neighbor → it becomes the new focus.
- Predicate filter on the bottom (checkbox per verb) — like Tinderbox Hyperbolic.
- Inspector on the right shows the focus entity's full details + claims + every source it appears in.

---

## View 3 — Claim card (right-pane component, used everywhere)

```
┌────────────────────────────────────────┐
│ Carlos *served as* alcalde of Popayán  │   ← S-V-O sentence, V italic
│ 📄 Shifting Livelihoods · p.12         │   ← tap → opens source w/ highlight
│ [Fact] [Confirmed]                     │   ← claim_type + epistemic_status
│                                    ▾   │   ← expand for excerpt + analysis
└────────────────────────────────────────┘
```

Expanded:

```
┌────────────────────────────────────────┐
│ Carlos *served as* alcalde of Popayán  │
│ 📄 Shifting Livelihoods · p.12         │
│ [Fact] [Confirmed]                ▴    │
│ ────────────────────────────────────── │
│ "Carlos served as alcalde of Popayán   │
│  during the 1933 reform period…"       │   ← verbatim excerpt
│ ────────────────────────────────────── │
│ Related: 2 claims, 1 contradiction     │   ← inline KG-analysis surface
│   • Heirs filed deed (1933) [doc-1]    │
│   • ⚠ Sánchez disputes term length     │
└────────────────────────────────────────┘
```

The "Related" section is the existing contradiction + evidence-chain pulled inline — was already wired, just visible only when expanded.

---

## View 4 — Source preview with related-claims sidecar (the key one)

When you click a source from a claim card or a graph edge:

```
┌────────────┬─────────────────────────────┬──────────────────┐
│ KG (last)  │  ┌─[source toolbar]───────┐ │  ▼ Active Claim  │
│            │  │ ◀ Carlos ⤴︎ Shifting…  │ │  ─────────────   │
│            │  │   Page 12       🔍 ✕   │ │  Carlos *served  │
│            │  └────────────────────────┘ │   as* alcalde of │
│            │                             │   Popayán        │
│            │  ┌─[page]──────────────┐    │   p.12           │
│            │  │                     │    │                  │
│            │  │ "Carlos served as   │    │  ▼ On this page  │
│            │  │  alcalde of Popayán │ ●  │  ─────────────   │
│            │  │  during the 1933    │    │  Carlos *served  │
│            │  │  reform period."    │    │   as* alcalde… ←│
│            │  │                     │    │  Heirs *filed* a │
│            │  │  "Heirs filed a     │    │   deed (1933)    │
│            │  │  deed with the new  │ ●  │  LFH Cooperative │
│            │  │  cooperative…"      │    │   *was* founded… │
│            │  │                     │    │                  │
│            │  └─────────────────────┘    │  ▼ Related       │
│            │                             │  ─────────────   │
│            │                             │  Sánchez (1955)  │
│            │                             │   disputes term  │
│            │                             │   length         │
│            │                             │                  │
│            │                             │  ▼ Entities here │
│            │                             │  ─────────────   │
│            │                             │  Carlos · Popa.. │
│            │                             │  · LFH Coop · …  │
└────────────┴─────────────────────────────┴──────────────────┘
```

Highlights: every claim that quotes from this page shows up as a tappable underline (●). Inspector right shows:

1. **Active Claim** — the one you clicked to get here, in full.
2. **On this page** — every other claim extracted from this same page (the "related items when we go to a source" Daniel asked for).
3. **Related** — claims from other docs that link to this one via KG (contradictions, evidence chain, similar claims via PyKEEN/vector).
4. **Entities here** — the entity chips for this page, tappable to refocus.

A **back button** at top-left returns you to wherever you came from (KG graph, entity detail, library list).

---

## Component reuse

| Component | Used in |
|---|---|
| ClaimCard | View 1 right pane, View 2 right pane, View 3, View 4 "Active/On this page/Related" |
| EntityChip | View 1 entities section, View 2 inspector header, View 4 entities-here |
| SourceBadge | inline on every claim card |
| HighlightedPagePreview | View 1 center, View 4 center |
| FocusNeighborhoodGraph | View 2 center |

Everything composes — same data, three layouts.

---

## What this maps to in the existing codebase

- **DocumentInspector** = the right pane in View 1. Today: tabs (Info/Content/Metadata/Artifacts). New: collapse the tabs, replace with Entities + Claims + Source sections (always visible, scrollable).
- **OntologyBrowser** = View 2. Today: list/graph/chart segmented in center pane. New: graph is dominant; List becomes an inspector affordance ("show all entities" sheet); Chart goes into a "Library stats" sheet.
- **A new SourcePreviewView** = View 4 center. Today: PDFPageView exists but doesn't take claim-highlight inputs. New: takes a `[ClaimHighlight]` array, renders underline markers per `source_char_start/end` (text docs) or `source_bbox` (PDFs).
- **A new ClaimNavigation router** — handles `ficheroOpenClaimSource` and navigates to the source doc + page + highlight. Sets `documentStore.selectedDocument` + scrolls the PDF + decorates with highlights.

---

## The smallest first step

**Wire the source navigation that's already half-built.**

The new `ficheroOpenClaimSource` notification (shipped in `39e7ed5d`) carries everything needed — `documentId`, `pageLabel`, `charStart/End`, `claimId`. ContentView listens, calls `selectDocument(documentId)`, scrolls the PDFView to `pageLabel`, decorates the page with a highlight rect from `source_bbox` (or `charStart/End` projected via PyMuPDF on the backend).

That single wire-up makes claim cards actionable in View 1 today. No new viz required.

Stage 2.1 — claim card source-doc navigation — is the next 30 min of work.

---

## Issues to file from this wireframe pass

- **Source preview with claim highlight overlay** — the SourcePreviewView component. Big — covers PDF / text / image. (Issue not yet filed.)
- **"On this page" claim list** — query by document_id + page_label. Backend endpoint exists; need the inspector section. (Folds into #982 / #986 expand.)
- **"Related when at a source" surface** — feeds from the KG (contradictions, evidence-chain, PyKEEN suggestions, vector similar). Combines existing endpoints; no new backend.
- **Three-column layout** as the canonical app shape, not a per-destination choice. (#985 / #980 expand.)
- **Highlight markers on PDFView** — extends PDFPageView with overlay annotations. Needs PDFKit annotation work. Medium.

---

## Open questions for Daniel — my recommended defaults

I'm going to default to these unless you say otherwise. Each carries a reason; redirect any of them.

### Q1. Three-column canonical?

**Default: yes — three columns everywhere.** `Nav + Center + Inspector`.

- Library = Nav + Source preview + Source/Claim/Entity inspector
- KG = Nav + Focus graph + Entity/Claims/Source inspector
- Workflows = Nav + Workflow canvas + Run/Activity inspector
- Activity = Nav + Run log + Run-detail inspector
- Chat = Nav + Conversation + Cite/Context inspector

The user's eye lands on "Center is the thing I'm doing; Inspector is *about* the thing I'm doing." Consistent across destinations.

Counter-argument (we should hold open): some destinations (Settings, Welcome, AddProvider) genuinely don't need an inspector and forcing three-column wastes pixels. Solution: the inspector pane is **collapsible globally** via `⌥⌘0` (same Apple convention as Xcode); destinations with no inspector content render an empty state ("No inspector for this view") or hide automatically.

### Q2. Tabs vs sections in the right inspector?

**Default: sections, not tabs.** A single scrollable inspector with collapsible sections.

Today the DocumentInspector has tabs (Info / Content / Metadata / Artifacts). The tabs were a workaround for "too much data, not enough vertical space." But you can't see Claims + Source + Artifacts at the same time, which is exactly what Daniel asked for. Sections solve that — collapsed by default, the user expands the ones they care about, persistence remembers which were expanded last time.

Section list (top-to-bottom default order for a Library doc):

1. **Header** — name, type chip, status pill, primary action (open source, run workflow)
2. **Entities** — chips, collapsed by default after 8
3. **Claims** — claim cards with S-V-O + source link, filterable by status/kind chip row at the top
4. **Source** — bibtex-style citation, file path, ingest mode, sources cited by this doc / cited by other docs (#974)
5. **Artifacts** — Catalogue, Transcription, Keywords, Tables, Slide text (existing inspector V2 collapsed into a section)
6. **Display attributes** — type / file / size / created / modified (today's "Info" tab content)
7. **Related claims (KG-RAG)** — similar claims library-wide (#959 — already shipped, just relocate)

Same sections work for entity detail in the KG view, just with different content density: Header + Entities-related-to-this-one + Claims + Sources-where-this-appears + Curation history.

### Q3. Entity list location when graph mode is dominant?

**Default: inspector header has a search field that filters the graph; full list is a sheet.**

Reasoning: in the KG explorer (View 2), the user wants the graph to dominate the center. A persistent left entity list (today's layout) costs ⅓ of the window. Replace with:

- **Search field** in the inspector header — types narrow the graph's focus (`onSubmit` recenters on the top hit; `onChange` filters by name match).
- **"Show all entities…" button** → opens a sheet with the full list, kind chips, sort, multi-select for "filter graph to these N entities."
- **Browse-by-kind** chips at the top of the graph viewport — click "People" and graph fades all non-people nodes.

This keeps the inspector tight + the graph large + still has the list when the user wants it.

### Q4. Bibtex / citation auto-pull?

**Default: try once on ingest; show "regenerate" + edit affordances in the inspector.**

The bibliography extractor (in `~/code/bibliography_extractor`) runs once at ingest and writes results to the new bibliography metadata fields (the methods I shipped today wire the read side). The Source section in the inspector shows:

- Formatted citation block (Chicago / APA toggle in section header)
- Raw bibtex (collapsed)
- "Re-extract" button (calls `runBibliographyExtractor` per #984)
- "Edit" button (PATCH via `patchBibliographyMetadata`)
- Linked-to-others count (inbound/outbound citation graph from #974)

If no bibtex exists yet (legacy ingest), the Source section shows just the file path + an "Extract bibliography" CTA.

---

## Five more wireframes (filling out the consistency story)

### View 5 — Library list (no doc selected)

```
┌────────────┬─────────────────────────────┬──────────────────┐
│ ▼ Library  │  ┌─[lib toolbar]──────────┐ │  Library Stats   │
│   Inbox    │  │ ◇ Shifting Liveli.  ⊞⊟│ │  ─────────────   │
│ ▼ Shifting │  │   84 docs · 156 ent.   │ │  84 documents    │
│   Liveli.. │  └────────────────────────┘ │  156 entities    │
│  ─ p1      │                             │  812 claims      │
│  ─ p2      │  ┌─[grid]─────────────────┐ │  3 contradictions│
│            │  │ ┌──┐ ┌──┐ ┌──┐ ┌──┐    │ │                  │
│ Workflows  │  │ │📄│ │📄│ │📄│ │📄│    │ │  ▼ Activity      │
│ KG         │  │ └──┘ └──┘ └──┘ └──┘    │ │  ─────────────   │
│ Activity   │  │  t   t2  t3  t4         │ │  Catalogue last  │
│            │  │                         │ │   ran 2hr ago    │
│            │  │ ┌──┐ ┌──┐ ┌──┐ ┌──┐    │ │  47 docs done    │
│            │  │ │📄│ │📄│ │📄│ │📄│    │ │  · 3 errors      │
│            │  │ └──┘ └──┘ └──┘ └──┘    │ │                  │
│            │  │  …                      │ │  ▼ Pinned        │
│            │  └─────────────────────────┘ │  ─────────────   │
│            │                             │  ★ t2020 p.12    │
│            │                             │  ★ Carlos        │
│            │                             │  ★ "served as     │
│            │                             │   alcalde"        │
└────────────┴─────────────────────────────┴──────────────────┘
```

- No doc selected → inspector shows **Library Stats** + recent **Activity** + **Pinned** items (docs / entities / claims the user starred).
- Click a doc card → transitions to View 1 (single doc reading).

### View 6 — Workflows (the existing surface, in consistent shape)

```
┌────────────┬─────────────────────────────┬──────────────────┐
│ Library    │  ┌─[wf toolbar]───────────┐ │  ▼ Workflow      │
│ ▼ Workflows│  │ Catalogue · Editing   ▶│ │  ─────────────   │
│   Catalog.●│  └────────────────────────┘ │  Name: Catalogue │
│   NER      │                             │  Last run: 2hr   │
│   Spanish  │  ┌─[canvas]───────────────┐ │   ago · 47 docs  │
│   Trans.   │  │ ●─Files                │ │                  │
│   Catalog. │  │   │                    │ │  ▼ Inputs        │
│   (mixed)  │  │   ▼                    │ │  ─────────────   │
│            │  │ ●─Extract All          │ │  Selected docs:  │
│ KG         │  │   │                    │ │   · t2020.pdf    │
│ Activity   │  │   ▼                    │ │   · t2021.pdf    │
│            │  │ ●─Catalogue            │ │                  │
│            │  │   │                    │ │  ▼ Tools         │
│            │  │   ▼                    │ │  ─────────────   │
│            │  │ ●─Save Artifacts       │ │  [search…]       │
│            │  │                        │ │  Files           │
│            │  │ + add node             │ │  Extract All     │
│            │  └─────────────────────────┘ │  Catalogue       │
│            │                             │  Transcribe      │
│            │                             │  Keywords        │
│            │                             │  …               │
└────────────┴─────────────────────────────┴──────────────────┘
```

The workflow-tool palette moves into the inspector as a section (was a sidebar to the right of the canvas in the current build — see Daniel's screenshot earlier today). Saves the column for canvas use.

### View 7 — Activity (already exists, mapped to the canonical shape)

```
┌────────────┬─────────────────────────────┬──────────────────┐
│ Library    │  ┌─[runs filter]──────────┐ │  ▼ Active Run    │
│ Workflows  │  │ All · Failed · Today  ↻│ │  ─────────────   │
│ KG         │  └────────────────────────┘ │  Catalogue       │
│ ▼ Activity │                             │  Started 13:42   │
│   All      │  ┌─[runs list]────────────┐ │  Status: Running │
│   Pinned   │  │ Catalogue · 47/50  ⟳   │ │   47 / 50 docs   │
│   Failed   │  │ Catalogue · done       │ │  Errors: 3       │
│            │  │ NER       · done       │ │                  │
│            │  │ Transcribe · failed (3)│ │  ▼ Progress      │
│            │  │ …                      │ │  ─────────────   │
│            │  └─────────────────────────┘ │  [progress bars  │
│            │                             │   per file]      │
│            │  ┌─[detail timeline]──────┐ │                  │
│            │  │ ▄▄▄▄▄▄▄▄▄▄░░░░          │ │  ▼ Errors        │
│            │  │ Extract All  Files  …  │ │  ─────────────   │
│            │  └─────────────────────────┘ │  • t-03 line 12 │
│            │                             │  • t-19 OCR fail │
│            │                             │  • t-22 LLM 429  │
└────────────┴─────────────────────────────┴──────────────────┘
```

### View 8 — Chat (KG-RAG, Daniel mentioned this as part of the vision)

```
┌────────────┬─────────────────────────────┬──────────────────┐
│ Library    │  ┌─[chat header]──────────┐ │  ▼ Context Mode  │
│ Workflows  │  │ Chat about Shifting L. │ │  ─────────────   │
│ KG         │  │   GPT-4o ▼   ⚙ ↺      │ │  ◯ Full library  │
│ Activity   │  └────────────────────────┘ │  ● KG-RAG (5)    │
│ ▼ Chat ●   │                             │  ◯ Vector (10)   │
│   Today    │  ┌─[messages]─────────────┐ │  ◯ This doc only │
│   …        │  │ Daniel:                │ │                  │
│            │  │  Who founded the gold- │ │  ▼ Active Claims │
│            │  │  mining cooperative?   │ │  ─────────────   │
│            │  │                        │ │  Carlos *founded*│
│            │  │ Claude:                │ │   LFH Coop  p.5  │
│            │  │  According to ¹ Sánchez│ │  Heirs *filed*…  │
│            │  │  (1933), Carlos        │ │                  │
│            │  │  founded LFH Coop in   │ │  ▼ Sources cited │
│            │  │  Oct 1933.  ² Andrea T │ │  ─────────────   │
│            │  │  later took over (1937)│ │  ¹ Sánchez 1933  │
│            │  │                        │ │  ² Torres notes  │
│            │  │ [send field]      send │ │                  │
│            │  └─────────────────────────┘ │  ▼ Tool calls    │
│            │                             │  ─────────────   │
│            │                             │  /kg/claim-search│
│            │                             │  → 5 claims      │
│            │                             │  /kg/neighborhood│
│            │                             │   → "Carlos"     │
└────────────┴─────────────────────────────┴──────────────────┘
```

Inspector shows: **Context Mode** (which retriever feeds the LLM), **Active Claims** (the claims the LLM has in its context for this turn), **Sources cited** (the docs/pages the active claims point to), **Tool calls** (transparency on what the model called).

Click a footnote in the chat (¹) → highlights the source claim in the inspector + opens View 4 (source preview) in a new tab. The KG is not just an explorer; it's the **citation surface for chat**.

### View 9 — Search (existing surface in canonical shape)

```
┌────────────┬─────────────────────────────┬──────────────────┐
│ Library    │  ┌─[search field]─────────┐ │  ▼ Result Detail │
│ Workflows  │  │ 🔍 "artisanal mining"  │ │  ─────────────   │
│ KG         │  │   ⚙ FTS · vector · KG │ │  Selected:       │
│ Activity   │  └────────────────────────┘ │  t2020 · p.12    │
│ Chat       │                             │  · "Carlos       │
│ ▼ Search ● │  ┌─[results]──────────────┐ │   served as      │
│            │  │ t2020 · p.12 ☆        │ │   alcalde…"      │
│            │  │  "Carlos served as    │ │                  │
│            │  │   alcalde of…"        │ │  ▼ Related       │
│            │  │ [Fact] [doc] [people] │ │  ─────────────   │
│            │  │                       │ │  Andrea T.       │
│            │  │ doc-2 · p.5           │ │   (co-mentioned) │
│            │  │  "The cooperative was │ │  Sánchez 1933    │
│            │  │   founded in 1933…"   │ │   (vector-sim)   │
│            │  │ [Fact] [doc] [event]  │ │                  │
│            │  │                       │ │  ▼ Refine        │
│            │  │ entity: Carlos        │ │  ─────────────   │
│            │  │  Person · 5 claims    │ │  Filter type:    │
│            │  │ [entity] [people]     │ │  ☑ doc           │
│            │  │                       │ │  ☑ claim         │
│            │  │ …                     │ │  ☑ entity        │
│            │  └────────────────────────┘ │  ☑ source        │
└────────────┴─────────────────────────────┴──────────────────┘
```

Search is unified — documents, claims, entities, sources all in one ranked list. The toggle row in the search field lets the user weight which channel matters (FTS vs vector vs KG-structural). Inspector shows the selected result + related items (the KG cross-links).

---

## Small-component wireframes

### Focus-neighborhood graph (View 2 center, detail)

```
                    Andrea Torres
                          ●
                       /
                  knows
                     /
                    /
   "Coop"  founded                       served    Popayán
        ● ◀──────────  Carlos  ──────────▶  ●
                       ◯                  (alcalde)
                      /  \\
                     /    \\
                "was"  "advised"
                   /        \\
                  ▼          ▼
              "in 1887"   J. Sánchez
              (literal)        ●

  [filter ▾]  ☑ knows   ☑ founded   ☑ served as   ☐ was   ☑ advised
              ↑ uncheck → fade those edges + their literal-only neighbors
```

- Focus node ◯ visually larger + accent ring.
- Entity neighbors ●; literal-only object nodes (square or rounded square shape — visually distinct from entities).
- Edge labels mid-arrow, predicate name; click an edge → opens the source claim in View 4.
- Predicate filter checkboxes at the bottom (Tinderbox-style). Uncheck → those edges fade to 20% opacity, literal-only nodes whose only edges are now hidden also fade.
- Hover an edge → tooltip shows the full claim sentence + source citation.
- Hover a node → label highlights, neighbors un-faded.
- Double-click a node → it becomes the new focus, re-fetch via `/api/kg/graph/neighborhood/{new-id}`.

### Claim card (compact + expanded states, refined)

```
Compact:
┌──────────────────────────────────────────┐
│ Carlos *served as* alcalde of Popayán    │
│ 📄 Shifting Livelihoods · p.12     [▾]   │
│ [Fact] [Confirmed]    ★ pinned by Daniel │
└──────────────────────────────────────────┘
         ▲                          ▲
         │                          │
   tap → opens source         tap → expand
   preview (View 4)              drawer

Expanded:
┌──────────────────────────────────────────┐
│ Carlos *served as* alcalde of Popayán    │
│ 📄 Shifting Livelihoods · p.12     [▴]   │
│ [Fact] [Confirmed]                       │
│ ────────────────────────────────────────│
│ Excerpt:                                 │
│ "Carlos served as alcalde of Popayán     │
│  during the 1933 reform period, taking   │
│  over from his uncle…"                   │
│ ────────────────────────────────────────│
│ Related: 2 claims · 1 contradiction      │
│  • Heirs filed deed (1933) [doc-1]   ↗   │
│  • ⚠ Sánchez disputes term length ↗      │
│ ────────────────────────────────────────│
│ Toulmin (analytic claims only):          │
│  Grounds: town records 1933              │
│  Warrant: term was 4 years by statute    │
│ ────────────────────────────────────────│
│ Confidence: 0.84 · Curation: unreviewed  │
│ [⏵ Open source]  [✎ Edit]  [⌧ Delete]    │
└──────────────────────────────────────────┘
```

### Source preview with highlight overlay (View 4 detail)

```
┌──────────────────────────────────────────┐
│ ◀ Back to Carlos          ⤴ Open original│
│ Shifting Livelihoods  ·  p.12      🔍    │
├──────────────────────────────────────────┤
│                                          │
│  Page 12 (PDF render)                    │
│                                          │
│  Lorem ipsum dolor sit amet, consect-    │
│  etur adipiscing elit. Carlos served as  │
│  ████████████████████████████████████    │ ← yellow underline,
│  alcalde of Popayán during the 1933      │   the active claim
│  reform period, taking over from his     │
│  uncle. Heirs filed a deed with the new  │
│  ████████████████ cooperative shortly    │ ← darker, another claim
│  after, citing economic pressure from    │   on this same page
│  the gold-mining boom.                   │
│                                          │
│  …                                       │
│                                          │
│        ◀ p.11        p.12 / 84      p.13 ▶│
└──────────────────────────────────────────┘
```

- The **active claim's** span is highlighted brightest (the one the user clicked).
- Other claims sourced from the same page get a fainter underline → tap one → that claim becomes active + scroll into view if off-screen.
- Hover a highlight → tooltip with the claim's S-V-O.
- Active claim's span auto-scrolls into the viewport on open.

### Entity card (the right pane in View 2, detail)

```
┌──────────────────────────────────────────┐
│ 👤 Carlos             [✎ Edit]  [⊕ Merge]│
│ Person                                   │
│ Aliases: J. Carlos · Carlos Restrepo     │
│                                          │
│ Description: Born 1887, served as        │
│ alcalde of Popayán 1933–1937. Founded    │
│ the LFH Cooperative.                     │
│ ──────────────────────────────────────── │
│ ▼ Claims (5)            [filter: all ▾] │
│ ──────────────────────────────────────── │
│ [claim card] [claim card] [claim card]   │
│ …                                        │
│ ──────────────────────────────────────── │
│ ▼ Related entities (top by Jaccard)      │
│ ──────────────────────────────────────── │
│ 👤 Andrea Torres · 0.42                  │
│ 📍 Popayán · 0.38                        │
│ 🏛 LFH Coop · 0.31                       │
│ …                                        │
│ ──────────────────────────────────────── │
│ ▼ Sources mentioning Carlos              │
│ ──────────────────────────────────────── │
│ 📄 Sánchez 1933 (3 claims) · p.12 · p.13│
│ 📄 Torres notes (1 claim) · p.5         │
│ ──────────────────────────────────────── │
│ ▼ Curation history (collapsed)           │
└──────────────────────────────────────────┘
```

---

## States — empty / loading / error

| State | View | What to show |
|---|---|---|
| Empty library | View 1 / 5 | "Drop documents here or click + to import" + onboarding hint |
| Empty KG | View 2 | "Run Catalogue to build the KG" + button that triggers the default workflow |
| Loading neighborhood | View 2 | Centered focus node + skeleton ring of 6 pending neighbor circles + "Loading 1-hop neighborhood…" |
| Loading source preview | View 4 | PDF skeleton + "Locating span on p.12…" while the backend resolves char_start/end to page coordinates |
| No bib | View 1 inspector Source section | File path + "Extract bibliography" CTA |
| Stale PyKEEN | View 2 inspector | "Predictions last trained 4 hours ago. Re-train?" inline link |
| SVO missing on claim | claim card | "No subject-verb-object — regenerate KG?" + button (already shipped) |
| Source highlight missing | View 4 | Page renders; soft banner "Couldn't locate the exact span — showing the page" |
| Network error | any | inline "Backend unreachable" + retry, NOT a modal alert |

---

## Interaction flows — the canonical paths

### Path A — "I'm reading a doc and want to follow a claim"

1. View 1, claim card in the right inspector.
2. Click claim → already on this doc, scroll center to the highlighted span (no destination change).
3. Click `📄 source` link on the card → if claim came from a different doc, transitions to View 1 of THAT doc with the highlight active.

### Path B — "I'm exploring the KG and want to find the source of a claim"

1. View 2, see an edge labeled "served as" between Carlos and Popayán.
2. Click the edge → posts `ficheroOpenClaimSource` with documentId + page + char_start/end + claim_id.
3. ContentView listens → selects the doc → transitions to View 4 (source preview).
4. Back button (top-left of View 4) → returns to View 2 with focus still on Carlos.

### Path C — "I'm in chat and want to verify a citation"

1. View 8, Claude responds with footnote ¹.
2. Click ¹ → footnote highlights in the inspector (Active Claims section).
3. Click the claim in the inspector → opens View 4 (source preview) with span highlighted, in a new tab so chat is preserved.
4. Back button → returns to the chat tab.

### Path D — "I'm at a source and want to know what else this page talks about"

1. View 4, looking at a highlighted span.
2. Right inspector "On this page" section lists all claims extracted from this page.
3. Click another claim → its span lights up + the inspector's "Active Claim" updates.
4. "Related" section shows cross-doc claims via KG (contradictions, evidence chain, vector-similar).

### Path E — "I want to ask the KG a question (SPARQL)"

1. View 2, top-right ⫶ menu → "Run SPARQL query…"
2. Sheet opens with a query editor + sample queries.
3. Submit → results render as a table (entity URI columns become tappable links → View 2 with that entity as focus).

---

## How the new design closes today's open bugs

| Bug | What this design fixes |
|---|---|
| #976 graph crash + co-occurrence is wrong model | View 2's focus-neighborhood + neighborhood endpoint (shipped today) replaces global force-directed; edges carry SVO from claim.metadata |
| #977 labels overlap into blob | Focus mode renders ≤30 nodes; labels visible only on focus + top-degree; hover for others |
| #978 list-mode S+P-without-O + missing description + source | Claim card SVO rendering (shipped today); entity card description (View entity card); source citation on every claim card |
| #979 claim card density + chip clarity | Expanded drawer collapses; status/kind chips become real filter bar on the Claims section header |
| #980 HSplitView width wrong | Three-column canonical layout, single @SceneStorage key |
| #981 redundant toolbar header + entity list anchors left | Drop the redundant text; entity list moves to inspector search field |
| #982 center=source, KG=inspector | This entire wireframe IS that architecture |
| #983 master plan | Wireframe IS the staged plan, made concrete |
| #984 promote SVO to top-level | Frontend reads from metadata today; #984 is the typed-field follow-up |
| #985 list-column width consistency | Three-column canonical + shared @SceneStorage |
| #986 entity detail no inspector + alias dup + garbled excerpt | View entity card has inspector affordances; alias normalization is a backend fix (filed separately) |
| #989 reconstructed-paragraph view | Entity card's "Description" field + a future "Compose biography" action that turns claims into prose |

---

## Phase plan revised against the wireframes

### Phase 1 (DONE today) — backend endpoints
✅ Stage 1a/b/c. `GET /api/kg/graph/neighborhood/{id}`, `POST /api/kg/sparql`, `/pagerank /communities /similar /components /triangles /clustering`.

### Phase 2 (in progress) — claim card consumes SVO
✅ Partial. SPO rendering + source-doc citation done. Remaining: wire `ficheroOpenClaimSource` listener in ContentView to navigate to the source doc with `pageLabel` + `charStart/End`.

### Phase 3 — three-column canonical layout
- `PaneThreeColumn` wrapper view (Nav + Center + Inspector).
- All four primary destinations adopt it (Library, KG, Workflows, Activity).
- `@SceneStorage` key `window.inspectorWidth` for the inspector column.
- `⌥⌘0` toggle hides/shows inspector globally.

### Phase 4 — source preview with highlights
- `SourcePreviewView` component takes `[ClaimHighlight]`.
- PDFKit overlay annotations for PDFs; `NSAttributedString` ranges for text.
- "On this page" + "Related" sections in the inspector.
- `ficheroOpenClaimSource` consumer.

### Phase 5 — focus-neighborhood viz
- Rewrites `ForceDirectedGraphView` as `FocusNeighborhoodView`.
- Consumes `/api/kg/graph/neighborhood/{id}` (shipped).
- Predicate filter checkboxes.
- Click-edge → posts `ficheroOpenClaimSource`.
- Double-click-node → refocus.

### Phase 6 — inspector reorg
- Collapse DocumentInspector tabs into scrollable sections.
- Same shell hosts entity inspector (KG view), workflow inspector, activity inspector.
- Inspector section state persisted per destination via `@SceneStorage`.

### Phase 7 — chat KG-RAG
- Context Mode selector on Chat inspector.
- Tool-call transparency in the inspector.
- Footnotes in messages → tap → highlight in inspector + open source in new tab.

### Phase 8 — search unification
- Single search field with FTS / vector / KG weight toggles.
- Results blend docs, claims, entities, sources.
- Inspector shows selected result + cross-links.

---

## Decision points still open

Picking these defaults unless you redirect:

1. **Inspector default width** → 360pt (slightly wider than today's 320pt; claim cards need room).
2. **Section persistence** → expanded/collapsed state per destination, not global.
3. **Highlight color** → accent color at 35% alpha for active; 15% for others on the same page.
4. **Back-button stack depth** → up to 10; older entries drop off (avoid memory leak on long navigation chains).
5. **PDF highlight rendering** → PDFKit annotations (native, prints with the doc) rather than overlay views (faster but ephemeral).
6. **Predicate filter UI** → checkboxes (Tinderbox style, multi-select); not a single-select picker.
7. **First view on app open** → resume last-active destination + selection (via `@SceneStorage`); if first launch, Library list.

---

## Naming — the conceptual rename

To match Daniel's clarification ("entities aren't the KG; the KG is claims") and the wireframe shape:

| Today | New | Why |
|---|---|---|
| "Knowledge Graph" sidebar entry | **"Graph"** | shorter, matches the icon |
| OntologyBrowser title bar text | (drop entirely, #981) | redundant with sidebar |
| "Entities" tab in inspector | **"Entities"** section | unchanged label, new container |
| (no current claims tab) | **"Claims"** section in DocumentInspector | new, per #979 |
| "Related Claims" Info-tab section | **"Similar Claims"** section | clearer — vector-similar, not graph-related |
| "Citations" Info-tab section | **"Sources"** section | matches the wireframe's third column section name |
| Entity card description | **"About"** | reads better as a header than "Description" |
| "Force-directed graph" mode | **"Focus"** view | matches what it does (focus + neighborhood, not whole graph) |
| "Chart" mode | **"Stats"** view | matches what it shows (kind distribution, not a real chart of relationships) |

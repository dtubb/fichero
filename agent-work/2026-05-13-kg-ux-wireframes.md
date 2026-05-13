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

## Open questions for Daniel

1. **Three-column canonical** — make Library + KG both use the same `Nav + Source + Inspector` shape? Or keep one-column-per-destination as today?
2. **Tabs vs sections in the right inspector** — collapse the existing Info / Content / Metadata / Artifacts tabs into one scrollable inspector with collapsible sections (matching this wireframe), or keep tabs?
3. **Where does the LIST of entities live** when graph mode is dominant in KG? Keep the searchable entity list as an inspector section that filters the graph? Or as a sheet?
4. **Bibtex / citation in the Source section** — pull from `bibliography` route automatically when the doc has metadata? Or surface "no bib yet — extract?" CTA?

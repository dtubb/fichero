# Segment Representations — Design Spec (#4635 · epic #4639)

> Milestone: segment-representations
> Manual: TBD — pairs with the archival-data-model section: a reader needs to be told that one
> patch of a page can carry several readings (the OCR's, the VLM's, their own correction), how to
> see them side by side, and which one counts as the transcription.
>
> Design-led (Testing Constitution). The Fichero creative director owns this intent;
> tests enforce it; code makes them pass. One line per behavior, each cited by its
> pinning test. **Status: DRAFT — awaiting creative-director approval before tests/code.**
> Tags: [OK] today · [MISSING] not built · [PARTIAL] exists elsewhere, not wired.

## Intent (the design)

A **segment** is one anchor — a region/line/word/polygon on a page. It does not hold a
single thing; it holds **versioned collections**: many transcriptions and many
representations, each with its own provenance and version. This spec covers the
**read model** — how a segment and its representations are produced, stored, served, and
handed to a consumer (a person, an AI, a search index, an exporter). It is the first
**vertical slice** that proves the whole archival-model spine end to end.

### The data shape (from #4635 / #4639)

```
Segment (anchor: geometry + page + layer + reading-order)
  ├─ Transcription[]   each { text, language, script, edition, version, provenance }
  ├─ Representation[]   each { kind, version, provenance, payload-ref }
  ├─ language/script    segment DEFAULT (a transcription may override)
  └─ export map         → ALTO / PageXML / TEI / JSON-LD / Linked Art
```

`Representation.kind` ∈ { `image-crop`, `text`, `tokens`, `image-vector`, `text-vector`,
… (extensible: glyph-rep for no-Unicode scripts, layout-features) }. Representations are
**append-only**: a re-crop or a new embedding model makes a new *version*; the old is
retained. Language/script live on the **Transcription**, not only the Segment (bilingual
gloss = two transcriptions on one segment; graphemic vs normalized = two transcriptions).

### The delivery contract (the cross-surface invariant, made concrete)

A capability is **DONE only across the whole spine**:

**backend → inspector (front end) → AI/MCP/CLI → tested → exportable.**

Backend row alone = not done. UX without MCP/CLI = not done. Untested = not done. Not
exportable = not done. Every behavior below names which spine segment it lands on.

## Behaviors

### A. Backend — the read model
- `segment.read.list` [PARTIAL] (#4762) — list a document/page's segments (anchor + defaults);
  builds on the Kraken segmenter that already persists baseline geometry.
- `segment.read.representations` [MISSING] (#4763) — for one segment, return its available
  representations (kind + version + provenance), lazily producing the cheap ones
  (`image-crop` via existing `_segment_image`; `text` from its transcription).
- `segment.read.transcriptions` [MISSING] (#4764) — a segment's transcriptions, each carrying
  language/script/edition/version, newest-version resolvable.
- `segment.rep.versioned` — a new crop / new embedding is a NEW version; prior versions
  are never overwritten (provenance/version slot at finest grain).
- `segment.rep.honest-absence` — a representation that hasn't been produced is reported as
  absent, never faked (no empty vector, no placeholder crop). (Ties: prefer-raise.)

### B. Front end — the inspector
- `segment.inspector.shows-representations` [MISSING] (#4765) — selecting a segment in the
  inspector shows its representations (the crop image, the text, which vectors exist) and
  its transcriptions (with language/script/edition badges).
- `segment.inspector.source-anchor` — the crop and text resolve to the same on-page
  anchor as everything else (reuse the F5 `ClaimSourceRequest` invariant seam).
- `segment.provenance.derived-from-split-page` — **[GAP]** (#1647) when a scanned page is
  split into two logical pages (a left/right facing-page split), each resulting page's
  segments must trace `derived_from` back to the ORIGINAL scan, not just to the split
  half — so a segment's anchor/provenance chain survives a page-split the same way it
  survives any other derived representation. Includes map-region support (a segment whose
  source is a map, not running text, still anchors to a region of the original scan).
- `segment.inspector.version-visible` — when a representation has multiple versions, the
  inspector shows which version is current and that older ones exist.
- `segment.overlay.recognized-text-regions` — **[GAP]** (#4418, redirected from the legacy
  "Preview - Image Editing" milestone while folding `preview-image-editing.md`'s pass 2) the
  Preview should overlay recognized text regions on BOTH images and PDFs, toggleable and off
  by default. A PDF with a text layer needs no recognition model at all — PyMuPDF's
  `get_text()` already returns per-word/block bounding rectangles "for free," and the loader
  today discards them, keeping only the flat string. Every region must be stored NORMALIZED
  and page-relative (never in one rendition's raw pixels, since a page has several
  renditions — original, enhanced, deskewed, split) and must record its OWN provenance (PDF
  text layer, a model, or a human correction) — this spec's own segment/representation model,
  not a new one. Selecting a region selects its text and vice versa, through the SAME cursor
  `reader-overlay-frame-identity.md` and `kg-entity-inspector.md`'s `ClaimSourceRequest` seam
  already use — explicitly not a third addressing scheme. Not verified as built.

### C. AI / MCP / CLI — made available to an agent
- `segment.mcp.get` [MISSING] (#4766) — an MCP tool returns a segment with requested
  representations (`image+text`, or `vector`, or `text`→for-export). An AI can be *given*
  "these segments with their images" in one call.
- `segment.cli.get` [MISSING] (#4767) — the same over the CLI (never curl/DuckDB direct).
- `segment.access.consumer-chooses` — the consumer names which representations it wants;
  the server produces/returns only those (an index wants vectors, an agent wants
  image+text, an exporter wants text).

### D. Tests (the pinning layer — this is what makes it real)
- `segment.test.rep-roundtrip` — produce → store → read back a representation; version
  bump retains the prior; absent kind reads as absent.
- `segment.test.transcription-language` — two transcriptions on one segment with different
  language/script both resolve; the segment default doesn't clobber a transcription's own.
- `segment.test.cross-surface` (HARD-GATE) — the same segment yields the same anchor +
  same text from backend, MCP, and CLI (the invariant the constitution requires).
- `segment.test.resource-safety` — vector/crop production is bounded and does not peg the
  machine (Article 4 resource-safety).

### E. Export
- `segment.export.map` [MISSING] — a segment's transcription serializes to at least one
  standard (ALTO or PageXML) with its anchor geometry intact; the export map slot is real,
  not aspirational. (This is one slice of the broader, cross-cutting Exporter Manager
  epic, → #4640 — not segment-representations-only work.)

## The first slice (slice-0, smallest honest end-to-end)

Prove the spine with the two **cheapest** representations on **existing** data:

1. **backend** `segment.read.representations` returning `image-crop` (existing
   `_segment_image`) + `text` (existing transcription) for a segment — read-only.
2. **inspector** `segment.inspector.shows-representations` — the crop + text, anchored.
3. **MCP + CLI** `segment.mcp.get` / `segment.cli.get` for `image+text`.
4. **tests** `rep-roundtrip` + `cross-surface` (HARD-GATE).
5. **export** `segment.export.map` to ALTO for that segment.

No new embedding models, no new schema beyond a representations read-view over what the
segmenter already persists. Vectors/tokens/vers’d re-crops are the next slice, once
slice-0 proves the pattern and the creative director approves.

## Open questions for the creative director
- Where do representations physically live — derivative files next to the page (like the
  existing `_segment_image` derivatives), a table, or both (file payload + metadata row)?
- Is `Transcription` a first-class record now, or does slice-0 read the existing
  transcription text and defer the multi-edition table to #4638?
- Which standard is the slice-0 export target — ALTO (line/word geometry) or PageXML?

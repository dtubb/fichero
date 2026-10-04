# Segment Representations — Design Spec (#4635 · epic #4639)

> **2026-09-19 — read this first.** The shared ideas in this file (what a segment is, its
> slots, the delivery rule) now have one home: `source-model.md` and its slices.
> Where this file and that set differ, that set wins. This file stays as the FIRST SLICE (reading a segment's picture and text across the spine). Its "a segment is one anchor" is now "a segment is a record with a lasting id whose place is an anchor"; its "representations" are the source model's "worked-out things" (pictures, vectors, word-level analysis) and "readings". Its `segment.*` ids stay, including its version behaviours. In its data shape below, "layer" now means a **pass** and a transcription's "edition" is a reading's **kind and level**; its open question on the first export target was answered by the rulings of 2026-09-19.
>
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

A **segment** is one anchor (now: a record with a lasting id whose place is an anchor; see the note above) — a region/line/word/polygon on a page. It does not hold a
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
- `segment.overlay.refreshes-when-segmentation-finishes` — **[BROKEN]** (#4890) seen live
  2026-09-19: the maintainer ran Kraken; it produced bounding boxes, but they did not appear on
  screen until he clicked the item — the overlay does not refresh on its own when segmentation
  finishes. **Cause, VERIFIED at the tree (not a hypothesis):** saving an artifact emitted NO
  change event; the run's only event fired on a document STATUS transition and never named an
  artifact. **THE THIRD CLAUSE OF THAT CAUSE WAS WRONG** — see the correction below; the app's
  subscriber existed the whole time. **The engine half is committed,
  193ce62ef**: one `artifact.updated` event per finished run, naming `artifact_ids` and
  `document_ids`, fired whether or not a document's status changed — covers every
  `process_vision` tool. **`align_transcript` is now covered too (2026-09-27), both ways it can
  run**: the on-demand route `POST /api/artifacts/{id}/align-transcript` emits `artifact.updated`
  itself, because no run boundary can cover it — there is no run — and the workflow tool now
  reports its aligned ids under `artifacts`, the one key `collect_created_artifact_ids` reads.
  It had been returning each `artifact_id` inside `documents`, under a name the collector does
  not look at, so the artifacts landed silently. Pinned by
  `test_align_transcript_announces_itself.py` (both ids, fires with no status change, the
  broadcast comes AFTER the save, and a declined alignment broadcasts nothing) and
  `test_align_transcript_reports_its_artifacts.py`.
  **THE APP'S SUBSCRIBER EXISTS AND ALWAYS DID, audited 2026-09-27.** This entry said twice that
  it did not, and that sent every reader looking on the wrong side of the wire.
  `ArtifactEntityStore` conforms to `ChangeEventConsumer` with `changeDomains = ["artifact"]`,
  is registered at `LibraryManager.swift:263`, and bumps a per-document revision for every id in
  `event.documentIds` — deliberately NOT gated on whether it holds a bundle for that document
  (ruling of 2026-09-19, quoted in its own comment: a Preview pane showing document X with no
  Inspector bundle for X would otherwise never refresh). Both overlays observe it through an
  `artifactEntityRevision` folded into their geometry `.task(id:)` — `ZoomableImagePreviewMac`
  for images, `PDFPageWithToolbar` for PDF pages — alongside `FocusedArtifact.shared.id`, so
  either signal re-fires the load.

  **Why the wrong clause looked true for eight days.** The revision path could not fire for
  Kraken, because `align_transcript` reported its ids under a key the collector never read, so
  the event carried none. The CLICK path (`FocusedArtifact`) was the only one that could ever
  work — which is precisely the reported symptom. From outside, "the only thing that refreshes
  the overlay is clicking the item" is indistinguishable from "there is no subscriber". The
  diagnosis was right about the symptom and wrong about which side of the wire held the cause,
  and being wrong in that direction cost more than being vague would have.

  **Tag stays BROKEN**: this was seen fail on a screen, and it is not claimed until the
  maintainer runs Kraken again and the boxes
  appear on their own.
- `segment.kraken.segments-a-pdf-page` — **[PARTIAL]** (#4892) seen live 2026-09-19: the
  maintainer ran Kraken segmentation on one page of a PDF and it failed, while Apple Vision on
  the same page worked. Cause, verified in source: the Kraken branch of the shared vision
  pipeline (`workflows/tools/vision_base.py`) raises "split the PDF into page images first"
  for any file path ending in `.pdf`, and a PDF's page child resolves to the parent PDF's
  file, so every PDF page is refused. The Apple Vision and LLM branches render the page
  themselves. Expected: Kraken segments a PDF page by rendering that page through the SAME
  page-render seam the other vision modes use and segmenting the render; the geometry is
  recorded against the page, and its provenance names the render (page index, resolution).

  **THE ENGINE HALF IS BUILT AND PINNED** (audited 2026-09-27): `vision_base.py` has
  `_render_pdf_page_to_temp_png` and `_KRAKEN_PDF_RENDER_DPI = 300` (matching Apple Vision's,
  so Kraken is not the lower-fidelity render), and
  `fichero-server/tests/unit/workflows/test_kraken_segments_pdf_page.py` pins every clause of
  that expectation rather than the happy path alone: the PDF path is never handed to the
  segmenter, the temp render is cleaned up, the artifact lands on the page AND a separate
  assertion proves it does not land on the parent PDF, the geometry is normalised and so
  independent of the render's pixel size and DPI, and the provenance names the render
  (`metadata["pdf_page_render"] == {"page_index": 0, "dpi": 300}`).

  **[PARTIAL] and not [OK] because this was seen fail on a SCREEN.** A passing engine test is
  not that evidence, and the behaviour is not claimed until the maintainer runs Kraken on a PDF
  page in the app and the boxes appear. If they are produced and appear only after clicking the
  item, that is the overlay behaviour above (#4890) and not this one — two defects on one
  screen.
  No manual split step. Not yet checked: whether the refusal reaches the run log as a
  readable message or only as a failed run.
- `segment.overlay.artifact-event-covers-every-write-tool` — **[OK]** (→ #4890) every tool that
  writes an artifact announces it, so an overlay subscriber is not correct for some tools and
  silently stale for others.
  **There are TWO ways to be covered, and this entry's list was wrong twice for not saying so.**
  A tool either reports its ids under the `artifacts` key, which the run boundary's
  `collect_created_artifact_ids` reads and broadcasts, **or** it emits mid-run itself through
  `emit_workflow_artifact_changes`. Both are real coverage; the entry had been written from which
  TOOL the original fix was tested against (`process_vision`), so it named as gaps first three
  tools that report the key (`merge_geometry`, `similarity`, `catalogue`) and then three more that
  emit directly (`extract_all`, `extractors`, `import_artifacts`).
  **Two were genuinely uncovered and were fixed on 2026-09-27**, each needing more than a key
  because neither captured an artifact id at all:
  `date_extract` — which already announced the DOCUMENTS whose date columns moved and said nothing
  about the `dates` artifacts beside them — now records both save sites' ids and emits separately,
  deliberately not folded into the document emit, because a page whose columns did not move still
  gets a new artifact and folding them would rebuild this defect's own cause in a new place; and
  `cleanup`, whose `<key>_clean` replacement now announces itself from inside `_replace_artifact`,
  the one helper both call sites use, and stays silent when the save failed. Pinned by
  `test_date_and_cleanup_artifacts_announce_themselves.py`.
  **`artifact.created` and `artifact.updated` are ONE signal**, which is why the two mechanisms
  can use different names: dispatch is by DOMAIN — `ChangeEvent.domain` is the prefix before the
  dot, `LibraryChangeStream` delivers on that, and `ArtifactEntityStore.apply` guards on
  `event.domain == "artifact"` with no verb filter. The run boundary and the alignment route emit
  `updated`; the six mid-run emitters default to `created`.
  **That equivalence is now PINNED** — it holds because dispatch is by domain, and a tidy-up
  narrowing that guard to one verb would silence six emitters while every other test still passed.
  `fichero/Tests/Unit/general/Models/ArtifactEntityStoreTests.swift::testArtifactCreatedBumpsTheRevisionToo`,
  `::testCreatedAndUpdatedAreTheSameSignalForTheSameDocument` (one of each on the same document,
  asserted as a PAIR because the claim is their equivalence and not either alone) and
  `::testAnotherDomainsCreatedEventStillBumpsNothing` (the guard that must not be widened while
  doing the other two — `document.created` is a real event name and the likeliest near miss).

  The sentence this replaces said the equivalence was pinned by nothing and that the cases were
  owed. Replaced rather than deleted, as it asked to be: a spec that records what it is missing
  should be able to record that it stopped missing it, in the same place, so the reason the tests
  exist stays attached to them.
  The engine half is pinned here: `test_align_transcript_announces_itself.py` and
  `test_date_and_cleanup_artifacts_announce_themselves.py`, plus
  `test_align_transcript_reports_its_artifacts.py` for the run-boundary key.

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

## Rulings

- **Ruled 2026-10-04 (design lead, applying the spec's own lean):** a representation is both a
  file payload (like the existing `_segment_image` derivatives) and a metadata row. `Transcription`
  is already first-class: the passes and their readings on segments are the transcription record (`source-model.md`).
- **Answered by what is built (2026-10-04):** ALTO and PAGE XML both export today
  (`fichero_server/api/routes/document/page_export.py`; `formats/alto.py`, `formats/pagexml.py`).

## Open questions for the creative director
None outstanding; all three are answered (see Rulings).
- **Answered** (design lead 2026-10-04, applying the spec's own lean): Both, a file payload and a metadata row. Where do representations physically live?
- **Answered** (source/source-model.md Rulings 2026-09-20): Text lives as readings on segments. Is `Transcription` a first-class record now?
- **Answered** (source/source-model.md Rulings 2026-09-19 item 19): PageXML, TEI and ALTO all first. Which standard is the slice-0 export target?

## Triaged from the backlog (2026-10-04)
- `segment.test.artifact-type-contract-clean` — **[GAP]** (#4910) check_artifact_type_contract passes: entity_merge_proposals is produced and queried by name.

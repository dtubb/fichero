# Revised Search Plan — 2026-08-19

Reconciles Daniel's north-star spec (**#4604** + its multilingual and paleography
comments) against what is actually **BUILT** in `lane/sidebar-ux`.
Working plan; no new issues are filed — every phase references existing issues.

Audit method: engine read directly (file:line cited), Swift surfaces swept by two
read-only explorers, GitHub milestones enumerated with `gh`.

---

## 0. Headline verdict

Search is **much further along than #4604 assumes**, and the two hardest-sounding
asks — the Andagoya heat map and multilingual soundness — are mostly *wiring* and
*precision* problems, not greenfield builds.

- Passage-level embedding with exact char anchors: **BUILT**
  (`db/embeddings.py:301` `split_text_passages`, anchors at `:350`).
- Char-span → page rectangles: **BUILT**, including an HTTP route
  (`media/ocr_geometry.py:676` `region_for_span`; `api/routes/document/artifacts.py:419`
  `GET /{artifact_id}/region`).
- e5 query/passage prefixes (#1795): **BUILT** (`db/embeddings.py:267` `format_for_model`).
- Accent/diacritic folding incl. early-modern Spanish: **BUILT** (`db/__init__.py:352`).
- KG **fusion into ranking** (#1833 item 3): **MISSING** — the graph retriever exists
  but only chat uses it (`retrieval/graph_rag.py:18`; consumers at
  `api/routes/system/chat.py:46`, `workflows/tools/sources.py:24`). `/api/search` only
  *annotates* results with KG ids after ranking (`db/__init__.py:4441`).
- Result → page → highlighted region navigation: **MISSING end-to-end** (the two halves
  exist; nothing joins them).

So the plan is short on new machinery and long on joining what is already there.

---

## 1. What is BUILT (engine)

| Capability | Where | State |
|---|---|---|
| `search()` semantic / fulltext / hybrid legs | `db/__init__.py:4614` | built |
| RRF hybrid fusion, k=60 | `db/__init__.py:4950-4999` | built |
| Passage chunking + char anchors | `db/embeddings.py:301` | built |
| e5 `query:`/`passage:` prefixes | `db/embeddings.py:267` | built (#1795 done) |
| Embedding model | `db/embeddings.py:31` `intfloat/multilingual-e5-large` | built, multilingual |
| Opt-in `BAAI/bge-m3` space | `db/embeddings.py:32`, `FICHERO_EMBED_MODEL` | built |
| Accent/diacritic fold (casefold→NFKD→drop Mn) | `db/__init__.py:352` | built (#4363) |
| Entity alias query expansion | `db/__init__.py:4653` `_expand_query_with_entity_aliases` | built |
| Entity rank bonus | `db/__init__.py:5006` `_entity_bonus_doc_ids` | built |
| Query syntax parser (scopes / phrases / NOT) | `search/query_parser.py` | built |
| NL→structured query compiler (#4116) | `retrieval/query_compiler.py`; gate at `:70` | built, opt-in `compile:` |
| `include=` legs: content, entities, claims, artifacts, interpretations | `api/routes/search/core.py:153` | built (#4118 partly) |
| Coverage stats (embedded docs **of** total) | `db/embeddings.py:573` | built |
| Saved searches CRUD + reorder + duplicate | `api/routes/search/core.py:1584-1880` | built |
| `sort_by: document_date` + JDN range filters | `core.py:765`, `db/__init__.py:5068+` | built (#3322) |
| Search explain / RAG modes | `api/routes/search/explain.py` | built |
| `exclude_from_search` honoured at embed AND query time | `db/__init__.py:4336`, `:4419` | built (#4580 mostly) |
| Char-span → boxes → union rect | `media/ocr_geometry.py:639,665,676` | built |
| Region HTTP route | `api/routes/document/artifacts.py:419` | built |
| Graph-hop KG retriever | `retrieval/graph_rag.py:18` | built — **but not used by search** |

---

## 2. What is MISSING or WRONG (engine) — ranked

**M1. KG/claims never influence ranking (#1833 item 3).**
`enrich_search_results_with_kg` (`db/__init__.py:4441`) attaches matching claim/entity
ids *after* ranking. `GraphAwareRetriever` — which already does seed→graph-hop→claim
expansion — is wired only into chat. The Andagoya golden path ("ranked by relevance
that considers the vector DB, the SVO/claims DB, entities, notes and highlights")
needs those legs fused into the RRF merge, not stapled on afterwards.

**M2. `min_score = 0.55` silently drops keyword-only hits — and the app sends it.**
Route default at `core.py:757`; **the Mac app passes it explicitly** —
`SearchStore.defaultMinScore = 0.55` (`Models/SearchStore.swift:65`, applied at `:102`).
Post-RRF the score is projected as `rrf/(2/61)`, so a document ranked #1 in fulltext but
absent from the semantic list scores exactly **0.50**, plus a `0.1 x normalised-BM25`
nudge (`db/__init__.py:4980`). Only the single top-BM25 document clears 0.55; the #2
keyword-only hit needs roughly >=0.58 relative BM25 to survive. Everything below that is
dropped **before the user ever sees it, with no error** — a confident, wrong, empty
answer. This is a concrete, testable candidate cause for **#4236** ("search returns 0
results for text the Inspector is displaying"): `jemseg` is a rare term that BM25 finds
and the semantic leg, over a page-level noise floor, does not.

The 0.55 floor is not wrong in itself — it was added for a real reason (#1054: an
unthresholded semantic leg returns every page at 42-50 % cosine). The bug is applying
ONE floor to a fused score whose two legs have incompatible geometry. Fix by
thresholding the semantic leg in cosine space (already done pre-RRF) and NOT
re-thresholding the fused RRF projection, or by giving fulltext-only hits their own floor.

**M3. Query syntax does not match the spec.** #4604 asks for
`person:` `place:` `organization:` `entity:` `date:`; the parser implements the
**plural** forms `people:` `places:` `organizations:` `dates:` `events:` `keywords:`
`entities:` `claims:` (`search/query_parser.py:33-37`). Singular aliases are a
five-line fix and must land with the field work or the documented syntax lies.

**M4. Smart routing is classified but not routed.** `looks_like_natural_language`
(`query_compiler.py:70`) already decides question-vs-keyword — in English and Spanish
only. Nothing routes a question to Ask; it only gates LLM compilation
(`core.py:954`). "Construct me a search" has no path at all.

**M5. Per-candidate N+1 and a full-corpus fallback scan.** *(Superseded by the
#4175 read path — see §5. Kept here because it is the measured problem that path solves.)*
`_is_active_document_id` (`db/__init__.py:4419`) does an uncached `self.get(Document, id)`
for **every** candidate row, and candidate count is `max(limit*4, offset+limit*2)`.
Worse, when the Lance FTS leg returns zero hits the code falls back to
`table.to_pandas()` — the whole embeddings table into memory (`db/__init__.py:4800`).
On Marshall-scale corpora (5.3k docs, several passages each) this is the real
scale ceiling. The #4175 spike measured the replacement at 17 ms warm (§5).

**M6. `exclude_from_processing` ≠ `exclude_from_search`.** #4580's engine ask is
essentially done, but under a *different* flag. Daniel's literal question — "if I
exclude from processing via the contextual menu, will it also exclude from search?" —
is still answered **no**, because the context menu he used sets the other flag
(`api/routes/document/documents.py:2369-2373` sets whichever the request names).
Also unresolved: existing vectors are **not** deleted when a doc is excluded (only
future embeds are skipped), and `/api/search/stats` does not subtract the excluded
population.

**M7. FTS recall is post-filtered to substring.** *(Superseded by `lance_fts` — see §5.)* The Lance FTS leg runs on the **raw**
query, then drops any hit whose folded text does not literally contain a folded term
(`db/__init__.py:4772`). Stemmed/tokenised recall is therefore thrown away, and the
accent-insensitive path only works because of the *fallback* scan. Correct today,
but it means FTS quality improvements cannot land until this post-filter is relaxed.

**M8. Neither `duckdb` nor `lancedb` is pinned — now BLOCKING.** `fichero-server/pyproject.toml:91,237` declare a bare
`lancedb`, while the code reasons explicitly about "the pinned lancedb version"
(`db/embeddings.py:589`). The interpreter on PATH here resolves **0.33.0**, not the
0.37.1 the brief assumed. A search stack whose select/FTS API differs across minor
versions must not float.

---

## 3. Multilingual & paleography reality check

Daniel's clarification — *"some of the multilingual support already exists; VERIFY what's
there rather than assume greenfield"* — is the framing for this section. Verified ledger,
against his checklist:

| His requirement | Status | Evidence |
|---|---|---|
| Storage / normalization, no lossy encoding | **BUILT, correct doctrine** | text stored exactly as transcribed; folding at MATCH time only (`db/__init__.py:352-360`) |
| NFC / normalization-form insensitivity | **BUILT** | NFKD fold makes NFC-vs-NFD input differences vanish (`db/__init__.py:367`) |
| Multilingual embedder | **BUILT** | `intfloat/multilingual-e5-large` (`db/embeddings.py:31`); `bge-m3` opt-in (`:32`) |
| e5 query/passage prefixes | **BUILT** | `format_for_model` (`db/embeddings.py:267`) — #1795 done |
| Accent-insensitive search | **BUILT** | `_fold_for_search`, casefold→NFKD→drop-Mn (#4363) |
| Long-s, çedilla, early-modern accents | **BUILT** (verified below) | fold table |
| Unicode-safe char offsets | **BUILT engine-side** | tokenizer-free splitter, code-point offsets (`db/embeddings.py:311`) |
| Scribal contractions (`ꝑ ꝓ ꝙ ꝫ`) | **MISSING** | no expansion; fold leaves them untouched |
| Early-modern spelling variants (u/v, i/j, ss/s) | **MISSING** | #3313's search half |
| Entity canonicalization across scripts | **PARTIAL** | alias expansion exists (`db/__init__.py:4653`); cross-script clustering is #3313 |
| Diplomatic vs normalized text layer | **MISSING** | #3312 open |
| Non-Latin FTS tokenization | **UNVERIFIED** | see M7 / §5 |
| Unicode-safe offsets at the Swift boundary | **MISSING** | grapheme/UTF-16 mismatch, §3 below |

So: **not greenfield.** The gaps are precisely three — scribal/orthographic variants,
script-aware folding, and the Swift offset boundary.


**Storage.** Text is stored as transcribed; folding happens **at match time only**
(`db/__init__.py:352-360`) — the diplomatic record is never mutated. Correct doctrine.
Dual diplomatic/normalized fields are still open as **#3312**.

**Embedding model.** `intfloat/multilingual-e5-large` (`db/embeddings.py:31`) —
genuinely multilingual (XLM-R 100-language base), so Amharic/Ge'ez and Hindi/Devanagari
are in-distribution. **Classical Sanskrit is not** in that language set; Devanagari
script coverage exists via Hindi, semantic quality for Sanskrit will be weak.
`BAAI/bge-m3` is available opt-in and is the better choice for cross-lingual retrieval.

**The fold, empirically verified** (run against `_fold_for_search`'s exact algorithm):

| Input | Folded | Verdict |
|---|---|---|
| `Quibdó` | `quibdo` | ✅ |
| `çedilla` | `cedilla` | ✅ cedilla decomposes |
| `ſeñor` (long-s) | `senor` | ✅ casefold maps U+017F→s |
| `CAFÉ` | `cafe` | ✅ |
| `ꝑsona` (scribal per-contraction) | `ꝑsona` | ❌ **no expansion** |
| `ኢትዮጵያ` (Ge'ez) | unchanged | ✅ syllabary, no combining marks |
| `ऋग्वेद` (Devanagari) | `ऋगवेद` | ❌ **virama + matras destroyed** |

Two real defects fall out:

- **Early-modern Spanish is 90 % handled.** Accents, cedillas and long-s all fold
  correctly. What does **not** work is the scribal contraction repertoire
  (`ꝑ` per/par, `ꝓ` pro, `ꝙ` quod, `ꝫ` et/con) — glyphs the transcription prompts
  explicitly instruct the model to *preserve* (`workflows/tools/handwriting.py:108`).
  We transcribe them faithfully and then cannot search them. Needs an expansion table
  in the fold (or a normalized-text layer, #3312), plus orthographic variant rules
  (u/v, i/j/y, ss/s, ç/z) — that is the search half of **#3313**.
- **Indic scripts lose meaning in the fold.** Devanagari vowel signs and the virama are
  Unicode category `Mn`, so the Mn-strip deletes them: `ऋग्वेद` → `ऋगवेद`,
  `वेद` → `वद`. Because the fold is applied symmetrically to query and content, recall
  survives — but precision collapses (distinct words become identical strings). The
  fold needs to be **script-aware**: strip Mn only for scripts where marks are
  diacritics, never for Brahmic scripts where they are letters. Ge'ez is unaffected.

**Offsets.** Python char offsets are code points and the passage splitter is
tokenizer-free by design (`db/embeddings.py:311`), so offsets stay exact for any UTF-8
script. The hazard is at the **Swift boundary**: `String` offsets are grapheme
clusters and `NSRange` is UTF-16. Any highlight overlay must convert engine code-point
offsets via `String.UnicodeScalarView`, or Ge'ez/Devanagari/emoji-adjacent text will
highlight the wrong span. This has no issue today.

**Alignment risk for the heat map.** Passage offsets index `documents.page_content`;
geometry offsets index the **artifact's** content (`artifacts.py:477`
`artifact.content or geometry.text`). Those are the same string only when
`page_content` was written from that artifact. Phase 2 must prove alignment before the
heat map is trusted, or the highlight lands on the wrong words silently.

**Tokenisation.** Non-Latin FTS recall is unproven — but the fallback substring scan
(M5/M7) means non-Latin queries still *work*, just slowly. Verify before optimising.

---

## 4. Front-end audit (Swift)

### 4.1 Why the field lands at the BOTTOM — it is one line

`.searchable` was removed from the shell in #4407
(`Views/Shell/ContentView/Layout/ContentView+RootLayout.swift:248-254`, `:471-476`).
The field today is a hand-rolled `HStack` — `Views/Library/LibraryView+MiniToolbar.swift:66-104`
(`TextField` at `:72`, clear button `:84-93`, mode menu `:95`).

The placement chain:

1. `Views/Library/LibraryView+Body.swift:108-110` — `.safeAreaInset(edge: .bottom)` hosts
   `bottomInsetContent`.
2. `Views/Library/LibraryView+Insets.swift:147-152` — that inset renders the mini toolbar
   when placement is `.bottom`.
3. `Views/Library/LibraryView+Body.swift:93-97` — **the top-edge twin already exists** and
   is currently unreachable.
4. **The deciding line: `Views/Components/PaneFilterBar.swift:24`** —
   `static var preferredForReader: MiniToolbarPlacement { .bottom }`, recorded as a
   2026-08-11 ruling ("BOTTOM everywhere now… the Xcode console model").
   `LibraryView.miniToolbarPlacement` reads it at `LibraryView+MiniToolbar.swift:29-31`.

So Phase 0.1 is a **one-line flip plus its consequences**: the same property also drives
the *reader's* find bar (`Views/Reader/Page/ReadingPaneView.swift:107,113`), so flipping
it globally moves that too. Either split the property per surface, or get Daniel's ruling
(design question 9). Note the toolbar magnifier is a `Toggle` on `showSearchField`
(`Views/Shell/ContentView/ContentView+Toolbar.swift:168-177`,
`@SceneStorage` at `ContentView.swift:218`) — "always visible and expanded" means
retiring that toggle, not just repositioning what it reveals.

### 4.2 Two disconnected mode controls

- **Ask / Keyword** — a `Menu` (not a `Picker`) in the library bar,
  `LibraryView+MiniToolbar.swift:107-136`; enum `SearchFieldMode` at
  `ContentView+RootLayout.swift:466-469`; persisted `@AppStorage("search.fieldMode")`
  (`ContentView.swift:254`). It only sets `compile:`
  (`Actions/ContentView+ActionsImport.swift:74` → `SearchStore.performSearch(compile:)`).
- **Hybrid / Semantic / Full Text** — a separate `Picker` in the *results* bar,
  `ContentView+SearchResults.swift:503-531`, backed by `transientSearchType`
  (`ContentView.swift:275-277`).

Two controls, two locations, no cross-reference. #4604's "mode menu on the magnifier"
means **merging these into one** — which is a simplification, not new UI.

### 4.3 The disclosure sections to kill

`nonDocumentHitSections` — `ContentView+SearchResults.swift:472-494` — renders three
`SearchHitSection`s: **Artifacts**, **People & Places**, **Claims**. The `DisclosureGroup`
itself is `Views/Shell/ContentView/SearchHitSection.swift:41-57`, collapsed by default
(`:27`), preview-capped at 5 (`Models/SearchHitPresentation.swift:40`). Rows are
`Button`s with no selection state (`SearchHitSection.swift:62-63,82-87`).

Document results are **already** library nodes — they replace the grid's `documents`
input and render through `MailStyleRow` with excerpt + score
(`Views/Library/LibraryViewComponents.swift:225-231`, `:261-264`). So #4118's "typed
results as first-class nodes" is: give entities/artifacts/claims the same row treatment
and delete `SearchHitSection` — not build a new results surface.

### 4.4 Spinner and sort already exist

- Spinner: `ContentView+SearchResults.swift:350-355` (`ProgressView` + "Searching for…"),
  driven by `SearchStore.isSearching` (`Models/SearchStore.swift:46,90-92`). It is in the
  header bar only — no skeleton over the grid.
- Sort: results-scoped at `ContentView+SearchResults.swift:514-523`; library-scoped at
  `LibraryView+MiniToolbar.swift:141-186`. Client-side sort is correctly suppressed during
  an active search so engine ranking survives
  (`Views/Library/LibraryView+FilterAndBatch.swift:153-162`).

**So Phase 0 items 4 and 5 are largely DONE.** What remains is placement and the
one-control merge. #4604 asks for them because they are not *visible* where expected,
not because they are missing.

### 4.5 The blocking gap for the heat map

The engine **sends** char anchors and the client **decodes** them —
`Models/SearchResult.swift:12` (`transcriptExcerpts`), generated
`SearchExcerpt { text, char_start, char_end, match_start, match_end, anchor }` and
`SearchAnchor { document_id, char_start, char_end }`.

Then the app **throws them away**: `Models/SearchResult.swift:59-73` collapses everything
to `TransientSearchRowHit(excerpt: transcriptExcerpts.first?.text, score:)`, and
`ContentView+SearchResults.swift:148-151` reduces results to `(documentId, rowHit)` pairs.
The code comment at `SearchResult.swift:53-58` says the span is kept "for the coming
sentence-level highlight provenance" — planned, never wired.

Navigation is therefore document-level only: `openHitDocument`
(`ContentView+SearchResults.swift:191-204`) → `navigateToDocument`
(`ContentView+SourceNavigation.swift:9-12`) sets `viewMode = .library(doc)`. No page,
no offset, no scroll target.

**And the contract is missing `page_id`.** `SearchAnchor` carries only
`document_id/char_start/char_end` — confirmed on the engine side at
`db/__init__.py:400-406`, even though the vector rows themselves *do* carry `page_id`
(`db/__init__.py:4715`). Adding `page_id` (and the producing `artifact_id`) to
`SearchAnchor` is the smallest change that unblocks click-through-to-page.

### 4.6 The overlay half is already built

- `Views/Preview/ImageViewer/OCRGeometryOverlay.swift:10-38` draws per-box rectangles.
- `Models/OCRGeometry.swift:12-35` — `OCRGeometryBox` carries `bbox`, `level`,
  `pageIndex`, and **`charStart`/`charEnd`**, documented at `:9-11` as spans "inside the
  owning artifact's content string" — the exact alignment caveat flagged in §3.
- `Models/BoundingBoxGeometry.swift:13-25` does the zoom/pan transform.
- Geometry is loaded from the **artifacts** API, not search:
  `Models/OCRGeometrySelection.swift:34-45` probes `text_geometry` / `transcription` /
  `regions` artifacts.
- **A `highlightBoxes: [[Double]]` input already exists** on the image previews
  (`ZoomableImagePreviewMac.swift:32`, `:350-379`; `DocumentCanvas.swift:134`). Its only
  producer today is entry provenance (`Views/Preview/EntrySourcePreview.swift:25-28`).

So the image-side heat map needs **no new view** — filter `OCRGeometry.boxes` by span
overlap and feed the existing `highlightBoxes` input. PDFs need a fourth annotation sweep
beside `applyOCRBoxes` (`Views/Preview/PDFViewer/PDFPageView+OCRBoxes.swift:40-60`).
A grep for `heatmap|searchHighlight|searchMatch` finds only find-in-page match *counts* —
there is no search overlay anywhere today.

### 4.7 Service layer

`SearchStore` (`Models/SearchStore.swift:40-54`) is `@Observable`, one per library, and
calls `SearchService` (`Services/SearchService.swift:17-33`), which uses the **generated
OpenAPI client** throughout (`POST /api/search` at `:82-86`, stats `:101`, reindex `:119`,
embed `:134`, keywords `:157`) — consistent with the knowledge-consistency mandate.

Two scale seams worth noting before Phase 1:
- **Not streaming.** One `await` POST per query, whole response applied at once
  (`SearchStore.swift:131-135`). "Results stream in" (#4604) is not achievable without an
  engine change; the spinner is the honest interim.
- **N+1 document resolution.** `ContentView+SearchResults.swift:128-147` fetches each hit
  document individually on cache miss and silently drops unresolvable ones (`:141-143`) —
  the client-side twin of engine M5.
- Paging is re-query with a larger `limit` (+50, `:156-162`), not a real offset page.

## 5. DuckDB-Lance extension (#4175) — SPIKE IS DONE; this is now the read path

**Superseded (2026-08-19).** An earlier draft of this plan said "take the spike later, and
there is no `lance_hybrid_search` SQL function to adopt." **Both statements were wrong.**
The read-path spike posted on #4175 proves the extension is real, loadable and fast:

- `INSTALL lance; LOAD lance;` on **duckdb 1.5.5** exposes `lance_vector_search`,
  `lance_fts` and **`lance_hybrid_search`** as SQL table functions.
- `lance_vector_search(path, 'vector', ?::FLOAT[1024])` **joined to `documents`**:
  786 ms cold, exact self-match at rank 1, sensible neighbours — against a real Marshall
  scratch library (382 passage vectors, 1024-dim).
- `lance_fts(path, 'text', 'Istmina')`: 57 ms, scores in `_score`.
- `lance_hybrid_search(path, 'vector', vec, 'text', query)` + join: **660 ms cold /
  17 ms warm**.
- **`document_id`, `page_id`, `char_start`, `char_end` and document dates all ride along
  in ONE statement** — the heat-map anchors come free.

Signature notes for implementation: score column is `_score` (FTS) / `_distance` (vector);
`lance_fts(path, text_col, query)`; `lance_hybrid_search(path, vector_col, query_vec,
text_col, query_text, [alpha/k/...])`.

**Daniel's direction:** this IS the way. The extension binary gets **embedded in the
Briefcase bundle** — no runtime `INSTALL`, shipped offline like every other dependency.
`lancedb-python` is retained for **writes** initially; only the read path moves.

### What this deletes

The extension read path makes three of the §2 findings obsolete rather than fixed:

- **M5 (per-candidate N+1 + `to_pandas()` full-corpus scan)** — gone. `_is_active_document_id`'s
  uncached per-row `get(Document, id)` and the whole-table pandas fallback both collapse
  into SQL predicates on the join (`d.deleted_at IS NULL AND NOT d.exclude_from_search`).
- **M7 (FTS post-filtered to substring)** — gone. `lance_fts` returns real `_score`; the
  folded-substring post-filter that currently throws away tokenised recall can be dropped
  once folding moves into the indexed text or a normalized column.
- **Hand-rolled RRF** — `lance_hybrid_search` does the fusion. Our RRF stays only for the
  legs the extension does not cover (entity + claim vectors, KG neighbourhood — M1).

It also changes the shape of **M2**: with one SQL statement producing one ranked list,
there is no second fused-score threshold to mis-apply. Fix M2 in Phase 0 anyway — the
cutover is later and the bug is dropping real hits today.

### What it does NOT solve

Ranking quality. The extension is plumbing: it makes the Andagoya query *one statement*
instead of two stores glued in Python, but it does not fuse entities, claims or the KG
neighbourhood. **M1 remains the substantive work** and is unaffected by this decision.

### Open items to close before cutover

1. **Index build/refresh at scale** — `__lance_optimize_index`. The spike's 382 vectors
   needed no FTS index; Marshall-scale corpora will. Verify build time and refresh policy.
2. **Concurrent read-while-append** — the Python `lancedb` writer keeps appending while
   DuckDB reads. Verify snapshot isolation and that a mid-append read cannot see a torn
   fragment.
3. **Extension load under the sandbox** — Dev Local **is** sandboxed now, so the binary
   must load from inside the app container, not `~/.duckdb/extensions`. Expect to need an
   explicit `LOAD '<abs path>'` and possibly `allow_unsigned_extensions`; both interact
   with codesigning and notarization of a loadable dylib inside a signed bundle.
4. **Bundling step in `build_backend_bundle.sh`.** There is already a precedent to copy:
   the script builds `fm-bridge` and stages it into
   `src/fichero_server/resources/bin/` before Briefcase packages
   (`fichero-server/scripts/build_backend_bundle.sh:9-10,31-33`). The `.duckdb_extension`
   binary follows the same path. Note the script builds **and signs as two deliberate
   steps** (`:41-45`) — the extension must be sealed in that same seam.
5. **PIN `duckdb` AND `lancedb`.** Both are declared bare in
   `fichero-server/pyproject.toml:90-91,236-237`. A DuckDB extension binary is locked to
   its DuckDB version *and* platform triple (`osx_arm64`); shipping a pinned extension
   against a floating `duckdb` is a guaranteed future load failure. This is now a
   **blocking prerequisite**, not the hygiene note it was before.
6. **Migration discipline.** Read-path only, no schema change — but Marshall Diaries are
   real data, so the cutover lands behind a flag with the Python path as fallback until
   a golden-set comparison shows identical or better results.

## 6. Phased plan

Dependency-ordered. Each phase is independently shippable and testable.

### Phase 0 — Quick UX wins (frontend, plus one 5-line engine change)
Goal: the field behaves the way Daniel expects within one session of work. Three of the
six items are smaller than #4604 assumes; two are already built and merely misplaced.

1. **Field top-right, always visible and expanded.** Flip
   `Views/Components/PaneFilterBar.swift:24` to `.top` (the top inset at
   `LibraryView+Body.swift:93-97` is already wired), and retire the `showSearchField`
   toggle (`ContentView+Toolbar.swift:168-177`, `@SceneStorage` `ContentView.swift:218`).
   Blocked on design question 9 — the same property drives the reader find bar.
2. **One mode menu on the magnifier.** Merge the Ask/Keyword `Menu`
   (`LibraryView+MiniToolbar.swift:107-136`) with the Hybrid/Semantic/Fulltext `Picker`
   (`ContentView+SearchResults.swift:503-531`) into a single control on the field.
3. **Kill the disclosure sections.** Delete `nonDocumentHitSections`
   (`ContentView+SearchResults.swift:472-494`) and `SearchHitSection.swift`; typed hits
   become ordinary rows (this is the front half of Phase 1.2).
4. **Spinner — already built** (`ContentView+SearchResults.swift:350-355`). Keep; the ask
   is really that it is invisible where the user looks. No work beyond re-placement.
5. **Sort — already built**, twice (`ContentView+SearchResults.swift:514-523`,
   `LibraryView+MiniToolbar.swift:141-186`), and correctly suppressed during an active
   search (`LibraryView+FilterAndBatch.swift:153-162`). Consolidate into the one menu.
6. **Fix M2 here, not later.** The `min_score` floor drops real keyword hits **today**
   (`SearchStore.swift:65,102` + `db/__init__.py:4994`). It is a handful of lines and it
   is the difference between search that answers and search that lies. Ship it in Phase 0
   and re-test #4236 against it.
7. Ship **M3** with it: singular scope aliases in `search/query_parser.py:33`.

Issues: #4604 (FIELD & SCOPES, RESULTS), #4236 (via item 6). Tests: view-model unit tests
for mode selection and sort; an engine regression test that a keyword-only match at rank 2
survives the default `min_score`; a `RenderPreview` pass per the preview-driven-UI memory.

### Phase 1 — Results are library nodes; unified relevance
1. Results render as ordinary **library nodes** usable in every view mode (#4118, #3091).
2. Entities / artifacts / statements as first-class result rows (#4118) — engine legs
   already exist (`core.py:153`).
3. **Fuse KG into ranking** (M1, #1833): call `GraphAwareRetriever` from the search
   route and merge entity + claim + graph-neighbourhood ranks into the RRF combine at
   `db/__init__.py:4950`, rather than annotating afterwards.
4. Fix **M2** (min_score default) as part of the same change — a fusion change that
   leaves a 0.55 post-filter in place will look like it did nothing.
5. Honest relevance display (#4119) rides here.

Tests: golden-set retrieval test — "Andagoya" must return the known pages, ranked,
with the claim that answers the query present; a regression test asserting a
keyword-only match at rank 2 survives the default `min_score`.

### Phase 2 — The Andagoya golden path: click-through + heat map
The two halves both exist; this phase is the join.

1. **Add `page_id` (and the producing `artifact_id`) to `SearchAnchor`** —
   `db/__init__.py:400-406`. The vector rows already carry `page_id`
   (`db/__init__.py:4715`); the contract simply drops it. Without this, click-through can
   never land on a page. Regenerate the OpenAPI client.
2. **Stop discarding the anchor client-side** — `Models/SearchResult.swift:59-73` and
   `ContentView+SearchResults.swift:148-151` collapse the span to a string. Carry
   `charStart/charEnd/matchStart/matchEnd/pageId` through `TransientSearchRowHit`.
3. **Prove offset alignment.** Passage offsets index `documents.page_content`; geometry
   offsets index the artifact's content (`Models/OCRGeometry.swift:9-11`;
   `artifacts.py:477`). They coincide only when `page_content` was written from that
   artifact. Add an engine test asserting it for a known Marshall page; if it fails, store
   the producing artifact id on the passage row (item 1 already adds the field).
4. **Batch region endpoint** beside the existing single-span
   `GET /artifacts/{id}/region` (`artifacts.py:419`) — many spans, one round trip.
   `region_for_span` / `boxes_for_span` (`media/ocr_geometry.py:639,676`) do the work.
5. **Image heat map needs no new view**: filter `OCRGeometry.boxes` by span overlap and
   feed the existing `highlightBoxes: [[Double]]` input
   (`ZoomableImagePreviewMac.swift:32,350-379`; `DocumentCanvas.swift:134`), whose only
   current producer is entry provenance (`EntrySourcePreview.swift:25-28`).
   Weight opacity by passage score for the heat effect (design question 6).
6. **PDF**: a fourth annotation sweep beside `applyOCRBoxes`
   (`PDFPageView+OCRBoxes.swift:40-60`) with its own `userName`.
7. **Reader**: same spans through the existing highlight machinery
   (`AnnotationHighlight.swift:21`, `PageContentPane+SourceHighlight.swift:27`).
8. **Unicode-scalar-safe offset conversion** at the Swift boundary (§3) — engine offsets
   are Python code points; `String` offsets are grapheme clusters and `NSRange` is UTF-16.
9. **Navigation**: extend `navigateToDocument` (`ContentView+SourceNavigation.swift:9-12`)
   to accept a page + span target instead of document only.

Issues: #4604 (NAVIGATION & HIGHLIGHTING), #4309/#4418 (geometry).
Tests: engine test that a passage span maps to non-empty boxes for a known page; the
alignment test in item 3; a Swift test on offset conversion with Ge'ez, Devanagari and
combining-mark fixtures.

### Phase 2.5 — Cut the search read path over to the DuckDB-Lance extension (#4175)
Runs after Phase 2 has proven the anchors, and can proceed in parallel with Phase 3.
Spike is done (§5); this is the productionisation.

1. **Pin `duckdb` and `lancedb`** in `fichero-server/pyproject.toml:90-91,236-237`.
   Blocking prerequisite — the extension binary is locked to a DuckDB version and to
   `osx_arm64`.
2. **Bundle the extension.** Stage the `.duckdb_extension` binary into
   `src/fichero_server/resources/` and copy the `fm-bridge` precedent in
   `fichero-server/scripts/build_backend_bundle.sh:31-33`; seal it in the existing
   build-then-sign seam (`:41-45`). No runtime `INSTALL`.
3. **Load under the sandbox** — `LOAD '<abs path inside the container>'`, since Dev Local
   is sandboxed. Verify signing/notarization of a loadable dylib inside the signed bundle,
   and whether `allow_unsigned_extensions` is required.
4. **Replace the search read path**: one `lance_hybrid_search(...) JOIN documents`
   statement in place of the two-store glue at `db/__init__.py:4614-5000`. Exclusion,
   soft-delete, folder scope and date filters become SQL predicates on the join — which
   deletes M5 and M7 outright.
5. **Keep `lancedb-python` for writes.** Read path only.
6. **Behind a flag, with the Python path as fallback**, until a golden-set comparison
   (the Andagoya set from Phase 1) shows identical-or-better ranking. Marshall is real data.
7. **Verify at scale**: `__lance_optimize_index` build/refresh cost, and concurrent
   read-while-the-python-writer-appends (snapshot isolation, no torn reads).

Tests: golden-set equivalence between the two read paths; a load test that fails loudly if
the bundled extension cannot load (per the absence-read-as-success memory — a missing
binary must not fake a green); a concurrency test appending while querying.

### Phase 3 — Multilingual & paleography soundness
*The colonial-archive core use case: 15th-c. Spanish paleography must search well.*
1. **Script-aware fold** — never Mn-strip Brahmic scripts (§3).
2. **Scribal contraction expansion table** (`ꝑ`→per/par, `ꝓ`→pro, `ꝙ`→quod, `ꝫ`→et/con)
   + early-modern orthographic variants (u/v, i/j/y, ss/s, ç/z). This is #3313's
   search half; ties #3312's normalized-text layer.
3. Extend the question-word gate beyond EN/ES (`query_compiler.py:33`).
4. Decide the embedding space for non-Latin corpora: stay on multilingual-e5-large or
   move to bge-m3 (already available). A space switch means a full re-embed —
   `migrate_embedding_space` exists (`db/embeddings.py:681`).
5. Verify Lance FTS tokenisation for Ge'ez/Devanagari; relax the substring post-filter
   (M7) once measured.

Tests: a fixture corpus with Ge'ez, Devanagari and 15th-c. Spanish pages; assert the
fold table in §3 as unit tests (they currently pass/fail exactly as tabulated).

### Phase 4 — Smart routing, expansion, sidebar smart folders
1. Route questions → Ask (M4); word lists → search; "construct me a search" → compiler.
2. Query expansion: "gold" offers precious-metal neighbours via entity/vector neighbours
   (`_expand_query_with_entity_aliases` is the seam).
3. Smart folders for Entities / Places / People (#4114), including one-click
   "all mentions of <entity>" from an entity context menu.

### Phase 5 — Restore the SVO/statement graph reader view (#4605)

**Nothing was deleted and no feature flag hides it.** The archaeology:

- The view Daniel remembers is `15bce1bd0` (2026-05-13), "focus-neighborhood with
  SVO-labeled edges" — predicate drawn mid-edge in italic.
- `f64ce0640` (2026-07-12, #3503) swapped the reader's Graph sub-mode from the WebKit SVO
  renderer to a **native entity co-occurrence** graph by flipping `.graph` to the `false`
  arm of `usesWebKit` (`Views/Reader/Knowledge/DocumentKGSurface.swift:120-128`).
- `39ae50b00` (2026-07-12, #3512) demoted **Statements** from a co-equal tab to a small
  borderless caption button (`Views/Reader/Page/ReadingPaneView+Knowledge.swift:38-50`);
  it is absent from `knowledgeVizModes` at `:64`.
- The `7f07127b4` / `6b17079f3` reorgs (#3999/#4012) that #4605 blames were **pure file
  moves** — no behaviour was lost there.

**Why the graph looks like unlabelled blobs today:** the surviving SVO label draw is
guarded by `lineLen > 72 && edge.weight >= 2 && !edge.predicate.isEmpty` —
`Views/Library/ViewModes/Graph/Ontology/ForceDirectedGraphView+Render.swift:32`. In a
single-document reader graph almost every claim edge has weight 1, so **no predicate ever
renders**. That guard is the actual regression.

**Restoration, smallest correct fix:**
1. Drop the `edge.weight >= 2` condition (and relax `lineLen > 72`) at
   `ForceDirectedGraphView+Render.swift:32`. This alone restores "subject-verb-object
   laid out".
2. Add `.digest` back to `knowledgeVizModes` (`ReadingPaneView+Knowledge.swift:64`),
   delete the standalone button at `:38-50`, and remove the `activeTab == .digest`
   special cases in `knowledgeVizBinding` (`:69-77`) and `effectiveKnowledgeTab` (`:81-83`).
3. *Optional* — restore the WebKit SVO graph as a comparison surface by moving `.graph`
   to the `true` arm of `usesWebKit` (`DocumentKGSurface.swift:127`), the exact line
   `f64ce0640` flipped.

**No enum cases to re-add, no files to un-delete, no flag to flip, and no engine work:**
`GET /api/kg/graph/neighborhood/{entity_id}` is live and documented as
"Focus entity + k-hop neighbors + SVO edges" (`api/routes/kg/graph.py:399-413`).

Tests: a render test asserting a weight-1 claim edge draws its predicate; a sub-mode
test asserting Statements is reachable from the picker.

Side finding worth Daniel's attention: `Views/Sidebar/SidebarView.swift` no longer renders
any `SidebarMode` switcher, so the Knowledge Graph mode is reachable **only** via
View menu / Cmd-9 (`App/Menus/ViewMenuCommands.swift:195`).

### Phase 6 — Vector-space visualisation
The "Nomic Atlas" mode below Dataset and above 3-D Space. **This already has an issue:
#878** (semantic embedding map, 2D projection) — #4604's VECTOR VISIBILITY section
should point at it rather than imply a new one. Feasibility spike first.

### Phase 7 — Scale
Cross-library fan-out (#4110), `_is_active_document_id` caching / SQL prefilter (M5),
Spotlight indexing (#4167). (#4175 now lands in Phase 2.5, and M5 dies with it.)

---

## 7. GitHub set-up problems found

- **`Search View - Engine` (milestone 186) is effectively dead** — 1 open issue (#4395)
  while every engine issue (#1833, #1824, #1782) sits in `Search View`. Either move the
  engine work in or retire the milestone.
- **#3309** (document date + sort) is filed under *Search View - Saved Searches* — wrong
  milestone, and it is **partly built already** (`sort_by: "document_date"`, `date_jdn`
  filters). Needs a verify-and-close pass on the built parts.
- **#4236** ("search returns 0 results for text the Inspector shows") is under
  *Library View*, not Search. It is the highest-signal search bug open and should sit
  in `Search View`; M2 above is a concrete candidate cause worth testing against it.
- **#4580** is largely **implemented** under a different flag (`exclude_from_search`).
  Re-scope to what actually remains: unify with `exclude_from_processing` (or state the
  two-switch UX), delete vectors on exclusion, subtract excluded docs from
  `/api/search/stats`.
- **#1782** (boost exact/keyword above semantic) appears **done** — the
  `0.1 × lexical` nudge at `db/__init__.py:4980`. Verify-and-close or re-scope.
- **#1795** (e5 prefixes), listed as blocking inside #1833, is **done**
  (`db/embeddings.py:267`). #1833's build order should be updated to start at fusion.
- **#4604's VECTOR VISIBILITY section duplicates #878**; its RESTORE section correctly
  points at #4605. Cross-link #878 so nobody files a third.
- **#4605's premise is wrong in a useful way.** It says the view was "hidden in some
  reorg"; in fact the reorg commits were pure file moves and the real cause is a
  `weight >= 2` label guard plus a deliberate #3503 swap to a native graph. The issue
  body should be corrected so nobody goes looking for deleted files (see Phase 5).
- **#4114 and #4118 carry no labels** while #4604 does — they will not show up in
  label-driven queries.
- **Not covered by any issue** (flagging only, not filing): the `min_score = 0.55`
  post-RRF trap (M2); passage-vs-geometry offset alignment (§3) — the precondition for
  the whole heat map; the batch region endpoint; singular scope aliases (M3); the
  unpinned `lancedb` (M8); and the script-aware fold defect for Brahmic scripts (§3).

---

## 8. Design questions for Daniel

1. **One exclusion switch or two?** Today `exclude_from_processing` and
   `exclude_from_search` are independent. Your question implies one switch. Collapse
   them, or keep two and label them clearly? (Memory: *dead-simple UX, no needless
   toggles* argues for one.)
2. **Scope prefix spelling:** you wrote `person:`/`place:`/`date:`; the parser
   implements `people:`/`places:`/`dates:`. Accept both (aliases), or rename to your
   singular forms and break saved searches that use plurals?
3. **Embedding space for non-Latin corpora:** multilingual-e5-large has no Sanskrit.
   Is a switch to `bge-m3` — and the **full re-embed** of Marshall it forces — worth it
   now, or do we route per-script later?
4. **Diacritic fold and Brahmic scripts:** the fix is a script-aware fold. Confirm that
   accent-insensitivity should stay *on* for Latin/Greek/Cyrillic while being *off* for
   Devanagari — i.e. behaviour differs by script.
5. **Scribal contractions:** expand at match time (fold-level table), or materialise a
   normalized-text layer (#3312)? The second is more work but makes contractions
   visible and correctable as curation.
6. **Heat map density:** when a page has 20 hits, do we shade every one equally, or
   weight by passage score? And does the heat map persist while reading, or fade?
7. **Ask mode:** confirm Ask = run the search, then open chat scoped to the results
   (#4117 behaviour kept), rather than a separate answer surface.
8. **Transient search canvas** (from #3091): positions for a transient search — ephemeral
   and non-persisted, or promote-to-saved-search before positions stick?
9. **Does the search field move for the reader too?** `PaneFilterBar.swift:24` is a single
   property driving both the library search bar and the reader find bar, set to `.bottom`
   by your 2026-08-11 "Xcode console model" ruling. Moving search to the top either moves
   the reader's find bar with it or requires splitting the property. Which?
10. **The magnifier toggle:** "always visible and expanded" implies retiring the
    `showSearchField` toolbar toggle entirely (`ContentView+Toolbar.swift:168-177`).
    Confirm — or should the toggle stay as a focus shortcut?
11. **Results streaming:** the client is one-shot POST/await
    (`SearchStore.swift:131-135`). "Results stream in" needs an engine streaming
    endpoint. Is the spinner acceptable for now, or is streaming in scope?

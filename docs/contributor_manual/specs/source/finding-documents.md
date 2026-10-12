# Finding the documents in a box — Design Spec (#5550)

> Milestone: Library View
> Manual: TBD — a section of "Organising a project": a box of loose pages; what Find the Documents
> proposes and from what evidence; accepting, rejecting and adjusting on the canvas; how corrections
> teach the project's own model.
>
> **Status: DRAFT — 2026-10-07.** Related: `ui/library-view-modes.md` §I "Arrangements that propose"
> (#5550), `source/undeciphered-scripts.md` §12 "The order of the leaves" (#5548), the vector map
> (#5549), `compute/distillation.md` (the teacher → student loop), group nodes (#5303), prototypes.

## Intent (the design)

Archives arrive as boxes of loose pages whose structure nobody knows: 203 pages filed as one folder
that are really several court judgments, each made of a complaint, a power of attorney, hearing
records, an inspection and a sentence; a bundle that may be letters, cables, or receipts; a manuscript
bound in the wrong order. A historian works this out by looking, reading, laying pages side by side,
and moving them until the structure is clear.

Fichero does this as a **tool any project can run on any folder** (a box, a bundle, a volume, a
selection of pages), not a one-off pass: **Find the Documents**. It proposes, with evidence and confidence, and never changes the source by itself:

1. **Boundaries** — where each document starts and ends in the stream of pages.
2. **Kinds** — what each document is, as a prototype with attributes (Sentencia {juzgado, juez,
   fecha, demandante, demandado, materia, resultado}; Demanda; Poder; Acta de audiencia; Carta;
   Cable; Recibo …), with the attribute values read from the page and cited to it.
3. **Groups** — which documents belong together (a case, a correspondence, a dossier), and their
   order within the group (the order the proceeding ran, or the order of the leaves).

The proposals are drawn on the **2D canvas**: a proposed document's pages sit together in order, a
proposed group is a region with a label, uncertain boundaries are shown as uncertain. A person accepts,
rejects, or adjusts by moving cards; an accepted document becomes a **group node** of its pages
(#5303) with its prototype assigned; an accepted group becomes a group of documents with a named
order. Every acceptance is audited and undone by Ungroup. Every correction is kept as training data.

It improves with use. The first run on a project uses rules, embeddings and a thinking model as the
teacher; the person's corrections and the teacher's decisions train the **project's own model** for
this task (the same distillation loop as the readers), which then runs locally, quickly, and asks the
teacher only where it is unsure.

## Ruled 2026-10-10 (the maintainer, after the Organise review)

- **The auto-accept covers boundaries only.** At or above the threshold, which pages form a document is
  accepted; the document's kind is left as a proposed kind on its node (the one proposed-kind mechanism
  `classify` uses), and cases are always proposed, never accepted by the run. This applies the 2026-10-08
  ruling that a kind is proposed, never assigned.
- **The auto-accept is off until a scored box.** The 95% is a hand-set score today, never checked against a
  box a person broke down. Until a real box (Istmina first) is scored against a person's breakdown and shows
  boundaries at least 99% right at that level, Find the Documents proposes and accepts nothing by itself;
  then it switches on at the measured level. **Built 2026-10-10 (engine):** the measurement
  (`finddocs.scored`): a folder is scored against the documents a person accepted or adjusted, the score is
  kept, and it suggests the level (`suggested_accept_above`); a person, not the score, switches it on.
- **Organise runs after names and dates.** Parties come from the names found; officials who appear on every
  document (a judge, a secretary) are not parties and link nothing. **Built 2026-10-10:** the step follows
  "Work out dates" in the recipe order, and a name on more than half of a folder's documents (four or more)
  is an official, shared by no case (`finddocs/propose._groups`); pinned by
  `fichero-server/tests/unit/finddocs/test_officials_are_not_parties.py`. *Not built: offices named per
  language (judge, notary, secretary) in place of the count.*
- **An accepted case is a group node**, holding its documents in their order, made only when a person accepts
  the case.

## Evidence Find the Documents uses (each signal named in the proposal's reasons)

| Signal | From | Says |
|---|---|---|
| Opening and closing cues | the page's text (any reading) | a caption ("JUZGADO DEL TRABAJO DEL CIRCUITO DE ISTMINA"), a heading ("Sentencia", "Demanda"), a place and date line, a salutation, a signature block, "Notifíquese", a seal mention — a document starts or ends here |
| Continuity across the break | the last lines of page *n* and the first lines of *n+1* | a sentence, list or table runs over the break (scored by a language model's surprise at the join) — same document |
| Page furniture | text and layout | folio numbers, "página 2 de 3", catchwords, running heads; numbering restarting means a new document |
| Look of the page | the image | stamp paper (papel sellado) and its revenue stamps, letterhead, typed vs handwritten, the typewriter, the hand, margins, paper — changes suggest a boundary, sameness suggests one document; measured by an image embedding of the page and of its layout |
| Who and what | names, organisations, places, dates, case or docket numbers (the KG and the page's mentions) | the same parties and case number tie documents into a group |
| Reply and reference | the text | "en contestación a su oficio de …", "visto el memorial de …" — links one document to an earlier one |
| Meaning | text embeddings and topic models | how alike two documents are (latent semantic analysis, as Layfield & Fagin Davis used for the Voynich leaves) |

## What the first real box taught (Istmina Full, '1948 Sentencias', 2026-10-07)

A visual pass over all 203 images found 8 judgments from 8 cases, in date order, from one court
(Juzgado del Trabajo de Istmina, judge Constantino Salazar Ruiz): most likely the court's 1948 register
of judgments. The folder's name came from the first case and was misleading; only 4 of the 8 cases
involve the company it names. Lessons the tool must carry:
- **Recto and verso.** Every leaf was photographed front then back, and the backs were blank: 203
  images ≈ 99 leaves. Pages pair into leaves before anything else; a blank verso is not a document.
  Bleed-through on a blank verso can be read mirrored and matched to its recto.
- **Duplicate and missing shots.** Some leaves were photographed twice (one with a catalogue slip over
  the text); some written pages were never photographed (seen only as bleed-through); one judgment's
  first leaf is gone. These are findings to report (and re-photograph), not boundaries.
- **Documents inside documents.** Each judgment copies its case record (complaint, power of attorney,
  hearing records, inspection, letters, contracts) into its own text; those copies begin and end
  mid-page. They are text ranges (segments) inside the judgment with their own prototype, not page
  groups that would overlap at their edge pages.
- **Fair copies and originals.** Typed "(fdo)" signatures mark copies for the court's book; real
  handwritten signatures mark originals. Worth an attribute.
- **No case numbers.** Cases are told apart by parties, subject and dates alone.
- **Boundaries were clear in this box** (a new judgment opens with "JUZGADO DEL TRABAJO / Istmina,
  <date> / VISTOS" right after the previous "FALLA … Cópiese" and signatures), so this box is a good
  first scored test with a known answer.

## How it works (one engine job, layered from cheap to expensive)

1. **Cues and features** for every page: the signals above, computed once and cached with the page.
2. **Boundaries** as page-stream segmentation: for each pair of neighbouring pages, the probability
   that a new document starts. A rule-and-feature scorer first; the project's trained model once it
   has one; the teacher on the uncertain pairs.
3. **Kinds**: each proposed document is matched to a prototype (an existing one, or a proposed new
   one with the attributes its pages show); attribute values are extracted and cited.
4. **Groups and order**: documents are clustered by shared parties, case numbers, dates and replies
   (a graph of links), and ordered within a group by the procedure's typical order and dates; for
   leaves of a manuscript, by adjacency scores (seriation over the similarity matrix).
5. **The teacher** — a thinking vision-language model that looks at the page images and the text and
   reasons about the hard cases — is asked only where steps 2–4 are unsure, and its reasons are kept.
6. **Proposals** are stored as hypotheses (never as changes) and drawn on the canvas.

## Learning (the same loop as the readers)

- Every accepted, rejected or moved proposal is a labelled example: boundary/no boundary between two
  pages, the kind of a document, which group it belongs to.
- With enough examples, Find the Documents trains the project's own model: a small multimodal
  classifier for boundaries and kinds (page image + text features; a fine-tuned small vision-language
  model or a layout model), distilled from the teacher plus the person's corrections, held-out pages
  split by box. It lives in the project (#5539) and can be made global for a collection.
- Scored as the readers are: boundary precision and recall, document-level agreement (how many
  documents come out exactly right), kind accuracy, group agreement — against a person's breakdown.
- **Known-answer tests** before any real box: the Voynich manuscript's conjugate leaves (which pages
  were once one sheet) and a public page-stream-segmentation set; then a real box broken down by a
  person (Istmina Full, '1948 Sentencias', 203 pages).

## Surfaces

- **The app:** Organise ▸ Find the Documents on a folder or a selection; the canvas shows the
  proposals; the Inspector shows a proposal's evidence and confidence; Accept, Reject, Accept All
  Above a Confidence; moving a card is an adjustment the tool learns from.
- **MCP and CLI:** the same job, its proposals, accept/reject, and a picture of the canvas, so an
  agent can lay out, look and adjust (#5568).
- **A recipe step:** "Find the documents" can be part of a project's recipe, after reading and
  before cataloguing.

## Behaviors

- `finddocs.job.any-box` — **[OK]** (#5550) Find the Documents runs on any folder or selection of
  pages as one background job and stores proposals. Finding changes nothing in the source; as the run
  ends it accepts by itself, through the one audited accept (`finddocs.accept-makes-groups`), the
  documents at least as sure as its setting (95% unless the run says otherwise, `finddocs.recipe-step`);
  a run with `accept_above: null` changes nothing and leaves every proposal for a person. **Built
  2026-10-07 (engine):** `POST /api/find-documents/runs` queues one `find-documents-in-a-folder` job
  (`finddocs/job.py`, images lane): each folder's loose pages in its order, read from the page's text or
  its best reading, the thumbnail's ink and look, and the knowledge graph's people on the page; the
  proposal is stored as a `grouping` artifact on the folder (the existing hypothesis store). A later run
  on any of the same pages supersedes the folder's earlier proposal (built 2026-10-10, below). Pinned by
  `fichero-server/tests/unit/finddocs/test_find_documents_to_spec.py`. **Built 2026-10-10 (app):** Find
  the Documents in the context menus of a folder or a selection of pages (library and sidebar).
- `finddocs.boundaries.proposed-with-evidence` — **[PARTIAL]** (#5550) every proposed start or end of a
  document carries its signals (cue lines, continuity score, furniture, look, parties) and a
  confidence. **Built 2026-10-07 (engine):** every join between written pages has a probability and
  its named signals, from one cue table (`finddocs/cues.py`, Spanish and English rows; a language adds
  rows): opening cues at the page's head (court caption, VISTOS, Sentencia, Demanda, Poder, Audiencia,
  salutations, Telegrama/Cable, Recibo, place-and-date lines), closing cues at the foot of the page
  before (Cópiese/notifíquese, "(fdo)", letter closings), folio numbers restarting or running on, and a
  sentence or a word running over the break (the cheap rule: page n ends mid-sentence and n+1 starts in
  lower case). Each document's confidence is the least sure of its start, its end and its inner joins.
  *Not built: the look of the page (an image embedding), a language model's surprise at the join.*
- `finddocs.kinds.prototypes` — **[PARTIAL]** (#5550) each proposed document is matched to a prototype or
  proposes a new one, and its attribute values are filled from the pages and cited to them. **Built
  2026-10-07 (engine):** the kind is the strongest opening cue's (VISTOS: Sentencia; a salutation:
  Carta or Letter; Telegrama: Cable), else a ruling or closing cue's; it is proposed as a prototype key,
  made on accept when the project has none of that name. *Not built: attribute values filled and cited.*
- `finddocs.groups.and-order` — **[PARTIAL]** (#5550) documents are proposed into groups by shared
  parties, case numbers, dates and replies, each group with an order and its reasons. **Built
  2026-10-07 (engine):** parties are read after "contra", "demandante", "demandado", "v.", a letter's
  addressee and its signer, and the knowledge graph's people and organisations on the page; documents
  sharing two parties are one group (one shared party, such as a company sued four times, is not a
  case), ordered by their dates, with reasons. *Not built: case numbers, replies ("en contestación a").*
- `finddocs.canvas.drawn` — **[GAP]** (#5550) proposals are drawn on the 2D canvas: a document's
  pages together in order, a group as a labelled region, uncertainty visible. (Accepting arranges the
  folder's canvas in the documents' order, `finddocs.accept-makes-groups`; drawing the proposals before
  they are accepted is the app's next slice.)
- `finddocs.accept-makes-groups` — **[PARTIAL]** (#5550, #5303) accepting a document makes a group node of
  its pages with its prototype; accepting a group makes a group of documents with a named order;
  audited; undone by Ungroup. **Built 2026-10-07 (engine):** one audited action, `finddocs.accept`
  (`POST /api/find-documents/proposals/{id}/accept`: all, the ones named, or those above
  `min_confidence`), groups each document's pages with the Group command's code, assigns its prototype
  (made if missing, the classifications code), groups the documents of a fully accepted group, and
  arranges the folder's canvas (the Arrange code); one undo of its audit row (`finddocs.unaccept`)
  restores the folder, the prototypes and the canvas; redo accepts again. Pinned by
  `fichero-server/tests/unit/finddocs/test_find_documents_to_spec.py`. **Built 2026-10-10 (engine):**
  every kind it writes, on a one-page document's page and on a document's group node alike, records who
  chose it through the one attribute-sources record (`metadata.attribute_sources.prototype`,
  `workflows/attribute_sources.py`): a person's accept records the run's proposal with `accepted_by` the
  person. **Built 2026-10-10 (engine, the ruling above):** the run's own auto-accept takes boundaries only:
  each document's kind is left as a proposed kind on its node, citing the run (machine: its proposal, its
  run and its method), through `attribute_sources.propose_prototype`, never over a person's kind; proposed
  cases are made only on a person's accept. Accept refuses in words (409), changing nothing, a
  document any of whose pages is no longer a loose page of the proposal's folder (grouped, moved or
  deleted since; a page cut from a photograph, whose parent is the photograph, is a loose page), naming
  the document and the page, and a proposal a later run superseded (`state` "superseded",
  `superseded_by`): a later run on any of the same pages supersedes it, and the folder's listing
  (`GET /api/find-documents/proposals`) leaves superseded proposals out unless `include_superseded` is
  asked for, so the Inspector never lists the same pages twice. Undo restores the kinds' records too.
  Pinned by `test_finddocs_run_accept_is_boundaries_only`,
  `test_finddocs_person_accept_records_the_person`, `test_finddocs_accept_refuses_pages_grouped_since`,
  `test_finddocs_pages_cut_from_a_photograph_accept_and_refuse` and
  `test_finddocs_a_second_run_supersedes_the_first` in the same file. **Built 2026-10-10 (app):** Find
  the Documents on a folder or a selection (library and sidebar menus); a folder's Inspector lists the
  documents still proposed (pages, kind, confidence, reasons) with Accept, Reject and Accept All at least
  95/90/80/70% sure, through the same actions; pinned by `fichero/Tests/Unit/general/Models/FoundDocumentsStoreTests.swift`.
  *Not built: proposals drawn on the canvas (`finddocs.canvas.drawn`).*
- `finddocs.adjust` — **[OK]** (#5550) before accepting, a person can adjust a proposal: split a proposed
  document at a page, join a document to the next, or move a document's first page to the document before
  it or its last page to the document after it. An adjustment changes the stored proposal only (no node in
  the library changes): the documents are renumbered in the folder's order, each document an adjustment
  touched says the person set it (`adjusted_by`, its confidence 1.0, no machine score, a reason naming what
  the person did), a proposed group keeps the documents it held (a split document's halves both, a joined
  document once), and each adjustment adds its labelled examples (`finddocs.corrections-teach`). Each is one
  audited action (`finddocs.split`, `finddocs.join`, `finddocs.move_page`; `POST
  /api/find-documents/proposals/{id}/split|join|move-page`), undone exactly by one undo of its audit row
  (`finddocs.unadjust`: the documents, groups and examples as they were) and redone by undoing that.
  Refused in words, changing nothing: a document index or page out of range, a split at a document's first
  page, a move that would empty a document (join it instead) or has no neighbour (422); a proposal a later
  run superseded, a document already accepted or rejected, or one whose pages are no longer the folder's
  loose pages (409). Accepting afterwards makes the adjusted documents. Pinned by
  `fichero-server/tests/unit/finddocs/test_find_documents_adjust.py`. **Built 2026-10-10 (engine).**
  **Built 2026-10-11 (app):** the Items pane's review (`finddocs.review.items`). *Not built: moving a card on
  the canvas (`finddocs.canvas.drawn`).*
- `finddocs.undo-keeps-later-work` — **[OK]** (#5698) undoing one answer on a proposal (an accept, a reject,
  a split, a join, a page moved) takes back only what that answer changed and keeps every later answer: an
  accept's or a reject's undo puts back the documents and groups it decided, each only while it still holds
  what that answer left; when a later answer changed one of them, or an adjustment's proposal has changed since
  (an adjustment renumbers the documents, so it is undone whole or not at all), the undo is refused in words
  (409, `reason: changed`), changing nothing, and says to undo the later answer first. An answer recorded
  before this rule that cannot be told apart from later ones is refused the same way, never guessed. Reject
  answers with its `audit_id`, as accept and the adjustments do. WHY (2026-10-11, the MCP walk): accept
  document 2, reject document 0, undo the accept, and document 0 was back to proposed (every answer was saved
  as a snapshot of the whole proposal and put back whole). Tested in
  `fichero-server/tests/unit/finddocs/test_undo_keeps_later_answers_5698.py`.
- `finddocs.review.items` — **[PARTIAL]** (#5550) after a run, a folder's Items list shows each document still
  proposed as a proposal, never as a document: one row per proposed document, marked Proposed with a dashed
  outline, its name, its pages ("Pages 3–5"), its kind and how sure the run was, holding its pages beneath it
  (disclosed as a document's pages are); a page the proposal puts in no document stays a loose page. A
  document a person or the run accepted is an ordinary group row; a rejected one leaves its pages loose. The
  person answers in place, by the row's menu, one at a time or for every proposed row selected at once:
  Accept, Reject, and the adjustments that change which pages belong: Split Here (on a page: it starts a new
  document), Join with Next, Move First Page to the Previous Document and Move Last Page to the Next Document.
  A page is taken out on its own by splitting before and after it and rejecting the one-page document. Each
  is the engine's audited action (`finddocs.accept`, `.reject`, `.split`, `.join`, `.move_page`, through
  `POST /api/actions/invoke`), and one answer, even over several proposals, is one ⌘Z step (`undo.batches`)
  undone by the engine's inverse; after it and after its undo the folder's proposals and contents are read
  again, so the list is what the engine holds. A refusal is said in the engine's words. The folder's
  Inspector offers the same answers and Accept All at least 95/90/80/70% sure, through the same actions.
  **Built 2026-10-11 (app):** `FoundDocumentsStore` (the actions and their one step) and the Items rows
  (`LibraryOutlineNode.proposedDocument`); pinned by `fichero/Tests/Unit/general/Models/FoundDocumentsStoreTests.swift`
  and `fichero/Tests/Unit/general/Models/ProposedDocumentsInItemsTests.swift`. **Built 2026-10-11 (app):** List
  heads a proposal's pages with its row (the dashed mark, name, pages, kind and how sure) at its first listed
  page, and Icon marks every page of one with the dashed Proposed mark, each with the same menu
  (`ProposedInItems`). The proposals are read when the folder is shown and again, with every folder read so
  far, whenever a Find the Documents run ends, the menu's or a recipe run's step: the jobs read the app
  already makes sees it leave the list or fail (`ActivityStore.findDocumentsRunsEnded`); pinned by
  `fichero/Tests/Unit/general/Models/FindDocumentsRunEndsTests.swift`. **Built 2026-10-11 (app):** Columns
  marks each page of a proposal in the folder a column lists with the dashed Proposed mark and its menu,
  reading that folder's proposals when the column opens (`MillerColumnModel.folder(atDepth:path:)`, pinned by
  `fichero/Tests/Unit/general/Views/Library/MillerColumnModelTests.swift`). *Not built: List on iPhone and iPad.*
- `finddocs.review.setup-page` — **[OK]** (#5550, #5668) Set Up's Organise page says what the stage will
  do in the engine's words, and how a run answers: documents at least as sure as the project's level are
  applied by the run (none until the level is switched on, `finddocs.recipe-step`), every other one is
  proposed for the person to confirm in Items. Trying it shows the grouping it proposes on a run of
  consecutive pages (`GET /api/recipes/samples?stage=organise`, `source.onboard.stages.organise-tried-on-a-run`):
  the run as a strip of thumbnails, each proposed document a dashed group over its pages with its name, kind
  and how sure (its reasons on hover), and the entries Split into entries found listed under the pages they
  open on. **Built 2026-10-11 (app):** the page's words (`SetupStagePage.howItAnswers`); the stage's own
  samples (`SetupStageTryStore.load`); the strip (`OrganiseTryStrip`, laid out by `OrganiseTryLayout` from the
  try's `pages`, `documents` and `entries`). Pinned by
  `fichero/Tests/Unit/general/Models/ProposedDocumentsInItemsTests.swift` and
  `fichero/Tests/Unit/general/Models/OrganiseTryStripTests.swift`.
- `finddocs.review.activity` — **[OK]** (#5550, #5670) a recipe run's details say, under its Organise stage,
  how many documents the run proposed and how many it applied: "N documents proposed, M applied", from the
  run's summary (`documents_proposed`, `documents_accepted`); the engine counts, the app only words it.
  **Built 2026-10-11 (app):** `ActivityDetails+RunStages.made`; pinned by
  `fichero/Tests/Unit/general/Models/ActivityStageCardsTests.swift`.
- `finddocs.corrections-teach` — **[PARTIAL]** (#5550) every accept, reject and adjustment is kept as a
  labelled example for the project. **Built 2026-10-07 (engine):** accepted and rejected documents keep
  their state on the stored proposal (`finddocs.reject`, undoable). **Built 2026-10-10 (engine):** each
  accepted or rejected document, and each accepted group, records who decided it (`decided_by`: the run
  that made the proposal, accepting by itself, or the person), so a person's answer can be told from the
  run's; a superseded proposal is kept with its answers. Pinned by
  `test_finddocs_run_accept_is_boundaries_only` and
  `test_finddocs_person_accept_records_the_person`. **Built 2026-10-10 (engine):** each adjustment
  (`finddocs.adjust`) appends to the proposal's `examples` one labelled example per join it decided: the
  two pages (`left_page_id`, `right_page_id`), `boundary` true (a document starts at the right page) or
  false (they are one document), the adjustment, who decided it (`decided_by`, the person), when (`at`),
  the proposal, and what the run had said of that join (`run_probability`, `run_reasons`, its named
  signals). A split records a boundary; a join records no boundary; a move records both (no boundary
  between the moved page and its new neighbour, a boundary between it and the page it left). Undoing the
  adjustment removes its examples. Pinned by `test_find_documents_adjust.py`. *Not built: the states and
  examples exported as training examples.*
- `finddocs.recipe-step` — **[OK]** (#5550) onboarding organises by itself: a recipe that reads a project
  of loose pages has the step "Find documents in a folder" after reading, names and dates (ruled 2026-10-10:
  parties group the documents, dates order them; `recipes/assemble.STEP_ORDER`),
  run as background work. **Built 2026-10-07 (engine):** setup's answer `loose_pages` adds it (unset, it
  is on when the open project holds a folder of loose page images, as "Everything automatic after
  Start" lays out for a box); Start runs it as its own card (`find-documents`) under the recipe's row.
  **Default (ruled 2026-10-10, replacing 2026-10-08's 95%):** the auto-accept is off until a box a person
  broke down is scored and shows boundaries at least 99% right; until then Find the Documents proposes
  every document for a person. One setting, `finddocs.AUTO_ACCEPT_ABOVE` (None today): the recipe step's
  `accept_above` (the project's setting) and the run's own default (`POST /api/find-documents/runs` with
  `accept_above` left out, so the MCP tool and the CLI command generated from it). A run given a level
  accepts boundaries at least that sure; one undo restores what it accepted. Pinned by
  `fichero-server/tests/unit/recipes/test_find_documents_step.py` and
  `fichero-server/tests/unit/finddocs/test_find_documents_to_spec.py::test_finddocs_proposes_only_by_default`.
  **Lines and priority (#5709):** a page is read as its lines: a page text derived from line readings (joined with
  spaces for the Reader's offsets) is split back into its lines by the page's line map, so a folio, an opening or a
  closing is found on its line. The step runs at utility QoS whoever waits on it (its work is light: a thumbnail
  and the text of each page). WHY: after a fresh line-by-line read every page was one line, no numbering restart
  was seen, and a folder of four documents was proposed as one; and the step, a recipe's unwatched child at the
  BACKGROUND class, took 27 minutes beside an import's all-core embedding where alone it took one. A proposal's
  `leaves` counts leaves, not pages: a blank verso or a second shot travels with its leaf (89 leaves of 92 pages).
  Two documents whose weakest join has the same evidence (a numbering restart alone) have the same confidence.
  Pinned by `fichero-server/tests/unit/finddocs/test_reads_lines_and_runs_at_utility_5709.py`.
- `finddocs.teacher-on-uncertain` — **[GAP]** (#5550) a thinking vision-language model is asked only
  about uncertain boundaries, kinds or groups, with its reasons kept; never about all pages by
  default; the egress gate applies.
- `finddocs.student-model` — **[GAP]** (#5550, #5539) with enough examples the project trains its own
  boundary-and-kind model (distillation.md), held out by box, scored, kept in the project.
- `finddocs.scored` — **[PARTIAL]** (#5550) a run against a person's breakdown reports boundary precision
  and recall, exact documents, kind accuracy and group agreement. **Built 2026-10-07 (engine):**
  `propose.score` gives boundary precision and recall and exact documents against a known answer.
  **Built 2026-10-10 (engine):** scoring is a stored measurement of a folder. A person's breakdown of a folder
  is the documents a person set on its proposal: those a person accepted (`decided_by` a person) and those a
  person adjusted (`adjusted_by`), rejected ones left out (a rejection says the run was wrong, not where the
  document runs). `POST /api/find-documents/score` (`finddocs.score`, audited; a measurement, so not
  undoable: it changes nothing but the record it adds) scores the folder's newest current proposal, or the
  one named, from the run's own call at each join (`joins`, kept as the run made them; an adjustment never
  changes them): a join is judged when either page is in one of the person's documents, a boundary when its
  two pages are not in the same one. It reports boundary precision and recall over the judged joins, exact
  documents (a person's document whose start and end the run called and inside which it called none), kind
  accuracy over the kinds confirmed (a document a person accepted whose node still has a kind: right when
  that kind is the one the run proposed; changed since, a correction), and, the number the auto-accept
  ruling needs, the run's agreement at each confidence level (0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 0.99): of the
  judged joins the run was at least that sure of (a boundary's probability, or one minus it for "runs on",
  the certainty a document's confidence is the least of), how many and how many the person agreed with. The
  score is kept as one `finddocs_score` artifact on the folder, with the proposal, its run, the date and who
  scored it; every score is kept. `GET /api/find-documents/score?folder_id=` lists the stored scores, newest
  first, with `suggested_accept_above`: pooling the newest score of every folder in the project, the lowest
  level whose joins were at least 99% agreed over at least 50 of them (`score.MIN_JOINS`: at 50 joins 99%
  allows no miss; a level only 95% right would pass 20 joins with none a third of the time), null until
  then. The suggestion never switches the auto-accept on: `finddocs.AUTO_ACCEPT_ABOVE` stays None and a
  person turns it on at the suggested level (that setting's surface is a later slice). Refused in words,
  changing nothing: a folder with no proposal, or none of whose documents a person accepted or adjusted
  (422); an unknown proposal (404). Pinned by `fichero-server/tests/unit/finddocs/test_find_documents_score.py`.
  *Not built: group agreement; the app's surface for the score and for turning the auto-accept on.*
- `finddocs.known-answer-first` — **[PARTIAL]** (#5548, #5550) the method is checked on the Voynich
  conjugate leaves and one public page-stream set before it is offered on a real box. **Built
  2026-10-07:** two synthetic boxes with a known answer and no real text
  (`fichero-server/tests/unit/finddocs/boxes.py`): the Istmina '1948 Sentencias' structure (eight
  judgments, blank versos, two leaves shot twice, four cases against one company) scores precision 1.0,
  recall 1.0, 8 of 8 documents exact; a bundle of letters, cables and a receipt in Spanish and English
  scores 1.0 and 1.0, 7 of 7, with both correspondences grouped. Pinned by
  `fichero-server/tests/unit/finddocs/test_find_documents_known_answer.py`. *Not built: the Voynich
  conjugate leaves, a public page-stream set, and the real box broken down by a person.*
- `finddocs.leaves-first` — **[PARTIAL]** (#5550) images pair into leaves (recto/verso) before boundaries
  are proposed; blank versos, duplicate shots and leaves seen only as bleed-through are reported as
  findings, not documents. **Built 2026-10-07 (engine):** a near-blank page (short reading, and little
  ink in its thumbnail) right after a written one is its verso; a written page whose text is at least
  90% the same as one of the last six is a second shot (its thumbnail's hash is named as support); a
  page with ink and no reading is reported; all travel with their leaf's document. Before reading, a
  blank verso as its image shows it is left out of finding lines and reading (#5579; a recipe run's
  reading cards, `runner._NOT_ON_BLANK_VERSOS`). *Not built: leaves seen only as bleed-through, mirrored
  bleed-through matched to its recto.*
- `finddocs.inserts-are-ranges` — **[GAP]** (#5550) a document copied inside another (a complaint
  inside a judgment) is proposed as a text range with its own prototype, not as a group of pages.
- `finddocs.mcp-cli` — **[PARTIAL]** (#5568, #5550) the job, its proposals, accept/reject and a picture of
  the canvas are MCP tools and CLI commands from the same routes. **Built 2026-10-07:** the
  `/api/find-documents/*` routes are generated into the MCP (the `find-documents` toolset, on by default)
  and the CLI; the canvas picture is #5568's. *Not seen: an agent driving it end to end on a real box.*

## Open questions

1. Prototypes per project or shared across a collection (the Istmina boxes share Sentencia,
   Demanda …)? Proposal: per project, promotable to the collection, like models (#5539).
2. Which thinking model is the default teacher, and the cost ceiling per box before asking.
3. The base for the student: a layout model (text + boxes + image) or a small vision-language model
   — to be decided by the first bake-off on the Istmina box.

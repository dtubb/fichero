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

- `finddocs.job.any-box` — **[GAP]** (#5550) Find the Documents runs on any folder or selection of
  pages as one background job and stores proposals; it changes nothing in the source.
- `finddocs.boundaries.proposed-with-evidence` — **[GAP]** (#5550) every proposed start or end of a
  document carries its signals (cue lines, continuity score, furniture, look, parties) and a
  confidence.
- `finddocs.kinds.prototypes` — **[GAP]** (#5550) each proposed document is matched to a prototype or
  proposes a new one, and its attribute values are filled from the pages and cited to them.
- `finddocs.groups.and-order` — **[GAP]** (#5550) documents are proposed into groups by shared
  parties, case numbers, dates and replies, each group with an order and its reasons.
- `finddocs.canvas.drawn` — **[GAP]** (#5550) proposals are drawn on the 2D canvas: a document's
  pages together in order, a group as a labelled region, uncertainty visible.
- `finddocs.accept-makes-groups` — **[GAP]** (#5550, #5303) accepting a document makes a group node of
  its pages with its prototype; accepting a group makes a group of documents with a named order;
  audited; undone by Ungroup.
- `finddocs.corrections-teach` — **[GAP]** (#5550) every accept, reject and adjustment is kept as a
  labelled example for the project.
- `finddocs.teacher-on-uncertain` — **[GAP]** (#5550) a thinking vision-language model is asked only
  about uncertain boundaries, kinds or groups, with its reasons kept; never about all pages by
  default; the egress gate applies.
- `finddocs.student-model` — **[GAP]** (#5550, #5539) with enough examples the project trains its own
  boundary-and-kind model (distillation.md), held out by box, scored, kept in the project.
- `finddocs.scored` — **[GAP]** (#5550) a run against a person's breakdown reports boundary precision
  and recall, exact documents, kind accuracy and group agreement.
- `finddocs.known-answer-first` — **[GAP]** (#5548, #5550) the method is checked on the Voynich
  conjugate leaves and one public page-stream set before it is offered on a real box.
- `finddocs.leaves-first` — **[GAP]** (#5550) images pair into leaves (recto/verso) before boundaries
  are proposed; blank versos, duplicate shots and leaves seen only as bleed-through are reported as
  findings, not documents.
- `finddocs.inserts-are-ranges` — **[GAP]** (#5550) a document copied inside another (a complaint
  inside a judgment) is proposed as a text range with its own prototype, not as a group of pages.
- `finddocs.mcp-cli` — **[GAP]** (#5568) the job, its proposals, accept/reject and a picture of the
  canvas are MCP tools and CLI commands from the same routes.

## Open questions

1. Prototypes per project or shared across a collection (the Istmina boxes share Sentencia,
   Demanda …)? Proposal: per project, promotable to the collection, like models (#5539).
2. Which thinking model is the default teacher, and the cost ceiling per box before asking.
3. The base for the student: a layout model (text + boxes + image) or a small vision-language model
   — to be decided by the first bake-off on the Istmina box.

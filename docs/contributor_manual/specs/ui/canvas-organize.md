# Canvas Organize — arranging an archive on the canvas — Design Spec (#4192)

> Milestone: canvas-organize
> Manual: TBD — a section of "Organising a project": what can be put on a board; grouping, ordering
> and connecting by hand; sets that hold related things without moving them; what the app proposes
> from the paper itself (outlines, overlaps, torn edges, holes and stains) and how to accept or
> reject a proposal; that the filed order is never lost.
>
> Design-led (Testing Constitution). The creative director owns this intent; tests enforce it;
> code makes them pass. **Status: DRAFT — awaiting approval before tests/code.**
> Direction given 2026-11-26 (paraphrased throughout). This file is the ORGANIZING slice of the
> canvas. `library-view-modes.md` §I stays the owner of the board itself (cards, places, camera,
> zoom, drag, Group and Ungroup, Arrange By); `../source/finding-documents.md` stays the owner of
> Find the Documents (boundaries, kinds, cases). Neither is restated here. This file adds the
> relations between things, the sets that hold them, the tools that make them by hand, the
> proposals a model draws, and the recognizers that read the physical sheet. Ids here are
> `canvas-organize.*`.
> Tags: [OK] built · [PARTIAL] exists in part / not wired · [GAP] not built · [BROKEN] seen fail.

## Intent

A researcher in a box of loose papers keeps finding the same things: two halves of one sheet; the
second page of a letter three folders away; a reply and the letter it answers; an enclosure parted
from its cover letter; a draft and its fair copy; pages bound or photographed out of order; a sheet
filed in the wrong place. Today the canvas lets them move cards and stack pages into one document.
It has no way to say *how* two things relate, to keep several orders side by side, or to hold a
correspondence together without moving its letters out of the folders they were found in.

The canvas becomes the place an archive is organized by eye and hand, the way the segment editor
is the place a page's layout is corrected: one selection, a handful of tools, a modifier for the
next most common thing, no dialog on the way. A researcher groups, orders and connects by
dragging; a model can propose the same groups, orders and connections, drawn apart from the
researcher's own, each with its evidence, and nothing a model proposes takes effect until a person
accepts it. Part of that evidence is the paper: the outline of a sheet, one sheet lying on another
in a photograph, torn edges that fit, and holes or stains that pass through several sheets.

Three rules hold everything below:

1. **The filed order is a fact and is never lost.** Organizing adds relations, sets and orders
   beside the place and order a thing was found in. Only Move and Group change where a thing is
   filed, and both are undone whole.
2. **A relation is one typed link.** Every line on a board is the engine's `TypedLink` with a key
   from the library's one vocabulary. The app keeps no word list of its own.
3. **A proposal is a hypothesis with evidence.** It is drawn as a proposal, names its method and
   score, shows what it saw, and is accepted or rejected by a person. Rejections are remembered.

The surface lives in `Views/Library/ViewModes/Canvas/**` (the board), a new
`Views/Library/ViewModes/Canvas/Organize/**` (toolbar, tools, proposal layer), the engine's
`models/typed_links.py`, `models/canvas.py`, `models/reading_orders.py`, `finddocs/**`, and a new
`fichero_server/physical/**` for the recognizers.

## What exists today (read on disk 2026-11-26)

**Specified and built on the board** (`library-view-modes.md` §I): places persist per folder scope
(`CanvasLayout`); one canvas in the Library and the Preview; Group makes a `DocType.group` node (a
document made of pages) and Ungroup restores each page to its place; a group lists, previews and
reads as one document; Arrange By (As Filed, Name, Type, Date); a drop on a container moves in;
an ⌥-drop draws an untyped line. Mostly [PARTIAL]: tested, not all seen in the app.

**Specified, not built** (`library-view-modes.md` "Arrangements that propose", #5550; #4192):
arrange by similarity, a model proposing groups, orders beside the filed one, pieces of one
document drawn joined, adornments, typed links with labels, aliases, notes and text on a board
(the store exists, nothing calls it).

**The organize step** is Find the Documents (`../source/finding-documents.md`): an engine job and
recipe stage that proposes document boundaries, kinds and cases from text cues, page furniture,
look of the page, shared names and reply phrases; it pairs rectos with versos and reports second
shots. Proposals are stored as hypotheses and accepted into group nodes. Drawing them on the
canvas (`finddocs.canvas.drawn`) is a gap; review today is a list.

**Relation and grouping kinds in the data model with no way to make them on a board:**

| Record (table) | Holds | Kinds it carries | Reachable today |
|---|---|---|---|
| `TypedLink` (`typedlinks`) + `LibraryLinkType` | one typed, directed, attributed link with certainty; ends may be segment, note, document, claim, canvas item, entity, URI | 10 from the knowledge graph (supports, contradicts, refines, duplicate of, corroborates, derives from, cites, follows, caused by, related to), 16 source kinds (glosses, comments on, answers, quotes, expands, reorders, marks, captions, labels, continues, translates, same as, different from, names, interprets, controls), 2 legacy (next, related) | the Inspector lists a segment's links; routes, MCP and CLI create them between segments and to entities; nothing draws or makes one on a board |
| `ReadingOrder` / `ReadingOrderEntry` | a named order over segments, fractional positions, nesting | as-written, imposed, commentary, **flow** (the one kind that crosses pages), project terms | the segment editor's Order tool, inside one page; a flow has no surface |
| `LibraryItemLink` | a link between any two of document, note, entity, claim | the knowledge graph's 10 | routes only |
| `SpatialConnection` | a line between two nodes of a room | evidentiary, semantic, ontological, hermeneutic, user drawn, with a free subtype | drawn in the 3D space |
| `CanvasItem` | a note, quote, work note, text or **link** placed on a folder's board | — | store with create, update, delete; no control calls it |
| `NoteLink`, `PredictionLink` | links between notes; between predictions | follows, references, contradicts, supports, free; next logical | notes only |
| `DocType.group` | a document made of pages; a group of groups (an accepted case) | — | Group / Ungroup; nesting drawn (`CanvasGroupNesting`) |
| Swift `LinkType` | the app's own list for colouring a line | citation, mentions, depicts, related, contradicts, supersedes, parent-child, user drawn | a sixth word list that matches none of the engine's |

The source model already ruled that these converge on `TypedLink` and that a line drawn on a canvas
is that record with a position (`../source/segments-and-geometry.md` "Links", "On the canvas";
`source.link.typed`, #4931, which left the canvas half to this spec). The zones-and-relationships
layer planned in `../source/archival-data-model-plan.md` P5 (#4639: reply-to, continues, part-of
across documents) is this spec.

**Physical evidence** is specified only in passing: `../source/undeciphered-scripts.md` §12 records
leaves, conjugate bifolia and quires and names stains and offsets as adjacency evidence;
`../source/image-enhancement.md` finds the page box (page-crop) and treats holes, stains and
show-through as things to clean. Nothing matches one sheet to another by its shape or damage.

## Prior art (what is adopted, what is done differently)

**Archival arrangement.** *Respect des fonds* has two halves: provenance and original order. The
order a body of records was kept in is evidence and is preserved even when a more useful order is
made. ISAD(G) describes from the general to the specific (fonds, series, file, item) and keeps
physical and intellectual arrangement distinct. Adopted: rule 1 above; a set's kind may be a level
(series, file); an order made here is always a second order beside the filed one.
Records in Contexts (ICA, RiC-CM and RiC-O 1.x, <https://www.ica.org/standards/RiC/ontology>)
replaces the single hierarchy with a graph and names the relations wanted here: *is copy of*, *is
draft of*, *is original of*, *replies to*, *precedes / follows* in a sequence, *is part of*, *is
included in* a record set. Adopted: the new link kinds below take RiC's meanings and export to its
terms (the exact RiC-O property names are checked against the ontology file when the export is
built).

**IIIF.** Presentation 3 (<https://iiif.io/api/presentation/3.0/>) gives a Range for a structure
or an alternative order over Canvases (the `sequence` behaviour marks a Range as a reading order
other than the Manifest's own) and a Collection for a set of Manifests; one Canvas may sit in many
Ranges. Adopted: an order exports as a Range, a set as a Collection (`../source/iiif.md` already
maps folders). Change Discovery (<https://iiif.io/api/discovery/1.0/>) publishes changes as an
ordered activity stream; adopted only as the shape a shared library's organizing changes take if
they are ever published, not built here.

**TEI.** `correspDesc` / `correspContext` (`ref type="reply"`), `msDesc/physDesc/collation`, and
`join` for a text divided across witnesses. Adopted for export. VisColl (Schoenberg Institute,
<https://viscoll.org>) models leaves, conjoins and quires and draws the collation; adopted as the
model `undeciphered-scripts.md` already names, not rebuilt here.

**Reuniting fragments.** The Friedberg Genizah Project's join finder (Wolf, Littman, Mayer,
German, Dershowitz et al., "Identifying Join Candidates in the Cairo Genizah", *IJCV* 2011,
<https://cris.tau.ac.il/en/publications/automatically-identifying-join-candidates-in-the-cairo-genizah/>)
ranks fragment pairs by handwriting similarity and physical measurements (line spacing, margins,
dimensions) and hands candidates to a scholar; nothing is joined unreviewed. Hand-torn paper is
matched by partial contour matching of the torn edges, then a global step that resolves conflicts
(Kleber & Sablatnig's survey of document reconstruction; Zhu, Zhou & Hu on ripped-up documents;
the bdw082010 torn-page set as a benchmark). Fragmentarium (<https://fragmentarium.ms>) reunites
dispersed leaves as IIIF. Adopted: candidate ranking, then a person; cheap descriptors before
contour matching; the two-stage shape.

**Order from damage.** The Stegemann method reconstructs a rolled scroll from damage that repeats
through its layers, each repeat a little smaller or further along (Stegemann, "Methods for the
Reconstruction of Scrolls from Scattered Fragments", 1990; summarised in
<https://amacad.org/news/jigsaw-puzzles-paper-doll-chains-and-computers-material-reconstruction-dead-sea-scrolls>).
Codicologists use worm tracks, rust from pins and stains the same way for leaves; a Folger imaging
note aligns worm holes across two leaves to recover how they lay
(<https://www.folger.edu/blogs/collation/following-a-worm/>). The standing caution, adopted in the
proposal's wording: damage shows how sheets lay **when the damage happened**, which may be after a
rebinding or a refiling, never by itself the original order.

**Overlapping sheets in one photograph.** No standard method was found; this is designed here from
the page finder (two outlines in one frame, one of them interrupted) and is marked as ours.

**Papyrology at scale.** The Oxyrhynchus papyri are the hard case: about half a million fragments
dug from ancient rubbish mounds, most unedited, held by many institutions, with no original order
to recover. Ancient Lives (Zooniverse and Oxford, 2011 to 2018) had volunteers mark each letter on
an image; Williams et al., "A Computational Pipeline for Crowdsourced Transcriptions of Ancient
Greek Papyrus Fragments" (IEEE Big Data 2014, <https://acwio.github.io/pubs/bhd2014.pdf>), turned
millions of clicks into consensus letters and lines, and a companion paper (IEEE eScience 2014,
<https://acwio.github.io/pubs/escience2014.pdf>) identified damaged texts by aligning the
consensus string against known texts with the tolerant alignment used for gene sequences.
Papyrologists identify a literary scrap the same way by hand: a string search of the surviving
letters in a corpus of Greek literature (the Thesaurus Linguae Graecae is the usual one, under
licence), and for documents a search of formulae in the Duke Databank of Documentary Papyri at
<https://papyri.info>, which joins that databank with the Heidelberg catalogue and image records.
Trismegistos (<https://www.trismegistos.org>) gives each ancient text one stable number and keeps a
register of holding collections and their inventory numbers, so a fragment in two catalogues is
one thing. Joins on papyrus use the fibres as well as the edge: Abitbol, Shimshoni & Ben-Dov,
"Machine Learning Based Assembly of Fragments of Ancient Papyrus" (*ACM JOCCH* 2021,
<https://cris.haifa.ac.il/en/publications/machine-learning-based-assembly-of-fragments-of-ancient-papyrus/>),
score whether the thread pattern continues across two edges, then vote and align; precision is
low alone, and the reported use is to discard about 98% of candidate pairs before a person looks.
Pirrone et al., "Papy-S-Net" (HIP 2019, <https://hal.archives-ouvertes.fr/hal-02367779v1>), train
a Siamese network to say whether two patches are from one papyrus. Same-hand work has the
GRK-Papyri set (<https://d-scribes.philhist.unibas.ch/en/gkr-papyri/>) and unsupervised writer
retrieval (Christlein et al., "Writer Retrieval and Writer Identification in Greek Papyri", 2022,
<https://arxiv.org/abs/2212.07664>), which notes that the fibres themselves disturb the features.
Adopted: fibres as a second join signal beside the edge; alignment that tolerates gaps for
identification; stable identifiers from the field's own registers, never ours; every one of these
as a filter that ranks candidates for a person. Different on purpose: no corpus under licence is
bundled, and a holder's images are referenced, never copied.

**Canvas tools.** Tinderbox maps: adornments (a labelled region behind notes), typed links with
labels, aliases (one note in several places), and agents that gather. Scrivener's corkboard: the
order of cards *is* the order of the manuscript. Obsidian Canvas and the open JSON Canvas format
(<https://jsoncanvas.org>): nodes, group nodes, edges with a label and ends. Miro: frames and
connectors that follow their cards. Muse: boards inside boards, ink over everything. Kinopio:
connections that carry a named, coloured type. Adopted: a set is an adornment that remembers its
members; an item may be in many sets (the alias problem solved by membership, with no copies); the
order of a row of cards can be the order; a line carries a type and a label. Different on purpose:
every line and set is a record the engine owns, with an author and a certainty, so MCP, the
command line and export see what the hand drew.

## Concepts

### Things that can be on a board

| Thing | What it is | Data model |
|---|---|---|
| Page | one image of one side of a sheet | exists: `Document`, `DocType.page` or an image `file` |
| Fragment | an image of part of a sheet | exists as a page; **new**: its `torn-edge` segments and a `joins` link make it a fragment |
| Sheet | the paper itself, front and back, reunited if torn | **new, derived**: pages tied by `verso_of` and `joins`; never a stored node |
| Document | pages that read as one (a letter, a deed) | exists: `DocType.group` |
| Letter, deed, receipt … | a document's kind | exists: the document's prototype |
| Enclosure | a document sent inside another | exists as a document; **new** link `encloses` |
| Series, correspondence, case, file | documents that belong together, wherever they are filed | **new**: a **set** (below); an accepted Find the Documents case stays a group of groups |
| Bundle (stack) | sheets that lay together physically, in an order | **new**: a set of kind `bundle` with `stacked_on` links |
| Folder | where things are filed | exists: `DocType.folder` |
| Note, quote, text | a researcher's own card | exists: `CanvasItem` |

**A set** is the one new grouping. It is a labelled region on a board that remembers its members:
a `CanvasItem` of a new kind `set` (label, set kind, colour) and one `member_of` link from each
member. Putting a thing in a set never moves it in the library, a thing can be in several sets,
and a set can be shown on any board its members are on. A **group** remains what it is: a
container that moves its pages in and reads as one document. The choice between them is the
researcher's: Group says *these pages are one document*; a set says *these things belong
together*.

### Relations

Every relation is a `TypedLink`. Eight keys are new; the rest are already in the vocabulary. A ninth,
`attests`, comes with the large-fragment case below.

| Relation | Key | Direction, as read | Model |
|---|---|---|---|
| Reading order within a page | — | — | exists: `ReadingOrder` over segments |
| Reading order across pages | — | — | exists: `ReadingOrder` of kind `flow` (engine only) |
| Order of items (pages in a bundle, letters in a correspondence) | — | — | **new**: an item order (below) |
| Continues on | `continues` | A continues B / B is continued by A | exists |
| Halves of one sheet | `joins` | symmetric | **new**; carries the placement of one piece against the other |
| Front and back | `verso_of` | A is the verso of B / B is the recto of A | **new** |
| Replies to | `answers` | A answers B / B is answered by A | exists; shown as "Replies to" |
| Encloses | `encloses` | A encloses B / B is enclosed in A | **new** |
| Copy of | `copy_of` | A is a copy of B / B has copy A | **new** |
| Draft of | `draft_of` | A is a draft of B / B has draft A | **new** |
| Second photograph of the same side | `duplicate_of` | symmetric in effect | exists |
| Translation of | `translates` | A translates B | exists |
| Stacked with | `stacked_on` | A lay on B / B lay under A | **new** |
| Misfiled | `belongs_in` | A belongs in B (a group, set or folder) | **new**; A stays filed where it was found |
| In a set | `member_of` | A is a member of set S | **new** |
| Came after | `follows` | A follows B | exists |
| Is part of a known text | `attests` | A attests work W, lines x to y | **new** (section F); the other end is a URI |

**An item order** is a named order over documents and pages with the same properties as a reading
order over segments: a name, a kind (`physical`, `chronological`, `as-read`, project terms), an
author, a certainty, fractional positions so a move writes one row, soft delete. It belongs to a
set, a group or a folder. The filed order is the order named *As Filed*; it is read from the
library's own sort order and never copied into an order record.

**Evidence** is a small record on a link or proposal: who or what says so (a person, a recognizer
with its version, a model), a score, a short reason, and where on each end it points (a segment: a
torn edge, a hole, a line of text). A link made by hand has one row saying a person made it.

## User stories

1. Two photographs are the top and bottom of one torn page. The researcher picks Join, drags one
   onto the other, and the edges snap together; the two now move as one sheet and read as one page.
2. A correspondence is scattered through six folders. The researcher selects the letters wherever
   they are, chooses New Set, names it, and orders them by date with the Order tool. The letters
   stay in their folders; the set is one click from any of them.
3. A letter mentions an enclosed invoice. The researcher draws a line from the letter to the
   invoice and picks Encloses. The invoice's card shows the mark and the Inspector names the letter.
4. A box was photographed badly: sheets overlap, some shot twice. The researcher runs Propose ▸
   From the Paper. The board shows dashed proposals: these two frames are the same side; this
   frame holds two sheets, the upper one hiding a third of the lower; these four sheets share a
   punch hole and a stain and lay in this order. Each shows its evidence. The researcher accepts
   the ones that are right with Return and rejects the rest with Delete.
5. A sheet is plainly from another file. The researcher drags it with ⌃ onto that file's group and
   it is marked as belonging there; in its own folder it carries a badge, and nothing has moved.

## The interaction model

One toolbar sits in the canvas pane's head when the view is Canvas. Tools are single keys, as in
the segment editor; a held key springs back on release.

| Tool | Key | What a drag does | With ⌥ | With ⇧ |
|---|---|---|---|---|
| Select | V, Esc | on a card moves it; on empty board bands a selection | on a card onto a card: connect (as today) | constrains to one axis |
| Hand | H, hold Space | pans | — | — |
| Connect | C, hold C | from a card to a card draws a link; the type menu opens at the release | repeats the last type without the menu | draws from every selected card |
| Order | O | click cards in turn to number them in the current order; drag a numbered card between two others to move it | click removes the card from the order | click extends the run to every card between |
| Set | S | on empty board draws a region and makes a set of the cards inside; a card dragged in or out joins or leaves | — | adds to the set under the pointer without moving the card |
| Join | J | a card dragged to another card's edge snaps where the edges fit; the handles rotate and nudge | disables the snap | — |
| Note | N | click on empty board places a note; drag sizes a text card | — | — |

Beside the tools: **Arrange By** (existing, gains *By Order* for the current order and *By Set*);
**Show** (which link kinds, sets, orders, proposals and physical marks are drawn; a quiet board is
one click); **Order** (which named order is current, New Order…); **Propose** (below); and a
proposal counter with Previous and Next.

Commands, each also in Edit and the context menu: Group ⌘G and Ungroup ⇧⌘G (existing), New Set
from Selection ⌃⌘G, Connect As ▸ (every type that fits the two selected cards), Join ⌘J and
Unjoin, Belongs In…, Reverse Link, Remove Link ⌫, Accept ↩, Reject ⌫ on a proposal, Accept All in
Selection ⇧↩.

Drops, in one table so no two gestures compete:

| Drag a card onto | Plain | ⌥ | ⌃ |
|---|---|---|---|
| empty board | place it | — | — |
| a card | place beside it | link (type menu) | — |
| a group or folder | move in (existing) | link | belongs in (nothing moves) |
| a set's region | join the set | — | — |
| a card's edge, Join tool | join | place, no snap | — |

What is drawn. A link is a line with an arrowhead when directed, its label at the middle when the
zoom allows, and a style per family: sequence (continues, follows, item order) solid; pieces of
one sheet (joins, verso) double; correspondence (replies, encloses) solid with a round start;
versions (copy, draft, translation, duplicate) dashed; physical (stacked) dotted; misfiled a
hooked arrow. Colour is never the only signal. A set is a rounded region with its label and count
at the top left. A bundle draws as a fanned pile in stacking order and opens to a row. An order
draws as numbers on the cards and a faint path. A proposal draws in the one proposal style
(dashed, the proposal tint, a confidence mark) and never in a link's own style.

iPad: a finger pans and moves, the Pencil draws with the current tool, a long press on a card
starts a connect. iPhone: no board; an item's relations, sets and proposals are a list in its
Inspector with the same Accept and Reject.

## Proposals

A proposal is what a recognizer or a model thinks is true, held apart until a person answers.
Find the Documents already stores its proposals this way; these join the same store and the same
review, so there is one list of things waiting for an answer.

- **Run.** Propose ▸ offers: From the Paper (the physical recognizers), Pieces of One Sheet, Order,
  Replies and Enclosures, Copies and Drafts, Sets, Layout. It runs on the selection or the board's
  scope as an Activity job, local by default; a paid model is offered with its estimate and never
  starts by itself.
- **Draw.** Each result is drawn where it applies: a dashed line between two cards, a ghost region
  for a set, ghost numbers for an order, ghost cards for a layout. No card moves and nothing is
  written to the library's links, sets or orders.
- **Evidence.** Selecting a proposal opens the evidence strip under the board: what was compared,
  side by side, with the method, its version and the score. A proposal with no evidence to show is
  not offered.
- **Answer.** Accept writes the link, set, order or group as a person's decision that records the
  proposal it came from. Reject records the pair so it is not offered again. Adjust (move a card,
  change the type, redo the fit) is an accept of what was adjusted. Each is one undoable action.
- **Never silent.** A run accepts nothing. There is no threshold above which these are accepted
  until a recognizer has been scored on a box a person organized (the rule Find the Documents
  already follows for boundaries).

## The physical recognizers

Each reads marks on the image, stores them as segments in a machine pass so they can be seen and
corrected in the segment editor like any other segment, then compares marks between sheets. All
run in the engine, locally, with OpenCV; none needs a paid model.

| Recognizer | Needs | Finds | Proposes | Shows as evidence |
|---|---|---|---|---|
| **Sheet outline** | the page finder's outline (`prep.find-the-page`), rectified for the camera's angle; a ruler or colour card in frame for true size, else relative size | the sheet's outline as a `sheet-outline` segment; a descriptor: proportions, corner cuts, the edge profile | `duplicate_of` (same side shot twice); `verso_of` (the mirrored outline, supported by show-through) | the two outlines laid over each other, the mirror stated, the residual |
| **Overlap** | the page finder returning more than one outline in a frame | which sheet is on top (its outline is whole; the lower one's is interrupted and resumes), the hidden area | split the frame into one page per sheet (the existing split step); `stacked_on`; a finding "part of this sheet is covered, re-photograph" | the frame with each outline drawn, the hidden part hatched |
| **Torn edge** | sheet outlines; which stretches are straight (cut or original) and which are irregular (`torn-edge` segments) | pairs of irregular stretches that fit, by partial contour matching, after a cheap filter on paper tone, ruling and line spacing, hand, and whether a line of writing continues across | `joins`, with the placement of one piece against the other | the two edges brought together, the gap along the fit, the lines of writing that cross it |
| **Holes and stains** | sheet outlines; holes (`hole` segments: punch, pin, worm, tear) and stains (`stain` segments) in sheet coordinates | marks at the same place on several sheets, mirrored for a verso; a regular pair or row is a filing punch; a mark that shrinks or fades from sheet to sheet gives the order | `stacked_on` between neighbours and a set of kind `bundle`; with regular punches only, the set without an order | the sheets overlaid with matched marks ringed; the size of each mark through the stack; the sentence that this is how they lay when the damage happened |

Rules for all four:

- A recognizer reports relative geometry unless the scale is known, and every proposal says which.
- The search is bounded: descriptors are indexed and only near candidates are compared in detail;
  a run on a large box is a resumable job with progress, never an all-pairs pass on the main path.
- Each is measured on a known-answer set before it is offered (pages torn and stacked
  synthetically from public images, then a public torn-page set), and each proposal carries the
  precision measured at its score.
- A person's correction to a mark (a hole redrawn, a torn edge marked as a cut) reruns only the
  comparisons that mark was part of.

## A test case at scale: an excavated dump of fragments

The design above is drawn from a box of a few hundred pages. The opposite case tests it: about
half a million papyrus fragments from one site's rubbish mounds, mostly unedited, with no order to
recover because none was ever kept, divided among many institutions, and partly transcribed
letter by letter by a crowd. Seven things change.

1. **Scale.** Nothing is compared with everything. Each fragment gets its descriptors once (outline,
   edge, fibres, hand, the letters read so far) and they go into an index that answers "the nearest
   few hundred to this one" in bounded time. A triage pass sorts fragments by what can be done with
   them. Matching runs as budgeted, resumable jobs that say how much of the scope they have
   covered. A board never holds the whole scope: it opens on a slice and says so.
2. **No original order.** A dump has a find context, not an arrangement: a dig season, a find spot,
   a box as the excavators packed it. Each is a set, sets nest, and a fragment can be in several.
   The order a holder gave its inventory is kept as *As Filed* and is labelled as the holder's
   order; nothing in the app calls it the original order.
3. **Fibres.** Papyrus is two layers of strips at right angles, horizontal on the recto and vertical
   on the verso. Across a vertical break the recto's fibres carry on; across a horizontal break the
   verso's do. Two pieces that agree on both faces are a strong join even where the edge has
   crumbled, and two that agree on one face with a gap between them are the same sheet, not
   neighbours. Sheet joins in a roll (kolleseis) are marks too.
4. **Hands.** Fragments written by one hand are proposed as a set, with the letter forms that say
   so. The set never names a scribe; a person may.
5. **Known texts.** A fragment's partial reading, gaps and doubtful letters included, is aligned
   against corpora of known texts the project has installed. A hit proposes "part of this work,
   these lines"; two fragments attesting neighbouring lines propose one roll and its order. A hit
   in a register of published papyri proposes that the fragment is already edited.
6. **Other holders.** A fragment in another institution comes in as a reference to that holder's
   IIIF manifest. A join across holders names both, with each one's inventory number, manifest and
   rights, and exports as a manifest of the reunited sheet that points at both image services.
7. **Many people.** Answers from a crowd or a team are kept one by one with who gave them. Agreement
   makes ground truth; disagreement is shown. The recognizers retrain on it and report their score
   before and after.

## What the person sees

- **Where it opens.** Any folder, group or set shown as Canvas (the Library's Canvas mode or a
  Preview pane's folder view) carries the toolbar. A set also appears in the sidebar under its
  board's folder and opens as its own board.
- **Empty.** A board with no links, sets or proposals looks as it does today, plus the toolbar. The
  Show menu's entries for things that do not exist are dimmed. An empty set says "Drag items here".
- **Loading.** The board opens settled, as today (`library.canvas.cards-move-only-when-asked`);
  links and sets draw in the same first frame as the cards. A running proposal job shows in the
  Activity pane and as a count on the Propose control; proposals appear as they are found.
- **Error.** A link the engine refuses (an unknown type, both ends the same) leaves no line and
  says why beside the pointer. A recognizer that cannot find a sheet outline says so on that card
  ("no outline found") and proposes nothing for it. A failed job keeps what it found.
- **Acceptance.** On a folder of twelve test images that include a torn pair, a letter with its
  reply and enclosure, one frame of two overlapping sheets and four sheets sharing a punch hole and
  a stain: the researcher joins the pair, makes a correspondence set of three items from two
  folders, orders it, connects reply and enclosure, runs From the Paper and sees the overlap and
  the stack proposed with their evidence, accepts both, relaunches, and finds every line, set,
  order and join where it was, with the filed order unchanged.

## Behaviors

Every test named below is owed (none is written). Engine tests go in `fichero-server/tests/unit/organize/` and
`fichero-server/tests/unit/physical/` (the bounded-run test under `fichero-server/tests/perf/`), Swift tests in
`fichero/Tests/Unit/general/Views/Library/` (the Relations section's under `Views/Inspector/`); each is named as
file, then function.

### A. Links, sets and orders in the engine

- `canvas-organize.link.archival-types` — **[GAP]** (→ #4639; engine) the library's link vocabulary
  gains `joins`, `verso_of`, `encloses`, `copy_of`, `draft_of`, `stacked_on`, `belongs_in` and
  `member_of`, each with its label and inverse label, seeded on open like the others; `joins` is
  symmetric. No existing key changes. Test:
  `py::test_the_eight_types_are_seeded_once`.
- `canvas-organize.link.document-ends` — **[GAP]** (→ #4639; engine) `typed_link.create` takes a
  page, file, group, folder or canvas item as either end, refuses an id that is none of those, and
  refuses a type that does not fit its ends (a `joins` between a folder and a page). One audited,
  undoable action. Test:
  `py::test_a_letter_answers_a_letter`.
- `canvas-organize.link.evidence` — **[GAP]** (→ #4639; engine) a link and a proposal carry evidence
  rows (who or what, method and version, score, short reason, the segment it points at on each
  end); a link made by hand has one row naming a person; evidence is returned with the link. Test:
  `py::test_a_hand_made_link_says_a_person_made_it`.
- `canvas-organize.set.record` — **[GAP]** (→ #4192; engine) a set is a `CanvasItem` of kind `set`
  with a label and a set kind (series, correspondence, case, file, bundle, free, project terms);
  its members are `member_of` links; a thing can be in several sets; adding to a set changes no
  parent and no sort order. Test:
  `py::test_a_set_holds_items_from_two_folders_and_moves_none`.
- `canvas-organize.order.items` — **[GAP]** (→ #5548; engine) a named order over pages and documents
  belongs to a set, group or folder; positions are fractions, so placing one item writes one row;
  it carries a kind, an author and a certainty; several orders can hold the same items. Test:
  `py::test_moving_one_item_writes_one_row`.
- `canvas-organize.order.filed-is-kept` — **[GAP]** (→ #5548; engine) no link, set, order, join or
  accepted proposal changes an item's folder or its filed position; *As Filed* is answered from the
  library's sort order and is never stored as an order. Test:
  `py::test_organizing_changes_no_parent_and_no_sort_order`.
- `canvas-organize.link.listed-for-a-scope` — **[GAP]** (→ #4639; engine) one route answers every
  link, set and order whose ends are in a folder scope, with a segment's links rolled up to its
  page and counted, in one bounded, paged call. Test:
  `py::test_segment_links_roll_up_to_their_pages`.

### B. The board

- `canvas-organize.toolbar` — **[GAP]** (→ #4192; app) the canvas pane's head shows the tools
  (Select, Hand, Connect, Order, Set, Join, Note), Arrange By, Show, Order, Propose and the proposal
  counter; each tool has a key, a held key springs back, and Esc returns to Select. Test:
  `swift::everyToolHasAKeyAndEscReturnsToSelect`.
- `canvas-organize.link.one-vocabulary-in-the-app` — **[GAP]** (→ #4192; app) the app reads link
  types and labels from the engine's types route; the Swift `LinkType` list is replaced by a table
  from the engine's key to a line style, and an unknown key draws in the plain style with its
  label. Test:
  `swift::everyEngineKeyHasAStyleAndUnknownKeysStillDraw`.
- `canvas-organize.links.existing-ones-show` — **[GAP]** (→ #4192; app) every link that already
  exists between two things on a board is drawn, a segment's links as one line between the two
  page cards with a count; Show chooses which families are drawn, per board, remembered. Test:
  `swift::aSegmentLinkDrawsBetweenItsPages`.
- `canvas-organize.tool.connect` — **[GAP]** (→ #4192; app) a Connect drag from one card to another
  opens a menu of the types that fit the two ends, the likeliest first; choosing one writes the
  link and draws it with its label; ⌥ repeats the last type; an ⌥-drop with the Select tool does
  the same (`library.canvas.a-drop-links-only-with-option`). Test:
  `swift::aDragBetweenTwoLettersOffersRepliesToFirst`.
- `canvas-organize.link.select-edit-remove` — **[GAP]** (→ #4192; app) a click on a line selects it;
  the Inspector shows its type, direction, author, certainty, note and evidence and can change the
  type, reverse it or set the certainty; Delete removes it; each is undone by one ⌘Z. Test:
  `swift::reversingALinkIsOneUndoableAction`.
- `canvas-organize.tool.set` — **[GAP]** (→ #4192; app) a Set drag makes a set of the cards inside
  it; New Set from Selection does the same for cards anywhere; a card dragged into a region joins
  it and out leaves it; the region is drawn behind its members with its label and count and follows
  them when they move. Test:
  `swift::draggingACardOutLeavesTheSet`.
- `canvas-organize.set.opens-as-a-board` — **[GAP]** (→ #4192; app) a set is listed in the sidebar
  under the folder it was made in and opens as its own board holding its members wherever they are
  filed, each card naming its folder; a member's own Inspector lists its sets. Test:
  `swift::aSetBoardShowsMembersFromTwoFolders`.
- `canvas-organize.tool.order` — **[GAP]** (→ #5548; app) with the Order tool, clicking cards in turn
  numbers them in the current order; dragging a numbered card between two others moves it with one
  write; the order draws as numbers and a path; the Order menu switches between As Filed and each
  named order and makes a new one. Test:
  `swift::clickingThreeCardsNumbersThemInTurn`.
- `canvas-organize.arrange.by-order-and-set` — **[GAP]** (→ #5550; app) Arrange By gains *By Order*
  (a row or grid in the current order) and *By Set* (each set's members together), saved and undone
  as every arrangement is (`library.canvas.arrange-is-an-action`). Test:
  `swift::byOrderLaysCardsOutInTheCurrentOrder`.
- `canvas-organize.tool.join` — **[GAP]** (→ #5550; app + engine) a card dragged to another's edge
  with the Join tool snaps where their outlines fit, or is placed by hand with ⌥; the result is a
  `joins` link holding the placement; joined pieces draw as one sheet, move together, and Unjoin
  parts them. Test:
  `swift::joinedPiecesMoveAsOneAndUnjoinPartsThem`.
- `canvas-organize.sheet.reads-as-one` — **[GAP]** (→ #5550; engine + app) a joined sheet shows in the
  Source view as one image composed from its pieces at their placement, and the Reader reads lines
  that cross the join as one line; a recto and its verso are one sheet with two sides. Test:
  `py::test_a_line_across_the_tear_is_one_line`.
- `canvas-organize.bundle.pile` — **[GAP]** (→ #5548; app) a set of kind bundle draws as a fanned
  pile in its stacking order, opens to a row and closes again; dragging within the row reorders
  the stack as one action. Test:
  `swift::aBundleDrawsInStackingOrder`.
- `canvas-organize.misfiled.belongs-in` — **[GAP]** (→ #4639; app + engine) a ⌃-drop of a card onto a
  group, set or folder, or Belongs In…, writes `belongs_in` and moves nothing; the card carries a
  badge where it is filed and is listed, marked as filed elsewhere, where it belongs. Test:
  `py::test_a_misfiled_sheet_is_listed_where_it_belongs_and_stays_where_filed`.
- `canvas-organize.inspector.relations` — **[GAP]** (→ #4639; app) the Inspector of a page, document
  or set has a Relations section: its links by family in both directions with the other end's
  picture and name, its sets, and its place in each order; a click goes to the other end. The same
  section is the whole surface on iPhone. Test:
  `swift::aLetterListsItsReplyAndItsEnclosure`.
- `canvas-organize.undo-and-touch` — **[GAP]** (→ #4192; app) every gesture above is one audited
  engine action undone by one ⌘Z; on iPad the Pencil draws with the current tool, a finger pans and
  moves, and a long press on a card starts a connect. Test:
  `swift::eachToolGestureIsOneUndoStep`.

### C. Proposals

- `canvas-organize.propose.one-store` — **[GAP]** (→ #5550; engine) proposed links, sets, orders,
  joins and layouts are stored with Find the Documents' proposals as hypotheses with their
  evidence, method, version and score; none is a link, set or order until accepted. Test:
  `py::test_a_proposed_link_is_not_a_link`.
- `canvas-organize.propose.run` — **[GAP]** (→ #5550; engine + app) Propose runs the chosen kinds on
  the selection or the board's scope as an Activity job that can be cancelled and resumed; it is
  local by default, and a paid model is offered with its estimate and starts only when chosen. Test:
  `py::test_a_run_writes_proposals_and_accepts_nothing`.
- `canvas-organize.propose.drawn-apart` — **[GAP]** (→ #5550; app) proposals draw in one proposal
  style with a confidence mark, apart from accepted links and sets; no card moves; a proposed
  layout draws as ghost cards with Apply Layout. This is the layer `finddocs.canvas.drawn` draws
  on. Test:
  `swift::aProposalNeverMovesACard`.
- `canvas-organize.propose.evidence-strip` — **[GAP]** (→ #5550; app) selecting a proposal shows its
  evidence under the board: the compared parts side by side from the engine's own crops, the
  method, version and score, and the reason in a sentence; a proposal without evidence is not
  listed. Test:
  `swift::aTornEdgeProposalShowsBothEdges`.
- `canvas-organize.propose.accept-reject` — **[GAP]** (→ #5550; engine + app) Accept (↩) writes the
  link, set, order or join as a person's, citing the proposal; Reject (⌫) records the pair so it is
  not proposed again; Accept All in Selection answers many as one undoable step; an adjusted
  proposal is accepted as adjusted. Test:
  `py::test_a_rejected_pair_is_not_proposed_again`.
- `canvas-organize.propose.step-through` — **[GAP]** (→ #5550; app) the proposal counter shows how
  many wait on this board; Next and Previous move the selection and the camera to each in order
  of confidence; the folder's Items list counts them with Find the Documents' own. Test:
  `swift::nextGoesToTheMostConfidentUnanswered`.
- `canvas-organize.propose.from-the-text` — **[GAP]** (→ #5550; engine) from readings and the cues
  Find the Documents already computes: `answers` (a reply phrase naming an earlier letter's date or
  number), `encloses` (an enclosure phrase and a document that fits it), `copy_of` and `draft_of`
  (near-identical text; typed signature marks against a signed original; density of corrections),
  `continues` (a sentence running over the break), and sets of correspondents. Test:
  `py::test_a_reply_phrase_proposes_answers_with_the_phrase_as_evidence`.
- `canvas-organize.propose.corrections-teach` — **[GAP]** (→ #5550; engine) each accept, reject and
  adjustment is kept as a labelled example with its evidence, in the form
  `finddocs.corrections-teach` keeps its own. Test:
  `py::test_an_accept_is_a_positive_example`.

### D. The physical recognizers

- `canvas-organize.physical.marks-are-segments` — **[GAP]** (→ #5548; engine) sheet outlines, torn
  edges, holes and stains are segments of their own kinds in a machine pass, in the page's
  coordinates, seen and corrected in the segment editor; a corrected mark reruns only the
  comparisons it was part of. Test:
  `py::test_a_hole_is_a_segment_of_kind_hole`.
- `canvas-organize.physical.sheet-outline` — **[GAP]** (→ #5548; engine) every image gets its sheet
  outline from the page finder, rectified, with a descriptor; two images whose outlines agree are
  proposed as `duplicate_of`, and two that agree mirrored as `verso_of`, each with the overlay and
  the residual as evidence. Test:
  `py::test_a_mirrored_outline_proposes_verso_of`.
- `canvas-organize.physical.overlap` — **[GAP]** (→ #5548; engine) a frame with more than one sheet
  is reported with each outline, which sheet lies on top and the hidden area; it proposes one page
  per sheet, `stacked_on` between them, and the finding that the covered sheet needs another
  photograph. Test:
  `py::test_the_whole_outline_is_the_upper_sheet`.
- `canvas-organize.physical.torn-edge` — **[GAP]** (→ #5548; engine) irregular stretches of two
  outlines that fit are proposed as `joins` with the placement, after the cheap filter; the
  evidence is the two edges together, the gap along the fit and the lines of writing that cross.
  A straight edge is never matched as a tear. Test:
  `py::test_two_halves_of_a_torn_page_are_proposed_with_their_placement`.
- `canvas-organize.physical.holes-and-stains` — **[GAP]** (→ #5548; engine) marks at the same place
  on several sheets propose a bundle; a mark that shrinks or fades through them proposes the
  `stacked_on` order; regular punches alone propose the bundle without an order; the proposal says
  that this is how the sheets lay when the damage happened. Test:
  `py::test_a_shrinking_stain_orders_four_sheets`.
- `canvas-organize.physical.scale-is-stated` — **[GAP]** (→ #5548; engine) each physical proposal says
  whether true size was known (a ruler or colour card in frame) or only relative shape, and a
  relative-only match scores lower. Test:
  `py::test_a_match_without_a_ruler_says_relative`.
- `canvas-organize.physical.bounded` — **[GAP]** (→ #5548; engine) a run compares in detail only the
  candidates the descriptor index returns, reports progress, resumes after a restart, and holds a
  stated memory ceiling on a folder of two thousand images. Test:
  `py::test_two_thousand_images_stay_under_the_ceiling`.
- `canvas-organize.physical.scored` — **[GAP]** (→ #5548; engine) each recognizer is scored on a
  known-answer set (public pages torn and stacked synthetically; a public torn-page set) and its
  proposals carry the precision measured at their score; a recognizer with no score is not offered
  in the Propose menu. Test:
  `py::test_torn_edge_precision_on_the_synthetic_set`.

### E. Out of the board

- `canvas-organize.reader.follows-an-order` — **[GAP]** (→ #5548; app + engine) the Reader's next and
  previous follow the order chosen for the set, group or folder being read, and say which order
  that is; a `continues` link stitches the text of its two ends with a page anchor between. Test:
  `py::test_next_follows_the_chosen_order`.
- `canvas-organize.export` — **[GAP]** (→ #4639; engine) an order exports as an IIIF Range and a set
  as a Collection; replies and enclosures as TEI `correspContext`; copies, drafts, sequence and
  membership as Records in Contexts relations; the catalogue sheet gains a Relations column; every
  export says who made each relation and how sure. Test:
  `py::test_an_order_exports_as_a_range`.
- `canvas-organize.mcp-cli` — **[GAP]** (→ #4639; engine) links between documents, sets, item orders,
  proposals, accept and reject, and each recognizer are MCP tools and CLI commands generated from
  the same routes, with the same result as the board. Test:
  `py::test_organize_tools_match_their_routes`.

### F. At the scale of a dump of fragments

- `canvas-organize.scale.descriptor-index` — **[GAP]** (→ #5548; engine) every fragment's descriptors
  (outline, edge, fibres, hand, read letters) are computed once, versioned by method, and held in an
  index that returns the nearest candidates to one fragment in bounded time on five hundred
  thousand fragments; adding fragments extends the index without rebuilding it. Test:
  `test_descriptor_index.py::test_nearest_candidates_are_bounded_at_half_a_million`.
- `canvas-organize.scale.triage` — **[GAP]** (→ #5550; engine + app) a triage pass gives each fragment
  facets: written or blank, size, script and language, which face shows which fibre direction,
  book hand or documentary hand, read or unread, in a set or in none; fragments too small to match
  are kept and left out of matching with that reason; the facets are counts and filters in the
  table and on the board. Test: `test_triage.py::test_a_blank_scrap_is_kept_and_left_out_with_its_reason`.
- `canvas-organize.scale.jobs-say-their-coverage` — **[GAP]** (→ #5550; engine) a matching job takes a
  budget (time, comparisons), works in priority order (the selection, then by triage), resumes
  where it stopped, and reports its coverage as fragments compared out of fragments in scope; a
  proposal list from a partial run says it is partial. Test:
  `test_matching_coverage.py::test_a_stopped_job_reports_what_it_covered_and_resumes`.
- `canvas-organize.scale.board-is-a-slice` — **[GAP]** (→ #4192; app) a board over a scope larger than
  two thousand items opens on a slice (a set, triage facets, a search, or one fragment and its
  candidates), states how many of how many are shown, and never loads the rest; Show Candidates
  brings a selected fragment's nearest onto the board as ghost cards. Test:
  `CanvasSliceTests.swift::aLargeScopeOpensOnASliceAndSaysHowMany`.
- `canvas-organize.findcontext.sets` — **[GAP]** (→ #4639; engine + app) set kinds gain find context
  terms (season, find spot, excavation box, project terms); a set can be a member of a set; find
  contexts are made from inventory metadata at import as proposals; the holder's inventory order
  is *As Filed*, labelled with the holder's name, and no surface calls it the original order. Test:
  `test_find_context_sets.py::test_a_fragment_is_in_its_box_its_season_and_still_filed_by_inventory`.
- `canvas-organize.physical.fibre-continuity` — **[GAP]** (→ #5548; engine) on papyrus, each face's
  fibre direction and the fibres meeting each edge (position, spacing, width, tone) are marks; two
  edges whose fibres continue are proposed as `joins`, scored higher when both faces agree, and
  with a stated gap when the fibres agree and the edges do not meet; the evidence draws the fibres
  running across the break on each face. Sheet joins of a roll are marks and never read as a tear.
  Test: `test_fibre_continuity.py::test_fibres_agreeing_on_both_faces_outrank_an_edge_fit_alone`.
- `canvas-organize.hand.same-hand-sets` — **[GAP]** (→ #5550; engine + app) fragments are clustered by
  an unsupervised hand descriptor and each cluster is proposed as a set of kind hand; the evidence
  is the same letters from several members side by side and the member that fits least; the set
  names no scribe; splitting or merging a set is an answer that teaches. Test:
  `test_same_hand_sets.py::test_a_proposed_hand_set_shows_matching_letter_forms_and_names_no_one`.
- `canvas-organize.text.identify` — **[GAP]** (→ #5550; engine) a fragment's reading, with gaps and
  doubtful letters, is aligned against the known-text corpora installed in the project by an
  alignment that tolerates both; a hit proposes `attests` to the work's identifier with the lines
  and the aligned text as evidence, and several rival hits are all shown; a hit in a register of
  published texts proposes `same_as` to that text's stable identifier. The vocabulary gains
  `attests`. Test: `test_text_identification.py::test_a_gapped_reading_proposes_the_work_and_its_lines`.
- `canvas-organize.text.same-work-orders` — **[GAP]** (→ #5548; engine) fragments that attest one work
  are proposed as one set with an order by line number, and two that attest neighbouring columns
  are proposed as candidates for a join, ranked above candidates with no text in common. Test:
  `test_text_identification.py::test_two_fragments_of_one_work_are_ordered_by_their_lines`.
- `canvas-organize.text.corpora-are-installed` — **[GAP]** (→ #5550; engine + app) a known-text corpus
  is installed per project with its name, licence and version; none under a licence that forbids
  it is bundled; identification runs locally and never sends a reading to a service unless a
  person chooses one; each proposal names the corpus and version it matched. Test:
  `test_text_corpora.py::test_a_proposal_names_its_corpus_and_version`.
- `canvas-organize.cross.join-names-both-holders` — **[GAP]** (→ #4639; engine + app) a fragment held
  elsewhere is on a board as a reference to its holder's manifest and canvas; a link whose ends
  have different holders records each holder, inventory number, manifest and rights statement,
  and its card and Inspector say who holds each piece; the reunited sheet exports as a manifest
  that references both holders' image services and copies no image. Test:
  `test_cross_holder_join.py::test_the_join_record_and_its_manifest_name_both_holders`.
- `canvas-organize.crowd.answers-are-ground-truth` — **[GAP]** (→ #5550; engine + app) every accept,
  reject and correction is kept with who gave it; a relation counts as ground truth when the
  project's rule is met (a number of people agreeing, or a named editor); disagreement is listed
  and never averaged; imported crowd transcriptions keep their agreement as certainty; a recognizer
  retrained on ground truth reports its score before and after, on fragments held out by find
  context. Test: `test_crowd_ground_truth.py::test_two_agreeing_answers_make_ground_truth_and_a_split_is_listed`.

## Data model and which operations are engine calls

Everything is an engine action through the audited layer; the app holds positions in flight and
nothing else. New actions: `set.create`, `set.rename`, `set.delete`, `set.add`, `set.remove`
(the last two are `typed_link.create` / `typed_link.delete` with `member_of`); `item_order.create`,
`item_order.place`, `item_order.remove`, `item_order.delete`; `sheet.join`, `sheet.unjoin`;
`organize.propose`, `organize.accept`, `organize.reject`; `physical.find_marks`. Existing actions
reused unchanged: `typed_link.create`, `typed_link.delete`, `typed_link.restore`, `canvas.arrange`,
the group and ungroup routes, the canvas layout and canvas item routes, the segment actions for
marks. New records: the evidence row; the item order and its entries (or the reading-order records
widened, open question 2). `CanvasItemKind` gains `set`. Nothing is added to `SpatialConnection`,
`LibraryItemLink` or the Swift `LinkType`; the first two keep reading until their own convergence
slice, the third is removed by `canvas-organize.link.one-vocabulary-in-the-app`.

## Build order

### Stage 1 — Engine: links between documents, sets, orders
#### Step 1.1 — The eight link types and document ends (#TBD)
- Behaviours: `canvas-organize.link.archival-types`, `canvas-organize.link.document-ends`, `canvas-organize.link.evidence`
- Tests: py, py, py
- Size: M
#### Step 1.2 — Sets, item orders and the filed order (#TBD)
- Behaviours: `canvas-organize.set.record`, `canvas-organize.order.items`, `canvas-organize.order.filed-is-kept`, `canvas-organize.link.listed-for-a-scope`
- Tests: py, py, py, py
- Size: M

### Stage 2 — The board: see and make relations by hand
#### Step 2.1 — Toolbar, one vocabulary, existing links drawn (#TBD)
- Behaviours: `canvas-organize.toolbar`, `canvas-organize.link.one-vocabulary-in-the-app`, `canvas-organize.links.existing-ones-show`
- Tests: CanvasOrganizeToolbarTests.swift, CanvasLinkStyleTests.swift, CanvasLinksDrawnTests.swift
- Depends on: 1.2
- Size: M
#### Step 2.2 — Connect, edit and remove a link; the Relations section (#TBD)
- Behaviours: `canvas-organize.tool.connect`, `canvas-organize.link.select-edit-remove`, `canvas-organize.inspector.relations`, `canvas-organize.undo-and-touch`
- Tests: CanvasConnectToolTests.swift, CanvasLinkEditTests.swift, RelationsSectionTests.swift, CanvasOrganizeUndoTests.swift
- Size: M
#### Step 2.3 — Sets and their boards (#TBD)
- Behaviours: `canvas-organize.tool.set`, `canvas-organize.set.opens-as-a-board`, `canvas-organize.misfiled.belongs-in`
- Tests: CanvasSetToolTests.swift, CanvasSetBoardTests.swift, py
- Size: M
#### Step 2.4 — Orders on the board (#TBD)
- Behaviours: `canvas-organize.tool.order`, `canvas-organize.arrange.by-order-and-set`, `canvas-organize.bundle.pile`, `canvas-organize.reader.follows-an-order`
- Tests: CanvasOrderToolTests.swift, CanvasArrangeByOrderTests.swift, CanvasBundlePileTests.swift, py
- Size: M

### Stage 3 — Proposals
#### Step 3.1 — One store, the job, accept and reject (#TBD)
- Behaviours: `canvas-organize.propose.one-store`, `canvas-organize.propose.run`, `canvas-organize.propose.accept-reject`, `canvas-organize.propose.corrections-teach`
- Tests: py, py, py, py
- Depends on: 1.2
- Size: M
#### Step 3.2 — The proposal layer, the evidence strip, stepping through (#TBD)
- Behaviours: `canvas-organize.propose.drawn-apart`, `canvas-organize.propose.evidence-strip`, `canvas-organize.propose.step-through`
- Tests: CanvasProposalLayerTests.swift, CanvasEvidenceStripTests.swift, CanvasProposalStepTests.swift
- Depends on: 3.1, 2.1
- Size: M
#### Step 3.3 — Relations proposed from the text (#TBD)
- Behaviours: `canvas-organize.propose.from-the-text`
- Tests: py
- Depends on: 3.1
- Size: M

### Stage 4 — The physical recognizers
#### Step 4.1 — Marks as segments, the sheet outline, scale, the known-answer sets (#TBD)
- Behaviours: `canvas-organize.physical.marks-are-segments`, `canvas-organize.physical.sheet-outline`, `canvas-organize.physical.scale-is-stated`, `canvas-organize.physical.scored`
- Tests: py, py, py, py
- Depends on: 3.1
- Size: M
#### Step 4.2 — Overlap and torn edges (#TBD)
- Behaviours: `canvas-organize.physical.overlap`, `canvas-organize.physical.torn-edge`
- Tests: py, py
- Size: M
#### Step 4.3 — Holes and stains; bounded runs (#TBD)
- Behaviours: `canvas-organize.physical.holes-and-stains`, `canvas-organize.physical.bounded`
- Tests: py, py
- Size: M
#### Step 4.4 — Join by hand and a sheet that reads as one (#TBD)
- Behaviours: `canvas-organize.tool.join`, `canvas-organize.sheet.reads-as-one`
- Tests: CanvasJoinToolTests.swift, py
- Depends on: 4.2, 2.1
- Size: M

### Stage 5 — Out of the board
#### Step 5.1 — Export, MCP and the command line (#TBD)
- Behaviours: `canvas-organize.export`, `canvas-organize.mcp-cli`
- Tests: py, py
- Depends on: 1.2, 3.1
- Size: M

### Stage 6 — The large-fragment case
#### Step 6.1 — The descriptor index, triage and coverage (#TBD)
- Behaviours: `canvas-organize.scale.descriptor-index`, `canvas-organize.scale.triage`, `canvas-organize.scale.jobs-say-their-coverage`
- Tests: test_descriptor_index.py, test_triage.py, test_matching_coverage.py
- Depends on: 4.3
- Size: M
#### Step 6.2 — A board that is a slice; find contexts (#TBD)
- Behaviours: `canvas-organize.scale.board-is-a-slice`, `canvas-organize.findcontext.sets`
- Tests: CanvasSliceTests.swift, test_find_context_sets.py
- Depends on: 6.1, 2.3
- Size: M
#### Step 6.3 — Fibres and hands (#TBD)
- Behaviours: `canvas-organize.physical.fibre-continuity`, `canvas-organize.hand.same-hand-sets`
- Tests: test_fibre_continuity.py, test_same_hand_sets.py
- Depends on: 6.1, 4.2
- Size: M
#### Step 6.4 — Known texts (#TBD)
- Behaviours: `canvas-organize.text.corpora-are-installed`, `canvas-organize.text.identify`, `canvas-organize.text.same-work-orders`
- Tests: test_text_corpora.py, test_text_identification.py
- Depends on: 6.1
- Size: M
#### Step 6.5 — Other holders and many people (#TBD)
- Behaviours: `canvas-organize.cross.join-names-both-holders`, `canvas-organize.crowd.answers-are-ground-truth`
- Tests: test_cross_holder_join.py, test_crowd_ground_truth.py
- Depends on: 5.1
- Size: M

## Test matrix

| Leg | This surface? | Pins | File |
|-----|---------------|------|------|
| Pure rule (Swift) | y | drop table, link styles, order numbering, set membership, proposal layer | `swift` |
| Availability (Swift) | y | every tool and command reachable from the toolbar, menu and context menu | `CanvasOrganizeToolbarTests.swift` |
| Backend (pytest) | y | links, sets, orders, proposals, recognizers on known-answer images | `tests/unit/organize/`, `tests/unit/physical/` in the engine |
| MCP | y | tools map to routes | `py` |
| CLI | y | commands wire the same routes | `py` |
| Click-around (XCUITest, Mac) | y | the acceptance walk in "What the person sees" | `swift` |
| iPhone (iOS) | y | the Relations section, accept and reject | `fichero/Tests/UI/ios` |
| iPad | y | Pencil connect, finger move | `fichero/Tests/UI/ipad` |
| Load (#4634) | y | recognizers on two thousand images; a board with five hundred links holds frame rate | `py` |

## Documentation matrix

| Audience | Doc leg | This feature? | Lives in |
|----------|---------|---------------|----------|
| User | user manual + screenshot | y | the maintainer's "Organising a project" section |
| Contributor | developer docs | y | this spec |
| AI / agent | MCP tool description | y | generated from the routes |
| Scripter | CLI `--help` | y | generated from the routes |
| Reference | capability/endpoint reference | y | generated |

## Preview harness

`CanvasOrganizePreview` beside the board's pure model renders, from fixed data and with no engine:
a board with one of each link family, a set from two folders, a bundle as a pile and opened, an
order drawn, and three proposals (a torn pair with its evidence strip, an overlap, a stack). It is
the source of the manual's pictures.

## Accessibility identifiers

Each identifier is `canvas-organize.` followed by: `tool.select`, `tool.hand`, `tool.connect`,
`tool.order`, `tool.set`, `tool.join`, `tool.note`; `menu.show`, `menu.order`, `menu.propose`,
`menu.connect-as.<key>`; `proposal.count`, `proposal.next`, `proposal.previous`, `proposal.accept`,
`proposal.reject`; `link.<id>`, `set.<id>`, `evidence.strip`; `inspector.relations`. Every link,
set and proposal is reachable from the keyboard (Tab through a card's relations) and is spoken as
a sentence: "Letter of 4 March replies to Letter of 20 February, made by a person".

## UX completeness

| Control (a11y id) | Label | Tooltip/help text | Localized key | Verified by |
|---|---|---|---|---|
| `canvas-organize.tool.connect` | Connect | Draw a relation between two items (C) | `canvas.organize.tool.connect` | [MISSING] |
| `canvas-organize.tool.order` | Order | Click items in turn to put them in order (O) | `canvas.organize.tool.order` | [MISSING] |
| `canvas-organize.tool.set` | Set | Draw around items that belong together (S) | `canvas.organize.tool.set` | [MISSING] |
| `canvas-organize.tool.join` | Join | Fit two pieces of one sheet together (J) | `canvas.organize.tool.join` | [MISSING] |
| `canvas-organize.menu.show` | Show | Choose which relations, sets and proposals are drawn | `canvas.organize.menu.show` | [MISSING] |
| `canvas-organize.menu.propose` | Propose | Ask for suggested relations, with their evidence | `canvas.organize.menu.propose` | [MISSING] |
| `canvas-organize.proposal.accept` | Accept | Keep this suggestion (Return) | `canvas.organize.proposal.accept` | [MISSING] |
| `canvas-organize.proposal.reject` | Reject | Dismiss this suggestion; it is not offered again (Delete) | `canvas.organize.proposal.reject` | [MISSING] |

## Open questions for the owner

1. **Set or folder?** Is a correspondence a new *set* (members stay where they are filed, a thing
   can be in several) or a folder the letters are moved into? *Recommended: a set.* It keeps the
   filed order, allows one letter in two series, and needs one new item kind and one link type; a
   folder remains for when the researcher does want to refile.
2. **One order record or two?** Should an order over pages and documents widen the existing
   reading-order records (entries may point at an item) or be its own pair of tables?
   *Recommended: widen the existing records*, so "next and previous in a named order" is one idea
   with one renumbering rule, and the Reader asks one question.
3. **Do joined halves become one page?** After a join, is the reunited sheet composed into one
   image that is segmented and read again, or do the two images keep their own readings, stitched?
   *Recommended: keep both images and stitch*, composing one picture for display only; no reading
   is thrown away and Unjoin is free. Re-reading the composed sheet is offered, never automatic.
4. **Eight new link kinds: the right eight?** `joins`, `verso_of`, `encloses`, `copy_of`,
   `draft_of`, `stacked_on`, `belongs_in`, `member_of`, with replies on the existing `answers` and
   duplicates on `duplicate_of`. *Recommended: yes, and no more in this spec*; a project can add
   its own terms, and each added built-in is a label to translate and a style to draw.
5. **Where do the physical recognizers run?** With every import, or only when asked?
   *Recommended: outlines and marks with image preparation (cheap, and the page finder already
   runs); matching between sheets only when Propose is chosen or a recipe's Organise stage asks
   for it*, since matching is the costly part and its proposals want a person's attention.
6. **Any automatic acceptance?** Should a near-certain proposal (the same side photographed
   twice) ever be accepted by the run? *Recommended: no, until each recognizer is scored on a box
   a person organized; then the same rule as Find the Documents' boundaries, per kind, switched on
   by a person.* Duplicates would be the first candidate.
7. **A paid vision model for the hard pairs?** Should the teacher model be asked to judge
   uncertain joins and stacks from the two crops? *Recommended: yes, as an offered step with its
   estimate, never by default*; the geometry stays local, and the model's reasons join the
   evidence.
8. **Does the 3D space get the tools?** *Recommended: it draws links, sets and proposals from the
   same records, and the tools stay on the 2D board in this spec*; drawing a region or fitting a
   torn edge in depth is a separate design.
9. **One milestone or the existing one?** This spec names a new `canvas-organize` milestone.
   *Recommended: new*, ordered in `build-order.md` after `library-view-modes` and the segment
   editor's steps, with Stage 1 (engine) free to start beside them since it touches no shared view.
10. **How large is one library meant to be?** The fragment case is five hundred thousand items.
   *Recommended: test and promise one hundred thousand in a library on a Mac; treat half a million
   as an index built on a cluster through the existing runner, with the app opening slices of it.*
   The board, the table and the jobs are designed for the larger number either way.
11. **Which known-text corpora are offered?** *Recommended: bundle none; offer open ones as
   downloads (the documentary texts published at papyri.info, open Greek and Latin literary
   collections), and let a project add a licensed corpus it already holds, used locally only.*
   Each corpus's licence is checked before it is listed.
12. **What makes a crowd's answer ground truth?** *Recommended: two people agreeing or one named
   editor, set per project, with every single answer kept.* Training uses ground truth only;
   proposals may show lone answers as a hint with their count.

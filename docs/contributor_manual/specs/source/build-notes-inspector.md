# Build notes: the Inspector, rethought from the archive model

**RULED 2026-09-27.** The maintainer ruled on all four questions in section 7; the rulings are in
section 8 and in `segment-editor.md`. Nothing here is built yet.

Asked for on 2026-09-27: rethink the Inspector from the archive model, not from the layout it had
before the model existed. It was read on disk on 2026-09-27 on `spec/page-model`.

## 1. What the Inspector is today, and why that is the wrong starting point

The Inspector is a **document** inspector (`Views/Inspector/InspectorSection.swift`,
`InspectorTab.swift`). It has four sections: Source, Notes, Knowledge and Artifacts. Behind them
are eleven tabs, from Content to Info. The Source section has one picker:
**Content / Info / Outline / Order** (`SourceSectionView.swift`, `SourceSectionMode`).

- **Order** was added in slice 13 (Q5). It is a bolt-on, built and kept, but provisional.
- **Artifacts** lists an artifact's line regions as rows, with Join (`ArtifactPanel+Regions.swift`).

Every tab answers "what is this DOCUMENT". None of them answers the model's question, "what is this
SEGMENT". The model says the Inspector "shows one segment: readings, versions, hand, links,
statements" (`source-model.md`, "One store, many uses"). The editor spec says it shows "the facts
about the one selected segment" (`segment-editor.md`). Today no tab shows a segment's readings,
hands, rights, certainty or signs; the app has no view of any of those records.

## 2. The proposal, in one paragraph

**The Inspector inspects the SELECTION, and a page or a source is a segment like any other.** Its
head is a **path**: Source › page 2 › block 3 › line 14 › word 5. Clicking a crumb inspects that
level, so the path is how you move up. Below the head sit **the same sections at every level**, in
a fixed order:

1. Text
2. Order
3. Language & script
4. Hands
5. Certainty
6. Signs
7. Links
8. Rights
9. Making

A section with nothing to say at that level is hidden, never shown empty. The document-level tabs
(Knowledge, Notes, Artifacts, Info) stay, as what the Inspector shows when the selection is the
source itself. Level changes what a section *holds*, not which sections exist, so the Inspector
never re-lays itself out when you go up or down.

## 3. What the Inspector shows at each level

The levels are the physical ladder. Any of them may be missing on a given source
(`source.segment.levels-optional` [GAP]). A source can also carry a logical ladder (article,
entry, letter) beside the physical one (`source.segment.physical-and-logical` [GAP]). The path
then shows whichever ladder the selection was made in, and a menu on the crumb switches ladders.

| Level | The one thing it adds | Text section shows | Order section shows |
|---|---|---|---|
| **Stroke** | the ink itself: which hand, which campaign | none of its own (it is below the reading) | stroke order, when traced (`source.editor.pencil-traces-strokes` [GAP]) |
| **Character / glyph** | the sign: its character, or its declared sign if it has none | the character, its confidence (`source.reading.char-confidence-on-line` [OK]), its variant (`source.sign.variants` [PARTIAL]) | none: characters follow the line's direction |
| **Word** | the reading of one word; its entity mentions | its readings (section 5.1) | its place among the line's words |
| **Line** | the unit readings are typed in; the unit that is moved | its readings, the line's picture beside them | its place under its block (**where "lines move in the text" happens**) |
| **Region / block** | the kind (paragraph, column, marginalia, table…) | the joined text of its lines, read-only here | its place in the page's as-written order, plus its lines as a list you can reorder |
| **Page** | the image, its passes, the page's own orders | the page text (derived, `source.point.text-is-derived` [OK]) | every order over the page (section 4) |
| **Source** | the whole: metadata, knowledge, notes | today's Content tab | the source's flows across pages (`source.segment.flow` [PARTIAL]) |

**A mixed selection** is a line and a word, or two lines from different blocks. It shows:

- the path of the **nearest common parent**;
- a count by kind ("3 lines, 1 word");
- only the facts that are **the same across all of them**. Where they differ, the row says "mixed" and
  lists the values, never picking one;
- the verbs that apply to every selected segment (set kind, language, hand), and no verb that only
  applies to some.

This follows the visible-surface selection ruling: a verb acts on what you can see is selected.

## 4. Moving through the hierarchy, and how it ties to the other two surfaces

The model's rule is: "up to the parent, down to the children, next and previous in a reading order,
across a link" (`source-model.md`).

- **Up** is the path's crumbs, and a menu command. It is not a back button: going up changes the
  selection, so the Source view and the Reader follow it (`source.editor.selection-shared` [PARTIAL]).
- **Down**: the Order section of any level lists its children. Selecting a row there selects that
  child everywhere.
- **Next / previous** are always asked *of a named order* (`source.order.next-previous` [OK]). The
  Inspector's next and previous use the order picked in its Order section, which is as-written by
  default.
- **Across** a link: the Links section's rows are the way across (`source.link.both-ways` [OK]).

**The Inspector follows the focused pane's selection** (the per-pane selection ruling, 2026-09-27):

- **Source view:** the Inspector shows the focused Source view pane's selection.
- **Reader:** the Reader's caret is a selection of one line, so the Inspector shows that line. A text
  selection across lines shows the lines it touches (`source.textedit.one-selection` [GAP]).
- **Segments pane:** once it exists (`source.segments-pane.exists` [GAP]), its selection counts the
  same way.

The Inspector has no selection of its own to keep in sync; it is always showing someone else's.

## 5. What each level carries, section by section

### 5.1 Text: readings, and which one counts
- Every reading of the segment, each with its kind, maker, author and the guideline it followed
  (`source.reading.set`, `source.reading.kinds`, `source.reading.author-and-guideline`,
  `source.reading.machine-is-labelled`, all [OK]).
- The one that counts is marked, with WHY it counts: chosen by a person, or the project's rule
  (`source.reading.chosen-is-worked-out`, `source.reading.chosen-follows-project-rule` [OK]).
  Equal alternatives are shown as equal until one is chosen (`source.reading.equal-alternatives` [OK]).
- Written / read pairs (orig, reg, sic, corr, abbr, expan) are shown as pairs
  (`source.reading.written-read-pair` [OK]).
- **Choosing** a reading is the one text verb the Inspector keeps. It changes which reading counts
  and types nothing. **Typing a reading belongs in the Reader** (`source.textedit.typing-is-a-new-reading` [PARTIAL]).

### 5.2 Order
- Every order the segment sits in: as-written, the named orders, and flows
  (`source.order.named-multiple` [OK], `source.segment.flow` [PARTIAL]).
- Its position in each order, and its children in the order picked here.
- **Reordering happens here, in the Reader and in the Segments pane, with ONE implementation**
  (segment-editor Q5 ruling; `source.editor.reorder` [PARTIAL], `source.textedit.lines-move-in-the-order` [GAP]).
  Today's `ReadingOrderList` is that one implementation. It moves out of the Source picker into this
  section unchanged.
- **Word under line** is reordered too, with the same verbs as lines (ruled, section 8).
  Its place still follows the line's direction when nobody has moved it
  (`source.dir.per-segment` [PARTIAL]).

### 5.3 Language, script and direction
- The three facts, each saying where it came from: set here, inherited from the block, the page or
  the project, or detected (`source.lang.three-facts`, `source.lang.says-where-from`,
  `source.lang.cascade` [OK]).
- "Unknown" is shown differently from "not examined" (`source.lang.unknown-is-not-unexamined` [OK]).
- Set through the Segment menu verbs (`source.editor.set-language-script`, `source.editor.set-direction` [PARTIAL]).

### 5.4 Hands
- Every attribution on the segment, rival ones side by side, never merged
  (`source.hand.attributed` [PARTIAL]).
- Each attribution shows its certainty, who judged it, and its source ("file: <name>" for an
  imported `<handShift>`).
- The hand record (scribe, date, style) is one click away (`source.hand.record` [OK]).
- **Who wrote the ink** and **who made the record** are shown on separate rows
  (`source.hand.not-provenance` [PARTIAL]).
- Campaigns are shown with the hand (`source.campaign.ordered` [GAP]).

### 5.5 Certainty and damage
- The three kinds are shown apart, never as one number (`source.sure.three-kinds` [GAP]):
  - machine confidence;
  - scholarly certainty;
  - the state of the page.
- The editorial facts: unclear, lost, restored, supplied, deleted (`source.sure.editorial-facts` [GAP]).

### 5.6 Signs
- A declared sign shows its name, its picture and its list (`source.sign.declared`,
  `source.sign.list-authority` [PARTIAL]; its picture is `source.sign.shown-as-picture` [GAP]).
- "Every instance of this sign" is a link to the Segments pane, which gathers them
  (`source.sign.gather-instances` [PARTIAL]).

### 5.7 Links and statements
- Typed links, both ways (`source.link.typed` [PARTIAL], `source.link.both-ways` [OK]), at any
  depth (`source.link.any-depth` [GAP]).
- The claims and mentions that point at this segment (`source.statement.on-segment`,
  `source.statement.both-ways` [GAP]). This is the segment-level view of today's Knowledge section.

### 5.8 Rights
- What applies here, worked out from the library down, with the records that added up to it (the
  `/rights/effective` route; `source.rights.record` [PARTIAL], `source.rights.tighten-only` [OK]).
- A restricted segment says it is restricted to those who may not see it
  (`source.rights.restricted-is-said` [GAP]).
- Setting a record is a verb here, for owners and editors only (`source.rights.who-acts` [PARTIAL]).

### 5.9 Making (provenance)
- How the segment came to be, as a short chain you can walk: "found by Kraken, read by model X,
  corrected by Daniel" (`source.making.in-inspector`, `source.making.walkable` [GAP]).
- Its versions, which one is current, and that older ones exist
  (`segment.inspector.version-visible`, `source.segment.versioned-alone` [OK]).
- The pass it belongs to, which is not the hand (section 5.4).

## 6. Where each thing lives: three surfaces, plus the Segments pane

| Stays in the Inspector | Belongs elsewhere |
|---|---|
| The facts of the selection, at its level (sections 5.1–5.9) | **Source view:** shapes. Drawing, reshaping, cutting, joining, marks on the page (`source.editor.shapes-in-source-view`) |
| Choosing which reading counts | **Reader:** typing readings, Return splits, Backspace joins (`source.textedit.*`) |
| Reordering children in the Order section (one of Q5's three places) | **Reader:** moving lines in the text, the same verb as the Inspector's |
| Set-kind / language / hand / rights verbs on the selection, the same verbs as the Segment menu (`source.editor.set-*`) | **Segments pane:** many segments at once. Every instance of a sign, every line by hand B, the order list for a whole page when it is long (`source.segments-pane.same-actions`) |
| The path and up / down / next / previous | The document tabs (Knowledge, Notes, Artifacts, Info): kept, shown when the selection is the source |

The Artifacts tab's line-region rows are the Order section at the page level seen through one
artifact. Once the Order section exists they fold into it; Join stays (#5115), as a verb on the
selection.

## 7. Questions for the maintainer

1. **"The Inspector shows and does not edit"** (`segment-editor.md`) against the rulings that it
   reorders (Q5) and joins (#5115). **Proposed reading:** the Inspector edits no *content*. It never
   types a reading and never draws a shape. It does offer *verbs on the selection*: choose a
   reading, reorder, set a fact. Is that right?
2. **The path head**: a breadcrumb path, with the same sections at every level. Or a different
   layout per level?
3. **Word order under a line**: reorderable in the Order section, or shown only, since a word's
   place follows the line's direction?
4. **The document tabs**: keep the eleven tabs as the source level's view, or fold them into the
   same nine sections? (Knowledge folds into Links; Info into Making.)

## 8. Ruled 2026-09-27

1. **Verbs, not typing.** The Inspector never types a reading or draws a shape. It offers verbs on the
   selection: reorder, Join, set language or hand, attribute. `segment-editor.md`'s "shows and does not
   edit" is reworded to say this.
2. **A path plus the same sections at every level**, empty sections hidden, as proposed.
3. **Words can be reordered under a line**, with the same verbs as lines: drag, ⌥⌘↑/↓, start and end.
   The same `ReadingOrderStore` does it.
4. **The eleven document tabs stay** for the source level. The Artifacts tab's region rows fold into
   Order.

**Build order:** first the path head plus the Text and Order sections at line, word, block and page,
using what exists (readings through the segment routes; `ReadingOrderList`). Then Language & script,
Hands and Making, the facts with engine data behind them.

## Future (ideas, not scheduled)
- (#1853) Inspector attributes as a compact list with click-to-view/edit (progressive disclosure)

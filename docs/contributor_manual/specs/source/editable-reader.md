# The Editable Reader — Design Spec (#5289)

> Milestone: editable-reader
> Manual: TBD — the user manual must explain that the Reader's text is edited in place, what an
> edit becomes (a new reading by you, the earlier one kept), what happens to a word's box on the
> image, and which views cannot be edited and why.
>
> Design-led. **Status: DRAFT — awaiting the design lead's rulings before tests or code.**
> Written 2026-09-30 from the code and the source-model specs as they stood that day. This spec
> does NOT restate the editing rules already written in
> [`segment-editor.md`](segment-editor.md) (`source.textedit.*`),
> [`line-editor.md`](line-editor.md) (`source.lineeditor.*`) and
> [`readings-and-apparatus.md`](readings-and-apparatus.md) (`source.reading.*`). It names them,
> says what is built, and adds only what #5289 asks for that they do not cover. Where this file
> and those differ, those win until the design lead rules otherwise.

## Intent (the design)

To a person reading, the Reader's text is a document. If a word is wrong they expect to click
and fix it, the way Descript lets you edit a recording by editing its transcript: you edit the
text, and the edit flows back to what the text was made from. Here the text is made from
**segments** (regions, lines, words, each a shape on the image with readings), so a fix in the
Reader is a new reading on a segment, by the person, undoable, with the earlier reading kept.
When the edit changes words (splits one, joins two, adds one, removes one), the word boxes on the
image must still be right afterwards.

The same holds for any text in the Reader that is someone's or some model's reading of the
source: the transcription, a translation, a transliteration, a normalised text. Text that is not
a reading (a comparison, a run log, a table) is not editable, and the Reader says why.

Lives in: the WebKit Reader (`fichero-server/src/fichero_server/api/templates/document_view.html`, served by
`api/routes/system/views.py`), its bridge (`DocumentKGWebPaneCoordinatorMacOS.swift`,
`ReaderTextEditRunner.swift`, `ReaderTextEdit.swift`), and the engine's audited actions
(`representation.create`, `segment.split`, `segment.merge`, `reading_order.place`).

## Prior art / best practices (don't invent from scratch)

- **Descript** (the maintainer's model): the transcript is the editing surface; an edit to the
  text is an edit to the media; word timing is kept by alignment, and a corrected word keeps its
  place in the recording. The analogue here: a corrected word keeps its place on the page.
- **Transkribus and eScriptorium** edit a line's text beside or over the line image; word boxes,
  where they exist, come from the recogniser or from a proportional cut of the line. Neither
  re-measures a word when its text changes. eScriptorium stores one transcription per line per
  "transcription layer", which is this model's set of readings.
- **PAGE XML and ALTO** carry `TextLine` and `Word` with their own coordinates and text. PAGE
  allows a `custom` attribute, which `line-editor.md` already uses to mark estimated geometry.
- **Forced alignment** (aligning known text to ink or audio) is the established way to recover
  word positions from a corrected line. It needs a recognition model per script. We do not build
  one here; a proportional estimate that is always labelled as an estimate is the honest floor,
  and a later alignment pass can replace estimates with measurements.
- **`difflib.SequenceMatcher`** token alignment is already the engine's word-diff
  (`views.diff_word_tokens`) and already chosen for `source.textedit.a-word-leaves-the-line`.
  We reuse it.
- What we do differently from a word processor: nothing is overwritten. A correction is a new
  reading that outranks the one it corrects (`source.reading.corrections-are-new`, #5175).

## What is built today (2026-09-30)

- **The Reader's Content view is already editable by line, on the Mac, with no mode.** A page's
  text is `contenteditable` when the page has a line map and the engine is reachable
  (`document_view.html`, `makeEditable`). Typing on a line saves one new line reading through
  `representation.create`; Return splits the line (`segment.split`); Backspace at a line's start
  joins it to the one before (`segment.merge`); moving a line is `reading_order.place`. Each is
  one audited action and one ⌘Z. A stale edit (409) keeps the person's words.
- **It is silent when it is not editable.** A page has no line map when it has no working pass,
  when a person edited its page text directly, or when the cached text is stale
  (`views.page_line_map`). Then the text does not accept typing and nothing says so.
- **Only the Content view gets a line map.** Translation, summary, conversion, a named artifact
  and the compare view are served without one (`views.py`), so none can be edited in the Reader.
- **iPhone and iPad cannot edit.** The iOS bridge handles none of the edit messages.
- **Words are untouched by an edit.** A Reader edit writes one line-level reading. Word segments
  and their readings are not changed. Once a person has a reading on a line, the page reads the
  line from that reading and skips its words (#5224, commit `61d332e63`; the matching behavior
  `source.textedit.an-edited-line-reads-from-itself` is still tagged GAP in `segment-editor.md`).
- **Retiring a word whose text left the line is ruled (2026-09-28, #5190) and not built.**
- **The only geometry ever worked out from text is the split's cut:** one rectangle cut in two at
  `offset / length`, both halves marked `metadata.cut = "estimated"` (`segments.py`,
  `estimated_cut`). The app does not read that mark.
- **A second writer exists.** The native page pane in the PDF reading view
  (`PageContentPane+Editing.swift`) has an Edit button that saves the whole page's text straight
  to the document, outside segments, readings, audit and undo.
- **A translation is an artifact, whole-page.** `artifact.translate` translates the page text in
  one call and stores one artifact. It can be edited only in the Inspector's artifact pane
  (`artifact.update`), which overwrites it. `translation` is also a reading kind the engine
  accepts, but nothing creates one.
- **The Inspector's Text section can edit a reading** (#5201) through the Reader's own runner.

## Behaviors

Tags: [OK] built · [PARTIAL] partly built · [MISSING] not built.

### The text is editable wherever it is a reading

- `reader.edit.content-is-editable-by-line` [PARTIAL] (#5289; the rules are `source.textedit.*`,
  #5001) — in the Content view a person types on a line and the line has a new reading by them.
  Built on the Mac; the open parts are the ones `segment-editor.md` lists.
- `reader.edit.a-page-without-lines-is-editable` [MISSING] (#5289) — a page that has text and no
  line map is still editable. The edit is one page-level reading by the person that corrects the
  text shown, through `representation.create` with no segment. The page has no boxes before and
  none after.
- `reader.edit.no-second-writer` [MISSING] (#5289) — the native page pane's Edit saves through
  the same runner as the Reader. Nothing writes a page's text to the document directly.
  (`source.lineeditor.one-path`, #5209, says the same of every home.)
- `reader.edit.translation-is-editable` [MISSING] (#5289) — in the Translation view a person
  edits the translation in place. The edit is a new reading of kind `translation` by the person
  that names the machine's translation as what it corrects. The machine's text is kept and can be
  shown again. The Reader shows the reading that counts.
- `reader.edit.other-readings-are-editable` [MISSING] (#5289) — the same for any view whose text
  is a reading kind of the source: transliteration, normalised text, description.
- `reader.edit.ios-and-ipad` [MISSING] (#5289) — the iPad and iPhone Readers send the same edit
  messages through the same runner. No second implementation.

### What is not editable, and saying so

- `reader.edit.not-a-reading-is-read-only` [MISSING] (#5289) — the compare view, a workflow run
  log, a table and the knowledge lenses are not editable in the Reader.
- `reader.edit.read-only-says-why` [PARTIAL] (#5289) — typing into text that cannot be edited
  shows one line naming the reason: the engine is out of reach (built), this view compares
  readings, this text is a table, the page's text is being refreshed. Never a beep and never
  nothing.
- `reader.edit.a-summary-is-the-models` [MISSING] (#5289) — a summary or a conversion is a
  model's product about the text, not a reading of the source. Whether a person may edit one is
  open question 4; until ruled, it is read-only and says so.

### Words and their boxes

The line rules stand as written: `source.textedit.word-spans-in-the-line`,
`source.textedit.a-word-leaves-the-line`, `source.textedit.retiring-is-part-of-the-edit` (#5190)
and `source.lineeditor.estimated-words` (#5212). These add what each kind of word edit does to
geometry. All of it happens inside the one `representation.create` the edit already is: one
audit row, one ⌘Z, worked out by the engine.

- `reader.edit.an-unchanged-word-keeps-its-box` [MISSING] (#5289, #5190) — a word whose token is
  untouched by the edit keeps its segment, its measured shape and its reading, and takes its new
  span in the new line text.
- `reader.edit.a-removed-word-keeps-its-ink` [MISSING] (#5289, #5190) — a word whose text is
  deleted has its reading retired. Its segment and shape stay: the ink is still on the page.
- `reader.edit.an-added-word-is-estimated` [MISSING] (#5289, #5212) — a word typed where there
  was none has no box of its own. It is shown laid along the line between its neighbours, by
  its share of the characters, dashed and labelled estimated. It is never stored as a measurement.
- `reader.edit.a-corrected-word-keeps-its-box` [MISSING] (#5289) — a word replaced by exactly one
  word (one token for one token) keeps its segment and measured shape and gets a new word reading
  by the person that corrects the old one. **This differs from the default in
  `source.textedit.a-word-leaves-the-line`, where a changed word leaves.** Open question 1.
- `reader.edit.a-split-word-is-cut` [MISSING] (#5289) — one word typed as two becomes two word
  segments, the original shape cut at the character offset, both marked estimated, as Return
  already cuts a line.
- `reader.edit.joined-words-are-joined` [MISSING] (#5289) — two words typed as one become one word
  segment whose shape is the two shapes joined, by the same rule `segment.merge` uses for lines.
  The shape stays measured.
- `reader.edit.an-estimate-can-be-made-real` [MISSING] (#5212) — dragging or reshaping an
  estimated word gives it a measured shape (`source.lineeditor.estimated-words`).
- `reader.edit.the-image-follows` [MISSING] (#5289) — after an edit the Source view draws the
  line's words as they now are, without a reload of the page: measured solid, estimated dashed,
  retired hollow.
- `reader.edit.a-line-without-words-has-none-made` [MISSING] (#5289) — an edit to a line that has
  no word segments creates none. Word boxes are kept right; they are not invented.

### Structure, undo, other people

- `reader.edit.return-and-backspace` [PARTIAL] (#5001) — Return splits a line and Backspace joins
  two, as built (`source.textedit.return-splits-the-line`, `…backspace-joins-in-reading-order`).
  When the line has word segments the cut falls between words.
- `reader.edit.one-undo-per-edit` [PARTIAL] (#5001) — a run of typing on one line is one reading,
  one audit record and one ⌘Z; the word changes it caused come back with it.
- `reader.edit.someone-elses-edit` [PARTIAL] (#5001) — an edit to a line someone else has changed
  since is refused and the person keeps their words (`source.textedit.stale-keeps-your-words`).
- `reader.edit.typing-never-waits` [MISSING] (#5289) — what is typed shows at once. Saving a line
  redraws that page only, never the whole Reader, on a document of any length. A budget for the
  save is open question 6.

## Where the code and the specs disagree

1. `source.textedit.an-edited-line-reads-from-itself` is tagged GAP (#5190) and is built and
   tested under #5224 (`61d332e63`). It should be retagged by whoever owns `segment-editor.md`.
2. `source.textedit.no-second-path` and `source.lineeditor.one-path` say no home has a writer of
   its own. The native page pane has one.
3. The source model calls a translation a reading. The engine stores it as an artifact and
   nothing creates a translation reading.
4. `line-editor.md` has the engine mark estimated words `geometry: estimated`. The one estimate
   the engine makes today is marked `cut: estimated`, and the app reads neither.
5. `ReaderLens.swift` says translation "does not exist" as a lens; it exists as a choice in the
   Page tab's representation menu.

## Test matrix

Tests follow the rulings. This is what would pin the design.

| Leg | This surface? | Pins | File |
|-----|---------------|------|------|
| Backend (pytest) | y | each word-edit kind (unchanged, removed, added, corrected, split, joined) gives the stated segments, shapes, marks and readings, from one action and undone by one undo | `fichero-server/tests/unit/api/test_reader_edit_keeps_word_boxes.py` |
| Backend (pytest) | y | a page with no line map takes a page-level reading; a translation edit is a `translation` reading that corrects the machine's and the view serves it | `fichero-server/tests/unit/api/test_reader_edits_any_reading.py` |
| Backend (pytest) | y | real files: a PAGE XML page with words, edited, exports words with the right marks | the formats harness |
| Pure rule (Swift) | y | the read-only reasons; which views are editable | `fichero/Tests/Unit/general/Views/Reader/…` |
| Availability (Swift) | y | the iOS bridge routes every edit message; the native page pane has no writer of its own | same, through the real coordinator |
| MCP | y | an agent's edit goes through the same actions (`source.lineeditor.agent-parity`) | `fichero-mcp/tests/test_mcp_full.py` |
| CLI | n | | |
| Click-around (XCUITest, Mac) | y | type a word, see the box; ⌘Z, see it back | `fichero/Tests/UI/…` |
| iPhone (iOS) | y | the edit path on iPhone | `fichero-ui-ios` plan |
| iPad | y | the edit path on iPad | `fichero-ui-ipad` plan |
| Load (#4634) | y | one line saved on a long document redraws one page, within the budget | `fichero-server/tests/perf/…` |

## Documentation matrix

| Audience | Doc leg | This feature? | Lives in |
|----------|---------|---------------|----------|
| User | user manual + screenshot | y | the maintainer's manual: editing in the Reader |
| Contributor | developer docs | y | this spec; `segment-editor.md`; `line-editor.md` |
| AI / agent | MCP tool description | y | the descriptions of `representation.create`, `segment.split`, `segment.merge` |
| Scripter | CLI `--help` | n | |
| Reference | capability/endpoint reference | y | generated |

## Preview harness

`ReaderEditWordBoxesPreview`: one line drawn over a sample image with its words in each state
(measured, estimated, retired), before and after each of the six word edits, from fixture data.
It is the picture the manual uses.

## Accessibility identifiers

- `reader.page.<id>.text` — a page's editable text
- `reader.readOnlyReason` — the line that says why text cannot be edited
- `source.word.<id>` — a word on the image, with its state (measured, estimated, retired) in its
  accessibility value

## UX completeness

| Control (a11y id) | Label | Tooltip/help text | Localized key | Verified by |
|---|---|---|---|---|
| `reader.readOnlyReason` | the reason itself | none | [MISSING] | [MISSING] |
| `source.word.<id>` | the word's text | Estimated position / Retired, when so | [MISSING] | [MISSING] |

## Open questions for the creative director

1. **A corrected word: keep its box, or retire it?** The written default (2026-09-28) retires a
   word whose text changed at all. #5289 asks that correcting a word updates that word and keeps
   the box right. Recommended: a one-for-one replacement keeps the segment and its measured shape
   and gives the word a corrected reading; anything else (split, join, move, delete) follows the
   rules above.
2. **A moved word.** The written default treats a word moved within its line as removed and
   added: the old box is retired and the new place is an estimate. Recommended: keep that.
3. **A translation edit: a new reading, or overwrite the artifact?** Recommended: a new reading
   that corrects the machine's, so the machine's text and its provenance are kept. That means the
   Translation view reads readings as well as artifacts.
4. **Summaries and conversions.** A person's edit of a model's summary is a new text by the
   person. Should the Reader allow it, as a person's version beside the model's? Recommended: not
   in this spec.
5. **Translation line by line.** A translation is one text for the page. Aligning it to lines, so
   a click in the translation shows the line on the image, is a larger piece of work
   (`representation.pair` exists for pairs). Recommended: a later spec.
6. **The save budget.** Recommended: the typed text never waits, and a line's save returns and
   redraws its page within 300 ms on a page of 60 lines with word boxes. To be measured before
   it is pinned.
7. **A page that gains lines later.** A page edited as one page-level reading and then segmented
   by a model: does the person's reading still count over the model's lines? By the strict-project
   rule it does. Confirm.
8. **iPhone.** Editing on a phone by line is possible; is it wanted, or is the phone read-only by
   design?
9. **Always editable, and accidents.** With no mode, a stray key edits a line. Recommended: no
   lock; ⌘Z, the kept earlier reading and the audit trail are the protection.

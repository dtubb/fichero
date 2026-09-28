# Source Model — The line editor — Design Spec (#5209, #5211, #5212)

> Milestone: source-model
> Manual: TBD — part of "Transcribing a page": typing a manuscript's text line by line, against the
> picture of each line.
>
> Design-led (Testing Constitution). **Status: DRAFT.** Read `segment-editor.md` first (the Reader's
> typing, `source.textedit.*`, and the Inspector's Edit…, #5201). This file adds no new way to WRITE a
> reading: every home below saves through the Reader's one path. Every behaviour is **[GAP]** with its
> issue unless it says otherwise.

## Intent

Daniel, 2026-09-28: transcribing a manuscript means looking at one line of ink and typing what it says,
then the next line, and the next, without hunting for either. eScriptorium's transcription panel and
Transkribus's line editor are built around exactly that pairing: the picture of the line, and a field for
its text, with a key to move on. Fichero already cuts every line's picture (`GET /api/segments/{id}/picture`)
and already saves a typed line as a person's reading with a stale check and ⌘Z (`ReaderTextEditRunner`).
The line editor puts the two together.

It is ONE editor with three homes, so the three can never disagree about how a line is saved:

| Home | Where | Issue |
|---|---|---|
| The Segments pane's strip | a column of line pictures, each with its field under it | #5209 |
| The Preview image | a field opened over the line, on the page itself | #5211 |
| The Inspector | Edit… on the reading that counts (built, #5201) | #5201 |

It fits the ruled three-column workspace (pane linking rulings, 2026-09-19). The Preview is on one side and
the Segments strip in the middle, and the Inspector follows the focused line.

## Conventions taken from eScriptorium and Transkribus

- **The picture sits above its text.** Both tools show the line's image directly above the field that
  holds its transcription, so the eye moves down, not across. Fichero does the same in the strip.
- **Return goes to the next line.** Both move the cursor on to the following line when you finish one, so
  a page is typed without the mouse. Fichero: Return or ↓ at a field's end moves to the next line in the
  page's reading order, and ↑ at a field's start to the previous. ⇧Return inserts nothing. A line is one
  line; splitting it is the Reader's Return in the middle of a line, `source.textedit.*`.
- **A virtual keyboard for what the keyboard lacks.** Both offer a configurable palette of special
  characters. Fichero offers one per script (below).
- **The line's own direction.** eScriptorium lays a line out in its script's direction. Fichero lays each
  field out in the line's RESOLVED direction (`source.editor.labels-in-their-direction`): right to left for
  Syriac, a column for vertical Han.

## Behaviours

- `source.lineeditor.one-path` — **[GAP]** (#5209) every home saves a line the way the Reader does.
  - The message is `ReaderTextEdit.Message.edited`, `basedOn` the reading shown, run through
    `ReaderTextEditRunner`.
  - One field's run of typing is one `representation.create`, a person's correction of the reading shown.
  - It is refused when another reading counts now: stale, nothing written, and Keep Mine / Take Theirs /
    Compare offered as in the Reader.
  - ⌘Z undoes it.

  No home has a writer of its own. The Inspector's Edit… already does this (#5201, `InspectorReadingEdit`).
- `source.lineeditor.strip` — **[GAP]** (#5209) the Segments pane's strip lens becomes the line editor.
  - Each line shows its picture, cut by the engine as the strip already shows it, with an editable field
    directly under it holding the line's counting reading.
  - The field is laid out in the line's resolved direction and set in the line's font
    (`source.fonts.per-script`).
  - A line with no reading shows an empty field, and typing in it is Type a Reading
    (`deleting-words-keeps-ink`).
  - The strip scrolls to keep the focused line in view, and the focused line is the window's selection,
    so the Preview highlights its box and the Inspector follows (`source.textedit.one-selection`).
- `source.lineeditor.moves-by-line` — **[GAP]** (#5209) Return or ↓ at a field's end commits the run and
  moves to the next line of the page's reading order, and ↑ at a field's start moves to the previous one.
  - The order is the named order shown, else as written.
  - At the page's last line, Return moves to the next page's first line when the Preview pages there
    (‹ ›).
  - Tab is left to the system (focus).
- `source.lineeditor.special-characters` — **[GAP]** (#5209) a palette of the characters the script uses
  that a keyboard lacks:
  - MUFI's medieval Latin for Latin pages;
  - the vowel points and diacritics for Syriac and Hebrew;
  - a project's own set, which a project can add to.

  It is opened from the field, and a click inserts at the caret. It shows the recently used characters
  first, and it is drawn in the bundled fonts (`source.fonts.bundled`), so a MUFI character is a glyph,
  not a box. The macOS Character Viewer stays available.
- `source.lineeditor.on-the-image` — **[GAP]** (#5211) double-clicking a line on the Preview image, or
  Return on the selected line, opens a field OVER the line on the page.
  - The field is placed along the line's baseline, in its direction and its font.
  - It saves through the one path (`one-path`). Escape cancels it; Return commits and moves to the next
    line (`moves-by-line`).
  - A vertical line's field is a column over the column.
  - Reading mode never opens it. It belongs to Edit Segments, or to a Transcribe preset that turns it on.
- `source.lineeditor.estimated-words` — **[GAP]** (#5212) a word with text but no geometry of its own is
  still shown, laid along its line's baseline. Each word gets its share of the line's length by its share
  of the line's characters, the spaces between words included.
  - It is drawn DASHED and labelled "estimated" in the Inspector and on hover. It is never drawn as
    measured.
  - Dragging it, or any reshape, gives it real geometry through `segment.update`, and it is no longer
    estimated.

  **Decided here: the ENGINE computes the estimate,** as it computes the box cut when Return splits a line
  (the precedent: the split's estimated geometry is the engine's, not the app's). So every surface and
  every export sees the same estimate.
  - The engine serves estimated words as segments marked `geometry: estimated` in their metadata. It
    never stores an estimate as a measurement.
  - PAGE XML carries the mark on the `Word` (`custom="geometry:estimated"`). ALTO and hOCR have nowhere
    to say it, and the export's loss report names each estimated word.

  The engine half goes to the bugs lane (bugs2). The app half draws what is served.
- `source.lineeditor.agent-parity` — **[GAP]** (#5209) everything the line editor does is an existing
  audited action (`representation.create`, `segment.update`), so a script or an agent can do it too.
  `source.editor.agent-parity` applies unchanged.

## Out of scope

- A second writer for any home. The Reader's runner is the only path.
- Recognising the line as you type (suggestions from a model). That is a later layer, #2056.
- Keyboard layouts. The OS switches those; the palette only inserts characters.

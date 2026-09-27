# Build notes: marks, measured against Apple Preview's PDF annotations (slice 13, Q6)

The wireframe ruling of 2026-09-27 (Q6, recorded in `segment-editor.md`): a mark applies to the
SELECTION, or attaches to whatever it is drawn over. Check can check a whole paragraph, star works
like check, and highlight draws over segments. **The target is what Apple Preview supports for PDF
annotations, so PDFKit's annotation types are read before marks are designed, and marks stay
exportable as real PDF annotations.** This file is that reading and a *proposal*; nothing here is
built. Read on disk 2026-09-27 from the macOS 27 SDK (`PDFKit.framework/Headers`).

## 1. What PDFKit has

`PDFAnnotationSubtype` (`PDFAnnotationUtilities.h`), thirteen values:

| Subtype | What it is | Anchored by |
|---|---|---|
| **Highlight**, **Underline**, **StrikeOut** | text markup | `quadrilateralPoints`: one quad per run of text, so a multi-line selection is one annotation |
| **Text** | a sticky note, drawn as an icon | a point; icon one of Comment, Key, Note, Help, NewParagraph, Paragraph, Insert |
| **FreeText** | text written on the page | a rectangle |
| **Line** | a line, with optional line-ending styles (arrows) | two points |
| **Square**, **Circle** | a box or an oval, stroke and optional fill | a rectangle |
| **Ink** | freehand strokes | a list of paths |
| **Stamp** | a named stamp (Approved, Draft …, or any name) | a rectangle |
| **Popup** | the window a note opens in | its parent annotation |
| **Link**, **Widget** | navigation and form fields | chrome, not marks |

Every annotation carries `contents` (its words), `userName` (its author), `modificationDate`,
`color`, a border, and arbitrary keys. Preview's Markup toolbar is these, and nothing else: text
highlight / underline / strike, shapes (Square, Circle, Line with arrows), Sketch and Draw (Ink),
Text (FreeText), Note (Text), Sign (Ink), and the loupe (a view, not an annotation).

## 2. What Fichero has today, and where each goes

`AnnotationKind` (`models/knowledge.py`) and the markup row:

| Fichero today | Anchored by today | PDF export as | Gap |
|---|---|---|---|
| highlight (5 colours) | char range, or bbox, or the selected word boxes | **Highlight** with one quad per selected box run | none in kind; quads to be kept (see 3) |
| underline | as highlight | **Underline** | none now. The app saves it as its own kind (`AnnotationBar`, the canvas); only `PreviewHighlightStyle`'s comment said otherwise, corrected 2026-09-27. The PDF IMPORT folded Underline into highlight; fixed in `c3b99eab9` |
| strikethrough | as highlight | **StrikeOut** | the same, both fixed |
| note (inline margin note) | a point beside the text | **FreeText** (written on the page) or **Text** (an icon that opens); proposal: FreeText, since ours shows its words in place | none |
| bookmark (the star) | a point, or the selection | **Stamp** named `Star` | PDF has no star; a named stamp is the standard way to carry one |
| check (✓ ✓✓ ✓✓✓), paragraph | a paragraph index, or the selection | **Stamp** named `Check`, `Check2`, `Check3` | none |
| line | two points | **Line** | none |
| (none) | -- | **Square**, **Circle** | a box or oval drawn OVER something: today only the Shape tool draws boxes, and in the mode those are segments |
| (none) | -- | **Ink** | freehand: `ink_payload` and `anchor_kind: "ink"` exist on the model and nothing draws them |
| rating, comment | -- | Text with `contents` | not page marks |

## 3. The proposal, in one paragraph

A mark keeps ONE record, `Annotation`, and says what it is attached to in one of two ways, matching
the ruling: **to the selection** (segment ids, plus the character ranges within them) or **to an
area drawn over the page** (its anchor, as today). A highlight, underline or strike over selected
words stores the segments it covers and exports as one PDF markup annotation with a quad per run --
exactly PDFKit's shape, so a multi-line highlight is one mark and not one per line. Check and star on
a selection attach to the selected segments; a check on a region is the paragraph case, now a
segment. Square, Circle and Ink are added as kinds only when a tool draws them. Every kind exports to
the subtype in section 2, with `contents` = its words, `userName` = its author, `color` = its colour.

## 4. Questions for the maintainer

1. **Note:** export as FreeText (the words shown on the page, as ours are) or Text (an icon that
   opens, as Preview's Note is)?
2. **Star and check:** as named Stamps (`Star`, `Check`) -- the PDF-standard way -- accepting that
   another reader shows them as that reader draws stamps?
3. **Shapes and freehand:** add Square, Circle and Ink as mark tools now, or only when asked for?
   (They are in Preview's bar; the Shape tool, while reading, already draws a box.)
4. **Import:** stop folding Underline and StrikeOut into highlight on PDF import? (Recommended: yes,
   they have their own kinds now.) The import also turns Square, Circle and Ink into highlights
   today; they would keep their own kinds once those exist.
